# 敏感内容审查（强制门禁）

本文件是 `coding-publish-skill` 的敏感内容审查分支。**任何** `git commit`、`git push`、`npm publish`、创建 Release 之前都必须先**完整执行**本节审查，避免把密钥、令牌、密码、客户 PII、生产配置或未脱敏日志推送到公网环境。

> 这是一道**不可跳过**的门禁：宁可报阻塞、拖延发布，也不带病提交。凡命中下文任意一类，一律停手，按「发现后的处理」处置。

---

## 1. 审查什么（敏感内容清单）

审查范围 = **本次将被推送到公网的一切内容**，包括：

- **git 提交内容**：工作区改动 + 暂存区 + 本次提交涉及的所有文件；
- **package.json / 打包产物**：`npm pack` 将打进 tarball 的一切；
- **Release notes / tag 注释**：写入 `/tmp/` 的 release notes 同样要查（会被发布到 GitHub Release 页）。

需要拦截的内容类型（命中即处理）：

| 类别 | 典型特征 / 正则示例 |
| --- | --- |
| 云服务 Access Key | `AKIA[0-9A-Z]{16}`（AWS）、`ASIA[0-9A-Z]{16}`、阿里云 `LTAI[A-Za-z0-9]{12,}` |
| GitHub / 个人令牌 | `ghp_[A-Za-z0-9]{36}`、`github_pat_[A-Za-z0-9_]{20,}`、`gho_`、`ghu_`、`ghs_` |
| Slack / 第三方令牌 | `xox[baprs]-[A-Za-z0-9-]{10,}`、`sk-[A-Za-z0-9]{20,}`、`Bearer [A-Za-z0-9._-]{20,}` |
| 私钥 / 证书 | `-----BEGIN [A-Z ]*PRIVATE KEY-----`、`.pem` / `.key` / `.p12` / `.pfx` 文件 |
| 数据库 / 服务凭据 | `postgres://user:pass@`、`redis://:pass@`、`mysql://user:pass@` 等连接串 |
| 明确命名的密钥字段 | `password:`, `passwd:`, `secret:`, `api_key:`, `access_token:`, `client_secret:` 后跟非空明文 |
| 客户 PII / 隐私数据 | 手机号、身份证号、真实姓名+邮箱、未脱敏的用户数据 dump、`*.sql` 数据导出 |
| 生产配置 | 指向生产数据库地址 / 内网 IP / 生产域名 / 生产环境变量的配置文件 |
| 未脱敏日志 / 缓存 | 含 token、cookie 的日志文件，`.env.local`、`*.session`、误提交的 `.vscode`/`.idea` 配置 |

> 判断原则：**「这个内容被搜索引擎/任何人看到会不会造成泄露」**。会 → 拦截。不确定 → 也拦截，交用户确认。宁可错拦，不可漏放。

---

## 2. 怎么查（扫描命令）

### 2.1 扫描将被提交的文本内容（核心）

```bash
# 扫描工作区 + 暂存区所有会被 git 追踪的文本文件；排除锁文件减少噪音
git grep -n -I -E \
  '(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|LTAI[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|\
  xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\
  (password|passwd|secret|api[_-]?key|access_token|client_secret)\s*[:=]\s*[^[:space:]]+|\
  (postgres|mysql|redis|mongodb)://[^[:space:]]*:[^[:space:]]*@)' \
  -- . 2>/dev/null
```

> 也可以先看「有什么会被提交」再针对扫描：`git status --short` + `git diff --cached --name-only`。

### 2.2 检查密钥文件是否被 git 追踪

```bash
# .env / 密钥文件是否已经被追踪（历史里有没有提交过）
git ls-files | grep -E '(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx)|id_rsa|id_ed25519)$' || echo "无已追踪密钥文件"
```

### 2.3 核对 .gitignore 覆盖

```bash
# .gitignore 是否忽略了常见敏感文件
cat .gitignore 2>/dev/null | grep -E '\.env|\.pem|\.key|\.p12|node_modules' || echo "⚠ .gitignore 未覆盖 .env / 密钥文件"
```

### 2.4 检查「已提交但想忽略」的文件

```bash
# 已被追踪但现在应该忽略的（比如之前误提交过 .env）
git ls-files -ci --exclude-standard 2>/dev/null || true
```

### 2.5 npm 打包范围核对

```bash
# tarball 里打进了什么——里面也不能有敏感文件
npm pack --dry-run 2>&1 | tail -40
```

---

## 3. 发现后的处理（命中即阻塞）

一旦命中，**立即停止提交/推送/发布**，按严重程度处置：

1. **误报 / 测试样例 / 已脱敏**：确认确实是占位符、假数据、且不会泄露后，记录结论、继续。
2. **纯本地文件（如 `.env`）被误追踪**：
   - 从追踪中移除：`git rm --cached .env`（保留本地文件）；
   - 加入 `.gitignore`；
   - **检查历史**：若之前某次提交已经推过 `.env`，必须提醒用户轮换（rotate）其中的密钥——单纯删除文件不能撤销已泄露的机密。
3. **真实密钥/令牌/PII 已出现在工作区/暂存区**：
   - 立即移除内容并告知用户；
   - 若该机密曾进入过**任何已推送的提交**，报阻塞，提醒用户轮换该密钥（GitHub token → 在 GitHub 里 revoke 重建；云 Access Key → 控制台禁用重发）。
4. **不确定**：一律报阻塞，把命中内容（脱敏展示）给用户判断，**不自作主张放行**。

> 关键认知：**删除 + 重新提交不等于消除泄露**。已推送到公网的机密要当作「已泄露」处理，必须轮换，而不是只删一行。

---

## 4. 完成标准（放行条件）

只有同时满足以下全部，才可进入提交/推送/发布：

- [ ] 2.1 内容扫描 **零命中**（或命中项均已确认是脱敏样例并记录）；
- [ ] 2.2 无 `.env` / `.pem` / `.key` / 私钥文件被 git 追踪；
- [ ] 2.3 `.gitignore` 已覆盖常见敏感文件；
- [ ] npm 场景下 `npm pack --dry-run` 的 tarball 内容不含敏感文件；
- [ ] 未发现任何「曾推送到公网的机密需轮换」的告警。

在最终报告里写明「敏感内容审查：已通过，扫描零命中」或逐项列出命中与处理方式。
