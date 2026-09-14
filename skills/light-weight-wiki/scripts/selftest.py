#!/usr/bin/env python3
"""selftest.py — light-weight-wiki 的最小回归检查（零第三方依赖，直接运行）。

    python3 selftest.py

锁住曾经的真实缺陷，改坏任何一个都会失败：
  1. lint 的 empty-section：标准 Markdown（`## 标题` + 空行 + 正文）不得报空节
     （修复前：真实 vault 183 条里 182 条是误报）
  2. generic 模式的 index 分节：type=concept 必须记在 `## Concepts`，
     修复前被兜底成 `## Resources`，与页面落盘目录不一致
  3. repository 模式的 stale-index：登记在分区 `_index.md` 的页不算失效
     （写入侧刻意不维护根 index.md，两处任一命中即已索引）
  4. 改名：页内 frontmatter `title` 跟改、log 历史行不被改写且追加改名记录、
     全库引用同步（修复前 title 留旧名、log 被就地改写、改名不留痕）
  5. 删页：标题含 `/` 时引用也要清掉（修复前用 safe_filename 匹配 `[[A/B]]`，清不掉）
  6. `unresolvedLinks`（写入侧）与 `dead-link`（检查侧）同源：
     指向分区 `_index.md` 的 `[[… Index]]` 两边都不算缺失
  7. 建库：目标目录还不存在时也出 dry-run 计划；已删的空模板 `minimal` 不再被接受
  8. `--type` 必须是不含路径分隔符的单个标记（否则能在 vault 里造出任意层目录）
  9. 检索：指向分区 `_index` 的链接能在链接图里落到点上（修复前边全丢）
 10. 手写 frontmatter 不丢数据：block 列表（`tags:` + `  - x`）经 wiki-write 更新后
     值仍在（修复前被读成空串、序列化时整段删掉）；改名只动 `title:` 一行，
     其余字节原样（修复前改名会把整块 frontmatter 重排）
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wiki_lib as lib  # noqa: E402

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


def run_fail(script: str, *args: str) -> tuple[int, str]:
    """跑一个预期会失败的命令，返回 (returncode, stderr)。"""
    p = subprocess.run([sys.executable, str(HERE / script), *args],
                       capture_output=True, text=True)
    return p.returncode, p.stderr


def scaffold(vault: Path) -> None:
    run("wiki-scaffold.py", str(vault), "--apply")


def fresh_vault(tmp: str) -> Path:
    vault = Path(tmp) / "vault"
    scaffold(vault)
    return vault


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
        vault = fresh_vault(tmp)
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


def test_rename() -> None:
    print("4) 改名：title 跟改、log 历史不被改写、引用同步")
    with tempfile.TemporaryDirectory() as tmp:
        vault = fresh_vault(tmp)
        run("wiki-write.py", str(vault), "--title", "旧名页", "--type", "area", "--content", "x\n")
        run("wiki-write.py", str(vault), "--title", "引用页", "--type", "area",
            "--content", "见 [[旧名页]]。\n")
        run("wiki-rename.py", str(vault), "--old", "旧名页", "--new", "新名页")

        new_page = vault / "wiki" / "areas" / "新名页.md"
        check(new_page.is_file(), "页面已改名")
        page_text = new_page.read_text(encoding="utf-8") if new_page.is_file() else ""
        check("title: 新名页" in page_text, "页内 frontmatter title 同步为新名")
        log = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
        check("[[旧名页]]" in log, "log 历史行保留旧名（审计轨迹不被就地改写）")
        check("renamed [[旧名页]] -> [[新名页]]" in log, "log 追加了改名记录")
        ref = (vault / "wiki" / "areas" / "引用页.md").read_text(encoding="utf-8")
        check("[[新名页]]" in ref and "[[旧名页]]" not in ref, "全库引用已同步为新名")


def test_delete_unsafe_title() -> None:
    print("5) 删页：标题含路径字符时引用也要清掉")
    with tempfile.TemporaryDirectory() as tmp:
        vault = fresh_vault(tmp)
        run("wiki-write.py", str(vault), "--title", "A/B", "--type", "area", "--content", "x\n")
        run("wiki-write.py", str(vault), "--title", "引用者", "--type", "area",
            "--content", "见 [[A/B]]。\n")
        check((vault / "wiki" / "areas" / "A-B.md").is_file(), "落盘文件名已做安全化（A-B.md）")
        run("wiki-rename.py", str(vault), "--delete", "A/B")
        check(not (vault / "wiki" / "areas" / "A-B.md").exists(), "页面已删除")
        body = (vault / "wiki" / "areas" / "引用者.md").read_text(encoding="utf-8")
        check("[[A/B]]" not in body, "指向它的 [[A/B]] 被清理（按原始标题匹配）")


def test_write_lint_agree_on_links() -> None:
    print("6) unresolvedLinks 与 dead-link 同源")
    with tempfile.TemporaryDirectory() as tmp:
        vault = fresh_vault(tmp)
        (vault / "wiki" / "runbooks").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "runbooks" / "_index.md").write_text(
            "---\ntype: meta\ntitle: Runbooks Index\n---\n\n", encoding="utf-8")
        out = run("wiki-write.py", str(vault), "--title", "重启手册", "--type", "runbook",
                  "--content", "见 [[Runbooks Index]] 与 [[不存在的页]]。\n")
        check(out["unresolvedLinks"] == ["不存在的页"],
              f"分区 _index 的 title 算已存在（实得 {out['unresolvedLinks']}）")
        dead = [i["message"] for i in run("wiki-lint.py", str(vault))["issues"]
                if i["category"] == "dead-link"]
        check(not any("Runbooks Index" in m for m in dead), "lint 也不把该链接报成死链")
        check(any("不存在的页" in m for m in dead), "lint 仍报真正的死链")


def test_scaffold_new_dir() -> None:
    print("7) 建库：新目录可 dry-run；空模板 minimal 已移除")
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "brand-new"
        out = run("wiki-scaffold.py", str(vault))
        check(out.get("dry_run") is True and bool(out["create"]),
              "目录不存在时 dry-run 仍给出 create 计划")
        check(not vault.exists(), "dry-run 不落盘")
        rc, _ = run_fail("wiki-scaffold.py", str(vault), "--template", "minimal")
        check(rc != 0, "已删除的空模板 minimal 不再被接受（避免与 default 同义的假选项）")


def test_type_must_be_path_free() -> None:
    print("8) --type 必须是不含路径分隔符的单个标记")
    with tempfile.TemporaryDirectory() as tmp:
        vault = fresh_vault(tmp)
        rc, err = run_fail("wiki-write.py", str(vault), "--title", "越界页",
                           "--type", "../../evil", "--content", "x\n")
        check(rc == 2 and "bad --type" in err, f"拒绝含路径的 type（rc={rc}）")
        rc, err = run_fail("wiki-write.py", str(vault), "--title", "越界页",
                           "--type", "a/b", "--content", "x\n")
        check(rc == 2, "拒绝 type 里的斜杠（否则会在 vault 里造出任意层目录）")


def test_search_link_graph() -> None:
    print("9) 检索：指向分区 _index 的链接落到点上")
    with tempfile.TemporaryDirectory() as tmp:
        vault = fresh_vault(tmp)
        (vault / "wiki" / "runbooks").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "runbooks" / "_index.md").write_text(
            "---\ntype: meta\ntitle: Runbooks Index\n---\n\n- [[重启手册]]\n", encoding="utf-8")
        run("wiki-write.py", str(vault), "--title", "重启手册", "--type", "runbook",
            "--content", "步骤见 [[Runbooks Index]]。\n")
        res = run("wiki-search.py", str(vault), "Runbooks Index", "--top", "5")
        check(all(h["title"] != "_index" for h in res["hits"]),
              "结果里不再出现没有信息量的 `_index` 标题")
        hit = next((h for h in res["hits"] if h["title"] == "Runbooks Index"), None)
        check(hit is not None and hit["inbound"] == ["重启手册"],
              f"导航页有入链（实得 {hit['inbound'] if hit else None}）")


BLOCK_FM = ("---\ntitle: {t}\ntype: domain\ntags:\n  - alpha\n  - beta\n"
            "repositories:\n  - repo-one\n  - repo-two\naliases:\n- flat-one\n- flat-two\n"
            "created: 2026-01-01\n---\n\n正文\n")


def test_frontmatter_survives() -> None:
    print("10) 手写 frontmatter 经写入/改名不丢数据")
    with tempfile.TemporaryDirectory() as tmp:
        vault = fresh_vault(tmp)
        domains = vault / "wiki" / "domains"
        domains.mkdir(parents=True, exist_ok=True)

        # (a) 更新一个手写的、block 列表写法的页
        a = domains / "手写页.md"
        a.write_text(BLOCK_FM.format(t="手写页"), encoding="utf-8")
        run("wiki-write.py", str(vault), "--title", "手写页", "--type", "domain",
            "--content", "更新后的正文\n")
        fm, _ = lib.parse_frontmatter(a.read_text(encoding="utf-8"))
        check(fm.get("tags") == ["alpha", "beta"], f"block 列表 tags 仍在（实得 {fm.get('tags')!r}）")
        check(fm.get("repositories") == ["repo-one", "repo-two"],
              f"未知键的 block 列表仍在（实得 {fm.get('repositories')!r}）")
        check(fm.get("aliases") == ["flat-one", "flat-two"],
              f"顶格写法的 block 列表也在（实得 {fm.get('aliases')!r}）")
        check(fm.get("created") == "2026-01-01", "created 未被覆盖")

        # (b) 改名不得重排它没在编辑的 frontmatter
        b = domains / "待改名.md"
        b.write_text(BLOCK_FM.format(t="待改名"), encoding="utf-8")
        before = b.read_text(encoding="utf-8")
        run("wiki-rename.py", str(vault), "--old", "待改名", "--new", "已改名")
        renamed = domains / "已改名.md"
        check(renamed.is_file(), "页面已改名")
        after = renamed.read_text(encoding="utf-8")
        check(after == before.replace("title: 待改名", "title: 已改名"),
              "除 title 行外字节完全不变（block 列表与缩进原样保留）")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        vault = fresh_vault(tmp)
        test_empty_section(vault)
        test_generic_section(vault)
    test_repository_stale_index()
    test_rename()
    test_delete_unsafe_title()
    test_write_lint_agree_on_links()
    test_scaffold_new_dir()
    test_type_must_be_path_free()
    test_search_link_graph()
    test_frontmatter_survives()
    print()
    if FAILED:
        print(f"FAILED ({len(FAILED)}): " + "; ".join(FAILED))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
