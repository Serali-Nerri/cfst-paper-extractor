# Repository Guidelines

## Project Structure & Module Organization
This repository centers on one skill: `.codex/skills/cfst-paper-extractor/`.
- `SKILL.md`: end-to-end workflow and runtime contracts.
- `references/`: extraction rules and single-paper flow (`extraction-rules.md`, `single-flow.md`).
- `scripts/`: operational Python tools (`reorganize_parsed_with_tables.py`, `validate_single_output.py`, `safe_calc.py`, git worktree/checkpoint helpers).
- `agents/openai.yaml`: skill interface metadata.

Data folders:
- `cfst_parsed/`: parsed MinerU paper folders used as input examples.
- `output/`: extraction JSON outputs.
- `backup/`: archived scripts/data for reference only; do not treat as the active source of truth.

## Build, Test, and Development Commands
No package build step is defined; run scripts directly with Python.
- Preprocess parsed data:
  - `python .codex/skills/cfst-paper-extractor/scripts/reorganize_parsed_with_tables.py <raw_root> -o <parsed_with_tables_root>`
- Validate extraction output:
  - `python .codex/skills/cfst-paper-extractor/scripts/validate_single_output.py --json-path <out.json> --expect-valid true --strict-rounding`
- Deterministic calculations (required for conversions/derived values):
  - `python .codex/skills/cfst-paper-extractor/scripts/safe_calc.py "0.327*1000" --round 3`

## Coding Style & Naming Conventions
- Language: Python 3, standard library only.
- Use 4-space indentation, type hints, and concise module/function docstrings.
- Prefer `snake_case` for files, functions, and variables; keep CLI flags long-form and explicit.
- Keep scripts deterministic and side-effect aware (copy/validate, avoid in-place mutation of source parsed data).

## Testing Guidelines
- There is no pytest suite in this repo; validation is script-driven.
- Treat `validate_single_output.py` as the primary test gate for JSON schema, numeric constraints, and `0.001` precision.
- When changing extraction logic, run at least one end-to-end sample: preprocess -> extract -> validate.

## Commit & Pull Request Guidelines
- Git history is minimal (currently `init commit`), so follow concise, imperative commit messages.
- Recommended style: `<scope>: <what changed>` (e.g., `scripts: tighten 0.001 rounding checks`).
- PRs should include:
  - purpose and impacted paths,
  - representative command(s) run,
  - before/after behavior (or sample JSON diff),
  - any rule changes in `references/`.
