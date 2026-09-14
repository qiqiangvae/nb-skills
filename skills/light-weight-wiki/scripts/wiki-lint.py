#!/usr/bin/env python3
"""wiki-lint.py — 知识库健康检查（镜像 dsh-obsidian 的 lint 契约）。

零第三方依赖。检查：重复文件名、frontmatter(type/created)缺失、死链、空章节、
孤儿页（无内容页入链）、失效 index、陈旧 hot cache。默认只报告；--report 写一份
带日期的报告到 <vault>/wiki/meta/Lint Report <date>.md。

用法：
  python3 wiki-lint.py <vault>
  python3 wiki-lint.py <vault> --report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# 让本脚本能找到同目录的 wiki_lib.py（无论从哪个 cwd 启动，也兼容
# embeddable python 的 _pth 限制；正常 Python 安装本就会把脚本目录放上 sys.path）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wiki_lib as lib

# 链接语法与「已知链接目标」都只有一份实现（在 wiki_lib）：lint 与 wiki-write 的
# dead-link / unresolvedLinks 必须同源，否则两边对同一页给出矛盾的结论。
link_name = lib.link_name
page_links = lib.extract_links


def empty_sections(body: str) -> list[str]:
    """返回自身没有内容的 `##` 小节标题。

    判定：某个 `##` 标题之后的下一个非空行不存在，或它本身是同级/更高级标题（`#`/`##`）。
    - 标题后跟一个空行再跟正文是标准 Markdown 写法，**不算**空节；
    - 下辖 `###` 子标题的父节也不算空，否则结构化导航会被整体误报；
    - 代码块 fence 内的 `##` 不是标题，跳过。
    """
    lines = body.splitlines()
    heads: list[tuple[int, str]] = []
    fenced = False
    for i, line in enumerate(lines):
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = re.match(r"^##\s+(\S.*?)\s*$", line)
        if m:
            heads.append((i, m.group(1)))
    out = []
    for i, title in heads:
        nxt = next((l for l in lines[i + 1:] if l.strip()), "")
        if not nxt or re.match(r"^#{1,2}\s", nxt):
            out.append(title)
    return out


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Health-check the lightweight wiki vault.")
    p.add_argument("vault", nargs="?", default=None,
                   help="vault root; omit to use LIGHTWEIGHT_WIKI_VAULT / config.json")
    p.add_argument("--report", action="store_true")
    args = p.parse_args(argv)

    vault = lib.ensure_vault_path(args.vault, require_wiki=True)
    if vault is None:
        print(json.dumps({"error": "no vault path: pass it, set LIGHTWEIGHT_WIKI_VAULT, "
                                    "or run light-weight-wiki-config.py --vault <path>"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    l = lib.layout(vault)
    wiki_dir = l["wiki"]
    if not wiki_dir.is_dir():
        print(json.dumps({"error": f"no wiki at {wiki_dir}; run wiki-scaffold.py first"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    issues = []
    title_count = Counter()
    for p in lib.walk_md(wiki_dir):
        name = p.stem
        if lib.is_machinery(name):
            continue
        title_count[name] += 1

    # 重复文件名
    for name, n in title_count.items():
        if n > 1:
            issues.append({"severity": "error", "category": "duplicate-filename",
                           "file": name, "message": f'filename "{name}" used {n} times',
                           "suggestion": "merge or rename"})

    # 已知链接目标（小写 → 规范写法）：内容页文件名、各页 frontmatter title、
    # 分区 _index.md、机器页 index/log/hot/readme。与 wiki-write 的 unresolvedLinks
    # 共用同一份实现，两边不会对同一条 [[链接]] 给出矛盾结论。
    by_lower = lib.linkable_names(vault)

    inbound = defaultdict(set)
    for p in lib.walk_md(wiki_dir):
        name = p.stem
        if lib.is_machinery(name):
            continue
        body = lib.read_utf8(p)
        for t in page_links(body):
            target = by_lower.get(t.lower())
            if target and target != name:
                inbound[target].add(name)

    for p in lib.walk_md(wiki_dir):
        name = p.stem
        if lib.is_machinery(name):
            continue
        raw = lib.read_utf8(p)
        fm, body = lib.parse_frontmatter(raw)
        if not fm.get("type"):
            issues.append({"severity": "warn", "category": "frontmatter", "file": f"- {name}",
                           "message": "missing `type`",
                           "suggestion": "add type: resource/domain/area/project/source/archive"})
        if not fm.get("created"):
            issues.append({"severity": "info", "category": "frontmatter", "file": f"- {name}",
                           "message": "missing `created`", "suggestion": "add created: YYYY-MM-DD"})
        for t in page_links(body):
            if t.lower() not in by_lower:
                issues.append({"severity": "warn", "category": "dead-link", "file": f"- {name}",
                               "message": f"unresolved [[{t}]]",
                               "suggestion": f'create "{t}" or fix the link'})
        for title in empty_sections(body):
            issues.append({"severity": "info", "category": "empty-section", "file": f"- {name}",
                           "message": f'section "{title}" is empty', "suggestion": "add content"})
        if not inbound.get(name):
            issues.append({"severity": "info", "category": "orphan", "file": f"- {name}",
                           "message": f'"{name}" has no inbound links', "suggestion": "link it"})

    # 失效 index / 陈旧 hot
    if l["index"].exists():
        # 登记方式两种都算：`[[页面]]` 与 markdown 链接 `[文字](页面.md)`。
        # 只看 wikilink 会把 `[Overview](overview.md)` 这类登记误报成失效。
        index_names = page_links(lib.read_utf8(l["index"]))
        # repository 模式：wiki-write 刻意不改根 index.md（分区导航由人工维护），
        # 页面的登记处是它自己分区的 `_index.md`。两处任一命中即算已索引，
        # 否则这些页会永远报 stale-index，与写入侧的契约自相矛盾。
        repository = lib.is_repository_vault(vault)
        for p in lib.walk_md(wiki_dir):
            name = p.stem
            if lib.is_machinery(name):
                continue
            fm, _ = lib.parse_frontmatter(lib.read_utf8(p))
            cands = {name}
            if fm.get("title"):
                cands.add(str(fm["title"]))
            linked = bool(cands & index_names)
            if not linked and repository:
                section_index = p.parent / "_index.md"
                linked = (section_index.is_file()
                          and bool(cands & page_links(lib.read_utf8(section_index))))
            if not linked:
                issues.append({"severity": "info", "category": "stale-index", "file": "- index",
                               "message": f'"{name}" missing from index',
                               "suggestion": "re-run wiki-write" if not repository else
                                             "add it to wiki/index.md or its section _index.md"})
    if l["hot"].exists():
        age = (datetime.now().timestamp() - l["hot"].stat().st_mtime) / 86400
        if age > 30:
            issues.append({"severity": "info", "category": "stale-hot", "file": "- hot",
                           "message": f"hot cache is {int(age)} days old",
                           "suggestion": "refresh via wiki_search --quick"})

    sev_count = Counter(i["severity"] for i in issues)
    result = {
        "generatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "totals": {"error": sev_count.get("error", 0),
                   "warn": sev_count.get("warn", 0),
                   "info": sev_count.get("info", 0),
                   "count": len(issues)},
        "issues": issues,
    }

    if args.report:
        l["meta"].mkdir(parents=True, exist_ok=True)
        date = result["generatedAt"][:10]
        report_path = l["meta"] / f"Lint Report {date}.md"
        lines = [f"# Lint Report — {date}", "",
                 f"Totals: {result['totals']['error']} error(s), {result['totals']['warn']} warn(s), "
                 f"{result['totals']['info']} info(s)", ""]
        for sev in ("error", "warn", "info"):
            group = [i for i in issues if i["severity"] == sev]
            if not group:
                continue
            lines.append(f"## {sev.upper()} ({len(group)})")
            lines.append("")
            for i in group:
                lines.append(f"- **{i['category']}** — {i['file']}: {i['message']}")
                if i.get("suggestion"):
                    lines.append(f"  - _suggestion:_ {i['suggestion']}")
            lines.append("")
        report_path.write_text("\n".join(lines), encoding="utf-8")
        result["reportPath"] = str(report_path)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
