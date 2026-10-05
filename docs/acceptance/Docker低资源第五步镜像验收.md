# Docker低资源第五步镜像验收

日期：2026-10-04（Asia/Shanghai）；版本：0.18.0；状态：镜像批已交付，第五步整体未完成。

## 交付范围

- 基础Compose不含build，local通过独立构建覆盖选择；published部署包不需要frontend/backend目录。
- CI标签在全部本次检查通过后直接发布本次受测runtime、摘要/源提交清单及开发版部署资产；不重新构建、不覆盖已有不同镜像。
- 首次/原卷升级共用固定摘要/OCI元数据、拉取及TLS/Nginx预检；通过后停止本项目旧角色，按基础→迁移→领域→后台→入口逐项等待，显式parallel=1/no-build/no-deps。
- 恢复后台禁用、旧profile停止、原卷/Secret及副作用默认值保持。

## 验证记录

- 后端ruff、231 passed / 1 skipped、OpenAPI和七域表目录通过；18项相关单位回归已验证版本不匹配、移动标签/构建入口/混用后端拒绝、源提交一致、local生产入口拒绝、拉取失败不停止应用、入口预检早于停机及逐服务无构建启动。
- 本机新空库首轮13长期容器健康；测试过程中编辑正在运行的start脚本导致shell读取偏移异常，首轮未记通过。固定脚本后同一隔离原卷分阶段启动成功，13容器全部healthy。
- 仅deploy的Git归档在同一隔离项目/原卷中通过published选择无构建启动；目录内没有frontend/backend，13长期容器全部healthy、七域角色ready、零OOMKilled和零重启。可靠事件smoke的七域权限/并发迁移/JWT/Redis ACL/Relay重复消息及Inbox也通过。
- [标签CI 37198320789](https://github.com/ChaceQC/elect/actions/runs/37198320789)全部success：231后端/49前端/32浏览器、空库T2–T6合成回归、无源码包、原卷13→30→13、资源/消息/并发取消、加密隔离恢复及模拟容量/生产前端通过。
- 已实际发布[开发版v0.18.0](https://github.com/ChaceQC/elect/releases/tag/v0.18.0)，3个资产完整上传并下载核对：镜像/基础服务均固定sha256，源提交2e130f199691664dd004980f715aaebe6f934e52、check链接相符；51个归档成员只含部署与手册，不含真实env/密钥/源码，外部副作用false和容量验收false。实际摘要见[发布清单](Docker低资源第五步镜像发布.json)。
- 仅停止本轮隔离项目并保留3个命名卷/受限证据；原业务停机、其余5个原容器仍运行。

## 未完成边界

第五步页面请求/数据留存清理未实现，本方案第五步继续未勾选。2核2GB/50人24小时、真实D02映射、生产异机/PITR及T8尚未验收；本轮不读取auth.txt/email_auth.txt，不调用真实学校/SMTP/支付，原业务保持停止。linux/amd64之外的平台未验收。
