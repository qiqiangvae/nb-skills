#!/usr/bin/env bash
# selftest.sh — coding-publish-skill 门禁脚本的最小回归检查（零依赖，直接运行）
#
#   bash scripts/selftest.sh
#
# 每个用例都锁住一个曾经真实发生过的缺陷，或者一个不该被悄悄改回去的决定：
#   1. 未追踪的新 .env   —— 旧命令用 git grep 扫，对未追踪文件完全不可见（漏报）
#   2. `password: hunter2` —— 旧正则用 \s，在 POSIX ERE 里是字面量 s，冒号后带空格就漏
#   3. 被追踪的 .env     —— 必须阻塞
#   4. 干净仓库          —— 必须放行
#   5. 锁文件里的令牌 URL —— 锁定「不排除锁文件」这个决定
#   6. 门禁脚本自身的正则写法 —— 不得再出现续行反斜杠或 \s
#   7. .gitignore 未覆盖 —— 必须阻塞
#   8. 全新仓库（无 commit）—— 必须能跑，而不是报环境错误
#   9. .env.example 占位符模板 —— 可提交，归入人工过目，不硬拦（硬拦会训练出绕过）
#  10. sk-proj- / sk_live_ 这类带连字符的 key —— 旧模式 sk-[A-Za-z0-9]{20,} 会漏
#  11. 文档里的 bash 块 —— 必须全部能被 bash 解析（曾经的 git grep 命令是语法错误）
#  12. 本 skill 自身不得含令牌字面量 —— 否则每次发布都要人工豁免自己的夹具

set -u

here=$(cd "$(dirname "$0")" && pwd)
SCAN="$here/scan-sensitive.sh"
[ -f "$SCAN" ] || { echo "找不到 $SCAN" >&2; exit 2; }

pass=0
fail=0

ok()   { pass=$((pass + 1)); echo "  ok   $1"; }
bad()  { fail=$((fail + 1)); echo "  FAIL $1"; [ $# -gt 1 ] && printf '%s\n' "$2" | sed 's/^/       /'; }

newrepo() {  # $1 = 目录
  git init -q "$1" || return 1
  git -C "$1" config user.email t@t
  git -C "$1" config user.name t
  printf '{"name":"x","version":"1.0.0"}\n' > "$1/package.json"
}

# 夹具是运行期拼出来的假 key（相邻字符串拼接）：写成字面量的话，门禁会扫到自己的测试夹具，
# 于是每次发布都要人工豁免一次——那等于训练「反正都是误报」，正是硬门禁要避免的事。
# 值本身就是字母表连排，不含任何真实凭据；拼完的形状才是被测对象。
fake_aws="AKIA""ABCDEFGHIJKLMNOP"
fake_slack="xoxb-""1234567890abcdef"
fake_gh="ghp_""ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
fake_openai="sk-proj-""abcdefghijklmnopqrstuvwxyz0123456789"
fake_stripe="sk_live_""abcdefghijklmnopqrstuvwx01"

echo "== 1/12 未追踪的新 .env 必须被拦 =="
d=$(mktemp -d); newrepo "$d"
{ printf '%s\n' "$fake_aws"; printf '%s\n' "$fake_slack"; } > "$d/.env"
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "1" ] && printf '%s' "$out" | grep -q '^    \.env:'; then ok "exit=1 且列出了 .env 的命中行"
else bad "exit=${rc}（期望 1）" "$out"; fi
rm -rf "$d"

echo "== 2/12 冒号后带空格的 password 必须进过目清单 =="
d=$(mktemp -d); newrepo "$d"
printf '.env\n' > "$d/.gitignore"
printf 'password: hunter2\n' > "$d/config.yml"
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "0" ] && printf '%s' "$out" | grep -q 'config.yml:1:password: hunter2'; then ok "exit=0 且过目清单含该行"
else bad "exit=${rc}（期望 0）或清单缺该行" "$out"; fi
rm -rf "$d"

echo "== 3/12 被追踪的 .env 必须阻塞 =="
d=$(mktemp -d); newrepo "$d"
printf 'PLACEHOLDER=1\n' > "$d/.env"
git -C "$d" add -f .env >/dev/null 2>&1
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "1" ] && printf '%s' "$out" | grep -q '硬门禁 2'; then ok "exit=1（被追踪的密钥文件）"
else bad "exit=${rc}（期望 1）" "$out"; fi
rm -rf "$d"

echo "== 4/12 干净仓库必须放行 =="
d=$(mktemp -d); newrepo "$d"
printf '.env\n*.pem\n' > "$d/.gitignore"
printf 'console.log(1)\n' > "$d/index.js"
git -C "$d" add -A >/dev/null 2>&1; git -C "$d" commit -qm init
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "0" ]; then ok "exit=0"
else bad "exit=${rc}（期望 0）" "$out"; fi
rm -rf "$d"

echo "== 5/12 锁文件里的令牌 URL 必须被拦（不许排除锁文件）=="
d=$(mktemp -d); newrepo "$d"
printf '{"lockfileVersion":3,"packages":{"x":{"resolved":"https://registry.npmjs.org/x/-/x-1.0.0.tgz?token=%s"}}}\n' "$fake_gh" > "$d/package-lock.json"
printf '.env\n' > "$d/.gitignore"
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "1" ] && printf '%s' "$out" | grep -q 'package-lock.json:1:'; then ok "exit=1 且锁文件被扫到"
else bad "exit=${rc}（期望 1）" "$out"; fi
rm -rf "$d"

echo "== 6/12 门禁脚本自身的正则写法（不得续行、不得 \\s）=="
bad_src=$(grep -vE '^[[:space:]]*#' "$SCAN" | grep -nE '\\$' || true)
if [ -n "$bad_src" ]; then bad "正文出现续行反斜杠" "$bad_src"; else ok "无续行反斜杠"; fi
bad_src=$(grep -vE '^[[:space:]]*#' "$SCAN" | grep -n '\\s' || true)
if [ -n "$bad_src" ]; then bad "正文出现 \\s（POSIX ERE 里是字面量 s）" "$bad_src"; else ok "无 \\s"; fi

echo "== 7/12 .gitignore 未覆盖必须阻塞 =="
d=$(mktemp -d); newrepo "$d"
printf 'node_modules\n' > "$d/.gitignore"
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "1" ] && printf '%s' "$out" | grep -q '硬门禁 3'; then ok "exit=1（.gitignore 未覆盖）"
else bad "exit=${rc}（期望 1）" "$out"; fi
rm -rf "$d"

echo "== 8/12 全新仓库（还没有 commit）也必须能跑 =="
d=$(mktemp -d)
git init -q "$d"; git -C "$d" config user.email t@t; git -C "$d" config user.name t
printf '.env\n' > "$d/.gitignore"; printf 'ok\n' > "$d/a.txt"
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "0" ]; then ok "exit=0（未误报环境错误）"
else bad "exit=${rc}（期望 0）" "$out"; fi
rm -rf "$d"

echo "== 9/12 .env.example 占位符模板必须归入人工过目、不硬拦 =="
d=$(mktemp -d); newrepo "$d"
printf '.env\n*.pem\n' > "$d/.gitignore"
printf 'DB_URL=postgres://user:CHANGE_ME@localhost:5432/app\nAPI_KEY=<your-key>\n' > "$d/.env.example"
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "0" ] && printf '%s' "$out" | grep -q '需人工过目 2' && printf '%s' "$out" | grep -q 'DB_URL'; then ok "exit=0（模板与占位符连接串都只进过目清单）"
else bad "exit=${rc}（期望 0）" "$out"; fi
rm -rf "$d"

echo "== 10/12 带连字符的 sk- key（sk-proj- / sk_live_）必须被拦 =="
d=$(mktemp -d); newrepo "$d"
printf '.env\n' > "$d/.gitignore"
printf 'OPENAI=%s\nSTRIPE=%s\n' "$fake_openai" "$fake_stripe" > "$d/keys.txt"
out=$(cd "$d" && bash "$SCAN" 2>&1); rc=$?
if [ "$rc" = "1" ] && [ "$(printf '%s' "$out" | grep -c 'keys.txt:')" = "2" ]; then ok "exit=1 且两个 key 都命中"
else bad "exit=${rc}（期望 1，命中 2 行）" "$out"; fi
rm -rf "$d"

echo "== 11/12 文档里的 bash 代码块必须全部能被 bash 解析 =="
docs_tmp=$(mktemp -d); docs_n=0; docs_bad=0
for md in "$here/../SKILL.md" "$here"/../references/*.md; do
  [ -f "$md" ] || continue
  inb=0; n=0
  while IFS= read -r line; do
    case "$line" in
      '```bash') inb=1; n=$((n + 1)); : > "$docs_tmp/$(basename "$md").$n.sh" ;;
      '```') inb=0 ;;
      *) if [ "$inb" = "1" ]; then printf '%s\n' "$line" >> "$docs_tmp/$(basename "$md").$n.sh"; fi ;;
    esac
  done < "$md"
done
for f in "$docs_tmp"/*.sh; do
  [ -f "$f" ] || continue
  docs_n=$((docs_n + 1))
  if ! out=$(bash -n "$f" 2>&1); then
    docs_bad=$((docs_bad + 1))
    bad "$(basename "$f") 无法解析" "$out"
  fi
done
[ "$docs_bad" -eq 0 ] && ok "$docs_n 个 bash 块全部可解析（曾经 SKILL.md 里那条 git grep 是 bash 语法错误）"
rm -rf "$docs_tmp"

echo "== 12/12 本 skill 自身不得含令牌字面量（否则每次发布都要人工豁免一次）=="
HARD_FROM_SCAN=$(grep -m1 '^HARD_PATTERN=' "$SCAN" | sed -e 's/^HARD_PATTERN=//' -e "s/^'//" -e "s/'$//")
if [ -z "$HARD_FROM_SCAN" ]; then bad "没能从 $SCAN 取出 HARD_PATTERN"
else
  hits=$(grep -rnE "$HARD_FROM_SCAN" "$here/.." || true)
  if [ -n "$hits" ]; then bad "skill 目录里出现令牌字面量" "$hits"
  else ok "无字面量令牌（夹具一律运行期拼接）"; fi
fi

echo
echo "通过 $pass 项，失败 $fail 项"
[ "$fail" -eq 0 ] || exit 1
