# 部署配置约定

T0 已提供 [.env.example](.env.example) 与 [Secret/数据库所有权清单](secrets.example.yaml)。变量、注入和能力开关见 [T0 决策](../docs/decisions/T0实施决策.md)。

当前没有 Compose、镜像、TLS 预检或可启动的业务服务。T1-01/T1-02 将创建两端 Dockerfile 与 `deploy/compose.yaml`，按 [部署说明](../docs/Docker部署配置说明.md)实现容器入口。
