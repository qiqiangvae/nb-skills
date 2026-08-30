# nb-skills

个人的 Agent Skills 仓库：存放自研 skills，并记录所用到的三方 skills。

## 目录结构

```
nb-skills/
├── skills/                    # 自研 skills（每个 <name>/SKILL.md 一个）
│   ├── coding-publish-skill/      # 发布到 GitHub / npm（含敏感内容审查门禁）
│   └── dsh-session-preset-repair/ # 修复 DSH session resume 报 preset 缺失
├── scripts/
│   └── setup.sh               # 安装脚本：把 skills 装到任意 coding agent
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

## 自研 skills

- **coding-publish-skill** — 把本地项目发布到 GitHub / npm，内置「敏感内容审查」强制门禁，提交/发布前必须先扫密钥、令牌、PII、生产配置，避免泄露到公网。
- **dsh-session-preset-repair** — 诊断并修复 DSH 会话因 preset 缺失而无法 resume 的问题，安全地只重写目标 zstd frame。

## 三方 skills

用到的三方 skills 记录在 [THIRD-PARTY-SKILLS.md](THIRD-PARTY-SKILLS.md)，重点推荐：

- **[playwright-cli](https://github.com/microsoft/playwright-cli)** — token 高效的浏览器自动化 CLI。
- **[mattpocock/skills](https://github.com/mattpocock/skills)** — 真·工程 skills 合集（规划/调试/TDD/领域建模/交接等）。本仓库的 `scripts/setup.sh` 即参考其 `/setup-matt-pocock-skills` 思路设计。
