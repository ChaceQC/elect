# Docker 部署入口

T1 已建立 [compose.yaml](compose.yaml)、[公开变量模板](.env.example)、[Secret/账号清单](secrets.example.yaml)、Nginx/TLS、MySQL 空卷 provisioning、Redis ACL 与 RabbitMQ 权限。

先配置 `.env` 并用后端镜像离线生成受限 Secret（已有目录拒绝覆盖），再执行：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
```

完整生成、首次启动与证书替换见 [部署说明](../docs/Docker部署配置说明.md)。`compose.test.yaml` 仅供一次性验收：Nginx 端口改为本机 18080/18443，smoke 显式挂载测试域凭据；不得在生产运行测试作业。

默认编排 22 个长期服务及 migrate/tls-check 一次性作业。T2 开放认证与本人读取，新增 identity-recovery、room-sync-worker、school-maintenance；六个 Relay 与 Audit Worker 实际执行持久事件扫描/投递/去重。监控、支付、邮件业务 Worker 随相应阶段实现后加入。`down` 保留命名卷，普通启停不使用 `down -v`。

仅依赖 Docker 的离线检查：`sh deploy/check.sh`；全新集成：`sh deploy/test-stack.sh /absolute/new-directory elect-test-local`。T2 认证 Secret、内部 TLS、学校出口与资源配置见 [实施决策](../docs/decisions/T2认证与读取.md)。已通过基础范围见 [T1 验收](../docs/acceptance/T1验收记录.md)。

T3 启用 Monitoring 控制/发送许可和 Identity 持久撤回，新增独立邮箱密钥及 identity_0003/school_0003/monitoring_0003；已有 T2/第一批 T3 部署须重复执行 `services.deployment.upgrade_controls`，迁移后重建 MQ/应用加载新增权限，不能重新 provision 覆盖既有 Secret。集成入口包含 `scripts.t3_control_smoke` 和 `scripts.t3_credential_smoke`，使用合成学校及实际数据库验证故障/竞态；合成任务终结后再恢复真实 Worker，未启动采集或 SMTP Worker。见 [凭据与许可决策](../docs/decisions/T3凭据协调与发送许可.md)。

## T4 采集引擎升级

独立故障验收的 `t4-fault` 目录保留宿主机属主，使用 GID 10001 和 0770 权限，让普通用户与 smoke 容器均可访问各自的日志/状态文件；正式 Secret 权限不变。CI 与 PR 合并门禁见 [GitHub 协作与合并流程](../docs/GitHub协作与合并流程.md)。

新增三个独立监控进程，长期进程增至25个；monitoring_0004保存采集时的间隔。保留原Secret与卷，重复upgrade_controls后重建RabbitMQ和全部相关应用以加载新文件挂载/权限，运行migrate，再启动新Scheduler/Worker/恢复器。不要重新provision已有Secret。

monitor.run_ready和room.history_sync_requested为持久签名唤醒；任务以MySQL为准，MQ失效时仍扫描。采集Worker每10秒续租，最长90秒，退出宽限100秒；Room/Identity长请求期间验证数据库并更新心跳。仅balance_only，SMTP/支付开关仍默认false。

`test-stack.sh`合成阶段暂停Identity/Room与监控三个进程、Monitoring Relay，运行t4_query_smoke/t4_monitor_smoke；合成监控全部关闭后再恢复。新验收见 [T4采集引擎](../docs/acceptance/T4采集引擎验收记录.md)。

T5新增 monitor-alerts、notification-worker、notification-recovery，长期进程共28个；SMTP默认关闭，仅Worker持有notification_egress出口。升级需要重复upgrade_controls、迁移monitoring_0005/notification_0002并重建RabbitMQ/应用加载Secret。本域密钥、HTTP CONNECT代理和本机TUN排查见 [邮件运行说明](../docs/runbooks/邮件投递与代理排查.md)。

0.11.0新增payment_0004和本人支付取消，仍为30个长期服务；保留原Secret/卷，先迁移再重建Payment/Gateway和两个支付后台进程。独立测试端口可通过ELECT_TEST_HTTP_PORT/ELECT_TEST_HTTPS_PORT覆盖，不停止原项目。

0.12.0交付T7集中回归、加密备份/隔离恢复、运行状态和模拟容量入口；证书部署/更换按用户要求跳过。完整范围与未验事项见 [T7验收](../docs/acceptance/T7验收记录.md)。
