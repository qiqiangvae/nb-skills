# nb-skills

个人的 Agent Skills 仓库：存放自研 skills，并记录所用到的三方 skills。

## 目录结构

```
nb-skills/
├── skills/                    # 自研 skills（每个 <name>/SKILL.md 一个）
│   ├── coding-publish-skill/      # 发布到 GitHub / npm：入口 SKILL + references/ 三个分支 + scripts/ 零依赖门禁脚本
│   ├── handdrawn-infographic/     # 手绘信息图提示词生成
│   └── light-weight-wiki/         # 轻量 LLM Wiki 工具链：入口 SKILL + references/（原 skill 名分册）+ 零依赖脚本
├── THIRD-PARTY-SKILLS.md      # 三方 skills 收录说明（重点：playwright-cli、mattpocock/skills）
└── README.md
```

无安装脚本。安装直接用社区通用的 [`skills`](https://github.com/vercel-labs/skills) CLI。

## 安装（把本仓库的 skills 装到你的 coding agent）

一条命令：

```bash
npx skills add https://github.com/qiqiangvae/nb-skills
```

会依次问你三件事：

1. **装哪些 skill** —— 列出 `coding-publish-skill` / `handdrawn-infographic` / `light-weight-wiki`，
   用 `↑↓` 移动、`空格` 勾选、`回车` 确认（第 1 项是「全选」）；
2. **装到哪些 agent** —— `Universal (~/.agents/skills)` 是**固定包含**的（各 agent 共享的通用目录），
   另有十几个常见 agent 默认已勾选，不需要的用 `空格` 取消；
3. **安装范围** —— 用户级还是当前项目级。

> 第 2 步里的 `Universal (~/.agents/skills)` 始终包含，无需额外操作。

### 想要「只装到 `~/.agents/skills`」——跳过交互

上面的向导默认还会装到十几个其它 agent 目录。要精确只装一处，用非交互参数：

```bash
npx skills add https://github.com/qiqiangvae/nb-skills -g -a universal -s '*' -y
```

| 参数 | 作用 | 不加会怎样 |
|---|---|---|
| `-g` | 用户级（装到 `~`） | 装进**当前目录**的 `./.agents/skills` |
| `-a universal` | 只指向 `~/.agents/skills` | 装到**所有**能识别的 agent（约 79 个目录） |
| `-s '*'` | 全部 skill | 逐个询问 |
| `-y` | 免确认 | 逐个询问 |

`~/.agents/skills` 是 skills 生态里各 agent 共享的通用目录；`-g` 和 `-a universal`
想「只装这一处」时**两个都不能省**。

### 常用变体

```bash
# 只预览有哪些 skill，不安装
npx skills add https://github.com/qiqiangvae/nb-skills -l

# 只装某一个 skill 到 ~/.agents/skills
npx skills add https://github.com/qiqiangvae/nb-skills -g -a universal -s light-weight-wiki -y

# 只装到指定 agent
npx skills add https://github.com/qiqiangvae/nb-skills -g -a claude-code -s '*' -y
```

> agent 名示例：`universal`（共享目录 `~/.agents/skills`）、`claude-code`、`gemini-cli`、
> `codex`、`opencode`、`cursor` 等。完整列表见 `npx skills add --help`。

### 更新与卸载

```bash
npx skills update            # 更新已装的 skills
npx skills list              # 查看已装 skills
npx skills remove <name>     # 卸载某个 skill
```

> **更新方式**：`skills` CLI 用**拷贝**而非软链接，所以改完本仓库需重跑 `add` 才会生效；
> 重跑即覆盖，无需先卸载。注意重跑会把既有的软链接替换成拷贝目录。

## 自研 skills

- **coding-publish-skill** — 把本地项目发布到 GitHub / npm。结构：`SKILL.md` 是**入口**（分派 + 公共前置 A–D），`references/` 一册一个分支（`github.md`、`npm.md`、`sensitive-content.md`）；`scripts/` 为零依赖 bash 脚本：`scan-sensitive.sh`（敏感内容审查强制门禁：先把待提交内容落到索引，再分「硬门禁 1–3」与「需人工过目 1–4」两段输出，命中即阻塞）、`selftest.sh`（10 个用例的回归自检，锁住历史缺陷：未追踪的新 `.env` 曾对 `git grep` 完全不可见、`\s` 在 POSIX ERE 里退化成字面量 s、`.env.example` 被硬拦逼出绕过习惯等）。跑 `bash scripts/selftest.sh` 验证。门禁只管机器能判定的（令牌形状 / 真实密钥文件 / `.gitignore` 覆盖），占位符与真值难分的模式走人工过目。
- **light-weight-wiki** — 把一个 Markdown 文件夹建成并维护成可检索的个人/项目知识库（LLM Wiki 工具链），并附配套能力。结构：`SKILL.md` 是**入口**（判断意图并分派 + 公共前置/护栏），`references/` 下**按原名**保留原 dsh-obsidian 各 skill 的中文分册——`wiki`(主入口/建库)、`wiki-ingest`(写入/记账)、`wiki-query`(检索/问答)、`wiki-lint`(健康检查)、`defuddle`(网页提净)、`save`(存洞察)、`think`(推理循环)、`obsidian-markdown`(OFM 语法)、`json-canvas`(.canvas)、`obsidian-bases`(.base)、`obsidian-cli`(需 Obsidian 运行)；`scripts/` 为零依赖 Python 标准库脚本：`wiki-scaffold.py`、`wiki-write.py`（frontmatter 补全、index/log 更新、文件名安全、机器页保护、来源哈希去重、未解析链接报告）、`wiki-search.py`（BM25 检索 + 链接图，分中文/日文 CJK n-gram 与英文）、`wiki-lint.py`（死链/孤儿/缺 frontmatter/失效 index）、`wiki-rename.py`（改名/删页，同步页内 title 与全库引用）、`light-weight-wiki-config.py`（vaultPath/typeFolders）、`selftest.py`（回归自检）。Agent 负责内容，脚本负责记账；跨 agent 通用。

## 三方 skills

用到的三方 skills 记录在 [THIRD-PARTY-SKILLS.md](THIRD-PARTY-SKILLS.md)，重点推荐：

- **[playwright-cli](https://github.com/microsoft/playwright-cli)** — token 高效的浏览器自动化 CLI。
- **[guizang-ppt-skill](https://github.com/op7418/guizang-ppt-skill)** — 用 Agent 生成网页 PPT（电子杂志风 / 瑞士国际主义），含演讲者模式与版式校验器。
- **[ponytail](https://github.com/DietrichGebert/ponytail)** — 常驻「懒惰资深工程师」极简编码约束（`/ponytail lite|full|ultra|off`）+ 过度工程审查 / 审计 / 技术债技能；多 agent 通用。
- **[mattpocock/skills](https://github.com/mattpocock/skills)** — 真·工程 skills 合集（规划/调试/TDD/领域建模/交接等）。
- **[vercel-labs/skills](https://github.com/vercel-labs/skills)** — 社区通用的 skills 安装 CLI（`npx skills add/update/remove`），本仓库即用它安装。
