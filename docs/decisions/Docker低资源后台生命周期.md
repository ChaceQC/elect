# Docker低资源后台生命周期

日期：2026-10-03（Asia/Shanghai）；版本：0.14.0。

本批实现[优化方案](../Docker低资源部署优化方案.md)第一步，先以Monitoring验证同一Python进程内的API、Relay、Scheduler、Worker、恢复器和提醒回报处理。其他领域尚未合并，MySQL/Redis/RabbitMQ参数与连接池上限不变。本批不是13容器或2核2GB容量交付。

## 运行模式

- `ELECT_PROCESS_MODE=standalone`为默认模式：API不启动后台，原独立角色入口继续可用。
- `ELECT_PROCESS_MODE=combined`目前仅支持Monitoring API，启动全部五个必需后台角色。无Supervisor子进程，每角色是一个受监督的asyncio任务，使用API已有的本域engine、ServiceClient和运行Secret。
- `ELECT_BACKGROUND_ENABLED=false`优先禁止合并角色和全部独立后台入口。该开关已加入恢复覆盖文件；应用可只读对账，但不会因为API启动而自动运行后台。两项变量严格校验，不接受其他拼写。
- 独立入口在combined模式直接拒绝启动；试点Compose同时将五个旧角色放入非默认profile。误指定旧服务不能在合并容器之外重复启动进程。跨容器的旧版本误启仍由原数据库租约、幂等和epoch保护，不能把进程开关视为新的业务权威。

## 共享和监督

`BackgroundSupervisor`复用业务初始化后的上下文，不重新加载Secret或创建连接池。`BrokerHub`按领域共享一条AMQP连接；Relay、运行提示消费者和投递回报消费者各自使用独立channel，保留confirm、手动ACK和消费者prefetch=1。角色关闭只释放自己的channel，全部任务退出后才释放共享连接。

每个角色写入独立的`/tmp/elect-job-health/<service>-<role>.json`，启动时清空旧成功状态，成功扫描/领取/提交或真实续租才更新成功心跳。API健康返回`background_roles`，包含各角色状态、最近推进时间、处理与失败计数。角色意外返回、异常退出、被取消或心跳过期返回503；进程仍可响应`/health/live`不能掩盖后台故障。数据库/迁移失败仍返回503；持续推进但MQ等依赖暂不可用时显示degraded，API继续受理已持久控制。

Scheduler/Worker/alerts心跳有效窗口20秒；15秒扫描的恢复器和最长30秒重连退避的Relay使用45秒。业务循环继续使用原扫描周期，本批不提前降低探针或扫描频率。未知状态、采集重试、代次屏障、SMTP DATA许可和支付发送边界不改变。

## 退出边界

Uvicorn入口统一处理SIGTERM/SIGINT，先设置后台停止事件，再进入HTTP退出。角色不再开始下一次领取，已领取任务保留原续租/取消/提交规则；Monitoring最多等待100秒，再取消剩余异步任务。退出预算从收到停止信号开始计时，覆盖API退出与后台等待，不叠加两个100秒窗口。数据库、HTTP客户端和共享AMQP连接在角色退出后关闭；强制取消留下的租约由原恢复器接管，不清空台账或自动重发。

Monitoring试点容器宽限110秒，给90秒采集预算和资源关闭留出余量。其他领域仍保留原独立Worker预算，邮件和支付没有合并进Monitoring，也没有缩短其发送边界。

## 编排与验证入口

`deploy/compose.monitoring-combined.yaml`是第一步试点覆盖，顺序为base → test/local覆盖（若有）→ monitoring-combined → ops → restore（若恢复）。当前基础长期容器从30降至25；Python进程从26降至21。其余领域推广、正式轻量编排和统一运维配置组合属于第二步，不默认切换现有部署。

恢复时必须最后应用`compose.restore.yaml`，其`ELECT_BACKGROUND_ENABLED=false`覆盖试点默认值。旧Worker/Relay还保留恢复profile，入口级禁用保证即使显式指定profile也无法自动启动。恢复入口原有无出口、空库、停止业务进程和旧Outbox隔离不变。

仅在新的隔离测试项目运行：

```sh
sh deploy/test-stack.sh /absolute/new-test-dir elect-test-name
sh deploy/test-monitoring-combined.sh /absolute/new-test-dir elect-test-name
```

第二条先验证真实Monitoring容器内API和五角色健康，再暂停测试项目的后台，以同进程合成学校验证调度/采集、取消、角色退出可见、租约接管、重启和在途退出。脚本不读取auth.txt/email_auth.txt，不调用学校/SMTP/支付；不会恢复原业务项目。

本批验收记录见[第一步验收](../acceptance/Docker低资源第一步验收.md)。2核2GB冷启动、50人/24小时、OCR和备份峰值仍按优化方案后续验收，不能根据进程数下降提前宣称资源达标。

## 第二步源码推广（2026-10-03，编排验收中）

公共角色工厂已覆盖七域；Gateway不增加业务库或角色。Identity为Relay/恢复，Adapter为Relay/清理，Room为Relay/任务，Notification为Relay/恢复（发送独立），Payment为Relay/执行/恢复，Audit为消费。Room历史及Payment唤醒消费者使用本域共享连接、独立channel，角色退出先释放channel再关闭共享连接。

Identity/Room收到停止信号后不继续处理下一项登录、同步、余额或历史任务；Payment消费唤醒后再次检查停止事件再领取订单。统一退出预算为Identity/Room125秒、Monitoring100秒、Payment180秒、其余30秒；保持原120/90/170秒在途处理预算。本批尚未交付正式轻量覆盖，基础服务参数、扫描周期和连接池上限不变。
