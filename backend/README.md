# 后端工程

当前为 T0 工程基线，领域包可加载；业务 API、后台进程和 Docker 镜像在 T1 及后续阶段实现。Python 固定为 3.12.10，使用 uv 管理独立依赖。

开发机安装 uv 后执行：

```sh
cd backend
uv sync --locked
uv run python -c 'import services.identity, services.school_adapter, services.room, services.monitoring, services.notification, services.payment, services.audit'
```

后续契约、迁移与验证入口见 [开发说明](../docs/开发说明.md)。生产部署目标仍是仅依赖 Docker Engine/Compose，当前没有业务服务启动入口。
