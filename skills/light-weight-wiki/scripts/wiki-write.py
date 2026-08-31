#!/usr/bin/env python3
"""wiki-write.py — 写入/更新一页，并自动完成记账（镜像 dsh-obsidian 的 writePage）。

零第三方依赖。Agent 提供 title/type/content/tags（内容由 Agent 判断），
本脚本负责机械记账：
  文件名安全 + 机器页保护 + 类型路由 + frontmatter 补全(保留 created/未知字段)
  + 更新 index.md + 追加 log.md + 来源哈希去重(未变则跳过) + 报告未解析前向链接。

用法：
  python3 wiki-write.py <vault> --title "X" --type project \
      --content "..." [--tags a,b] [--source_path f] [--force]
  python3 wiki-write.py <vault> --title "X" --type resource --content-file notes.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 让本脚本能找到同目录的 wiki_lib.py（无论从哪个 cwd 启动，也兼容
# embeddable python 的 _pth 限制；正常 Python 安装本就会把脚本目录放上 sys.path）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wiki_lib as lib

TYPES = ("domain", "area", "project", "resource", "source", "archive")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Write/update one wiki page with bookkeeping.")
    p.add_argument("vault")
    p.add_argument("--title", required=True)
    p.add_argument("--type", required=True, choices=list(TYPES))
    p.add_argument("--content", default=None, help="inline markdown body")
    p.add_argument("--content-file", default=None, help="read body from file")
    p.add_argument("--tags", default=None, help="comma-separated tags")
    p.add_argument("--source_path", default=None, help="path to source file; hash recorded")
    p.add_argument("--force", action="store_true", help="overwrite even if source hash unchanged")
    args = p.parse_args(argv)

    vault = Path(args.vault)
    if not vault.is_dir():
        print(json.dumps({"error": f"vault is not a directory: {args.vault}"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    if args.content is not None and args.content_file is not None:
        print(json.dumps({"error": "use either --content or --content-file, not both"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    if args.content_file is not None:
        src = Path(args.content_file)
        if not src.is_file():
            print(json.dumps({"error": f"content file not found: {args.content_file}"},
                             ensure_ascii=False), file=sys.stderr)
            return 2
        content = src.read_text(encoding="utf-8-sig", errors="replace")
    else:
        content = args.content or ""

    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]

    filename = lib.safe_filename(args.title)
    if lib.is_machinery(filename):
        print(json.dumps({"error": f"refusing to write machinery page: {filename}"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    if not lib.is_portable_filename(filename):
        print(json.dumps({"error": f"non-portable filename: {filename}"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    folder = lib.route_folder(vault, args.type)
    fs_root = vault.resolve()
    if not (folder / f"{filename}.md").resolve().is_relative_to(fs_root):
        print(json.dumps({"error": "path escapes vault"}, ensure_ascii=False), file=sys.stderr)
        return 2
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{filename}.md"

    # source hash + dedup
    source_hash = None
    if args.source_path:
        sp = Path(args.source_path)
        if not sp.is_file():
            print(json.dumps({"error": f"source not found: {args.source_path}"},
                             ensure_ascii=False), file=sys.stderr)
            return 2
        source_hash = lib.sha256(sp.read_text(encoding="utf-8-sig", errors="replace"))

    existing = {}
    existing_body = ""
    if target.exists():
        existing, existing_body = lib.parse_frontmatter(lib.read_utf8(target))

    if existing.get("source_hash") and source_hash and existing["source_hash"] == source_hash and not args.force:
        out = {"path": str(target), "action": "skipped", "sourceHash": source_hash,
               "reason": "source hash unchanged (pass --force to rewrite)"}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    now = datetime.now().strftime("%Y-%m-%d")
    fm = lib.complete_frontmatter(existing, {
        "title": args.title,
        "type": args.type,
        **({"tags": tags} if tags else {}),
        **({"source": args.source_path} if args.source_path else {}),
        **({"source_hash": source_hash} if source_hash else {}),
    }, now)
    final = lib.serialize_frontmatter(fm) + content
    target.write_text(final, encoding="utf-8")

    # index + log 记账
    section_heading = lib.DEFAULT_TYPE_FOLDERS.get(args.type, "resources").split("/")[-1]
    lib.upsert_index_entry(lib.layout(vault)["index"], args.type, section_heading, args.title)
    log_line = f"{args.type} [[{args.title}]]" + (f" (source {args.source_path})" if args.source_path else "")
    lib.append_log(lib.layout(vault)["log"], log_line)

    # 前向链接报告
    known = set()
    wiki_dir = lib.layout(vault)["wiki"]
    for md in lib.walk_md(wiki_dir):
        known.add(md.stem)
    known.add(args.title)
    unresolved = lib.collect_unresolved_links(content, known)

    action = "updated" if existing_body else "created"
    out = {
        "path": str(target),
        "action": action,
        "title": args.title,
        "type": args.type,
        "created": fm.get("created"),
        "updated": fm.get("updated"),
        "unresolvedLinks": unresolved,
    }
    if source_hash:
        out["sourceHash"] = source_hash
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
