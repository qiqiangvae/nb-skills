# obsidian-bases（Obsidian Bases 视图）

> 原 dsh-obsidian skill `obsidian-bases`，名字保留。

Obsidian Bases 是 `.base` YAML 文件（放在 vault 根或任意位置），定义"按属性筛选/分组"的表格或卡片视图。**写入是跨 agent 的**（就是写合法 YAML）；但只有 Obsidian 能渲染 `.base`，所以面对不用 Obsidian 的用户要先说明"写完的库只能在 Obsidian 里展开"。

## 最小示例

```yaml
title: Projects
filter:
  and:
    - type == "project"
views:
  - type: table
    name: Active
    filter:
      and:
        - status == "active"
    order:
      - file.name
      - due
  - type: cards
    name: By status
    groupBy: status
```

## 公式模板

```yaml
formulas:
  days_to_due: (date(prop("due")) - today()) / 86400000
  is_overdue: (date(prop("due")) < today()) && (prop("status") != "done")
```

## 常见坑

- 含空格的属性名要加引号：`prop("Project Status")`。
- `today()` 是 **UTC 午夜**；做"按天比较"用 `date(prop("due")) < today()`，别用字符串比较。
- `groupBy` 一个缺失属性会**全部静默归到 `null`**。

## 何时用

- "项目看板" → `groupBy: status, orderBy: due`
- "阅读清单" → `filter: type == "resource" && status == "to-read"`
- "按作者" → `groupBy: author`

> 依赖本工具链写入的 frontmatter（`type`/`status` 等属性）作为筛选依据；先确认库里的页有这些 property。
