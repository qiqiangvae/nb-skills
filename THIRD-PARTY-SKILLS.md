# 三方 Skills 收录说明

> 本文件记录 `nb-skills` 项目所使用/收录的第三方 Agent Skills，与 `skills/` 目录下自研 skill 区分。
> 安装位置：`~/.agents/skills/`（全局），各项目可按需在 `.agents/skills/` 下单独安装。
>
> 更新时间：2026-09-13

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
- **安装位置**：全局 skills 目录 `~/.agents/skills/playwright-cli/`（或项目级 `.agents/skills/`）
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

- **附带参考文档**（`references/`）：`element-attributes.md`、`playwright-tests.md`、`request-mocking.md`、`session-management.md`、`storage-state.md`、`tracing.md`、`video-recording.md`。

---

### ⭐ mattpocock/skills

Matt Pocock 公开的「真·工程」Agent Skills 合集，强调可组合、可读、编码纪律而非 vibe coding。

- **来源**：mattpocock/skills
  - 仓库：<https://github.com/mattpocock/skills>
- **安装**：仓库内自带 `/setup-matt-pocock-skills`，在每个 repo 里跑一次即可（写入 `CLAUDE.md` / `AGENTS.md` 的 `## Agent skills` 块，并配置 issue tracker、triage 标签、domain doc 布局）。
- **安装位置**：全局 skills 目录 `~/.agents/skills/`（或项目级 `.agents/skills/`）
- **为什么重要**：它把「规划、调试、TDD、领域建模、交接、git 护栏」这类真实工程流程固化成小颗、可组合的 skill，是比「一段 prompt 一个文件夹」更健康的 agent 工作流范式。
- **完整 skill 清单**：

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

### ⭐ guizang-ppt-skill（歸藏 PPT Skill）

用 Agent 生成网页 PPT：**单文件 HTML 横向翻页 deck**，自带演讲者视图、观众屏同步、讲稿备注与排练计时。

- **来源**：op7418/guizang-ppt-skill（作者 [歸藏](https://x.com/op7418)），仓库 <https://github.com/op7418/guizang-ppt-skill>
- **一句话**：两套视觉系统 —— Style A「电子杂志 × 电子墨水」（衬线标题 + WebGL 流体背景 + 暖色），Style B「瑞士国际主义」（网格点阵 + IKB / 柠檬黄 / 柠檬绿 / 安全橙锚点色）；同一套视觉规则还能出公众号 21:9、小红书 3:4 等封面。
- **亮点**：单文件 HTML，不需要构建或服务器；横向翻页支持键盘 ← →、滚轮、触屏、底部圆点与 ESC 索引；Style A 多种布局、Style B 锁定版式；内置演讲者模式（当前页 / 下一页 16:9 预览、结构化备注、计时排练、自动翻页、激光笔、圈选、黑/白屏、观众屏同步）；按 `B` 可关掉 WebGL 动画走低功耗静态背景。
- **适合 / 不适合**：适合线下分享、行业讲话、产品发布、demo day、带个人风格的演讲；不适合大段表格数据、培训课件、需要多人协作编辑（静态 HTML）。当前核心交付是 HTML，PPTX 不在主流程内。
- **触发词**：「杂志风 PPT」「瑞士风 PPT」「Swiss Style」「horizontal swipe deck」「editorial magazine style presentation」。
- **自检**：对照 `references/checklist.md`（P0 项必须全过）；两套主题分别跑 `node scripts/validate-swiss-deck.mjs`、`node scripts/validate-presenter-mode.mjs` 校验版式 / 图片槽位 / 对齐（有 Playwright 时做后验测量）。

---

### ⭐ ponytail

「懒惰资深工程师」编码技能：每轮给 Agent 注入一套极简编码约束，外加一组按需加载的过度工程审查 / 审计 / 技术债技能。

- **来源**：[DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)（MIT，20+ 种 agent 通用）
  - npm：`@dietrichgebert/ponytail`
- **一句话**：用 YAGNI 决策阶梯（能不写 → 复用已有 → 标准库 → 原生能力 → 已装依赖 → 一行 → 最小实现）约束每轮产出，默认选最短正确实现，修根因而非症状；安全底线（输入校验、防数据丢失、安全措施、无障碍、明确验收项）在任何档位都不可删。**先读懂问题再看阶梯**——懒惰是针对方案，不是针对读代码。
- **档位**：`/ponytail lite|full|ultra|off`（默认 `full`；`ultra` 会先要证据、优先删除或复用、主动质疑投机性抽象/缓存/新依赖，但不是无脑拒绝）。可用 `PONYTAIL_DEFAULT_MODE` 环境变量或 `~/.config/ponytail/config.json` 的 `defaultMode` 设默认值。
- **配套技能**（按需加载，不占常驻 prompt）：`/ponytail-review` 针对最近改动只挑过度工程（每条带位置、替代方案与实际调用证据）、`/ponytail-audit` 全仓审计并区分「可安全删除」与「需先验证」、`/ponytail-debt` 把代码里的 `ponytail:` 注释收割成债务账本、`/ponytail-gain` 上游 Benchmark 计分板、`/ponytail-help` 参考卡。
- **为什么推荐**：它把「能不写就不写」变成常驻约束而不是一次性提醒，恰好对冲 Agent 默认爱加抽象、缓存和新依赖的偏科。上游实测（真实 Claude Code 会话改真实开源仓库，Haiku 4.5，n=4）：代码量 **-54%**（过度构建场景最高 -94%）、成本 -20%、耗时 -27%，且安全项 100% 保留。注意该数字来自**上游 Benchmark，不是普遍保证**——上游也说明在以「思考 token」为主的推理模型上可能反向变差。
- **形态**：多 agent 通用，各宿主装法不同（plugin / extension / 规则文件 / `AGENTS.md`），详见下方安装小节。

---

## 收录一览

> 星级 = 该 skill 的推荐程度（⭐⭐⭐ 强烈推荐 / ⭐⭐ 值得一试 / ⭐ 场景有限）。

| Skill | 来源 | 用途 | 推荐 |
| --- | --- | --- | --- |
| `playwright-cli` | microsoft/playwright-cli | 浏览器自动化 CLI | ⭐⭐⭐ |
| `guizang-ppt-skill` | op7418/guizang-ppt-skill | 网页 PPT（杂志风 / 瑞士风）+ 演讲者模式 | ⭐⭐⭐ |
| `ponytail` | DietrichGebert/ponytail | 常驻极简编码模式 + review / audit / debt 技能 | ⭐⭐⭐ |
| `setup-matt-pocock-skills` 及整套工程 skill | mattpocock/skills | 规划/调试/TDD/领域建模/交接 | ⭐⭐⭐ |
| `find-skills` | 社区 | 发现并安装 agent skills | ⭐⭐ |
| `okr-coach-zh` | 社区 | 大厂风格 OKR 教练 | ⭐ |
| `outlook-microsoft` | 社区 | 世纪互联版 Outlook 邮件/日历 | ⭐ |

> 注：`handdrawn-infographic`、`reply-cr`、`zagent-gen` 为自研 / 团队 skill，来源与用法见各自项目。
> 注：`ponytail` 是多 agent 通用技能，各宿主装法不同（plugin / extension / 规则文件），见下节。

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

### guizang-ppt-skill

```bash
# 官方一行安装（skills CLI）
npx skills add https://github.com/op7418/guizang-ppt-skill --skill guizang-ppt-skill

# 或 git clone 到全局 skills 目录，之后可用 git pull 更新
git clone https://github.com/op7418/guizang-ppt-skill.git ~/.agents/skills/guizang-ppt-skill
```

更新：`cd ~/.agents/skills/guizang-ppt-skill && git pull`。上游说明见 <https://github.com/op7418/guizang-ppt-skill>。

### ponytail

上游是一个多 agent 通用技能（[DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)，MIT，
官方标注 works with 20 agents），各宿主装法不同，按自己的 agent 选一种：

```bash
# Claude Code（两条命令要分两次发送）
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail

# Codex
codex plugin marketplace add DietrichGebert/ponytail && codex plugin add ponytail@ponytail

# GitHub Copilot CLI
copilot plugin marketplace add DietrichGebert/ponytail && copilot plugin install ponytail@ponytail

# Gemini CLI
gemini extensions install https://github.com/DietrichGebert/ponytail

# OpenCode（写进 opencode.json）
{ "plugin": ["@dietrichgebert/ponytail"] }

# Cursor
git clone https://github.com/DietrichGebert/ponytail && node ponytail/scripts/cursor-hooks.js install
```

Windsurf / Cline / Kiro / Qoder / Zed / Aider / Junie / Copilot Chat 等：拷贝对应的规则文件
（`.windsurf/rules/`、`.clinerules/`、`.kiro/steering/`、`.qoder/rules/`、`AGENTS.md` 等），
或直接读仓库自带的 `AGENTS.md` 即可生效（无需安装）。

Claude Code / Codex 的插件会跑两个 Node.js 生命周期钩子，需 `node` 在 PATH 上；没有也能用，
只是「每轮自动注入」会静默失效。完整宿主列表、卸载方式与 Agent portability 说明见上游 README。

> 社区另有针对特定宿主的封装版（如 npm 上的 `@mengyuly/dsh-ponytail`），本质是同一套规则的上游再分发；
> 除非该宿主没有上游原生支持，优先用上游。

---

## 维护约定

- 新收录三方 skill 时，在本文件「收录一览」加一行，并在相应小节补充来源、能力亮点、适用场景与安装 / 更新方式；只写 skill 本身（来源、能做什么、怎么装怎么用），不写个人机器上的安装状态或目录。
- 自研 skill 放 `skills/` 目录并写 `SKILL.md`；三方 skill 只记录来源与使用说明，不在本项目内复制其内容（避免版本漂移）。
- 链接上方「更新时间」为当前日期。
