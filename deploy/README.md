# Docker 部署入口

T1 已建立 [compose.yaml](compose.yaml)、[公开变量模板](.env.example)、[Secret/账号清单](secrets.example.yaml)、Nginx/TLS、MySQL 空卷 provisioning、Redis ACL 与 RabbitMQ 权限。

先配置 `.env` 并用后端镜像离线生成受限 Secret（已有目录拒绝覆盖），再执行：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
```

完整生成、首次启动与证书替换见 [部署说明](../docs/Docker部署配置说明.md)。`compose.test.yaml` 仅供一次性验收：Nginx 端口改为本机 18080/18443，smoke 显式挂载测试域凭据；不得在生产运行测试作业。

默认编排 19 个长期服务及 migrate/tls-check 一次性作业。八个 API 的学校业务关闭；六个 Relay 与 Audit Worker 实际执行持久事件扫描/投递/去重。监控、支付、邮件业务 Worker 随相应阶段实现后加入。`down` 保留命名卷，普通启停不使用 `down -v`。
