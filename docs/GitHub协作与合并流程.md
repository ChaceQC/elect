# GitHub 协作与合并流程

更新日期：2026-10-06。适用于源码、文档、配置、修复和分支同步。

## 分支与 PR

`main` 保存已交付内容，日常默认在 `dev` 开发。当前开发分支允许直接 commit 并 push，无需为提交或推送创建 PR，也不强制另建工作分支。每完成一个可验证小步，检查差异、同步受影响文档与 `PROJECT_PROGRESS.md`，再用中文说明提交推送。

2026-10-06按用户最终更正，撤回“CI成功后不再更新文档”的新增AGENTS规则，改由Actions跳过纯Markdown分支push。文档仍按需要同步、提交和推送；纯文档提交记录“按路径规则未触发CI”，不能写成CI成功。含任何非`.md`文件的提交仍等待最新SHA的CI/check；文档收口须能追溯最近一次包含业务/配置改动且CI成功的提交，不能借文档提交掩盖此前失败。main PR不跳过，主分支必需检查保持可用。

```sh
# 完成实现、文档与相关本地验证后：
git status --short --branch
git diff --check
git diff
git add <本次相关文件>
git commit -m 'fix: 本次修复的中文说明'
git push -u origin HEAD
# 仅准备合并到 main 时创建 PR；通常从 dev 发起：
gh pr create --base main --head dev --title 'fix: 本次修复的中文说明' --body-file /absolute/pr-description.md
```

仅合并到 `main` 时必须使用 PR，通常为 `dev → main`；PR 描述说明问题、最终行为和实际验证。交付后若 `dev` 不包含最新 `main`，可 fetch 后将 `origin/main` 合入 `dev` 并直接 push，不需要同步 PR。主分支 PR 使用 merge commit 保留祖先关系，不能直接 push `main`。

## Actions 合并条件

`.github/workflows/check.yaml` 对非main分支push使用`paths-ignore: ['**/*.md']`：只改Markdown时整个workflow不触发；含任意代码、配置、锁文件或契约JSON/YAML时执行前后端快速检查与构建（含查询配额数据库和浏览器）。不整目录忽略docs，以保留docs/contracts及schema-catalog等检查。目标为main的PR及vX.Y.Z标签push仍完整验证；GitHub不对标签push应用路径过滤，手动默认full，分支可选quick，标签手动运行始终完整且不发布。前后端并行；完整场景镜像就绪后，业务消息、13/30兼容、七容器交付恢复三组使用独立运行器和空库并行。快速场景不导出/上传镜像。稳定作业check以always()独立判定场景：快速要求两组success及三组skipped，完整要求五组success；失败、取消、缺失或意外跳过均拒绝。界面仍为`容器验证 / check`，push快速成功不能替代PR完整门禁。覆盖、镜像清单与计时见[CI决策](decisions/CI并行验证.md)。 main push按用户追加要求不触发CI，PR合并后不重复运行。

分支、PR按事件和ref分别取消过时运行；标签独立分组且不自动取消正在发布的同标签运行。普通验证仅contents读取，标签发布作为独立作业依赖check成功，才获得contents/packages写权限。PR的构建和验证统一使用默认检出的合并结果，不混用源分支镜像。

合并到 `main` 必须同时满足：

- 该 PR 最新提交的 Actions 全部为 `success`，必需检查 `check` 来自 GitHub Actions。
- PR 分支已包含目标分支最新提交，GitHub 严格检查通过且没有冲突。
- 已检查本次差异，文档、进度及相关本地验证完成。

PR必需的五组验证失败、运行中、取消、跳过或没有检查都不能视为通过；普通PR的发布作业按设计跳过，不属于必需验证。旧提交的绿色结果、本地测试通过、同提交push快速检查或历史阶段验收不能替代当前PR的完整结果；新提交、冲突解决或更新分支后重新等待检查。

```sh
gh pr checks <PR编号> --watch --interval 10
gh pr view <PR编号> --json headRefOid,mergeStateStatus,statusCheckRollup
# 核对所有 Actions 的 conclusion 为 SUCCESS、门禁满足，并取得最新 headRefOid 后：
gh pr merge <PR编号> --merge --match-head-commit <最新headRefOid>
```

不使用 `--admin` 或绕过主分支保护。检查失败时查看 `gh run view <运行ID> --log-failed`，在当前开发分支修复、提交并推送，让 PR 重新检查。main push不触发CI，合并后不重复运行；合并前必须通过当前PR完整门禁。后续修复仍在开发分支提交推送，再通过新的PR合入main。

## GitHub 分支保护

`main` 要求 PR，`check` 为来自 GitHub Actions（App ID 15368）的必需检查，启用严格模式以要求分支包含最新目标提交，管理员也受规则约束，禁止强制推送和删除。不额外要求他人审批，以保持当前单人开发流程。`dev` 不要求 PR 或推送前状态检查，允许日常直接提交推送，仅保留禁止强推/删除。

仓库管理员在 GitHub Settings → Branches 配置并读取 API 核对；本地 Markdown 本身不能启用服务器保护。检查当前配置：

```sh
gh api repos/ChaceQC/elect/branches/dev/protection
gh api repos/ChaceQC/elect/branches/main/protection
```

main 预期 `required_status_checks.strict=true`、必需 `checks` 中含 `context=check`/`app_id=15368`，`required_pull_request_reviews` 存在且审批数为 0，`enforce_admins.enabled=true`，强推与删除均为 false。dev 的 `required_status_checks` 和 `required_pull_request_reviews` 均为 null，强推与删除仍为 false。仓库权限或 GitHub 套餐不支持时，如实记录未启用，不宣称已有保护；继续遵守 main 的 PR 与 Actions 合并规则。

## 开发版镜像发布

0.18.0起，版本标签vX.Y.Z触发同一完整check。所有本次验证通过后，才将本次实际受测runtime发布至GHCR，保存固定摘要/源提交清单与仅deploy包，并创建标记为prerelease的GitHub开发版资产。标签必须匹配前后端版本；已有不同镜像的版本拒绝覆盖。标签发布不合并main、不表示T8或2核2GB容量验收，具体见[固定镜像手册](runbooks/固定镜像发布与启动.md)。

普通分支/PR不进入发布步骤。发布作业声明packages/contents写权限，registry和release认证使用本次GITHUB_TOKEN；该token不写入镜像、env模板或仓库。目标机使用已记录的摘要，不跟随latest。
