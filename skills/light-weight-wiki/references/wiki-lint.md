# wiki-lint（健康检查）

> 原 dsh-obsidian skill `wiki-lint`（工具 `wiki_lint` → 脚本 `../scripts/wiki-lint.py`），名字保留。

发现/验证知识库的问题：死链、孤儿、缺信息、index 失效。

## 前置

- **脚本**：检查脚本在 `../scripts/`（相对本文件）：

  ```bash
  LINT="$SKILL_DIR/scripts/wiki-lint.py"     # SKILL_DIR 为本 skill 根目录
  ```

- **vault**：确定知识库根目录，且已有内容。

## 运行

```bash
python3 "$LINT" "<vault>"          # 报告，默认不落盘
python3 "$LINT" "<vault>" --report # 额外写 <vault>/wiki/meta/Lint Report <日期>.md
```

## 检测项

| 类别 | 级别 | 含义 / 建议 |
| --- | --- | --- |
| `duplicate-filename` | error | 同名页出现多次 → 合并或改名 |
| `dead-link` | warn | 引用了不存在的 `[[页面]]` → 补页或改链 |
| `frontmatter` | warn/info | 缺 `type`/`created` → 按写作时补 |
| `orphan` | info | 无内容页入链 → 从相关页链接它 |
| `empty-section` | info | `## 标题` 无内容 → 补充或删节 |
| `stale-index` | info | 某页不在 `index.md` → 重跑写入或手动补 |
| `stale-hot` | info | `hot.md` > 30 天未刷新 → 用 `--quick` 刷新 |

## 输出（JSON）

```json
{"generatedAt":"…","totals":{"error":0,"warn":2,"info":1,"count":3},
 "issues":[{"severity":"…","category":"…","file":"…","message":"…","suggestion":"…"}],
 "reportPath":"…"}
```

## 修复流程

1. 跑 lint，按 `error → warn → info` 逐条看。
2. 对每个 `dead-link`：用 [wiki-ingest.md](wiki-ingest.md) 的脚本补一页，或改链。
3. 对每个 `orphan`：从相关页链入。
4. 对缺 `type`/`created` 的页：补 frontmatter。
5. 改完**重跑 lint** 确认问题已清。

## 边界

- 不要**批量重命名**页面；改名/合并要逐页和用户确认（脚本里没有 rename 工具，改名请用文件工具并同步修 index/引用）。
- `--report` 写的 `Lint Report <日期>.md` 是**机器页**，不参与检索、不算内容页。

## 完成标准

- 报告生成；对 `error`/`warn` 逐条给出处置（补页/改链/合并）。
- 若用户要，`--report` 落一份带日期的报告到 `wiki/meta/`。
