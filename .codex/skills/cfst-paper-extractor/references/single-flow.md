# Single-Paper Worker Flow

Use this file as the worker execution contract for one paper.

## Worker Contract

- Process exactly one paper folder: `<paper_dir_relpath>`.
- Run only inside `worker_sandbox.py` runtime (`CFST_SANDBOX=1` must exist).
- Do not read files outside this paper folder, skill references, and skill scripts.
- Return only validated JSON result or a clear failure reason.

## Required Paper Layout

The worker input folder must contain:
- `<paper_token>.md`
- `<paper_token>_content_list_v2.json`
- `images/`
- `table/`

If any required file/folder is missing, fail fast and report the missing path.

## Mandatory Execution Order

1. Input guard:
- assert `CFST_SANDBOX=1`; if missing, fail fast with sandbox-required error
- verify required files/folders exist
- load `references/extraction-rules.md` first

2. Validity gate:
- decide whether paper is valid CFST experimental paper
- if invalid, output fixed invalid JSON shape and stop

3. Markdown-first evidence scan:
- read markdown text before any table extraction
- list candidate loading-setup figure mentions and candidate table mentions

4. Loading setup resolution (hard rule):
- identify loading-setup figure from markdown context (caption or nearby paragraph)
- locate markdown image reference path, for example `![](images/xxx.jpg)`
- open that exact referenced image file under paper folder
- decide loading mode from image evidence
- do not decide loading mode from text alone when setup image exists

5. Table evidence resolution:
- use `table/` as primary source for table images
- locate table image by table title and filename first
- if title match fails, use markdown context + `*_content_list_v2.json` path mapping
- if still unresolved, fallback to mapped image under `images/`
- treat markdown table as invalid and switch to image-first extraction when any of these appears:
  - empty key cells in required columns
  - row/column misalignment
  - multiple values in one scalar cell
  - merged specimen labels

6. OCR corruption recovery:
- treat merged labels or multi-value row cells as corruption risk
- realign row values using table-image visual evidence
- do not split merged values by guesswork

7. Deterministic normalization:
- run all numeric conversions and derived values with `scripts/safe_calc.py`
- do not use mental arithmetic for conversion or derived geometry values
- enforce numeric precision to `0.001`
- enforce group geometry mapping and constraints
- enforce `ref_no=""` for every specimen row (no auto numbering)
- set `fc_type` from explicit concrete specification text:
  - keep size when provided (for example `Cylinder 100x200`, `Cube 150`, `Prism 150x150x300mm`)
  - if size is absent but shape is known, use `cylinder` / `cube` / `prism`
  - do not infer type from symbols alone (`f'c`, `fcu`, `fck`)
  - if symbol exists but type is not explicitly defined in text/table notes, set `fc_type=Unknown`
  - do not output symbols themselves as `fc_type`

## Special-Case Examples

- Loading setup:
  - markdown snippet: `... setup shown in Fig. 4 ... ![](images/f1.jpg)`
  - action: read `images/f1.jpg`, decide loading mode from image
- Invalid markdown table:
  - row example: `| C1 | 43.2 46.1 |`
  - action: treat as invalid markdown table and recover from `table/` image evidence
- Unit conversion:
  - value example: `0.245 (MN)`
  - action: compute `n_exp` in kN with `safe_calc.py` (`0.245 * 1000`)

8. JSON assembly:
- output keys must be exactly:
  - `is_valid`, `reason`, `ref_info`, `Group_A`, `Group_B`, `Group_C`
- keep numeric fields unit-free
- when `is_valid=true`, `reason` must be non-empty single-line text (no newline/control chars)
- `source_evidence` must at least include page/table localization; include setup/table image references when available

9. Validation:
- run `scripts/validate_single_output.py` on produced JSON
- return success only when validation passes

## Failure Output Rules

If invalid paper:
- `is_valid=false`
- `reason="Not experimental CFST column paper"`
- `ref_info={}`
- `Group_A=[]`, `Group_B=[]`, `Group_C=[]`

If processing failure:
- return concise error with missing evidence or validation error
- include intermediate output path when available
