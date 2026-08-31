#!/usr/bin/env python3
"""light-weight-wiki-config.py — 查看/设置 light-weight-wiki 的全局配置。

替代原版 dsh-obsidian 的 cordis.patch.yml 配置（vaultPath + typeFolders），
用跨 agent 通用的 JSON 配置文件。配置文件位置：
  <$XDG_CONFIG_HOME|~/.config>/light-weight-wiki/config.json

用法：
  python3 light-weight-wiki-config.py                     # 打印当前配置
  python3 light-weight-wiki-config.py --vault /abs/path   # 设置 vaultPath
  python3 light-weight-wiki-config.py --type-folders 'project=wiki/projects;area=wiki/concepts'
  python3 light-weight-wiki-config.py --unset-vault       # 清除 vaultPath
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiki_lib as lib


def parse_type_folders(s: str) -> dict:
    tf: dict = {}
    for kv in s.split(";"):
        kv = kv.strip()
        if not kv:
            continue
        if "=" not in kv:
            raise ValueError(f"bad item (need key=value): {kv}")
        k, v = kv.split("=", 1)
        tf[k.strip()] = v.strip()
    return tf


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="View/set light-weight-wiki global config.")
    p.add_argument("--vault", default=None, help="set vaultPath to this absolute path")
    p.add_argument("--type-folders", default=None,
                   help='set typeFolders, e.g. "project=wiki/projects;area=wiki/concepts"')
    p.add_argument("--unset-vault", action="store_true", help="remove vaultPath")
    p.add_argument("--get", action="store_true", help="print the resolved vault path only")
    args = p.parse_args(argv)

    cfg = lib.load_config()

    changed = False
    if args.vault is not None:
        cfg["vaultPath"] = os.path.abspath(args.vault)
        changed = True
    if args.type_folders is not None:
        cfg["typeFolders"] = parse_type_folders(args.type_folders)
        changed = True
    if args.unset_vault:
        cfg.pop("vaultPath", None)
        changed = True

    if changed:
        path = lib.save_config(cfg)
        print(json.dumps({"saved": str(path), "config": cfg}, ensure_ascii=False, indent=2))
        return 0

    # 只读模式
    if args.get:
        vp = lib.resolve_vault_path()
        print(vp if vp else "")
        return 0

    resolved = lib.resolve_vault_path()
    env = os.environ.get(lib.CONFIG_ENV_VAR)
    print(json.dumps({
        "configFile": str(lib.config_path()),
        "vaultPath": str(resolved) if resolved else None,
        "vaultPathSource": ("argv" if args.vault else
                            ("env" if env else
                             ("config" if cfg.get("vaultPath") else None))),
        "envVar": lib.CONFIG_ENV_VAR,
        "typeFolders": cfg.get("typeFolders"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
