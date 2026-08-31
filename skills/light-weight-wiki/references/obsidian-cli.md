# obsidian-cli（控制运行中的 Obsidian）

> 原 dsh-obsidian skill `obsidian-cli`，名字保留。**注意：这一册需要 Obsidian 应用在运行并启用 CLI**（Settings → General → Enable CLI），只在装好 Obsidian 及其 CLI 的环境可用，其余 agent/机器上会失效——其余分册才是跨 agent 通用的部分。

通过 `obsidian` CLI 与运行中的 Obsidian 实例对话：读、建、搜、管理笔记/任务/属性，以及插件/主题开发循环。

## 常用命令

```bash
obsidian read file="My Note"
obsidian create name="New Note" content="# Hello" template="Template" silent
obsidian append file="My Note" content="New line"
obsidian search query="search term" limit=10
obsidian daily:read
obsidian daily:append content="- [ ] New task"
obsidian property:set name="status" value="done" file="My Note"
obsidian tasks daily todo
obsidian tags sort=count counts
obsidian backlinks file="My Note"
```

- `file=<name>` 按 wikilink 风格定位；`path=<path>` 按精确路径。
- 打开了多个 vault 时先用 `vault=<name>` 消歧。
- `--copy` 把结果放到剪贴板。

## 插件 / 主题开发循环

```bash
obsidian plugin:reload id=my-plugin
obsidian dev:errors
obsidian dev:screenshot path=screenshot.png
obsidian dev:dom selector=".workspace-leaf" text
obsidian dev:console level=error
obsidian eval code="app.vault.getFiles().length"
```

循环：重载 → 查错 → 可视核验 → 查 console。

## 与本工具链的关系

CLI 直连 Obsidian 应用；而本 skill 的 `scripts/`（检索/写入/检查）是**文件层**操作，不需要 Obsidian 运行。需要"打开/展示/插件开发"才走 CLI；纯内容沉淀用脚本即可。
