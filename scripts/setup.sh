#!/usr/bin/env bash
#
# setup.sh — 把 nb-skills 仓库里的自研 skills 安装到任意 coding agent 的 skill 目录。
#
# 思路参考 mattpocock/skills 的 `/setup-matt-pocock-skills`：
#   explore（探测装了哪些 agent、有哪些 skill）→ 交互确认（装到哪个 agent、勾选哪些 skill）
#   → write（用 symlink 或 copy 落盘）。
#
# 安装机制：coding agent 会扫描一个「skill 根目录」下的每个 <name>/SKILL.md 作为可发现 skill。
#   不同 agent 的 skill 根目录不同（本脚本内置了一张映射表，见 AGENT_NAMES/AGENT_DIRS 数组），
#   所以「安装」= 把本仓库 skills/<name>/ 链接/拷贝进目标 agent 的 skill 根目录。
#
# 用法：
#   ./setup.sh                              # 交互式：选 agent、勾选 skill、选 link/copy
#   ./setup.sh --agent dsh                   # 只装到 DSH（~/.agents/skills）
#   ./setup.sh --agent claude --link         # 装到 Claude Code，用 symlink
#   ./setup.sh --dir ~/custom --skill coding-publish-skill
#   ./setup.sh --all --copy --yes            # 全装、拷贝、非交互（无 TTY 时用）
#   ./setup.sh --dry-run                     # 只打印将执行的动作，不真正写入
#
# 解释器守卫：本脚本是 bash 专用（用了 [[ ]]、数组 += 等 bash 特性）。
# 用 `sh setup.sh` 会以 POSIX sh 运行；请用 `bash setup.sh` 或 `./setup.sh`。
if [ -z "${BASH_VERSION:-}" ]; then
  echo "错误：本脚本需用 bash 运行（当前不是 bash）。请改用: bash $0 或 ./$0" >&2
  exit 1
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SKILLS_SRC="${REPO_ROOT}/skills"

# ---------------------------------------------------------------------------
# 已知 agent 的 skill 根目录映射（两列平行数组，兼容 bash 3.2，不能用关联数组）
# ---------------------------------------------------------------------------
AGENT_NAMES=( dsh claude codex gemini opencode cursor )
AGENT_DIRS=(
  "~/.agents/skills"
  "~/.claude/skills"
  "~/.codex/skills"
  "~/.gemini/skills"
  "~/.config/opencode/skills"
  "~/.cursor/skills"
)

# agent 名 -> 目录（供 --agent 使用）
agent_dir_of() {
  local name="$1" i
  for i in "${!AGENT_NAMES[@]}"; do
    [[ "${AGENT_NAMES[$i]}" == "$name" ]] && { printf '%s' "${AGENT_DIRS[$i]}"; return 0; }
  done
  return 1
}

# ---------------------------------------------------------------------------
# 命令行选项
# ---------------------------------------------------------------------------
TARGET_AGENT=""        # --agent 指定的 agent 名
TARGET_DIR=""          # --dir 直接指定目录（优先级高于 --agent）
MODE=""                # link | copy
SELECT_ALL=false       # --all：跳过勾选，装全部
DECLARED_SKILLS=()     # --skill 可多次指定，过滤 skill
DRY_RUN=false
ASSUME_YES=false       # --yes：非交互自动确认（创建目录、勾选默认）

usage() {
  cat <<'HELP'
用法：
  ./setup.sh                              # 交互式：选 agent、勾选 skill、选 link/copy
  ./setup.sh --agent dsh                   # 只装到 DSH（~/.agents/skills）
  ./setup.sh --agent claude --link         # 装到 Claude Code，用 symlink
  ./setup.sh --dir ~/custom --skill coding-publish-skill
  ./setup.sh --all --copy --yes            # 全装、拷贝、非交互（无 TTY 时用）
  ./setup.sh --dry-run                     # 只打印将执行的动作，不真正写入

选项：
  --agent <名>   目标 agent（见下方可用列表）
  --dir <目录>   直接指定 skill 根目录（优先级高于 --agent）
  --skill <名>   只装指定 skill（可多次；不指定则报全部）
  --all          跳过勾选，安装全部 skill
  --link         用软链接安装（默认，更新仓库即生效）
  --copy         用拷贝安装
  --dry-run      只打印动作，不实际写入
  --yes / -y     非交互自动确认（创建目录等）
HELP
  echo "可用 --agent: ${AGENT_NAMES[*]}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)  TARGET_AGENT="$2"; shift 2 ;;
    --dir)    TARGET_DIR="$2"; shift 2 ;;
    --skill)  DECLARED_SKILLS+=("$2"); shift 2 ;;
    --all)    SELECT_ALL=true; shift ;;
    --link)   MODE="link"; shift ;;
    --copy)   MODE="copy"; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --yes|-y) ASSUME_YES=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
say()  { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[警告]\033[0m  %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[错误]\033[0m  %s\n' "$*" >&2; exit 1; }

expand_home() { printf '%s' "$1" | sed "s|^~/|$HOME/|"; }

ask() { # ask "提示" "默认值" -> 结果写入 REPLY
  # 不用 read -p（POSIX sh 下 -p 不可靠），改 printf 提示 + read，兼容 sh/bash
  local prompt="$1" def="$2" __prompt
  if [[ -n "$def" ]]; then
    __prompt="$(printf '\033[1;36m[setup]\033[0m %s [%s] ' "$prompt" "$def")"
  else
    __prompt="$(printf '\033[1;36m[setup]\033[0m %s ' "$prompt")"
  fi
  printf '%s' "$__prompt"
  IFS= read -r REPLY
  if [[ -z "$REPLY" && -n "$def" ]]; then REPLY="$def"; fi
}

confirm_yn() { # confirm_yn "提示" [default_no] -> 0=yes；无 TTY 时按 ASSUME_YES 决定
  local prompt="$1" default="${2:-no}" __prompt r
  if ! [[ -t 0 ]]; then
    [[ "$ASSUME_YES" == true ]] && return 0 || return 1
  fi
  __prompt="$(printf '\033[1;36m[setup]\033[0m %s ' "$prompt")"
  printf '%s' "$__prompt"
  IFS= read -r r
  if [[ -z "$r" ]]; then r="$default"; fi
  [[ "$r" == "y" || "$r" == "Y" || "$r" == "yes" || "$r" == "YES" ]]
}

# ---------------------------------------------------------------------------
# 枚举本仓库的 skills
# ---------------------------------------------------------------------------
SKILLS=()
_tmp_skills="$(mktemp)"
find "$SKILLS_SRC" -mindepth 2 -maxdepth 2 -name SKILL.md -exec dirname {} \; 2>/dev/null | sort > "$_tmp_skills"
while IFS= read -r d; do SKILLS+=("$d"); done < "$_tmp_skills"
rm -f "$_tmp_skills"
[[ ${#SKILLS[@]} -gt 0 ]] || err "在 $SKILLS_SRC 未发现任何 skill（每个 skill 需有 <name>/SKILL.md）。"

# 应用 --skill 过滤
if [[ ${#DECLARED_SKILLS[@]} -gt 0 ]]; then
  FILTERED=()
  for d in "${SKILLS[@]}"; do
    for want in "${DECLARED_SKILLS[@]}"; do
      [[ "$(basename "$d")" == "$want" ]] && FILTERED+=("$d")
    done
  done
  [[ ${#FILTERED[@]} -gt 0 ]] || err "没有匹配到 --skill 指定的 skill: ${DECLARED_SKILLS[*]}"
  SKILLS=("${FILTERED[@]}")
fi

# ---------------------------------------------------------------------------
# 1. Explore：选定目标 agent / 目录
# ---------------------------------------------------------------------------
say "探测目标 agent 的 skill 根目录…"

if [[ -n "$TARGET_DIR" ]]; then
  : # 已通过 --dir 指定

elif [[ -n "$TARGET_AGENT" ]]; then
  __d="$(agent_dir_of "$TARGET_AGENT")" || err "未知 agent: ${TARGET_AGENT}（可选: ${AGENT_NAMES[*]}）"
  TARGET_DIR="$(expand_home "$__d")"

elif [[ -t 0 ]]; then
  # 交互：列出已探测到存在的 + 全部可选 agent
  say "可选目标 agent 的 skill 目录:"
  found=(); i=1
  for name in "${AGENT_NAMES[@]}"; do
    p="$(expand_home "$(agent_dir_of "$name")")"
    printf '   %2d) %-10s %s%s\n' "$i" "$name" "$p" \
      "$([[ -d "$p" ]] && echo '  [已存在]' || echo '')"
    found+=("$name"); i=$((i+1))
  done
  printf '   %2d) %s\n' "$i" "自定义目录"
  ask "选择目标 agent（输入序号）" "1"
  sel="$REPLY"
  if [[ "$sel" -ge 1 && "$sel" -le ${#found[@]} ]] 2>/dev/null; then
    TARGET_AGENT="${found[$((sel-1))]}"
    TARGET_DIR="$(expand_home "$(agent_dir_of "$TARGET_AGENT")")"
  elif [[ "$sel" == "$i" ]] 2>/dev/null; then
    ask "输入自定义 skill 根目录" ""
    TARGET_DIR="$REPLY"
    [[ -n "$TARGET_DIR" ]] || err "未输入目录。"
  else
    err "无效选择: $sel"
  fi

else
  # 非交互且未指定 --agent/--dir：默认 DSH
  say "非交互且未指定 --agent/--dir，默认使用 DSH 目录。"
  TARGET_AGENT="dsh"
  TARGET_DIR="$(expand_home "$(agent_dir_of dsh)")"
fi

say "目标目录: $TARGET_DIR"

# 目录不存在时：确认创建（dry-run 直接模拟）
if [[ ! -d "$TARGET_DIR" ]]; then
  warn "目标目录不存在: $TARGET_DIR"
  if $DRY_RUN; then
    say "（dry-run 模拟）将创建: $TARGET_DIR"
  elif confirm_yn "是否创建它？[y/N]"; then
    mkdir -p "$TARGET_DIR"
    say "已创建: $TARGET_DIR"
  else
    err "未创建目录，退出。可用 --dir 指定其它已存在目录。"
  fi
fi

# ---------------------------------------------------------------------------
# 2. Confirm：勾选要安装的 skills
# ---------------------------------------------------------------------------
SELECTED=()   # 存放选中的 skill 源路径
if $SELECT_ALL || [[ ${#DECLARED_SKILLS[@]} -gt 0 ]]; then
  SELECTED=("${SKILLS[@]}")
elif [[ -t 0 ]]; then
  say "勾选要安装的 skills（输入序号，多个用空格分隔；直接回车=全选）:"
  idx=1
  for d in "${SKILLS[@]}"; do
    printf '   %2d) %s\n' "$idx" "$(basename "$d")"
    idx=$((idx+1))
  done
  printf '\033[1;36m[setup]\033[0m 选择（回车=全部）: '
  IFS= read -r choice
  if [[ -z "$choice" ]]; then
    SELECTED=("${SKILLS[@]}")
  else
    for t in $choice; do
      if [[ "$t" -ge 1 && "$t" -le ${#SKILLS[@]} ]] 2>/dev/null; then
        SELECTED+=("${SKILLS[$((t-1))]}")
      else
        warn "忽略无效序号: $t"
      fi
    done
    [[ ${#SELECTED[@]} -gt 0 ]] || err "未选中任何 skill。"
  fi
else
  # 非交互、未 --all/--skill：默认全装
  SELECTED=("${SKILLS[@]}")
fi

# ---------------------------------------------------------------------------
# 3. Confirm：安装方式 link / copy
# ---------------------------------------------------------------------------
if [[ -z "$MODE" ]]; then
  if [[ -t 0 ]]; then
    ask "安装方式（link=推荐/软链接，copy=拷贝快照）" "link"
    MODE="$REPLY"
  else
    MODE="link"
  fi
  [[ "$MODE" == "link" || "$MODE" == "copy" ]] || err "只能选 link 或 copy，得到: $MODE"
fi

say "将安装 ${#SELECTED[@]} 个 skill（方式: ${MODE}）："
for d in "${SELECTED[@]}"; do printf '   - %s\n' "$(basename "$d")"; done
$DRY_RUN && say "（dry-run 模式，只打印不写入）"

# ---------------------------------------------------------------------------
# 4. Write：执行
# ---------------------------------------------------------------------------
installed=0; skipped=0; failed=0
FAILED_NAMES=()

for src in "${SELECTED[@]}"; do
  name="$(basename "$src")"
  dst="${TARGET_DIR}/${name}"

  if [[ -e "$dst" || -L "$dst" ]]; then
    say "跳过（已存在）: $name"
    skipped=$((skipped+1)); continue
  fi

  if $DRY_RUN; then
    say "将安装: $name -> $dst"
    installed=$((installed+1)); continue
  fi

  if [[ "$MODE" == "link" ]]; then
    if ln -s "$src" "$dst"; then
      say "已链接: $name"; installed=$((installed+1))
    else
      warn "链接失败: $name"; failed=$((failed+1)); FAILED_NAMES+=("$name")
    fi
  else
    if cp -R "$src" "$dst"; then
      say "已拷贝: $name"; installed=$((installed+1))
    else
      warn "拷贝失败: $name"; failed=$((failed+1)); FAILED_NAMES+=("$name")
    fi
  fi
done

# ---------------------------------------------------------------------------
# 5. Done：汇总
# ---------------------------------------------------------------------------
say ""
say "完成。已安装 ${installed}，跳过 ${skipped}，失败 ${failed}。"

if [[ "${TARGET_AGENT:-dsh}" == "dsh" || "$TARGET_DIR" == *"/agents/skills" ]]; then
  cat <<'EOF'
提示（DSH）：
  · DSH 会在下次扫描 skill 目录时自动发现这些 skill（通常在下次对话前生效）。
  · 想让某个 skill 不可见：在 DSH 设置里禁用对应目录/技能。
  · 卸载：rm ~/.agents/skills/<name>（链接模式删软链，拷贝模式删目录）。
EOF
fi

if [[ $failed -gt 0 ]]; then
  warn "失败项: ${FAILED_NAMES[*]}"
fi
if $DRY_RUN; then
  warn "这是 dry-run，未实际写入。去掉 --dry-run 重新执行即可真正安装。"
fi
