# 三方 Skills 收录说明

> 本文件记录 `nb-skills` 项目所使用/收录的第三方 Agent Skills，与 `skills/` 目录下自研 skill 区分。
> 安装位置：`~/.agents/skills/`（全局），各项目可按需在 `.agents/skills/` 下单独安装。
>
> 更新时间：2026-06-XX

---

## 目录

- [重点推荐](#重点推荐)
- [收录一览](#收录一览)
- [如何安装 / 更新](#如何安装--更新)

---

## 重点推荐

### ⭐ playwright-cli

浏览器自动化 CLI，为 coding agent 设计，token 高效。

- **来源**：microsoft/playwright-cli
  - 仓库：<https://github.com/microsoft/playwright-cli>
  - 文档：<https://playwright.dev/docs/getting-started-cli>
- **本地路径**：`~/.agents/skills/playwright-cli/`
- **一句话**：用精简的 CLI 命令驱动浏览器（点按、输入、截图、录屏、mock 请求、跑 Playwright 测试），避免把笨重的 tool schema 和无障碍树塞进模型上下文。
- **为什么重要**：相比 Playwright MCP，CLI + SKILL 更省 token，适合要同时处理大代码库 + 浏览器自动化的高频 coding agent。
- **常用命令速查**：

  ```bash
  playwright-cli open <url>            # 打开浏览器（可 --headed / --browser=chrome）
  playwright-cli click <ref>          # 点击（支持 CSS / role= 选择器）
  playwright-cli fill <ref> <text>    # 填入文本
  playwright-cli screenshot           # 截图
  playwright-cli snapshot             # 页面可访问性快照
  playwright-cli pdf                  # 导出 PDF
  playwright-cli press <key>          # 按键 / 回车
  playwright-cli install --skills     # 安装 skill 集
  ```

- **本地附带参考文档**（`references/`）：`element-attributes.md`、`playwright-tests.md`、`request-mocking.md`、`session-management.md`、`storage-state.md`、`tracing.md`、`video-recording.md`。

---

### ⭐ mattpocock/skills

Matt Pocock 公开的「真·工程」Agent Skills 合集，强调可组合、可读、编码纪律而非 vibe coding。

- **来源**：mattpocock/skills
  - 仓库：<https://github.com/mattpocock/skills>
- **安装**：仓库内自带 `/setup-matt-pocock-skills`，在每个 repo 里跑一次即可（写入 `CLAUDE.md` / `AGENTS.md` 的 `## Agent skills` 块，并配置 issue tracker、triage 标签、domain doc 布局）。
- **本地路径**：`~/.agents/skills/`
- **为什么重要**：它把「规划、调试、TDD、领域建模、交接、git 护栏」这类真实工程流程固化成小颗、可组合的 skill，是比「一段 prompt 一个文件夹」更健康的 agent 工作流范式。
- **完整 skill 清单**（已本地安装）：

  | Skill | 用途 |
  | --- | --- |
  | `setup-matt-pocock-skills` | 一次性初始化仓库（issue tracker / triage 标签 / domain 文档） |
  | `ask-matt` | 路由：帮用户判断当前用哪个 skill / 流程 |
  | `wayfinder` | 把超出一个 session 的大块工作拆成共享决策地图（issue 上的 decision tickets），逐个推进 |
  | `to-spec` | 把当前对话综合成 spec，发布到 issue tracker（不反问、直接综合） |
  | `to-tickets` | 把 plan/spec/对话拆成带阻塞边的 tracer-bullet tickets |
  | `to-questionnaire` | 把回答不了的决策转成问卷给他人异步填写 |
  | `triage` | 让 issue / 外部 PR 走 triage 状态机（分类、验证、必要时 grill、写 agent-ready brief） |
  | `handoff` | 把当前对话压缩成交接文档，供新 agent 接手 |
  | `grill-me` / `grill-with-docs` / `grilling` | 对计划/设计做无情追问（`grill-with-docs` 额外产出 ADR + 术语表） |
  | `code-review` | 按「标准 + 规格」双轴 review 一处改动 |
  | `codebase-design` / `improve-codebase-architecture` / `domain-modeling` | 深模块设计、架构改进、领域建模词汇 |
  | `diagnosing-bugs` | 疑难 bug / 性能回退诊断回路 |
  | `tdd` | 测试驱动开发（red-green-refactor） |
  | `prototype` | 建一次性原型验证设计问题 |
  | `research` | 对高可信一手来源做调研并沉淀带引用的 Markdown |
  | `resolving-merge-conflicts` | 解 git merge/rebase 冲突 |
  | `implement` | 执行实现 |
  | `teach` | 在该 workspace 内教用户一个新 skill / 概念 |
  | `writing-for-agents` | 写给 agent 看的文档（skill / AGENTS.md / CLAUDE.md） |
  | `wait-what` | 澄清前置：先对「到底要做什么」对齐再动手 |
  | `wizard` | 生成交互式 bash wizard，引导人类完成只有他能做的步骤 |

---

## 收录一览

> 星级 = 该 skill 对本项目/日常的推荐程度；「已装」指本地 `~/.agents/skills/` 实际存在。

| Skill | 来源 | 用途 | 推荐 |
| --- | --- | --- | --- |
| `playwright-cli` | microsoft/playwright-cli | 浏览器自动化 CLI | ⭐⭐⭐ |
| `setup-matt-pocock-skills` 及整套工程 skill | mattpocock/skills | 规划/调试/TDD/领域建模/交接 | ⭐⭐⭐ |
| `find-skills` | 社区 | 发现并安装 agent skills | ⭐⭐ |
| `okr-coach-zh` | 社区 | 大厂风格 OKR 教练 | ⭐ |
| `outlook-microsoft` | 社区 | 世纪互联版 Outlook 邮件/日历 | ⭐ |

> 注：`handdrawn-infographic`、`reply-cr`、`zagent-gen` 为自研/团队 skill 的符号链接，指向 `~/.config/ocean-skills/skills/`，详见各自项目。

---

## 如何安装 / 更新

### playwright-cli

```bash
# 安装 CLI（npm 全局或 npx）
npm i -g @playwright/cli        # 视实际包名而定，见官方文档
playwright-cli install --skills # 同时安装 skill 集到 ~/.agents/skills/
```

更新方式见 <https://playwright.dev/docs/getting-started-cli>。

### mattpocock/skills

```bash
# 在每个 repo 里跑一次初始化
/setup-matt-pocock-skills
```

或将仓库 `skills/` 目录同步到 `~/.agents/skills/`。更新源仓库：<https://github.com/mattpocock/skills>。

---

## 维护约定

- 新收录三方 skill 时，在本文件「收录一览」加一行，并在相应小节补充来源、本地路径、一句话用途。
- 自研 skill 放 `skills/` 目录并写 `SKILL.md`；三方 skill 只记录来源与使用说明，不在本项目内复制其内容（避免版本漂移）。
- 链接上方「更新时间」为当前日期。
