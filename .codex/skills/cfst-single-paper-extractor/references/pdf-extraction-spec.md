### 1. 文档有效性校验标准

文档必须满足以下所有条件才被视为有效，包含有效数据的论文即视为通过（即使包含有限元分析或其他构件的研究）：

- **研究对象**: 钢管混凝土 (CFST) 构件。
- **内容要求**: 包含物理试验 (Physical Experiments) 数据（如试验装置图、试件破坏照片、或包含 "Test/Exp" 字样的结果表格）。
- **受力模式**: 轴压 (Axial Compression) 或 偏压 (Eccentric Compression) 试验（包含短柱 Stub columns 或轴压构件）。

**明确拒绝（无效）的情况：**

- 纯有限元模拟 (Pure FEA) 且全文无任何自测数据。
- 纯理论推导 (Pure Analytical) 或综述文章 (Review)。
- 仅研究纯钢管 (Steel tube only) 或纯混凝土 (Concrete only)。
- 仅研究梁 (Pure Bending) 或仅研究节点 (Joints) 而无柱构件数据。

*若文档无效，对应的数据结构状态应为：* `{ "ref_info": {}, "Group_A": [], "Group_B": [], "Group_C": [], "is_valid": false, "reason": "Not experimental CFST column paper" }`

------

### 2. 构件分类与几何映射规则

需要按试件标签（Specimen Label）整合各个表格中的数据，并将构件分为三组，几何参数映射规则如下：

- **Group_A (方形/矩形 Square/Rectangular)**
  - `b`: 宽度 (Width)
  - `h`: 深度 (Depth)
- **Group_B (圆形 Circular)**
  - `b`: 直径 (Diameter)
  - `h`: 直径 (Diameter)
  - *必须满足 `b == h`*
- **Group_C (圆端形/椭圆形 Round_ended)**
  - `b`: 长轴 (Major Axis)
  - `h`: 短轴 (Minor Axis)
  - *必须满足 `b >= h`*

------

### 3. 数据提取字典与格式规范

所有数值字段需去除单位，且数值精度保留至 **0.01**。提取过程中需注意排除常见OCR识别错误（如 `1` 与 `l/I`，`0` 与 `O`，以及异常的小数点位置）。

#### 3.1 论文元数据 (Bibliographic Info)

- `title`: 论文完整标题。
- `authors`: 所有作者的列表。
- `journal`: 期刊或会议名称（如未找到则填 "Unknown"）。
- `year`: 出版年份（整数）。

#### 3.2 试件数据 (Specimen Data)

- `specimen_label`: 试件的唯一编号/标签。
- `fc_value`: 混凝土抗压强度数值（单位：MPa）。
- `fc_type`: 混凝土强度规格描述（例如："Cube 150", "Cylinder 150x300", "prism 150×150×300mm"）。若文中未说明尺寸，则使用 "cube", "cylinder", 或 "prism"。
- `fy`: 钢材屈服强度（单位：MPa）。
- `r_ratio`: 再生骨料比例（%）。普通混凝土该值为 `0`。
- `b` & `h`: 基于上述分类规则的截面尺寸（单位：mm）。
- `t`: 钢管壁厚（单位：mm）。
- `r0`: 外部圆角/半径（单位：mm）。计算规则如下：
  - Group_A: 固定填 `0`
  - Group_B: 填 `h / 2`
  - Group_C: 填 `h / 2`（圆端部分的半径）
- `L`: 试件长度（单位：mm）。
- `e1`, `e2`: 偏心距（单位：mm）。`e1` 为上端偏心，`e2` 为下端偏心。若未明确区分上下端，则 `e1 = e2 = 文中偏心距e`。轴压构件为 `0`。
- `n_exp`: 试验测得的极限承载力/峰值荷载（单位：kN）。**注意**：需排除有限元/计算结果；若原表格单位为 N 或 MN，必须换算为 kN。
- `source_evidence`: 数据来源的页面和表格定位（格式如："Page [X], Table [Y]" 或 "Page [X] text section"）。
- `fcy150`: 留空（固定为 `""`）。

------

### 4. 目标数据结构 Schema

所需的最终数据输出结构如下：

JSON

```
{
  "is_valid": true,
  "reason": "Valid CFST experimental data...",
  "ref_info": {
      "title": "String",
      "authors": ["Author 1", "Author 2"],
      "journal": "String",
      "year": 2024
  },
  "Group_A": [
    {
      "ref_no": "",
      "specimen_label": "String",
      "fc_value": 0.00,
      "fc_type": "String",
      "fy": 0.00,
      "fcy150": "",
      "r_ratio": 0.00,
      "b": 0.00,
      "h": 0.00,
      "t": 0.00,
      "r0": 0.00,
      "L": 0.00,
      "e1": 0.00,
      "e2": 0.00,
      "n_exp": 0.00,
      "source_evidence": "String"
    }
  ],
  "Group_B": [],
  "Group_C": []
}
```