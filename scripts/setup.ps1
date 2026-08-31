#Requires -Version 5.1
<#
setup.ps1 — 把 nb-skills 仓库里的自研 skills 安装到任意 coding agent 的 skill 目录。
Windows 原生 PowerShell 版，功能等价于 scripts/setup.sh（Unix/macOS 用 bash 那个）。

安装机制：coding agent 会扫描一个「skill 根目录」下的每个 <name>/SKILL.md 作为可发现 skill。
不同 agent 的 skill 根目录不同（见下方 Get-AgentDir 映射表），所以「安装」=
把本仓库 skills/<name>/ 链接（符号链接/目录联接）或拷贝进目标 agent 的 skill 根目录。

用法：
  .\setup.ps1                              # 交互式：选 agent、勾选 skill、选 link/copy
  .\setup.ps1 --agent dsh                  # 只装到 DSH（~\.agents\skills）
  .\setup.ps1 --agent claude --link        # 装到 Claude Code，用符号链接
  .\setup.ps1 --dir ~\custom --skill coding-publish-skill
  .\setup.ps1 --all --copy --yes           # 全装、拷贝、非交互（无 TTY 时用）
  .\setup.ps1 --dry-run                    # 只打印将执行的动作，不真正写入

链接兼容性：Windows 上「符号链接」需要管理员权限或开发者模式；本脚本会先尝试
符号链接，失败则自动用「目录联接（Junction，无需提权）」，再失败才降级为拷贝。
#>

$ErrorActionPreference = 'Stop'

# 脚本自身所在目录（与当前目录无关，避免 cd 后失效）
$script:SCRIPT_DIR = $PSScriptRoot
$script:REPO_ROOT  = Split-Path -Parent $PSScriptRoot
$script:SKILLS_SRC = Join-Path $script:REPO_ROOT 'skills'

# 用户主目录（.agents/skills 等都以它打底）
$script:HomePath = $HOME
if ([string]::IsNullOrWhiteSpace($script:HomePath)) { $script:HomePath = $env:USERPROFILE }

# 已知 agent 的 skill 根目录映射（Windows：%USERPROFILE% 下）
$script:AgentNames = @('dsh', 'claude', 'codex', 'gemini', 'opencode', 'cursor')

function Get-AgentDir([string]$name) {
  $map = @{
    dsh      = (Join-Path $script:HomePath '.agents\skills')
    claude   = (Join-Path $script:HomePath '.claude\skills')
    codex    = (Join-Path $script:HomePath '.codex\skills')
    gemini   = (Join-Path $script:HomePath '.gemini\skills')
    opencode = (Join-Path $script:HomePath '.config\opencode\skills')
    cursor   = (Join-Path $script:HomePath '.cursor\skills')
  }
  if ($map.ContainsKey($name)) { return $map[$name] }
  return $null
}

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
function Write-Say([string]$m)  { Write-Host ("[setup] {0}" -f $m) -ForegroundColor Cyan }
function Write-Warn([string]$m) { [Console]::Error.WriteLine('[警告] ' + $m) }
function Write-Err([string]$m)  { [Console]::Error.WriteLine('[错误] ' + $m); exit 1 }

function Expand-HomePath([string]$p) {
  if ([string]::IsNullOrWhiteSpace($p)) { return $p }
  if ($p -eq '~') { return $script:HomePath }
  if ($p.StartsWith('~/') -or $p.StartsWith('~\')) { return Join-Path $script:HomePath $p.Substring(2) }
  return $p
}

function Read-Ask([string]$prompt, [string]$default = '') {
  if ($default) { $r = Read-Host ("{0} [{1}]" -f $prompt, $default) }
  else { $r = Read-Host $prompt }
  if ([string]::IsNullOrWhiteSpace($r) -and $default) { return $default }
  return $r
}

function Confirm-YN([string]$prompt, [bool]$defaultYes = $false) {
  if ([Console]::IsInputRedirected) { return $script:ASSUME_YES }
  $r = Read-Host $prompt
  if ([string]::IsNullOrWhiteSpace($r)) { return $defaultYes }
  return $r -match '^(y|yes)$'
}

function Show-Usage {
  @'
用法：
  .\setup.ps1                              # 交互式：选 agent、勾选 skill、选 link/copy
  .\setup.ps1 --agent dsh                  # 只装到 DSH（~\.agents\skills）
  .\setup.ps1 --agent claude --link        # 装到 Claude Code，用符号链接
  .\setup.ps1 --dir ~\custom --skill coding-publish-skill
  .\setup.ps1 --all --copy --yes           # 全装、拷贝、非交互（无 TTY 时用）
  .\setup.ps1 --dry-run                    # 只打印将执行的动作，不真正写入

选项：
  --agent <名>   目标 agent（见下方可用列表）
  --dir <目录>   直接指定 skill 根目录（优先级高于 --agent；不支持 ~ 的可用 $HOME）
  --skill <名>   只装指定 skill（可多次；不指定则装全部）
  --all          跳过勾选，安装全部 skill
  --link         用符号链接/目录联接安装（默认，更新仓库即生效）
  --copy         用拷贝安装
  --dry-run      只打印动作，不实际写入
  --yes / -y     非交互自动确认（创建目录等）

'@ | Write-Host
  Write-Host ("可用 --agent: {0}" -f ($script:AgentNames -join ' '))
}

# ---------------------------------------------------------------------------
# 命令行选项
# ---------------------------------------------------------------------------
$TARGET_AGENT = $null        # --agent 指定的 agent 名
$TARGET_DIR   = $null        # --dir 直接指定目录（优先级高于 --agent）
$MODE         = $null        # link | copy
$SELECT_ALL   = $false       # --all：跳过勾选，装全部
$DECLARED_SKILLS = @()       # --skill 可多次指定，过滤 skill
$DRY_RUN      = $false
$ASSUME_YES   = $false
$script:ASSUME_YES = $false

for ($i = 0; $i -lt $args.Count; $i++) {
  $a = $args[$i]
  switch ($a) {
    '--agent'   { $TARGET_AGENT = $args[++$i] }
    '--dir'     { $TARGET_DIR   = $args[++$i] }
    '--skill'   { $DECLARED_SKILLS += $args[++$i] }
    '--all'     { $SELECT_ALL = $true }
    '--link'    { $MODE = 'link' }
    '--copy'    { $MODE = 'copy' }
    '--dry-run' { $DRY_RUN = $true }
    '-y'        { $ASSUME_YES = $true }
    '--yes'     { $ASSUME_YES = $true }
    '--help'    { Show-Usage; exit 0 }
    '-h'        { Show-Usage; exit 0 }
    default     { Write-Err ("未知参数: {0}" -f $a); Show-Usage; exit 2 }
  }
}
$script:ASSUME_YES = $ASSUME_YES

# ---------------------------------------------------------------------------
# 枚举本仓库的 skills（<name>/SKILL.md）
# ---------------------------------------------------------------------------
$SKILLS = @(Get-ChildItem -Path $script:SKILLS_SRC -Directory -ErrorAction SilentlyContinue |
  Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') -PathType Leaf } |
  ForEach-Object { $_.FullName })

if ($SKILLS.Count -eq 0) {
  Write-Err ("在 {0} 未发现任何 skill（每个 skill 需有 <name>/SKILL.md）。" -f $script:SKILLS_SRC)
}

# 应用 --skill 过滤
if ($DECLARED_SKILLS.Count -gt 0) {
  $FILTERED = @()
  foreach ($d in $SKILLS) {
    $name = Split-Path -Leaf $d
    if ($DECLARED_SKILLS -contains $name) { $FILTERED += $d }
  }
  if ($FILTERED.Count -eq 0) {
    Write-Err ("没有匹配到 --skill 指定的 skill: {0}" -f ($DECLARED_SKILLS -join ' '))
  }
  $SKILLS = $FILTERED
}

# ---------------------------------------------------------------------------
# 1. Explore：选定目标 agent / 目录
# ---------------------------------------------------------------------------
Write-Say '探测目标 agent 的 skill 根目录…'

if ($TARGET_DIR) {
  # 已通过 --dir 指定
} elseif ($TARGET_AGENT) {
  $__d = Get-AgentDir $TARGET_AGENT
  if (-not $__d) {
    Write-Err ("未知 agent: {0}（可选: {1}）" -f $TARGET_AGENT, ($script:AgentNames -join ' '))
  }
  $TARGET_DIR = Expand-HomePath $__d
} elseif (-not [Console]::IsInputRedirected) {
  # 交互：列出可选 agent
  Write-Say '可选目标 agent 的 skill 目录:'
  $found = @()
  $i = 1
  foreach ($name in $script:AgentNames) {
    $p = Get-AgentDir $name
    $mark = ''
    if (Test-Path $p -PathType Container) { $mark = '  [已存在]' }
    Write-Host ("   {0,2}) {1,-10}{2}{3}" -f $i, $name, $p, $mark)
    $found += $name
    $i++
  }
  Write-Host ("   {0,2}) {1}" -f $i, '自定义目录')
  $sel = Read-Ask '选择目标 agent（输入序号）' '1'
  $num = 0
  if ([int]::TryParse($sel, [ref]$num)) {
    if ($num -ge 1 -and $num -le $found.Count) {
      $TARGET_AGENT = $found[$num - 1]
      $TARGET_DIR = Expand-HomePath (Get-AgentDir $TARGET_AGENT)
    } elseif ($num -eq $i) {
      $TARGET_DIR = Read-Ask '输入自定义 skill 根目录' ''
      if (-not $TARGET_DIR) { Write-Err '未输入目录。' }
      $TARGET_DIR = Expand-HomePath $TARGET_DIR
    } else {
      Write-Err ("无效选择: {0}" -f $sel)
    }
  } else {
    Write-Err ("无效选择: {0}" -f $sel)
  }
} else {
  # 非交互且未指定 --agent/--dir：默认 DSH
  Write-Say '非交互且未指定 --agent/--dir，默认使用 DSH 目录。'
  $TARGET_AGENT = 'dsh'
  $TARGET_DIR = Expand-HomePath (Get-AgentDir 'dsh')
}

Write-Say ("目标目录: {0}" -f $TARGET_DIR)

# 目录不存在时：确认创建（dry-run 直接模拟）
if (-not (Test-Path $TARGET_DIR -PathType Container)) {
  Write-Warn ("目标目录不存在: {0}" -f $TARGET_DIR)
  if ($DRY_RUN) {
    Write-Say ("（dry-run 模拟）将创建: {0}" -f $TARGET_DIR)
  } elseif (Confirm-YN '是否创建它？[Y/n]' $true) {
    New-Item -ItemType Directory -Path $TARGET_DIR -Force | Out-Null
    Write-Say ("已创建: {0}" -f $TARGET_DIR)
  } else {
    Write-Err '未创建目录，退出。可用 --dir 指定其它已存在目录。'
  }
}

# ---------------------------------------------------------------------------
# 2. Confirm：勾选要安装的 skills
# ---------------------------------------------------------------------------
$SELECTED = @()   # 存放选中的 skill 源路径
if ($SELECT_ALL -or $DECLARED_SKILLS.Count -gt 0) {
  $SELECTED = @($SKILLS)
} elseif (-not [Console]::IsInputRedirected) {
  Write-Say '勾选要安装的 skills（输入序号，多个用空格分隔；直接回车=全选）:'
  $idx = 1
  foreach ($d in $SKILLS) {
    Write-Host ("   {0,2}) {1}" -f $idx, (Split-Path -Leaf $d))
    $idx++
  }
  $choice = Read-Host '选择（回车=全部）'
  if ([string]::IsNullOrWhiteSpace($choice)) {
    $SELECTED = @($SKILLS)
  } else {
    foreach ($t in ($choice -split '\s+')) {
      if ($t) {
        $n = 0
        if (([int]::TryParse($t, [ref]$n)) -and $n -ge 1 -and $n -le $SKILLS.Count) {
          $SELECTED += $SKILLS[$n - 1]
        } else {
          Write-Warn ("忽略无效序号: {0}" -f $t)
        }
      }
    }
    if ($SELECTED.Count -eq 0) { Write-Err '未选中任何 skill。' }
  }
} else {
  # 非交互、未 --all/--skill：默认全装
  $SELECTED = @($SKILLS)
}

# ---------------------------------------------------------------------------
# 3. Confirm：安装方式 link / copy
# ---------------------------------------------------------------------------
if (-not $MODE) {
  if (-not [Console]::IsInputRedirected) {
    $MODE = Read-Ask '安装方式（link=默认/软链接，copy=拷贝快照）' 'link'
  } else {
    $MODE = 'link'
  }
  if ($MODE -notin @('link', 'copy')) {
    Write-Err ("只能选 link 或 copy，得到: {0}" -f $MODE)
  }
}

Write-Say ("将安装 {0} 个 skill（方式: {1}）：" -f $SELECTED.Count, $MODE)
foreach ($d in $SELECTED) { Write-Host ("   - {0}" -f (Split-Path -Leaf $d)) }
if ($DRY_RUN) { Write-Say '（dry-run 模式，只打印不写入）' }

# ---------------------------------------------------------------------------
# 4. Write：执行
# ---------------------------------------------------------------------------
$installed = 0; $skipped = 0; $failed = 0
$FAILED_NAMES = @()

foreach ($src in $SELECTED) {
  $name = Split-Path -Leaf $src
  $dst = Join-Path $TARGET_DIR $name

  if (Test-Path $dst -PathType Any) {
    Write-Say ("跳过（已存在）: {0}" -f $name)
    $skipped++
    continue
  }

  if ($DRY_RUN) {
    Write-Say ("将安装: {0} -> {1}" -f $name, $dst)
    $installed++
    continue
  }

  $ok = $false
  $mechanism = $MODE
  if ($MODE -eq 'link') {
    try {
      New-Item -ItemType SymbolicLink -Path $dst -Target $src -ErrorAction Stop | Out-Null
      $ok = $true; $mechanism = 'link'
    } catch {
      try {
        New-Item -ItemType Junction -Path $dst -Target $src -ErrorAction Stop | Out-Null
        $ok = $true; $mechanism = 'junction'
      } catch {
        Copy-Item -Path $src -Destination $dst -Recurse -Force -ErrorAction Stop
        $ok = $true; $mechanism = 'copy-fallback'
      }
    }
  } else {
    try {
      Copy-Item -Path $src -Destination $dst -Recurse -Force -ErrorAction Stop
      $ok = $true; $mechanism = 'copy'
    } catch { $ok = $false }
  }

  if ($ok) {
    switch ($mechanism) {
      'link'         { Write-Say ("已链接: {0}" -f $name) }
      'junction'     { Write-Say ("已用目录联接链接: {0}" -f $name) }
      'copy-fallback'{ Write-Warn ("链接/联接失败，已降级为拷贝: {0}" -f $name); Write-Say ("已拷贝: {0}" -f $name) }
      default        { Write-Say ("已拷贝: {0}" -f $name) }
    }
    $installed++
  } else {
    Write-Warn ("安装失败: {0}" -f $name)
    $failed++
    $FAILED_NAMES += $name
  }
}

# ---------------------------------------------------------------------------
# 5. Done：汇总
# ---------------------------------------------------------------------------
Write-Say ''
Write-Say ("完成。已安装 {0}，跳过 {1}，失败 {2}。" -f $installed, $skipped, $failed)

if ($TARGET_AGENT -eq 'dsh' -or $TARGET_DIR -match 'agents[/\\]skills') {
  Write-Host ''
  Write-Host '提示（DSH）：'
  Write-Host '  · DSH 会在下次扫描 skill 目录时自动发现这些 skill（通常在下次对话前生效）。'
  Write-Host '  · 想让某个 skill 不可见：在 DSH 设置里禁用对应目录/技能。'
  Write-Host '  · 卸载：Remove-Item ~\.agents\skills\<name>（链接模式删软链/联接，拷贝模式删目录）。'
}

if ($failed -gt 0) {
  Write-Warn ("失败项: {0}" -f ($FAILED_NAMES -join ' '))
}
if ($DRY_RUN) {
  Write-Warn '这是 dry-run，未实际写入。去掉 --dry-run 重新执行即可真正安装。'
}
