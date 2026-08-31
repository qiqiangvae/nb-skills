# nb-skills

个人的 Agent Skills 仓库：存放自研 skills，并记录所用到的三方 skills。

## 目录结构

```
nb-skills/
├── skills/                    # 自研 skills（每个 <name>/SKILL.md 一个）
│   ├── coding-publish-skill/      # 发布到 GitHub / npm（含敏感内容审查门禁）
│   ├── dsh-session-preset-repair/ # 修复 DSH session resume 报 preset 缺失
│   └── light-weight-wiki/         # 轻量 LLM Wiki 工具链：入口 SKILL + references/（原 skill 名分册）+ 零依赖脚本
├── scripts/
│   ├── setup.sh               # 安装脚本（bash，Unix/macOS/Git Bash）
│   ├── setup.ps1              # 安装脚本（PowerShell，Windows 原生，功能等价）
│   └── setup.cmd              # Windows 启动器（自带 -ExecutionPolicy Bypass）
├── THIRD-PARTY-SKILLS.md      # 三方 skills 收录说明（重点：playwright-cli、mattpocock/skills）
└── README.md
```

## 安装（把自研 skills 装到你的 coding agent）

```bash
./scripts/setup.sh
```

脚本会交互式引导你：
1. **选目标 agent**（DSH / Claude Code / Codex / Gemini / OpenCode / Cursor，或自定义目录）；
2. **勾选要装哪些 skill**（回车 = 全部）；
3. **选安装方式**（`link` 软链接 —— 推荐，更新仓库即生效；或 `copy` 拷贝快照）。

也可以非交互一次性完成：

```bash
# 装到 DSH（~/.agents/skills），软链接
./scripts/setup.sh --agent dsh --link

# 全装到 Claude Code，用拷贝
./scripts/setup.sh --agent claude --copy --all

# 只装 coding-publish-skill 到自定义目录
./scripts/setup.sh --dir ~/my-skills --skill coding-publish-skill

# 试运行（只打印、不写盘）
./scripts/setup.sh --dry-run --agent dsh
```

> 脚本兼容 macOS 默认 bash 3.2，不依赖额外工具。

完整选项见 `./scripts/setup.sh --help`。

### Windows（原生 PowerShell / CMD）

Windows 直接运行启动器（它自带 `-ExecutionPolicy Bypass`，**无需**改系统策略）：

```bat
.\scripts\setup.cmd                    # 交互式：选 agent、勾选 skill、选 link/copy
.\scripts\setup.cmd --agent dsh --all  # 全装到 DSH，非交互
.\scripts\setup.cmd --dry-run --agent dsh
```

也可直接跑 PowerShell 版；若系统提示「禁止运行脚本」，先执行一次
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，或改用上面的 `setup.cmd`：

```powershell
.\scripts\setup.ps1 --agent dsh --all
```

> `--link` 在 Windows 上会先尝试符号链接；若无权限（管理员/开发者模式），自动降级为目录联接（Junction，无需提权），再失败才拷贝。完整选项见 `.\scripts\setup.cmd --help`（与 `setup.ps1 --help` 等价）。

## 自研 skills

- **coding-publish-skill** — 把本地项目发布到 GitHub / npm，内置「敏感内容审查」强制门禁，提交/发布前必须先扫密钥、令牌、PII、生产配置，避免泄露到公网。
- **dsh-session-preset-repair** — 诊断并修复 DSH 会话因 preset 缺失而无法 resume 的问题，安全地只重写目标 zstd frame。
- **light-weight-wiki** — 把一个 Markdown 文件夹建成并维护成可检索的个人/项目知识库（LLM Wiki 工具链），并附配套能力。结构：`SKILL.md` 是**入口**（判断意图并分派 + 公共前置/护栏），`references/` 下**按原名**保留原 dsh-obsidian 各 skill 的中文分册——`wiki`(主入口/建库)、`wiki-ingest`(写入/记账)、`wiki-query`(检索/问答)、`wiki-lint`(健康检查)、`defuddle`(网页提净)、`save`(存洞察)、`think`(推理循环)、`obsidian-markdown`(OFM 语法)、`json-canvas`(.canvas)、`obsidian-bases`(.base)、`obsidian-cli`(需 Obsidian 运行)；`scripts/` 为零依赖 Python 标准库脚本：`wiki-scaffold.py`、`wiki-write.py`（frontmatter 补全、index/log 更新、文件名安全、机器页保护、来源哈希去重、未解析链接报告）、`wiki-search.py`（BM25 检索 + 链接图，分中文/日文 CJK n-gram 与英文）、`wiki-lint.py`（死链/孤儿/缺 frontmatter/失效 index）。Agent 负责内容，脚本负责记账；跨 agent 通用（不绑定 DSH）。

## 三方 skills

用到的三方 skills 记录在 [THIRD-PARTY-SKILLS.md](THIRD-PARTY-SKILLS.md)，重点推荐：

- **[playwright-cli](https://github.com/microsoft/playwright-cli)** — token 高效的浏览器自动化 CLI。
- **[mattpocock/skills](https://github.com/mattpocock/skills)** — 真·工程 skills 合集（规划/调试/TDD/领域建模/交接等）。本仓库的 `scripts/setup.sh` 即参考其 `/setup-matt-pocock-skills` 思路设计。
