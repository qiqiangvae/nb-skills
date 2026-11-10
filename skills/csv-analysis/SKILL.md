---
name: csv-analysis
description: 用 pandas 分析 CSV / TSV / CSV.GZ 表格：先探测编码与规模，再用脚本算分布统计、分组占比、时间序列、窗口对比、基线偏离、结构变化、间隔节奏、形态与两表对齐，只把结构化 JSON 结论喂给模型，绝不把原始表格读进上下文。当用户让你分析、统计、对比、找异常一个 csv/tsv（含 .gz），问「这批数据里怎么样」「哪个最多」「最近有没有变化」，要看趋势/占比/集中度/快慢/留存，或要核对两张表的差异时使用。不触发：要改 xlsx / Excel 公式 / 多 sheet（用 office-xlsx），要生成图表图片，要出 Word/PPT/PDF。
---

# csv-analysis

**这个 skill 存在的唯一理由**：让模型只看见「结论和口径」，不看见原始表格。
数据体量再小，逐行读进上下文也会让判断失准 —— 数字是抄来的，不是算来的。

## 铁律

1. **不许直接读数据文件**。`Read` / `cat` / `head` / `less` 一律不用；想看原文只走 `peek`。其余一切数值必须由脚本算。
2. **分析结果只走 `show()`**。禁止裸 `print(df)`、禁止 `df.to_csv`、禁止把整表塞进回答。
3. **数值比较先定容差**。金额/浮点先 `round(2)` 或给 `--tol`，禁止裸 `==`；1e-12 的浮点噪声会把「完全匹配」算成「不匹配」。
4. **除法前判零**。除数为 0 输出 `null`，不要 `inf` / `NaN` 混进结论。
5. **不完整的时间桶不进基线**。`complete:false` 的当期不能和完整期直接比。
6. **采样必须声明**。用了 `--sample` / `nrows`，结论里必须写「基于前 N 行」。
7. **不造阈值**。所有阈值都是参数；没给参数就只描述相对偏离，别下「异常」结论。
8. **不同口径不硬比**。单位、币种、时区、去重主体没对齐时，先报「不可比」。

## 开局三步（几乎总是这么起）

```bash
python3 scripts/tabular.py peek   data.csv          # 编码/分隔符/表头/前 5 行原文
python3 scripts/tabular.py scout  data.csv          # 字节/估算行数/内存档位/列名
python3 scripts/tabular.py profile data.csv         # 质量体检 + flags
```

`peek` 是**唯一**允许看原始内容的命令（6 行 × 300 字符）。`profile` 遇到可疑列会在 `flags` 里点名：
`leading_zero_lost`（前导零已被丢）、`numeric_as_text`（千分位/符号导致存成文本）、
`mixed_type`（同列数字与文本混杂）、`id_like`（唯一率 >95%）、`has_null`。
**看到这些 flag 先处理口径，再算指标**——否则后面每个数都是错的。

问题已经非常具体时（「这列均值多少」）可以跳过开局，直接 `agg`。

## 算子对照表

| 你要回答 | 命令 |
|---|---|
| 最小值/最大值/均值/中位/分位/波动/0 值 | `agg --col x` |
| 哪一组最大、占比、集中度、组内去重数 | `agg --col x --by g --top 10 --distinct-by id` |
| 按天/周/月的走势；最近一期 vs 历史基线 | `agg --col x --time t --freq M --baseline 12` |
| 最近 7/30/90 天 vs 之前 | `agg --col x --time t --windows 7,30,90` |
| 哪些组新出现/消失了、份额怎么迁移 | `agg --col x --by g --time t --compare 30d,90d` |
| 节奏：相邻事件间隔、是否过密 | `agg --time t --interval --key id` |
| 整数金额、相近金额、同刻多笔、重复行 | `shape --col x --time t --ints --near 5 --same-ts 3 --dups` |
| 两张表按 key 对齐：时间差、金额是否匹配 | `match a.csv b.csv --key id --time-a t1 --time-b t2 --val-a v1 --val-b v2` |
| 以上都不够 | `run`（现写 pandas，出口只有 `show()`） |

`agg` 输出里 **`baseline.ratio_to_baseline` / `zscore` 是偏离证据**，`by` 模式里 `hhi` / `cr3` / `share` 是集中度证据，
`freq` 模式里每个桶的 `complete` 是可比性证据。引用结论时把这三类数字带上，别只写「有变化」。

## 内存与规模

`scout` 会给出 `budget_mb`（cgroup 可用内存 × 0.7）和 `tier`；`est_mem = 解压后字节 × 3`
（×3 是实测上界：数值表 1.74×、长文本宽表 2.72×，宁可保守也不让 OOM 静默发生）：

- **A**：直接全读，别优化。
- **B**：仍可全读；宽表加 `--cols` 裁列。
- **C**：`profile` 能跑（全程流式，12M 行实测 171MB）；`agg` / `shape` / `match` 会**拒绝执行**并给提示，
  此时只能 `--sample 200000`（并声明采样）或改用 `run` 配 `chunksize`。

`agg` 拒绝不是 bug —— 被 OOM 杀掉是静默的，拒绝是响亮的。

## 输出与引用

- 除 `peek` 外全部输出 **JSON**，直接取里面的数字，**不要自己重算**。
- `run` 里可用 `pd`、`np`、`show()`、`load()`、`budget()`（当前可用内存 MB），以及预加载的 `df`（给了路径时）。
  文件超过 `budget()` 的大致 1/3 就别 `read_csv` 整表，直接用 `chunksize`。
- 结论里出现数字，必须能对回某个 JSON 字段；写不出来源的数字就是编的。
- 超过长度上限会报 `output_too_large`，用 `--top` / `--windows` / `--cols` 收窄，不要重试原命令。

## 出错怎么办

| 输出 | 处理 |
|---|---|
| `error: bad_rows` | 列数不齐/引号未闭合，`detail` 里有行号；用 `peek` 看原文，修源数据，或 `--skip-bad`（必须注明跳过） |
| `error: tier_C` | 见上节，`--sample` 或 `run` + `chunksize` |
| `error: output_too_large` | 收窄参数 |
| `encoding` 相关失败 | 不猜编码；让用户把源文件统一成 utf-8 |
| `no_match` | 两表 key 没有一个交集，先核对 key 的格式（前导零、大小写、空格） |
| `merge_explosion` | key 不唯一，对齐后行数是两侧 10 倍以上；换唯一 key（订单号/流水号），别硬对齐 |

## 分析纪律

- 先建基线再判断偏离；样本不足时别用不稳定的均值下结论。
- 单一指标偏离只是线索；多维度同向变化才值得下判断。
- 统计异常 ≠ 风险，要区分「异常」与「有解释的异常」。
- 数据不可比时先降置信度，不要硬算一个漂亮数字。

## 不做的事

xlsx / Excel 公式 / 多 sheet（→ office-xlsx）、图表图片、写回文件、自动清洗修数据（只报不修）、
模糊实体归一、cohort 留存矩阵、季节性分解、变点检测。

更细的坑与实测数字见 `references/pitfalls.md`。
