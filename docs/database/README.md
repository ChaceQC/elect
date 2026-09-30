# T0 数据结构与初始化

更新日期：2026-10-01。七个库共有 47 张领域/事件表，每库另有独立 alembic_version；没有业务种子数据。

| 领域 | 数据库 | 初始 revision | 领域/事件表数 |
| --- | --- | --- | --- |
| Identity | elect_identity | identity_0001 | 7 |
| School Adapter | elect_school | school_0001 | 7 |
| Room | elect_room | room_0001 | 10 |
| Monitoring | elect_monitoring | monitoring_0001 | 12 |
| Payment | elect_payment | payment_0001 | 4 |
| Notification | elect_notification | notification_0001 | 4 |
| Audit | elect_audit | audit_0001 | 3 |

[schema-catalog.json](schema-catalog.json)从初始迁移导出列类型、null、主键、唯一键、CHECK、外键、生成列与查询索引。可执行定义在 backend/services/{domain}/migrations/versions/0001_initial.py；后续变更使用新 revision，不改已发布迁移。

业务 ID 用 BINARY(16)，hash 用 BINARY(32)，UTC DATETIME(6)、Shanghai DATE、DECIMAL(14,2)/DECIMAL(18,4)。本库 FK 为 RESTRICT，不跨库 FK、不级联删除审计/任务历史。`created_at/updated_at` 有数据库默认值，后续写操作由领域服务更新 updated_at。

关键约束包括：每用户一个 monitor/default preference、唯一计划 (monitor_id,generation,scheduled_for)、单 run 单成功 sample、唯一 episode/ordinal、单 alert_slot 单 notification_job、本用户/键唯一订单。生成列约束一个 open episode、一个未解决目标绑定、一个并行默认切换及同用户/绑定一笔未解决订单。CHECK 固定状态枚举、正版本、整数间隔与次数；绑定默认采用复合外键保护本人归属，active 状态仍需领域事务校验。

新增 schedule_anchor_at、run.version、history_sync_windows、credential_operations、control_operations、payment_sessions 和持久快照成员表，覆盖状态恢复与联调字段。current_run/current_episode/last_sample 的循环引用在表创建后建立本库外键。

## 初始化与验证边界

开发入口支持每域独立升级及离线 MySQL DDL；在线 URL 必须由本域 `ELECT_{DOMAIN}_DDL_URL_FILE` 提供且指向对应库。临时 MySQL 8.4.8 已验证七域在线升级两次、业务表为空、无跨库 FK、运行账号无 DDL/跨库权限，并验证监控间隔、唯一计划/样本和未知订单屏障。

T1 仍需正式 provisioning、probe、Compose 健康依赖、统一迁移锁与非 root 作业。此处的临时数据库验收不代表目标机器已完成全栈部署。

暂存清理先按 attempt 查询激活结果，未激活且过期才能清；expired lease 提升 epoch 后恢复，不删除任务；unknown 操作/投递/订单保留台账；快照先清成员后清快照。日常清理及归档在容量/恢复验收后启用。细节见 [T0 决策](../decisions/T0实施决策.md)。
