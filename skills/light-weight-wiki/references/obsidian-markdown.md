# obsidian-markdown（Obsidian Flavor Markdown）

> 原 dsh-obsidian skill `obsidian-markdown`，名字保留。写进知识库的任何 `.md` 都以此为准（常驻语法参考）。

写进知识库的 Markdown 用 **OFM**，不要用裸的通用 Markdown。

## Wikilinks

```markdown
[[Page Name]]                  → 链接
[[Page Name|alias]]            → 别名显示
[[Page Name#Heading]]          → 链接到某节
![[Page Name]]                 → 嵌入（transclude）整页
![[Page Name#Heading]]         → 嵌入某节
```

## Properties（YAML frontmatter）

```yaml
---
title: My Note
type: resource
tags: [rust, async, ownership]
created: 2026-08-29
updated: 2026-08-29
source: https://example.com/article
source_hash: a1b2c3...
aliases: [Note Alias]
status: seedling
---
```

- `type` — 必填，驱动类型路由（见 [wiki.md](wiki.md)）。
- `created` — 只设一次，**不覆盖**。
- `updated` — 每次写入都改。
- `source` / `source_hash` — 摄取内容的来源与去重（`../scripts/wiki-write.py` 自动维护）。

## Callouts

```markdown
> [!note]
> 普通 callout 正文。

> [!warning] 可选标题
> 带标题的正文。

> [!quote] 标题
> 用于带出处的引用。
```

其它可用类型：`tip`、`info`、`example`、`question`、`success`、`failure`、`danger`、`bug`。

## 标准 Markdown

标题、列表、表格、代码块、链接、引用、图片：标准 **CommonMark** 就好，别在一册里从头复述。
