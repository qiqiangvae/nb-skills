# npm 发布流程

本文件是 `coding-publish-skill` 的 npm 分支。**前置**：已完成主 `SKILL.md` 里的「公共前置」（版本号确认 + 认证预探测 + **敏感内容审查** + 公共提交打 tag）。

> 发布前务必确认敏感内容审查（`references/sensitive-content.md`）已通过，并核对 `npm pack --dry-run` 的 tarball 内容不含敏感文件——这是不可跳过的门禁。

目标交付物：registry 上的 `+ <pkg>@<version>`，且 `dist-tags.latest` 指向刚发布版本。

---

## 1. 探测包名归属（避免撞名 / 误判）

```bash
npm view <pkg-name> name version dist-tags 2>&1 | head -20
```

按结果判断：

- 输出「不存在 / 404」→ 全新包。问用户：沿用当前 `name`，还是改成 scoped（`@用户名/包名`）。
- 输出其他作者的同名包 → **必须改名或加 scope**，提示撞名风险。
- 输出「name 与自己一致、版本是历史版本」→ 这是用户自己的包，直接做版本升级（`npm publish` 会覆盖 `latest`）。

确认登录账号（避免发到错误账号）：

```bash
npm whoami
```

> 前置认证预探测里已确认 `npm whoami` 有输出；若为空，报阻塞并交用户执行 `npm login`。

---

## 2. 发布前校验（pack 内容 + 版本号）

```bash
# files 白名单 + 版本号核对，不真的上传
npm pack --dry-run 2>&1 | tail -30
```

核对：

- `Tarball Contents` 含预期的 `lib/**`、`README*`、`build.mjs`、`cordis.patch.yml` 等；
- `version` 是目标版本；
- 没把 `node_modules`、`.git`、源文件（若不想暴露）打进包。

若缺 `repository` 字段，先在 `package.json` 补上（npm 页面需要它链接回 GitHub），并重新提交。

---

## 3. 发布与核验

```bash
npm publish 2>&1 | tail -20
```

**核验以 `npm publish` 的成功回显为准**（打印 `+ <pkg>@<version>`），并核对 `dist-tags` 与 `versions`：

```bash
npm view <pkg-name> dist-tags
npm view <pkg-name> versions --json
```

> `npm view <pkg> version` 可能因 registry/镜像缓存显示旧版本，**不可单独作为核验依据**；以 `dist-tags.latest` 与 `versions` 数组为准。

**完成标准**：`npm publish` 回显 `+ <pkg>@<version>`，且 `dist-tags.latest` 指向刚发布的版本。

---

## 4. 修复发布错误后的重新发布

npm 同一版本号**不可重复覆盖发布**（`E403` / `cannot publish over previously published version`）。若发布内容有误：

- 递增到新版本（patch/minor）后重新 `npm publish`；
- 或先 `npm unpublish <pkg>@<version>`（仅在发布后很短时间窗口内、且符合 npm 策略时允许，需谨慎并征得用户同意）。

---

## npm 特有经验

- 先 `npm view` 确认同名包归属（是否是自己已发的历史版本），避免误以为撞名。
- 发布前 `npm pack --dry-run` 确认 tarball 内容，防止漏打 `lib/` 或误打源文件。
- `dist-tags.@latest` 是权威「当前版本」指针；单看 `npm view <pkg> version` 可能被缓存误导。
