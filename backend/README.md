# 后端工程

T0 工程/DTO/状态模型与七域初始 Alembic 迁移已完成。T1 已建立非 root Docker 镜像、八个 API 骨架、Secret 加载、UTC 连接池、脱敏日志、统一错误、live/ready、Ed25519 服务认证与 TLS 预检、Outbox/Inbox、Relay 与 Audit Worker；业务 API 在后续阶段实现。Python 固定为 3.12.10，使用 uv 管理独立依赖。

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

配置/真实烟测/临时 MySQL 验证见 [开发说明](../docs/开发说明.md)，表结构见 [数据结构](../docs/database/README.md)。普通 pytest 不执行真实学校检查。`docker build -t elect-backend:v0.1.0 backend` 在仓库根构建；服务使用 `python -m services.gateway` 等入口，须挂载对应运行 Secret 并配置 ELECT_PUBLIC_ORIGIN，正式编排已在 deploy/compose.yaml 交付。公开业务入口暂返回 FEATURE_DISABLED。
