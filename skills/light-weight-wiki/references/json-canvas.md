# json-canvas（JSON Canvas 视图）

> 原 dsh-obsidian skill `json-canvas`，名字保留。

JSON Canvas 是**开放规范**（https://jsoncanvas.org），不限于 Obsidian——Obsidian Canvas / Kinopio / Jiyuu 都能读 `.canvas` 文件。本册指导**生成符合规范的 `.canvas` JSON 文件**，用内置文件工具写盘即可（不需要专用工具）。

## Schema（1.0）

```json
{
  "nodes": [
    { "id": "uuid-or-string", "type": "text", "x": 0, "y": 0, "width": 250, "height": 100,
      "label": "Optional", "text": "# Heading\nMarkdown body" },
    { "id": "uuid-or-string", "type": "file", "x": 300, "y": 0, "width": 250, "height": 100,
      "file": "Notes/My Note.md" },
    { "id": "uuid-or-string", "type": "link", "x": 600, "y": 0, "width": 250, "height": 100,
      "url": "https://example.com" },
    { "id": "uuid-or-string", "type": "group", "x": 0, "y": 150, "width": 500, "height": 200,
      "label": "Cluster", "color": "1" }
  ],
  "edges": [
    { "id": "edge-1", "fromNode": "uuid-1", "fromSide": "right",
      "toNode": "uuid-2", "toSide": "left", "label": "links to" }
  ]
}
```

- `type` 取值：`text`（正文）、`file`（指向一个 md 文件）、`link`（外链）、`group`（分组）。
- `edges` 连接节点，`fromNode`/`toNode` 用节点 `id`；`fromSide`/`toSide` 用 `top|right|bottom|left`（缺省 `top`）。

## 要点

- **`id` 用稳定字符串**；下游工具按它去重。
- 坐标是**像素**；Obsidian 默认缩放时 100×100 视野合适。
- **从 vault 的 wikilinks 生成图谱**：遍历 `.md` 页，每个标题建一个节点，每处 `[[link]]` 加一条边。

## 写到哪里

把 `.canvas` 放到 vault 根或 `wiki/` 下即可（如 `<vault>/mindmap.canvas`）；写后校验 JSON 合法（节点/边 id 引用一致）。
