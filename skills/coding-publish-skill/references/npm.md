# npm 发布流程

本文件是 `coding-publish-skill` 的 npm 分支。**前置**：主 `SKILL.md`「公共前置」A–D 已完成（版本号确认 + 预探测含包名归属 + **敏感内容审查** + 公共提交打 tag）；敏感审查与 tarball 范围的权威清单在 [`sensitive-content.md`](sensitive-content.md)。

目标交付物：registry 上的 `+ <pkg>@<version>`，且 `dist-tags.latest` 指向刚发布版本。

---

## 1. 发布前校验（pack 内容 + 版本号）

```bash
# files 白名单 + 版本号核对，不真的上传
npm pack --dry-run 2>&1 | tail -30
```

核对：

- `Tarball Contents` 与 `package.json#files` 白名单一致，该发的构建产物没漏；
- `version` 是目标版本；
- 没把 `node_modules`、`.git`、不想公开的源文件打进包。

**完成标准**：tarball 清单与 `files` 白名单逐项对上，`version` 等于目标版本。

---

## 2. 发布与核验

```bash
npm publish 2>&1 | tail -20
```

**核验以 `npm publish` 的成功回显为准**（打印 `+ <pkg>@<version>`），并核对 `dist-tags` 与 `versions`：

```bash
npm view <pkg-name> dist-tags
npm view <pkg-name> versions --json
```

**完成标准**：`npm publish` 回显 `+ <pkg>@<version>`，且 `dist-tags.latest` 指向刚发布的版本。

---

## 3. 修复发布错误后的重新发布

npm 同一版本号**不可重复覆盖发布**（`E403` / `cannot publish over previously published version`）。若发布内容有误：

- 递增到新版本（patch/minor）后重新 `npm publish`；
- 或先 `npm unpublish <pkg>@<version>`（仅在发布后很短时间窗口内、且符合 npm 策略时允许，需谨慎并征得用户同意）。

**完成标准**：新版本号已发布且 `dist-tags.latest` 指向它；走了 unpublish 分支则以用户确认完成为准。

---

## npm 特有经验

- 发布前 `npm pack --dry-run` 确认 tarball 内容，防止漏打 `lib/` 或误打源文件。
- `npm view <pkg> version` 可能因 registry / 镜像缓存显示旧版本，**不可单独作为核验依据**；以 `dist-tags.latest` 与 `versions` 数组为准。
