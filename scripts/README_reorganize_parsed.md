# `reorganize_parsed.py` 使用说明

## 目标

对 `cfst_parsed/` 的 MinerU 原始解析结果做标准化重组：

1. 每篇论文输出到 `"[A*-*]"` 目录。
2. `images/` 全量保留，不删图、不改名。
3. 在同级新增 `table/`，仅复制表格图片。
4. `table/` 内文件按表名命名（来自 `table_caption`）。
5. 兼容读取 `*_content_list.json` 与 `*_content_list_v2.json`（hybrid_auto），但输出只保留 v2。

## 推荐命令

```bash
python scripts/reorganize_parsed.py cfst_parsed
```

默认输出目录：`cfst_parsed_with_tables/`

先预览（不落盘）：

```bash
python scripts/reorganize_parsed.py cfst_parsed --dry-run
```

指定输出目录：

```bash
python scripts/reorganize_parsed.py cfst_parsed -o data/cfst_parsed_with_tables
```

## JSON 保留策略

脚本固定为只保留 `*_content_list_v2.json`，不再输出 legacy JSON。

## 输出结构示例

```text
cfst_parsed_with_tables/
  [A1-2]/
    [A1-2].md
    [A1-2]_content_list_v2.json
    images/
      ...
    table/
      TABLE 1. Properties for Concrete-Filled Steel Tube Components.jpg
      TABLE 2. Comparison of Experimental Data to Predicted Axial Capacity.jpg
```

## 备注

- 脚本只“复制”原始数据，不修改 `cfst_parsed/` 原目录。
- 若同一篇中表名重名，脚本会自动追加 `_2`, `_3` 防止覆盖。
- 若某个表格图片在 `images/` 中缺失，会计入 `tables_missing` 统计。
