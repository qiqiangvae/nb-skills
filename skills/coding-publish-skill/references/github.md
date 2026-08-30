# GitHub 发布流程

本文件是 `coding-publish-skill` 的 GitHub 分支。**前置**：已完成主 `SKILL.md` 里的「公共前置」（版本号确认 + 认证预探测 + **敏感内容审查** + 公共提交打 tag）。以下从「检查/推送」开始。

> 推送前务必确认敏感内容审查（`references/sensitive-content.md`）已通过——这是不可跳过的门禁。

目标交付物：提交 + annotated tag + GitHub Release。三者都要逐项核验。

---

## 1. 发布前检查与提交

这些公共动作在主 `SKILL.md`「公共前置 C」完成，此处仅核验：

```bash
git status --short          # 应为空
git log --oneline --decorate -5
git remote -v
git show-ref --heads --tags
```

**完成标准**：`git status --short` 无输出，目标提交含正确版本号，已有 annotated tag。

---

## 2. 创建或检查远程仓库

必要时通过 GitHub 工具或网页创建空仓库。不要索取或接收密码、PAT 或 SSH 私钥。

若远程仓库已通过 README 初始化，先拉取并合并两段历史：

```bash
git fetch origin main
git merge origin/main --allow-unrelated-histories -m 'chore: initialize GitHub repository'
```

出现 README 冲突时保留项目自己的 README，再完成合并提交。

**完成标准**：`git log --all --decorate` 显示本地与远程历史进入同一提交图。

---

## 3. 稳健推送（含 send-pack 兜底）

先尝试常规推送：

```bash
git push -u origin main
git push origin vX.Y.Z
```

**若 `git push` 被执行环境反复强制终止**（`Killed: 9` / `SIGKILL` / exit 137），但远程可访问，改用 plumbing 命令 `git send-pack`。注意：`send-pack` **不解析 `origin` 别名**，必须传完整远程 URL。

先确认远程协议：

```bash
git remote get-url origin
```

SSH 远程：

```bash
GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=10' \
  git send-pack --verbose \
  git@github.com:OWNER/REPOSITORY.git \
  refs/heads/main:refs/heads/main \
  refs/tags/vX.Y.Z:refs/tags/vX.Y.Z
```

HTTPS 远程：

```bash
git send-pack --verbose \
  https://github.com/OWNER/REPOSITORY.git \
  refs/heads/main:refs/heads/main \
  refs/tags/vX.Y.Z:refs/tags/vX.Y.Z
```

`send-pack` 输出必须同时含 `main -> main` 与 `vX.Y.Z -> vX.Y.Z` 的成功更新记录。

**推送后务必核验远程引用**（push 被截断/静默失败时尤其重要）：

```bash
git ls-remote --heads --tags git@github.com:OWNER/REPOSITORY.git
# 核验 annotated tag 解引用目标 == 发布提交
git ls-remote origin refs/tags/vX.Y.Z refs/tags/vX.Y.Z^{}
```

**完成标准**：远程 `main` SHA 指向发布提交，且存在 `refs/tags/vX.Y.Z`，`vX.Y.Z^{}` 与 `main` 指向同一提交。

---

## 4. 创建 GitHub Release

推送 tag **不会**自动创建 Release。

### 4.1 判断能否自动化（依据主 SKILL.md 的认证预探测）

- ✅ **可自动**：`gh` 已登录，或 `GH_TOKEN`/`GITHUB_TOKEN` 长度非 0 → 走 4.2。
- ❌ **不可自动**（未登录且无 token）→ **不要索取 token**，走 4.3「交给用户」。

> GitHub MCP 工具 release 能力不可靠：常见 MCP 凭据只提供只读 `get_*`/`list_releases`，**没有 create release**。别假设它能创建。

### 4.2 自动创建（gh 已认证）

release notes 一律先写文件（写入 `/tmp/`，**不写进项目目录**），再用 `--notes-file`：

```bash
cat > /tmp/release-notes-vX.Y.Z.md <<'EOF'
## 新增

- 一句话…（正文可含反引号、中文引号、换行，安全）
EOF

gh release create vX.Y.Z \
  --repo OWNER/REPOSITORY \
  --title 'vX.Y.Z' \
  --notes-file /tmp/release-notes-vX.Y.Z.md
```

> **健壮写法**：内联 `--notes '...'` 用单引号包裹时正文内不得再出现单引号，否则截断。内容变长或含反引号 `` ` `` 时必须用 `--notes-file`。

### 4.3 交给用户（未认证）

最常见的收尾场景，做到「用户拿来即用」，交付**三件套**：

1. **notes 文件**：把 release 内容用 write 工具写到 `/tmp/release-notes-vX.Y.Z.md`（不写进项目目录）。
2. **一条可直接执行的命令**（bash 多行 + fish 单行两种形态都给）：

   ```bash
   gh release create vX.Y.Z \
     --repo OWNER/REPOSITORY \
     --title 'vX.Y.Z' \
     --notes-file /tmp/release-notes-vX.Y.Z.md
   ```

   ```fish
   gh release create vX.Y.Z --repo OWNER/REPOSITORY --title vX.Y.Z --notes-file /tmp/release-notes-vX.Y.Z.md
   ```

3. **备用网页链接**：

   ```text
   https://github.com/OWNER/REPOSITORY/releases/new?tag=vX.Y.Z
   ```

   并提示：未登录先 `gh auth login`。

若用户明确要**完整 fish 脚本**，用 heredoc `<<'EOF'`（单引号防展开，让反引号 `` ` ``、`$`、`**` 原样保留），脚本内用 `set -l` 定义局部变量、`$status` 取退出码，含登录检查 + 失败时打印网页备用链接。

### 备选方案：GitHub REST API

仅当用户已在本地配置 token 时使用。token 必须保存在环境变量中；不得打印 token，也不得要求用户粘贴。

```bash
curl --request POST \
  --url 'https://api.github.com/repos/OWNER/REPOSITORY/releases' \
  --header 'Accept: application/vnd.github+json' \
  --header 'Authorization: Bearer '$GH_TOKEN \
  --header 'X-GitHub-Api-Version: 2022-11-28' \
  --data '{
    "tag_name": "vX.Y.Z",
    "target_commitish": "main",
    "name": "vX.Y.Z",
    "body": "## 新版\n\n- 亮点。",
    "draft": false,
    "prerelease": false
  }'
```

**完成标准**：从 `gh release view` 或 API 响应拿到 Release 的 `html_url`。

```bash
gh release view vX.Y.Z --repo OWNER/REPOSITORY --json url,tagName,targetCommitish
```

---

## 5. tag 需要迁移时的兜底（Release tag 必须指向最终提交）

若合并或最终修复发生在打 tag 之后，先在本地移动带注释标签，再仅强推该 tag：

```bash
git tag -d vX.Y.Z
git tag -a vX.Y.Z -m 'vX.Y.Z' HEAD
git send-pack --verbose REMOTE_URL refs/tags/vX.Y.Z:refs/tags/vX.Y.Z
```

---

## GitHub 特有经验

- GitHub MCP 凭据可能有仓库读取/写入权限，但不一定有创建仓库/PR/Release 权限，每项能力独立验证。
- `gh` 要 `gh auth login` 或非空 `GH_TOKEN`；能走 SSH 的 key 不代表 CLI API 已认证。
- 即使 Git SSH 可用，浏览器自动化会话仍可能未登录 GitHub；只有用户已登录浏览器时才操作受保护页面。
