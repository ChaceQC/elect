# T0 契约基线

版本：0.1.0；冻结日期：2026-10-01。此目录定义目标行为，业务服务按总计划的 T1–T6 分阶段实现。

## 公开 API

[openapi.yaml](openapi.yaml)包含全部 28 个方法/路径。由后端 Pydantic DTO 和 `backend/services/gateway/contract_routes.py` 生成，前端提交对应 `generated.d.ts`；不得只修改夹具绕过契约。变更在同一提交同步源、契约、类型、场景及验收。

- 同源 `/api/v1`；Cookie 为 `__Host-elect_session`，Secure/HttpOnly/SameSite=Lax/Path=/、不设置 Domain。全部敏感响应 no-store。
- 匿名验证码/登录使用浏览器 nonce、Origin 与限流；已有会话的重认证还要校验当前会话与 CSRF，登录接口不得静默切账号，账号不同返回 `409 REAUTH_ACCOUNT_MISMATCH`。
- 受保护写请求使用 Origin 和内存 `X-CSRF-Token`；每次实时 introspection，依赖不可用时拒绝新写入。对象不属于本人返回不可枚举 404。
- 成功信封为 data/meta；失败为 error/meta，meta 包含 request_id 与带时区 server_time；logout 204 无正文。429 使用 Retry-After，错误中 retry_after_seconds 表达相同等待期。
- 金额为 `DECIMAL(14,2)` 对应的固定两位十进制字符串，读数为 `DECIMAL(18,4)` 对应固定四位字符串；不接受 float、科学计数法、NaN/Infinity。未知为 null。
- 日期是上海自然日期，范围含首尾、最多 366 天、不能超过 server_time 对应上海今天；数据库边界转成 UTC 半开区间。日/周一至周日/月桶只计选中范围，缺失日保持 unknown。
- 所有 202 均由 MySQL 事务持久受理后返回；操作、运行和订单分别用 `/operations/{id}`、`/monitor/runs/{id}`、`/payment-orders/{id}`查询。QR GET 的 202 代表原订单的持久二维码工作，不创建新订单。
- 绑定、同步、余额/历史刷新、立即采集、建单及二维码刷新使用 Idempotency-Key，长度 16..128，按用户+操作类型分区。相同键不同摘要返回 `409 IDEMPOTENCY_CONFLICT`，网络重试保持原键；台账至少 180 天，unknown 不普通过期清除。
- 配置、默认、撤回和取消分别使用 monitor.version、preference_version、credential_version、run.version。缺失 expected_version 返回 428，冲突返回 409 与 current_version；租约心跳不修改客户端版本。PATCH/PUT 响应丢失先 GET 对账，不自动重放覆盖并发值。

## 恢复与未确定状态

`/room-bindings` 提供最多 20 条本人待完成摘要，含截断标识；当前默认切换 ID 独立返回，避免被摘要上限挤掉。摘要只含 ID、类型、状态、目标和时间；每条恢复前重新校验归属。`/auth/me` 提供正在撤回的操作。能力接口提供当前绑定的未解决订单引用，订单始终返回原寝室/金额/currency，未知 QR 有效期为 null。

监控控制状态与健康状态分别返回；current_run 和 last_run 包含版本，notification 摘要提供发送中、失败、结果未知、最近错误、重试时间和在途数。关闭只提交 enabled=false 与版本，不因其他未保存草稿或学校离线失败。普通退出保留后台授权；撤回先提交监控/提醒屏障再撤销密文/token。

`unknown/reconciling/submit_unknown/status_unknown/delivery_unknown` 使用 [状态模型](states.yaml)的恢复入口；等待超时不等于失败，二维码成功不等于支付成功。默认切换、绑定确认分别呈现 binding_status/default_status。

## 采集快照

首个明细查询固定本人/绑定/日期范围的已提交样本 ID 集合，在 Monitoring 持久保存 `sample_snapshots` 和 `sample_snapshot_items`，按 captured_at DESC,id DESC 排序，total 是此集合大小。TTL 初值 30 分钟，expires_at 随响应返回；期间新增或迟到样本不加入该集合。

- 后续页复用 token，页码从 1 开始，每页默认 10、最大 100；超出末页返回空 items 与同一 total。
- 换绑定、范围、账号或主动刷新清空 token/page；换粒度只影响消费聚合，不改变明细范围。
- token 过期/服务端快照丢失返回 `410 SNAPSHOT_EXPIRED`，保留日期/草稿，提示重新加载第一页；范围不匹配返回 `400 SNAPSHOT_MISMATCH`，其他用户 token 返回 404。
- 快照 TTL 内保留成员样本，归档不能破坏集合；过期先清成员再清快照，不级联删除历史。token 只保存 hash，不暴露业务 ID 集合。

## 内部协议与场景

[内部命令](internal/commands.yaml)声明服务调用白名单、幂等边界和 DTO 引用；[schemas.json](internal/schemas.json)是后端内部 DTO 导出。[事件登记](events/registry.yaml)声明生产者、消费者、schema_version、聚合版本和去重键；内部事件 DTO 验证载荷与生产者，不含敏感材料。Outbox/Inbox 属于各域，不用消息替代 MySQL 权威状态。

前端 MSW 场景位于 `frontend/src/mocks/scenarios.json`，覆盖空账户、有绑定、学校失败、部分历史、默认切换中、运行取消、未知订单和快照过期；普通 CI 对响应按 OpenAPI 校验。学校夹具为合成数据，不能作为真实支付状态映射证据。生产入口不导入 mocks，也不注册 service worker。

生成与检查命令见 [开发说明](../开发说明.md)，按钮、字段和实现阶段见 [需求追踪](../T0需求追踪表.md)。
