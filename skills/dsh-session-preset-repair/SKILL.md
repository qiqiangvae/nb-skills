---
name: dsh-session-preset-repair
description: Diagnose and fix a DSH (DeepSeek Harness) session that fails to resume with `agent-presets: preset "X" not found`, and prevent the same breakage before deleting a preset. Use when a session errors on resume mentioning a missing agent preset, or before removing/renaming a custom agent preset directory under ~/.dsh/.agent-presets/.
---

# DSH Session Preset Repair（修复 resume 报 preset 缺失 / 预防删 preset 踩坑）

## 何时使用

- 一个历史 session 打开 / resume 时报错：`Error: agent-presets: preset "pp-liangshen" not found (available: ...)`
- 你**即将删除或重命名** `~/.dsh/.agent-presets/` 下的某个 preset，想先评估影响面、避免历史会话打不开。

## 背景：为什么删了 preset 会导致会话打不开

DSH 把一个会话的「实际运行的 preset」记录在会话日志里，而不是某个全局配置：

1. **物理位置**：每个会话一个目录，日志文件路径为
   `~/.dsh/sessions/<projectKey>/<sessionId>/session.jsonl.zstd`
   （`<projectKey>` 是 cwd 经过 `projectKey()` 转义后的目录名，形如 `--Users-qiqiang-Code-zagent--`）。
2. **preset 的解析规则**（源码 `@deepseek-ai/dsh-agent-presets/lib/types/session.js` 的 `resolveSessionPreset`）：
   - 会话头（第一行 `type:"session"`）里的 `agentPreset` 只是**创建时**的值；
   - 会话运行中切换 preset 会写入一条事件 `{"type":"agent-preset/selected","data":{"agentPreset":"..."}}`；
   - resume 时**从后往前**遍历 events，取**最后一个** `agent-preset/selected` 的 `agentPreset`，没有才回退到头里的值。
3. 所以：即使头里写的是 `standard`，只要运行中某时刻选过一个后来**被删掉**的 preset（如 `pp-liangshen`），那条事件就还在日志里，resume 时就会读到一个已不存在的 id 而报错。

## 文件格式的硬约束（务必先懂再动手）

`session.jsonl.zstd` 是「**多个独立可解压、带 checksum 的 zstd frame 拼接**」容器，不是单个压缩块：

- 第一个 frame **必须恰好是独立的一行 header**（源码 `assertZstdHeaderFrame` 要求 `plaintext.indexOf("\n") === plaintext.length - 1`）。
- 读取时 `scanZstdFrames` 按 `magic → frame header → blocks → checksum` 逐帧扫描；每帧独立解压、独立校验 checksum。
- 每次 append 都追加一个新的独立 frame，所以一个长会话可能有两千多个 frame。

**绝对禁止**：用 `zstd` CLI 或任何"整体解压后重新压缩"的方式改写这个文件。把 2000+ frame 压成单 frame 后，第一帧不再是"一行 header"，帧边界全乱，DSH 会抛 `corrupt Zstandard session log` 甚至崩溃（这是本 skill 面世前实测踩过的坑）。**修复必须做到"只动目标那一个 frame，其余字节零改动"。**

## 诊断流程

1. **确认是哪个 preset 缺失、可用哪些**：报错文本里已给出 `not found (available: ...)`。用 `ls ~/.dsh/.agent-presets/` 交叉核对实际存在哪些 preset 目录（内置 preset 如 `standard/code/minimal/cordis` 不一定在 `.agent-presets/` 下）。
2. **定位报错的 session**：报错里的 session id → 找到其目录
   `find ~/.dsh/sessions -maxdepth 3 -type d -name '<sessionId>'`
3. **确认该 session 日志里记录的 preset**（用脚本或 `zstd -dc` 解压看）：
   - 会话头 `agentPreset`（第 1 行）
   - 所有 `agent-preset/selected` 事件，最后一个即生效值
4. **评估影响面**（尤其删 preset 前做这一步）：
   `grep -rln "<旧preset名>" ~/.dsh/sessions/ 2>/dev/null`
   找出所有引用了该 preset 的 session。

## 修复流程（安全、不破坏格式）

用本 skill 附带的脚本 `scripts/fix-session-preset.mjs`，它精确复刻 DSH 的帧扫描逻辑，只重写含目标事件的那一个 frame：

```bash
# 先备份（脚本本身不会覆盖输入，但养成习惯）
node ~/.agents/skills/dsh-session-preset-repair/scripts/fix-session-preset.mjs \
  "$HOME/.dsh/sessions/--Users-qiqiang-Code-zagent--/fc53fdbf-f3f5-4b2e-9680-14ce8b66c78a/session.jsonl.zstd" \
  pp-liangshen pingpong
```

脚本会：
1. 复刻 `scanZstdFrames` 逐帧扫描，打印总帧数；
2. 从后往前找第一个包含 `"agentPreset":"<旧preset>"` 的 `agent-preset/selected` 帧；
3. 只解压该帧 → 字符串替换 → 用 `ZSTD_c_checksumFlag:1` 重压这**一个**帧；
4. 原位 splice 回去，其余帧字节不动；
5. 输出到 `<name>.fixed.zstd` 并打印校验报告（帧数不变、无 torn tail、每帧可解压、头帧仍是单行、旧 preset 无残留、新 preset 已写入）。

校验报告全部 OK 后，手动落盘：

```bash
cd <session目录>
cp session.jsonl.zstd session.jsonl.zstd.orig
cp session.jsonl.zstd.fixed.zstd session.jsonl.zstd
```

然后在 GUI 里重新打开 / resume 该 session 即可。

### 若不用脚本、手工改（原理一致）

1. 用 DSH 同样的 `scanZstdFrames` 逻辑（magic `0xFD2FB528` + frame header 解析）找出每个 frame 的字节范围；
2. 定位包含目标行的那个 frame；
3. 只解压/替换/重压那一个 frame（务必带 checksum 参数，与原写路径一致）；
4. 其余 frame 用原始字节原样拼接。
任何"整体重压"都会破坏容器。

## 预防清单（删 preset 之前）

删除或重命名 `~/.dsh/.agent-presets/<name>/` 之前：

1. `grep -rln "\"agentPreset\":\"<name>\"" ~/.dsh/sessions/ 2>/dev/null` 扫一遍历史会话；
2. 若有用到它的会话：要么先按上文把那些会话切到仍存在的 preset，要么**保留一个同名空壳 preset**（只留 `preset.yml` 的 name/order 最小字段）让历史会话能正常打开；
3. 确认无遗漏后再删。

## 相关机制速查

- session 目录：`~/.dsh/sessions/<projectKey(cwd)>/<sessionId>/`
- preset 目录：`~/.dsh/.agent-presets/<presetName>/`（内置 preset 不在磁盘此目录）
- 关键源码文件（npm 包）：
  - `@deepseek-ai/dsh-agent-presets/lib/types/session.js` → `resolveSessionPreset`
  - `@deepseek-ai/dsh-session-persistence-jsonl/lib/index.js` → `scanZstdFrames`、`assertZstdHeaderFrame`、`CHECKSUM_OPTIONS`
