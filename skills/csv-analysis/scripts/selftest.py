#!/usr/bin/env python3
"""selftest.py — tabular.py 的回归自检。

只依赖标准库 + 被测脚本。造 6 个坏样本，断言探测/体检/聚合的关键判定。
跑：python3 selftest.py          全部用例
    python3 selftest.py -v       失败时打印完整输出
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TAB = os.path.join(HERE, "tabular.py")
PY = sys.executable
VERBOSE = "-v" in sys.argv

PASS = 0
FAIL = []


def check(cond, msg, detail=None):
    global PASS
    if cond:
        PASS += 1
        print(f"  ok   {msg}")
    else:
        FAIL.append(f"{msg}\n       {detail}")
        print(f"  FAIL {msg}")


def run(*args, stdin=None):
    return subprocess.run([PY, TAB, *args], capture_output=True, text=True,
                          input=stdin, timeout=600)


def jrun(*args, expect_ok=True):
    p = run(*args)
    if expect_ok and p.returncode != 0:
        raise SystemExit(f"命令失败 {args}\nrc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        raise SystemExit(f"输出不是 JSON {args}\nrc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")


# ------------------------------------------------------------------ 造样本

def build(d):
    """6 个故意有坑的样本。"""
    # 1. GBK 编码的中文表
    with open(os.path.join(d, "gbk.csv"), "w", encoding="gbk", newline="") as f:
        f.write("渠道,金额\n应用商店,1200\n华为,800\n")
    # 2. UTF-8 BOM
    with open(os.path.join(d, "bom.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write("col_a,col_b\n1,2\n3,4\n")
    # 3. 前导零单号（被 pandas 推断成 int64 就会丢零）
    with open(os.path.join(d, "ids.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("order_no,amount\n")
        for i in range(10):
            f.write(f"00000000000{i},{100 + i}\n")
    # 4. 金额列混着文本
    with open(os.path.join(d, "mixed.csv"), "w", encoding="utf-8", newline="") as f:
        f.write('amount\n"1,200"\n800\nabc\n"1,500"\n900\n')
    # 4b. 整列是"数字文本"（千分位），dtype 不是数值
    with open(os.path.join(d, "money.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("amount\n\"1,200\"\n\"800\"\n\"1,500\"\n\"900\"\n\"2,000\"\n")
    # 5. gzip
    base = os.path.join(d, "t.csv")
    with open(base, "w", encoding="utf-8", newline="") as f:
        f.write("id,val\n")
        for i in range(1000):
            f.write(f"{i},{i * 1.5}\n")
    with open(base, "rb") as fi, gzip.open(os.path.join(d, "t.csv.gz"), "wb") as fo:
        shutil.copyfileobj(fi, fo)
    # 6. 坏行：多出一列
    with open(os.path.join(d, "bad.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("a,b,c\n1,2,3\n4,5,6,7\n8,9,10\n")
    # 7. 月度序列（算基线/窗口/结构对比用）
    with open(os.path.join(d, "series.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("month,amount,channel\n")
        rows = [
            ("2026-01-05", 100, "a"), ("2026-01-20", 100, "a"),
            ("2026-02-10", 200, "b"), ("2026-03-15", 300, "a"),
            ("2026-04-10", 400, "c"), ("2026-11-03", 50, "a"),
        ]
        for m, v, c in rows:
            f.write(f"{m},{v},{c}\n")
    # 7b. 同表两列比值：含分母为 0 的月份
    with open(os.path.join(d, "flow.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("month,in_amt,out_amt\n2026-09,1000,1000\n2026-10,500,0\n2026-11,2000,1500\n")
    # 8. 两表对齐：金额差 1e-12（浮点噪声），时间差 30 分钟
    with open(os.path.join(d, "left.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("id,created_at,amount\nk1,2026-10-05 10:00:00,5537.499648730936\n")
    with open(os.path.join(d, "right.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("id,created_at,amount\nk1,2026-10-05 10:30:00,5537.499648730935\n")
    return d


# ------------------------------------------------------------------ 用例

def case_encoding(d):
    print("[1] 编码：GBK / UTF-8-BOM")
    g = jrun("peek", os.path.join(d, "gbk.csv"))
    check(g["encoding"] in ("gb18030", "gbk", "gb2312"), "GBK 被识别", g["encoding"])
    check(any("应用商店" in ln for ln in g["lines"]), "GBK 内容正确解码", g["lines"])
    p = jrun("profile", os.path.join(d, "gbk.csv"))
    check(p["rows"] == 2 and p["cols"] == 2, "GBK 表 2 行 2 列", p)
    check(p["columns"][0]["col"] == "渠道", "中文列名无乱码", p["columns"][0]["col"])

    b = jrun("peek", os.path.join(d, "bom.csv"))
    check(b["has_bom"] is True and b["encoding"] == "utf-8-sig", "BOM 被识别", b["encoding"])
    check(b["lines"][0].startswith("col_a"), "BOM 不污染列名", b["lines"][0])
    bp = jrun("profile", os.path.join(d, "bom.csv"))
    check(bp["columns"][0]["col"] == "col_a", "profile 列名无 BOM", bp["columns"][0]["col"])


def case_flags(d):
    print("[2] flags：前导零 / 混合类型")
    p = jrun("profile", os.path.join(d, "ids.csv"))
    flags = p["columns"][0].get("flags", [])
    check("leading_zero_lost" in flags, "前导零被判出", flags)
    check("digit_string" in flags, "纯数字串被判出", flags)
    check(p["columns"][0]["dtype"] != "object", "默认推断成数值（正是零丢失的原因）",
          p["columns"][0]["dtype"])
    m = jrun("profile", os.path.join(d, "mixed.csv"))
    mflags = m["columns"][0].get("flags", [])
    check("mixed_type" in mflags, "混合类型被判出（数字+文本同列）", mflags)
    mo = jrun("profile", os.path.join(d, "money.csv"))
    moflags = mo["columns"][0].get("flags", [])
    check("numeric_as_text" in moflags, "整列数字文本被判出（千分位）", moflags)


def case_gz(d):
    print("[3] gzip：ISIZE 与档位")
    base = os.path.getsize(os.path.join(d, "t.csv"))
    s = jrun("scout", os.path.join(d, "t.csv.gz"))
    check(s["size_source"] == "isize", "用 ISIZE 估解压后大小", s["size_source"])
    check(s["decompressed_bytes"] == base, f"解压后大小 = {base}", s["decompressed_bytes"])
    check(s["tier"] == "A", "小文件判 A 档", s["tier"])
    check(abs(s["est_rows"] - 1000) <= 250, "估算行数 ≈1000（外推估，容差 25%）", s["est_rows"])
    check("±25%" in s["est_rows_note"], "估算精度如实标注", s["est_rows_note"])
    p = jrun("profile", os.path.join(d, "t.csv.gz"))
    check(p["rows"] == 1000, "profile 读 gzip 行数正确", p["rows"])
    k = jrun("peek", os.path.join(d, "t.csv.gz"))
    check(k["decompressed_bytes"] == base and len(k["lines"]) == 6, "peek 只给 6 行", len(k["lines"]))


def case_bad_rows(d):
    print("[4] 坏行：默认报错带行号，--skip-bad 才跳")
    p = run("profile", os.path.join(d, "bad.csv"))
    check(p.returncode != 0, "坏行默认失败", p.returncode)
    try:
        e = json.loads(p.stdout)
        check(e.get("error", "").startswith("bad_rows"), "给出结构化错误", e)
        check("line 3" in e.get("detail", "") or "line 3" in p.stderr, "错误里带行号", e.get("detail"))
    except json.JSONDecodeError:
        check(False, "坏行错误输出应为 JSON", p.stdout[:200])
    p2 = jrun("profile", os.path.join(d, "bad.csv"), "--skip-bad")
    check(p2["rows"] == 2 and p2["skipped_bad_lines"] is True, "skip-bad 后剩 2 行且标注",
          (p2["rows"], p2["skipped_bad_lines"]))


def case_agg(d):
    print("[5] agg：分布 / 分组 / 时间桶 / 基线 / 窗口 / 结构对比 / 间隔")
    ser = os.path.join(d, "series.csv")

    dist = jrun("agg", ser, "--col", "amount")
    check(dist["dist"]["count"] == 6 and dist["dist"]["sum"] == 1150, "全表 sum=1150", dist["dist"]["sum"])
    check(dist["dist"]["median"] == 150.0, "全表 median=(100+200)/2=150", dist["dist"]["median"])
    check(dist["dist"]["max"] == 400.0 and dist["dist"]["top3"][0] == 400.0, "峰值/top3", dist["dist"]["top3"])

    g = jrun("agg", ser, "--col", "amount", "--by", "channel", "--top", "2")
    got = {r["key"]: r["sum"] for r in g["groups"]}
    check(got == {"a": 550, "c": 400}, "top2 取 sum 最大的 a=550 c=400", got)
    check(g["group_truncated"] == 1, "top=2 时截断 1 组", g.get("group_truncated"))
    check(abs(g["hhi"] - 0.3800) < 1e-3, "HHI≈0.38", g["hhi"])

    f = jrun("agg", ser, "--col", "amount", "--time", "month", "--freq", "M", "--baseline", "12")
    keys = [b["key"] for b in f["buckets"]]
    check(keys == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-11"], "月份桶有序", keys)
    comp = {b["key"]: b["complete"] for b in f["buckets"]}
    check(comp["2026-01"] is True and comp["2026-11"] is False, "当月标 incomplete", comp)
    check(abs(f["baseline"]["mean"] - 233.3333) < 0.01, "基线均值 233.33", f["baseline"]["mean"])
    check(abs(f["baseline"]["ratio_to_baseline"] - 400 / 233.33333) < 0.01,
          "最新完整期/基线≈1.714", f["baseline"]["ratio_to_baseline"])

    w = jrun("agg", ser, "--col", "amount", "--time", "month", "--windows", "7,30")
    check(w["windows"]["7"]["sum"] == 50 and w["windows"]["7"]["rows"] == 1, "7 天窗口只有 11-03 那笔",
          w["windows"]["7"])
    check(w["anchor"].startswith("2026-11-03"), "锚点取数据内最大时间", w["anchor"])

    c = jrun("agg", ser, "--col", "amount", "--by", "channel", "--time", "month",
             "--compare", "2026-01-01:2026-02-28,2026-03-01:2026-03-31")
    st = {x["key"]: x["status"] for x in c["compare"]["groups"]}
    check(st.get("b") == "gone", "1-2 月有、3 月没的组标 gone", st)

    r = jrun("agg", os.path.join(d, "flow.csv"), "--col", "in_amt", "--time", "month",
             "--freq", "M", "--ratio", "out_amt")
    rr = {b["key"]: b for b in r["buckets"]}
    check(rr["2026-09"]["ratio"] == 1.0, "入/出比 1000/1000=1.0", rr["2026-09"]["ratio"])
    check(rr["2026-10"]["ratio"] is None and rr["2026-10"]["den_zero"] is True,
          "分母 0 给 null 而不是 inf", rr["2026-10"])
    check(abs(rr["2026-11"]["ratio"] - 2000 / 1500) < 1e-6, "2000/1500", rr["2026-11"]["ratio"])

    # 流式降级：与全量结果必须一致，且分位数如实标为不可得
    st = jrun("agg", ser, "--col", "amount", "--stream")
    check(st["mode"] == "streaming", "mode 标为 streaming", st.get("mode"))
    check(st["dist"]["sum"] == 1150 and st["dist"]["count"] == 6,
          "流式 sum/count 与全量一致", st["dist"])
    check(st["dist"]["quantiles"] == "unavailable_in_streaming" and "median" not in st["dist"],
          "流式不给 median 并如实标注", list(st["dist"])[:6])
    stg = jrun("agg", ser, "--col", "amount", "--by", "channel", "--top", "2", "--stream")
    got2 = {r["key"]: r["sum"] for r in stg["groups"]}
    check(got2 == {"a": 550, "c": 400}, "流式分组求和与全量一致", got2)
    check(abs(stg["hhi"] - 0.3800) < 1e-3, "流式 HHI≈0.38", stg["hhi"])
    std = jrun("agg", ser, "--col", "amount", "--stream")
    check(std["null_rate"] == 0.0 and std["distinct"] is None
          and std["distinct_note"] == "unavailable_in_streaming",
          "流式给精确 null_rate，distinct 显式标不可得（不静默丢）", (std["null_rate"], std["distinct"]))
    stdb = jrun("agg", ser, "--col", "amount", "--by", "channel", "--top", "1",
                "--distinct-by", "channel", "--stream")
    check(stdb["groups"][0].get("distinct_channel", "缺失") is None
          and stdb.get("distinct_note") == "unavailable_in_streaming",
          "流式 --distinct-by 显式给 null 而不是丢字段", stdb["groups"][0])
    stf = jrun("agg", ser, "--col", "amount", "--time", "month", "--freq", "M",
               "--baseline", "12", "--stream")
    check([b["key"] for b in stf["buckets"]] == ["2026-01", "2026-02", "2026-03", "2026-04", "2026-11"],
          "流式月份桶一致", [b["key"] for b in stf["buckets"]])
    check(abs(stf["baseline"]["mean"] - 233.3333) < 0.01, "流式基线均值一致", stf["baseline"]["mean"])
    check(stf["buckets"][-1]["complete"] is False, "流式也标当期不完整", stf["buckets"][-1]["complete"])
    str_ = jrun("agg", os.path.join(d, "flow.csv"), "--col", "in_amt", "--time", "month",
                "--freq", "M", "--ratio", "out_amt", "--stream")
    sr = {b["key"]: b for b in str_["buckets"]}
    check(sr["2026-09"]["ratio"] == 1.0 and sr["2026-10"]["ratio"] is None,
          "流式比值一致且除零给 null", (sr["2026-09"]["ratio"], sr["2026-10"]["ratio"]))
    stw = jrun("agg", ser, "--col", "amount", "--time", "month", "--windows", "7", "--stream")
    check(stw["windows"]["7"]["sum"] == 50, "流式窗口求和一致", stw["windows"]["7"])

    i = jrun("agg", ser, "--col", "amount", "--time", "month", "--interval", "--key", "channel")
    check(i["interval"]["n"] == 3, "channel a 有 4 条记录 → 3 个间隔", i["interval"]["n"])
    check(i["interval"]["unit"] == "minutes", "间隔单位分钟", i["interval"]["unit"])


def case_shape_match(d):
    print("[6] shape / match")
    s = jrun("shape", os.path.join(d, "series.csv"), "--col", "amount", "--ints")
    check(s["ints"]["ratio"] == 1.0, "金额全为整数", s["ints"])
    s2 = jrun("shape", os.path.join(d, "series.csv"), "--col", "amount", "--near", "50")
    check(s2["near"]["count"] >= 1, "相近值能抓到 100/100", s2["near"])

    m = jrun("match", os.path.join(d, "left.csv"), os.path.join(d, "right.csv"),
             "--key", "id", "--time-a", "created_at", "--time-b", "created_at",
             "--val-a", "amount", "--val-b", "amount")
    check(m["pairs"] == 1, "匹配到 1 对", m["pairs"])
    check(abs(m["time_diff"]["median"] - 30.0) < 1e-6, "时间差 30 分钟", m["time_diff"]["median"])
    check(m["within_tol"]["count"] == 1, "浮点噪声 1e-12 在 tol 内算匹配（裸 == 会误判）",
          m["within_tol"])
    m2 = jrun("match", os.path.join(d, "left.csv"), os.path.join(d, "right.csv"),
              "--key", "id", "--time-a", "created_at", "--time-b", "created_at",
              "--val-a", "amount", "--val-b", "amount", "--within", "0.1")
    check(m2.get("pairs", 0) == 0, "--within 0.1 小时滤掉 30 分钟那对", m2.get("pairs"))


def case_run(d):
    print("[7] run：show() 截断与口径")
    code = (
        "print('rows', len(df))\n"
        "print(df.head(2).to_dict('records'))\n"
        "show(pd.DataFrame({'x': range(250)}))\n"
    )
    p = run("run", os.path.join(d, "t.csv.gz"), stdin=code)
    check(p.returncode == 0, "run 正常退出", p.stderr[:300])
    check("省略 150 行" in p.stdout, "show() 只输出 100 行并报省略数", p.stdout.strip().splitlines()[-3:])
    check("[elapsed" in p.stdout, "run 打印耗时", p.stdout.strip().splitlines()[-1])

    code2 = "x = pd.read_csv('/nonexistent.csv')\n"
    p2 = run("run", os.path.join(d, "t.csv.gz"), stdin=code2)
    check(p2.returncode != 0, "错误脚本非零退出（异常可见）", p2.returncode)


def main():
    d = tempfile.mkdtemp(prefix="tabular-selftest-")
    try:
        build(d)
        case_encoding(d)
        case_flags(d)
        case_gz(d)
        case_bad_rows(d)
        case_agg(d)
        case_shape_match(d)
        case_run(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    print()
    if FAIL:
        print(f"FAILED {len(FAIL)} / {PASS + len(FAIL)}")
        for f in FAIL:
            print(" - " + f)
        return 1
    print(f"ALL PASS ({PASS} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
