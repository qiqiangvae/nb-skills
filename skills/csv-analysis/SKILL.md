---
name: csv-analysis
description: 用脚本算 csv/tsv/gz 表格，只把 JSON 指标喂进上下文，不读原始行。触发：给了表格要结论（怎么回事 / 哪边多 / 为什么变了）、两张表要对齐、怀疑编码乱码或文件大到读不动。不触发：改 xlsx、出图、出文档。
---

# csv-analysis

**只算不读**：看原文只走 `peek`，其余一切数值由脚本算，结论只引 JSON 字段。
数字是抄来的就会错，算出来的不会。

## 铁律

1. **看数据只走 `peek`** —— 编码、分隔符、表头、前 5 行一次给全。
2. **输出只走 `show()`** —— 自动 `head(100)`、每格截 120 字符、末尾报省略行数。
3. **数值比较带容差** —— 先 `round(2)` 或给 `--tol`。
4. **除法先判零** —— 分母为 0 时给 `null`。
5. **口径不一致先报「不可比」** —— 单位、币种、时区、去重主体、时间桶完整性（`complete:false`）任一没对齐，就不比。
6. **输出里出现的截断，结论里必须同步声明** —— `--sample` / `group_truncated` / `bucket_truncated` / `quantiles: unavailable_in_streaming`。
7. **阈值只用参数** —— 没给参数就只报相对偏离。

## 开局

```bash
python3 scripts/tabular.py peek    data.csv   # 必做
python3 scripts/tabular.py profile data.csv   # 必做
python3 scripts/tabular.py scout   data.csv   # .gz 或 >50MB 才做
```

**探究完成判据**（三条全满足才进分析）：

- `profile` 的 JSON 已出，行数、列数都在（有时间列则 `time_range` 也在）；
- 每个 `flags` 命中都已按下面的动作表处理，或明确记入「口径待确认」；
- 已能说出接下来要用哪几条算子 —— 说不出就 `profile --cols` 收窄再看一次。

用户只说「帮我分析一下」时的默认范围，按顺序做三步：`agg` 主要数值列（sum/mean/median/min/max）→ 有时间列就 `--freq M --baseline 12` → 有分组列就 `--by --top 10`。

## flag 动作表

| flag | 动作 |
|---|---|
| `leading_zero_lost` | 重读时显式 `dtype={"该列":"str"}`，零已经丢了 |
| `numeric_as_text` | 先 `run` 清洗（千分位 / 货币符号 / 空格）再 `agg`，结论注明已清洗 |
| `mixed_type` | 只对可解析部分算，或按可解析性分列；静默丢行会让分母变小 |
| `non_numeric` / `digit_string` | 当编号用（count / distinct），不进均值 |
| `id_like` | 只做 count / distinct，不做 mean |
| `has_null` | 先定分母口径：含空行还是不含 |

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
| 两列比值 / 留存 | `agg --col 分子 --ratio 分母 [--by g \| --freq M]` |
| 以上都不够 | `run`（现写 pandas，出口只有 `show()`） |

引用结论时带上证据字段：`baseline.ratio_to_baseline` / `zscore`（偏离）、`hhi` / `cr3` / `share`（集中度）、`complete`（可比性）。

## 写 `run` 时的四个坑

1. **`low_memory` 保持默认** —— 设成 `False` 会让 682MB 的文件峰值从 268MB 涨到 2100MB。
2. **`dtype="category"` 在读入时更费内存** —— 转换要先建整列 object 再 factorize，实测比全读还高（226MB → 388MB）。
3. **`"202611"` 这类月份是字符串** —— 转 int 会排错序；要转日期先补日（`2026-11-01`）。
4. **gzip 不能随机 seek** —— 跳读第 10 万行要先解压到那里，所以采样只能从头 `nrows`。

## 内存与规模

`scout` 给出 `budget_mb`（cgroup 可用内存 × 0.7）和 `tier`：

- **A / B**：可全读；宽表加 `--cols` 裁列。
- **C**：`profile` 与 `agg` 自动切流式，`sum/count/mean/min/max/std/cv/zeros/top3`、分组、时间桶、窗口、比值、基线**保持精确**；只有分位数与 `distinct` 不可得，分别标 `quantiles: unavailable_in_streaming` 和 `distinct_note`。
- **`shape` / `match` / `agg --interval` 在 C 档拒绝**（需要排序或双向对齐）。此时用 `--sample 200000` 并声明采样，或 `run` 配 `chunksize`。

`run` 里用 `budget()` 自查：文件超过它的 1/3 就直接 `chunksize`。

## 收尾判据

交付前逐条过：

1. 用户问的每个数，都能指出是哪次命令的哪个字段；
2. 每个「变化 / 异常」结论，至少有「分布 / 时间 / 结构」三维里两维的独立证据；
3. 采样、不完整期、分组截断、分位数不可得，四处中命中哪些就声明哪些；
4. 说「异常」之前先写了正常解释的可能，或明确写了「未验证」。

## 出错怎么办

| 输出 | 处理 |
|---|---|
| `error: bad_rows` | 列数不齐 / 引号未闭合，`detail` 带行号；`peek` 看原文，修源数据，或 `--skip-bad`（须注明） |
| `error: tier_C` | 只出现在 `shape` / `match` / `--interval`：`--sample` 或 `run` + `chunksize` |
| `error: output_too_large` | 用 `--top` / `--windows` / `--cols` 收窄，别重试原命令 |
| `error: merge_explosion` | key 不唯一导致笛卡尔积；换唯一 key（订单号 / 流水号） |
| 编码失败 | 让用户把源文件统一成 utf-8，不猜编码 |
| `{"error":"no_match"}`（正常输出，rc=0） | 两表 key 无交集，核对格式：前导零、大小写、前后空格 |

## 边界

这个 skill 覆盖「读 + 算 + 答」。任务里出现改 xlsx、出图、写回文件时，直接说它不覆盖并停在结论 —— 那几件事属于别的工具。
