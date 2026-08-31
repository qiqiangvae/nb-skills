#!/usr/bin/env python3
"""wiki_lib.py — light-weight-wiki 的共享机械层（记账/安全/工具）。

零第三方依赖。实现 dsh-obsidian `vault.js` 的核心记账逻辑：
frontmatter 解析/补全/序列化、文件名安全、类型路由、index/log 记账、sha256 去重。
被 wiki-scaffold.py / wiki-write.py / wiki-lint.py 复用。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────────
# 配置：vaultPath 的持久化（对齐原版 config.vaultPath / config.typeFolders，
# 但不绑定 DSH，用跨 agent 通用的「环境变量 + JSON 配置文件」机制）。
#
# 解析优先级（vault 路径）：
#   1. 命令行显式传入的 vault 参数（最高）
#   2. 环境变量 LIGHTWEIGHT_WIKI_VAULT
#   3. JSON 配置文件 <config_dir>/light-weight-wiki/config.json 的 `vaultPath`
#
# JSON 配置文件同时承载 typeFolders：
#   { "vaultPath": "/abs/path/to/vault", "typeFolders": { "project": "wiki/projects" } }
# ────────────────────────────────────────────────────────────────────────────
CONFIG_ENV_VAR = "LIGHTWEIGHT_WIKI_VAULT"


def _config_dir() -> Path:
    """配置文件目录：$XDG_CONFIG_HOME/light-weight-wiki，否则 ~/.config/light-weight-wiki。"""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "light-weight-wiki"


def config_path() -> Path:
    return _config_dir() / "config.json"


def load_config() -> dict:
    """读取 JSON 配置文件；不存在或损坏返回空 dict（静默，不抛错）。"""
    p = config_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(cfg: dict) -> Path:
    """把配置写回 config.json（用于 `light-weight-wiki-config` 命令）。"""
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def resolve_vault_path(explicit: str | Path | None = None) -> Path | None:
    """按优先级解析 vault 路径：命令行 > 环境变量 > 配置文件。都无则返回 None。"""
    if explicit:
        return Path(explicit)
    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        return Path(env)
    cfg = load_config()
    vp = cfg.get("vaultPath")
    return Path(vp) if vp else None


def resolve_type_folders(explicit: dict | None = None) -> dict | None:
    """解析 typeFolders：命令行显式 > 配置文件。都无则 None（用默认值）。"""
    if explicit:
        return explicit
    ts = load_config().get("typeFolders")
    return ts if isinstance(ts, dict) else None


def ensure_vault_path(explicit: str | Path | None = None, *,
                      interactive: bool | None = None,
                      require_wiki: bool = True) -> Path | None:
    """解析 vault 路径；全部来源缺失时，若有 TTY 则主动询问用户并写入配置。

    优先级：命令行 > 环境变量 > 配置文件 > 交互询问（仅 TTY）> None。
    - interactive：None=自动检测 stdin 是否 TTY；True/False 强制。
    - require_wiki：校验时是否要求 `wiki/` 子目录已存在（写/查/检需要，scaffold 不需要）。
    询问命中且校验通过后，把 vaultPath 写回 config.json。
    """
    v = resolve_vault_path(explicit)
    if v is not None:
        return v

    tty = (interactive if interactive is not None
           else (sys.stdin.isatty() if sys.stdin else False))
    if not tty:
        return None

    # 主动询问，循环直到给到可接受路径或用户放弃
    while True:
        try:
            ans = input("light-weight-wiki 未配置 vault 路径。请粘贴你知识库(vault)的绝对路径: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            return None
        if not ans:
            print("（未输入，跳过配置）", file=sys.stderr)
            return None
        p = Path(ans).expanduser()
        if not p.is_dir():
            print(f"  目录不存在: {p}", file=sys.stderr)
            yn = _ask_yn("仍要使用这个路径吗（scaffold 可新建）？")
            if not yn:
                continue
        if require_wiki and not (p / "wiki").is_dir():
            print(f"  该路径下没有 wiki/ 子目录（{p / 'wiki'}）。", file=sys.stderr)
            yn = _ask_yn("是尚未 scaffold 的新库吗？仍要使用该路径吗？")
            if not yn:
                continue
        # 校验通过，写入配置
        cfg = load_config()
        cfg["vaultPath"] = str(p.resolve())
        save_config(cfg)
        print(f"  已写入配置: {config_path()}", file=sys.stderr)
        return p.resolve()


def _ask_yn(prompt: str) -> bool:
    try:
        r = input(f"  {prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return r in ("y", "yes")


# 默认类型 → 相对 vault 的目录（dsh-obsidian 默认值，含机器页 index/log/hot）
DEFAULT_TYPE_FOLDERS = {
    "domain": "wiki/areas",
    "area": "wiki/areas",
    "project": "wiki/projects",
    "resource": "wiki/resources",
    "source": "wiki/sources",
    "archive": "wiki/archive",
    "index": "wiki",
    "log": "wiki",
    "hot": "wiki",
}

# 机器页：是索引/热缓存/日志，由系统管理，不作为内容页、不可被覆盖/改名/删除
MACHINERY_BASENAMES = frozenset({"index", "hot", "log", "readme"})
MACHINERY_PREFIX = "lint report"

# 分区索引页（Obsidian repository 模式）：每分区一个 `_index.md`，是导航索引而非内容页。
# 内容页判定、lint 死链/孤儿、删页/改名引用扫描都要跳过它。
INDEX_BASENAME = "_index"

# type → 目录复数（对齐 Obsidian repository 约定：目录名 = type 的复数）。
# 覆盖既有 Obsidian vault 实际出现过的全部 type；未知 type 走 "wiki/{type}" + 规整复数。
TYPE_PLURALS = {
    "area": "areas",
    "archive": "archive",
    "comparison": "comparisons",
    "component": "components",
    "concept": "concepts",
    "decision": "decisions",
    "dependency": "dependencies",
    "domain": "domains",
    "entity": "entities",
    "flow": "flows",
    "module": "modules",
    "project": "projects",
    "question": "questions",
    "resource": "resources",
    "runbook": "runbooks",
    "source": "sources",
    "standard": "standards",
    "synthesis": "syntheses",
    "known-issue": "known-issues",
    "meta": "meta",
}

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


def is_index_page(name: str) -> bool:
    """是否为分区索引页（Obsidian repository 模式的 `_index.md`）。"""
    return name.lower() == INDEX_BASENAME


def pluralize_type(type_: str) -> str:
    """返回 type 的目录复数名（用于路由到 wiki/<复数>）。"""
    t = type_.strip().lower()
    if t in TYPE_PLURALS:
        return TYPE_PLURALS[t]
    # 未知 type：规整复数（s/x/z/ch/sh 加 es，y 变 ies，其余加 s）
    if t.endswith(("s", "x", "z", "ch", "sh")):
        return t + "es"
    if t.endswith("y") and len(t) > 1 and t[-2] not in "aeiou":
        return t[:-1] + "ies"
    return t + "s"


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


def is_repository_vault(vault: Path) -> bool:
    """检测 vault 是否为 Obsidian repository 模式。

    判据：`wiki/` 下存在「5 个 generic 扁平目录之外」的、带 `_index.md` 的分区目录，
    或根 `index.md` 不是脚本预置的 `# Index` 分节模板（而是 Obsidian 导航）。
    """
    wiki = vault / "wiki"
    if not wiki.is_dir():
        return False
    generic = {"areas", "projects", "resources", "sources", "archive"}
    for d in wiki.iterdir():
        if not d.is_dir():
            continue
        if d.name in generic:
            continue
        if (d / "_index.md").is_file():
            return True
    # 兜底：根 index.md 若由脚本生成会是 `# Index\n\n## Areas` 结构；
    # 出现 Obsidian 导航标题（如 `# Wiki Index` / `## AI Coding`）也判为 repository。
    idx = wiki / "index.md"
    if idx.is_file():
        head = read_utf8(idx)[:200]
        if "# index" not in head.lower():
            return True
    return False


def layout(vault: Path, type_folders: dict | None = None) -> dict:
    """返回 vault 的目录/文件布局。所有值基于 vault 根，是 Path。

    type_folders：可选，覆盖 DEFAULT_TYPE_FOLDERS（对齐 dsh-obsidian 的
    config.typeFolders 合并逻辑——非 generic 模式（repository/sitemap/…）的自定义路由）。
    """
    vault = Path(vault)
    merged = {**DEFAULT_TYPE_FOLDERS, **(type_folders or {})}
    return {
        "vault": vault,
        "wiki": vault / "wiki",
        "raw": vault / ".raw",
        "meta": vault / "wiki" / "meta",
        "index": vault / "wiki" / "index.md",
        "hot": vault / "wiki" / "hot.md",
        "log": vault / "wiki" / "log.md",
        "type_folders": merged,
    }


def route_folder(vault: Path, type_: str, type_folders: dict | None = None) -> Path:
    """返回 type 对应页面的落点目录（相对 vault 的 Path）。

    优先级：显式 type_folders 覆盖 > type 复数推导（默认 `wiki/<type复数>`）。
    后者对齐 Obsidian repository 约定（目录名 = type 复数），因此不再局限于 6 类型白名单。
    """
    if type_folders and type_ in type_folders:
        return Path(vault) / type_folders[type_]
    return Path(vault) / "wiki" / pluralize_type(type_)


def walk_md(root: Path, include_index: bool = False):
    """递归列出 .md，跳过隐藏/机器/缓存目录。

    include_index=False（默认）：跳过分区索引页 `_index.md`——它们不是内容页，
    用于 lint 死链/孤儿判定、删页/改名引用扫描等内容页场景。
    include_index=True：含 `_index.md`（索引/全量列举时用）。
    """
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
        if not include_index and is_index_page(entry.stem):
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
def upsert_index_entry(index_file: Path, type_: str, section_heading: str, title: str,
                       style: str = ":") -> None:
    if not index_file.exists():
        index_file.write_text("# Index\n\n", encoding="utf-8")
    md = read_utf8(index_file)
    # 分节标题大小写不敏感匹配：库里的 ## Projects 能被 section_heading="projects" 命中，
    # 避免往末尾追加重复的小写分节。
    section_re = re.compile(
        rf"(^## {re.escape(section_heading)}\n)([\s\S]*?)(?=^## |\Z)",
        re.M | re.IGNORECASE)
    sep = " — " if style == "—" else ": "
    entry = f"- [[{title}]]{sep}{type_}\n"
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


_WIKILINK_NAME_RE = re.compile(r"!?\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")


def _replace_wikilink_targets(text: str, old_title: str, new_title: str) -> tuple[str, int]:
    """把文本中所有 [[旧名]]、[[旧名|alias]]、[[旧名#sec]] 的目标名替换为新名。

    返回 (新文本, 替换次数)。仅替换目标名完全等于 old_title 的链接，不影响其它页面。
    Embed ![[旧名]] 同样处理。
    """
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        full = m.group(0)
        target = m.group(1)
        # 剩余部分：可能是 |alias 或 #section 或空
        rest = full[len(m.group(0)) - len(m.group(0)):]  # placeholder, replaced below
        count += 1
        return full.replace(target, new_title, 1)

    # 更稳妥：直接重建
    out = []
    last = 0
    count = 0
    for m in _WIKILINK_NAME_RE.finditer(text):
        target = m.group(1)
        # 目标名去掉前后空格后精确等于 old_title 才替换
        if target.strip() == old_title:
            # 保留 target 的前后空格位置，仅把中间内容换成 new_title
            lead = target[:len(target) - len(target.lstrip())]
            trail = target[len(target.rstrip()):]
            start, end = m.span(1)
            out.append(text[last:start])
            out.append(lead + new_title + trail)
            last = end
            count += 1
    out.append(text[last:])
    return "".join(out), count


def _sync_links_after_rename(vault: Path, old_title: str, new_title: str) -> list[str]:
    """扫描全库 .md（含 index/log），把 [[旧名]] 替换为 [[新名]]，返回被改的文件列表。"""
    changed = []
    wiki_dir = vault / "wiki"
    if not wiki_dir.is_dir():
        return changed
    for md in walk_md(wiki_dir):
        raw = read_utf8(md)
        new_raw, n = _replace_wikilink_targets(raw, old_title, new_title)
        if n > 0:
            md.write_text(new_raw, encoding="utf-8")
            changed.append(str(md))
    return changed


def _remove_wikilink_targets(text: str, title: str) -> tuple[str, int]:
    """把文本中引用 title 的 wikilink 移除，返回 (新文本, 移除处数)。

    三种形态：
    - [[title]]                       → 删除（就地留空）
    - [[title|alias]]、[[title#sec]]  → 删除整条（连同 alias/锚点，不保留残留文本）
    - 独立行 "- [[title]]... "（index/log 的条目行）→ 整行删除，避免留下 "- : xxx"
    其它行内出现时只删除链接本身。
    """
    # 整行条目：行首（允许缩进/列表符）到行尾仅是一条指向 title 的链接行
    line_re = re.compile(rf"^[ \t]*-\s*!?\[\[\s*{re.escape(title)}\s*(\|[^\]]*)?(?:#[^\]]*)?\]\][^\n]*\n?",
                         re.M)
    text, n_line = line_re.subn("", text)

    inline_re = re.compile(
        rf"!?\[\[\s*{re.escape(title)}\s*(?:\|[^\]]*)?(?:#[^\]]*)?\]\]")
    text, n_inline = inline_re.subn("", text)
    return text, n_line + n_inline


def _sync_links_after_delete(vault: Path, title: str) -> list[str]:
    """扫描全库 .md，移除对被删页的 [[引用]]，返回被改文件列表。

    覆盖 index/hot 与各类型页正文（导航与正文必须留有效链接）；跳过 log.md——
    log 是审计轨迹，历史创建记录里指向已删页的链接属于正常的历史引用，不应被改写。
    """
    changed = []
    wiki_dir = vault / "wiki"
    if not wiki_dir.is_dir():
        return changed
    for md in walk_md(wiki_dir):
        if md.name.lower() == "log.md":
            continue
        raw = read_utf8(md)
        new_raw, n = _remove_wikilink_targets(raw, title)
        if n > 0:
            md.write_text(new_raw, encoding="utf-8")
            changed.append(str(md))
    return changed


def _find_page(vault: Path, title: str) -> Path | None:
    """按标题全库定位一个内容页（跳过机器页与 _index），返回 Path 或 None。

    repository 模式页面可落在任意分区目录（concepts/decisions/entities/…），
    因此不按 6 类型遍历，而是 walk_md 全库匹配文件名（safe_filename(title).md）。
    """
    name = safe_filename(title)
    wiki_dir = vault / "wiki"
    if not wiki_dir.is_dir():
        return None
    for md in walk_md(wiki_dir):
        if md.stem == name:
            return md
    return None


def rename_page(vault: Path, old_title: str, new_title: str,
                type_folders: dict | None = None, sync_refs: bool = True) -> dict:
    """重命名一页（镜像 dsh-obsidian 的 renamePage + wiki_rename tool）。

    拒绝机器页（index/hot/log/readme/Lint Report*），拒绝非可移植文件名。
    全库定位旧页（repository 模式任意分区目录），改为新文件名。
    sync_refs=True（默认）时，同步全库正文与 index 里的 [[旧名]] → [[新名]] 引用。
    """
    old_name = safe_filename(old_title)
    new_name = safe_filename(new_title)
    if is_machinery(old_name) or is_machinery(new_name):
        raise ValueError("refusing to rename machinery page")
    if not is_portable_filename(new_name):
        raise ValueError(f"non-portable filename: {new_name}")
    src = _find_page(vault, old_title)
    if src is None:
        raise FileNotFoundError(f"not found: {old_title}")
    dst = src.with_name(f"{new_name}.md")
    if dst.exists():
        raise FileExistsError(f"target exists: {dst}")

    src.rename(dst)

    result: dict = {"from": str(src), "to": str(dst)}
    if sync_refs and old_title != new_title:
        synced = _sync_links_after_rename(vault, old_title, new_title)
        result["syncedLinks"] = synced
    return result


def delete_page(vault: Path, title: str, type_folders: dict | None = None) -> dict:
    """删除一页（镜像 dsh-obsidian deletePage）。拒绝机器页。

    全库定位页面（repository 模式任意分区目录）并删除，随后同步清理全库
    （含 index/hot 与各类型页正文）对该页的 [[引用]]，并追加 log 记账，
    避免留下指向已删页的死链（原实现只 unlink、不清理引用）。
    """
    name = safe_filename(title)
    if is_machinery(name):
        raise ValueError("refusing to delete machinery page")
    p = _find_page(vault, title)
    if p is None:
        raise FileNotFoundError(f"not found: {title}")
    p.unlink()
    synced = _sync_links_after_delete(vault, name)
    append_log(layout(vault, type_folders)["log"], f"deleted [[{name}]]")
    result = {"deleted": str(p)}
    if synced:
        result["syncedLinks"] = synced
    return result
