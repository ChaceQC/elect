# 后端工程

T0 工程/DTO/状态模型与七域初始 Alembic 迁移已完成。T1 已建立非 root Docker 镜像、八个 API 骨架、Secret 加载、UTC 连接池、脱敏日志、统一错误、live/ready、Ed25519 服务认证与 TLS 预检、Outbox/Inbox、Relay 与 Audit Worker；业务 API 在后续阶段实现。Python 固定为 3.12.10，使用 uv 管理独立依赖。

T2 后端已实现正式 httpx 学校认证、Redis 原子验证码、密文暂存/激活、持久登录恢复、应用 Cookie/CSRF、本人绑定同步与候选分页。真实学校指定账号认证、1 条本人绑定、候选第一页、退出与后台认证恢复已通过；前端/阶段验收正在实施。设计与真实证据见 [T2 决策](../docs/decisions/T2认证与读取.md)。

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

配置/真实烟测/临时 MySQL 验证见 [开发说明](../docs/开发说明.md)，表结构见 [数据结构](../docs/database/README.md)。普通 pytest 不执行真实学校检查。`docker build -t elect-backend:v0.2.0 backend` 在仓库根构建；服务使用 `python -m services.gateway` 等入口，须挂载对应运行 Secret 并配置 ELECT_PUBLIC_ORIGIN，正式编排已在 deploy/compose.yaml 交付。T2 认证和读取路由已接通；后续阶段入口返回 FEATURE_DISABLED。

容器检查在仓库根执行 `sh deploy/check.sh`，全新一次性集成使用 `sh deploy/test-stack.sh /absolute/new-directory elect-test-name`，不调用学校或 SMTP。T2 增加实际 MySQL/Redis 的合成上游隔离/恢复检查；显式真实学校烟测独立执行，不进入 CI。默认/写绑定/监控/邮件/支付为后续阶段。
