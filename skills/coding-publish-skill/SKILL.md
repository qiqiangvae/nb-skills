---
name: coding-publish-skill
description: 当需要把本地编码项目发布出去——发布到 GitHub（提交、推送、打 tag、创建 Release）或发布到 npm，或两者都要、诊断 Git push 受阻（Killed:9/SIGKILL），或用 git、git send-pack、curl、gh、npm 完成发布时使用。任何提交或发布之前都必须先做敏感内容审查，避免密钥/令牌/PII/生产配置泄露到公网。
---

# 编码项目发布（GitHub / npm）

本 skill 负责把本地编码项目发布到 **GitHub** 和/或 **npm**，以**可验证的远程状态**完成，每一步都有独立的「完成标准」。

## 你先做什么：判断发布目标并分派

1. **确认发布目标**：问用户要发布到哪里——只 GitHub？只 npm？还是两者？（用户说「发布到 github 和 npm」就是两者。）
2. **公共前置**：完成下方「公共前置」小节的版本号确认、认证预探测与敏感内容审查。
3. **按目标分派**，读取对应子文档并**完整遵循**其流程：

   | 发布目标 | 读取并遵循 |
   | --- | --- |
   | GitHub（含 Release） | [references/github.md](references/github.md) |
   | npm | [references/npm.md](references/npm.md) |
   | 两者都要 | 先 GitHub，再 npm（二者共享同一次版本号 bump 与提交） |

> 子文档位于 `references/` 目录，相对本 `SKILL.md` 解析。

发布交付物清单（最终报告里逐项确认）：

1. 源码提交（commit）与分支
2. 带注释标签（annotated tag）及其指向的提交
3. GitHub Release（`html_url`）
4. npm 包版本（若发布 npm）
5. 敏感内容审查结论（已通过 / 发现并已处理）

---

## 公共前置（不区分 GitHub / npm，两者都要）

### A. 版本号确认

按语义化版本从当前 `package.json` 版本推断，给推荐值让用户选（**不要擅自 bump**）：

- 新增用户可见功能 → **minor**（`x.Y.0`）
- 小修/文档/补依赖 → **patch**（`x.y.Z`）
- 首个可用版本 → `v0.1.0`

### B. 认证预探测（决定哪些步骤能自动、哪些交用户）

在改任何文件、跑任何发布命令**之前**先做，避免 push 完才发现 Release / npm 无法自动化：

```bash
gh auth status 2>&1 | head -5
echo "GH_TOKEN len: ${#GH_TOKEN}  GITHUB_TOKEN len: ${#GITHUB_TOKEN}"
npm whoami 2>&1 | head -5
```

按结果给「可自动 / 不可自动」下结论：

| 能力 | 可用条件 | 不可用时如何处理 |
| --- | --- | --- |
| git push / send-pack | SSH key 或 HTTPS 凭据可用 | 报阻塞，交用户执行 |
| GitHub Release | `gh` 已登录 **或** `GH_TOKEN`/`GITHUB_TOKEN` 长度非 0 | 交用户执行（见 references/github.md） |
| npm publish | `npm whoami` 有输出 | 报阻塞，交用户执行 |

> **认证判定陷阱**：`gh auth status` 报 `not logged in` 且环境变量为空时，`[ -n "$GH_TOKEN" ]` 可能误判（变量名存在但值为空）。务必用 `${#GH_TOKEN}` 检查**实际长度**，而不是 `-n`。

### C. 敏感内容审查（强制门禁，提交 / 发布前必做）

在**任何一次** `git commit`、`git push`、`npm publish` 或创建 Release 之前，都必须先完成敏感内容审查，确保没有把密钥、令牌、密码、客户 PII、生产配置或未脱敏日志带入将被推送到公网的提交/包体。这是**不可跳过**的步骤——发现可疑内容直接报阻塞，不得带病提交。

详细清单、扫描命令与校验方式见 [references/sensitive-content.md](references/sensitive-content.md)。核心动作：

```bash
# 1) 扫描工作区与暂存区所有将被提交的文本内容
git grep -n -I -E '(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9-]+|-----BEGIN [A-Z ]*PRIVATE KEY-----|sk-[A-Za-z0-9]{20,}|password\s*[:=]|secret\s*[:=]|api[_-]?key\s*[:=]|token\s*[:=])' -- . :(exclude)package-lock.json 2>/dev/null
# 2) 核对 .gitignore 是否覆盖 .env / *.pem / 密钥文件
# 3) 检查 .env*、密钥文件本身有没有被 git 追踪
```

**完成标准**：上述扫描零命中，`.env*`/密钥文件未被追踪或已被忽略，方可进入提交/发布。命中任一项 → 报阻塞并交用户脱敏（详见子文档）。

### D. 公共提交与打 tag（两者共享）

版本号 bump、CHANGELOG 归位、重新构建、提交、打 annotated tag 是**一次性的共同动作**，不要为 GitHub 和 npm 各做一遍：

```bash
# 1) package.json version 与 CHANGELOG [Unreleased] → [vX.Y.Z] 同步
# 2) 若 package.json 缺 repository 字段，补上（npm 页面需要它链接回 GitHub）
# 3) 按项目方式重新构建并验证（pnpm run build / typecheck / node --check ...）
# 4) 提交
git commit -m 'chore: bump to vX.Y.Z'
# 5) 打带注释 tag（annotated tag，而非轻量 tag）
git tag -a vX.Y.Z -m 'vX.Y.Z: <一句话概述>'
```

**注意**：清理构建/验证过程中误生成的文件（`pnpm-workspace.yaml`、项目根 `release-notes-*.md` 等），`git status --short` 逐个核对，非预期的一律删除，**不得带入提交**。

---

## 最终报告格式（两部分都要遵守）

无论发布了几个目标，最终报告都分别说明：

- 仓库 URL；
- 分支及提交 SHA；
- 带注释标签及其目标提交；
- GitHub Release URL（或「已交用户执行，待回传 URL」）；
- npm 包版本（或「未发布 npm」）；
- 敏感内容审查结论（扫描零命中 / 命中项及其脱敏处理方式）；
- 已通过的验证命令；
- 未完成步骤及其确切阻塞原因。

---

## 通用经验（两部分共享）

- GitHub MCP 凭据可能有仓库读取或文件写入权限，但不一定有创建仓库/PR/Release 的权限。每项 API 能力必须独立验证；常见 MCP 只有只读 `get_*`/`list_releases`，**没有 create release**。
- `gh` 需要 `gh auth login` 或非空 `GH_TOKEN`；能走 Git SSH 的 SSH key **不代表** GitHub CLI API 已认证。
- Release tag 必须指向最终发布提交；若合并发生在打 tag 之后，先本地移动带注释标签再强推 tag（细节见 references/github.md）。
- release notes 一律写 `/tmp/`，**不写进项目目录**以免污染仓库。
- `npm view <pkg> version` 可能缓存延迟显示旧版本，核验 npm 以 `dist-tags.latest` 与 `versions` 数组为准。
- DSH 插件安装命令 `dsh plugin --profile <name> add <package>`，支持 `link:` / `github:owner/repo[#tag]` / npm 包名；装完还要列入该 profile 的 `dsh.profile.bundles` 才生效。
