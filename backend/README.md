# 后端工程

T0 工程/DTO/状态模型与七域初始 Alembic 迁移已完成。T1 已建立非 root Docker 镜像、八个 API 骨架、Secret 加载、UTC 连接池、脱敏日志、统一错误、live/ready、Ed25519 服务认证与 TLS 预检、Outbox/Inbox、Relay 与 Audit Worker；业务 API 在后续阶段实现。Python 固定为 3.12.10，使用 uv 管理独立依赖。

T2 后端已实现正式 httpx 学校认证、Redis 原子验证码、密文暂存/激活、持久登录恢复、应用 Cookie/CSRF、本人绑定同步与候选分页。真实学校指定账号认证、1 条本人绑定、候选第一页、退出与后台认证恢复已通过；生产前端/阶段验收见 [T2 记录](../docs/acceptance/T2验收记录.md)。设计与真实证据见 [T2 决策](../docs/decisions/T2认证与读取.md)。

T3 已接通 GET/PATCH monitor、配置/取消/代次事务、提交屏障、持久 retarget 与 Room 证明查询；Identity 登录先 prepare-update 再激活/确认，公开撤回返回持久操作，恢复器按屏障、Adapter 删除、Monitoring 确认续作。撤回清除历史密码暂存与旧 token，保留应用会话；Notification 发送前许可核对当前样本/代次/邮箱/冷却，尚无 SMTP Worker。见 [控制决策](../docs/decisions/T3监控控制基础.md)、[凭据决策](../docs/decisions/T3凭据协调与发送许可.md) 与 [增量验收](../docs/acceptance/T3凭据与许可验收记录.md)。新 head 为 identity_0003、school_0005、room_0004、monitoring_0003；现有 T2/T3 部署先重复运行 upgrade_controls 再迁移。

开发机安装 uv 后执行：

```sh
cd backend
uv sync --locked
uv run ruff check .
uv run pytest -q
uv run python -m scripts.generate_openapi --check
uv run python -m scripts.generate_protocols --check
uv run python -m scripts.schema_catalog --check
uv run python -m scripts.migrations --domain all --sql --output-dir /tmp/elect-ddl
```

配置/真实烟测/临时 MySQL 验证见 [开发说明](../docs/开发说明.md)，表结构见 [数据结构](../docs/database/README.md)。普通 pytest 不执行真实学校检查。`docker build -t elect-backend:v0.9.0 backend` 在仓库根构建；服务使用 `python -m services.gateway` 等入口，须挂载对应运行 Secret 并配置 ELECT_PUBLIC_ORIGIN，正式编排已在 deploy/compose.yaml 交付。T2 认证/读取及 T3 监控配置/撤回路由已接通；后续阶段入口返回 FEATURE_DISABLED。

容器检查在仓库根执行 `sh deploy/check.sh`，全新一次性集成使用 `sh deploy/test-stack.sh /absolute/new-directory elect-test-name`，包含 T2 合成上游、T3 控制及凭据/发送许可竞态检查，不调用真实学校或 SMTP。显式真实学校烟测独立执行，不进入 CI。Room 默认受理/恢复/补偿与首次同步默认初始化已接通；scripts.t3_default_smoke 验证响应丢失、迟到租约、目标失效和切换中关闭。绑定已实现幂等台账/一次 dispatch/B02 回查及默认子操作，三级筛选与本人 Binding 读取已接通；指定目标真实新增已通过 [绑定验收](../docs/acceptance/T3绑定与界面验收记录.md)。删除已接通单次 POST 方法覆盖/两次缺席/默认清空屏障与租约证明，指定同一目标真实删除通过 [删除验收](../docs/acceptance/T3删除绑定验收记录.md)。M1 已完成；真实采集/邮件/支付进入 T4/T5/T6。

T4 查询首批已接通余额/刷新、C02持久窗口/内容快照、日周月聚合和总览后端；[增量验收](../docs/acceptance/T4查询验收记录.md)记录逐寝室余额隔离与数据库故障验证。采集与前端继续接入；未知日期不补零，覆盖证据未确认时不返回 complete。

T4采集引擎见 [增量验收](../docs/acceptance/T4采集引擎验收记录.md)。新增monitor-scheduler/monitor-worker/monitor-recovery、运行/取消/采集快照与内部指标；head为monitoring_0004。只采余额，未发送邮件，前端与阶段故障回归继续接入。

T4整体已通过 [完整验收](../docs/acceptance/T4验收记录.md)，真实本人B02/C02与一次持久采集、实际依赖/进程故障通过。下一步P6邮件事件与发送，未执行SMTP/支付。

T5 episode/slot、跨事件冷却、可释放序号与独立采集周期故障已接通，head 为 monitoring_0005；见 [事件验收](../docs/acceptance/T5事件验收记录.md)。Notification 投递继续实施，不将合成计数写入视为 SMTP 验收。

T5/P6 已完成，版本0.9.0，head 为 monitoring_0005、notification_0002。持久邮件 job、当前许可、DATA 边界、三次重试/unknown、不确定结果镜像、独立故障计数与本域邮箱密钥接通。真实本人 B02 到指定 SMTP 一次投递并由用户确认收件；见 [T5验收](../docs/acceptance/T5验收记录.md)。下一步 P7-01 支付能力/幂等台账。
