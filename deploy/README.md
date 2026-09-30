# 部署配置约定

T0 已提供 [.env.example](.env.example) 与 [Secret/数据库所有权清单](secrets.example.yaml)。变量、注入和能力开关见 [T0 决策](../docs/decisions/T0实施决策.md)。

T1 已建立两端 Dockerfile 与 TLS 预检，当前尚无 Compose 和可用业务服务。本阶段继续创建 `deploy/compose.yaml`，按 [部署说明](../docs/Docker部署配置说明.md)实现容器入口。
