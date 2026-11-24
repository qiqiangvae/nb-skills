#!/usr/bin/env python3
"""体检一个 skill 目录，只报告机器能判定的部分。

用法: python3 lint_skill.py <skill-dir> [--test]
退出码: 0 无硬问题；1 有硬问题；2 用法错误

硬问题（退出码 1）：SKILL.md 缺失、frontmatter 缺 name/description、name 与目录名不符、
指向 skill 内不存在文件的引用、references/ 下存在没人引用的文件、
疑似密钥、脚本语法错误、危险操作（递归删除、改写远端/历史、提权、管道执行外部代码、命令注入面）。
提示（不影响退出码）：超长入口、重复句、指向 skill 之外的链接、写死的个人路径、
改用户仓库状态的命令、没人引用的脚本、编写过程残渣、空话弱指令。
指针 = Markdown 链接 + 反引号里的相对路径；反引号里的裸文件名和 ~/$ 开头的环境路径不算指针。
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
CODE_PATH = re.compile(r"`([^`\n]*?\.(?:md|py|sh|json|ya?ml))`")
PLACEHOLDER = re.compile(r"[<>*{}$]|^(?i:url|link|path|href)$|^\.+$")

NAME_LINE = re.compile(r"^name:\s*(\S+)", re.M)
DESC_LINE = re.compile(r"^description:\s*(.*)$", re.M)
HINTS = [
    ("编写过程残渣", re.compile(r"(我们(决定|当初|曾经|讨论|对比)|曾考虑|之前考虑|对比过|对比了|最终选|原方案|已废弃|上一版|按你的要求|如你所说|TODO|待定|暂定|后续再说)")),
    ("空话/弱指令", re.compile(r"(务必|高质量|好好|注意质量)")),
]
LIST_MARKER = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
TABLE_RULE = re.compile(r"^\|?[\s:|-]+\|?$")
LONG_ENTRY = 220

CODE_SUFFIX = {".py", ".sh", ".bash", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env"}
STRONG_SECRET = [
    ("私钥", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("云厂商 access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token 前缀", re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{10,})")),
]
WEAK_SECRET = re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|private[_-]?key)\b\s*[:=]\s*[\'\"]([^\'\"\s]{8,})[\'\"]")
NOT_SECRET = re.compile(r"[<>{}$]|(?i:your|xxx|example|redacted|placeholder|change_?me|test|dummy|fake|mock|sample|demo)|\.\.\.")
HOME_PATH = re.compile(r"(?<![\w.~$/])(?:/(?:Users|home)/[A-Za-z0-9._-]+|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+)")


DANGEROUS = [
    ("递归删除", re.compile(r"\brm\s+-[a-zA-Z]*(?:rf|fr)[a-zA-Z]*\b|\bfind\b[^\n|]*-delete\b"), "error"),
    ("Python 递归删除", re.compile(r"shutil\.rmtree\b"), "hint"),
    ("改写远端或历史", re.compile(r"\bgit\s+push\b[^\n]*--force|\bgit\s+reset\s+--hard\b|\bgit\s+clean\s+-[a-zA-Z]*[xdf]|\bgit\s+branch\s+-D\b|\bnpm\s+unpublish\b|\bgh\s+release\s+delete\b"), "error"),
    ("云端或系统销毁", re.compile(r"\bkubectl\s+delete\b|\bterraform\s+(?:destroy|apply\s+-auto-approve)|\baws\s+s3\s+rm[^\n]*--recursive|\bdocker\s+(?:rm|rmi)\s+-f\b|\bDROP\s+(?:TABLE|DATABASE)\b", re.I), "error"),
    ("管道执行外部代码", re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:ba|z|k)?sh\b|\beval\b[^\n]*\$\(\s*curl"), "error"),
    ("提权或系统改动", re.compile(r"\bsudo\b|\bchmod\s+777\b|(?:^|[;&|]\s*)(?:/sbin/)?(?:shutdown|reboot|halt|poweroff|mkfs)\b|\bdd\s+if=|\bgit\s+config\s+--global\b"), "error"),
    ("命令注入面", re.compile(r"shell\s*=\s*True|\bos\.system\(|subprocess\.(?:call|run|Popen)\(\s*[f\"']"), "error"),
]
SIDE_EFFECT = re.compile(r"\bgit\s+add\s+-A\b|\bgit\s+checkout\s+--\s|\bgit\s+stash\b")


def inside_string(line, pos):
    """命中位置是否落在引号里：引号里的危险命令是数据（黑名单、示例），不是要执行的操作。"""
    for m in re.finditer(r""""[^"]*"|'[^']*'""", line):
        if m.start() < pos < m.end():
            return True
    return False


def scan_scripts(directory, described_scripts, linked):
    """扫脚本：密钥、语法、写死的个人路径、没人引用的脚本。"""
    errors, hints = [], []
    for f in sorted(directory.rglob("*")):
        if not f.is_file() or f.suffix not in CODE_SUFFIX | {".md"}:
            continue
        if f.resolve() == Path(__file__).resolve():
            continue  # 扫描器不扫自己：自检 fixture 里就有假的密钥和假路径
        rel = f.relative_to(directory)
        body = read(f)
        # 文件里出现 mktemp / TemporaryDirectory 时，递归删除多半在清自己的临时目录：降为提示
        temp_ctx = re.search(r"mktemp|mkdtemp|TemporaryDirectory|TMPDIR", body) is not None
        cleanup = []
        for lineno, line in enumerate(body.splitlines(), 1):
            for label, pattern in STRONG_SECRET:
                if pattern.search(line):
                    errors.append(f"疑似{label} {rel}:{lineno}: {line.strip()[:60]}")
            if f.suffix not in CODE_SUFFIX:
                continue
            m = WEAK_SECRET.search(line)
            if m and not NOT_SECRET.search(m.group(1)):
                errors.append(f"疑似硬编码密钥 {rel}:{lineno}: {line.strip()[:60]}")
            if HOME_PATH.search(line):
                hints.append(f"写死个人路径 {rel}:{lineno}: {line.strip()[:60]}")
            for label, pattern, severity in DANGEROUS:
                m = pattern.search(line)
                if not m:
                    continue
                where = f"{rel}:{lineno}"
                snippet = line.strip()[:70]
                if inside_string(line, m.start()):
                    hints.append(f"引号里的危险命令（确认是数据不是指令，{label}） {where}: {snippet}")
                elif temp_ctx and label == "递归删除" and not re.search(r"/Users/|/home/|/etc/|/var/|/usr/", line):
                    cleanup.append(where)
                elif severity == "error":
                    errors.append(f"危险操作（{label}） {where}: {snippet}")
                else:
                    hints.append(f"危险操作（{label}，确认删的是自建目录） {where}: {snippet}")
            if not line.lstrip().startswith("#") and SIDE_EFFECT.search(line):
                hints.append(f"改用户仓库状态 {rel}:{lineno}: {line.strip()[:60]}")
        if cleanup:
            hints.append(f"递归删除 {len(cleanup)} 处（文件里有 mktemp/TemporaryDirectory，确认删的是自建临时目录）: {', '.join(cleanup[:5])}")

    scripts = directory / "scripts"
    if scripts.is_dir():
        for f in sorted(scripts.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(directory)
            if f.suffix == ".py":
                try:
                    compile(read(f), str(f), "exec")
                except SyntaxError as e:
                    errors.append(f"Python 语法错误 {rel}:{e.lineno}: {e.msg}")
            elif f.suffix in (".sh", ".bash") and shutil.which("bash"):
                proc = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
                if proc.returncode:
                    first = (proc.stderr.strip().splitlines() or ["bash -n 失败"])[0]
                    errors.append(f"Shell 语法错误 {rel}: {first[:80]}")
            if f.suffix in CODE_SUFFIX and f.name not in described_scripts and f.resolve() not in linked:
                hints.append(f"没人引用的脚本 {rel}（文档里没提到 {f.name}）")
    return errors, hints


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def in_code_span(line, pos):
    """命中的词是否被反引号包着（那是在引用这个词，不是在犯这个错）。"""
    return sum(1 for i, ch in enumerate(line) if ch == "`" and i < pos) % 2 == 1


def described(head):
    """取 frontmatter 里 description 的值，块标量（| / >）继续往下取缩进正文。"""
    m = DESC_LINE.search(head)
    if not m:
        return ""
    value = m.group(1).strip()
    if value not in ("|", ">", "|-", ">-"):
        return value
    return " ".join(ln.strip() for ln in head[m.end():].splitlines()[1:] if ln.startswith((" ", "\t")))


def check(directory):
    """返回 (errors, hints)。"""
    errors, hints = [], []
    entry = directory / "SKILL.md"
    mds = sorted(directory.rglob("*.md"))
    if not entry.is_file():
        return ["缺少 SKILL.md"], hints

    text = read(entry)
    if not text.startswith("---"):
        errors.append("SKILL.md 缺少 frontmatter")
    else:
        head = text.split("---", 2)[1]
        m = NAME_LINE.search(head)
        name = m.group(1) if m else None
        desc = described(head)
        if not name:
            errors.append("frontmatter 缺少 name")
        elif name != directory.name:
            errors.append(f"frontmatter name={name} 与目录名 {directory.name} 不符")
        if not desc:
            errors.append("frontmatter 缺少 description（模型无法发现该 skill）")

    # 指针识别：Markdown 链接 + 反引号里的相对路径（本仓库多数指针是后者）
    top_dirs = {p.name for p in directory.iterdir() if p.is_dir()}
    linked = set()
    for md in mds:
        for lineno, line in enumerate(read(md).splitlines(), 1):
            found_here = [(t, False) for t in LINK.findall(line)]
            found_here += [(t, True) for t in CODE_PATH.findall(line)]
            for target, in_code in found_here:
                rel = target.split("#")[0].strip()
                if in_code and "/" not in rel:
                    continue  # 反引号里的裸文件名多是指令或命令
                if not rel or re.match(r"([a-z]+:|/|~|\$|%)", rel, re.I):
                    continue
                if PLACEHOLDER.search(rel) or ("/" not in rel and "." not in rel):
                    continue
                found = next((c.resolve() for c in (md.parent / rel, directory / rel) if c.exists()), None)
                if found:
                    linked.add(found)
                    continue
                # 找不到时判断它是不是本该在本 skill 里：同目录的兄弟文件、
                # 或本 skill 已有的顶层目录（references/、scripts/…）下面
                sibling = "/" not in rel
                inside = rel.strip("./").split("/")[0] in top_dirs
                if sibling or inside:
                    errors.append(f"指向不存在的文件 {md.relative_to(directory)}:{lineno} -> {target}")
                elif not in_code:
                    # 链接指向 skill 之外（./src/x.md 这类），多于在描述目标环境
                    hints.append(f"指针指向 skill 之外 {md.relative_to(directory)}:{lineno} -> {target}")

    mentioned = set()
    for md in mds:
        mentioned |= set(re.findall(r"[\w.-]+\.[A-Za-z0-9]+", read(md)))

    # 没人引用的参考文件：references/ 下没有任何文件引用它
    for md in sorted((directory / "references").rglob("*.md")):
        if md.resolve() not in linked:
            errors.append(f"没人引用的参考文件 {md.relative_to(directory)}（没有任何文件引用它）")

    # 提示类
    entry_lines = text.count("\n") + 1
    if entry_lines > LONG_ENTRY:
        hints.append(f"入口 {entry_lines} 行 > {LONG_ENTRY}：先找该下沉到 references/ 的参考")

    seen = {}
    for md in mds:
        rel = md.relative_to(directory)
        for line in read(md).splitlines():
            s = LIST_MARKER.sub("", line.strip())
            if len(s) >= 25 and not s.startswith("#") and not TABLE_RULE.match(s):
                seen.setdefault(s, set()).add(str(rel))
    for s, files in seen.items():
        if len(files) > 1:
            hints.append(f"重复句（{', '.join(sorted(files))}）: {s[:60]}")

    script_errors, script_hints = scan_scripts(directory, mentioned, linked)
    errors += script_errors
    hints += script_hints

    for label, pattern in HINTS:
        for md in mds:
            for lineno, line in enumerate(read(md).splitlines(), 1):
                m = next((m for m in pattern.finditer(line) if not in_code_span(line, m.start())), None)
                if m:
                    hints.append(f"{label} {md.relative_to(directory)}:{lineno} 「{m.group(0)}」: {line.strip()[:60]}")
    return errors, hints


def report(directory):
    errors, hints = check(directory)
    for e in errors:
        print(f"ERROR {e}")
    for h in hints:
        print(f"HINT  {h}")
    print(f"--- {directory.name}: {len(errors)} 个硬问题, {len(hints)} 条提示")
    return 1 if errors else 0


def self_test():
    cases = {"good": 0, "rootrel": 0, "blockdesc": 0, "dup": 0, "envpath": 0,
             "abspath": 0, "scriptorphan": 0, "deadlink": 1, "orphan": 1, "noname": 1,
             "secret": 1, "syntax": 1, "danger": 1, "tempclean": 0}
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def make(slug, entry, extra=None):
            d = root / slug / "s"
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(entry, encoding="utf-8")
            for name, body in (extra or {}).items():
                p = d / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body, encoding="utf-8")
            return d

        make("good", "---\nname: s\ndescription: 用 A。\n---\n# t\n见 [r](references/r.md)\n",
             {"references/r.md": "# r\n"})
        make("rootrel", "---\nname: s\ndescription: 用 A。\n---\n见 [r](references/r.md)\n",
             {"references/r.md": "# r\n", "sub/x.md": "见 [r](../references/r.md)\n"})
        make("deadlink", "---\nname: s\ndescription: 用 A。\n---\n见 [r](references/none.md)\n",
             {"references/r.md": "# r\n"})
        make("orphan", "---\nname: s\ndescription: 用 A。\n---\n# t\n", {"references/r.md": "# r\n"})
        make("noname", "---\ndescription: 用 A。\n---\n# t\n")
        make("blockdesc", "---\nname: s\ndescription: >\n  用 A 处理 B，\n  也处理 C。\n---\n# t\n")
        make("envpath", "---\nname: s\ndescription: 用 A。\n---\n配置在 `~/.config/x.json`，生成 `wiki/index.md`。\n")
        make("dup", "---\nname: s\ndescription: 用 A。\n---\n- 这一条同样的说明在入口和参考文件里各写了一遍，必须一致\n",
             {"sub/x.md": "- 这一条同样的说明在入口和参考文件里各写了一遍，必须一致\n"})
        make("residue", "---\nname: s\ndescription: 用 A。\n---\n我们当初对比过两种方案，最终选了 A。\n")
        make("quoted", "---\nname: s\ndescription: 用 A。\n---\n反例词：`待定`、`TODO`。\n")
        make("secret", "---\nname: s\ndescription: 用 A。\n---\n见 `scripts/x.py`\n",
             {"scripts/x.py": 'api_key = "abcdefgh12345678"\n'})
        make("abspath", "---\nname: s\ndescription: 用 A。\n---\n见 `scripts/y.py`\n",
             {"scripts/y.py": 'BASE = "/Users/someone/work"\n'})
        make("syntax", "---\nname: s\ndescription: 用 A。\n---\n见 `scripts/z.py`\n",
             {"scripts/z.py": "def f(:\n"})
        make("scriptorphan", "---\nname: s\ndescription: 用 A。\n---\n# t\n",
             {"scripts/w.py": "print(1)\n"})
        make("danger", "---\nname: s\ndescription: 用 A。\n---\n见 `scripts/d.sh`\n",
             {"scripts/d.sh": "rm -rf /var/www/html\n"})
        make("tempclean", "---\nname: s\ndescription: 用 A。\n---\n见 `scripts/t.py`\n",
             {"scripts/t.py": "import tempfile, shutil\nd = tempfile.mkdtemp()\nshutil.rmtree(d)\n"})

        results = {slug: check(root / slug / "s")[0] for slug in cases}
        for slug, expect in cases.items():
            got = 1 if results[slug] else 0
            if got != expect:
                bad.append(f"{slug}: 期望退出码 {expect}，实际 {got}（{results[slug]}）")
        if not any("没人引用" in e for e in results["orphan"]):
            bad.append("orphan: 没报出没人引用的参考文件")
        if not any("残渣" in h for h in check(root / "residue" / "s")[1]):
            bad.append("residue: 没报出残渣")
        if not any("重复句" in h for h in check(root / "dup" / "s")[1]):
            bad.append("dup: 没报出跨文件重复的列表项")
        if any("残渣" in h for h in check(root / "quoted" / "s")[1]):
            bad.append("quoted: 反引号里引用的词被当成残渣")
        for slug, want in [("secret", "密钥"), ("syntax", "语法")]:
            if not any(want in e for e in check(root / slug / "s")[0]):
                bad.append(f"{slug}: 没报出{want}")
        if not any("危险操作" in e for e in check(root / "danger" / "s")[0]):
            bad.append("danger: 没报出危险操作")
        if any("危险操作" in e for e in check(root / "tempclean" / "s")[0]):
            bad.append("tempclean: 清理自建临时目录被当成危险操作")
        for slug, want in [("abspath", "个人路径"), ("scriptorphan", "没人引用")]:
            if not any(want in h for h in check(root / slug / "s")[1]):
                bad.append(f"{slug}: 没报出{want}")
    print("自检通过" if not bad else "自检失败:\n" + "\n".join(bad))
    return 0 if not bad else 1


def main(argv):
    if "--test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__.strip())
        return 2
    code = 0
    for arg in args:
        directory = Path(arg).expanduser().resolve()
        if not directory.is_dir():
            print(f"ERROR {arg} 不是目录")
            code = 1
            continue
        code = report(directory) or code
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
