# T3 默认 Saga 增量验收

日期：2026-10-01（Asia/Shanghai）。版本 0.5.0。T3 整体继续进行。

Room `PUT /room-preferences/default` 事务受理后返回 202；已有同目标/版本操作返回原 ID，默认无变化返回 200，缺版本 428、冲突/并发 409、非本人 active 目标 404。成功同步按学校 room ID 稳定顺序创建初始默认操作，偏好与监控确认前保留 switching。

既有 Room Worker 扫描默认与同步，持久租约防止迟到 Worker 推进。锁顺序为 preference → operation → sync_state/绑定；外部调用不持事务锁。prepare → 偏好提交 → commit 逐步保存，响应丢失按同操作恢复；偏好提交后向前完成。失效目标在未提交时明确进入补偿阶段，经 Monitoring 回查本域证明后采用新代次恢复旧目标；补偿完成后才公开 failed。

验证入口为 `scripts.t3_default_smoke`，已接入 `deploy/test-stack.sh`。实际 MySQL/Redis、签名内部 ASGI 调用验证：首次稳定默认、prepare/commit 响应丢失、偏好提交后进程恢复、迟到租约拒绝、目标失效补偿、并发默认受理、428/404/409、无变化 200，以及 active 监控切换中关闭后完成仍保持 disabled。后端 90 项离线测试和 ruff/契约/目录检查通过。

本批不执行真实绑定写入。用户新指定的枫苑5号-402 已通过学校三级筛选只读定位并核对 B03 目标字段，尚未执行 batchAdd。下一步完成一次 dispatch 台账、首次绑定默认子操作和 F3/F5 界面后，再执行该明确目标的真实验收。采集、SMTP 和支付仍属后续阶段。
