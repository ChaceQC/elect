# 数据结构与初始化

更新日期：2026-10-01。七个库共有 51 张领域/事件表，每库另有独立 alembic_version；没有业务种子数据。

| 领域 | 数据库 | 当前 revision | 领域/事件表数 |
| --- | --- | --- | --- |
| Identity | elect_identity | identity_0003 | 7 |
| School Adapter | elect_school | school_0005 | 9 |
| Room | elect_room | room_0004 | 11 |
| Monitoring | elect_monitoring | monitoring_0003 | 13 |
| Payment | elect_payment | payment_0001 | 4 |
| Notification | elect_notification | notification_0001 | 4 |
| Audit | elect_audit | audit_0001 | 3 |

[schema-catalog.json](schema-catalog.json)按迁移链导出当前 head 的列类型、null、主键、唯一键、CHECK、外键、生成列与查询索引。可执行定义在 backend/services/{domain}/migrations/versions/0001_initial.py；后续变更使用新 revision，不改已发布迁移。

业务 ID 用 BINARY(16)，hash 用 BINARY(32)，UTC DATETIME(6)、Shanghai DATE、DECIMAL(14,2)/DECIMAL(18,4)。本库 FK 为 RESTRICT，不跨库 FK、不级联删除审计/任务历史。`created_at/updated_at` 有数据库默认值，后续写操作由领域服务更新 updated_at。

关键约束包括：每用户一个 monitor/default preference、唯一计划 (monitor_id,generation,scheduled_for)、单 run 单成功 sample、唯一 episode/ordinal、单 alert_slot 单 notification_job、本用户/键唯一订单。生成列约束一个 open episode、一个未解决目标绑定、一个并行默认切换及同用户/绑定一笔未解决订单。CHECK 固定状态枚举、正版本、整数间隔与次数；绑定默认采用复合外键保护本人归属，active 状态仍需领域事务校验。

新增 schedule_anchor_at、run.version、history_sync_windows、credential_operations、control_operations、payment_sessions 和持久快照成员表，覆盖状态恢复与联调字段。current_run/current_episode/last_sample 的循环引用在表创建后建立本库外键。

## 初始化与验证边界

开发入口支持每域独立升级及离线 MySQL DDL；在线 URL 必须由本域 `ELECT_{DOMAIN}_DDL_URL_FILE` 提供且指向对应库。临时 MySQL 8.4.8 已验证七域在线升级两次、业务表为空、无跨库 FK、运行账号无 DDL/跨库权限，并验证监控间隔、唯一计划/样本和未知订单屏障。

T1 已通过正式 provisioning/Compose 验收。T2 新增 Identity 登录恢复元数据、School 账号占位/授权标记和 Room 同步状态/任务租约，已在实际 MySQL 8.4 验证。运行事务采用 READ COMMITTED、学校 room ID 使用 binary collation，详情见 [T2 决策](../decisions/T2认证与读取.md)。

T3 第一批 monitoring_0002 增加 monitors.preference_version、credential_operation_id、credential_allowed，以及 control_operations.request_digest、previous_binding_id、credential_version；支持幂等控制、补偿及凭据屏障，不回改初始迁移。邮箱密文使用独立多版本 AES-GCM 密钥，AAD 绑定 owner/email_version。

第二批 identity_0003 增加 users.credential_version/status/operation_id 与 credential_operations 用户+版本唯一键；school_0003 增加 account_display 密文和 credential_revocations；monitoring_0003 增加 send_permits，job_id/execution_epoch 唯一且引用本域 slot。撤回会清空当前凭据和全部历史 activated/staged 密码暂存，展示账号单独加密，旧 token 清理可恢复。见 [凭据/许可决策](../decisions/T3凭据协调与发送许可.md)。

暂存清理先按 attempt 查询激活结果，未激活且过期才能清；expired lease 提升 epoch 后恢复，不删除任务；unknown 操作/投递/订单保留台账；快照先清成员后清快照。日常清理及归档在容量/恢复验收后启用。细节见 [T0 决策](../decisions/T0实施决策.md)。

第三批 school_0004 增加 upstream_operations 加密候选/脱敏 B02 确认记录、binary 目标比较与同用户未解决目标唯一约束；room_0003 增加候选/凭据快照、绑定/默认状态和默认子操作引用。学校 dispatched 后不能重新发送，unknown 不能普通过期清除。详见 [绑定决策](../decisions/T3绑定筛选与异步界面.md)。

删除增量 room_0004 增加 unbind_room/removed 状态、新增与解绑共用目标唯一屏障、removal_was_default 和 room_preferences.removal_operation_id；school_0005 扩展解绑类型/目标约束及 absence_first_at。inactive 保留缓存/历史，不进行物理删除，显式清空默认后 preference.state=blocked 防止下一次同步擅自重选。
