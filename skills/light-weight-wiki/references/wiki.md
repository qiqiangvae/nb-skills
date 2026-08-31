# wiki（知识库主入口 / 建库）

> 原 dsh-obsidian skill `wiki`，名字保留。本册是 wiki 四册的**主册**：建库 + 全套脚本总览。

把一个 Markdown 文件夹变成可检索的知识库。**Agent 负责内容与判断，脚本负责机械记账**。

## 脚本总览（托管在 `../scripts/`）

| 脚本 | 用途 | 对应原工具 |
| --- | --- | --- |
| `wiki-scaffold.py` | 建库 / 补目录骨架 | `wiki_scaffold` |
| `wiki-write.py` | 写入/更新一页并记账 | `wiki_write` |
| `wiki-search.py` | BM25 检索 + 链接图 | `wiki_query` |
| `wiki-lint.py` | 健康检查 | `wiki_lint` |

```bash
SKILL_DIR=<本 skill（light-weight-wiki）所在目录>
SCAFFOLD="$SKILL_DIR/scripts/wiki-scaffold.py"
WRITE="$SKILL_DIR/scripts/wiki-write.py"
SEARCH="$SKILL_DIR/scripts/wiki-search.py"
LINT="$SKILL_DIR/scripts/wiki-lint.py"
```

从本 skill 目录解析，勿从 cwd 或 vault 猜。脚本与 `wiki_lib.py` 需一起拷贝。

## 何时建库

- 用户想**新建**一个知识库：给一个空/不存在目录，让它长出 `wiki/` 结构。
- 库建好后想补缺（`.raw/`、`inbox/` 或 research 模板）。

## 运行

```bash
python3 "$SCAFFOLD" "<vault>"               # 先 dry-run：只打印计划，不改盘
python3 "$SCAFFOLD" "<vault>" --apply       # 真正创建目录 + index/hot/log/Inbox
python3 "$SCAFFOLD" "<vault>" --apply --template research   # 额外建 Research Questions.md
```

- **默认 dry-run**，输出 `{"dry_run":true, "create":[...], "write":[...]}`；用 `--apply` 才写盘。
- 模板：`default`（标准）、`minimal`（最小）、`research`（外加 `Research Questions.md`）。
- 已存在的目录/文件会被跳过（`skipped`），**不会覆盖**已有内容。

## 它会创建什么

```
<vault>/wiki/
  index.md   hot.md   log.md   meta/
  areas/  projects/  resources/  sources/  archive/
<vault>/.raw/          # 不可变来源（只读）
<vault>/inbox/Inbox.md # 临时收集，待整理
```

- `index.md` 预置小写分节：`## areas` `## projects` `## resources` `## sources`（与 `wiki-write.py` 记账一致，避免重复空节）。
- `hot.md` 近期上下文缓存（`wiki-search.py --quick` 读它）；`log.md` 变更流水（`wiki-write.py` 追加）。
- **机器页**（`index`/`hot`/`log`/`readme`/`Lint Report*`）由系统管理，不可覆盖/改名/删除。

## 分派

- 写页/摄取 → [wiki-ingest.md](wiki-ingest.md)
- 检索问答 → [wiki-query.md](wiki-query.md)
- 健康检查 → [wiki-lint.md](wiki-lint.md)

## 完成标准

- `--apply` 后目录存在，且 `wiki/index.md`、`wiki/hot.md`、`wiki/log.md` 已生成。
- 若对已有内容建库，先备份或确认 `skipped` 不覆盖现有文件。
