# 业绩追踪看板 → GitHub 推送说明

> 目标：用整个「业绩追踪看板」工作区替换原先仅含中远海控的 GitHub 项目
> 仓库：`Kelvin-Liu1982/PersonalStock`（分支 `main`）

## 做了什么

1. 把原来位于 `cosco-shipping/` 内的 `.git` 仓库与 `.gitignore` 上移到工作区根目录，
   git 自动识别为 rename，旧根文件整体落入 `cosco-shipping/` 子目录。
2. 新增 `china-coal/`、`index.html` 一级导航页；根目录 `.gitignore` 增加 `.workbuddy/`，
   并忽略 `.venv/`、`__pycache__/`、`.DS_Store` 等。
3. 本地提交（66 个文件变动，含 rename）。
4. 强制推送到 GitHub，远程 `main` 被整体替换为新结构。

## 关键命令（在本机执行）

```bash
# 1. 仓库上移
mv cosco-shipping/.git .git
mv cosco-shipping/.gitignore .gitignore

# 2. 暂存并提交
git add -A
git commit -m "重构：以业绩追踪看板工作区为根仓库，整合中煤能源与中远海控两个看板"

# 3. 推送（非快进，属"替换旧项目"，需用 --force）
#    因本机钥匙串无 GitHub 凭据，推送时直接在 URL 中带 PAT：
git push "https://Kelvin-Liu1982:<你的PAT>@github.com/Kelvin-Liu1982/PersonalStock.git" main --force

# 4. 设好上游，之后在该目录直接 git push 即可
git branch --set-upstream-to=origin/main
```

## 注意事项

- 用的是 **fine-grained（细粒度）PAT**，必须在
  `Settings → Developer settings → Fine-grained tokens → 该 token → Edit`
  里把 **Repository access** 指向 `PersonalStock`（或 All repositories），
  并在 **Permissions → Repository permissions → Contents** 设为 **Read and write**，否则 push 会 403。
- `--force-with-lease` 因本地远程状态过期会报 `stale info`，直接用 `--force` 即可。
- 本机 `git credential-osxkeychain store` 写入失败（错误 100001），token 未存入钥匙串；
  后续普通 `git push` 仍需在 URL 带 token，或手动把 PAT 存进钥匙串。
- 推送完成后如需收回权限，可在 GitHub 对应 token 页面直接 Revoke。

## 推送结果

- 远程 `main`：`0df887f`（与本地 HEAD 一致）
- 远程根目录结构：`index.html` / `cosco-shipping/` / `china-coal/` / `.gitignore`
