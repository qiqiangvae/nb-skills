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

# 常见 type（用于帮助提示）；实际不设 choices 限制——
# repository 模式下 type 是内容页 frontmatter 的自由取值（concept/decision/entity/…），
# 路由按 `type 复数 → wiki/<复数>` 推导，见 wiki_lib.pluralize_type。
TYPES = ("domain", "area", "project", "resource", "source", "archive",
         "concept", "decision", "dependency", "domain", "entity", "flow",
         "module", "comparison", "component", "question", "runbook", "standard")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Write/update one wiki page with bookkeeping.")
    p.add_argument("vault", nargs="?", default=None,
                   help="vault root; omit to use LIGHTWEIGHT_WIKI_VAULT / config.json")
    p.add_argument("--title", required=True)
    p.add_argument("--type", required=True,
                   help="page type; routes to wiki/<type plural>. "
                        "common: " + ",".join(TYPES))
    p.add_argument("--content", default=None, help="inline markdown body")
    p.add_argument("--content-file", default=None, help="read body from file")
    p.add_argument("--tags", default=None, help="comma-separated tags")
    p.add_argument("--source_path", default=None, help="path to source file; hash recorded")
    p.add_argument("--force", action="store_true", help="overwrite even if source hash unchanged")
    # 自定义 type 路由（对齐 dsh-obsidian 的 config.typeFolders）。
    # 格式 "project=wiki/projects;resource=wiki/resources"，用分号分隔。
    p.add_argument("--type_folders", default=None,
                   help="semicolon-separated type->dir overrides, e.g. \"project=wiki/projects;area=wiki/concepts\"")
    args = p.parse_args(argv)

    type_folders = None
    if args.type_folders:
        type_folders = {}
        for kv in args.type_folders.split(";"):
            kv = kv.strip()
            if not kv:
                continue
            if "=" not in kv:
                print(json.dumps({"error": f"bad --type_folders item: {kv}"},
                                 ensure_ascii=False), file=sys.stderr)
                return 2
            k, v = kv.split("=", 1)
            type_folders[k.strip()] = v.strip()

    # vault 解析：命令行 > 环境变量 > 配置文件 > 交互询问（无障碍则报错）
    vault = lib.ensure_vault_path(args.vault, require_wiki=True)
    if vault is None:
        print(json.dumps({"error": "no vault path: pass it, set LIGHTWEIGHT_WIKI_VAULT, "
                                    "or run light-weight-wiki-config.py --vault <path>"},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    # 配置文件里的 typeFolders 作为命令行未指定时的回退
    if type_folders is None:
        type_folders = lib.resolve_type_folders()
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

    folder = lib.route_folder(vault, args.type, type_folders)
    fs_root = vault.resolve()
    if not (folder / f"{filename}.md").resolve().is_relative_to(fs_root):
        print(json.dumps({"error": "path escapes vault"}, ensure_ascii=False), file=sys.stderr)
        return 2
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{filename}.md"

    # source hash + dedup
    # 兼容两种 --source_path 用法：
    #  1) 真实文件路径 → 记录 SHA-256 用于去重（原行为）
    #  2) 非文件的标记字符串（如 "conversation"）→ 仅作为 source 元数据，不算哈希不去重
    source_hash = None
    if args.source_path:
        sp = Path(args.source_path)
        if sp.is_file():
            source_hash = lib.sha256(sp.read_text(encoding="utf-8-sig", errors="replace"))
        elif args.source_path.strip():
            # 非文件：当作来源标记，不哈希
            source_hash = None

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

    # index + log 记账（使用合并后的 type 路由，而非默认值）
    log_line = f"{args.type} [[{args.title}]]" + (f" (source {args.source_path})" if args.source_path else "")
    lib.append_log(lib.layout(vault, type_folders)["log"], log_line)
    if lib.is_repository_vault(vault):
        # Obsidian repository 模式：分区导航（根 index.md / 各分区 _index.md）由人工维护，
        # 脚本只落盘 + log，不改动导航页，避免往精排的导航里塞机械条目。
        indexed = False
    else:
        # generic 扁平模式：脚本负责 index.md 的 ## Section 记账
        effective_tf = type_folders if type_folders is not None else lib.DEFAULT_TYPE_FOLDERS
        section_heading = effective_tf.get(args.type, effective_tf.get("resource", "wiki/resources")).split("/")[-1]
        # 统一首字母大写，与 scaffold 生成的 ## Areas/## Projects 分节一致（避免小写分节分裂）
        section_heading = section_heading[:1].upper() + section_heading[1:] if section_heading else section_heading
        lib.upsert_index_entry(lib.layout(vault, type_folders)["index"], args.type, section_heading, args.title)
        indexed = True

    # 前向链接报告
    known = set()
    wiki_dir = lib.layout(vault, type_folders)["wiki"]
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
        "indexed": indexed,
    }
    if source_hash:
        out["sourceHash"] = source_hash
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
