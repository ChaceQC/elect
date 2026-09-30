# 后端工程

T0 工程/DTO/状态模型与七域初始 Alembic 迁移已完成。T1 已建立非 root Docker 镜像、八个 API 骨架、Secret 加载、UTC 连接池、脱敏日志、统一错误、live/ready、Ed25519 服务认证与 TLS 预检、Outbox/Inbox、Relay 与 Audit Worker；业务 API 在后续阶段实现。Python 固定为 3.12.10，使用 uv 管理独立依赖。

T2 正在实施：school_adapter/infrastructure 已建立正式 httpx CAS/SDGL 协议、学校兼容 RSA、验证码图片校验、AES-GCM 信封及 Redis 原子状态。当前仅通过离线定向测试，公开登录仍未开放；不等同于凭据激活、应用会话或学校业务验收。

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

配置/真实烟测/临时 MySQL 验证见 [开发说明](../docs/开发说明.md)，表结构见 [数据结构](../docs/database/README.md)。普通 pytest 不执行真实学校检查。`docker build -t elect-backend:v0.2.0 backend` 在仓库根构建；服务使用 `python -m services.gateway` 等入口，须挂载对应运行 Secret 并配置 ELECT_PUBLIC_ORIGIN，正式编排已在 deploy/compose.yaml 交付。公开业务入口暂返回 FEATURE_DISABLED。

容器检查在仓库根执行 `sh deploy/check.sh`，全新一次性集成使用 `sh deploy/test-stack.sh /absolute/new-directory elect-test-name`，不调用学校或 SMTP。测试流程实际通过；学校 API/会话、监控、邮件、支付均为后续阶段。
