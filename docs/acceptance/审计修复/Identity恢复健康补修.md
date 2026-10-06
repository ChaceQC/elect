# Identity恢复健康补修（AUD-14 / AUD-07）

日期：2026-10-06（Asia/Shanghai）。输入：干净dev `03a99b1`；补修版本0.20.2。状态：本缺口源码、定向验证及最新quick/check已通过，补修完成；现有部署未升级。

## 缺口与结论修正

原登录恢复捕获ApiError后以候选行是否存在返回，生产business_loop把正常返回记作健康成功，导致identity_committed/activating下游持续503不能积累60秒失败预算。撤回恢复存在相同的异常吞没；单纯抛异常也不足以解决5秒退避期间空扫描清空失败的问题。

R3、R7原“全部闭合”结论因此需修正。[R7](R7集成兼容与恢复.md)中8928b51的[full37464974149](https://github.com/ChaceQC/elect/actions/runs/37464974149)和quick仍是有效历史证据，但没有覆盖本路径，也不属于0.20.2完整验证。本次仅补修此缺口及同入口关联分支，不重跑全部R7场景。

## 实现与不变量

- [执行门](../../../backend/services/identity/application/login_gate.py)增加ApiError子类LoginBusy，公开429/错误码/Retry-After不变；仅本地执行门或命名锁繁忙可正常跳过，下游429不使用这条豁免。
- [恢复入口](../../../backend/services/identity/recovery.py)仅把实际推进或合法失败终结计作activity；未终结的依赖错误保留在既有error_code中，继续使用5秒重试。记录错误不回写旧阶段，不能覆盖已终结或被前台推进的状态。
- 每次准备报告恢复成功前，用同一个Identity库检查仍待恢复且带错误的登录/撤回记录。未到期扫描、执行门繁忙、同批成功或优先处理的撤回成功均不能掩盖失败。只返回布尔存在性，不读取凭据字段，不扩业务池。
- [登录状态](../../../backend/services/identity/application/login.py)写入中间阶段时保留既有错误，前台重试尚在激活也不能提前清错；终态退出恢复查询。提交身份前的明确业务拒绝仍可标记failed并作为正常处理完成。
- [撤回](../../../backend/services/identity/revocation.py)持久保存reconciling/error/重试时间后继续抛出错误；真正完成时按既有事务清错。
- 公共business_loop、Heartbeat、health_state和ProcessControl沿用原实现：未恢复错误进入healthy=False，60秒后not_ready并通知协调停止；暂时失败实际恢复后清除连续失败。统计次数表示失败的恢复轮次，包含等待轮次，不等于下游请求次数。

无迁移、新Secret、公开DTO、学校并发、业务池、进程或容器数量变化。未启动/停止现有部署，未读取真实凭据、调用学校/SMTP/支付或执行生产存量apply。

## 定向证据

使用WSL Ubuntu-24.04的Python3.12.10检查镜像，只读挂载当前源码；MySQL8.4.6为internal网络/tmpfs一次性环境，生产2+1连接池，无业务配置/凭据和外发。

| 入口 | 结果与边界 |
| --- | --- |
| [恢复健康专项](../../../backend/tests/integration/test_identity_recovery_health.py)首轮10项 + 原[test_login_resources](../../../backend/tests/integration/test_login_resources.py)5项 | 15 passed（23.62秒），实际Saga、命名锁、MySQL事务、recover_tick、business_loop、Heartbeat、BackgroundSupervisor、ProcessControl判定；下游及时间为合成 |
| 连续失败 | identity_committed、activating和撤回各持续503；含真实到期筛选的退避空扫描，61轮时单调时间已过60秒，最后原因为BUSINESS_FAILURE_BUDGET，业务成功时间保持None，协调stop已设置，连接全部归还 |
| 恢复/边界 | 暂时503恢复后实际完成才ready；本地门繁忙71轮不记失败/activity；下游429/404持续失败不伪装本地门忙；撤回成功与前台激活中间写入不能清掉另一个待恢复错误 |
| 相邻单元检查 | test_login_gate、test_domain_background、test_health_progress共24 passed（4.70秒）；断网容器执行 |

随后新增提交身份前明确拒绝的终态回归，并在已有失败场景补充本地门忙不能清错的断言；两项定向复核2 passed（3.54秒），合计覆盖11项恢复健康专项。新增专项已纳入deploy/test-query-resources.sh默认列表，CI实际MySQL入口会执行，不以普通pytest的跳过代替通过。

第一次用stdin执行原部署测试脚本时工作目录不匹配，测试文件未找到，未执行测试；修正调用目录后得到上述通过结果，不计失败启动为验收。所有临时容器/网络由入口清理。

可控时钟直接调用生产监督判定，证明本路径已连接fatal/协调stop；没有把它写成真实60秒等待、操作系统退出或容器重启验收。R3既有三模式真实进程/容器证据保持原SHA；本轮不宣称重测或升级生产。

## 门禁与下一步

- 本地ruff已通过；版本0.20.2同步前后端包、锁文件及OpenAPI元数据，接口和依赖不变。
- 最终源码/测试提交`6a95627b4c1e99cc86ca8ef4bbac76eb3a9c6687`已push到origin/dev；[quick37485986038](https://github.com/ChaceQC/elect/actions/runs/37485986038)于2026-10-06 23:22:11（Asia/Shanghai）completed/success。backend / build、frontend / build和check均success，business/compatibility/delivery及publish按quick规则skipped，无发布。
- 该SHA后端普通入口345 passed/102 skipped（119.79秒），一次性MySQL98 passed（136.95秒，包含本次11项恢复健康专项）；前端62项、浏览器46项（40.2秒）通过。跳过项不计通过，新增专项有独立MySQL执行证据。未运行本版本full，不宣称R7已经对0.20.2重新执行完整验证。
- 首次提交768586ca8f1ed16cf6ebf2a6bf0b807c81cea726已push；[quick37483740551](https://github.com/ChaceQC/elect/actions/runs/37483740551)前端成功，后端344 passed/102 skipped/1 failed。失败来自OpenAPI生成脚本版本仍为0.20.1，与本次0.20.2公开契约不一致；补齐生成常量后重新验证，恢复源码保持不变，旧失败不作为成功门禁。
- 生成版本修正后公开契约定向3 passed（2.35秒）；第一次本地调用缺少前端合成响应只读挂载，补全挂载后通过，未改动响应夹具或接口。
- 本缺口按源码/定向验证和quick门禁关闭；R3/R7原结论以本页补修证据修正。部署、真实目标、生产异机/PITR及长期容量仍独立待验收。下一次完整交付先针对最终候选运行full，再核对目标模式、七域迁移、备份/维护窗口及回退镜像；本次不自动执行。
- 最终收尾仅同步Markdown，检查UTF-8/链接和Git差异后提交推送；按当前workflow的paths-ignore不触发CI，不将文档提交记为额外受测业务SHA。
