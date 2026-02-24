---
name: cfst-paper-extractor
description: Extract structured CFST experimental specimen data from one MinerU-parsed paper folder into Group_A/Group_B/Group_C JSON. Use for one-paper extraction tasks, including preprocessing a raw parsed root into a normalized parsed-with-tables root (full images kept + table folder extracted), then applying deterministic validity and field-mapping rules.
---

# CFST Paper Extractor

## Overview

Extract one CFST paper into strict JSON with:
- validity decision
- bibliographic metadata
- grouped specimen records (`Group_A`, `Group_B`, `Group_C`)

Keep this skill self-contained:
- use only scripts and references inside this skill directory
- do not depend on external helper scripts or external skill files

## Runtime Path Variables (Required)

Use user-provided variables at runtime. Do not hardcode fixed dataset paths in workflow prompts:
- `<raw_parsed_root>`: raw MinerU parsed root (optional, only when preprocess is needed)
- `<parsed_with_tables_root>`: parsed root for extraction stage (`images/` + `table/`)
- `<paper_dir_relpath>`: one paper folder path relative to repo root
- `<output_json_path>`: final output JSON path
- `<expected_specimen_count>`: expected record count when applicable

## Input Layout

Use one required layout for extraction:
- markdown + content-list-v2 + full `images/` + `table/`
- `images/` remains unchanged
- `table/` contains extracted table images renamed by table title

Extraction logic:
- read markdown first
- identify loading setup figure from markdown context and markdown image references
- load the chosen setup figure by markdown path (for example `![](images/xxx.jpg)`)
- when needed, compare markdown table text against table images in `table/`

## Built-in Preprocess Workflow (Raw -> Normalized)

When input is raw parsed root, run this skill script before launching workers:

```bash
python .codex/skills/cfst-paper-extractor/scripts/reorganize_parsed_with_tables.py \
  <raw_parsed_root> \
  -o <parsed_with_tables_root>
```

Dry-run:

```bash
python .codex/skills/cfst-paper-extractor/scripts/reorganize_parsed_with_tables.py \
  <raw_parsed_root> \
  -o <parsed_with_tables_root> \
  --dry-run
```

Script behavior:
- keep all files under `images/`
- extract table images into `table/`
- rename table files from table captions
- copy markdown and `*_content_list_v2.json`

## Mandatory Agent Model

Use a parent-child model for every extraction task:

1. Parent agent is only orchestrator and reviewer.
2. Parent MUST spawn one worker sub-agent per paper folder.
3. Parent MUST enforce concurrency cap: at most 3 worker sub-agents running at the same time.
4. Each worker MUST process exactly one paper folder.
5. Worker MUST complete extraction, calculation, validation, and JSON write for its own folder.
6. Parent MUST run git preflight first; if current directory is not a git repository, stop and report.
7. Parent preflight is limited to git/path checks and optional script-based preprocess; parent MUST NOT manually read raw paper markdown/json/images.
8. Parent MUST NOT read raw paper markdown/json/images once workers are launched.
9. Parent waits for worker results, records pass/fail, and retries only failed workers.

## Git Repository Gate (Required, No Fallback)

Run before any worker launch:

```bash
git rev-parse --is-inside-work-tree
```

If this fails:
- do not continue extraction
- report current directory is not a git repository
- ask user to initialize git first, then rerun skill

## Worker Runtime Isolation (Required via Git Worktree + Bubblewrap)

For each paper folder, parent MUST allocate one dedicated git worktree and branch. Plain `workdir` isolation without worktree is not allowed.
Parent MUST then launch the worker command through `scripts/worker_sandbox.py`.
Direct worker execution without the sandbox launcher is forbidden.

Create one worker worktree:

```bash
python .codex/skills/cfst-paper-extractor/scripts/git_worktree_isolation.py create \
  --paper-dir <paper_dir_relpath>
```

Returned JSON includes:
- `worktree_path`
- `branch`
- `paper_rel`
- `skill_rel`
- `output_dir`
- `sandbox_allowed_rw`
- `sandbox_allowed_ro`
- `sandbox_entry_cwd`

Use `worktree_path` as worker `workdir` when invoking the sandbox launcher.

Launch worker command in sandbox:

```bash
python .codex/skills/cfst-paper-extractor/scripts/worker_sandbox.py \
  --worktree-path <worker_worktree_path> \
  --paper-dir-relpath <paper_rel> \
  --skill-dir-relpath <skill_rel> \
  --output-dir <output_dir> \
  -- <worker_command>
```

Sandbox contract:
- `sandbox_allowed_rw` is the only writable host path set
- `sandbox_allowed_ro` is the only skill-policy readable host path set
- worker process gets `CFST_SANDBOX=1`
- if `bwrap` is unavailable or sandbox startup fails, stop immediately (no fallback to soft isolation)

Worker read scope is enforced by filesystem sandbox:
- RW: `./<paper_dir_relpath>/`, `./<output_dir>/`
- RO: `./.codex/skills/cfst-paper-extractor/SKILL.md`
- RO: `./.codex/skills/cfst-paper-extractor/references/*`
- RO: `./.codex/skills/cfst-paper-extractor/scripts/*`

Expected paper-local files:
- `<paper_token>.md`
- `<paper_token>_content_list_v2.json`
- `images/`
- `table/`

After worker finishes, parent cleans up:

```bash
python .codex/skills/cfst-paper-extractor/scripts/git_worktree_isolation.py remove \
  --worktree-path <worker_worktree_path> \
  --branch <worker_branch> \
  --delete-branch
```

## Retry Strategy

Use deterministic retry at worker level:

1. First run: worker performs full extraction and validation.
2. If validation fails: worker fixes issues and reruns validation once.
3. If still failing: worker returns failure reason and intermediate JSON path.
4. Parent may respawn failed paper worker at most one additional time with focused correction prompt.

## Worker Extraction Workflow (Single Paper)

1. Read `references/extraction-rules.md` before extracting fields.
2. Read `references/single-flow.md` and follow the same control pattern.
3. Run validity gate first (CFST object + physical test evidence + axial/eccentric compression mode).
4. If invalid, stop immediately and output only:
- `is_valid=false`
- `reason="Not experimental CFST column paper"`
- `ref_info={}`
- `Group_A=[]`, `Group_B=[]`, `Group_C=[]`
5. Only when valid, read markdown for global context and specimen/table candidates.
6. Determine loading mode from markdown-linked setup figure:
- find loading-setup related context in markdown text (caption/nearby paragraph)
- identify the referenced image path in markdown (for example `![](images/xxx.jpg)`)
- open that referenced image file under paper folder and decide loading mode from visual evidence
- do not infer loading mode from text alone when setup image evidence exists
7. Detect and repair table corruption from OCR/markdown:
- treat merged specimen labels (for example, multi-label single cells) as high-risk corruption
- if corruption appears, inspect table image evidence and re-align rows by visual evidence
- locate target table image in `table/` by table title/file name first
- if title-based lookup fails, use markdown/context + `*_content_list_v2.json` to map and fallback to image path under `images/`
- do not split merged values by guesswork
8. Complete image evidence usage:
- loading mode must come from the markdown-linked setup figure in `images/`
- use `table/` as primary source for table-image verification when markdown table is ambiguous or corrupted
9. Compute unit conversions and derived values explicitly:
- use deterministic calculations for `r0`, unit normalization, and geometry conversion
- run `scripts/safe_calc.py` for every numeric transformation (mandatory; no mental arithmetic)
- keep numeric values as plain numbers (no unit suffix), rounded to `0.001`
10. Build final JSON exactly with keys:
- `is_valid`, `reason`, `ref_info`, `Group_A`, `Group_B`, `Group_C`
11. Validate output with `scripts/validate_single_output.py`.
12. Write JSON to `<output_json_path>`.
13. Return concise status summary to parent.

## Calculation Script

Run deterministic calculations with:

```bash
python .codex/skills/cfst-paper-extractor/scripts/safe_calc.py "<expression>"
python .codex/skills/cfst-paper-extractor/scripts/safe_calc.py "<expression>" --round 3
```

Use for:
- `r0 = h / 2` in Group_B and Group_C
- unit conversion (for example MN -> kN)
- derived geometry values
- precision normalization to `0.001`

## Validation

Validate valid-paper output:

```bash
python .codex/skills/cfst-paper-extractor/scripts/validate_single_output.py \
  --json-path <output_json_path> \
  --expect-valid true \
  --expect-count <expected_specimen_count> \
  --strict-rounding
```

`--strict-rounding` enforces precision `0.001` (three decimal places).

Validate invalid-paper output:

```bash
python .codex/skills/cfst-paper-extractor/scripts/validate_single_output.py \
  --json-path <output_json_path> \
  --expect-valid false
```

## Output Commit And Push Policy (Required)

For batch extraction:
- every 10 processed papers: create one checkpoint commit
- every 20 processed papers: push
- each checkpoint commit MUST include only files under output directory

Run policy script:

```bash
python .codex/skills/cfst-paper-extractor/scripts/checkpoint_output_commits.py \
  --processed-count <processed_count> \
  --commit-every 10 \
  --push-every 20 \
  --output-dir <output_dir> \
  --remote <remote_name>
```

Script hard-fails on:
- non-git directory
- staged files outside output directory

## Parent Orchestration Template

Use this structure for multi-paper execution:

1. Run git preflight; stop on failure.
2. Resolve runtime paths (`<raw_parsed_root>`, `<parsed_with_tables_root>`, target paper folders, output path).
3. If raw parsed root is provided, run preprocess script to produce `<parsed_with_tables_root>`.
4. Enumerate target paper folders.
5. Build a pending-paper queue.
6. Launch workers in batches with a hard cap of 3 active workers:
- create dedicated worktree via `git_worktree_isolation.py create`
- launch worker command through `worker_sandbox.py` (mandatory)
- spawn one worker that runs only the sandboxed command
- assign only that paper path and output path
- when one worker finishes, launch the next pending paper
7. Wait until all queued papers are completed.
8. Retry only failed workers according to retry policy (retry phase also keeps max 3 active workers).
9. Run post-check per worker output:
- valid paper: `--expect-valid true`, optional count, with `--strict-rounding`
- invalid paper: `--expect-valid false`, no count
10. Update processed counter and run `checkpoint_output_commits.py`.
11. Report final per-paper status table.
12. Remove worker worktrees and worker branches.

Tool-call template:

```text
spawn_agent(agent_type="worker", message="<single-paper contract with runtime paths + sandbox launch command>")
wait(ids=["<worker-id>"])
send_input(id="<worker-id>", interrupt=true, message="<focused fix request>")
```

## References

- `references/extraction-rules.md`: field-level extraction rules and validity decision
- `references/single-flow.md`: workflow pattern for single-paper execution
