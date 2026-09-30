# 后端工程

T0 工程/DTO/状态模型与七域初始 Alembic 迁移已完成，业务 API、后台进程和 Docker 镜像在 T1 及后续阶段实现。Python 固定为 3.12.10，使用 uv 管理独立依赖。

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

配置/真实烟测/临时 MySQL 验证见 [开发说明](../docs/开发说明.md)，表结构见 [数据结构](../docs/database/README.md)。普通 pytest 不执行真实学校检查，未配置临时 MySQL 时跳过 1 项集成检查。生产部署目标仍是仅依赖 Docker Engine/Compose，当前没有业务服务启动入口。
