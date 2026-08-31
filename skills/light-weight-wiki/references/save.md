# save（把洞察存回知识库）

> 原 dsh-obsidian skill `save`（工具 `wiki_write`/`wiki_query` → 脚本 `../scripts/wiki-write.py`、`../scripts/wiki-search.py`），名字保留。

把一次对话中的洞察持久化到知识库。**只读库默认不改**；本册仅在用户明确要求保存时写入。

## 何时用

- "把这条洞察存到笔记"
- "关于这次对话加条笔记"
- "我想记住……"

> 前置：确定 **vault 根路径**（光一个"存起来"是不够的）——问用户、读配置、或取本 skill 约定的库目录。确认 vault 已 scaffold（见 [wiki.md](wiki.md)）。

## 流程

1. **定类型**：这是一条 `resource`（事实/概念）、`project`（决策/状态）、还是 `source`（外部来源）？
2. **取标题**：先用 `../scripts/wiki-search.py` 检索主题，若库里有现成 `[[标题]]` 就**复用**，否则拟一个简短名词短语。
3. **正文**：精简。用户说了可引用的话，用 `> quote` 块 + `**Source:** conversation, YYYY-MM-DD`。
4. **写入**：用 `../scripts/wiki-write.py`：
   ```bash
   python3 "$SEARCH" "<vault>" "<主题>" --top 3   # 先查重
   python3 "$WRITE" "<vault>" \
       --title "<标题>" --type resource --content "<正文>" \
       --source_path conversation [--tags 对话,洞察]
   ```
   `--source_path conversation` 记录来源，但**不产真实文件哈希**（无哈希去重副作用）。
5. **确认**：把落盘路径和新增的 master index 条目告诉用户。

## 不要

- 没有**明确同意**（"save this"/"remember this"/"add a note"）就不存；一句"嗯，有点意思"**不算同意**。
- 不先检索查重，**不**重复建已有页。
