#!/usr/bin/env python3
"""wiki-scaffold.py — 初始化一个 LLM-Wiki 目录结构（dry-run 默认，--apply 才写）。

零第三方依赖。结构与 light-weight-wiki 约定的类型路由一致：
  <vault>/wiki/{areas,projects,resources,sources,archive}
  <vault>/wiki/{index.md, hot.md, log.md}
  <vault>/.raw/   <vault>/inbox/Inbox.md   （可选 <vault>/inbox/）

用法：
  python3 wiki-scaffold.py <vault> [--apply] [--template default|minimal|research]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 让本脚本能找到同目录的 wiki_lib.py（无论从哪个 cwd 启动，也兼容
# embeddable python 的 _pth 限制——正常 Python 安装本就会把脚本目录放上 sys.path）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wiki_lib as lib


def plan(vault: Path, template: str) -> dict:
    l = lib.layout(vault)
    dirs = [
        l["wiki"], l["meta"], l["raw"],
        l["wiki"] / "areas", l["wiki"] / "projects",
        l["wiki"] / "resources", l["wiki"] / "sources", l["wiki"] / "archive",
        vault / "inbox",
    ]
    plan = {"create": [], "write": [], "skipped": []}
    for d in dirs:
        if d.exists():
            plan["skipped"].append(str(d))
        else:
            plan["create"].append(str(d))

    files = {
        l["index"]: "# Index\n\n## areas\n\n## projects\n\n## resources\n\n## sources\n\n",
        l["hot"]: "# Hot Cache\n\n_Recent context, refreshed by `wiki_search --quick`._\n",
        l["log"]: "# Log\n\n",
        vault / "inbox" / "Inbox.md":
            "# Inbox\n\nDrop source URLs, files, or pasted notes here. The `wiki` "
            "skill turns them into wiki pages.\n",
    }
    if template == "research":
        files[l["wiki"] / "Research Questions.md"] = "# Research Questions\n\n- [ ] \n"

    files_written = 0
    files_skipped = 0
    for path, content in files.items():
        if path.exists():
            plan["skipped"].append(str(path))
            files_skipped += 1
        else:
            plan["write"].append({"path": str(path), "content": content})
            files_written += 1
    plan["summary"] = {"dirs_to_create": len(plan["create"]),
                       "files_to_write": files_written,
                       "skipped": len(plan["skipped"])}
    return plan


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Scaffold a lightweight LLM-Wiki vault.")
    p.add_argument("vault")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--template", choices=["default", "minimal", "research"], default="default")
    args = p.parse_args(argv)

    vault = Path(args.vault)
    if not vault.is_dir() and not args.apply:
        print(json.dumps({"error": f"vault is not a directory: {args.vault}"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    pl = plan(vault, args.template)
    if not args.apply:
        result = {"dry_run": True, **pl}
    else:
        vault.mkdir(parents=True, exist_ok=True)
        for d in pl["create"]:
            Path(d).mkdir(parents=True, exist_ok=True)
        for f in pl["write"]:
            path = Path(f["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f["content"], encoding="utf-8")
        result = {"dry_run": False, "applied": True,
                  "created_dirs": len(pl["create"]),
                  "wrote_files": len(pl["write"]),
                  "skipped": len(pl["skipped"])}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
