# CFST Extraction Rules

## 1. Validity Decision

Mark paper as valid only if all are true:
- Research object is CFST members.
- Paper contains physical experiment evidence (test setup, specimen failure photos, or explicit test/experiment tables).
- Loading mode is axial compression or eccentric compression (including stub columns).

Mark paper as invalid if it is:
- Pure finite element simulation without self-conducted experiment data.
- Pure theoretical derivation or review paper.
- Steel-only or concrete-only material study.
- Beam/joint-only study without CFST column test data.

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
- `title`
- `authors` (list)
- `journal` (`"Unknown"` if not found)
- `year` (integer)

Specimen fields:
- `specimen_label`
- `fc_value` (MPa)
- `fc_type`
- `fy` (MPa)
- `r_ratio` (%) and use `0` for normal concrete
- `b`, `h`, `t`, `r0`, `L` (mm)
- `e1`, `e2` (mm)
  - if only one eccentricity `e` exists, set `e1 = e2 = e`
  - set `e1 = e2 = 0` for axial loading
- `n_exp` (kN), must be test ultimate/peak load
- `source_evidence` (for example `Page [X], Table [Y]`)
- `fcy150` fixed `""`

## 4. Numeric Requirements

- Remove all unit suffixes in final JSON numeric fields.
- Normalize loads to kN.
- Run `scripts/safe_calc.py` for conversions and derived values.
- Guard against OCR confusion (`1` vs `I/l`, `0` vs `O`, misplaced decimal points).
- Round to 0.01 when project requires strict rounding.

## 5. OCR Distortion Handling

Treat these as strong corruption signals:
- merged labels (`C1 C2`, `S5 R1`)
- one cell containing multiple numbers for one row
- misaligned rows between specimen label and value columns

When corruption appears:
- inspect original table image
- map values row-by-row by visual evidence
- do not infer split rules by guesswork
