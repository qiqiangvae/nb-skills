#!/usr/bin/env python3
"""wiki_lib.py — light-weight-wiki 的共享机械层（记账/安全/工具）。

零第三方依赖。实现 dsh-obsidian `vault.js` 的核心记账逻辑：
frontmatter 解析/补全/序列化、文件名安全、类型路由、index/log 记账、sha256 去重。
被 wiki-scaffold.py / wiki-write.py / wiki-lint.py 复用。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

# 默认类型 → 相对 vault 的目录（dsh-obsidian 默认值）
DEFAULT_TYPE_FOLDERS = {
    "domain": "wiki/areas",
    "area": "wiki/areas",
    "project": "wiki/projects",
    "resource": "wiki/resources",
    "source": "wiki/sources",
    "archive": "wiki/archive",
}

# 机器页：是索引/热缓存/日志，由系统管理，不作为内容页、不可被覆盖/改名/删除
MACHINERY_BASENAMES = frozenset({"index", "hot", "log", "readme"})
MACHINERY_PREFIX = "lint report"

# 文件名安全（Windows 保留设备名 + 非法字符 + 尾随空格点）
RESERVED_DEVICE = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])$", re.IGNORECASE)
BAD_CHARS = re.compile(r'[:<>"|?*\\]')
BAD_TAIL = re.compile(r"[ .]+$")

_FM_RE = re.compile(r"\A---\r?\n([\s\S]*?)\r?\n---\r?\n?")


def read_utf8(path: Path) -> str:
    """utf-8-sig 读取：剥 BOM，兼容 CRLF。"""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def is_machinery(name: str) -> bool:
    t = name.lower()
    return t in MACHINERY_BASENAMES or t.startswith(MACHINERY_PREFIX)


def is_portable_filename(name: str) -> bool:
    if not name:
        return False
    if RESERVED_DEVICE.match(name):
        return False
    if BAD_CHARS.search(name):
        return False
    if BAD_TAIL.search(name):
        return False
    return True


def safe_filename(title: str) -> str:
    name = re.sub(r"[\\/]", "-", title)
    name = re.sub(r'[:<>"|?*]', "", name).strip()
    return name or "untitled"


def layout(vault: Path) -> dict:
    """返回 vault 的目录/文件布局。所有值基于 vault 根，是 Path。"""
    vault = Path(vault)
    return {
        "vault": vault,
        "wiki": vault / "wiki",
        "raw": vault / ".raw",
        "meta": vault / "wiki" / "meta",
        "index": vault / "wiki" / "index.md",
        "hot": vault / "wiki" / "hot.md",
        "log": vault / "wiki" / "log.md",
        "type_folders": dict(DEFAULT_TYPE_FOLDERS),
    }


def route_folder(vault: Path, type_: str) -> Path:
    tf = DEFAULT_TYPE_FOLDERS.get(type_, DEFAULT_TYPE_FOLDERS["resource"])
    return Path(vault) / tf


def walk_md(root: Path):
    """递归列出 .md，跳过隐藏/机器/缓存目录（与 wiki-search.py 一致）。"""
    root = Path(root)
    if not root.is_dir():
        return
    skip = frozenset({"meta", "raw", ".raw", "node_modules", ".git", ".obsidian", "inbox"})
    for entry in root.rglob("*.md"):
        try:
            rel = entry.relative_to(root)
        except ValueError:
            continue
        if any(part in skip or part.startswith(".") for part in rel.parts):
            continue
        yield entry


# ────────────────────────────────────────────────────────────────────────────
# frontmatter
# ────────────────────────────────────────────────────────────────────────────
def parse_frontmatter(text: str):
    """返回 (fm, body)。fm 为 dict（列表项→list，其余→str）。无 frontmatter 返回 ({}, text)。"""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        idx = line.find(":")
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1:].strip()
        if val.startswith("[") and val.endswith("]"):
            items = val[1:-1].split(",")
            fm[key] = [x.strip().strip("\"'") for x in items if x.strip()]
        else:
            fm[key] = val.strip("\"'")
    return fm, text[m.end():]


def serialize_frontmatter(fm: dict) -> str:
    lines = ["---"]
    for k, v in fm.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            # JSON 数组即合法 YAML flow 序列
            lines.append(f"{k}: {json_dumps(list(v))}")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k}: {v}")
        elif isinstance(v, str) and (":" in v or v.startswith("[") or v.startswith("{")):
            lines.append(f'{k}: "{v.replace(chr(34), chr(92) + chr(34))}"')
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def json_dumps(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def complete_frontmatter(existing: dict, patch: dict, now: str) -> dict:
    merged = {**existing, **patch}
    if not merged.get("created"):
        merged["created"] = existing.get("created", now)
    merged["updated"] = now
    return merged


def sha256(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────────────────
# index / log 记账
# ────────────────────────────────────────────────────────────────────────────
def upsert_index_entry(index_file: Path, type_: str, section_heading: str, title: str) -> None:
    if not index_file.exists():
        index_file.write_text("# Index\n\n", encoding="utf-8")
    md = read_utf8(index_file)
    section_re = re.compile(rf"(^## {re.escape(section_heading)}\n)([\s\S]*?)(?=^## |\Z)", re.M)
    entry = f"- [[{title}]]: {type_}\n"
    m = section_re.search(md)
    if m:
        body = m.group(2)
        if f"[[{title}]]" in body:
            return  # 已存在
        new_md = md[:m.start()] + m.group(1) + body + entry + md[m.end():]
    else:
        new_md = md.rstrip("\n") + f"\n## {section_heading}\n\n{entry}"
    index_file.write_text(new_md, encoding="utf-8")


def append_log(log_file: Path, line: str) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    entry = f"- {iso} — {line}\n"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    md = read_utf8(log_file) if log_file.exists() else ""
    if not re.match(r"^# Log\s*\n", md, re.I):
        md = "# Log\n\n" + md.lstrip("\n")
    # 保证今天的小节存在（放在标题之后，最新在前）
    if not re.search(rf"^## {today}\n", md, re.M):
        md = re.sub(r"(^# Log[^\n]*\n+)", rf"\1## {today}\n", md, count=1)
    # 注意：entry 可能含 Windows 路径反斜杠（如 \Users），re.sub 的替换串会把它当转义。
    # 用函数式替换，让 entry 原样插入，避免 bad escape。
    md = re.sub(rf"(^## {today}\n)", lambda m: m.group(1) + entry, md, count=1, flags=re.M)
    log_file.write_text(md, encoding="utf-8")


def collect_unresolved_links(body: str, known_titles: set) -> list[str]:
    """返回正文里引用但尚不存在的 [[页面名]] 目标（去重）。"""
    link_re = re.compile(r"!?\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
    out = []
    seen = set()
    for m in link_re.finditer(body):
        target = m.group(1).strip()
        if target and target not in known_titles and target not in seen:
            seen.add(target)
            out.append(target)
    return out
