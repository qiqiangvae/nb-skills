---
name: handdrawn-infographic
description: 生成「手绘信息图」的提示词（只产提示词，不直接画图），投喂给图片大模型出图。当用户想做手绘风（涂鸦/素描/水彩/蜡笔/粉笔黑板/sketchnote/线条）的信息图、海报、图表、流程图、知识图谱、教学/总结图，或要"手绘风的 AI 绘画提示词/画图 prompt"，或只是随口说"画一张手绘风格的 XX 图"且内容属信息展示类时使用。
---

# 手绘信息图提示词生成器

把用户的**内容需求**（一个主题、几个要点、一段文字）转成一段**结构化提示词**，复制后投喂给图片大模型，得到一张生动的手绘信息图。

## 两条铁律

这两条不处理，出图就会翻车，任何风格都适用。

1. **文字铁律**：信息图必有文字，而模型渲染文字最容易乱码、错拼、变形。核心标题只写 2-6 个短词（中文 2-6 字 / 英文 2-6 词），别用长句；文字语言始终跟随【信息展示语言】；细节说明文字不指望模型画出来，后期用工具叠加。
2. **手绘感要词引导**：默认模型会出完美矢量图，必须显式给 `hand-drawn`、`imperfect sketchy lines`、`visible stroke texture`、`organic wobble` 这类"不完美"词。生动形象同样靠词引导（具体名词 + 动作/表情/隐喻），见【生动化工具箱】。

## 模型分工

给 `中文` 和 `英文` 的提示词各配一组模型，按【信息展示语言】选用，下文统一用这两个词指代：

- **国内模型** = 即梦 / 通义万相 / 文心一格：渲染中文文字可靠，配**中文提示词**。
- **海外模型** = Midjourney / DALL-E / Flux：渲染英文文字可靠，配**英文提示词**。Midjourney 风格最强但文字差；DALL-E 3 英文文字较可靠、适合文字稍多。

## 工作流

### Step 1 理解内容

从用户输入里提取信息图要承载的东西：

- **主题**：一句话说清"这张图在讲什么"
- **信息点**：3-7 个（信息图装不下太多；超过 7 个先帮用户精简或建议拆成多张图）
- **数据/数字**：要突出的数字（如有）
- **目标受众**：给谁看？儿童、同事、客户、大众？决定画风与文案语气
- **信息展示语言**：`中文` / `英文` / `双语`，**默认中文**——用户没提就用中文，不要替他默认英文；用户明确指定则遵循。内容明显面向国外受众（如英文输入的内容）时，可建议切英文，但在输出的大纲里标注出来让用户确认。双语：标题可中英双行，主体短词建议选一种主语言，减少乱码风险。

内容太少（如只说"画一张春节的手绘图"）→ 先补一个合理骨架（如 春节元素 + 习俗 + 时间 + 祝福），写进【内容大纲】让用户改。

**完成标志**：主题 + ≤7 个信息点 + 受众 + 信息展示语言（默认中文）都已确定。

### Step 2 确认风格（必须询问，不自动决定）

- 用户已明确指定 → 读取 `references/style-<风格名>.md`，遵循其中视觉特征，不用再问
- 用户未指定 → **必须问**："想要哪种手绘风格？"，列出 7 种风格 + 一句话特征（见下方风格速查表），等用户确认

询问时可按内容给参考建议（帮他选，不替他选）：

| 内容类型 | 可参考的风格 |
|---------|------------|
| 儿童/教育/亲子 | 蜡笔儿童画风 |
| 教学/课堂/科普 | 粉笔黑板风 |
| 会议记录/知识总结/方法论 | 涂鸦笔记 sketchnote |
| 汇报演示/头脑风暴/活泼内容 | 马克笔涂鸦风 |
| 科技/学术/思考/复古 | 铅笔素描风 |
| 文艺/生活方式/健康/优雅 | 水彩风 |
| 现代/高端/简洁/封面 | 极简线条 |

举例（"参考建议"式询问）：*"这张图适合几种风格：马克笔涂鸦（活泼有能量）、涂鸦笔记（信息密度高）、水彩（文艺优雅）。你想要哪种？"*

**完成标志**：已拿到一个明确风格（指定或用户选出），并读入对应 reference。

### Step 3 规划信息图布局

在提示词里描述布局，模型才能把元素放对位置。常用模式：

- **中心辐射**：中央大标题 + 四周分区（适合概念总览）
- **顶部横幅 + 多列**：标题横贯顶部，下方 3 列并排（适合流程/对比）
- **路径/时间线**：元素沿一条蜿蜒的线排列（适合流程、时间线）
- **堆叠分层**：自上而下分层堆叠（适合金字塔、层级结构）

为每个信息点分配一个**具体视觉元素**（图标/图示），比如"喝水提醒"→ 一杯冒热气的水杯 + 笑脸。

**完成标志**：选定布局模式，且每个信息点都有对应视觉元素。

### Step 4 组装提示词

按【主提示词模板】组装，风格细节从对应 reference 取，生动化手法从【生动化工具箱】取。生成后通读，逐条对照：

- 每个信息点都有对应的视觉元素吗？
- 画面里有"活着"的东西吗（表情、动作、动态元素）？信息图最怕死板。
- 文字克制吗？标题 2-6 个短词，不要长句；文字语言跟随【信息展示语言】。
- 手绘感词到位吗？

### Step 5 输出

按【输出格式】输出结构化提示词包，用户直接复制即可用。

---

## 主提示词模板

一段主提示词，按此结构组织（顺序即优先级）。**提示词整体语言跟随【信息展示语言】**：中文 → 中文提示词 + 国内模型；英文 → 英文提示词 + 海外模型。下面模板是英文结构骨架，中文时翻译对应字段即可：

```
A hand-drawn infographic titled "[TITLE]" about [TOPIC].
Core elements: [元素1], [元素2], [元素3]...
[风格描述：从 references 文件取，直接嵌入]
Layout: [布局描述]
Color palette: [配色]
Mood: [氛围，如 playful / warm / thoughtful]
[生动化细节：拟人、动态、隐喻，见工具箱]
Text on image: "[图中文字，2-6 个短词 — 语言跟随信息展示语言：中文→中文短词，英文→英文短词，双语→中英双行]"
Hand-drawn charm: imperfect sketchy lines, visible stroke texture, organic wobble
```

**示例**（马克笔风，主题：每日喝水；信息展示语言 = 英文）：

```
A hand-drawn infographic titled "DRINK WATER" about daily hydration habits.
Core elements: a smiling water glass doing a little dance, a row of water droplets
marching left to right, a happy faucet with a big grin, a small cactus with a
bubbly speech bubble, a progress tracker drawn as a wobbly ladder.
In thick black marker doodle style: bold hand-drawn outlines with slightly wobbly
uneven strokes, flat bold color fills with visible marker streaks, drawn on white
paper, whiteboard marker energy.
Layout: top title banner with wobbly underline, three sections stacked with
hand-drawn dividers.
Color palette: red, yellow, blue, green primaries on white background, thick black
outlines.
Mood: playful and encouraging.
A water drop character with a determined face climbing a hand-drawn mountain,
little splash stars around it.
Text on image: "8 GLASSES", "HYDRATE", "FEEL GREAT".
Hand-drawn charm: imperfect sketchy lines, visible stroke texture, organic wobble.
```

---

## 生动化工具箱

把抽象信息变成"活的画面"，按需组合使用（不用全用，每张图 2-4 个手法足够）：

- **拟人化**：给物体画脸和表情 — 水杯在微笑、灯泡在思考、箭头有得意的小表情。信息图里的小人/小物有情绪，画面立刻活起来。
- **动态动作**：用动词写元素状态 — "跳起来的水珠"、"飘动的叶子"、"正在奔跑的时钟"。静止的图标 + 动态修饰词 = 生动。
- **隐喻替代**：抽象概念换成具体事物 — "坚持"→ 一只乌龟爬上陡坡；"进步"→ 小树苗长成大树的三个阶段；"团队"→ 一群手拉手的火柴人。隐喻是信息图打动人心的核心。
- **场景化**：把元素放进一个场景，而不是悬浮在白纸上 — "一只小猫趴在数据图表的折线上打盹"。有场景就有故事感。
- **细节加分项**：给画面加一点点"意外" — 飞溅的墨点、飘散的纸屑、一个悄悄藏在角落的小彩蛋（比如一只偷看的小老鼠）。克制地用，一两个就够。

---

## 输出格式

严格按此结构输出（直接给用户，附使用说明）：

### 📋 内容大纲
- 标题：`[标题]`
- 信息点：1. `[...]` 2. `[...]` 3. `[...]`
- 风格：`[风格名]`（用户已确认）
- 信息展示语言：`[中文 / 英文 / 双语]`（默认中文，用户可改）
- 说明：大纲可修改，改完重新生成提示词即可

### 🎨 主提示词（`[信息展示语言]` · 复制即用）
```
[完整提示词 — 语言跟随信息展示语言：中文→中文提示词（国内模型）；英文→英文提示词（海外模型）]
```

### 🌏 备选提示词（`[另一语言]` · 备选给其他模型）
```
[另一语言版本的提示词，保留同样结构与风格描述 — 中文为主时给海外模型用；英文为主时给国内模型用；双语时两版均完整输出]
```

### 🚫 负面提示词（Stable Diffusion / 国内模型）
```
text watermark, blurry, distorted text, misspelled words, photorealistic, 3d render,
perfect vector graphics, smooth gradients, excessive detail, cropped, low quality
```

### 📐 参数建议
- 宽高比：`[竖版 2:3 / 方图 1:1 / 横版 16:9，按内容选：流程/时间线用横版，层级/海报用竖版]`
- 主提示词已按信息展示语言生成 → **中文找国内模型，英文找海外模型**；文字乱码时重绘几次或后期补字
- 模型细节：
  - **Midjourney**：风格最强，但文字渲染差 — 图片文字尽量压到 2-4 个短词，或出图后后期加字
  - **DALL-E 3**：英文文字渲染相对可靠，适合文字稍多的信息图
  - **Stable Diffusion / Flux**：搭配对应风格 Lora 效果更佳，文字仍需克制
  - **国内模型**：支持中文文字渲染，中文提示词可用；长段文字仍建议后期叠加
- 出图后：文字有乱码就重绘几次，或直接用 Canva / 即时设计 后期补文字

---

## 风格速查（详见 references/）

| 风格 | reference 文件 | 一句话特征 |
|------|---------------|-----------|
| 铅笔素描风 | `references/style-pencil-sketch.md` | 石墨排线、灰度质感、内敛复古 |
| 马克笔涂鸦风 | `references/style-marker-doodle.md` | 粗黑描边、高饱和色块、白板能量 |
| 蜡笔儿童画风 | `references/style-crayon-kids.md` | 蜡笔颗粒、天真构图、童趣 |
| 水彩风 | `references/style-watercolor.md` | 柔和晕染、透明通透、文艺 |
| 粉笔黑板风 | `references/style-chalkboard.md` | 深色底 + 粉笔颗粒、课堂感 |
| 涂鸦笔记 sketchnote | `references/style-sketchnote.md` | 手写体 + 框线箭头、信息密度高 |
| 极简线条 line art | `references/style-line-art.md` | 单色流畅线条、大量留白、现代 |

**用户指定风格时，务必读取对应 reference 文件后再组装提示词**，不要凭印象写。
