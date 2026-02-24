# CFST Extraction Rules (Single Source of Truth)

Use this file as the only extraction specification.

## 1. Validity Decision

Mark paper as valid only if all are true:
- research object is CFST members
- paper contains physical experiment evidence (test setup, specimen failure photos, or explicit test/experiment tables)
- loading mode is axial compression or eccentric compression (including stub columns)

Mark paper as invalid if it is:
- pure finite element simulation without self-conducted experiment data
- pure theoretical derivation or review paper
- steel-only or concrete-only material study
- beam/joint-only study without CFST column test data

Invalid output shape:

```json
{
  "ref_info": {},
  "Group_A": [],
  "Group_B": [],
  "Group_C": [],
  "is_valid": false,
  "reason": "Not experimental CFST column paper"
}
```

## 2. Group Mapping

- `Group_A` Square/Rectangular:
  - `b`: width
  - `h`: depth
  - `r0`: `0`
- `Group_B` Circular:
  - `b`: diameter
  - `h`: diameter
  - enforce `b == h`
  - `r0 = h / 2`
- `Group_C` Round-ended/Elliptical:
  - `b`: major axis
  - `h`: minor axis
  - enforce `b >= h`
  - `r0 = h / 2`

## 3. Field Dictionary

Metadata:
- `title`: full paper title.
- `authors`: all authors as a list.
- `journal`: journal or conference name (`"Unknown"` if not found).
- `year`: publication year (integer).

Specimen fields:
- `ref_no`: fixed empty string `""` for all rows in this skill (reserved field, do not auto-number)
- `specimen_label`: unique specimen ID/label.
- `fc_value`: concrete compressive strength value in MPa.
- `fc_type`: concrete strength specification text
  - if size is explicitly provided, keep explicit form, for example:
    - `Cube 150`
    - `Cylinder 100x200`
    - `Prism 150x150x300mm`
  - if size is not provided but specimen shape is clear, use one of:
    - `cube`
    - `cylinder`
    - `prism`
  - if only symbolic strength notation appears (for example `f'c`, `fcu`, `fck`) and the paper does not explicitly define specimen type, do NOT infer type from symbol alone; set `fc_type` to `Unknown`
  - symbolic notation (`f'c`, `fcu`, `fck`, etc.) must not be written directly as `fc_type` output
  - do not output synthetic labels that are not directly supported by the paper text/table
- `fy`: steel yield strength in MPa.
- `fcy150`: fixed `""`.
- `r_ratio`: recycled aggregate ratio in percent; use `0` for normal concrete.
- `b`, `h`: section dimensions in mm, mapped by group rules in Section 2.
- `t`: steel tube wall thickness in mm.
- `r0`: external corner radius in mm, mapped by group rules in Section 2.
- `L`: specimen length in mm.
- `e1`, `e2` (mm)
  - `e1`: top-end eccentricity; `e2`: bottom-end eccentricity
  - if only one eccentricity `e` exists, set `e1 = e2 = e`
  - set `e1 = e2 = 0` for axial loading
- `n_exp`: test ultimate/peak load in kN
  - must be experimental value; do not use FE/theoretical values
  - if raw unit is `N` or `MN`, convert to `kN`
- `source_evidence`: page/table localization string
  - baseline format example: `Page [X], Table [Y]`
  - when available, append resolved image references for traceability, for example:
    - `Page [6], Table [2]; setup=images/xxx.jpg; table=table/yyy.jpg`

## 4. Numeric and Rounding Rules

- remove all unit suffixes in final JSON numeric fields
- normalize loads to kN
- run `scripts/safe_calc.py` for conversions and derived values
- any conversion/derived numeric result MUST come from `scripts/safe_calc.py`; do not use mental arithmetic
- guard against OCR confusion (`1` vs `I/l`, `0` vs `O`, misplaced decimal points)
- strict precision target is `0.001` (three decimal places)
- when running validator with `--strict-rounding`, all numeric fields must satisfy `0.001` precision
- example:
  - `r0 = h / 2` must be computed by `safe_calc.py`
  - `0.327 MN -> kN` must be computed by `safe_calc.py` (`0.327 * 1000`)

## 5. Markdown Table Validity Gate

Treat markdown table as invalid (must fallback to image evidence) when any condition holds:
- table is empty or near-empty for required specimen rows/columns
- obvious row/column misalignment exists (label row and value row cannot be one-to-one aligned)
- one cell contains multiple candidate values for one expected scalar field
- specimen label row count mismatches key value columns after basic alignment
- key numeric fields are missing in markdown table but present in related table image

Common invalid examples:
- multi-value cell example:
  - `| Specimen | fc |`
  - `| C1 | 42.1 45.3 |`
- merged-label row example:
  - `| Specimen | n_exp |`
  - `| C1 C2 | 520 |`
- row-shift example:
  - label row and `n_exp` row shifted by one row after OCR
- empty-cell example:
  - required `fy` column appears as blank for most rows

When markdown table is invalid:
- use `table/` image as primary evidence
- if needed, use `*_content_list_v2.json` + markdown context to map to original `images/` path
- rebuild row mapping by visual evidence before writing JSON

## 6. OCR Distortion Handling

Treat these as strong corruption signals:
- merged labels (`C1 C2`, `S5 R1`)
- one cell containing multiple numbers for one row
- misaligned rows between specimen label and value columns

When corruption appears:
- inspect table image evidence
- map values row-by-row by visual evidence
- do not infer split rules by guesswork

## 7. Special Cases and Examples

- Loading setup figure identification:
  - example markdown evidence: `... loading setup is shown in Fig. 2 ... ![](images/abc123.jpg)`
  - action: open `images/abc123.jpg` and determine axial/eccentric mode from image
- Table name mismatch:
  - if markdown says `Table 3` but `table/` filename differs, match by caption keywords first, then by `*_content_list_v2.json` mapping
- Unit ambiguity:
  - if table header is `Load (MN)`, convert to kN via `safe_calc.py` before writing `n_exp`

## 8. Target JSON Shape

Top-level keys must be:
- `is_valid`
- `reason`
- `ref_info`
- `Group_A`
- `Group_B`
- `Group_C`

`reason` rules:
- when `is_valid=true`, `reason` must be non-empty single-line text
- do not include line breaks (`\n`, `\r`) or control characters
- when `is_valid=false`, use fixed value: `Not experimental CFST column paper`
