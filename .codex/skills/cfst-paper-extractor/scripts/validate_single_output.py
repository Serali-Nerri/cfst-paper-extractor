#!/usr/bin/env python3
"""Validate one CFST extraction JSON against single-paper rules."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Any

EPS = 1e-3
FC_TYPE_ALLOWED_SHAPE_ONLY = {"cube", "cylinder", "prism", "unknown"}
FC_TYPE_SIZED_PATTERN = re.compile(
    r"^(cube|cylinder|prism)\s+\d+(\.\d+)?(?:\s*[x×*]\s*\d+(\.\d+)?){0,2}\s*(mm)?$",
    re.IGNORECASE,
)
FC_TYPE_DISALLOWED_SYMBOL_PATTERN = re.compile(r"\b(f'?c|fc'|fcu|fck|fcm|fcd)\b", re.IGNORECASE)

TOP_LEVEL_KEYS = {
    "is_valid",
    "reason",
    "ref_info",
    "Group_A",
    "Group_B",
    "Group_C",
}

SPECIMEN_KEYS = {
    "ref_no",
    "specimen_label",
    "fc_value",
    "fc_type",
    "fy",
    "fcy150",
    "r_ratio",
    "b",
    "h",
    "t",
    "r0",
    "L",
    "e1",
    "e2",
    "n_exp",
    "source_evidence",
}

NUMERIC_FIELDS = {"fc_value", "fy", "r_ratio", "b", "h", "t", "r0", "L", "e1", "e2", "n_exp"}


def _as_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _roughly_equal(a: float, b: float, tol: float = EPS) -> bool:
    return abs(float(a) - float(b)) <= tol


def _has_3dp(value: float) -> bool:
    return abs(round(float(value), 3) - float(value)) <= 1e-6


def _has_control_chars(value: str) -> bool:
    return any(ord(ch) < 32 for ch in value)


def _is_valid_fc_type(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in FC_TYPE_ALLOWED_SHAPE_ONLY:
        return True
    return FC_TYPE_SIZED_PATTERN.fullmatch(text) is not None


def _validate_ref_info(obj: dict[str, Any], errors: list[str], allow_empty: bool = False) -> None:
    if not isinstance(obj, dict):
        errors.append("`ref_info` must be an object.")
        return

    # Invalid-paper payload may intentionally keep bibliographic metadata empty.
    if allow_empty and not obj:
        return

    for key in ("title", "authors", "journal", "year"):
        if key not in obj:
            errors.append(f"`ref_info.{key}` is required.")

    if "title" in obj and not isinstance(obj["title"], str):
        errors.append("`ref_info.title` must be string.")
    if "authors" in obj and not isinstance(obj["authors"], list):
        errors.append("`ref_info.authors` must be list.")
    if "journal" in obj and not isinstance(obj["journal"], str):
        errors.append("`ref_info.journal` must be string.")
    if "year" in obj and not isinstance(obj["year"], int):
        errors.append("`ref_info.year` must be integer.")


def _validate_specimen(
    group_name: str,
    idx: int,
    specimen: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    strict_rounding: bool,
) -> None:
    tag = f"{group_name}[{idx}]"
    if not isinstance(specimen, dict):
        errors.append(f"`{tag}` must be object.")
        return

    missing = SPECIMEN_KEYS - set(specimen.keys())
    if missing:
        errors.append(f"`{tag}` missing keys: {sorted(missing)}")

    for key in NUMERIC_FIELDS:
        if key in specimen and not _is_number(specimen[key]):
            errors.append(f"`{tag}.{key}` must be numeric.")

    if "specimen_label" in specimen and not isinstance(specimen["specimen_label"], str):
        errors.append(f"`{tag}.specimen_label` must be string.")
    if "ref_no" in specimen:
        if not isinstance(specimen["ref_no"], str):
            errors.append(f"`{tag}.ref_no` must be string.")
        elif specimen["ref_no"] != "":
            errors.append(f"`{tag}.ref_no` must be empty string.")
    if "fc_type" in specimen:
        if not isinstance(specimen["fc_type"], str):
            errors.append(f"`{tag}.fc_type` must be string.")
        else:
            fc_type = specimen["fc_type"].strip()
            if not fc_type:
                errors.append(f"`{tag}.fc_type` must be non-empty.")
            else:
                if FC_TYPE_DISALLOWED_SYMBOL_PATTERN.search(fc_type):
                    errors.append(
                        f"`{tag}.fc_type` must not use symbolic notation like f'c/fcu/fck. "
                        "Use cube/cylinder/prism (with optional size) or `Unknown`."
                    )
                elif not _is_valid_fc_type(fc_type):
                    errors.append(
                        f"`{tag}.fc_type` invalid. Allowed forms: cube/cylinder/prism/Unknown "
                        "or sized forms like `Cylinder 100x200`."
                    )
    if "source_evidence" in specimen:
        if not isinstance(specimen["source_evidence"], str):
            errors.append(f"`{tag}.source_evidence` must be string.")
        elif not specimen["source_evidence"].strip():
            errors.append(f"`{tag}.source_evidence` must be non-empty.")
        else:
            lowered = specimen["source_evidence"].lower()
            if "page" not in lowered:
                warnings.append(f"`{tag}.source_evidence` should include page localization.")
            if all(token not in lowered for token in ("table", "fig", "figure", "text section")):
                warnings.append(f"`{tag}.source_evidence` should include table/figure/text locator.")

    if "n_exp" in specimen and _is_number(specimen["n_exp"]) and specimen["n_exp"] <= 0:
        errors.append(f"`{tag}.n_exp` must be > 0.")
    for e_key in ("e1", "e2"):
        if e_key in specimen and _is_number(specimen[e_key]) and specimen[e_key] < 0:
            errors.append(f"`{tag}.{e_key}` must be >= 0.")

    if group_name == "Group_A" and "r0" in specimen and _is_number(specimen["r0"]):
        if not _roughly_equal(specimen["r0"], 0.0):
            errors.append(f"`{tag}.r0` must be 0 for Group_A.")

    if group_name == "Group_B":
        if all(k in specimen and _is_number(specimen[k]) for k in ("b", "h")):
            if not _roughly_equal(specimen["b"], specimen["h"]):
                errors.append(f"`{tag}` must satisfy b == h for Group_B.")
        if all(k in specimen and _is_number(specimen[k]) for k in ("h", "r0")):
            if not _roughly_equal(specimen["r0"], specimen["h"] / 2.0):
                errors.append(f"`{tag}.r0` must equal h/2 for Group_B.")

    if group_name == "Group_C":
        if all(k in specimen and _is_number(specimen[k]) for k in ("b", "h")):
            if specimen["b"] + EPS < specimen["h"]:
                errors.append(f"`{tag}` must satisfy b >= h for Group_C.")
        if all(k in specimen and _is_number(specimen[k]) for k in ("h", "r0")):
            if not _roughly_equal(specimen["r0"], specimen["h"] / 2.0):
                errors.append(f"`{tag}.r0` must equal h/2 for Group_C.")

    for key in NUMERIC_FIELDS:
        if key in specimen and _is_number(specimen[key]) and not _has_3dp(specimen[key]):
            msg = f"`{tag}.{key}` is not rounded to 0.001: {specimen[key]}"
            if strict_rounding:
                errors.append(msg)
            else:
                warnings.append(msg)


def validate_payload(
    payload: dict[str, Any],
    expect_valid: bool | None,
    strict_rounding: bool,
    expect_count: int | None,
) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        return ["Top-level JSON must be object."], warnings, 0

    missing_top = TOP_LEVEL_KEYS - set(payload.keys())
    if missing_top:
        errors.append(f"Missing top-level keys: {sorted(missing_top)}")

    if "is_valid" in payload and not isinstance(payload["is_valid"], bool):
        errors.append("`is_valid` must be boolean.")
    if "reason" in payload and not isinstance(payload["reason"], str):
        errors.append("`reason` must be string.")
    if isinstance(payload.get("reason"), str):
        reason = payload["reason"]
        if payload.get("is_valid") is True and not reason.strip():
            errors.append("`reason` must be non-empty when `is_valid=true`.")
        if "\n" in reason or "\r" in reason:
            errors.append("`reason` must be single-line (no newline characters).")
        if _has_control_chars(reason):
            errors.append("`reason` must not contain control characters.")
        if payload.get("is_valid") is False and reason != "Not experimental CFST column paper":
            errors.append("Invalid-paper `reason` must be `Not experimental CFST column paper`.")

    for group_name in ("Group_A", "Group_B", "Group_C"):
        if group_name in payload and not isinstance(payload[group_name], list):
            errors.append(f"`{group_name}` must be list.")

    if "ref_info" in payload:
        _validate_ref_info(payload["ref_info"], errors, allow_empty=(payload.get("is_valid") is False))

    if expect_valid is not None and "is_valid" in payload and payload["is_valid"] != expect_valid:
        errors.append(f"`is_valid` expected {expect_valid}, got {payload['is_valid']}.")

    total = 0
    label_index: dict[str, list[str]] = defaultdict(list)
    for group_name in ("Group_A", "Group_B", "Group_C"):
        group = payload.get(group_name, [])
        if isinstance(group, list):
            total += len(group)
            for idx, specimen in enumerate(group):
                _validate_specimen(group_name, idx, specimen, errors, warnings, strict_rounding)
                tag = f"{group_name}[{idx}]"
                if isinstance(specimen, dict) and isinstance(specimen.get("specimen_label"), str):
                    label = specimen["specimen_label"].strip()
                    if label:
                        label_index[label].append(tag)

    for label, tags in label_index.items():
        if len(tags) > 1:
            errors.append(f"`specimen_label` duplicated across rows: '{label}' in {tags}.")

    if expect_count is not None and total != expect_count:
        errors.append(f"`specimen` total expected {expect_count}, got {total}.")

    if payload.get("is_valid") is True and total == 0:
        errors.append("`is_valid=true` but specimen count is 0.")
    if payload.get("is_valid") is False and total > 0:
        warnings.append("`is_valid=false` but specimens exist; verify validity decision.")

    return errors, warnings, total


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate single-paper CFST extraction JSON.")
    parser.add_argument("--json-path", required=True, help="Path to extraction JSON file.")
    parser.add_argument(
        "--expect-valid",
        default=None,
        type=_as_bool,
        help="Optional expected value for `is_valid` (true/false).",
    )
    parser.add_argument(
        "--strict-rounding",
        action="store_true",
        help="Fail when numeric fields are not rounded to 0.001.",
    )
    parser.add_argument(
        "--expect-count",
        type=int,
        default=None,
        help="Optional expected total specimen count across Group_A/B/C.",
    )
    args = parser.parse_args()

    json_path = Path(args.json_path)
    if not json_path.exists():
        print(f"[FAIL] JSON file not found: {json_path}")
        return 1

    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[FAIL] Invalid JSON: {exc}")
        return 1

    errors, warnings, total = validate_payload(
        payload,
        args.expect_valid,
        args.strict_rounding,
        args.expect_count,
    )

    print(f"[INFO] Specimen count: {total}")
    if warnings:
        print("[WARN] Validation warnings:")
        for msg in warnings:
            print(f"- {msg}")

    if errors:
        print("[FAIL] Validation errors:")
        for msg in errors:
            print(f"- {msg}")
        return 1

    print("[OK] Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
