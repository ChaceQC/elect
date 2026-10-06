# Docker低资源后台生命周期

日期：2026-10-04（Asia/Shanghai）；版本：0.17.0。

0.19.7审计R5在既有Room worker和Payment reconciliation角色内分别启用两个执行槽，所有运行模式共用同一循环；各槽独立心跳、任务身份、停止/续租，保留原领域退出预算与副作用边界。只有原上下文/2+1池，无新增角色容器或进程；新旧领取协议不能混跑。规则与三模式真实进程停止证据见[读取与有界调度](../runbooks/读取与有界调度.md)和[R5验收](../acceptance/审计修复/R5读取与调度优化.md)。

0.19.5审计R3统一健康与进程监督；本页旧版本背景保留，当前判定、三模式退出预算与Compose宽限以[后台健康与协调退出](../runbooks/后台健康与协调退出.md)为准。SELECT 1/有效续租只更新tick或在途证据，不能刷新业务成功；连续业务失败60秒、角色异常或OCR卡住触发进程fatal，恢复false无监督线程。完整CI compatibility增加R3三模式容器重启及不重放验证。

0.18.3追加Payment独立回查与Room独立控制异步角色，沿用原池/统一退出，不增加容器；standalone在原Worker内运行对应TaskGroup。支付与解绑正常2秒回查及页面规则见[自动更新决策](支付与解绑自动更新.md)。

0.14.0以Monitoring验证[优化方案](../Docker低资源部署优化方案.md)第一步；0.15.0推广到七域，形成第二步13个长期容器的轻量组合。0.16.0调整共享池、基础服务、探针与OCR，见[资源参数决策](Docker低资源资源参数.md)。0.17.0第四步已引入成功提交后的本域Outbox提示/空闲退避、有界推送与两个监控执行槽，见[执行效率决策](Docker低资源执行效率.md)；2核2GB容量尚未验收。

## 运行模式与角色

- `ELECT_PROCESS_MODE=standalone`是默认模式，API不启动后台，原独立入口继续可用。
- `ELECT_PROCESS_MODE=combined`在七域API中启动受监督的asyncio任务，使用API已有的本域engine、按需复用ServiceClient及运行Secret。没有额外Python子进程；Gateway仍无业务库和后台。
- `ELECT_BACKGROUND_ENABLED=false`优先禁止合并角色和全部独立后台。恢复覆盖强制false，应用启动不会自动领取任务；模式和开关严格校验。
- 轻量覆盖将17个旧后台放入非默认profile并设置combined，使手工指定旧服务也拒绝独立启动。Notification发送Worker保持独立，显式使用standalone；只给它SMTP出口。

| 领域 | 合并角色 | 统一退出预算 | 容器宽限 |
| --- | --- | --- | --- |
| Identity | Relay、恢复 | 125秒 | 135秒 |
| School Adapter | Relay、过期暂存清理 | 30秒 | 40秒 |
| Room | Relay、同步/余额/历史任务、独立控制（默认/绑定/解绑） | 125秒 | 135秒 |
| Monitoring | Relay、Scheduler、Worker、恢复、提醒回报 | 100秒 | 110秒 |
| Notification | Relay、恢复；发送另设独立Worker | 30秒 | 40秒（发送仍45秒） |
| Payment | Relay、建单/取码Worker、独立回查、恢复 | 180秒 | 190秒 |
| Audit | 消费 | 30秒 | 40秒 |

跨容器旧版本误启仍由原数据库租约、幂等和epoch保护；进程选择不是业务权威。七域独立库/账号、Secret、事件签名、内部TLS和学校/支付/邮件开关不改变。

## 共享、监督与退出

`BackgroundSupervisor`复用业务初始化后的上下文，不重新加载Secret或创建连接池。`BrokerHub`按领域共享一条AMQP连接；Relay、采集/回报、Room历史及Payment唤醒使用独立channel，保留confirm、手动ACK及消费者prefetch=1。角色退出先释放channel，最后关闭共享连接。独立发送Worker有自己的运行上下文和连接。

每个角色写独立`/tmp/elect-job-health/<service>-<role>.json`，启动清空旧成功状态；成功扫描/提交、连接tick和有效租约续期分别记录。API健康返回`background_roles`，包含状态、最近推进、处理和失败计数，Monitoring两个执行槽在slots中独立判定。意外返回、异常、取消、心跳过期或持续业务失败超预算返回503并触发协调退出；live可响应不能掩盖后台故障。MQ等暂不可用但持久扫描仍推进时显示degraded。20秒窗口用于活跃角色，Relay/Audit及15秒扫描恢复器使用45秒窗口；Docker探针在combined改为30秒/启动5秒，独立角色心跳及20/45秒失效窗口保持原值。

Monitoring每轮处理MQ提示后仍尝试MySQL持久领取；重复/已终结提示不能使数据库扫描跳过，否则旧队列积压会延迟新任务。领取前再次核对停止事件，签名/Inbox/提交后ACK及持久执行幂等保持原边界。

Uvicorn统一处理SIGTERM/SIGINT，先设置停止事件，再退出HTTP。角色不开始下一次领取；Identity逐登录检查停止事件，Room在控制、同步、余额、历史各项之间检查，Payment在唤醒后再次检查。已领取任务保持原120/90/170秒处理、续租/取消/提交规则，退出预算从收到停止信号开始计时，不叠加HTTP和后台两套等待。预算耗尽才取消余留任务，租约与未知结果由原恢复器接管，不删除台账或自动重发。

## 编排与运维

`deploy/compose.low-resource.yaml`将基础长期容器30→13，Python进程26→9；可选SMTP通道另加1个。第一步`compose.monitoring-combined.yaml`保留作单域试点对照（25个长期容器），不要同时加载两份合并覆盖。

`deploy/compose.sh`按公开`ELECT_DEPLOYMENT_MODE=standalone|combined`选择模式。顺序为base → local（若HTTP）→ smtp-direct（若显式启用且非恢复）→ test（仅隔离测试）→ browser（仅前端隔离检查）→ low-resource（若combined）→ ops → restore（若恢复）。status/backup/restore/upgrade共用此入口，不source或执行dotenv内容。私网模式由`ELECT_ALLOW_LOCAL_HTTP=true`选择；通道须另设`ELECT_SMTP_DIRECT_ENABLED=true`，不由邮件文件存在推断。

已有卷切换使用`sh deploy/upgrade.sh /absolute/stack.env 项目名`：配置检查后停止API、发送Worker和全部旧profile角色，再启动基础服务、迁移、TLS预检与应用。镜像须已构建，使用`--no-build`；不重新provision、不删除卷。直接对已有独立部署执行普通up不能保证旧角色已停止。原业务项目本轮保持停机。

恢复最后应用`compose.restore.yaml`，同时禁止七域合并任务与所有独立入口。`restore.sh`检查全部profile的运行进程，避免旧Worker因profile隐藏绕过停机门禁；恢复完全不加载host网络SMTP通道。无出口、空库检查、会话/凭据与监控屏障、未知写入和旧Outbox隔离保持原规则，见[恢复手册](../runbooks/备份恢复与隔离对账.md)。

## 隔离验证入口

仅在新的测试项目运行，不读取auth.txt/email_auth.txt或调用真实学校/SMTP/支付：

```sh
sh deploy/test-stack.sh /absolute/new-test-dir elect-test-name combined
sh deploy/test-low-resource.sh /absolute/new-test-dir elect-test-name
sh deploy/test-resource-parameters.sh /absolute/new-test-dir elect-test-name
sh deploy/test-t7-recovery.sh /absolute/new-test-dir elect-test-name
```

test-stack同时支持省略第三参数的standalone；合成阶段停止合并API，避免生产SchoolSessions领取假账号。第二条验证实际七域健康、MQ断线持久扫描、恢复只启动API而无后台、合成同进程任务，以及原卷从13→30→13的双向升级。恢复验证保留unknown和Outbox隔离。证据见[第一步验收](../acceptance/Docker低资源第一步验收.md)和[第二步验收](../acceptance/Docker低资源第二步验收.md)。

轻量模式仍有8个持库进程（七域API及独立发送Worker），池为2+1，理论24条应用连接；MySQL上限40，为迁移、备份和运维留出16条。执行效率已通过[第四步验收](../acceptance/Docker低资源第四步验收.md)，固定镜像发布与目标机验收按第五至六步推进；已有Secret须重复离线upgrade_controls并重建MQ加载绑定确认最小权限。进程数、短时内存快照和本机合成恢复均不能替代2核2GB/50人/24小时容量或生产灾备验收。
