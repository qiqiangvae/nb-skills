---
name: coding-publish-skill
description: 当需要把本地编码项目发布出去——发布到 GitHub（含打 tag、创建 Release）或 npm，或两者都要，或诊断 Git push 受阻（Killed:9/SIGKILL / send-pack 兜底）时使用。任何提交或发布之前都必须先做敏感内容审查，避免密钥/令牌/PII/生产配置泄露到公网。
---

# 编码项目发布（GitHub / npm）

本 skill 负责把本地编码项目发布到 **GitHub** 和/或 **npm**，以**可验证的远程状态**完成，每一步都有独立的「完成标准」。

## 你先做什么：判断发布目标并分派

1. **确认发布目标**：目标以用户话里已声明的为准（用户说「发布到 github 和 npm」就是两者），未声明才问。
2. **公共前置**：完成下方「公共前置」的 A–D（固定顺序见该小节开头）。
3. **按目标分派**，读取对应子文档并**完整遵循**其流程：

   | 发布目标 | 读取并遵循 |
   | --- | --- |
   | GitHub（含 Release） | [references/github.md](references/github.md) |
   | npm | [references/npm.md](references/npm.md) |
   | 两者都要 | 先 GitHub，再 npm（二者共享同一次版本号 bump 与提交） |

发布交付物清单（最终报告里逐项确认）：

1. 源码提交（commit）与分支
2. 带注释标签（annotated tag）及其指向的提交
3. GitHub Release（`html_url`）
4. npm 包版本（若发布 npm）
5. 敏感内容审查结论（已通过 / 发现并已处理）

---

## 公共前置

A、B 只读不写；C 是强制门禁，在任何一次提交之前完成；D 是写操作的收口。顺序固定为 **A → B → C →（GitHub 目标需要时做 `references/github.md` §1 对齐远程历史）→ D**。

### A. 版本号确认

按语义化版本从当前 `package.json` 版本推断，给推荐值让用户选：

- 新增用户可见功能 → **minor**（`x.Y.0`）
- 小修/文档/补依赖 → **patch**（`x.y.Z`）
- 首个可用版本 → `v0.1.0`

**完成标准**：推荐值已给用户且用户已确认；确认之前不改 `package.json`。

### B. 预探测：认证能力 + 目标可用性

先探清哪些步骤能自动、哪些必须交用户，**免得 push 完才发现 Release / npm 无法自动化**。只探测本次会用到的目标（不发布 npm 就不必看 `npm whoami`）：

```bash
gh auth status 2>&1 | head -5
echo "GH_TOKEN len: ${#GH_TOKEN}  GITHUB_TOKEN len: ${#GITHUB_TOKEN}"
npm whoami 2>&1 | head -5
```

认证能力按结果判定：

| 能力 | 可用条件 | 不可用时如何处理 |
| --- | --- | --- |
| git push / send-pack | SSH key 或 HTTPS 凭据可用 | 报阻塞，交用户执行 |
| GitHub Release | `gh` 已登录 **或** `GH_TOKEN`/`GITHUB_TOKEN` 非空 | 交用户执行（见 references/github.md） |
| npm publish | `npm whoami` 有输出 | 报阻塞，交用户执行 |

再探**目标可用性**——这两项结论会改变版本号、包名，甚至提交内容，必须在 D 之前拿到：

| 探测项 | 命令 | 结论与去向 |
| --- | --- | --- |
| 远程仓库（GitHub 目标） | `git remote -v`；`git ls-remote --heads origin` | origin 已存在且有远程提交（如 GitHub 用 README 初始化）→ C 之后、D 之前按 [references/github.md](references/github.md) §1 对齐两段历史（这一步会产生一个合并提交），tag 才能一次就落在最终提交上 |
| npm 包名归属（npm 目标） | `npm view <pkg-name> name version dist-tags` | 404 → 全新包，问用户是否改用 scoped 名；与他人同名 → 必须改名或加 scope；是自己 → 版本升级（`npm publish` 会顶掉 `latest`） |

**完成标准**：本次每个发布目标都已有明确结论——可自动 / 不可自动，仓库与包名是就绪还是需要先处理。

### C. 敏感内容审查（强制门禁）

在任何一次 `git commit`、`git push`、`npm publish` 或创建 Release 之前完成，确保没有把密钥、令牌、密码、客户 PII、生产配置或未脱敏日志带进将被推送到公网的提交 / 包体。发现可疑内容直接报阻塞，不带病提交。

清单、门禁脚本（`scripts/scan-sensitive.sh`）与放行条件见 [references/sensitive-content.md](references/sensitive-content.md)——该文件是这项门禁的唯一权威版本，命令不要在此处复制。

**完成标准**：`references/sensitive-content.md` §4 的放行条件全部满足；§D 提交前对最终索引重跑一次门禁脚本。结论写进最终报告。

### D. 公共提交与打 tag（两者共享）

版本号 bump、CHANGELOG 归位、重新构建、提交、打 annotated tag 是**一次性的共同动作**，不要为 GitHub 和 npm 各做一遍：

```bash
# 1) package.json version 与 CHANGELOG [Unreleased] → [vX.Y.Z] 同步
# 2) 若 package.json 缺 repository 字段，补上（npm 页面需要它链接回 GitHub）
# 3) 按项目方式重新构建并验证（pnpm run build / typecheck / node --check ...）
# 4) 提交前重跑门禁脚本：bash "<skill 目录>/scripts/scan-sensitive.sh"
#    （构建产物、§1 合并进来的文件，只有到这一刻才进入扫描范围）
# 5) 提交
git commit -m 'chore: bump to vX.Y.Z'
# 6) 打带注释 tag（annotated tag，而非轻量 tag）
git tag -a vX.Y.Z -m 'vX.Y.Z: <一句话概述>'
```

**注意**：构建 / 验证过程常会顺手生成工作区配置或临时 notes 之类的文件；`git status --short` 逐个核对，非预期的一律删除，**不得带入提交**。

**完成标准**：`git status --short` 无输出，且 `git rev-parse vX.Y.Z^{}` 与 `git rev-parse HEAD` 指向同一提交。

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
