---
name: cfst-single-paper-extractor
description: Extract structured CFST experimental specimen data from a single parsed paper folder into Group_A/Group_B/Group_C JSON. Use when the task is one-paper extraction (not batch), especially with folders like data/[A1-2]/ containing markdown text, content-list JSON, and images. Follow rules from built-in references and a cfst-ex-inspired agent workflow pattern.
---

# CFST Single Paper Extractor

## Overview

Extract one CFST paper into a strict structured JSON with validity decision, bibliographic metadata, and grouped specimen records. Use this skill as a self-contained Codex workflow and enforce rule-based field mapping from built-in references.

## Required Inputs

Prepare one parsed paper directory with the following files:
- Main markdown text (for example `data/[A1-2]/[A1-2].md`)
- Content list JSON (for example `data/[A1-2]/[A1-2]_content_list.json`)
- Image directory used by markdown (for example `data/[A1-2]/images/`)

## Mandatory Agent Model

Use a parent-child model for every extraction task:

1. Parent agent is only an orchestrator and reviewer.
2. Parent agent MUST spawn one worker sub-agent per paper folder.
3. Each worker sub-agent MUST process exactly one paper folder.
4. Worker sub-agent MUST complete extraction, calculation, validation, and JSON write for its own folder.
5. Parent MUST run git preflight first; if current directory is not a git repository, stop immediately and report this to user.
6. Parent preflight is limited to git/path checks; parent MUST NOT read raw paper markdown/json/images content.
7. Parent agent MUST NOT read raw paper markdown/json/images once workers are launched.
8. Parent agent waits for worker results, records pass/fail status, and only retries failed workers.

This avoids context mixing when multiple papers are processed in parallel.

## Git Repository Gate (Required, No Fallback)

Run before any worker launch:

```bash
git rev-parse --is-inside-work-tree
```

If this command fails:
- do not continue extraction
- report: current directory is not a git repository
- ask user to initialize local git repository first (`git init`, branch/remote setup), then rerun skill

## Worker Directory Isolation (Required via Git Worktree)

For each paper folder, parent MUST allocate one dedicated git worktree and branch. Plain `workdir` isolation without worktree is not allowed.

Create one worker worktree:

```bash
python .codex/skills/cfst-single-paper-extractor/scripts/git_worktree_isolation.py create \
  --paper-dir data/[A1-2]
```

The script prints JSON including:
- `worktree_path`
- `branch`
- `paper_rel`

Use `worktree_path` as the worker command `workdir`.

Worker read scope inside its worktree:
- `./data/[A1-2]/[A1-2].md`
- `./data/[A1-2]/[A1-2]_content_list.json`
- `./data/[A1-2]/images/`
- `./.codex/skills/cfst-single-paper-extractor/references/*`
- `./.codex/skills/cfst-single-paper-extractor/scripts/*`

After worker finishes, parent cleans up:

```bash
python .codex/skills/cfst-single-paper-extractor/scripts/git_worktree_isolation.py remove \
  --worktree-path .codex/worktrees/<worker-folder> \
  --branch <worker-branch> \
  --delete-branch
```

## Retry Strategy

Use deterministic retry at worker level:

1. First run: worker performs full extraction and validation.
2. If validation fails: worker fixes issues and reruns validation once.
3. If still failing: worker returns failure reason and intermediate JSON path.
4. Parent may respawn the failed paper worker at most one additional time with a focused correction prompt.

## Worker Extraction Workflow (Single Paper Task)

1. Read `references/extraction-rules.md` before extracting any field.
2. Read `references/pdf-extraction-spec.md` for full source requirements.
3. Read `references/single-flow.md` and follow the same control pattern as a generic agent pipeline.
4. Run validity gate first (CFST object + physical test evidence + axial/eccentric compression mode).
5. If invalid, stop extraction immediately and output only:
- `is_valid=false`
- `reason="Not experimental CFST column paper"`
- `ref_info={}`
- `Group_A=[]`, `Group_B=[]`, `Group_C=[]`
6. Only when valid, read markdown for global context and specimen/table candidates.
7. Confirm load condition by inspecting the loading setup figure image; do not infer from text alone when image evidence exists.
8. Detect table corruption from OCR/markdown:
- Treat merged specimen labels such as `C1 C2` or `S5 R1` as high-risk corruption.
- If merged labels or multi-value cells appear, inspect the original table image and re-align rows by visual evidence.
- Do not split merged values by guesswork.
9. Compute unit conversions and derived values explicitly:
- Use deterministic calculations for `r0`, unit normalization, and any geometric conversion.
- Run `scripts/safe_calc.py` for every numeric transformation instead of mental arithmetic.
- Keep numeric values as plain numbers (no unit suffixes).
10. Build final JSON exactly with keys:
- `is_valid`, `reason`, `ref_info`, `Group_A`, `Group_B`, `Group_C`
11. Validate output with `scripts/validate_single_output.py`.
12. Write JSON to paper-local output path or user-requested output path.
13. Return only a concise status summary to parent agent.

## Calculation Script

Run deterministic calculations with:

```bash
python .codex/skills/cfst-single-paper-extractor/scripts/safe_calc.py "141.4 / 2"
python .codex/skills/cfst-single-paper-extractor/scripts/safe_calc.py "(2.715 * 1000)" --round 2
```

Use the script for:
- `r0 = h / 2` in Group_B and Group_C
- unit conversion such as `MN -> kN`
- simple derived geometry values

## Validation

Validate an already generated JSON:

```bash
python .codex/skills/cfst-single-paper-extractor/scripts/validate_single_output.py \
  --json-path output/[A1-2].json \
  --expect-valid true \
  --expect-count 14
```

Use `--strict-rounding` to enforce 2-decimal precision as a hard failure.

For invalid-paper output, do not use `--expect-count`:

```bash
python .codex/skills/cfst-single-paper-extractor/scripts/validate_single_output.py \
  --json-path output/[X].json \
  --expect-valid false
```

## Output Commit And Push Policy (Required)

For batch extraction:
- every 10 processed papers: create one checkpoint commit
- every 20 processed papers: push to GitHub
- each checkpoint commit MUST include only files under `output/`

Run policy script from repository root:

```bash
python .codex/skills/cfst-single-paper-extractor/scripts/checkpoint_output_commits.py \
  --processed-count 10 \
  --commit-every 10 \
  --push-every 20 \
  --output-dir output \
  --remote origin
```

The script enforces:
- non-git directory -> hard fail
- staged non-output files -> hard fail
- commit message default: `cfst-output: processed {count} papers`

## Parent Orchestration Template

Use this structure when parent handles multiple papers:

1. Run git preflight. If not git repository, stop and report to user.
2. Enumerate target paper folders.
3. For each paper:
- create dedicated worktree via `git_worktree_isolation.py create`
- spawn one worker with `workdir=<worktree_path>`
- assign only that paper path and output path
4. Wait for worker completion.
5. Retry only failed workers according to retry policy.
6. Run script-based post-check for each worker output (`validate_single_output.py`):
- valid paper: `--expect-valid true`, optional `--expect-count`, plus `--strict-rounding`
- invalid paper: `--expect-valid false` and no `--expect-count`
7. After each successful paper completion, update processed counter and run `checkpoint_output_commits.py`.
8. Report final per-paper status table.
9. Remove worker worktrees and worker branches.

Tool-call template:

```text
spawn_agent(agent_type="worker", message="<single-paper contract>")
wait(ids=["<worker-id>"])
send_input(id="<worker-id>", interrupt=true, message="<fix request>")  # only for retry
```

## References

- `references/extraction-rules.md`: Field-level extraction rules and validity decision.
- `references/pdf-extraction-spec.md`: Full extraction specification embedded inside this skill.
- `references/single-flow.md`: cfst-ex-inspired workflow pattern rewritten as framework-independent steps.
