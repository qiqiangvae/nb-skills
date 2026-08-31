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

WIKILINK_RE = re.compile(r"!?\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)(?:#[^)]*)?\)", re.IGNORECASE)


def link_name(target: str) -> str:
    name = target.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"\.md$", "", name, flags=re.IGNORECASE)
    return name.split("#", 1)[0].split("|", 1)[0].strip()


def page_links(body: str) -> set[str]:
    s = set()
    for m in WIKILINK_RE.finditer(body):
        t = m.group(1).strip()
        if t:
            s.add(link_name(t))
    for m in MDLINK_RE.finditer(body):
        t = m.group(1).strip()
        if t:
            s.add(link_name(t))
    return s


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Health-check the lightweight wiki vault.")
    p.add_argument("vault")
    p.add_argument("--report", action="store_true")
    args = p.parse_args(argv)

    vault = Path(args.vault)
    l = lib.layout(vault)
    wiki_dir = l["wiki"]
    if not wiki_dir.is_dir():
        print(json.dumps({"error": f"no wiki at {wiki_dir}; run wiki-scaffold.py first"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    issues = []
    by_title = {}
    title_count = Counter()
    for p in lib.walk_md(wiki_dir):
        name = p.stem
        if lib.is_machinery(name):
            continue
        title_count[name] += 1
        by_title.setdefault(name, p)

    # 重复文件名
    for name, n in title_count.items():
        if n > 1:
            issues.append({"severity": "error", "category": "duplicate-filename",
                           "file": name, "message": f'filename "{name}" used {n} times',
                           "suggestion": "merge or rename"})

    titles = set(title_count.keys())
    by_lower = {t.lower(): t for t in titles}

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
        for m in re.finditer(r"\n## ([^\n]+)\n(?=\n|## |$)", body):
            issues.append({"severity": "info", "category": "empty-section", "file": f"- {name}",
                           "message": f'section "{m.group(1)}" is empty', "suggestion": "add content"})
        if not inbound.get(name):
            issues.append({"severity": "info", "category": "orphan", "file": f"- {name}",
                           "message": f'"{name}" has no inbound links', "suggestion": "link it"})

    # 失效 index / 陈旧 hot
    if l["index"].exists():
        index_body = lib.read_utf8(l["index"])
        for p in lib.walk_md(wiki_dir):
            name = p.stem
            if lib.is_machinery(name):
                continue
            fm, _ = lib.parse_frontmatter(lib.read_utf8(p))
            cands = {name}
            if fm.get("title"):
                cands.add(str(fm["title"]))
            if not any(f"[[{c}]]" in index_body for c in cands):
                issues.append({"severity": "info", "category": "stale-index", "file": "- index",
                               "message": f'"{name}" missing from index', "suggestion": "re-run wiki-write"})
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
