# GitHub 协作与合并流程

更新日期：2026-10-01。适用于源码、文档、配置、修复和分支同步。

## 分支与 PR

`main` 保存已交付内容，`dev` 是集成分支。日常任务从最新 `dev` 创建 `codex/` 前缀的工作分支，每完成一个可验证小步，检查差异、同步受影响文档与 `PROJECT_PROGRESS.md`，再用中文说明 commit 并 push。

```sh
git fetch origin
git switch -c codex/任务名称 origin/dev
# 完成实现、文档与相关本地验证后：
git status --short --branch
git diff --check
git diff
git add <本次相关文件>
git commit -m 'fix: 本次修复的中文说明'
git push -u origin HEAD
gh pr create --base dev --title 'fix: 本次修复的中文说明' --body-file /absolute/pr-description.md
```

PR 描述说明问题、最终行为和实际验证。工作分支通过 PR 合入 `dev`；完整功能再创建 `dev → main` PR，并重新执行检查。交付后若下一任务的 `dev` 不包含最新 `main`，先通过 `main → dev` PR 同步，仍需等待检查，不直接 push 或在本地快进推送受保护分支。PR 使用 merge commit 保留分支祖先关系。

## Actions 合并条件

`.github/workflows/check.yaml` 对目标为 `dev`/`main` 的 PR 和两个分支的 push 执行。稳定作业名 `check` 包含单元、契约、规则、类型、构建、浏览器和实际容器集成，界面显示为 `容器验证 / check`；不按文件路径跳过文档改动。同一 PR 的新提交取消旧运行。

合并必须同时满足：

- 该 PR 最新提交的 Actions 全部为 `success`，必需检查 `check` 来自 GitHub Actions。
- PR 分支已包含目标分支最新提交，GitHub 严格检查通过且没有冲突。
- 已检查本次差异，文档、进度及相关本地验证完成。

失败、运行中、取消、跳过、没有检查都不能视为通过。旧提交的绿色结果、本地测试通过或历史阶段验收不能替代当前 PR 的结果；新提交、冲突解决或更新分支后重新等待检查。

```sh
gh pr checks <PR编号> --watch --interval 10
gh pr view <PR编号> --json headRefOid,mergeStateStatus,statusCheckRollup
# 核对所有 Actions 的 conclusion 为 SUCCESS、门禁满足，并取得最新 headRefOid 后：
gh pr merge <PR编号> --merge --match-head-commit <最新headRefOid>
```

不使用 `--admin` 或绕过保护。检查失败时查看 `gh run view <运行ID> --log-failed`，在原工作分支修复、提交并推送，让 PR 重新检查。合并后保留 push 检查；若失败，在新的修复 PR 处理，不直接修改目标分支。

## GitHub 分支保护

`dev` 和 `main` 使用相同保护：要求 PR，`check` 为来自 GitHub Actions（App ID 15368）的必需检查，启用严格模式以要求分支包含最新目标提交，管理员也受规则约束，禁止强制推送和删除。不额外要求他人审批，以保持当前单人开发流程。

仓库管理员在 GitHub Settings → Branches 配置并读取 API 核对；本地 Markdown 本身不能启用服务器保护。检查当前配置：

```sh
gh api repos/ChaceQC/elect/branches/dev/protection
gh api repos/ChaceQC/elect/branches/main/protection
```

预期 `required_status_checks.strict=true`、必需 `checks` 中含 `context=check`/`app_id=15368`，`required_pull_request_reviews` 存在且审批数为 0，`enforce_admins.enabled=true`，强推与删除均为 false。仓库权限或 GitHub 套餐不支持时，如实记录未启用，不宣称已有保护；继续遵守 PR 与 Actions 规则。
