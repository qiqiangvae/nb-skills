#!/usr/bin/env python3
"""selftest.py — light-weight-wiki 的最小回归检查（零第三方依赖，直接运行）。

    python3 selftest.py

锁住三个曾经的真实缺陷，改坏任何一个都会失败：
  1. lint 的 empty-section：标准 Markdown（`## 标题` + 空行 + 正文）不得报空节
     （修复前：真实 vault 183 条里 182 条是误报）
  2. generic 模式的 index 分节：type=concept 必须记在 `## Concepts`，
     修复前被兜底成 `## Resources`，与页面落盘目录不一致
  3. repository 模式的 stale-index：登记在分区 `_index.md` 的页不算失效
     （写入侧刻意不维护根 index.md，两处任一命中即已索引）
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

FAILED: list[str] = []


def check(ok: bool, label: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        FAILED.append(label)


def run(script: str, *args: str) -> dict:
    p = subprocess.run([sys.executable, str(HERE / script), *args],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise AssertionError(f"{script} {' '.join(args)} failed: {p.stderr.strip()}")
    return json.loads(p.stdout)


def scaffold(vault: Path) -> None:
    run("wiki-scaffold.py", str(vault), "--apply")


def test_empty_section(vault: Path) -> None:
    print("1) empty-section 只报真空节")
    # 正文前面必须有一个非标题行/标题，否则第一个 `##` 位于正文开头，
    # 旧正则（要求前置 \n）会漏掉它，测试就抓不到误报了。
    body = ("# 空节测试\n\n## 有正文的小节\n\n这里是正文。\n\n"
            "## 只有子标题的父节\n\n### 子节\n\n子节有内容。\n\n## 真的空节\n")
    run("wiki-write.py", str(vault), "--title", "空节测试", "--type", "concept",
        "--content", body)
    hits = [i for i in run("wiki-lint.py", str(vault))["issues"]
            if i["category"] == "empty-section"]
    check(len(hits) == 1, f"只报 1 条空节（实得 {len(hits)}）")
    check(hits and "真的空节" in hits[0]["message"],
          "报的是真的空节，而不是「标题+空行+正文」的标准写法")
    check(hits and "只有子标题的父节" not in hits[0]["message"],
          "下辖 ### 子标题的父节不算空节")


def test_generic_section(vault: Path) -> None:
    print("2) generic 模式 index 分节跟随实际落点")
    index = (vault / "wiki" / "index.md").read_text(encoding="utf-8")
    check((vault / "wiki" / "concepts" / "空节测试.md").is_file(), "页面落在 wiki/concepts/")
    concept_sec = index.split("## Concepts", 1)[1].split("\n## ", 1)[0] if "## Concepts" in index else ""
    resource_sec = index.split("## Resources", 1)[1].split("\n## ", 1)[0] if "## Resources" in index else ""
    check("[[空节测试]]" in concept_sec, "记在 ## Concepts 分节")
    check("[[空节测试]]" not in resource_sec, "没有串到 ## Resources 分节")


def test_repository_stale_index() -> None:
    print("3) repository 模式：两种登记方式都算已索引")
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        scaffold(vault)
        # (a) 登记在分区 _index.md
        (vault / "wiki" / "runbooks").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "runbooks" / "_index.md").write_text(
            "---\ntype: meta\ntitle: Runbooks Index\n---\n\n- [[重启手册]]\n", encoding="utf-8")
        run("wiki-write.py", str(vault), "--title", "重启手册", "--type", "runbook",
            "--content", "步骤见 [[Runbooks Index]]。\n")
        # (b) 登记在根 index.md，但用 markdown 链接而非 wikilink
        run("wiki-write.py", str(vault), "--title", "概览页", "--type", "area",
            "--content", "见 [[Runbooks Index]]。\n")
        index = vault / "wiki" / "index.md"
        index.write_text(index.read_text(encoding="utf-8") + "\n- [概览页](areas/概览页.md)\n",
                         encoding="utf-8")
        run("wiki-write.py", str(vault), "--title", "真没登记的页", "--type", "area",
            "--content", "见 [[Runbooks Index]]。\n")

        stale = [i["message"] for i in run("wiki-lint.py", str(vault))["issues"]
                 if i["category"] == "stale-index"]
        check(not any("重启手册" in m for m in stale), "分区 _index.md 里登记的页不报")
        check(not any("概览页" in m for m in stale), "根 index.md 用 markdown 链接登记的页不报")
        check(any("真没登记的页" in m for m in stale), "两处都没登记的页仍然照报")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        scaffold(vault)
        test_empty_section(vault)
        test_generic_section(vault)
    test_repository_stale_index()
    print()
    if FAILED:
        print(f"FAILED ({len(FAILED)}): " + "; ".join(FAILED))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
