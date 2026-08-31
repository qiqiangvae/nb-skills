#!/usr/bin/env python3
"""wiki-rename.py — 重命名/删除一页（镜像 dsh-obsidian 的 wiki_rename / deletePage）。

零第三方依赖。拒绝机器页（index/hot/log/readme/Lint Report*），拒绝非可移植文件名。
在所有有效的 type 目录里定位旧页并改名/删除，支持 --type_folders 自定义路由。

用法：
  python3 wiki-rename.py <vault> --old "旧标题" --new "新标题" [--type_folders "project=wiki/projects"]
  python3 wiki-rename.py <vault> --delete "标题"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 让本脚本能找到同目录的 wiki_lib.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wiki_lib as lib


def parse_type_folders(s: str | None) -> dict | None:
    if not s:
        return None
    tf: dict = {}
    for kv in s.split(";"):
        kv = kv.strip()
        if not kv:
            continue
        if "=" not in kv:
            raise ValueError(f"bad --type_folders item: {kv}")
        k, v = kv.split("=", 1)
        tf[k.strip()] = v.strip()
    return tf


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Rename or delete one wiki page.")
    p.add_argument("vault", nargs="?", default=None,
                   help="vault root; omit to use LIGHTWEIGHT_WIKI_VAULT / config.json")
    p.add_argument("--old", default=None, help="old title (for rename)")
    p.add_argument("--new", default=None, help="new title (for rename)")
    p.add_argument("--delete", default=None, help="title to delete")
    p.add_argument("--no-sync-refs", action="store_true",
                   help="do NOT rewrite [[old]] -> [[new]] references across the vault (default rewrites)")
    p.add_argument("--type_folders", default=None,
                   help='semicolon-separated type->dir overrides, e.g. "project=wiki/projects"')
    args = p.parse_args(argv)

    vault = lib.ensure_vault_path(args.vault, require_wiki=True)
    if vault is None:
        print(json.dumps({"error": "no vault path: pass it, set LIGHTWEIGHT_WIKI_VAULT, "
                                    "or run light-weight-wiki-config.py --vault <path>"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    if args.delete and (args.old or args.new):
        print(json.dumps({"error": "--delete is exclusive with --old/--new"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    if (args.old and not args.new) or (args.new and not args.old):
        print(json.dumps({"error": "--old and --new must be given together"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    try:
        tf = parse_type_folders(args.type_folders) or lib.resolve_type_folders()
        if args.delete:
            out = lib.delete_page(vault, args.delete, tf)
        else:
            if not args.old or not args.new:
                p.error("provide --old/--new (rename) or --delete (delete)")
            out = lib.rename_page(vault, args.old, args.new, tf, sync_refs=not args.no_sync_refs)
    except (ValueError, FileNotFoundError, FileExistsError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
