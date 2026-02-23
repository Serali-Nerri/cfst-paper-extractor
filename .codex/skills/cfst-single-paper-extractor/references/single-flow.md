# Single-Paper Agent Flow Pattern

Use this pattern as an implementation reference for one-paper extraction.

## Control Pattern

1. Input guard:
- verify the paper folder exists
- verify markdown, content list JSON, and image directory are present
2. Task setup:
- define one-paper extraction objective
- bind current paper directory as the only data scope
3. Evidence collection:
- read markdown first for global understanding
- list candidate tables/figures and their locations
- inspect images when loading mode or table alignment is uncertain
4. Deterministic normalization:
- normalize units
- compute derived geometric values explicitly with `scripts/safe_calc.py`
- enforce group mapping constraints
5. Structured assembly:
- generate strict JSON with required top-level keys and specimen fields
6. Post-check:
- run `scripts/validate_single_output.py`
- return result only after validation passes (or report violations)

## Mandatory Step Ordering

1. Read markdown text first.
2. Confirm loading setup from image evidence.
3. Resolve table corruption before assigning specimen row values.
4. Run calculations for conversions and derived fields.
5. Generate schema-compliant JSON.
6. Validate output.
