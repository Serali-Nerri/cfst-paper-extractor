#!/usr/bin/env python3
"""
重组 MinerU 解析结果：
1. 简化目录结构：嵌套目录 -> 扁平化
2. 重命名为简短 ID（如 [A1-4]）
3. 保留 images 目录全部图片（不做筛删）
4. 在 markdown 同级新增 table 目录，复制表格图片并按表名重命名
5. 兼容 auto / hybrid_auto，兼容 *_content_list.json / *_content_list_v2.json
"""

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


def extract_paper_id(name: str) -> str | None:
    """从文件名提取论文 ID，兼容 [A1-4] / A1-4__xxx。"""
    match = re.match(r"\[?(A\d+-\d+)\]?", name)
    if not match:
        return None
    return f"[{match.group(1)}]"


def find_parse_dir(src_dir: Path) -> Path | None:
    """优先定位 hybrid_auto，其次 auto。"""
    hybrid_dirs = sorted(src_dir.rglob("hybrid_auto"))
    if hybrid_dirs:
        return hybrid_dirs[0]

    auto_dirs = sorted(src_dir.rglob("auto"))
    if auto_dirs:
        return auto_dirs[0]

    return None


def read_json_file(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def caption_from_nodes(nodes: Any) -> str:
    """提取 caption 节点中的纯文本。"""
    if not isinstance(nodes, list):
        return ""

    parts: list[str] = []
    for node in nodes:
        if isinstance(node, dict):
            text = node.get("content")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(node, str):
            parts.append(node)

    return "".join(parts).strip()


def parse_legacy_table_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """解析 legacy table 条目。"""
    if item.get("type") != "table":
        return None

    img_path = item.get("img_path")
    if not isinstance(img_path, str) or not img_path:
        return None

    captions = item.get("table_caption") or []
    caption = caption_from_nodes(captions) if isinstance(captions, list) else str(captions).strip()

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
    """递归遍历 v2 节点。"""
    if isinstance(node, list):
        for item in node:
            yield from iter_v2_nodes(item)
    elif isinstance(node, dict):
        yield node
        for value in node.values():
            yield from iter_v2_nodes(value)


def parse_v2_table_items(content_list_v2: Any) -> list[dict[str, Any]]:
    """解析 v2 table 条目。"""
    if not isinstance(content_list_v2, list):
        return []

    parsed: list[dict[str, Any]] = []
    for page_idx, page in enumerate(content_list_v2):
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
    """
    合并 legacy + v2 的表格图片信息：
      - 以 img_path 去重
      - caption 选更长的非空文本
      - page_idx 优先取存在值
    """
    merged: dict[str, dict[str, Any]] = {}
    seen_order: list[str] = []

    def upsert(item: dict[str, Any]):
        img_path = item["img_path"]
        caption = str(item.get("caption", "")).strip()
        page_idx = item.get("page_idx")
        source = item.get("source", "unknown")

        old = merged.get(img_path)
        if old is None:
            merged[img_path] = {
                "img_path": img_path,
                "caption": caption,
                "page_idx": page_idx if isinstance(page_idx, int) else None,
                "source": source,
            }
            seen_order.append(img_path)
            return

        if len(caption) > len(old["caption"]):
            old["caption"] = caption
            old["source"] = source

        if old["page_idx"] is None and isinstance(page_idx, int):
            old["page_idx"] = page_idx

    if isinstance(legacy_content, list):
        for item in legacy_content:
            if not isinstance(item, dict):
                continue
            parsed = parse_legacy_table_item(item)
            if parsed:
                upsert(parsed)

    for parsed in parse_v2_table_items(v2_content):
        upsert(parsed)

    # 按 page_idx + 首次出现顺序排序，保证输出稳定
    order_index = {img: idx for idx, img in enumerate(seen_order)}
    return sorted(
        merged.values(),
        key=lambda x: (
            x["page_idx"] if isinstance(x["page_idx"], int) else 10**9,
            order_index.get(x["img_path"], 10**9),
        ),
    )


INVALID_FILENAME_CHARS = re.compile(r"[\\/:*?\"<>|]+")
WHITESPACE = re.compile(r"\s+")


def sanitize_table_title(title: str) -> str:
    """
    将表名转为文件名：
      - 保留中英文与数字
      - 去除文件系统非法字符
      - 压缩空白并截断长度
    """
    text = WHITESPACE.sub(" ", title).strip()
    text = INVALID_FILENAME_CHARS.sub(" ", text)
    text = WHITESPACE.sub(" ", text).strip(" .")
    if len(text) > 120:
        text = text[:120].rstrip(" .")
    return text


def unique_filename(base_name: str, suffix: str, used_names: set[str]) -> str:
    """避免同目录重名。"""
    if not base_name:
        base_name = "table"

    candidate = f"{base_name}{suffix}"
    idx = 2
    while candidate in used_names:
        candidate = f"{base_name}_{idx}{suffix}"
        idx += 1

    used_names.add(candidate)
    return candidate


def copy_images_dir(src_images: Path, dst_images: Path, dry_run: bool = False) -> int:
    """完整复制 images 目录并返回图片数量。"""
    if not src_images.exists() or not src_images.is_dir():
        return 0

    img_count = sum(1 for p in src_images.rglob("*") if p.is_file())
    if dry_run:
        return img_count

    shutil.copytree(src_images, dst_images, dirs_exist_ok=True)
    return img_count


def copy_table_images(
    parse_dir: Path,
    table_items: list[dict[str, Any]],
    table_dir: Path,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    复制表格图片到 table 目录并重命名。
    返回 (copied_count, missing_count)。
    """
    copied = 0
    missing = 0
    used_names: set[str] = set()

    if not dry_run:
        table_dir.mkdir(parents=True, exist_ok=True)

    for idx, item in enumerate(table_items, start=1):
        img_path = item["img_path"]
        caption = str(item.get("caption", "")).strip()

        src = parse_dir / img_path
        if not src.exists() or not src.is_file():
            missing += 1
            continue

        suffix = src.suffix or ".jpg"
        base_name = sanitize_table_title(caption)
        if not base_name:
            base_name = f"table_{idx}"

        filename = unique_filename(base_name, suffix, used_names)
        dst = table_dir / filename

        if not dry_run:
            shutil.copy2(src, dst)
        copied += 1

    return copied, missing


def reorganize_paper(
    src_dir: Path,
    dst_dir: Path,
    paper_id: str,
    dry_run: bool = False,
):
    """重组单篇论文的解析结果。"""
    parse_dir = find_parse_dir(src_dir)
    if not parse_dir:
        print(f"  [SKIP] 未找到 hybrid_auto/auto 目录: {src_dir.name[:50]}")
        return None

    md_files = sorted(parse_dir.glob("*.md"))
    legacy_json_files = sorted(parse_dir.glob("*_content_list.json"))
    v2_json_files = sorted(parse_dir.glob("*_content_list_v2.json"))
    images_dir = parse_dir / "images"

    if not md_files:
        print(f"  [SKIP] 缺少 md 文件: {src_dir.name[:50]}")
        return None
    if not v2_json_files:
        print(f"  [SKIP] 缺少 *_content_list_v2.json: {src_dir.name[:50]}")
        return None

    md_file = md_files[0]
    legacy_content = read_json_file(legacy_json_files[0]) if legacy_json_files else None
    v2_content = read_json_file(v2_json_files[0]) if v2_json_files else None

    table_items = collect_table_images(legacy_content, v2_content)

    paper_dst = dst_dir / paper_id
    new_md = paper_dst / f"{paper_id}.md"
    new_images_dir = paper_dst / "images"
    new_table_dir = paper_dst / "table"

    stats = {
        "images_all": 0,
        "tables_copied": 0,
        "tables_missing": 0,
        "tables_detected": len(table_items),
    }

    if not dry_run:
        paper_dst.mkdir(parents=True, exist_ok=True)

    # 复制 markdown
    if not dry_run:
        shutil.copy2(md_file, new_md)

    # 输出 JSON：仅保留 v2
    new_v2_json = paper_dst / f"{paper_id}_content_list_v2.json"
    if not dry_run:
        shutil.copy2(v2_json_files[0], new_v2_json)

    # images 全量保留
    stats["images_all"] = copy_images_dir(images_dir, new_images_dir, dry_run=dry_run)

    # table 目录提取
    copied, missing = copy_table_images(parse_dir, table_items, new_table_dir, dry_run=dry_run)
    stats["tables_copied"] = copied
    stats["tables_missing"] = missing

    return stats


def main():
    parser = argparse.ArgumentParser(description="标准化重组 MinerU 结果：保留 images，提取 table")
    parser.add_argument("input_dir", type=Path, help="MinerU 解析输出目录")
    parser.add_argument("-o", "--output", type=Path, default=None, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只显示操作，不实际执行")
    args = parser.parse_args()

    output_dir = args.output or args.input_dir.parent / f"{args.input_dir.name}_with_tables"

    print(f"输入目录: {args.input_dir}")
    print(f"输出目录: {output_dir}")
    print("JSON 保留策略: v2 only")
    if args.dry_run:
        print("[DRY RUN 模式]")
    print()

    total_stats = {
        "papers": 0,
        "images_all": 0,
        "tables_detected": 0,
        "tables_copied": 0,
        "tables_missing": 0,
    }

    for item in sorted(args.input_dir.iterdir()):
        if not item.is_dir():
            continue

        paper_id = extract_paper_id(item.name)
        if not paper_id:
            print(f"  [SKIP] 无法提取 ID: {item.name[:50]}")
            continue

        stats = reorganize_paper(
            item,
            output_dir,
            paper_id,
            dry_run=args.dry_run,
        )
        if not stats:
            continue

        total_stats["papers"] += 1
        total_stats["images_all"] += stats["images_all"]
        total_stats["tables_detected"] += stats["tables_detected"]
        total_stats["tables_copied"] += stats["tables_copied"]
        total_stats["tables_missing"] += stats["tables_missing"]

        print(
            f"  [OK] {paper_id}: "
            f"{stats['images_all']} images kept, "
            f"{stats['tables_copied']}/{stats['tables_detected']} tables extracted"
        )

    print("\n=== 完成 ===")
    print(f"论文: {total_stats['papers']}")
    print(f"images 全量保留: {total_stats['images_all']}")
    print(f"识别到表格图片: {total_stats['tables_detected']}")
    print(f"成功提取表格图片: {total_stats['tables_copied']}")
    print(f"缺失表格图片: {total_stats['tables_missing']}")


if __name__ == "__main__":
    main()
