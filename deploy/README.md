# Docker 部署入口

T1 已建立 [compose.yaml](compose.yaml)、[公开变量模板](.env.example)、[Secret/账号清单](secrets.example.yaml)、Nginx/TLS、MySQL 空卷 provisioning、Redis ACL 与 RabbitMQ 权限。

先配置 `.env` 并用后端镜像离线生成受限 Secret（已有目录拒绝覆盖），再执行：

```sh
sh deploy/compose.sh "$PWD/deploy/.env" elect config --quiet
sh deploy/compose.sh "$PWD/deploy/.env" elect up -d --build
```

完整生成、首次启动与证书替换见 [部署说明](../docs/Docker部署配置说明.md)。`compose.test.yaml` 仅供一次性验收：Nginx 端口改为本机 18080/18443，smoke 显式挂载测试域凭据；不得在生产运行测试作业。

当前基础编排为 30 个长期服务及 migrate/tls-check 一次性作业，包括八个 API、六个 Relay、Audit Worker 和各域已实现的后台角色；本机 SMTP 定向通道另加一个长期服务。`down` 保留命名卷，普通启停不使用 `down -v`。

50人、2核2GB的资源改造见[Docker低资源部署优化方案](../docs/Docker低资源部署优化方案.md)。0.15.0的`compose.low-resource.yaml`合并七域，基础长期容器30→13，Python进程26→9；SMTP发送Worker独立，可选通道另计1个。`ELECT_DEPLOYMENT_MODE=combined`由统一`compose.sh`选择覆盖，默认standalone保留原编排；0.16.0增加每池2+1、MySQL 128MiB/40连接、Redis 32MiB/96MiB限额、普通RabbitMQ/128MiB绝对水位和30秒探针，OCR线程及容器预算单独受控；兼容旧Secret与持久卷，见[资源参数决策](../docs/decisions/Docker低资源资源参数.md)。2GB容量仍待验收。旧Monitoring单域试点仅用于第一步对照。

`compose.sh`按公开配置选择私网HTTP、可选SMTP通道、轻量组合和ops覆盖；status/backup/restore/upgrade使用相同入口。恢复覆盖最后应用，完全不加载host网络SMTP通道。已有卷使用已构建镜像执行`sh deploy/upgrade.sh /absolute/stack.env 项目名`，先停止全部API和旧profile角色，再迁移/启动，不重新provision、不删除卷。组合、退出宽限及隔离验证见[生命周期决策](../docs/decisions/Docker低资源后台生命周期.md)。

仅依赖 Docker 的离线检查：`sh deploy/check.sh`；全新轻量集成：`sh deploy/test-stack.sh /absolute/new-directory elect-test-local combined`，随后`sh deploy/test-low-resource.sh /absolute/new-directory elect-test-local`验证七域角色与双向升级；随后`sh deploy/test-resource-parameters.sh /absolute/new-directory elect-test-local`验证池等待、基础服务生效值、MQ流控与独立无网络Redis写满/AOF重写/重启。省略第三参数仍验证standalone。T2 认证 Secret、内部 TLS、学校出口与资源配置见 [实施决策](../docs/decisions/T2认证与读取.md)。已通过基础范围见 [T1 验收](../docs/acceptance/T1验收记录.md)。

T3 启用 Monitoring 控制/发送许可和 Identity 持久撤回，新增独立邮箱密钥及 identity_0003/school_0003/monitoring_0003；已有 T2/第一批 T3 部署须重复执行 `services.deployment.upgrade_controls`，迁移后重建 MQ/应用加载新增权限，不能重新 provision 覆盖既有 Secret。集成入口包含 `scripts.t3_control_smoke` 和 `scripts.t3_credential_smoke`，使用合成学校及实际数据库验证故障/竞态；合成任务终结后再恢复真实 Worker，未启动采集或 SMTP Worker。见 [凭据与许可决策](../docs/decisions/T3凭据协调与发送许可.md)。

## T4 采集引擎升级

独立故障验收的 `t4-fault` 目录保留宿主机属主，使用 GID 10001 和 0770 权限，让普通用户与 smoke 容器均可访问各自的日志/状态文件；正式 Secret 权限不变。CI 与 PR 合并门禁见 [GitHub 协作与合并流程](../docs/GitHub协作与合并流程.md)。

新增三个独立监控进程，长期进程增至25个；monitoring_0004保存采集时的间隔。保留原Secret与卷，重复upgrade_controls后重建RabbitMQ和全部相关应用以加载新文件挂载/权限，运行migrate，再启动新Scheduler/Worker/恢复器。不要重新provision已有Secret。

monitor.run_ready和room.history_sync_requested为持久签名唤醒；任务以MySQL为准，MQ失效时仍扫描。采集Worker每10秒续租，最长90秒，退出宽限100秒；Room/Identity长请求期间验证数据库并更新心跳。仅balance_only，SMTP/支付开关仍默认false。

`test-stack.sh`合成阶段暂停Identity/Room与监控三个进程、Monitoring Relay，运行t4_query_smoke/t4_monitor_smoke；合成监控全部关闭后再恢复。新验收见 [T4采集引擎](../docs/acceptance/T4采集引擎验收记录.md)。

T5新增 monitor-alerts、notification-worker、notification-recovery，长期进程共28个；SMTP默认关闭，仅Worker持有notification_egress出口。升级需要重复upgrade_controls、迁移monitoring_0005/notification_0002并重建RabbitMQ/应用加载Secret。本域密钥、HTTP CONNECT代理和本机TUN排查见 [邮件运行说明](../docs/runbooks/邮件投递与代理排查.md)。

0.11.0新增payment_0004和本人支付取消，仍为30个长期服务；保留原Secret/卷，先迁移再重建Payment/Gateway和两个支付后台进程。独立测试端口可通过ELECT_TEST_HTTP_PORT/ELECT_TEST_HTTPS_PORT覆盖，不停止原项目。

0.12.0交付T7集中回归、加密备份/隔离恢复、运行状态和模拟容量入口；证书部署/更换按用户要求跳过。完整范围与未验事项见 [T7验收](../docs/acceptance/T7验收记录.md)。

本机私网部署使用 `.env.local`、`compose.yaml` 和 `compose.local.yaml`，只发布指定 `10.8.0.88:6874`，暂不配置入口域名/证书；本机SMTP代理问题由 `compose.smtp-direct.yaml` 定向直连解决。首次Secret/邮件导入、显式开关与启停见[本机私网部署](../docs/runbooks/本机私网部署.md)。
