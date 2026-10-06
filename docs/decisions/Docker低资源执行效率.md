# Docker低资源执行效率

日期：2026-10-04（Asia/Shanghai）；版本：0.17.0，第四步已交付。

0.19.7审计R5扩展读取调度：Room同步/余额/历史共享两个轮转槽，Payment回查两个槽；每次最多32个owner候选、锁忙跳过、独立在途/心跳，保持原2+1池与学校5/4/1。Room空闲1→2→5秒，Payment回查空闲1秒，有工作立即继续；Room慢读取每10秒读库心跳保留。下文第四步历史证据不变，当前读取规则及50合成账号对照见[读取与有界调度](../runbooks/读取与有界调度.md)和[R5验收](../acceptance/审计修复/R5读取与调度优化.md)。

## 提交后唤醒与可靠扫描

`create_database`返回保持SQLAlchemy AsyncEngine接口的`DomainEngine`。本域所有生产写事务仍使用`engine.begin()`；`append_event`只在成功INSERT后设置连接局部标记，`begin()`在数据库COMMIT及事务退出成功后发进程内提示。回滚、取消及提交失败不发提示；连接归还前清除标记，避免池复用误唤醒。没有使用在实际COMMIT之前触发的ConnectionEvents.commit。

提示只属于当前engine，不跨进程传输，不代表发布或消费成功。合并模式中API和Relay共享engine，可立即唤醒；独立模式、进程崩溃或提示丢失仍靠数据库扫描。没有改变数据库结构、公共API、事件字段和外部副作用开关。

Relay空闲扫描采用1→2→5→10秒退避，提示或活动重置；积压最多连续处理16条再让出执行。每条仍独立领取发布租约、签名、等待publisher confirm，再按原owner/租约条件标记。MQ失败保留原持久重试，加1秒范围抖动的指数重连，最大31秒；45秒真实角色心跳窗口保持。未到available_at的事件不会提前发布。

## 实施与验收边界

- 最终容器回归220 passed / 1 skipped，前端49项单元组件/32项浏览器与构建通过；提交/回滚、MQ断线/推送/重复、双槽取消/关闭/排队及原卷升级/恢复隔离通过，见[第四步验收](../acceptance/Docker低资源第四步验收.md)。
- 原业务环境保持停机，未调用真实学校/SMTP/支付，2核2GB/50人24小时未验收；固定镜像发布/分阶段启动及长期运行按第五至六步推进。

## 有界推送与执行

公共`PushConsumer`使用basic.consume，prefetch及本地缓冲均为1；领域入口的get只读取本地缓冲，不再发送basic.get。签名校验、Inbox事务和提交后ACK仍由原领域处理。断线重连使旧缓冲失效并唤醒循环，关闭旧channel后由MQ重排未ACK消息，显式重建consumer；消费者不自动ACK、不在推送回调中执行业务。发布及不同消费者继续使用独立channel。

Monitoring的Worker采用两个TaskGroup执行槽，共用本域engine、client和AMQP连接，各持一个prefetch=1的channel；每槽处理提示后仍尝试持久领取。重复或已终结提示不能饿死SQL扫描，单run仍受原租约/epoch/唯一样本约束。停止事件禁止下一次领取，等待两个在途槽按原90秒预算续租、取消、提交；整体100秒退出预算保留，取消整个Worker同时取消两个槽。Notification邮件Worker保持单槽和独立出口，DATA前许可、有限重试及unknown不变。

| 角色 | 空闲/扫描周期 | 健康与依据 |
| --- | --- | --- |
| Relay、Audit | 1→2→5→10秒，积压每批16条 | 实际扫描/事务/发布推进，45秒心跳窗口 |
| Monitoring Worker | 每槽1→2→5秒，推送到达立即唤醒 | 学校等待每10秒真实续租，20秒窗口 |
| Monitoring提醒回报 | 1→2→5→10秒，推送立即唤醒 | 保留15秒过期提示判定，20秒窗口 |
| Monitoring Scheduler /恢复 | 5 / 15秒 | 原调度锚点、取消/恢复逻辑不变 |
| Notification Worker /恢复 | 1→2→5秒 / 15秒 | 单槽、真实读库/租约检查，20 / 45秒窗口 |
| Payment Worker /恢复 | 1→2→5秒、推送唤醒 / 1秒 | 原发送标记/回查/取消屏障保持 |
| Identity、Room控制 | 1秒 | 保留持久Saga及交互控制响应周期 |
| Room读取（0.19.7） | 每槽1→2→5秒，有工作立即继续 | 两槽/owner互斥、每10秒读库心跳，历史另保留续租 |
| Payment回查（0.19.7） | 每槽空闲1秒，有工作立即继续 | 两槽/owner互斥、原2秒到期计划和10秒续租 |
| Adapter暂存清理 | 60秒，每批最多100行；有积压继续小批 | 空闲每10秒SELECT 1确认真实数据库，20秒窗口；使用凭据时仍独立校验有效性 |

MQ重建尝试间隔为15–16秒；连接/声明整体8秒预算不变，失败时仍由持久扫描继续处理。没有提升学校共享全局5/后台4/账号1的限制，也没有将各角色统一调慢。

## 既有绑定确认事件与升级

隔离回归发现Room已产生的`room.binding_confirmed`缺失发布Topic权限，MQ持续拒绝，Relay正确显示degraded。现在仅给Room增加该事件发布权限，绑定到既有`elect.monitoring.runs`并允许Monitoring读取。Worker将此类提示按原签名规则写Inbox后ACK；不依据提示创建run或绕过持久默认/绑定Saga。没有增加队列或后台角色，恢复器和业务事实继续以MySQL为准。

新provision包含此定义。已有部署保留Secret与原卷，先按统一入口停止全部API/独立Worker/Relay；使用已构建的新后端镜像离线重复原upgrade_controls：

```sh
docker run --rm --network none --user 0:0 \
  -v /opt/elect/secrets:/run/upgrade elect-backend:v0.17.0 \
  python -m services.deployment.upgrade_controls --directory /run/upgrade
```

替换镜像和Secret目录为已审核配置。它原子更新既有runtime/定义，保留密码hash、数据库/Redis/MQ连接凭据、签名及加密密钥；两次升级与旧缺失定义的回归用例通过。随后重建RabbitMQ加载定义，再用upgrade入口启动应用（原结构迁移重复执行为无操作）。不要重新provision已有Secret。只换镜像不加载定义会继续保持Relay降级，不能将该状态当ready。
