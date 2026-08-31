# wiki-ingest（写入 / 摄取）

> 原 dsh-obsidian skill `wiki-ingest`（工具 `wiki_write` → 脚本 `../scripts/wiki-write.py`），名字保留。

把来源（URL/文件/粘贴/对话）或笔记提炼后写进知识库，新建或更新一页。**Agent 负责内容与判断，脚本负责记账。**

## 前置

- **脚本**：写入脚本在 `../scripts/`（相对本文件）：

  ```bash
  WRITE="$SKILL_DIR/scripts/wiki-write.py"     # SKILL_DIR 为本 skill 根目录
  ```

- **vault**：确定知识库根目录，且已 scaffold（见 [wiki.md](wiki.md)）。
- **内容来源**：URL（先过 [defuddle.md](defuddle.md) 提净）、文件、粘贴文本、或对话内容。

## 核心原则

1. **先读来源、提炼内容**：正文应是精炼后的页，不是原文大段照搬。大的原文必要时存为 `source` 类型的页再链接它。
2. **决定字段**：`--title`（页标题）、`--type`（见下表）、正文、`--tags`（可选）。
3. **同一来源沉淀多个概念页**：逐个调用，都带同一个 `--source_path`；内容变了加 `--force`。
4. **别重复写**：不确定是否已有时，先用 [wiki-query.md](wiki-query.md) 的脚本检索查重。

## 运行

```bash
python3 "$WRITE" "<vault>" --title "知识库" --type project \
    --content "正文..." [--tags a,b] [--source_path 来源.txt]
python3 "$WRITE" "<vault>" --title "检索" --type area --content-file note.md
```

| 参数 | 说明 |
| --- | --- |
| `--title` | 页标题（必填） |
| `--type` | 必填，`domain/area/project/resource/source/archive` |
| `--content` / `--content-file` | 正文（二选一；文件方式避免 shell 转义） |
| `--tags` | 逗号分隔 |
| `--source_path` | 来源文件路径；脚本记录其 SHA-256 用于去重 |
| `--force` | 即使来源哈希未变也重写 |

类型→目录：`domain/area→wiki/areas`，`project→wiki/projects`，`resource→wiki/resources`，`source→wiki/sources`，`archive→wiki/archive`。

## 脚本自动做的记账

- **文件名安全**：拒绝保留设备名（`con`/`prn`/…）、非法字符、尾随空格。
- **机器页保护**：标题为 `index`/`hot`/`log`/… 直接拒绝。
- **frontmatter 补全**：保留 `created` 与未知字段，只改 `updated`。
- **更新 `index.md`、追加 `log.md`**。
- **来源哈希去重**：同 `--source_path` 内容没变 → `{"action":"skipped"}`，除非 `--force`。
- **报告未解析前向链接**（`unresolvedLinks`），下轮补页或改链。

## 输出（JSON）

```json
{"path":"…/wiki/projects/知识库.md","action":"created|updated|skipped",
 "title":"…","type":"project","created":"…","updated":"…",
 "unresolvedLinks":["…"],"sourceHash":"sha256:…"}
```

- `action`：`created`（新页）/ `updated`（改已有页）/ `skipped`（哈希未变）。
- `unresolvedLinks`：正文引用但尚不存在的 `[[页面]]`，用于后续补页。

## 边界

- **不要徒手写 `wiki/` 目录**：一律走 `wiki-write.py`，否则丢记账/去重。
- **不要把大段原文塞进 `--content`**：正文要提炼；原文链接放 `source` 页。
- 消除死链时，对 lint/检索报出的每个未解析目标**补一页**或改链。

## 完成标准

- 返回 `action` 非报错；页面落盘在类型目录；`index.md`/`log.md` 已更新。
- `unresolvedLinks` 已记录并决定后续动作（补页 / 改链 / 忽略并说明）。
