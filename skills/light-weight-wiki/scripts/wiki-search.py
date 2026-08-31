#!/usr/bin/env python3
"""wiki-search.py — 轻量 BM25 + 链接图 检索，针对「一个 Markdown 知识库文件夹」。

特性
----
- 纯 Python 3 标准库，零第三方依赖，跨平台（Windows / macOS / Linux）。
- 对**整页** markdown 建 BM25 倒排索引（不做 chunk、不做 .vault-meta、不加锁），
  因此可以在任意一个 .md 文件夹上直接运行。
- 分词用 NFKC 归一 + 按 script 拆分 + CJK 1/2/3 元词，兼顾中文/日文/韩文与英文。
- 同时抽取 [[wikilink]] 与 markdown [..](..md) 链接，构建入链/出链图，
  供 Agent 沿链接展开、定位孤岛页。

用法（命令行）
------------
  python3 wiki-search.py <wiki_dir> "查询" [--top 10] [--no-links] [--include-machinery]
  python3 wiki-search.py <wiki_dir> --list
  python3 wiki-search.py <wiki_dir> --quick        # 读序用：吐出 index.md + hot.md + log.md

输出（JSON 到 stdout；默认不整页带回，只给 snippet，避免灌爆上下文）
------------
  { "query": "...", "file_count": N,
    "hits": [ { "title":"..", "path":"..", "score":1.234,
                "snippet":"..", "inbound":[...], "outbound":[...] } ] }

机器页（默认跳过，与被借鉴的 LLM-Wiki 惯例一致）：index / hot / log / readme / "Lint Report*"。
用 --include-machinery 把它们也纳入索引。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────────
# 常量
# ────────────────────────────────────────────────────────────────────────────
K1 = 1.5
B = 0.75
SNIPPET_RADIUS = 80
MAX_DOC_TERMS = 20000  # 单页 token 上限，防 CJK 元词爆炸

# 机器页：默认不进入索引
MACHINERY_BASENAMES = frozenset({"index", "hot", "log", "readme"})
MACHINERY_PREFIX = "lint report"

# 索引时跳过的目录（隐藏目录 + 常见机器/缓存目录）
SKIP_DIR_NAMES = frozenset({"meta", "raw", ".raw", "node_modules", ".git", ".obsidian", "inbox"})

# 英文常见停用词（保守、偏召回）
STOPWORDS = frozenset(
    "a an and are as at be by for from has have he her him his i if in is it its "
    "of on or that the their them they this to was were will with you your".split()
)

# CJK 区间（中日韩统一表意文字 + 假名 + 注音 + 谚文等）
CJK_RANGES = (
    (0x1100, 0x11FF), (0x3040, 0x309F), (0x30A0, 0x30FF), (0x3100, 0x312F),
    (0x3130, 0x318F), (0x31A0, 0x31BF), (0x31F0, 0x31FF), (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF), (0xA960, 0xA97F), (0xAC00, 0xD7AF), (0xF900, 0xFAFF),
    (0xFF66, 0xFF9F), (0x20000, 0x2FA1F), (0x30000, 0x323AF),
)
CJK_NGRAM_SIZES = (1, 2, 3)

# 分词：字母/数字/下划线开头的词（Python 的 \w 默认按 Unicode 匹配，含中日韩字母），
# 内部保留连字符/撇号/下划线（如 "user's"、"well-formed"、"search_term"）。
TOKEN_RE = re.compile(r"[\w][\w'\-]*", re.UNICODE)

# 链接：
#  [[目标]] / [[目标|别名]] / [[目标#标题]] / ![[嵌入]]
WIKILINK_RE = re.compile(r"!?\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
#  [文字](相对路径.md) 或 [文字](./路径.md#标题)
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)(?:#[^)]*)?\)", re.IGNORECASE)
# YAML frontmatter（兼容 CRLF 行结尾；BOM 在读取时用 utf-8-sig 剥掉）
_FM_RE = re.compile(r"\A---\r?\n([\s\S]*?)\r?\n---\r?\n?")


# ────────────────────────────────────────────────────────────────────────────
# 工具
# ────────────────────────────────────────────────────────────────────────────
def is_machinery(title: str) -> bool:
    t = title.lower()
    return t in MACHINERY_BASENAMES or t.startswith(MACHINERY_PREFIX)


def walk_md(root: Path):
    """递归列出 root 下的 .md，跳过隐藏/机器/缓存目录。"""
    if not root.is_dir():
        return
    for entry in root.rglob("*.md"):
        try:
            rel = entry.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIR_NAMES or part.startswith(".") for part in rel.parts):
            continue
        yield entry


def strip_frontmatter(text: str) -> str:
    m = _FM_RE.match(text)
    return text[m.end():] if m else text


def fm_title(text: str) -> str:
    m = _FM_RE.match(text)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in CJK_RANGES)


def _script_runs(token: str):
    """把一个词按 CJK / 非-CJK 切成若干段，产出 (substr, is_cjk)。"""
    if not token:
        return
    start = 0
    cur = _is_cjk(token[0])
    for pos, ch in enumerate(token[1:], start=1):
        cjk = _is_cjk(ch)
        if cjk != cur:
            yield token[start:pos], cur
            start = pos
            cur = cjk
    yield token[start:], cur


def tokenize(text: str) -> list[str]:
    """NFKC 归一化后分词：CJK 段发 1/2/3 元词，其它段按词下发、小写、过滤停用词。"""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKC", text)
    terms: list[str] = []
    for m in TOKEN_RE.finditer(normalized):
        word = m.group(0)
        for sub, cjk in _script_runs(word):
            if cjk:
                n = len(sub)
                for size in CJK_NGRAM_SIZES:
                    if n >= size:
                        for off in range(n - size + 1):
                            terms.append(sub[off:off + size])
            else:
                sub = sub.strip("'_-")
                if len(sub) > 1 and sub.lower() not in STOPWORDS:
                    terms.append(sub.lower())
    return terms


def _link_name(target: str) -> str:
    """把链接目标归一成可匹配的页面标题（去掉目录前缀 / 扩展名 / 锚点）。"""
    name = target.replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith(".md"):
        name = name[:-3]
    name = name.split("#", 1)[0].split("|", 1)[0].strip()
    return name


def extract_links(body: str) -> set[str]:
    """抽取一页的出链目标（去重，返回标题名）。"""
    links: set[str] = set()
    for m in WIKILINK_RE.finditer(body):
        t = m.group(1).strip()
        if t:
            links.add(_link_name(t))
    for m in MDLINK_RE.finditer(body):
        t = m.group(1).strip()
        if t:
            links.add(_link_name(t))
    return links


def _snippet(body: str, qterms: list[str], radius: int = SNIPPET_RADIUS) -> str:
    lower = body.lower()
    best = -1
    for t in qterms:
        i = lower.find(t)
        if i >= 0 and (best < 0 or i < best):
            best = i
    if best < 0:
        return collapse_ws(body[:radius * 2])
    start = max(0, best - radius)
    end = min(len(body), best + radius)
    snip = collapse_ws(body[start:end])
    if start > 0:
        snip = "…" + snip
    if end < len(body):
        snip += "…"
    return snip


# ────────────────────────────────────────────────────────────────────────────
# 索引与检索
# ────────────────────────────────────────────────────────────────────────────
def build_index(wiki_dir: Path, include_machinery: bool = False) -> dict:
    docs: list[dict] = []
    df: dict[str, int] = defaultdict(int)
    total_len = 0
    titles: set[str] = set()
    title_by_lower: dict[str, str] = {}

    for path in walk_md(wiki_dir):
        title = path.stem
        if not include_machinery and is_machinery(title):
            continue
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        body = strip_frontmatter(raw)
        fm_t = fm_title(raw)
        # 标题并入索引文本，否则「标题匹配但正文无该词」的页召回不到
        tokens = tokenize(f"{title} {fm_t} {body}".strip())[:MAX_DOC_TERMS]
        outbound = extract_links(body)
        docs.append({
            "title": title, "path": str(path), "tokens": tokens,
            "body": body, "outbound": outbound,
        })
        titles.add(title)
        title_by_lower.setdefault(title.lower(), title)
        total_len += len(tokens)
        seen: set[str] = set()
        for t in tokens:
            if t in seen:
                continue
            seen.add(t)
            df[t] += 1

    inbound: dict[str, set[str]] = defaultdict(set)
    for d in docs:
        for t in d["outbound"]:
            target = title_by_lower.get(t.lower())
            if target and target != d["title"]:
                inbound[target].add(d["title"])

    avgdl = (total_len / len(docs)) if docs else 0.0
    return {
        "docs": docs, "df": dict(df), "avgdl": avgdl,
        "doc_count": len(docs), "titles": titles, "inbound": dict(inbound),
    }


def bm25_score(qterms: list[str], doc: dict, idx: dict) -> float:
    N = idx["doc_count"] or 1
    dl = len(doc["tokens"])
    tf: dict[str, int] = defaultdict(int)
    for t in doc["tokens"]:
        tf[t] += 1
    score = 0.0
    for q in qterms:
        f = tf.get(q, 0)
        if not f:
            continue
        n = idx["df"].get(q, 0)
        idf = math.log(1 + (N - n + 0.5) / (n + 0.5))
        norm = f * (K1 + 1) / (f + K1 * (1 - B + B * dl / max(1.0, idx["avgdl"])))
        score += idf * norm
    return score


def search(wiki_dir: Path, query: str, top: int = 10,
           no_links: bool = False, include_machinery: bool = False) -> dict:
    idx = build_index(wiki_dir, include_machinery)
    qterms = list(dict.fromkeys(tokenize(query)))  # 去重保序
    if not qterms:
        return {"query": query, "file_count": idx["doc_count"], "hits": []}
    scored = [(bm25_score(qterms, d, idx), d) for d in idx["docs"]]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    hits = []
    for s, d in scored[:top]:
        hit = {
            "title": d["title"],
            "path": d["path"],
            "score": round(s, 4),
            "snippet": _snippet(d["body"], qterms),
        }
        if not no_links:
            hit["inbound"] = sorted(idx["inbound"].get(d["title"], set()))
            hit["outbound"] = sorted(d["outbound"])
        hits.append(hit)
    return {"query": query, "file_count": idx["doc_count"], "hits": hits}


# ────────────────────────────────────────────────────────────────────────────
# 命令行
# ────────────────────────────────────────────────────────────────────────────
def _find_machinery(root: Path, name: str):
    for cand in (root / f"{name}.md", root / "wiki" / f"{name}.md"):
        if cand.is_file():
            return cand
    return None


def cmd_quick(root: Path) -> int:
    out = {}
    for name in ("index", "hot", "log"):
        p = _find_machinery(root, name)
        if p:
            out[name] = p.read_text(encoding="utf-8-sig", errors="replace")
    print(json.dumps({"quick": out}, ensure_ascii=False, indent=2))
    return 0


def cmd_list(root: Path, include_machinery: bool = False) -> int:
    titles = [p.stem for p in walk_md(root)
              if include_machinery or not is_machinery(p.stem)]
    titles.sort()
    print(json.dumps({"titles": titles, "count": len(titles)},
                     ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    # 强制 UTF-8 输出：避免 Windows 上按系统码页(如 GBK)写 stdout，导致
    # 下游 agent 按 UTF-8 解析 JSON 时中文乱码。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(
        description="Light-weight BM25 + link-graph search over a markdown wiki folder.")
    p.add_argument("wiki_dir", help="markdown wiki folder")
    p.add_argument("query", nargs="?", help="search text")
    p.add_argument("--top", type=int, default=10, help="max results (default 10)")
    p.add_argument("--no-links", action="store_true", help="skip inbound/outbound")
    p.add_argument("--include-machinery", action="store_true",
                   help="also index index/hot/log/readme/Lint Report pages")
    p.add_argument("--list", action="store_true", help="list page titles")
    p.add_argument("--quick", action="store_true",
                   help="echo index.md + hot.md + log.md (read-order orientation)")
    args = p.parse_args(argv)

    root = Path(args.wiki_dir)
    if not root.is_dir():
        print(json.dumps({"error": f"wiki_dir is not a directory: {root}"},
                         ensure_ascii=False), file=sys.stderr)
        return 2

    if args.quick:
        return cmd_quick(root)
    if args.list:
        return cmd_list(root, args.include_machinery)
    if not args.query:
        p.error("query required unless --list/--quick")

    result = search(root, args.query, args.top, args.no_links, args.include_machinery)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
