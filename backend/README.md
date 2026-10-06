# 后端工程

0.20.1恢复门禁增加跨库观测水位校验，缺失/倒退保持隔离并拒绝恢复完成；见[集成恢复手册](../docs/runbooks/审计修复集成与恢复.md)。

R6新增Identity本库会话接口`/auth/session`，与依赖Adapter的旧`/auth/me`分开；旧Me和登录响应保持兼容。无新增数据库迁移或Secret；协议和回退见[本地会话与学校资料](../docs/runbooks/本地会话与学校资料.md)。

0.19.7读取优化：会话每60秒条件续期、monitor GET无写一致性读、样本重复索引、Payment回查和Room三类读取各两个公平执行槽。连接池与学校预算不变；升级须monitoring_0010。实现/回退规则见[读取与有界调度](../docs/runbooks/读取与有界调度.md)，验证见[R5专项](../docs/acceptance/审计修复/R5读取与调度优化.md)。

0.19.6增加三域请求预算、支付系统来源验证、公平快照回收及冷热归档/去重，升级须七域新增迁移；[受理与保留规则](../docs/runbooks/请求预算与保留归档.md)记录参数、默认dry-run维护入口与回退限制。既有分派诊断、后台健康与三模式fatal/drain见[后台健康与协调退出](../docs/runbooks/后台健康与协调退出.md)。

0.19.1增加采集快照复用、受理配额及每60秒的小批到期清理，历史同步在本人锁内检查速率/待办/窗口配额。升级先应用`monitoring_0006`和`room_0005`，构建迁移清单已同步；不新增进程或Secret，详见[查询资源规则](../docs/decisions/查询资源受理与快照清理.md)。

0.19.0新增`python -m services.core`，一个Web服务和各领域上下文运行Gateway及六个业务域，School Adapter和邮件发送仍为独立进程。邮件入口不创建FastAPI应用；运行时读取构建生成的migration_heads.json，不加载Alembic。`ELECT_DEPLOYMENT_MODE=core`及回退/安全边界见[七容器方案](../docs/decisions/七容器核心组合.md)，下文业务规则沿用0.18.3。

后台自动认证每轮最多获取5张验证码、提交2次登录，仅在明确拒绝后换新图重试；保持总deadline、账号限流与人工修复，见[认证规则](../docs/decisions/后台认证与刷新反馈.md)。

沿用0.18.3业务规则：支付确认与建单/取码独立调度，Room控制与历史查询分开运行；正常支付/解绑每2秒安排回查，失败退避30秒，沿用原租约，见[自动更新规则](../docs/decisions/支付与解绑自动更新.md)。采集保存C02日读数；支付仍按[D04与原票据规则](../docs/decisions/电表读数与缴费结果确认.md)确认，协议2026-10-04.1与既有安全栅栏保持。

0.18.0增加已受测runtime镜像的CI固定版本/摘要发布及只依赖Docker的串行启动。镜像带版本/源提交标签，目标机发布配置无构建入口；见[运行手册](../docs/runbooks/固定镜像发布与启动.md)。第五步页面请求/数据清理和目标机容量尚未完成。

0.17.0在13容器共享生命周期上接通事务成功提交后的Outbox提示、1→2→5→10秒空闲退避、有界basic.consume和两个监控执行槽；邮件发送Worker保持独立单槽，签名/Inbox/提交后ACK、持久扫描/续租/取消不变，见[执行效率决策](../docs/decisions/Docker低资源执行效率.md)。默认仍为standalone；combined配置、升级与恢复方式见[生命周期决策](../docs/decisions/Docker低资源后台生命周期.md)。combined固定每池2+1、MySQL上限40，基础服务与OCR参数延续0.16.0，见[资源决策](../docs/decisions/Docker低资源资源参数.md)；2核2GB/50人容量仍待验收。

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

配置/真实烟测/临时 MySQL 验证见 [开发说明](../docs/开发说明.md)，表结构见 [数据结构](../docs/database/README.md)。普通 pytest 不执行真实学校检查。Docker构建使用BuildKit缓存复用锁定依赖，两段uv sync均保留--locked；缓存仅在构建阶段使用，不复制到生产镜像。`docker build -t elect-backend:v0.18.3 backend` 在仓库根构建；服务使用 `python -m services.gateway` 等入口，须挂载对应运行 Secret 并配置 ELECT_PUBLIC_ORIGIN，正式编排已在 deploy/compose.yaml 交付。页面能力以当前服务端开关与状态为准。

容器检查在仓库根执行 `sh deploy/check.sh`，全新一次性集成使用 `sh deploy/test-stack.sh /absolute/new-directory elect-test-name`，包含 T2 合成上游、T3 控制及凭据/发送许可竞态检查，不调用真实学校或 SMTP。显式真实学校烟测独立执行，不进入 CI。Room 默认受理/恢复/补偿与首次同步默认初始化已接通；scripts.t3_default_smoke 验证响应丢失、迟到租约、目标失效和切换中关闭。绑定已实现幂等台账/一次 dispatch/B02 回查及默认子操作，三级筛选与本人 Binding 读取已接通；指定目标真实新增已通过 [绑定验收](../docs/acceptance/T3绑定与界面验收记录.md)。删除已接通单次 POST 方法覆盖/两次缺席/默认清空屏障与租约证明，指定同一目标真实删除通过 [删除验收](../docs/acceptance/T3删除绑定验收记录.md)。M1 已完成；真实采集/邮件/支付进入 T4/T5/T6。

T4 查询首批已接通余额/刷新、C02持久窗口/内容快照、日周月聚合和总览后端；[增量验收](../docs/acceptance/T4查询验收记录.md)记录逐寝室余额隔离与数据库故障验证。采集与前端继续接入；未知日期不补零，覆盖证据未确认时不返回 complete。

T4采集引擎见 [增量验收](../docs/acceptance/T4采集引擎验收记录.md)。新增monitor-scheduler/monitor-worker/monitor-recovery、运行/取消/采集快照与内部指标；head为monitoring_0004。只采余额，未发送邮件，前端与阶段故障回归继续接入。

T4整体已通过 [完整验收](../docs/acceptance/T4验收记录.md)，真实本人B02/C02与一次持久采集、实际依赖/进程故障通过。下一步P6邮件事件与发送，未执行SMTP/支付。

T5 episode/slot、跨事件冷却、可释放序号与独立采集周期故障已接通，head 为 monitoring_0005；见 [事件验收](../docs/acceptance/T5事件验收记录.md)。Notification 投递继续实施，不将合成计数写入视为 SMTP 验收。

T5/P6 已完成，版本0.9.0，head 为 monitoring_0005、notification_0002。持久邮件 job、当前许可、DATA 边界、三次重试/unknown、不确定结果镜像、独立故障计数与本域邮箱密钥接通。真实本人 B02 到指定 SMTP 一次投递并由用户确认收件；见 [T5验收](../docs/acceptance/T5验收记录.md)。下一步 P7-01 支付能力/幂等台账。

0.10.0接通T6能力/幂等订单、Adapter D01及E01–E04、本人图片、持久Worker/恢复器和D02/D04安全回查。新增school_0006、payment_0002/0003。`scripts.t6_smoke`使用实际MySQL与合成学校验证一次发送、并发/未知屏障与迟到租约；精确状态映射仍为空，真实支付未验收，默认关闭。见[T6决策](../docs/decisions/T6支付与二维码.md)。

0.12.0交付T7集中回归、加密备份/隔离恢复、运行状态和模拟容量入口；证书部署/更换按用户要求跳过。完整范围与未验事项见 [T7验收](../docs/acceptance/T7验收记录.md)。

0.13.0增加显式私网HTTP部署、对应会话Cookie和安全随机UUID兼容、用户指定SMTP Secret导入及物理网卡定向出口；部署与验证范围见[本机私网部署](../docs/runbooks/本机私网部署.md)。
