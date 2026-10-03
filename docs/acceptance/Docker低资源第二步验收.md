# Docker低资源优化第二步验收

日期：2026-10-03（Asia/Shanghai）；版本：0.15.0。对应[优化方案](../Docker低资源部署优化方案.md)第二步与[生命周期决策](../decisions/Docker低资源后台生命周期.md)。

## 交付范围

- 七域API与后台共享本域engine/客户端/AMQP连接，独立channel、角色心跳及统一退出；邮件发送Worker独立、Gateway无库。
- `compose.low-resource.yaml`形成13个基础长期容器，Python进程26→9；17个旧角色在非默认profile且独立入口拒绝combined。可选SMTP通道另加1个，本轮未运行。
- `compose.sh`统一公开配置选择，status/backup/restore/upgrade及集成/前端恢复检查使用相同组合。已有卷切换先停止全部旧角色；恢复最后覆盖、不加载host SMTP通道，停机门禁检查全部profile。
- Room/Identity逐项停止新领取，Payment唤醒后检查停止；退出预算保留120/90/170秒在途处理窗口。MQ总等待有界，消息签名、提交后ACK、租约/幂等/代次和unknown边界保留。

## 已完成验证

- 离线`sh deploy/check.sh`通过：后端规则/单位/契约/目录及七域离线迁移，前端49项单元组件、32项浏览器、规则/类型/契约及构建通过。最后MQ积压修正后后端198 passed / 1 skipped，并在容器重跑规则/公开与内部契约/数据库目录通过。
- 新增22项单位用例，覆盖七域上下文复用、邮件发送隔离、停止领取、断开channel总预算、旧提示积压下持续SQL扫描、不执行dotenv、严格配置选择、恢复覆盖顺序/SMTP排除及隐藏旧角色停机门禁。
- `test-stack.sh ... combined`通过：13容器空库初始化、七域独立权限/并发迁移、实际Relay/Audit签名/Inbox去重，T2–T6全部合成回归，实际MySQL/Redis/MQ中断；全部长期容器healthy，内部TLS预检通过。
- `test-low-resource.sh`最终通过：实际七域API/全部角色ready，八条领域AMQP连接（含独立发送Worker），Room/Payment消费者与Relay同连接不同channel；MQ断开后全部持久扫描角色继续推进且API degraded。
- 实际应用restore覆盖，八个API可启动但`background_roles`全部为空，合并与独立入口均被禁止。合成Monitoring验证单run单样本、在途取消、角色故障可见、租约接管/旧epoch拒绝、重启、停止领取后在途提交及连接释放。
- 七域合成学校进程共同运行，Room自动同步/默认Saga，Adapter过期暂存清理；Notification恢复DATA后delivery_unknown，发送角色没有进入API；Payment重复受理自动执行、丢失D01响应并回查，仍仅一次D01。
- 同一卷/Secret执行13→30→13双向upgrade，standalone与combined均全部healthy；最后17个旧后台全部exited，没有两套角色并行运行。
- `test-t7-recovery.sh`通过：实际MySQL加密快照/封存binlog、隔离恢复，62张表计数及密文保留，快照后模拟邮件/建单保持unknown，旧Outbox不自动重放；本机合成RPO4.631秒/RTO77秒，不代表生产异机/PITR或持续灾备。
- 统一前端恢复入口通过：真实生产静态前端/Nginx/Gateway/七域API，1440px/375px四页共8次读取、账户弹窗、同源/CSRF/对象归属及双标签退出，零浏览器错误、无mock路由。测试会话仅由合成学校预置。

## 资源证据与修正

本轮隔离项目在6核、15.51GiB主机，原业务停机。双向升级过程中各做一次Docker CLI快照：30容器2623.91MiB，13容器1376.16MiB，约减少47.6%。[原始组件汇总](Docker低资源第二步资源.json)保留采样时间和口径；这是启动后的短时单次样本，未加载OCR、未运行50人持续负载/备份，未核算宿主机开销，不代表稳态平均、冷启动峰值或2GB容量。

首次MQ断开检查失败：Payment消费者等待Robust channel.ready，Worker心跳过期，API正确503；Room有相同阻塞路径。修正Room/Payment整个唤醒阶段8秒总预算、Notification取消息3秒/建队列8秒及Audit初始化8秒，新增挂起channel回归；实际MQ断开重跑通过，没有改变可靠事件或业务发送规则。

GitHub Actions在3c64651/737f406的Monitoring合成采集入口超时：已终结/重复MQ提示仍返回“有消息处理”，原循环据此跳过持久领取；CI积压较多，延迟领取新运行。修正为每轮处理提示后仍扫描MySQL，并在停止信号后拒绝领取；两项单位用例先复现失败再通过。实际MySQL/Redis/MQ预置50条签名的已终结/重复消息，合并采集、取消、接管/重启及在途退出全部通过；没有靠清空队列或延长验收等待掩盖问题。

宿主机默认Docker地址池已耗尽，本轮只为两个新隔离项目创建未占用的小网段；没有删除历史网络、修改Docker全局配置或恢复原业务。

生产前端恢复脚本首次因旧标题“用电总览/我的寝室/监控提醒”失败，0.13.2正式页面已改为“总览/选择与绑定/监控与预警”。只更新验收定位器，保留原访问/隔离/退出断言，真实容器复验通过；生产页面没有改动。

验证结束只down本轮两个新隔离项目，保留六个命名卷与受限测试证据；所有elect项目运行容器为0，原业务及历史环境继续停止，其他五个容器保留。受影响文档本地链接、版本/锁文件、逐文件Shell语法、真实凭据忽略和Git差异检查通过。

## 未完成范围

第二步无阻塞，第三至六步（资源参数、执行效率、镜像发布/长期运行和2vCPU/2GB/50人24小时验收）未完成。真实D02映射、生产异机/PITR与T8仍未验收；原业务部署继续停机，未读取真实auth.txt/email_auth.txt或访问真实学校/SMTP/支付。
