#!/usr/bin/env python3
"""tabular.py — CSV / TSV / CSV.GZ 的通用分析原语。

子命令：
  peek     原文视图（唯一允许看原始内容的口子）
  scout    元数据 + 内存档位（不加载数据）
  profile  质量体检：空值/重复/类型混杂/基数/时间范围/flags
  agg      万用聚合：分布统计 / 分组 / 时间桶 / 窗口 / 基线 / 间隔 / 结构对比
  shape    形态识别：整数、相近值、同刻多笔、重复行、短间隔
  match    两表按 key 对齐 → 时间差 / 数值差分布
  run      自由执行器（模型现写脚本，唯一输出出口是 show()）

除 peek 外的输出都是 JSON。所有阈值都走参数，不给暗值。
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

SAMPLE_BYTES = 1 << 18
HEAD_LINES = 200
LIMITS = {"scout": 2500, "profile": 9000, "agg": 14000, "shape": 5000, "match": 5000}
TIER_A_MB = 300
MEM_FACTOR = 2.0
MAX_BUCKETS = 60
MAX_DISTINCT = 10000
SHOW_ROWS = 100
SHOW_CHARS = 120
CANDIDATE_DELIMS = ",;\t|"
NUM_TOKENS = ("sum", "count", "mean", "median", "min", "max", "std", "cv",
              "p01", "p25", "p75", "p99", "zeros", "top3")


# ---------------------------------------------------------------- 输出与清理

def _clean(v):
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_clean(x) for x in v]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)
    if v is None or v is pd.NaT or v is pd.NA:
        return None
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return str(v)
    if isinstance(v, str):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def _dumps(obj):
    return json.dumps(_clean(obj), ensure_ascii=False, separators=(",", ":"))


def _emit(obj, kind):
    s = _dumps(obj)
    limit = LIMITS.get(kind, 8000)
    if len(s) > limit:
        print(_dumps({"error": "output_too_large", "chars": len(s), "limit": limit,
                      "hint": "收窄参数：--top / --windows / --cols / --by"}))
        sys.exit(3)
    print(s)


def _die(msg, **kw):
    print(_dumps({"error": msg, **kw}))
    sys.exit(2)


# ---------------------------------------------------------------- 读取与探测

def _is_gz(path):
    return path.lower().endswith(".gz")


def _open_bin(path):
    return gzip.open(path, "rb") if _is_gz(path) else open(path, "rb")


def _open_text(path, encoding):
    kw = dict(encoding=encoding, errors="replace", newline="")
    return gzip.open(path, "rt", **kw) if _is_gz(path) else open(path, "r", **kw)


def _sample(path, n=SAMPLE_BYTES):
    with _open_bin(path) as f:
        return f.read(n)


def detect_encoding(path):
    """utf-8 优先；失败交给 charset_normalizer；最后退 gb18030。混编不猜，直接报错。"""
    raw = _sample(path)
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None and best.encoding:
            enc = best.encoding.lower().replace("_", "-")
            raw.decode(enc)
            return "gb18030" if enc in ("gb2312", "gbk") else enc
    except Exception:
        pass
    return "gb18030"


def detect_delimiter(path, encoding):
    raw = _sample(path, 1 << 16)
    text = raw.decode(encoding, errors="replace")
    sample = "\n".join(text.splitlines()[:50])
    try:
        return csv.Sniffer().sniff(sample, delimiters=CANDIDATE_DELIMS).delimiter
    except csv.Error:
        pass
    first = text.splitlines()[0] if text.splitlines() else ""
    counts = {c: first.count(c) for c in CANDIDATE_DELIMS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


def decompressed_size(path):
    if not _is_gz(path):
        return os.path.getsize(path), "file_size"
    comp = os.path.getsize(path)
    if comp > 4 * 1024 ** 3:  # ISIZE 是 mod 2^32，超过就老实扫一遍
        n = 0
        with gzip.open(path, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                n += len(b)
        return n, "stream_scan"
    with open(path, "rb") as f:
        f.seek(-4, os.SEEK_END)
        return int.from_bytes(f.read(4), "little"), "isize"


def head_lines(path, encoding, n=HEAD_LINES):
    out = []
    with _open_text(path, encoding) as f:
        for line in f:
            out.append(line)
            if len(out) >= n:
                break
    return out


def memory_budget_mb(fraction=0.7):
    """可用内存：优先 cgroup 限额，其次 MemAvailable，取小再打 7 折。"""
    limit = None
    for p in ("/sys/fs/cgroup/memory.max",
              "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            v = open(p).read().strip()
            if v and v != "max":
                iv = int(v)
                if iv < (1 << 60):
                    limit = iv / 1e6
                    break
        except (OSError, ValueError):
            pass
    avail = None
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) * 1024 / 1e6
                    break
    except OSError:
        pass
    cands = [x for x in (limit, avail) if x]
    if not cands:
        return 1024.0
    return round(min(cands) * fraction, 1)


def tier_for(est_mem_mb, budget_mb=None):
    budget = budget_mb if budget_mb is not None else memory_budget_mb()
    if est_mem_mb < min(TIER_A_MB, budget * 0.25):
        return "A"
    if est_mem_mb < budget:
        return "B"
    return "C"


def meta(path):
    enc = detect_encoding(path)
    return enc, detect_delimiter(path, enc)


def read_table(path, enc, delim, **kw):
    """注意：不要设 low_memory=False。实测同一份 682MB 文件读单列，
    low_memory=True 峰值 268MB，False 是 2100MB（整块解析）。"""
    if kw.pop("skip_bad", False):
        kw["on_bad_lines"] = "skip"
    return pd.read_csv(path, encoding=enc, sep=delim, compression="infer", **kw)


def guard_full_read(path, sample, what):
    """整表入内存的命令在 C 档必须先拒绝：OOM 是静默的，结构化报错不是。"""
    total, _ = decompressed_size(path)
    est = total * MEM_FACTOR / 1e6
    budget = memory_budget_mb()
    tier = tier_for(est, budget)
    if tier == "C" and not sample:
        _die(f"tier_C: {what} 需要整表入内存，估算 {est:.0f}MB 超出可用 {budget:.0f}MB",
             tier=tier, est_mem_mb=round(est, 1), budget_mb=budget,
             hint="加 --sample 200000 只读前 N 行（结论须注明基于采样），"
                  "或改用 run 配 chunksize 流式聚合；profile 全程流式，可直接跑")
    return tier


def need_col(df, name, role="列"):
    if name not in df.columns:
        _die(f"{role}不存在: {name}", available=list(map(str, df.columns))[:60])
    return name


def to_time(df, col):
    s = pd.to_datetime(df[col], errors="coerce", format="mixed")
    return s


# ---------------------------------------------------------------- peek / scout

def cmd_peek(a):
    enc = detect_encoding(a.path)
    delim = detect_delimiter(a.path, enc)
    total, src = decompressed_size(a.path)
    lines = head_lines(a.path, enc, a.lines + 1 if a.lines else 6)
    width = a.width
    header = lines[0].rstrip("\n") if lines else ""
    out = {
        "path": a.path,
        "encoding": enc,
        "has_bom": enc == "utf-8-sig",
        "delimiter": delim,
        "decompressed_bytes": total,
        "size_source": src,
        "columns": len(next(csv.reader([header], delimiter=delim), [])) if header else 0,
        "lines": [ln.rstrip("\n")[:width] for ln in lines[:a.lines or 6]],
        "note": "只允许从 peek 看原始内容；其余数据一律走 profile/agg/run",
    }
    print(_dumps(out))


def cmd_scout(a):
    enc = detect_encoding(a.path)
    delim = detect_delimiter(a.path, enc)
    total, src = decompressed_size(a.path)
    lines = head_lines(a.path, enc)
    header = next(csv.reader([lines[0].rstrip("\n")], delimiter=delim), []) if lines else []
    lens = [len(ln.encode(enc, errors="replace")) for ln in lines]
    avg = (sum(lens) / len(lens)) if lens else 1.0
    est_rows = max(int(total / max(avg, 1.0)) - 1, 0)
    est_mem = total * MEM_FACTOR / 1e6
    budget = memory_budget_mb()
    tier = tier_for(est_mem, budget)
    _emit({
        "path": a.path,
        "bytes_on_disk": os.path.getsize(a.path),
        "decompressed_bytes": total,
        "size_source": src,
        "encoding": enc,
        "delimiter": delim,
        "est_rows": est_rows,
        "est_rows_note": f"按前 {len(lines)} 行平均行长外推，±25%；判档位只看字节不看行数",
        "est_cols": len(header),
        "header": [str(c) for c in header],
        "avg_line_bytes": round(avg, 1),
        "est_mem_mb": round(est_mem, 1),
        "budget_mb": budget,
        "tier": tier,
        "tier_rule": f"A<{min(TIER_A_MB, budget * 0.25):.0f}MB B<{budget:.0f}MB(可用) 否则 C；"
                     f"est_mem=解压后字节×{MEM_FACTOR}",
        "advice": {"A": "可直接全读",
                   "B": "配 --cols 裁列；文本列基数 <50 才用 category",
                   "C": "走 chunksize 流式；禁全量 sort_values/merge/pivot_table"}[tier],
    }, "scout")


# ---------------------------------------------------------------- profile

def _looks_numeric(vals):
    ok = 0
    for v in vals:
        try:
            float(str(v).strip().replace(",", ""))
            ok += 1
        except ValueError:
            pass
    return ok / len(vals) if vals else 0.0


def cmd_profile(a):
    enc, delim = meta(a.path)
    total, src = decompressed_size(a.path)
    tier = tier_for(total * MEM_FACTOR / 1e6, memory_budget_mb())
    usecols = a.cols.split(",") if a.cols else None
    chunk_iter = read_table(a.path, enc, delim, usecols=usecols,
                            chunksize=a.chunk, skip_bad=a.skip_bad)
    str_sample = read_table(a.path, enc, delim, nrows=5000, dtype=str,
                            skip_bad=a.skip_bad)
    first = None
    acc = {}
    rows = 0
    t0 = time.time()
    outlier_buf = {}

    for chunk in chunk_iter:
        if first is None:
            first = chunk.head(5000)
        rows += len(chunk)
        for col in chunk.columns:
            s = chunk[col]
            st = acc.get(col)
            if st is None:
                st = acc[col] = {"non_null": 0, "distinct": set(), "distinct_trunc": False,
                                 "sum": 0.0, "sumsq": 0.0, "n_num": 0, "min": None, "max": None}
            vals = s.dropna()
            st["non_null"] += len(vals)
            if not st["distinct_trunc"]:
                try:
                    st["distinct"].update(vals.unique().tolist())
                except TypeError:
                    st["distinct_trunc"] = True
                if len(st["distinct"]) > MAX_DISTINCT:
                    st["distinct_trunc"] = True
                    st["distinct"] = set()
            if pd.api.types.is_numeric_dtype(s):
                arr = pd.to_numeric(vals, errors="coerce").dropna().to_numpy(dtype="float64")
                st["n_num"] += len(arr)
                st["sum"] += float(arr.sum())
                st["sumsq"] += float((arr ** 2).sum())
                if len(arr):
                    lo, hi = float(arr.min()), float(arr.max())
                    st["min"] = lo if st["min"] is None else min(st["min"], lo)
                    st["max"] = hi if st["max"] is None else max(st["max"], hi)
            if a.outliers and pd.api.types.is_numeric_dtype(s):
                buf = outlier_buf.setdefault(col, [])
                if len(buf) < 100000:
                    buf.extend(pd.to_numeric(vals, errors="coerce").dropna().tolist())

    if first is None:
        _die("空文件或无法解析", path=a.path)

    cols_out = []
    for col in first.columns:
        st = acc[col]
        s0 = first[col].dropna()
        cast = s0.astype(str)
        flags = []
        null_rate = float(first[col].isna().mean()) if len(first) else 0.0
        if null_rate > 0:
            flags.append("has_null")
        distinct = None if st["distinct_trunc"] else len(st["distinct"])
        if st["non_null"] and not st["distinct_trunc"] and len(st["distinct"]) > 0.95 * st["non_null"] and st["non_null"] >= 100:
            flags.append("id_like")
        if not pd.api.types.is_numeric_dtype(first[col]) and len(s0) >= 5:
            num_ratio = _looks_numeric(s0.head(500).tolist())
            if 0.02 < num_ratio < 0.98:
                flags.append("mixed_type")
            elif num_ratio >= 0.98:
                # 整列看着是数字却不是数值 dtype：千分位/货币符号/文本存储
                flags.append("numeric_as_text")
            else:
                flags.append("non_numeric")
        raw = str_sample[col].dropna().astype(str) if col in str_sample.columns else cast
        if len(raw):
            if raw.str.match(r"^0\d+$").mean() >= 0.5:
                flags.append("leading_zero_lost")
            if raw.str.match(r"^0?\d{12,}$").mean() > 0.9:
                flags.append("digit_string")
        entry = {
            "col": str(col),
            "dtype": str(first[col].dtype),
            "non_null": st["non_null"],
            "null_rate": round(null_rate, 4),
            "distinct": distinct,
            "distinct_trunc": st["distinct_trunc"] or None,
        }
        if st["n_num"]:
            mean = st["sum"] / st["n_num"]
            var = max(st["sumsq"] / st["n_num"] - mean ** 2, 0.0)
            entry.update({"mean": mean, "min": st["min"], "max": st["max"],
                          "std": math.sqrt(var) if st["n_num"] > 1 else None})
            arr0 = pd.to_numeric(s0, errors="coerce").dropna().to_numpy(dtype="float64")
            if len(arr0):
                entry["int_ratio"] = round(float((arr0 == np.floor(arr0)).mean()), 3)
        # 时间范围：只在首块上判定，如实标注
        if not pd.api.types.is_numeric_dtype(first[col]) and len(s0):
            parsed = pd.to_datetime(pd.Series(s0.to_numpy()), errors="coerce", format="mixed")
            if parsed.notna().mean() >= 0.95:
                entry["time_range"] = [str(parsed.min()), str(parsed.max())]
                entry["time_range_based_on"] = "first_chunk"
        if flags:
            entry["flags"] = flags
        cols_out.append(entry)

    dup = None
    if a.dups:
        guard_full_read(a.path, a.sample, "profile --dups")
        seen = pd.read_csv(a.path, encoding=enc, sep=delim, compression="infer")
        dup = int(seen.duplicated().sum())

    out = {
        "path": a.path,
        "tier": tier,
        "rows": rows,
        "cols": len(cols_out),
        "decompressed_bytes": total,
        "size_source": src,
        "encoding": enc,
        "delimiter": delim,
        "elapsed_s": round(time.time() - t0, 2),
        "flags_based_on": f"first {len(first)} rows",
        "skipped_bad_lines": bool(a.skip_bad),
    }
    if dup is not None:
        out["duplicate_rows"] = dup
    if a.outliers:
        out["outliers"] = _outliers(outlier_buf)
    # 超长时从尾部削列，如实报数
    while len(_dumps({**out, "columns": cols_out})) > LIMITS["profile"] and len(cols_out) > 1:
        cols_out.pop()
    out["columns"] = cols_out
    out["shown_cols"] = len(cols_out)
    _emit(out, "profile")


def _outliers(buf):
    res = {}
    for col, vals in buf.items():
        a = np.asarray(vals, dtype="float64")
        a = a[~np.isnan(a)]
        if len(a) < 20:
            continue
        q1, q3 = np.percentile(a, [25, 75])
        iqr = q3 - q1
        if iqr == 0:
            continue
        lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
        flags = a[(a < lo) | (a > hi)]
        if len(flags):
            res[col] = {"method": "iqr_3x", "lo": float(lo), "hi": float(hi),
                        "count": int(len(flags)),
                        "top": [float(x) for x in np.sort(flags)[-10:][::-1]],
                        "based_on": "first_100k_values"}
    return res


# ---------------------------------------------------------------- agg

def _dist(a):
    a = np.asarray(a, dtype="float64")
    a = a[~np.isnan(a)]
    n = len(a)
    if n == 0:
        return {"count": 0}
    mean = float(a.mean())
    std = float(a.std(ddof=1)) if n > 1 else None
    p = np.percentile(a, [1, 25, 50, 75, 99])
    srt = np.sort(a)
    out = {
        "count": n, "sum": float(a.sum()), "mean": mean, "median": float(p[2]),
        "min": float(a.min()), "max": float(a.max()),
        "p01": float(p[0]), "p25": float(p[1]), "p75": float(p[3]), "p99": float(p[4]),
        "std": std,
        "cv": (std / mean) if (std is not None and mean) else None,
        "zeros": int((a == 0).sum()),
        "top3": [float(x) for x in srt[-3:][::-1]],
    }
    return out


def _ratio(num, den):
    """除零返回 None，绝不产生 inf/nan 进结论。"""
    n = pd.to_numeric(num, errors="coerce").sum()
    d = pd.to_numeric(den, errors="coerce").sum()
    if not d:
        return {"ratio": None, "diff": float(n - d) if pd.notna(n) else None,
                "den_zero": True}
    return {"ratio": float(n) / float(d), "diff": float(n) - float(d), "den_zero": False}


def _pick(block, tokens):
    if not tokens:
        return block
    want = set(tokens)
    return {k: v for k, v in block.items() if k in want}


def _fmt_bucket(t, freq):
    if freq == "M":
        return t.dt.strftime("%Y-%m")
    if freq == "W":
        return t.dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d")
    return t.dt.strftime("%Y-%m-%d")


def _bucket_end(label, freq):
    try:
        if freq == "M":
            return pd.Period(label, "M").end_time
        if freq == "W":
            return pd.Period(label, "W").end_time
        return pd.Period(label, "D").end_time
    except Exception:
        return None


def _parse_window(spec, anchor):
    """'30d' | 'YYYY-MM-DD:YYYY-MM-DD' → (start, end)"""
    if ":" in spec:
        lo, hi = spec.split(":", 1)
        return pd.Timestamp(lo), pd.Timestamp(hi) + pd.Timedelta(days=1)
    days = int(spec.rstrip("d"))
    return anchor - pd.Timedelta(days=days), anchor + pd.Timedelta(days=1)


def cmd_agg(a):
    enc, delim = meta(a.path)
    tier = guard_full_read(a.path, a.sample, "agg")
    usecols = [c for c in [a.col, a.by, a.time, a.key, a.ratio] if c]
    df = read_table(a.path, enc, delim, usecols=usecols if usecols else None,
                    skip_bad=a.skip_bad, nrows=a.sample)
    tokens = a.agg.split(",") if a.agg else None
    out = {"path": a.path, "rows": len(df), "col": a.col, "tier": tier}
    if a.sample:
        out["sampled_rows"] = a.sample

    if a.interval:
        need_col(df, a.time, "时间列")
        d = df.copy()
        d["_t"] = to_time(d, a.time)
        d = d.dropna(subset=["_t"]).sort_values("_t")
        if a.key:
            need_col(df, a.key, "分组键")
            d["_dt"] = d.groupby(a.key, observed=True)["_t"].diff().dt.total_seconds() / 60
        else:
            d["_dt"] = d["_t"].diff().dt.total_seconds() / 60
        gaps = d["_dt"].dropna().to_numpy(dtype="float64")
        out["interval"] = {"unit": "minutes", "n": len(gaps), **_dist(gaps),
                           "groups": a.key or None}
        if a.gaps:
            out["short_intervals"] = {"threshold_minutes": a.gaps,
                                      "count": int((gaps < a.gaps).sum())}
        _emit(out, "agg")
        return

    need_col(df, a.col, "指标列")

    if a.freq:
        need_col(df, a.time, "时间列")
        d = df.copy()
        d["_t"] = to_time(d, a.time)
        d = d.dropna(subset=["_t"])
        d["_b"] = _fmt_bucket(d["_t"], a.freq)
        rows = []
        for label, sub in d.groupby("_b", observed=True):
            blk = _dist(pd.to_numeric(sub[a.col], errors="coerce").dropna().to_numpy())
            blk["key"] = str(label)
            if a.ratio:
                need_col(sub, a.ratio, "分母列")
                blk.update(_ratio(sub[a.col], sub[a.ratio]))
            end = _bucket_end(label, a.freq)
            blk["complete"] = bool(end is not None and end <= pd.Timestamp(a.as_of or pd.Timestamp.now()))
            rows.append(blk)
        rows.sort(key=lambda r: r["key"])
        truncated = len(rows) > MAX_BUCKETS
        if truncated:
            rows = rows[-MAX_BUCKETS:]
        out["freq"] = a.freq
        out["buckets"] = rows
        out["bucket_truncated"] = truncated or None
        if a.baseline and len(rows) > 1:
            complete = [r for r in rows if r["complete"]]
            base = complete[:-1] if len(complete) > 1 else complete
            last = (complete or rows)[-1]
            bm = np.array([r.get("sum", 0.0) for r in base], dtype="float64")
            if len(bm):
                mean_b = float(bm.mean())
                std_b = float(bm.std(ddof=1)) if len(bm) > 1 else 0.0
                out["baseline"] = {
                    "basis_buckets": len(bm), "mean": mean_b, "median": float(np.median(bm)),
                    "max": float(bm.max()), "min": float(bm.min()),
                    "std": std_b,
                    "cv": (std_b / mean_b) if mean_b else None,
                    "latest_key": last["key"], "latest_sum": last.get("sum"),
                    "ratio_to_baseline": (last.get("sum") / mean_b) if (mean_b and last.get("sum") is not None) else None,
                    "zscore": ((last.get("sum", 0.0) - mean_b) / std_b) if std_b else None,
                }
        _emit(out, "agg")
        return

    if a.windows:
        need_col(df, a.time, "时间列")
        d = df.copy()
        d["_t"] = to_time(d, a.time)
        d = d.dropna(subset=["_t"])
        anchor = pd.Timestamp(a.as_of) if a.as_of else d["_t"].max()
        res = {}
        for w in [x.strip() for x in a.windows.split(",") if x.strip()]:
            lo, hi = _parse_window(w, anchor)
            sub = d[(d["_t"] >= lo) & (d["_t"] < hi)]
            blk = _dist(pd.to_numeric(sub[a.col], errors="coerce").dropna().to_numpy())
            if a.ratio:
                need_col(sub, a.ratio, "分母列")
                blk.update(_ratio(sub[a.col], sub[a.ratio]))
            blk["active_keys"] = int(sub["_t"].dt.date.nunique())
            blk["rows"] = int(len(sub))
            res[w] = blk
        out["anchor"] = str(anchor)
        out["windows"] = res
        _emit(out, "agg")
        return

    if a.by:
        need_col(df, a.by, "分组列")
        if a.compare:
            need_col(df, a.time, "时间列")
            d = df.copy()
            d["_t"] = to_time(d, a.time)
            d = d.dropna(subset=["_t"])
            anchor = pd.Timestamp(a.as_of) if a.as_of else d["_t"].max()
            specs = [x.strip() for x in a.compare.split(",")]
            if len(specs) != 2:
                _die("--compare 需要两个窗口，如 30d,90d 或 2026-10-01:2026-10-31,2026-09-01:2026-09-30")
            shares = []
            for spec in specs:
                lo, hi = _parse_window(spec, anchor)
                sub = d[(d["_t"] >= lo) & (d["_t"] < hi)]
                g = pd.to_numeric(sub[a.col], errors="coerce").groupby(sub[a.by], observed=True).sum()
                tot = float(g.sum()) or 1.0
                shares.append((spec, (g / tot).to_dict(), g.to_dict()))
            out["compare"] = {"windows": [shares[0][0], shares[1][0]], "groups": []}
            keys = set(shares[0][1]) | set(shares[1][1])
            for k in keys:
                pa = shares[0][1].get(k)
                pb = shares[1][1].get(k)
                if pa is None:
                    status = "new"
                elif pb is None:
                    status = "gone"
                elif abs(pb - pa) < 1e-9:
                    status = "same"
                else:
                    status = "up" if pb > pa else "down"
                out["compare"]["groups"].append({
                    "key": str(k),
                    "share_a": pa, "share_b": pb,
                    "delta_pp": None if (pa is None or pb is None) else round((pb - pa) * 100, 2),
                    "sum_a": shares[0][2].get(k), "sum_b": shares[1][2].get(k),
                    "status": status,
                })
            out["compare"]["groups"].sort(
                key=lambda r: (r["share_b"] is None, -(r["share_b"] or 0)))
            _emit(out, "agg")
            return

        g = df.groupby(a.by, observed=True, dropna=False)
        total_sum = float(pd.to_numeric(df[a.col], errors="coerce").sum()) or 1.0
        rows = []
        for key, sub in g:
            blk = _dist(pd.to_numeric(sub[a.col], errors="coerce").dropna().to_numpy())
            blk["key"] = str(key)
            blk["share"] = (blk.get("sum", 0.0) / total_sum) if blk.get("sum") is not None else None
            if a.ratio:
                need_col(sub, a.ratio, "分母列")
                blk.update(_ratio(sub[a.col], sub[a.ratio]))
            if a.distinct_by:
                need_col(sub, a.distinct_by, "去重列")
                blk["distinct_" + a.distinct_by] = int(sub[a.distinct_by].nunique())
            rows.append(blk)
        rows.sort(key=lambda r: (-(r.get("sum") or 0)))
        tot_share = [r["share"] for r in rows if r.get("share") is not None]
        out["by"] = a.by
        out["group_count"] = len(rows)
        out["hhi"] = round(float(sum(s * s for s in tot_share)), 6) if tot_share else None
        out["cr3"] = round(float(sum(tot_share[:3])), 4) if tot_share else None
        if a.top and len(rows) > a.top:
            out["groups"] = rows[:a.top]
            out["group_truncated"] = len(rows) - a.top
        else:
            out["groups"] = rows
        _emit(out, "agg")
        return

    vals = pd.to_numeric(df[a.col], errors="coerce").dropna().to_numpy()
    out["dist"] = _pick(_dist(vals), tokens)
    if a.ratio:
        need_col(df, a.ratio, "分母列")
        out.update(_ratio(df[a.col], df[a.ratio]))
    out["null_rate"] = round(float(1 - len(vals) / len(df)), 4) if len(df) else None
    out["distinct"] = int(df[a.col].nunique())
    _emit(out, "agg")


# ---------------------------------------------------------------- shape

def cmd_shape(a):
    enc, delim = meta(a.path)
    tier = guard_full_read(a.path, a.sample, "shape")
    usecols = [c for c in [a.col, a.time] if c]
    df = read_table(a.path, enc, delim, usecols=usecols if usecols else None,
                    skip_bad=a.skip_bad, nrows=a.sample)
    out = {"path": a.path, "rows": len(df), "tier": tier,
           "skipped_bad_lines": bool(a.skip_bad)}
    if a.sample:
        out["sampled_rows"] = a.sample
    num = pd.to_numeric(df[a.col], errors="coerce").dropna().to_numpy(dtype="float64") if a.col else None
    if num is not None:
        out["col"] = a.col
        if a.ints:
            frac = float((num == np.floor(num)).mean()) if len(num) else 0.0
            out["ints"] = {"ratio": round(frac, 4), "count": int((num == np.floor(num)).sum())}
        if a.near:
            srt = np.sort(num)
            rel = np.abs(np.diff(srt)) / np.maximum(np.abs(srt[:-1]), 1e-12)
            hit = rel < (a.near / 100.0)
            out["near"] = {"threshold_pct": a.near, "adjacent_pairs": int(len(rel)),
                           "count": int(hit.sum())}
            if hit.any():
                idx = np.where(hit)[0][:10]
                out["near"]["samples"] = [[float(srt[i]), float(srt[i + 1])] for i in idx]
    if a.time:
        need_col(df, a.time, "时间列")
        t = to_time(df, a.time)
        if a.same_ts:
            vc = t.value_counts()
            hit = vc[vc >= a.same_ts]
            out["same_ts"] = {"threshold": a.same_ts, "timestamps": int(len(hit)),
                              "rows": int(hit.sum()),
                              "samples": [str(x) for x in hit.index[:5]]}
        if a.gaps:
            d = t.sort_values().diff().dt.total_seconds() / 60
            d = d.dropna().to_numpy()
            out["gaps"] = {"threshold_minutes": a.gaps, "count": int((d < a.gaps).sum()),
                           "median_minutes": float(np.median(d)) if len(d) else None}
    if a.dups:
        out["duplicate_rows"] = int(df.duplicated().sum())
    _emit(out, "shape")


# ---------------------------------------------------------------- match

def cmd_match(a):
    encA, delimA = meta(a.a)
    encB, delimB = meta(a.b)
    guard_full_read(a.a, a.sample, "match")
    guard_full_read(a.b, a.sample, "match")
    A = read_table(a.a, encA, delimA, usecols=[a.key, a.time_a, a.val_a], nrows=a.sample)
    B = read_table(a.b, encB, delimB, usecols=[a.key, a.time_b, a.val_b], nrows=a.sample)
    for df, cols in ((A, [a.key, a.time_a, a.val_a]), (B, [a.key, a.time_b, a.val_b])):
        for c in cols:
            need_col(df, c)
    A = A[[a.key, a.time_a, a.val_a]].rename(columns={a.time_a: "_ta", a.val_a: "_va"})
    B = B[[a.key, a.time_b, a.val_b]].rename(columns={a.time_b: "_tb", a.val_b: "_vb"})
    m = A.merge(B, on=a.key, how="inner")
    if not len(m):
        _emit({"error": "no_match", "key": a.key}, "match")
        return
    ta = pd.to_datetime(m["_ta"], errors="coerce", format="mixed")
    tb = pd.to_datetime(m["_tb"], errors="coerce", format="mixed")
    dt = (tb - ta).dt.total_seconds() / 60.0
    if a.within:
        keep = dt.abs() <= a.within * 60.0
        m, dt = m[keep], dt[keep]
    va = pd.to_numeric(m["_va"], errors="coerce")
    vb = pd.to_numeric(m["_vb"], errors="coerce")
    diff = (va - vb).abs()
    rel = diff / np.maximum(va.abs(), 1e-12)
    out = {
        "pairs": int(len(m)),
        "keys": int(m[a.key].nunique()),
        "time_diff": {"unit": "minutes", **_dist(dt.dropna().to_numpy(dtype="float64"))},
        "val_abs_diff": _dist(diff.dropna().to_numpy(dtype="float64")),
        "val_rel_diff": _dist(rel.replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype="float64")),
        "within_tol": {"tol": a.tol, "count": int((diff <= a.tol).sum()),
                       "ratio": round(float((diff <= a.tol).mean()), 4)},
        "note": "金额比较先按 tol 容差，禁止裸 == ；浮点噪声会误判不匹配",
    }
    if a.within:
        out["within_hours"] = a.within
    _emit(out, "match")


# ---------------------------------------------------------------- run

def _show(obj, rows=None, width=None):
    rows = rows or SHOW_ROWS
    width = width or SHOW_CHARS
    tot = None
    if isinstance(obj, pd.DataFrame):
        tot = len(obj)
        sub = obj.head(rows)
        cols = [str(c)[:width] for c in sub.columns]
        print(" | ".join(cols))
        print(" | ".join("-" * min(len(c), 12) for c in cols))
        for row in sub.itertuples(index=False):
            print(" | ".join(str(v)[:width] for v in row))
        if tot > rows:
            print(f"… 省略 {tot - rows} 行（共 {tot} 行）")
    elif isinstance(obj, pd.Series):
        tot = len(obj)
        for k, v in obj.head(rows).items():
            print(f"{k} | {str(v)[:width]}")
        if tot > rows:
            print(f"… 省略 {tot - rows} 行（共 {tot} 行）")
    else:
        print(str(obj)[: rows * width])


def cmd_run(a):
    enc, delim = meta(a.path) if a.path else (None, None)
    src = sys.stdin.read() if a.script in (None, "-") else open(a.script, encoding="utf-8").read()
    if not src.strip():
        _die("没有脚本内容：用 --script file.py 或把代码从 stdin 传入")
    ns = {"pd": pd, "np": np, "show": _show, "__name__": "__main__"}

    def load(path=None, **kw):
        p = path or a.path
        if not p:
            _die("load() 需要路径")
        e, d = (enc, delim) if p == a.path and enc else meta(p)
        return read_table(p, e, d, **kw)

    ns["load"] = load
    if a.path:
        ns["df"] = load()
    t0 = time.time()
    exec(compile(src, "<run>", "exec"), ns)
    print(f"[elapsed {time.time() - t0:.2f}s]")


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(prog="tabular.py", description="CSV/TSV/CSV.GZ 分析原语")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("peek", help="原文视图")
    q.add_argument("path")
    q.add_argument("--lines", type=int, default=6)
    q.add_argument("--width", type=int, default=300)
    q.set_defaults(func=cmd_peek)

    q = sub.add_parser("scout", help="元数据 + 内存档位")
    q.add_argument("path")
    q.set_defaults(func=cmd_scout)

    q = sub.add_parser("profile", help="质量体检")
    q.add_argument("path")
    q.add_argument("--cols", help="只看这些列（逗号分隔）")
    q.add_argument("--chunk", type=int, default=200000)
    q.add_argument("--dups", action="store_true", help="统计完全重复行（会全量读一次）")
    q.add_argument("--skip-bad", dest="skip_bad", action="store_true",
                   help="跳过坏行（默认报错并给出行号）；跳过时结论必须注明")
    q.add_argument("--outliers", action="store_true", help="IQR 3x 离群值（基于前 10 万值）")
    q.add_argument("--sample", type=int, help="只给 --dups 用：只读前 N 行")
    q.set_defaults(func=cmd_profile)

    q = sub.add_parser("agg", help="万用聚合")
    q.add_argument("path")
    q.add_argument("--col", help="指标列")
    q.add_argument("--by", help="分组列")
    q.add_argument("--time", help="时间列")
    q.add_argument("--freq", choices=["D", "W", "M"], help="时间桶粒度")
    q.add_argument("--windows", help="如 7,30,90（天），需要 --time")
    q.add_argument("--baseline", type=int, help="以最近 N 期之外为基线")
    q.add_argument("--compare", help="两个窗口对比结构，如 30d,90d")
    q.add_argument("--interval", action="store_true", help="相邻事件时间间隔分布")
    q.add_argument("--key", help="--interval 的分组键")
    q.add_argument("--gaps", type=float, help="短间隔阈值（分钟）")
    q.add_argument("--agg", help="限定输出指标，如 sum,mean,median,max")
    q.add_argument("--skip-bad", dest="skip_bad", action="store_true", help="跳过坏行")
    q.add_argument("--sample", type=int, help="只读前 N 行（C 档必填，结论须注明采样）")
    q.add_argument("--top", type=int, default=10)
    q.add_argument("--distinct-by", dest="distinct_by", help="按组统计该列去重数")
    q.add_argument("--ratio", help="同表两列的比值/差值：本列作分子，该列作分母（除零给 null）")
    q.add_argument("--as-of", dest="as_of", help="锚点日期，默认取数据内最大时间")
    q.set_defaults(func=cmd_agg)

    q = sub.add_parser("shape", help="形态识别")
    q.add_argument("path")
    q.add_argument("--col")
    q.add_argument("--time")
    q.add_argument("--ints", action="store_true")
    q.add_argument("--near", type=float, help="相近值相对差阈值（百分比）")
    q.add_argument("--same-ts", dest="same_ts", type=int, help="同一时间戳至少几笔")
    q.add_argument("--gaps", type=float, help="间隔小于多少分钟算过密")
    q.add_argument("--dups", action="store_true")
    q.add_argument("--skip-bad", dest="skip_bad", action="store_true", help="跳过坏行")
    q.add_argument("--sample", type=int, help="只读前 N 行")
    q.set_defaults(func=cmd_shape)

    q = sub.add_parser("match", help="两表对齐")
    q.add_argument("a")
    q.add_argument("b")
    q.add_argument("--key", required=True)
    q.add_argument("--time-a", dest="time_a", required=True)
    q.add_argument("--time-b", dest="time_b", required=True)
    q.add_argument("--val-a", dest="val_a", required=True)
    q.add_argument("--val-b", dest="val_b", required=True)
    q.add_argument("--within", type=float, help="只看时间差在 N 小时内")
    q.add_argument("--tol", type=float, default=0.01)
    q.add_argument("--sample", type=int, help="两侧各只读前 N 行")
    q.set_defaults(func=cmd_match)

    q = sub.add_parser("run", help="自由执行器")
    q.add_argument("path", nargs="?")
    q.add_argument("--script", help="脚本路径，或用 - 从 stdin 读")
    q.set_defaults(func=cmd_run)
    return p


def main():
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 40)
    a = build_parser().parse_args()
    if getattr(a, "path", None) and a.func is not cmd_run:
        if not os.path.exists(a.path):
            _die("文件不存在", path=a.path)
    try:
        a.func(a)
    except pd.errors.ParserError as e:
        _die("bad_rows: 列数不齐或引号未闭合（pandas 已给出行号）",
             detail=str(e)[:400],
             hint="先用 peek 看原文；修源数据，或加 --skip-bad 跳过（跳过会少行，结论须注明）")
    except UnicodeDecodeError as e:
        _die("decode_failed: 同一文件里混了编码，本工具不猜", detail=str(e)[:300],
             hint="先统一源文件编码为 utf-8；GBK 请整体转码，不要逐行混转")
    except ValueError as e:
        _die("invalid_argument_or_data", detail=str(e)[:400])


if __name__ == "__main__":
    main()
