# API 契约

0.22.6沿用balance_refresh_state=failed：尚无operation时，余额刷新受理返回404 NOT_FOUND视为绑定明确失效，订单保持paid_confirmed、balance_refresh_operation_id为null、error_code保留NOT_FOUND，并结束自动回查。429/503、解绑处理中409与已受理operation的状态查询失败仍pending/30秒重试；见[余额受理失败终结](../decisions/付款后余额受理失败终结.md)。不新增接口字段或枚举。

0.22.5付款后余额任务必须独立读取B02，不能复用付款确认前的余额根结果；同订单原键仍返回同一operation，旧未终结payment别名按原ID恢复独立读取。公开/内部字段与状态保持，succeeded表示付款确认后重新查询学校余额，不保证余额已增加；见[付款后余额独立读取](../decisions/付款后余额独立读取.md)。

0.22.4沿用已有SchoolOrderResult、订单rejected与操作failed，不新增接口字段。Adapter在本库事务中将尚未发送的凭据版本/授权失效持久化为rejected，Payment收到台账结果后终结并释放未解决槽；旧键仍返回原订单。已有发送台账优先，通用SCHOOL_REAUTH_REQUIRED或NOT_FOUND错误本身不能证明未发送，发送后继续未知保护；见[发送边界](../decisions/建单凭据失效与发送边界.md)。

0.22.0新增GET /room-bindings/{id}/payment-records与PaymentRecords契约，当前公开36个方法/路径；内部新增Payment /browser/records与Adapter /payments/records，沿用payment:browser、school:payment。实缴金额全范围合计、部分结果null及学校渠道边界见[规则](../decisions/学校缴费明细列表.md)。

0.21.1的Consumption桶/汇总amount按日合并学校与监控余额变化估算：学校非零金额优先；缺失或0且有余额减少时补估算，每日首次有效余额减少先归前一天，再按归属日期筛选、合并并聚合周/月。Bucket/ConsumptionSummary可选estimated_amount、estimated_days标明估算部分；Consumption可选monitoring_status标明降级，version包含归属所选范围的样本数，0.22.1起complete按known_days等于expected_days判断，0金额计入已知日期，估算来源独立标注；coverage同步为complete/partial/unknown，普通数据状态按合并覆盖更新，学校同步进行中/失败及依赖降级不被覆盖。内部增加Monitoring的/browser/consumption，沿用monitor:browser；原余额变化/电表字段不变，规则见[消费趋势合并](../decisions/消费趋势合并监控估算.md)。

R6新增`GET /auth/session`及`LocalSession`，仅返回Identity本库用户ID、CSRF和同意记录；旧`/auth/me`及登录完整Me保持兼容。当前公开35个方法/路径，内部55个静态路由。失效401/依赖503与前端兼容规则见[本地会话与学校资料](../runbooks/本地会话与学校资料.md)。

R5.1公开DTO不变：会话每请求权威校验，续期每60秒合并（12小时滑动最多60秒粒度差异、7天绝对上限）。`/auth/me`在Identity一次校验，内部`/browser/me`允许已签名Gateway不携带用户上下文，由会话自行建立；若携带上下文仍检查归属。monitor GET返回独立一致性快照，规则见[读取与有界调度](../runbooks/读取与有界调度.md)。

0.19.6审计R4完成，最终业务提交d5faff6快速CI/check成功：三域预算、快照公平回收、180天保留、冷热去重及七库加密恢复已接通。规则、迁移和未部署边界见[请求预算与保留归档](../runbooks/请求预算与保留归档.md)。

当前版本：0.22.0；T0 冻结基线 0.1.0，更新日期：2026-10-06。此目录定义目标行为，业务服务按总计划的 T1–T6 分阶段实现。

0.19.4公开DTO不变，Balance.fetched_at为最后成功取得学校结果的观察时间，未知旧缓存不伪造新鲜度。内部BalanceReading统一序号/结果时间/错误，三入口共用比较；HistoryExecutionQuery传剩余预算。支付余额业务失败终结自动跟踪，读取暂时失败保持pending/30秒。内部命令和schemas已同步，详见[执行与余额语义](../runbooks/余额观测与历史执行边界.md)。

0.19.3修复历史合并请求的多窗口终态传播，登录增加进程内持锁执行门；公开DTO、幂等/授权和429重试格式不变。GET_LOCK获取前的资源等待至多250ms，沿用RATE_LIMITED及3秒重试提示；原challenge/attempt保留。运行与存量边界见[维护手册](../runbooks/历史合并修复与登录执行门.md)。

0.19.2仅新增客户端协议阅读提示与成功登录后的本地版本/摘要记忆；LoginRequest、协议版本、明确同意及后台授权校验不变，不自动勾选同意。规则见[界面与登录](../decisions/界面状态与登录授权.md)。

core模式公开API和领域DTO不变。核心内部52个接口直接复用原身份依赖、参数与返回模型；独立Adapter/邮件通过`https://identity:8000/domains/{domain}/internal/v1/...`访问相同领域协议，沿用原issuer/audience/scope和Identity证书。部署模式不引入全权core服务身份，也不允许跨库查询；详见[核心组合](../decisions/七容器核心组合.md)。

0.18.3不改变DTO或学校确认条件。订单GET只读本地状态，回查由独立持久调度负责；支付/解绑每2秒自动更新，规则见[支付与解绑自动更新](../decisions/支付与解绑自动更新.md)。

当前协议2026-10-04.1已将后台授权并入登录/重新认证同意，LoginRequest.credential_use_allowed须为true（false或缺失返回422）。历史未授权凭据保持原状，需本人阅读新版协议重新认证。Bindings.binding_write_enabled默认为false，由Room根据当前副作用开关返回，供入口提前展示绑定/解绑限制；写接口仍独立校验，旧未知请求可按原键查询。详见[界面规则](../decisions/界面状态与登录授权.md)。

## 公开 API

[openapi.yaml](openapi.yaml)包含全部 35 个方法/路径。由后端 Pydantic DTO 和 `backend/services/gateway/contract_routes.py` 生成，前端提交对应 `generated.d.ts`；不得只修改夹具绕过契约。变更在同一提交同步源、契约、类型、场景及验收。

- 同源 `/api/v1`；Cookie 为 `__Host-elect_session`，Secure/HttpOnly/SameSite=Lax/Path=/、不设置 Domain。全部敏感响应 no-store。显式私网 HTTP 模式使用 elect_session_local/elect_browser_local（HttpOnly/SameSite=Lax/Path=/、不设 Domain）；模式由服务端校验的 Origin 决定，Origin/CSRF 与归属校验保留。
- 匿名验证码/登录使用浏览器 nonce、Origin 与限流；已有会话的重认证还要校验当前会话与 CSRF，登录接口不得静默切账号，账号不同返回 `409 REAUTH_ACCOUNT_MISMATCH`。
- 受保护写请求使用 Origin 和内存 `X-CSRF-Token`；每次实时 introspection，依赖不可用时拒绝新写入。对象不属于本人返回不可枚举 404。
- 成功信封为 data/meta；失败为 error/meta，meta 包含 request_id 与带时区 server_time；logout 204 无正文。429 使用 Retry-After，错误中 retry_after_seconds 表达相同等待期。
- 金额为 `DECIMAL(14,2)` 对应的固定两位十进制字符串，读数为 `DECIMAL(18,4)` 对应固定四位字符串；不接受 float、科学计数法、NaN/Infinity。未知为 null。
- 0.20.3采集Sample新增可选meter_capture_delta，表示本次meter_reading减previous_sample_id对应止码；相同为0、首次/任一缺失为null、负差保留，固定四位小数（相减允许15位整数）。分页/日期筛选不改变基线，学校原始meter_delta等字段含义不变；旧后端缺字段时前端显示—。
- 日期是上海自然日期，范围含首尾、最多 366 天、不能超过 server_time 对应上海今天；数据库边界转成 UTC 半开区间。日/周一至周日/月桶只计选中范围，缺失日保持 unknown。
- 所有 202 均由 MySQL 事务持久受理后返回；操作、运行和订单分别用 `/operations/{id}`、`/monitor/runs/{id}`、`/payment-orders/{id}`查询。QR GET 的 202 代表原订单的持久二维码工作，不创建新订单。
- 绑定、同步、余额/历史刷新、立即采集、建单及二维码刷新使用 Idempotency-Key，长度 16..128，按用户+操作类型分区。相同键不同摘要返回 `409 IDEMPOTENCY_CONFLICT`，网络重试保持原键；台账至少 180 天，unknown 不普通过期清除。
- 配置、默认、撤回和取消分别使用 monitor.version、preference_version、credential_version、run.version。缺失 expected_version 返回 428，冲突返回 409 与 current_version；租约心跳不修改客户端版本。PATCH/PUT 响应丢失先 GET 对账，不自动重放覆盖并发值。
- 0.22.3起PATCH /monitor因开启或修改间隔而触发立即采集时，与POST /monitor/runs共享每用户6次/分钟、48次/滚动24小时、8个非终态映射的预算。额度不足返回429/Retry-After，配置、版本、代次、旧任务和计划均不改变；成功响应的current_run可直接包含本次持久任务，next_run_at指向下一定期槽。关闭、无变化保存和非采集配置不新增计额；相同版本的并发保存仍先执行409版本检查。

## 恢复与未确定状态

`/room-bindings` 提供最多 20 条本人待完成摘要，含截断标识；当前默认切换 ID 独立返回，避免被摘要上限挤掉。摘要只含 ID、类型、状态、目标和时间；每条恢复前重新校验归属。`/auth/me` 提供正在撤回的操作。能力接口提供当前绑定的未解决订单引用，订单始终返回原寝室/金额/currency，未知 QR 有效期为 null。

监控控制状态与健康状态分别返回；current_run 和 last_run 包含版本，notification 摘要提供发送中、失败、结果未知、最近错误、重试时间和在途数。关闭只提交 enabled=false 与版本，不因其他未保存草稿或学校离线失败。普通退出保留后台授权；撤回先提交监控/提醒屏障再撤销密文/token。

`unknown/reconciling/submit_unknown/status_unknown/delivery_unknown` 使用 [状态模型](states.yaml)的恢复入口；等待超时不等于失败，二维码成功不等于支付成功。默认切换、绑定确认分别呈现 binding_status/default_status。

## 采集快照

首个明细查询固定本人/绑定/日期范围的已提交样本 ID 集合，在 Monitoring 持久保存 `sample_snapshots` 和 `sample_snapshot_items`，按 captured_at DESC,id DESC 排序，total 是此集合大小。TTL 初值 30 分钟，expires_at 随响应返回；期间新增或迟到样本不加入该集合。

- 后续页复用 token，页码从 1 开始，每页默认 10、最大 100；超出末页返回空 items 与同一 total。
- 换绑定、范围、账号或主动刷新清空 token/page；换粒度只影响消费聚合，不改变明细范围。
- 前端第一页可见时每60秒不带token读取最新集合，恢复可见时重新读取已过期的查询缓存；后续页停止定时刷新并复用原token，分页缓存按token隔离。total是当前日期范围的快照总数，没有50条上限。
- 已存在的 token 过期返回 `410 SNAPSHOT_EXPIRED`，保留日期/草稿，提示重新加载第一页；范围不匹配返回 `400 SNAPSHOT_MISMATCH`。已清理、不存在或其他用户的 token 返回 404，避免暴露他人快照是否存在。
- 快照 TTL 内保留成员样本，归档不能破坏集合；过期先清成员再清快照，不级联删除历史。token 只保存 hash，不暴露业务 ID 集合。
- 0.19.1首页按本人/绑定/范围及有序成员摘要复用有效快照，不续期；迟到提交产生新集合。token以独立用途HMAC重建，密钥轮换后旧token仍按hash验证至到期。
- 每用户最多6个新快照/分钟、12个保留快照和60,000成员，单快照最多20,000条（超过时429并提示缩小范围，不截断）。过期但未清理的快照仍计入存量；有效token分页不扣创建额度。recovery每60秒清理最多4个过期快照/共1,000成员，先子后父，分页共享锁防止并发清理破坏响应。

## 历史同步受理

0.19.1在本人偏好行锁内先检查幂等重放，再检查新operation预算（每分钟6个、24小时24个、非终态最多8个，包含合并别名）。相同幂等键重放不扣额度，摘要冲突仍409；每用户未完成sync最多2个、未完成窗口最多64个。被当前同绑定同步范围完整覆盖时合并到原操作；部分重叠保留独立请求并计入配额，成功缓存不阻止显式刷新。拒绝返回`429 RATE_LIMITED`、`Retry-After`和`retry_after_seconds`，不持久化新operation/sync/窗口/Outbox。operation保留原至少180天的幂等契约，执行租约、每账号串行及学校限制不变。详见[受理规则](../decisions/查询资源受理与快照清理.md)。

## 内部协议与场景

[内部命令](internal/commands.yaml)声明服务调用白名单、幂等边界和 DTO 引用；[schemas.json](internal/schemas.json)是后端内部 DTO 导出。[事件登记](events/registry.yaml)声明生产者、消费者、schema_version、聚合版本和去重键；内部事件 DTO 验证载荷与生产者，不含敏感材料。Outbox/Inbox 属于各域，不用消息替代 MySQL 权威状态。

0.17.0仅更新版本及事件传输实现说明，公共字段与事件schema不变：事务成功提交后本进程提示、空闲最多10秒扫描及有界basic.consume/prefetch=1；原签名、Inbox、提交后ACK与持久恢复规则保留。

前端 MSW 场景位于 `frontend/src/mocks/scenarios.json`，覆盖空账户、有绑定、学校失败、部分历史、默认切换中、运行取消、未知订单和快照过期；普通 CI 对响应按 OpenAPI 校验。学校夹具为合成数据，不能作为真实支付状态映射证据。生产入口不导入 mocks，也不注册 service worker。

生成与检查命令见 [开发说明](../开发说明.md)，按钮、字段和实现阶段见 [需求追踪](../T0需求追踪表.md)。

## T2 当前实现

公开认证五接口、本人绑定列表/持久同步/候选和 operation 查询已接通；后续阶段仍返回 FEATURE_DISABLED。LoginRequest 密码 1..1024、challenge 43..128；学号 1..128 且无空白/控制字符，不限制为参考页面的纯数字正则。当前协议已将后台授权并入登录同意（2026-10-04.1），新登录/重认证须传credential_use_allowed=true；历史未授权凭据仍不进行后台密码认证。SessionContext 内部增加本人 CSRF；凭据激活内部命令携带显式 credential_use_allowed，凭据失效新增 credential.requires_reauth 持久广播。

T2 默认 id 始终为已有偏好或 null，不自行初始化。首次成功空列表 sync_status=empty，首次失败 failed；该阶段采用缺席复核；现行0.13.1按用户要求，成功B02列表覆盖当前绑定，缺席记录inactive并保留历史；原默认仍在保留，不在选学校列表第一项，成功空列表清空默认/监控目标。查询失败才保留原列表并标记stale。B03 候选固定 unverified，完整记录仅在服务端加密短期缓存。细节见 [实施决策](../decisions/T2认证与读取.md)。

## T3 第一批增量

GET/PATCH monitor 已接通，首次幂等创建 disabled 记录；版本匹配且配置无变化不增加 version/generation，旧版本即便重放相同值仍 409（含 current_version），响应丢失先 GET。缺 expected_version 为 428。等待重新认证仍可保存参数；关闭不调用学校/缓存/MQ/SMTP。

内部 retarget 完成必须查询 Room 持久操作证明，新增 OperationQuery/PreferenceProof。单次取消已完成本域原语，公开 run 接口按 T4 接入；默认切换、真实绑定及监控设置界面继续按阶段实施。T3 控制不运行采集/邮件。详见 [控制决策](../decisions/T3监控控制基础.md)。

## T3 第二批增量

公开撤回返回持久 202，使用 credential_version；同用户/旧版本重放返回原操作。me 返回真实 revoked/revoking 状态和待完成摘要，Gateway 在 Room/Identity 固定白名单查询本人 operation。应用会话保留，consent 记录 revoked_at；旧登录重放不能重新签发已撤回版本的会话。

内部新增 UpdateCredentialBarrier、CredentialProof、prepare/commit/abort-update、barrier/control-view、commit-revoke；Adapter 自行读取持久屏障，Monitoring 自行读取当前凭据证明。Notification 发送许可已实现 job/epoch 持久去重、30 秒到期和当前代次/邮箱/样本/冷却检查；实际 SMTP 留待 T5。详见 [凭据与许可决策](../decisions/T3凭据协调与发送许可.md)。

## T3 筛选与绑定增量

新增本人 GET /room-candidates/buildings、/floors（building_id 必填）、/rooms（building_id/floor 必填）和 /room-bindings/{id}；统一 FilterChoices 返回 items[].id/label，读取绑定返回 Binding。前端按三级筛选取得列表后在列表内搜索，选择 roomId 再核对精确候选。写绑定必须使用服务器候选和原幂等键，existing_operation_id 仅返回本人的未解决操作。详见 [绑定决策](../decisions/T3绑定筛选与异步界面.md)。

## 删除绑定增量

`DELETE /room-bindings/{id}` 使用 Idempotency-Key、Origin/CSRF，返回持久 202 并查询原 operation；无学校 ID/正文/自动重试。Operation 新增 unbind_room 和 binding_status=removed；Bindings 独立返回 binding_removal_operation_id 与 preference_state，避免摘要截断影响恢复。默认删除保留旧显示直到学校确认，再清空默认并等待监控确认；未知态保留操作槽。详见 [删除决策](../decisions/T3删除绑定.md)。

## T5投递与状态

AlertSlotQuery/AlertSnapshot仅Notification受限本人上下文读取，包含邮箱明文仅在内部请求中传输，不能进入MQ。投递事件增加execution_epoch及retry_wait/脱敏error_code/next_retry_at；结果由job版本/许可epoch与Inbox防重。Monitor.failed_cycles与NotificationSummary.delivery_enabled为兼容新增字段，发送默认关闭。slot镜像持久错误/重试时间，unknown永久占一个名额。当前首次投递后最多三次重试，1/5/15分钟，固定Message-ID不代表SMTP去重。见 [T5决策](../decisions/T5低余额与邮件.md)。

## T6订单增量

能力、建单和订单读取接入本人会话与内部 payment:browser 权限。capabilities.amount_policy_source=application_policy，金额初始为1–500元整数；不是学校确认上限。原键重放返回原订单，键同内容不同409，同用户/寝室未解决订单以409 existing_operation_id恢复，不能换键重建。订单新增qr_error_code、balance_refresh_state/operation_id（兼容默认）；尚未确认付款时不计算充值后余额。学校写入/二维码/真实状态继续实施，普通部署开关仍关闭。

T6后续接通原订单QR/qr-refresh和三域operation查询。QR 200仅image/png或image/jpeg（二进制/no-store），202为QRPending JSON；未知表单只查原结果，不重发。订单余额刷新状态的succeeded仅表示School余额已重新查询，不表示本地已加到账。内部SchoolOrderResult/SchoolQRResult/PaymentImage/PaymentDispatchProof及实际路径已同步；Adapter独占票据密文。

## 支付本地取消

`POST /payment-orders/{id}/cancel` 使用本人Cookie、Origin、CSRF与 `expected_version`，返回含 `version/cancel_pending/cancelled_at` 的 Order；订单ID使重复取消返回原结果，不需要新的幂等键。缺版本428、冲突409、跨用户404；已确认付款不能取消。取消停止本系统执行，不撤销学校订单或退款，不删除D01/E02/E03台账。未取得许可的后续发送被阻断；已有运行等待原租约安全边界结束，随后释放未解决槽。旧键仍返回原订单，不重新派发；二维码读取/刷新拒绝取消订单。学校只读核对仍可记录原订单真实终态。

## 本机受理拒绝与本地重试

FEATURE_DISABLED即使返回503也表示该功能未受理，客户端清理该未受理意图及弹窗冻结状态；DEPENDENCY_UNAVAILABLE/网络超时保留原幂等请求。历史无操作ID的绑定/删除恢复记录可由用户停止本地重试，仅移除浏览器那一条记录，不发学校请求、不撤销服务端/学校受理，其他未知记录和服务端进度继续保留。

0.18.0更新发布版本元数据；公共字段与事件schema保持不变，固定摘要镜像与启动配置见[运行手册](../runbooks/固定镜像发布与启动.md)。
