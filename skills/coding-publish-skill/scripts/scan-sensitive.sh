#!/usr/bin/env bash
# scan-sensitive.sh — coding-publish-skill 的敏感内容门禁（零第三方依赖，兼容 macOS bash 3.2）
#
#   bash scripts/scan-sensitive.sh          # 扫描「本次将被提交的内容」
#   bash scripts/scan-sensitive.sh --help
#
# 退出码：0 = 硬门禁通过（可能仍有需人工过目的清单，已打印）
#         1 = 命中硬门禁 —— 先按 references/sensitive-content.md §3 判定：确属占位符/假数据
#             就记录结论继续；真实机密则停手并轮换
#         2 = 用法或环境错误（例如不在 git 仓库里）
#
# 硬门禁（不可带着命中项提交）：令牌/私钥形状、被追踪的真实密钥文件、.gitignore 未覆盖。
#   硬门禁只放机器能判定的东西；`password: xxx`、`postgres://u:p@h` 这类占位符与真值
#   长得一样的模式一律走人工过目，否则模板文件和示例配置会被硬拦，逼出「绕过门禁」的习惯。
# 需人工过目（不影响退出码）：凭据模式、.env.* 模板、已追踪但应忽略的文件、待提交文件清单。
# 覆盖 references/sensitive-content.md §2 的 git 侧检查；§2.6 的 npm tarball 核对与
# 「已推送到公网的机密要轮换」由 agent 判断，不在本脚本内。
#
# 维护约定（改这个文件前先读）：
#   * 正则必须是单行字面量。单引号里的 `\` + 换行是字面量，git 会 fatal
#     `trailing backslash` 退出 128；再配上 2>/dev/null，门禁会静默变成「零命中」。
#   * `git grep -E` 走 POSIX ERE，`\s` 是字面量字母 s（`password\s*:` 匹配不上
#     `password: `）。查空白一律写 [[:space:]]。
#   * git grep 默认只搜已追踪文件的工作区版本，看不见未追踪的新 .env；所以先
#     `git add -A`，再用 --cached 扫索引——扫描范围才等于提交范围。
#   * 不排除锁文件。实测真实 lock 文件对本脚本两个模式都是零命中，而 registry URL
#     里嵌 token 的情况正藏在锁文件里，排除掉就是白送一个盲区。
#   * 多字节字符不要紧跟在 $var 后面（bash 3.2 会把它吃进变量名），一律写 ${var}。

set -u

HARD_PATTERN='(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|LTAI[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{36}|gh[ous]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk[_-][A-Za-z0-9_-]{24,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)'
REVIEW_PATTERN='((password|passwd|secret|token|api[_-]?key)[[:space:]]*[:=][[:space:]]*[^[:space:]]+|(postgres|postgresql|mysql|redis|mongodb|amqp)://[^[:space:]]*:[^[:space:]]*@)'
KEYFILE_PATTERN='(^|/)(\.env|.*\.(pem|key|p12|pfx)|id_rsa|id_ed25519)$'
TEMPLATE_PATTERN='(^|/)\.env\.[^/]+$'
GITIGNORE_PATTERN='\.env|\.pem|\.key|\.p12'

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  '') ;;
  *) echo "未知参数：$1（用 --help）" >&2; exit 2 ;;
esac

root=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "错误：当前目录不在 git 仓库里" >&2; exit 2
}
cd "$root" || exit 2

echo "== 敏感内容门禁 · $(basename "$root") =="
echo "仓库：$root"

git add -A 2>&1 || { echo "错误：git add -A 失败" >&2; exit 2; }
staged=$(git diff --cached --name-only | grep -c . || true)
echo "扫描范围：索引中 ${staged} 个文件（= 本次将被提交的内容；被 .gitignore 排除的本地 .env 不会进这里，也就进不了提交）"
echo

blocked=0
review=0

echo "[硬门禁 1] 高置信令牌特征（云 key / 令牌 / 私钥头）"
out=$(git grep -n -I --cached -E "$HARD_PATTERN" -- . 2>&1); rc=$?
case $rc in
  0) printf '%s\n' "$out" | sed 's/^/    /'
     echo "    → 命中，阻塞"
     blocked=$((blocked + 1)) ;;
  1) echo "    零命中" ;;
  *) printf '%s\n' "$out" | sed 's/^/    /'
     echo "    → 扫描本身失败（git grep 退出码 ${rc}），不得当作零命中"
     blocked=$((blocked + 1)) ;;
esac
echo

echo "[硬门禁 2] 被追踪（含本次新增）的真实密钥文件"
out=$(git ls-files | grep -E "$KEYFILE_PATTERN" || true)
if [ -n "$out" ]; then
  printf '%s\n' "$out" | sed 's/^/    /'
  echo "    → 命中，阻塞（先 git rm --cached，见 references/sensitive-content.md §3）"
  blocked=$((blocked + 1))
else
  echo "    无"
fi
echo

echo "[硬门禁 3] .gitignore 覆盖 .env / 密钥文件"
if [ ! -f .gitignore ]; then
  echo "    没有 .gitignore → 阻塞（补上 .env / *.pem / *.key 后再继续）"
  blocked=$((blocked + 1))
elif grep -qE "$GITIGNORE_PATTERN" .gitignore; then
  echo "    已覆盖"
else
  echo "    .gitignore 未覆盖 .env / 密钥文件 → 阻塞（补上后再继续）"
  blocked=$((blocked + 1))
fi
echo

echo "[需人工过目 1] 凭据模式（字段赋值、带密码连接串——占位符与真值长得一样，必须逐条判断）"
if out=$(git grep -n -I --cached -E "$REVIEW_PATTERN" -- . 2>&1); then rc=0; else rc=$?; fi
case $rc in
  0) printf '%s\n' "$out" | sed 's/^/    /'
     review=$((review + 1)) ;;
  1) echo "    无" ;;
  *) printf '%s\n' "$out" | sed 's/^/    /'
     echo "    → 扫描失败（退出码 ${rc}），人工确认这一项有没有跑成" ;;
esac
echo

echo "[需人工过目 2] .env.* 模板文件（可提交，但要确认里面是占位符而不是真值）"
out=$(git ls-files | grep -E "$TEMPLATE_PATTERN" || true)
if [ -n "$out" ]; then
  printf '%s\n' "$out" | sed 's/^/    /'
  review=$((review + 1))
else
  echo "    无"
fi
echo

echo "[需人工过目 3] 已被追踪但现在应该忽略的文件"
out=$(git ls-files -ci --exclude-standard 2>/dev/null || true)
if [ -n "$out" ]; then
  printf '%s\n' "$out" | sed 's/^/    /'
  review=$((review + 1))
else
  echo "    无"
fi
echo

echo "[需人工过目 4] 本次将提交的文件清单（每个都要能说清「为什么可以公开」）"
git diff --cached --stat | sed 's/^/    /'
echo

if [ "$blocked" -gt 0 ]; then
  echo "结论：硬门禁命中 ${blocked} 项 —— 先按 references/sensitive-content.md §3 判定：占位符/假数据则记录结论后继续，真实机密则停手并轮换"
  exit 1
fi
if [ "$review" -gt 0 ]; then
  echo "结论：硬门禁通过；另有 ${review} 项需人工过目（逐条确认后写进最终报告）"
  exit 0
fi
echo "结论：硬门禁通过，且没有需要人工过目的清单"
exit 0
