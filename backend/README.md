# 后端工程

T0 工程/DTO/状态模型与七域初始 Alembic 迁移已完成。T1 已建立非 root Docker 镜像、八个 API 骨架、Secret 加载、UTC 连接池、脱敏日志、统一错误、live/ready、Ed25519 服务认证与 TLS 预检、Outbox/Inbox、Relay 与 Audit Worker；业务 API 在后续阶段实现。Python 固定为 3.12.10，使用 uv 管理独立依赖。

T2 后端已实现正式 httpx 学校认证、Redis 原子验证码、密文暂存/激活、持久登录恢复、应用 Cookie/CSRF、本人绑定同步与候选分页。真实学校指定账号认证、1 条本人绑定、候选第一页、退出与后台认证恢复已通过；生产前端/阶段验收见 [T2 记录](../docs/acceptance/T2验收记录.md)。设计与真实证据见 [T2 决策](../docs/decisions/T2认证与读取.md)。

T3 已接通 GET/PATCH monitor、配置/取消/代次事务、提交屏障、持久 retarget 与 Room 证明查询；Identity 登录先 prepare-update 再激活/确认，公开撤回返回持久操作，恢复器按屏障、Adapter 删除、Monitoring 确认续作。撤回清除历史密码暂存与旧 token，保留应用会话；Notification 发送前许可核对当前样本/代次/邮箱/冷却，尚无 SMTP Worker。见 [控制决策](../docs/decisions/T3监控控制基础.md)、[凭据决策](../docs/decisions/T3凭据协调与发送许可.md) 与 [增量验收](../docs/acceptance/T3凭据与许可验收记录.md)。新 head 为 identity_0003、school_0003、monitoring_0003；现有 T2/T3 部署先重复运行 upgrade_controls 再迁移。

开发机安装 uv 后执行：

```sh
cd backend
uv sync --locked
uv run ruff check .
uv run pytest -q
uv run python -m scripts.generate_openapi --check
uv run python -m scripts.generate_protocols --check
uv run python -m scripts.schema_catalog --check
uv run python -m scripts.migrations --domain all --sql --output-dir /tmp/elect-ddl
```

配置/真实烟测/临时 MySQL 验证见 [开发说明](../docs/开发说明.md)，表结构见 [数据结构](../docs/database/README.md)。普通 pytest 不执行真实学校检查。`docker build -t elect-backend:v0.4.0 backend` 在仓库根构建；服务使用 `python -m services.gateway` 等入口，须挂载对应运行 Secret 并配置 ELECT_PUBLIC_ORIGIN，正式编排已在 deploy/compose.yaml 交付。T2 认证/读取及 T3 监控配置/撤回路由已接通；后续阶段入口返回 FEATURE_DISABLED。

容器检查在仓库根执行 `sh deploy/check.sh`，全新一次性集成使用 `sh deploy/test-stack.sh /absolute/new-directory elect-test-name`，包含 T2 合成上游、T3 控制及凭据/发送许可竞态检查，不调用真实学校或 SMTP。显式真实学校烟测独立执行，不进入 CI。默认/写绑定、真实采集/邮件/支付为后续批次。
