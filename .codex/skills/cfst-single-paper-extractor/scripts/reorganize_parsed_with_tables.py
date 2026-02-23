#!/usr/bin/env python3
"""Normalize raw MinerU parsed papers into a table-augmented layout.

Output per paper:
1) keep full images/ unchanged
2) copy table images into table/
3) rename table files by caption-derived title
4) keep markdown + *_content_list_v2.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


INVALID_FILENAME_CHARS = re.compile(r"[\\/:*?\"<>|]+")
WHITESPACE = re.compile(r"\s+")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def find_parse_dir(src_dir: Path) -> Path | None:
    """Find parse leaf directory, preferring hybrid_auto over auto."""
    hybrid_dirs = sorted(src_dir.rglob("hybrid_auto"))
    if hybrid_dirs:
        return hybrid_dirs[0]

    auto_dirs = sorted(src_dir.rglob("auto"))
    if auto_dirs:
        return auto_dirs[0]

    return None


def infer_paper_id(folder_name: str) -> str:
    """Infer paper id from folder name without hardcoded dataset pattern."""
    bracket_match = re.search(r"\[([^\[\]]+)\]", folder_name)
    if bracket_match:
        return bracket_match.group(1).strip()

    if "__" in folder_name:
        head = folder_name.split("__", 1)[0].strip()
        if head:
            return head.strip("[] ")

    fallback = folder_name.strip().strip("[] ")
    return fallback or folder_name.strip()


def extract_paper_id(folder_name: str, id_regex: str | None) -> str | None:
    """Extract paper id via optional user regex, else infer from folder name."""
    if not id_regex:
        return infer_paper_id(folder_name)

    try:
        match = re.search(id_regex, folder_name)
    except re.error:
        return None
    if not match:
        return None

    group_dict = match.groupdict()
    if "id" in group_dict and group_dict["id"]:
        return group_dict["id"].strip()
    if match.groups():
        return match.group(1).strip()
    return match.group(0).strip()


def caption_from_nodes(nodes: Any) -> str:
    if not isinstance(nodes, list):
        return ""

    parts: list[str] = []
    for node in nodes:
        if isinstance(node, dict):
            content = node.get("content")
            if isinstance(content, str):
                parts.append(content)
        elif isinstance(node, str):
            parts.append(node)
    return "".join(parts).strip()


def parse_legacy_table_item(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("type") != "table":
        return None

    img_path = item.get("img_path")
    if not isinstance(img_path, str) or not img_path:
        return None

    table_caption = item.get("table_caption")
    caption = caption_from_nodes(table_caption) if isinstance(table_caption, list) else str(table_caption or "").strip()
    page_idx = item.get("page_idx")
    if not isinstance(page_idx, int):
        page_idx = None

    return {
        "img_path": img_path,
        "caption": caption,
        "page_idx": page_idx,
        "source": "legacy",
    }


def iter_v2_nodes(node: Any):
    if isinstance(node, list):
        for item in node:
            yield from iter_v2_nodes(item)
    elif isinstance(node, dict):
        yield node
        for value in node.values():
            yield from iter_v2_nodes(value)


def parse_v2_table_items(content_v2: Any) -> list[dict[str, Any]]:
    if not isinstance(content_v2, list):
        return []

    parsed: list[dict[str, Any]] = []
    for page_idx, page in enumerate(content_v2):
        for item in iter_v2_nodes(page):
            if not isinstance(item, dict) or item.get("type") != "table":
                continue

            content = item.get("content")
            if not isinstance(content, dict):
                continue

            image_source = content.get("image_source")
            if not isinstance(image_source, dict):
                continue

            img_path = image_source.get("path")
            if not isinstance(img_path, str) or not img_path:
                continue

            caption = caption_from_nodes(content.get("table_caption"))
            parsed.append(
                {
                    "img_path": img_path,
                    "caption": caption,
                    "page_idx": page_idx,
                    "source": "v2",
                }
            )

    return parsed


def collect_table_images(legacy_content: Any, v2_content: Any) -> list[dict[str, Any]]:
    """Merge legacy and v2 table image records with stable ordering."""
    merged: dict[str, dict[str, Any]] = {}
    seen_order: list[str] = []

    def upsert(record: dict[str, Any]) -> None:
        img_path = record["img_path"]
        caption = str(record.get("caption", "")).strip()
        page_idx = record.get("page_idx")
        source = record.get("source", "unknown")

        existing = merged.get(img_path)
        if existing is None:
            merged[img_path] = {
                "img_path": img_path,
                "caption": caption,
                "page_idx": page_idx if isinstance(page_idx, int) else None,
                "source": source,
            }
            seen_order.append(img_path)
            return

        if len(caption) > len(existing["caption"]):
            existing["caption"] = caption
            existing["source"] = source
        if existing["page_idx"] is None and isinstance(page_idx, int):
            existing["page_idx"] = page_idx

    if isinstance(legacy_content, list):
        for item in legacy_content:
            if not isinstance(item, dict):
                continue
            parsed = parse_legacy_table_item(item)
            if parsed:
                upsert(parsed)

    for parsed in parse_v2_table_items(v2_content):
        upsert(parsed)

    order_index = {img: idx for idx, img in enumerate(seen_order)}
    return sorted(
        merged.values(),
        key=lambda item: (
            item["page_idx"] if isinstance(item["page_idx"], int) else 10**9,
            order_index.get(item["img_path"], 10**9),
        ),
    )


def sanitize_table_title(title: str) -> str:
    cleaned = WHITESPACE.sub(" ", title).strip()
    cleaned = INVALID_FILENAME_CHARS.sub(" ", cleaned)
    cleaned = WHITESPACE.sub(" ", cleaned).strip(" .")
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rstrip(" .")
    return cleaned


def unique_filename(base_name: str, suffix: str, used: set[str]) -> str:
    if not base_name:
        base_name = "table"
    candidate = f"{base_name}{suffix}"
    idx = 2
    while candidate in used:
        candidate = f"{base_name}_{idx}{suffix}"
        idx += 1
    used.add(candidate)
    return candidate


def copy_images_dir(src_images: Path, dst_images: Path, dry_run: bool) -> int:
    if not src_images.exists() or not src_images.is_dir():
        return 0

    image_count = sum(1 for p in src_images.rglob("*") if p.is_file())
    if dry_run:
        return image_count

    shutil.copytree(src_images, dst_images, dirs_exist_ok=True)
    return image_count


def resolve_table_image_path(parse_dir: Path, raw_img_path: str) -> Path | None:
    path = Path(raw_img_path)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        normalized = raw_img_path.strip()
        normalized = re.sub(r"^\./", "", normalized)
        normalized = re.sub(r"^\.\\", "", normalized)
        rel_path = Path(normalized)
        candidates.append(parse_dir / rel_path)
        candidates.append(parse_dir / "images" / rel_path.name)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def copy_table_images(parse_dir: Path, table_items: list[dict[str, Any]], dst_table_dir: Path, dry_run: bool) -> tuple[int, int]:
    copied = 0
    missing = 0
    used_names: set[str] = set()

    if not dry_run:
        dst_table_dir.mkdir(parents=True, exist_ok=True)

    for idx, item in enumerate(table_items, start=1):
        img_path = str(item.get("img_path", "")).strip()
        if not img_path:
            missing += 1
            continue

        src = resolve_table_image_path(parse_dir, img_path)
        if src is None:
            missing += 1
            continue

        caption = str(item.get("caption", "")).strip()
        suffix = src.suffix or ".jpg"
        base_name = sanitize_table_title(caption) or f"table_{idx}"
        filename = unique_filename(base_name, suffix, used_names)
        dst = dst_table_dir / filename

        if not dry_run:
            shutil.copy2(src, dst)
        copied += 1

    return copied, missing


def reorganize_one_paper(
    src_paper_dir: Path,
    dst_root: Path,
    paper_token: str,
    dry_run: bool,
) -> dict[str, int] | None:
    parse_dir = find_parse_dir(src_paper_dir)
    if parse_dir is None:
        print(f"  [SKIP] parse leaf not found (expect auto/hybrid_auto): {src_paper_dir.name}")
        return None

    md_files = sorted(parse_dir.glob("*.md"))
    legacy_json_files = sorted(parse_dir.glob("*_content_list.json"))
    v2_json_files = sorted(parse_dir.glob("*_content_list_v2.json"))
    images_dir = parse_dir / "images"

    if not md_files:
        print(f"  [SKIP] markdown not found: {src_paper_dir.name}")
        return None
    if not v2_json_files:
        print(f"  [SKIP] *_content_list_v2.json not found: {src_paper_dir.name}")
        return None

    legacy_content = read_json(legacy_json_files[0]) if legacy_json_files else None
    v2_content = read_json(v2_json_files[0])
    table_items = collect_table_images(legacy_content, v2_content)

    paper_dst = dst_root / paper_token
    dst_md = paper_dst / f"{paper_token}.md"
    dst_v2 = paper_dst / f"{paper_token}_content_list_v2.json"
    dst_images = paper_dst / "images"
    dst_table = paper_dst / "table"

    stats = {
        "images_all": 0,
        "tables_detected": len(table_items),
        "tables_copied": 0,
        "tables_missing": 0,
    }

    if not dry_run:
        paper_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(md_files[0], dst_md)
        shutil.copy2(v2_json_files[0], dst_v2)

    stats["images_all"] = copy_images_dir(images_dir, dst_images, dry_run=dry_run)
    copied, missing = copy_table_images(parse_dir, table_items, dst_table, dry_run=dry_run)
    stats["tables_copied"] = copied
    stats["tables_missing"] = missing
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize raw MinerU parsed folders into full-images + table-images layout."
    )
    parser.add_argument("input_dir", type=Path, help="Raw parsed root directory.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output root directory. Default: <input_dir>_with_tables sibling.",
    )
    parser.add_argument(
        "--id-regex",
        default=None,
        help="Optional regex to extract paper id from each source folder name. Use a first group or named group 'id'.",
    )
    parser.add_argument(
        "--name-template",
        default="{paper_id}",
        help="Output paper token template. Example: '{paper_id}' or '[{paper_id}]'.",
    )
    parser.add_argument(
        "--strict-id",
        action="store_true",
        help="Skip folder when id cannot be extracted by --id-regex.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    input_dir: Path = args.input_dir
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"[FAIL] input_dir does not exist or is not a directory: {input_dir}")
        return 2

    output_dir = args.output or input_dir.parent / f"{input_dir.name}_with_tables"
    print(f"Input root: {input_dir}")
    print(f"Output root: {output_dir}")
    print("Output policy: keep markdown + content_list_v2 + full images + extracted table images")
    if args.dry_run:
        print("[DRY RUN]")
    print()

    totals = {
        "papers": 0,
        "images_all": 0,
        "tables_detected": 0,
        "tables_copied": 0,
        "tables_missing": 0,
        "skipped": 0,
    }

    for item in sorted(input_dir.iterdir()):
        if not item.is_dir():
            continue

        paper_id = extract_paper_id(item.name, args.id_regex)
        if not paper_id:
            if args.strict_id:
                print(f"  [SKIP] paper id cannot be extracted: {item.name}")
                totals["skipped"] += 1
                continue
            paper_id = infer_paper_id(item.name)

        try:
            paper_token = args.name_template.format(paper_id=paper_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] invalid --name-template: {exc}")
            return 2

        stats = reorganize_one_paper(item, output_dir, paper_token, dry_run=args.dry_run)
        if stats is None:
            totals["skipped"] += 1
            continue

        totals["papers"] += 1
        totals["images_all"] += stats["images_all"]
        totals["tables_detected"] += stats["tables_detected"]
        totals["tables_copied"] += stats["tables_copied"]
        totals["tables_missing"] += stats["tables_missing"]
        print(
            f"  [OK] {paper_token}: "
            f"{stats['images_all']} images kept, "
            f"{stats['tables_copied']}/{stats['tables_detected']} tables extracted"
        )

    print("\n=== Done ===")
    print(f"Papers processed: {totals['papers']}")
    print(f"Papers skipped: {totals['skipped']}")
    print(f"Images kept: {totals['images_all']}")
    print(f"Table images detected: {totals['tables_detected']}")
    print(f"Table images copied: {totals['tables_copied']}")
    print(f"Table images missing: {totals['tables_missing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
