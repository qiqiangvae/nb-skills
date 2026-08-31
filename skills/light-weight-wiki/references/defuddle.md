# defuddle（网页 → 干净正文）

> 原 dsh-obsidian skill `defuddle`，名字保留。真正抽取由 [Defuddle](https://github.com/kepano/defuddle) 这个 **npm CLI / 包**完成；本册负责**指导 agent 去调用它**。

把网页清理成纯文章正文。

## 何时用

- 任何 URL 走 [wiki-ingest.md](wiki-ingest.md) 摄取**之前**，先做 defuddle 式抽取，省 token、让来源可读。

## 流程

1. **抓取** URL；若响应已是 markdown，跳过 defuddle。
2. 否则跑 `npx defuddle <url>`（或你运行时的等价物）。
3. 把干净 markdown 交给 [wiki-ingest.md](wiki-ingest.md) 摄取，写一个 **`resource`** 类型的页（用 `../scripts/wiki-write.py`，`--source_path` 指向抓下来的文件，原 URL 放 `--tags` 或正文）。

## 它会去掉

- 导航 / 头部 / 页脚
- Cookie / GDPR 横幅
- 侧栏、相关推荐块
- 大多广告与追踪脚本

## 它会保留

- 文章标题（h1）
- 作者与日期元数据
- 标题、段落、列表、代码块
- 图片（`src` 原样保留）

## 降级

无 `npx defuddle` 时，退回直接 `web_fetch`/read_page 拿到文本，仍写入知识库，并**说明未做 defuddle 清理**。
