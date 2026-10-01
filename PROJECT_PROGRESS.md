## 2026-10-02 · 按学校快照覆盖绑定与默认回退（0.13.1）

### 已完成

- 本机部署与HTTP/绑定受理修复415d242已提交推送dev，最新Actions36936491533全部成功。
- 根据用户明确规则，成功且结构有效的学校B02列表完整覆盖当前绑定；缺席记录inactive且保留历史，默认仍在就保留，不在按学校返回的第一项回退，成功空列表清空默认及监控目标。
- 复用已有默认/监控Saga，支持null目标清空；持久保存成功快照第一项，在途默认失效补偿后按最近成功快照重新对齐，不直接绕过监控屏障修改默认。查询失败不覆盖，未知学校写台账不清除。
- 修复已部署v0.13.1。本机真实本人验证码登录/同步通过，当前列表与学校均1间、无旧rechecking条目，当前有效默认保留；手动余额刷新202及服务端succeeded、新鲜余额读取通过。桌面/手机四页、HTTP会话/CSRF、停止本地重试、双标签退出均通过，0页面异常/0测试学校绑定写。
- 同步当前规则、契约/架构/AGENTS、前后端版本/锁文件、部署模板和独立SQL回归；新t7_sync_smoke加入test-stack/CI。

### 进行中

- 本机部署与此次同步规则修复已交付；真实D02自动终态、生产异机/PITR和T8发布仍按原计划继续。

### 阻塞与风险

- 本机部署无阻塞。学校失败/异常响应仍保留最近数据，不能当成空列表；按用户明确规则，成功空列表会清空当前绑定/默认，历史与未知写入证据保留。
- 域名/入口证书暂不配置，唯一项目入口10.8.0.88:6874；指定SMTP启用并使用物理网卡定向出口，公共支付保持关闭。

### 下一步

- 只读取得本人1元订单D02/D04正确关联与真实终态证据，再补齐支付自动终态验收；T8前配置异机备份/PITR和发布回滚清单。

### 主要文件或模块

- Room mirror/repository/sync_defaults/defaults/default_saga；t2/t3回归、t7_sync_smoke、test-stack和真实浏览器脚本；版本/锁文件及相关架构/契约/部署文档。

### 验证

- 后端ruff/166项测试通过、1项专用MySQL跳过，公开/内部契约与七域目录通过；前端lint/typecheck/47项测试/契约类型/生产构建通过。锁文件最终审查恢复两处误改的第三方Node最低版本，逐包比对确认仅项目版本变化，第三方依赖元数据保持原值。
- 实际隔离MySQL/合成学校验证学校第一项不同于排序、已有默认不变、缺席默认回退、监控跟随/保留历史、失败不覆盖、成功空列表清空、空列表后恢复、在途失效默认补偿后重选；T2、T3默认恢复/租约、绑定、删除必要回归全部通过，没有真实学校写入。
- 真实HTTP浏览器本人同步与新鲜余额刷新通过；默认规则本次命中preserved，缺席/空列表/竞态由隔离SQL验证，分别记录。域名/入口TLS仍跳过，邮件未自动发送正文，不改变此前T5接受/收件记录。

## 2026-10-02 · 本机私网部署与HTTP登录修复（0.13.0）

### 已完成

- 按用户要求建立独立 elect-local 本机部署，入口仅为 http://10.8.0.88:6874；暂不配置域名或入口证书，内部TLS保留。生成新受限Secret、七域空库和独立持久卷，未导入合成业务数据。
- 增加显式私网HTTP模式、精确IPv4/端口Origin校验、独立HTTP会话/nonce Cookie及Nginx Host限制；HTTPS保留原Cookie和证书预检。小网段避免历史验收网络耗尽默认地址池。
- 用户指定使用email_auth.txt；由专用进程内存解析并导入SMTP Secret，本机明确开启SMTP。普通连接被透明代理重置，物理网卡直连/TLS通过；常驻认证通道只接受指定SMTP目标，监听Docker网桥，SMTP密码仅给Notification，不改变全局代理。
- 用户反馈登录页不可用，生产HTTP浏览器复现crypto.randomUUID缺失，修复请求/幂等意图/快照修订为安全getRandomValues UUID v4回退，重建并部署前端。真实学校验证码登录、本人绑定读取、四页×桌面/手机、刷新会话、Origin/CSRF和双标签页退出全部通过。
- 用户绑定页反馈后，本机Room/Adapter/Worker明确开启新增/解绑写开关，仍由用户在页面确认目标后执行。修复503 FEATURE_DISABLED明确未受理仍留恢复记录的问题，增加停止单条历史本地重试（不发学校请求/不撤销学校受理）；依赖503/网络未知继续保留原键。
- 停止已完成的T7合成源/隔离恢复长期容器释放本机资源，保留全部卷和原真实T6项目/订单记录。定向SMTP通道改用轻量标准库健康探针，避免低CPU限额下导入业务依赖导致探针超时。
- 同步README、AGENTS、前后端/部署README、公开Cookie契约/版本、架构、部署与邮件运行说明；本机凭据、env、Secret、验证码/OCR产物不提交。

### 进行中

- 本机部署交付与定向验证已完成；T6真实D02自动终态、生产异机/PITR和T8发布按原计划继续。

### 阻塞与风险

- 本机部署无阻塞。域名/入口证书按用户要求暂不配置，HTTP只用于指定私网入口；根据用户绑定页反馈，本机启用页面确认后的新增/解绑；支付写和支付验收标志仍关闭。
- 用户指出手动余额刷新SCHOOL_INVALID_RESPONSE并确认属于学校错误；该次余额读取未成功，保留未知/最近成功数据，不将页面和登录通过称为本次新鲜余额通过。学校返回有效数据后的余额复核另行记录。
- 本轮SMTP验证到连接/最终TLS/账号认证，没有自动发送正文，不替代T5服务器接受或最终收件证据。真实D02仍待验，不将此前1元到账当作自动终态证据。

### 下一步

- 只读核对本人1元原订单的D02/D04关联与真实终态映射，取得证据后补齐支付验收；T8前配置异机备份/PITR和发布回滚清单。

### 主要文件或模块

- deploy/compose.local.yaml、compose.smtp-direct.yaml、.env.local.example、nginx/local.conf.template；common/runtime、gateway/cookies/api/query_api、deployment/email_auth/configure_smtp/smtp_direct_proxy。
- frontend/lib/uuid、API客户端/意图/采集快照、local-browser专用脚本及HTTP回归；docs/runbooks/本机私网部署.md、docs/acceptance/local-deploy/及受影响契约/文档/锁文件。

### 验证

- 后端ruff、166项测试通过/1项专用MySQL测试跳过，17项新增覆盖HTTP授权/Origin、两种Cookie实际登录/CSRF/退出和SMTP目标/认证/Secret。协议/数据库目录/公开契约检查通过。
- 前端lint/typecheck/47项单元组件/契约类型通过；Docker生产构建成功，HTTP浏览器验证四页×1440/375px、真实学校验证码登录/绑定读取、会话恢复/双标签页退出、跨来源/缺CSRF403和0页面异常；最终复验含历史本地重试停止，实际学校绑定POST为0，无API mock或测试触发的真实学校写入。
- 首次浏览器检查定位HTTP随机ID故障后修复；下一次脚本能力检查遗漏必需binding_id，修正验收请求参数后最终整套通过，未放宽业务校验。
- 31个长期服务全部healthy，七域迁移成功；Nginx语法/入口/healthz/登录协议200。Compose唯一发布10.8.0.88:6874→80，Nginx无入口证书挂载；127.0.0.1及两个物理网卡IPv4的6874连接均被拒绝。
- 由真实Notification Worker配置连接指定SMTP，物理网卡定向通道、最终证书TLS和AUTH认证通过，QUIT结束，message_sent=false；没有关闭TLS验证或输出密码/完整邮件地址。

## 2026-10-02 · T7集中验证与恢复交付

### 已完成

- 0.12.0提供仅Docker的一致性AES-GCM快照/已关闭binlog封存、完整认证/空库/停应用门禁、默认无外发的隔离恢复和运行状态入口，运维与前端交付文档同步。
- 独立源/恢复项目实测62表行数一致、样本和凭据密文可读；快照后模拟D01一次/SMTP接受一封，旧快照恢复后保留unknown且零重发/零采集，重复门禁通过。RPO4.795秒、RTO62秒仅为本机小数据演练。
- 100模拟计划、2 Scheduler、8同进程并发，100唯一样本/签名唤醒，55.36样本/秒、学校峰值5；OCR冷加载107964KiB。连接池总预算125/200和磁盘/积压/未知/队列状态记录。
- 生产静态页面经Nginx/真正Gateway与SQL的无API mock回归通过：四页×两屏宽、跨站/CSRF403、已知他人Binding404、双标签页退出401。补齐44px触控、表格键盘区域、监控错误关联/修正和隐藏时钟暂停。
- 097997f的最新[Actions 36918846146](https://github.com/ChaceQC/elect/actions/runs/36918846146)全部成功，证明此前默认Saga准备不足失败已修复；T7新步骤加入CI，最终本批检查继续跟踪。

### 进行中

- 本批最后检查、提交推送和最新Actions核对，不再扩展本轮范围。

### 阻塞与风险

- 无独立实现阻塞。按用户要求跳过生产证书部署/更换，保留测试HTTPS/内部TLS。真实D02支付映射仍500，未设置验收标志；不将1元用户付款/B02增量混作状态枚举证据。
- 生产异机/PITR/持续15分钟备份频率及人工日历、实际200%缩放/屏幕阅读器尚未验证；本机恢复结果不等于持续生产灾备，T7/M3不提前全勾选。

### 下一步

- 只读核对本人已支付D04明细与1元原订单关联标识，取得D02准确参数/真实终态映射；实际部署前配置异机备份目标并演练PITR/持续频率，再推进T8发布清单。

### 主要文件或模块

- services/deployment备份/恢复/聚合状态、t7恢复/容量/OCR/会话驱动、deploy的ops/restore/t7覆盖与Shell入口、生产浏览器脚本、F7公共组件/样式、CI与docs/runbooks/acceptance/计划。

### 验证

- 后端149通过/1项显式MySQL测试跳过，ruff/契约/目录/DDL通过；新Crypto6项含大文件、错误密钥、截断、篡改/追加和权限。仅Docker全套149后端/41前端/29生产浏览器通过，随后新增监控错误关联定向及包含五屏宽登录的7项回归通过；前端总数42，最终CI再次核对。
- 全新独立test-stack七域与30长期服务健康；实际依赖/进程故障、取消/旧epoch/SMTP模拟边界全部通过。Docker仅需验证与无mock全栈浏览器、加密恢复、容量/OCR分类证据已保存docs/acceptance/t7。
- 首次恢复清点发现MySQL元数据字段大小写问题，改用显式AS name后新隔离演练完整通过；未覆盖失败产物。MySQL强制重建后所有62表结构/行数一致；原真实测试项目未用于合成恢复/压力，未新增真实学校绑定或邮件。

## 2026-10-02 · 支付取消、1元付款与CI失败修复

### 已完成

- 0.11.0新增本人支付取消按钮/API与payment_0004：独立取消意图、版本/归属/CSRF、立即阻断后续派发、在途租约安全结束后释放占位；保留原键和学校永久发送台账，不撤销学校订单、不退款。
- 按用户更新范围取消原10元本地意图，执行一次1元D01/E链路并提供仓库外私人二维码；用户确认成功支付，精确匹配同一寝室的新鲜B02较付款前增加1.00元。
- 查明两次失败Actions（36912271378/36914180079）均在T4依赖prepare的enable断言。T6合成账户仅等绑定就返回，留下默认Saga队列，后续固定推进5次不足。实际复现默认未确认/切换pending、启用422；新增等待本人默认终态的有界测试准备，保留业务拒绝。
- 修复后T6合成/实际MySQL取消通过，实际Redis/MySQL/MQ中断与恢复通过；生产浏览器回归改为build/preview，解决开发按需优化引发空白加载的验证缺口。

### 进行中

- 完整容器离线与29项生产浏览器回归已通过；全新独立项目正在完成健康收尾，提交推送后等待最新GitHub Actions成功。T7备份恢复、容量与运行状态入口随后继续。

### 阻塞与风险

- D02 HTTP200/业务500/data=null，自动支付终态映射未验证；用户付款与B02增量分别记录，T6-04/P7-06/M3不提前完成。公共支付验收标志保持false。
- 本地取消无法保证学校旧二维码失效；提示勿扫描旧码。第一次付款后人工验证码重新登录失败，随后复用既有加密授权只读核对成功，不新增订单。

### 下一步

- 取得本批完整Docker与最新Actions绿色结果，随后实现加密一致性备份及无外发隔离恢复，并测量RPO/RTO。

### 主要文件或模块

- Payment取消/DTO/迁移/恢复、Gateway/OpenAPI与前端取消/原订单恢复；T6真实专用脚本、合成默认准备与依赖故障脚本；锁文件、部署模板和相关契约/学校/验收文档。

### 验证

- 后端ruff与143测试通过，1项需要专用MySQL跳过；公开契约/数据库目录通过，前端取消5项组件及lint/typecheck通过。
- 两个Actions失败日志和本地同条件复现均指向默认Saga准备不足；修复后T6与真实Redis/MySQL/MQ依赖演练通过。完整29项开发服务器浏览器中2项空白加载失败，因此改用生产build/preview后重新验证，不靠重试掩盖。
- 原10元取消与1元建单/付款后只读分类记录已脱敏保存，无私人支付票据/二维码进入仓库。
- 取消后原引用跨组件内存残留已修复，新增独立断言；生产build/preview完整29浏览器、41前端单元组件、143后端通过（1项专用MySQL跳过），deploy/check.sh仅Docker全套通过。

## 2026-10-02 · T7集中验收开始

### 已完成

- 按用户要求开始 T7，阅读总计划、P8、F7/F8、架构与部署文档，核对 dev 工作区干净。
- 明确跳过部署证书/更换域名证书演练，保留测试 HTTPS、内部 TLS 与生产安全约定；T6 真实到账未确认，支付保持关闭。
- 已补齐跨标签页退出/登录通知、旧缓存/草稿清理与后台恢复时会话核对；修复401初始化通知互相触发的问题。五种屏宽四页/弹窗、长错误、日期错误关联、图表观察器释放定向通过。

### 进行中

- 用户追加1元支付与取消支付按钮：先实现本地取消/占位释放与在途栅栏，取消原10元后按新授权建1元订单。T7备份恢复和容量/运行状态入口随后继续。

### 阻塞与风险

- 无独立实施阻塞。T6-04/P7-06 真实状态映射与到账仍未验证，T7/M3 不提前标为全部完成；本轮不执行新的真实副作用。

### 下一步

- 实现支付取消接口、持久取消屏障与界面；验证跨用户404、重复取消、在途拒绝和已支付禁止取消，再执行指定1元验收。

### 主要文件或模块

- frontend 的会话、公共样式、日期选择器及浏览器回归；docs/decisions/T7集中验收与恢复.md；后续 deploy 与 backend/services/deployment。

### 验证

- 已确认 dev 跟踪 origin/dev、仅根 AGENTS.md 生效、无 AGENT.md；现有 elect-test-t6 的30个长期服务健康，后续使用独立项目。
- 前端lint/typecheck与39项单元组件通过；T7新增7项浏览器场景的五种屏宽/图表6项通过，双标签页修复401通知循环后定向通过。初次测试错误选择了无支付入口的明细页，已修正到寝室详情，不更改产品入口。
- 原10元订单真实只读回查仍awaiting_payment，未确认学校终态；未新建1元订单、未执行付款。

## 2026-10-02 · T6订单与二维码实现

### 已完成

- 0.10.0实现T6-01..03/P7-01..05与F6：D01永久单次台账、E01–E04独立会话、E02/E03未知屏障、本人图片、Payment Worker/恢复器/续租/迟到栅栏、签名Outbox/Inbox与安全D02/D04回查。
- 同订单QR并发合并、每原键持久引用和前端响应丢失/关闭重开恢复；不以二维码认定支付、不直接加余额。契约、迁移、部署权限与文档同步。
- 真实本人验证码登录/默认/B02只读通过；当前两个指定关系所需整数为10/11元，已按范围完成一次10元真实D01和E01–E04，二维码ready；原订单awaiting_payment，D02返回SCHOOL_INVALID_RESPONSE，未确认付款。用户要求本轮只交付代码，暂不扫码。

### 进行中

- 本轮代码交付完成：a657620、ff25ff2已推送origin/dev，工作区确认干净，未合入main。仅Docker检查与30个长期服务全部healthy复核通过。T6-04/P7-06等待用户后续付款验收；第二笔未执行，T6/M3不提前完成。

### 阻塞与风险

- 实现无阻塞。学校D02映射尚未验证，默认精确映射为空；同寝室一个未解决订单约束不能为第二笔绕过。公共写与验收标志仍false。

### 下一步

- 下次用户继续付款验收时，只读核对原10元订单的D02/D04及学校余额，取得真实状态映射；首笔确认终结后按最新余额选择较大整数，完成T6-04/P7-06。

### 主要文件或模块

- backend/services/payment与school_adapter支付模块、两个域迁移、gateway、内部DTO、部署权限/Compose、frontend/features/payments、T6烟测/真实专用脚本、docs/contracts/database/decisions/acceptance。

### 验证

- ruff、143项后端测试（1项需专用MySQL跳过）、39项前端测试、完整22项浏览器回归通过；开发服务器初次存在间歇加载失败，单项和完整回归重跑通过。实际MySQL/合成学校验证五并发幂等、跨用户404、二维码MIME/原键合并、响应丢失/阶段恢复、旧epoch拒绝以及不以加法造余额。新增DTO回应校验后的实际MySQL/合成学校回归通过；deploy/check.sh仅Docker执行143后端/39前端/22浏览器及契约/DDL全部通过。真实Redis/MySQL/MQ中断恢复验证通过；依赖故障期间与T6合成测试并发造成503，恢复后串行T6回归通过。

## 2026-10-02 · T6 能力与本地订单首批

### 已完成

- 开始T6：支付能力使用应用1–500元整数政策，标明金额来源；本人建单/订单读取、Payment事务幂等与未解决订单槽位、Outbox/审计、迁移和内部权限已实现。
- DTO/OpenAPI/前端生成类型及数据库目录同步；支付默认关闭，原键重放返回同一订单，不因二维码失败重新建单。

### 进行中

- Adapter D01单次dispatch、E01–E04独立会话与表单未知屏障、Worker/恢复器和F6前端；T6-01..04不提前勾选。

### 阻塞与风险

- 实现无阻塞。用户指定auth.txt本人默认寝室、各一个高于/低于最新余额的金额；学校状态映射仍未验证，同寝室只能保留一个未解决订单，第二笔需第一笔真实终态后执行。实际扫码付款由用户完成，默认能力不提前开放。

### 下一步

- 实现Adapter D01及E02/E03持久发送台账，验证响应丢失/重启只能回查，接通Payment Worker和二维码本人图片接口。

### 主要文件或模块

- backend/services/payment、school_adapter内部DTO、gateway/payment_api.py、部署权限/Compose、docs/contracts、docs/database、T6决策、frontend/src/api/generated.d.ts。

### 验证

- 后端ruff通过，pytest 130通过/1项需显式MySQL环境跳过；新增16项金额/验收开关测试。OpenAPI/内部DTO/数据库目录生成通过；实际MySQL竞态与外部学校尚待后续验证。

## 2026-10-02 · T5 主分支交付

### 已完成

- T5 实现提交 660b3cc 的完整 GitHub Actions 已成功：[容器验证 36893685280](https://github.com/ChaceQC/elect/actions/runs/36893685280)，包含规则/契约/构建/浏览器与隔离容器集成。
- 确认 main 的严格必需检查 check、PR 与管理员约束仍生效；当前 dev 尚未包含上次 PR #2 的 main 合并提交 f8ce023。
- 将 origin/main 合入当前 dev，无冲突、无业务源码差异；只补齐主分支祖先关系与本次交付进度。
- 同步提交 5cb00c7 的 [push Actions](https://github.com/ChaceQC/elect/actions/runs/36900430563) 与 [PR Actions](https://github.com/ChaceQC/elect/actions/runs/36900491814) 全部成功后，核对 head、严格检查与最新 main，再合并 [T5 PR #3](https://github.com/ChaceQC/elect/pull/3)。
- PR #3 于上海时间 2026-10-02 01:43 合入 main，merge commit 为 4ac0127；未使用 admin、自动合并或绕过保护。已将本地 main/dev 快进到该交付提交，保留 dev，并在 dev 更新本次完成记录。

### 进行中

- 无 T5 合并工作进行中；main 例行 push CI 由合并触发，分支同步和完成记录在 dev 正常推送。

### 阻塞与风险

- 无合并冲突或交付阻塞；合并前最新提交两套 Actions 均已成功，未用旧提交绿色结果代替。
- 真实 SMTP/学校写/支付开关保持默认关闭，本次不重新执行真实外发或学校操作。

### 下一步

- 实施 T6-01/P7-01 支付能力政策与幂等台账；真实支付开关保持关闭，后续合入 main 继续经过 PR 与最新 Actions 门禁。

### 主要文件或模块

- PROJECT_PROGRESS.md、dev/main 的 Git 祖先关系与 T5 交付 PR；T5 源码不变。

### 验证

- 工作区开始时干净，dev 跟踪 origin/dev；fetch 后确认 main=f8ce023、dev=660b3cc，原 dev 缺少 main 最新合并提交。
- GitHub API 确認 660b3cc 的 check 为 GitHub Actions/success；main 必需 check/app_id=15368、strict=true、审批数0、enforce_admins=true。
- git merge --no-commit origin/main 成功，无冲突；本次仅 Git 同步和进度文档，不新增或重跑本地业务测试。
- 合并前 PR head=5cb00c7、base=f8ce023、mergeStateStatus=CLEAN，push/PR check 均为 SUCCESS；合并后 GitHub main=4ac0127，本地 main/dev 快进成功。完成记录另在 dev 提交推送，不直接推 main。

## 2026-10-02 · T5 与 M2 完成

### 已完成

- T5-01..04、P6-01..05、F5 完整状态实现与必要验收完成，工程版本0.9.0；低余额次数/回差小步4b51314已提交推送。
- Notification独立邮箱密钥/AAD、持久job/租约/epoch、固定Message-ID、每次当前许可、DATA前发送边界、三次有限重试与unknown占名额、Outbox/Inbox进度/结果镜像接通。
- 前端展示SMTP接受/失败/重试时间/未知占次数、采集周期故障与取消在途；新增三个真实后台进程与最小队列/内部接口权限。
- 真实本人学校验证码登录、B02新鲜采集到指定SMTP一封发送成功，job/Monitoring均sent且只一次attempt；用户于2026-10-02确认测试邮箱收到。临时阈值为真实余额加5.00元，总次数1，验收后原配置恢复并关闭。
- 验证学校验证码：完全省略字段和有效uid留空答案均拒绝，正常验证码登录通过，保留原学校验证码链路。
- 定位SMTP连接重置为Clash TUN的Match/PROXY路径；物理网卡直连TLS成功。真实验收用限定单SMTP端点、随机认证、单连接的临时CONNECT通道完成，结束自动关闭，未改系统代理。
- email_auth.txt按五行格式仅由专用进程在内存解析；未直接查看、未进入Git/镜像。auth.txt权限保留600，凭据经匿名stdin进入验收容器，无明文副本或命令行凭据。

### 进行中

- T5实现与最终定向验证完成；本批提交推送dev，无业务实现待办。

### 阻塞与风险

- 无T5实施阻塞，真实SMTP与用户收件确认均通过。默认真实SMTP/学校写/支付仍关闭。
- 普通直连TCP仍受本机TUN路由影响，本次临时通道不是生产网络配置；正式部署须提供可达SMTP网络或明确代理。
- 本次真实内部联调为正式业务代码/实际MySQL与内部ASGI，未宣称公网完整部署/容量/集中故障演练；这些范围属T7。低余额通过临时提高阈值触发，不声称自然低余额周期。

### 下一步

- 按T6-01/P7-01实现支付capabilities与金额政策，再建立本地幂等订单/一次学校dispatch台账；真实支付开关继续保持false，未指定金额时不执行建单或付款。

### 主要文件或模块

- Monitoring alert_snapshot/delivery_reports/alert_recovery/permits，Notification connection/smtp/repository/worker/results/recovery/job/template，monitoring_0005、notification_0002。
- 公共邮箱加密实现移入common，两个领域保留独立密钥/AAD；重构仅复用加密基础，控制许可、结果镜像和恢复仍分责。
- Secret/队列/Compose、前端NotificationStatus/MonitorPage、T5验收/运行说明、学校验证码分类记录与所有受影响README/计划/契约/进度。

### 验证

- 事件增量实际MySQL、114项后端/空库及旧T1–T4故障回归已通过；遵循用户要求，此批未重复整套大型故障测试。
- 此批后端ruff、23项定向契约/事件/凭据/Secret检查、公开/内部协议/七域目录一致性通过；前端5项定向组件、类型和生产构建通过。
- t5_delivery_smoke验证SMTP接受/永久拒绝/临时重试、固定Message-ID、重复事件/job、双Worker、关闭零连接、DATA后断连/租约丢失unknown不重发，全部通过。
- 独立真实MySQL/Redis/迁移和正式代码链路通过；分类证据docs/acceptance/school/T5-live-delivery.json，用户收件已确认，未输出学校/邮件地址或凭据。
- 学校无验证码省略/空答案拒绝有分类证据；代理TUN路径失败、物理网卡TLS成功、临时通道真实单封SMTP接受均已验证。
- 重建后Monitoring/Room/Notification、三个新增后台进程、Notification Relay和RabbitMQ定向健康检查通过；SMTP默认关闭。286项本地文档链接、shell语法、锁文件同步和git diff --check通过。

## 2026-10-01 · T5 事件规则完成

### 已完成

- P6-01/02、T5-01：新鲜样本事务内的低余额 episode/slot、回差、含首封总次数、未知占名额、配置计数迁移、合法序号释放和跨事件冷却。
- 新增 monitoring_0005；四个完整失败采集周期建立独立故障事件，成功关闭，不使用低余额额度。
- 本地邮件凭据保护小步 fc6a9e0 已提交推送 dev；已按用户最新明确要求同步本轮真实投递范围，email_auth.txt 未直接读取。

### 进行中

- Notification 持久 job、发送前许可、DATA 边界/恢复、结果镜像与前端邮件状态。

### 阻塞与风险

- 无实施阻塞。真实邮件已获指定目标授权，先验证模拟故障边界再执行；SMTP 接受与邮箱实际收件分别记录。
- 本批合成 sent/unknown 直接写状态，只能证明事件计数规则，不能称为投递验收；M2 未完成。

### 下一步

- 实现 Notification Worker/恢复器及本域密钥、队列权限；完成 SMTP 接受/拒绝/正文后断连和进程故障验证，再执行真实本人采集到指定邮箱链路。

### 主要文件或模块

- monitoring/alerts/faults/results/repository/recovery、monitoring_0005、t5_alert_smoke、schema-catalog 与 T5 决策/验收和计划文档。

### 验证

- ruff 通过，pytest 114 passed / 1 skipped，七域目录/DDL 检查通过。
- 全新 elect-test-t5 Docker 空库与全部 T1–T4 脚本通过，实际 Redis/MySQL/MQ 中断、SIGKILL、多 Worker/重复消息恢复通过。
- t5_alert_smoke 的严格阈值/负余额/回差/防重、未知额度、上限降低/提高/计数迁移、跨事件冷却和四周期故障/成功关闭检查全部通过。
- git check-ignore 证实根和两端 email_auth.txt 排除且未跟踪，未读取文件内容；提交前检查差异与受影响 README/AGENTS/进度。

## 2026-10-01 · T5 实施开始

### 已完成

- 核对 T5/P6、F5 和 T3 发送许可；确认当前 dev 工作区干净。用户已将本轮范围调整为包含真实邮件投递，配置与指定收件人由本地 email_auth.txt 提供；先验证模拟故障边界，再执行真实验收。
- 固化 T5 事件、次数、恢复和模拟验收范围，见 docs/decisions/T5低余额与邮件.md。
- 按用户补充，为本地 email_auth.txt 增加 Git/两端 Docker 排除规则，文档记录五行格式、禁止直接读取及仅限后续专用本地测试进程内存解析的约束；尚未读取该文件；真实验收仅由专用进程在内存解析，不直接查看。

### 进行中

- P6-01/02：接入新鲜样本、episode/slot、回差、跨事件冷却与配置迁移；随后接入持久投递与前端状态。

### 阻塞与风险

- 无代码实施阻塞。真实投递已获用户明确授权；配置内容不直接读取，SMTP 接受与实际邮箱收件分别记录，验证前不标 M2 完成。
- 需要将原发送许可模块按授权检查、结果镜像和恢复职责拆分；仅影响 T5 发送流程，保留已有取消线性化语义。

### 下一步

- 完成事件规则与 MySQL 次数/配置/回差检查，提交推送该小步；再实现 Notification job、发送边界与模拟 SMTP 验收。

### 主要文件或模块

- Monitoring results/configuration/repository/permits、Notification、迁移与 T5 决策文档。

### 验证

- 已确认 dev 跟踪 origin/dev，初始工作区无未提交改动；AGENT.md 和子目录 AGENTS.md 不存在。
- 凭据规则已通过 git check-ignore、未跟踪检查和 git diff --check；新增事件代码验证单独记录。

## 2026-10-01 · Actions 修复与 main 合并门禁

### 已完成

- 定位最近四次 `dev`/`main` 容器 CI 失败：`test-t4-dependencies.sh` 将共享目录改为 UID 10001、0700，普通 Runner 无法写入 `hold.log` 或检查就绪文件；此前 root 本地验收掩盖该权限错误。
- 修复为保留宿主机属主、共享 GID 10001 和 0770 权限，正式 Secret 与生产服务权限不变。
- 同步 AGENTS、README、开发/实施/部署说明，并新增 GitHub 协作流程。按用户明确范围，当前开发分支直接 commit/push，无需 PR；仅合并到 main 时需要 PR，合并前确保最新提交的 Actions 全部成功。
- CI 对所有分支 push 和目标为 main 的 PR 执行，保持必需作业名 `check`，同一 PR 新提交取消旧运行。
- 已在 GitHub 为 main 启用并核对 PR、严格必需检查 `check`（App ID 15368）、管理员约束、禁止强推/删除；dev 已取消 PR/推送前检查要求，允许直接提交推送，保留禁止强推/删除。
- 初始权限修复 PR #1 的最新提交 28c6b61 已在 Actions 全部成功后合入 dev（601cb9c）；当前开发流程文档修正在 dev 直接提交推送，更新既有 main 交付 PR #2，不再创建 dev PR。

### 进行中

- main 交付 PR #2 等待最终文档/CI配置提交的完整 Actions；最新提交全部成功后才合并。

### 阻塞与风险

- 无已确认实施阻塞；修复完整 CI 已通过，main 保护已生效。流程文档/触发配置更新后仍需重新验证最新提交，成功前不得合并。
- 学校/SMTP/支付验收范围不变，本次只修复合成故障验收与开发流程。

### 下一步

- 将流程文档直接提交推送 dev，等待 PR #2 最新提交的 push/PR Actions 全部成功后合入 main。
- 完成修复交付后按 T5-01/P6-01 实现低余额 episode/slot、总次数含首封、冷却/回差与取消边界。

### 主要文件或模块

- deploy/test-t4-dependencies.sh、.github/workflows/check.yaml、AGENTS.md、README.md、docs/GitHub协作与合并流程.md 及相关开发/实施/部署文档。

### 验证

- 已读取 Actions 运行 36875792322 的失败日志，确认离线/浏览器步骤通过、故障共享目录的 `Permission denied` 导致容器集成失败。
- 开始时工作区干净，dev/main 均在 9d8c8cd，未启用分支保护；已从 origin/dev 创建 codex/fix-actions-pr-gate，未直接改动受保护目标分支。
- 本地以宿主机 UID 1000 复现原目录的写入失败；修复后宿主机日志写入/追加、容器 UID 10001 状态/就绪写入、宿主机状态读取均通过，属主保留1000、组10001、权限0770。
- [Actions 36877986899](https://github.com/ChaceQC/elect/actions/runs/36877986899) 完整通过：后端107 passed/1 skipped，前端33项、Playwright20项、空库/迁移/权限/可靠事件/T2-T4脚本、实际Redis/MySQL/MQ故障恢复；普通GitHub Runner验证原权限错误已消失。未调用真实学校、SMTP或支付。
- main/dev 最终分支保护 API 核对：main 严格检查+PR+管理员约束；dev 的 PR/推送前检查均为 null。shell语法、受影响文档链接与 `git diff --check` 通过；最终提交的 Actions 结果以 [PR #2](https://github.com/ChaceQC/elect/pull/2) 最新检查为准。

## 2026-10-01 · T4 完成

### 已完成

- T4-01..04、P4/P5b、F4/F5-05实现与验收完成，版本0.8.0。查询263e736、采集引擎9007a6b、界面/故障交付1c798ac均已提交推送；已从dev快进合并并推送origin/main。
- 余额按本人Binding/学校roomId精确匹配，合并请求不混用房间；缺席/未知值保留该房间成功缓存。C02七天窗口/修订快照、Decimal聚合与保守覆盖度接通。
- 持久Scheduler/Worker/恢复器、短租约/续租/三次重试/栅栏、Outbox/Inbox、唯一样本、完成槽防重、运行取消与固定成员分页接通。
- 正式总览、范围草稿/URL恢复、日周月图表、采集分页与立即采集/取消、桌面和375px接通。图表按需加载，修复ARIA未知值/弹窗空白误关闭等回归问题。
- 生产前端真实学校只读通过：本人B02余额刷新、最近7天C02、6个已知记录日/partial、持久Scheduler/Worker采集1条balance_only、快照读取、原配置恢复与退出。

### 进行中

- 无T4实现进行中；M2仍等待T5邮件闭环。

### 阻塞与风险

- 无T4实施阻塞。当前只采余额，电表未知保持null，不执行SMTP/支付。
- 学校完整覆盖/稳定来源ID/频率上限未确认；真实账号仅1个绑定，双房间隔离为合成学校+实际数据库证据。
- 故障脚本人为推进持久租约/重试与已退出合成账号的Redis锁以缩短等待，不宣称完整自然小时周期或公网部署已验收。

### 下一步

- 按T5-01/P6-01实现新鲜有效样本驱动的低余额episode/slot、总次数含首封、冷却/回差、配置修改与取消边界，再接通Notification持久发送job。

### 主要文件或模块

- Room/Adapter/Gateway/Monitoring、monitoring_0004、25进程Compose和依赖故障入口；frontend/features/history、RunControls、URL日期/快照、图表、Modal。
- docs/acceptance/T4验收记录.md、前端四张合成截图、学校分类结果与所有相关计划/架构/部署/README。

### 验证

- 完整Docker检查通过：后端ruff/107 passed/1 skipped、33接口/内部schema/七域目录与DDL；前端contract/lint/typecheck/33项单元组件/build/20项Playwright。
- 全新Docker空库/权限/重复迁移/TLS/可靠事件及全部T2/T3/T4脚本通过；最终镜像重建后25个长期进程healthy。验收环境已停止，保留命名卷，不影响原有服务。
- 253项本地文档链接、git diff --check与auth.txt/依赖/构建产物忽略检查通过；代码已推送dev/main，GitHub CI由推送触发。
- 真实SIGKILL、实际Redis/MySQL/RabbitMQ中断、重复签名消息、多Scheduler/Worker、取消/切换/迟到提交、三次重试、固定分页均通过。
- 空余额缓存保持、同步修订/重复/空响应、完成逻辑槽重扫补充验证通过；真实只读分类记录passed，无认证材料/学校IDs/金额输出、无真实截图/trace。

## 2026-10-01 · T4 持久采集引擎

### 已完成

- 查询小步263e736已提交推送origin/dev。
- P5b持久调度/运行领取/45秒租约与10秒续租、90秒预算、三次重试/恢复器、Outbox/Inbox、公开运行/取消及固定成员快照接通。
- 同账号不同房间仍按roomId匹配；切换后首次样本独立基线。采集观察以Adapter受限身份写对应房间缓存，样本与缓存保持不同职责。
- 新增monitoring_0004保存采集间隔与内部持久指标；Compose新增三个真实后台进程。

### 进行中

- F4真实总览/日期范围/图表/快照明细和F5-05立即采集/取消界面；全阶段容器与依赖故障回归。

### 阻塞与风险

- 无当前实施阻塞；尚未真实C02/采集联调，当前balance_only，不生成或发送邮件。
- Secret原子替换后旧容器仍挂载旧文件；升级后必须重建RabbitMQ/应用以加载新ACL/内部权限，已复验该流程。

### 下一步

- 完成F4/F5-05桌面与375px浏览器检查，再进行全新空库与MySQL/Redis/MQ故障回归及生产前端只读学校验证。

### 主要文件或模块

- Monitoring scheduler/execution/results/recovery/worker/job/run_api/samples与0004；Adapter/Room观察命令、长任务心跳、消息权限与Compose。
- docs/acceptance/T4采集引擎验收记录.md与受影响的契约、数据库、部署和开发说明。

### 验证

- 后端ruff、107 passed/1 skipped；schema/protocol导出和实际七域在线迁移通过。
- 实际MySQL/Redis+合成学校：多副本/重复受理、唯一样本、退避耗尽、取消/切换/旧epoch、缓存目标与固定快照通过。
- 真实SIGKILL领取进程（人为推进数据库租约到期以缩短测试）、RabbitMQ重复消息只一条样本/Inbox通过。
- 新生产后端镜像成功，三个新增长期进程与相关API健康；全部合成监控已关闭后才启动真实进程。

## 2026-10-01 · T4 查询与持久采集启动

### 已完成

- 核对总/前后端计划、学校 C02 与现有控制栅栏；开始时 dev 与 origin/dev 同步，工作区干净。
- P4-01..04与总览后端完成，记录T4决策与查询增量验收。用户强调同账号不同房间不得混用余额，已落实roomId精确匹配及目标缺席拒绝。

### 进行中

- P4 余额受理/刷新、C02 持久窗口与聚合、总览；随后接通 P5b 和 F4/F5-05。
- 新查询职责拆成独立模块，既有修改限于路由、权限、Worker 编排和必要文档同步，避免把学校访问放入数据库事务。

### 阻塞与风险

- 无当前实施阻塞。C02 边界与稳定来源 ID 未确认，成功响应不证明全日完整，缺失数据保留 unknown。

### 下一步

- 实现余额刷新幂等合并/冷却、C02 窗口恢复/内容快照修订，并验证跨周/月、同日多条、空响应与学校失败保留缓存。

### 主要文件或模块

- Room、School Adapter、Gateway、Monitoring、frontend/features/history、deploy 与 T4 决策/验收。

### 验证

- 后端105 passed/1 skipped及ruff通过；独立Docker空库与全部T2/T3脚本通过。T4查询脚本实际MySQL/Redis/合成学校通过逐房间余额、合并请求、目标缺席、租约/窗口接管、重复/修订/空响应、范围和权限。
- 无真实C02或采集验收；总阶段T4保持进行中。

# 项目进度

日期按 `Asia/Shanghai` 记录；完成、验证、阻塞与下一步随任务更新。

## 2026-10-01 · T3 与 M1 完成交付

### 已完成

- 0.7.0 完成 T3-01..05、P3b/F3、F5 控制范围：持久绑定/默认/删除、凭据与许可、三级筛选/列表内搜索、确认/unknown/刷新恢复、独立查看与监控草稿/冲突/独立关闭。
- 按用户指定，枫苑5号-402 先真实新增（1→2）再真实删除（2→1）；生产前端与正式后端/B02/台账均通过，原默认保留、各上游一次 dispatch。删除缺席观察使用正常时间，间隔30秒。
- 更新33个公开接口/内部命令与权限、room_0004/school_0005、B05–B08学校协议、总/前后端/部署/根规范与验收；普通写开关已恢复 false，实际采集/SMTP/支付未开放。
- 功能提交073582e已推送origin/dev并快进合并推送origin/main，工作区回到dev；所有本轮独立验收项目已down并保留命名卷，不改动其他服务。

### 进行中

- 本阶段无未完成实现任务；接下来按 T4 推进真实查询与持久采集。

### 阻塞与风险

- 无T3/M1实现阻塞。真实默认删除/竞态使用合成学校和MySQL验证，真实学校新增/删除仅覆盖指定账号与目标；其他权限/限额/错误码仍不扩大解释。

### 下一步

- 按 T4-01/P4-01/05 实现本人余额/总览缓存读取接口和 F4 页面，再接入 C02 的7天持久历史窗口与覆盖度；随后 P5b 接通 Scheduler/Worker/租约/采集样本，F5-05 不提前勾选。

### 主要文件或模块

- Room/Adapter/Gateway/Monitoring/common、两域迁移/Secret权限、前端rooms/monitoring、33个契约、T3删除决策与验收、两份真实记录。

### 验证

- 完整容器 ruff/93 passed、1个需显式临时root入口跳过、全部契约/七域head与DDL；前端31项单元/组件、14项Playwright桌面/375px回归通过。
- 全新Docker空库/权限/重复迁移/TLS/可靠事件、T2及全部T3控制/凭据/默认/新增/删除故障脚本通过，22个长期服务healthy。
- 真实新增/删除记录passed：一次dispatch、B02确认/两次缺席、原默认/监控一致、删除档案和缓存保留、刷新/404/手机/退出/存储检查；无认证材料/学校IDs输出、无真实截图/trace。
- 新增基线0035cce的GitHub CI已success；删除交付073582e的[GitHub CI](https://github.com/ChaceQC/elect/actions/runs/36852315195)已启动，记录时in_progress，本地完整检查已通过。
- 204项本地文档链接、git diff --check、auth.txt/Secret/依赖/构建产物忽略检查通过。

## 2026-10-01 · T3 删除绑定验证进行中

### 已完成

- 新增基线 0035cce 已提交推送；真实枫苑5号-402 仍保持绑定，用户已明确授权同一目标删除。
- 删除 API/持久撤除槽、学校方法覆盖单次写入、两次30秒缺席观察、默认 retarget-to-null/补偿、迟到租约证明、inactive 历史保留与前端确认/恢复已实现。
- Schema/契约扩展至 33 个方法/路径、room_0004/school_0005；B08 学校协议、内部命令与权限升级同步。

### 进行中

- 版本 0.7.0，完成全部回归/容器/迁移与确认界面，然后对枫苑5号-402 做生产前端真实删除及台账证明。
- 三份真实验收脚本共用 schoolLogin/readApp，避免复制认证处理和独立 Node DNS 读取；无 trace/真实截图。

### 阻塞与风险

- 无实现阻塞。真实删除尚未执行；普通写开关关闭，采集/SMTP/付款保持未开放。

### 下一步

- 完整容器检查和临时升级后执行指定目标删除，确认 B02 缺席与列表/404/默认保持，恢复写开关，再同步完成状态、提交推送与主分支交付。

### 主要文件或模块

- Room removal、Adapter removal、Monitoring nullable retarget/证明 API、两域迁移/权限、前端删除确认/操作恢复和真实验收脚本。

### 验证

- 实际 MySQL 与合成学校通过：同键/换键/归属、一次POST方法覆盖、响应丢失/30秒缺席、短暂空列表/重现、unknown、关闭/清默认、明确拒绝补偿、迟到租约、偏好提交后确认丢失、Outbox 回滚；未调用真实学校删除。
- 后端现有93项通过，前端31项单元/组件与14项Playwright通过；33个契约和新迁移继续核对。

## 2026-10-01 · T3 新增绑定基线完成，删除增量接续

### 已完成

- 0.6.0 的绑定台账、默认子操作、三级筛选/列表内搜索、F3 异步恢复/独立查看和 F5 草稿/冲突/关闭已完成验证。
- 全新 Docker 空库与全部基础/控制/凭据/默认/绑定故障脚本通过，22 个长期服务 healthy。
- 生产前端实际新增枫苑5号-402 成功，B02/台账 confirmed、一次 dispatch，绑定数 1 → 2、原默认保留；桌面刷新/独立查看与手机监控只读、退出/存储检查通过。临时写开关已恢复 false。
- 同步 32 个公开接口/内部协议、两域迁移、学校 B05–B07、阶段/升级/前后端说明，保存不含认证材料的真实记录与六张合成截图。

### 进行中

- 用户追加删除绑定，并明确使用枫苑5号-402 进行真实删除验收。核对学校页面 roomUserremove 为 POST /base/roomUser/{bruId} + X-HTTP-Method-Override: DELETE；不使用其他写接口作为自动兜底。
- 删除增量先占本人 Room 撤除槽；默认目标先建立 Monitoring retarget-to-null 屏障，学校连续两次成功缺席（间隔至少 30 秒）后才标 inactive/清空默认，保留历史与关闭意图。unknown 不自动重发。
- 为复用凭据/学校账号锁和发送前检查，将 SchoolSessions 单次绑定扩为共同 write_once 入口；台账按 bind/unbind 类型复用基本事务，删除单独实现缺席观察与租约证明，避免复制敏感认证处理。

### 阻塞与风险

- 无实现阻塞。删除尚未执行；真实采集/SMTP/支付仍未开放。其他学校限制仍保持未确认，不将单目标成功推广为全部写入验收。

### 下一步

- 增加解绑持久受理/一次 dispatch/连续 B02 缺席确认、默认清空与监控屏障、前端确认/刷新恢复；通过合成竞态与容器后对同一目标执行真实删除，再恢复开关并提交推送。

### 主要文件或模块

- Room/Adapter/Gateway/common、两域迁移、控制 Worker、前端 rooms/monitoring、学校与公开/内部契约、T3 决策和验收。

### 验证

- 完整容器检查：后端初轮 90 项；末次缓存质量与证明脚本重建后 93 passed/1 skipped，ruff/全部契约/七域离线 DDL；前端 28 项、Playwright 12 项通过。
- 实际 MySQL/合成学校的一次写入、unknown/缓存丢失/强杀/默认失败分态/Outbox 回滚通过；真实新增的分类记录与台账证明 passed，未输出真实密码、Cookie/token 或学校 IDs。
- 一次宿主机截图补采初始化 monitor 超时，针对失败页面复验通过；初次真实脚本 Node DNS 读取失败未发绑定，改为浏览器同源读取后通过。
- git diff --check、本地 187 项文档链接和 Secret/构建忽略检查通过；无 AGENT.md。

## 2026-10-01 · T3 绑定与异步界面验收进行中

### 已完成

- 默认 Saga 小步 3544b38 已提交并推送 origin/dev。
- 实现 Adapter prepared/dispatched 加密台账、唯一未解决目标、B02 回查/unknown；Room 幂等受理、确认与 Outbox、默认子操作及分态恢复。
- 新增三级筛选与本人绑定读取四个 API，公开契约增至 32；前端使用筛选配合当前列表内搜索、冻结目标/操作恢复、独立查看与监控草稿/冲突/独立关闭。
- 按学校 B05/B06/B07 实测唯一定位枫苑5号-402；用户已明确授权该目标真实新增。学校 API、契约、表目录与升级文档已同步。

### 进行中

- 用户追加删除绑定能力，并指定删除验收同样使用枫苑5号-402；在新增验收小步提交后接入学校页面 roomUserremove（POST + X-HTTP-Method-Override: DELETE），验证默认/监控屏障、一次发送与连续 B02 缺席确认。
- 版本同步 0.6.0，执行完整容器规则/浏览器/空库恢复回归，随后执行指定目标的生产前端真实绑定验收。
- 真实验收共享 auth/OCR 读取抽为 live-school-helpers，避免两个显式脚本复制敏感材料处理；T2 脚本改用新的筛选只读入口，T3 脚本要求显式目标且不截图/trace。

### 阻塞与风险

- 无实现阻塞。真实 batchAdd 尚未执行；普通部署绑定/邮件/支付开关保持 false。采集与 SMTP 属于 T4/T5，页面明确说明未运行。

### 下一步

- 完成全新 Docker/MySQL/Redis/MQ 和生产镜像回归，再对枫苑5号-402 执行一次真实新增、B02 确认和前端刷新/手机只读验收；恢复写开关后更新阶段状态、提交推送。

### 主要文件或模块

- backend/services/{room,school_adapter,gateway,common,deployment}、两域迁移、scripts/t3_binding*、deploy/test-stack.sh。
- frontend/features/{rooms,monitoring}、组件/浏览器/显式真实脚本，公开/内部契约、学校 API 与 T3 决策/验收。

### 验证

- 后端 ruff、90 passed/1 skipped、OpenAPI/内部协议/七域目录检查通过；新增两域在线迁移通过。
- 实际 MySQL/合成学校绑定/故障脚本通过：响应丢失/缓存丢失只一次 POST、10分钟 unknown/空列表/换键屏障、已绑定零 POST、dispatch后HTTP前崩溃、明确拒绝、默认失败分态和 Outbox 回滚恢复。
- 前端 contract/lint/typecheck、28 项单元/组件和 12 项 Playwright 通过；1440/375px 的筛选/搜索、刷新、独立查看、默认终态、无效草稿关闭/冲突/路由保留均覆盖，无横向溢出。合成截图已检查。

## 2026-10-01 · T3 默认与绑定继续实施

### 已完成

- 接通 Room 默认公开 API、后台控制租约/恢复、首次成功同步稳定默认、偏好提交证明与明确补偿；版本同步为 0.5.0。
- RoomRepository 镜像职责拆分，统一 preference → operation → sync_state/绑定锁顺序，保留 sync_tick。
- 用户指定真实新增寝室枫苑5号-402；检查学校已发布筛选页面，三级列表只读实测唯一定位、B03 roomId 返回精确匹配，当前账号尚未绑定。

### 进行中

- 接通默认受理/恢复/补偿、成功同步后的稳定默认初始化，再实现绑定一次 dispatch 台账和 F3/F5 控制界面。
- 将 RoomRepository 中 B02 镜像写入抽到既有 mirror 草稿，统一写入锁顺序为 preference → operation → sync_state/绑定；恢复 Worker 的领取只锁操作，短事务释放后才推进 Saga。

### 阻塞与风险

- 无实现阻塞。用户已授权枫苑5号-402 的真实新增；实现与合成验证完成后对该目标验收，普通部署的绑定写开关继续默认关闭。

### 下一步

- 实现 Adapter 加密候选/一次 dispatch/B02 回查台账、Room 同键与目标屏障和默认子操作；前端改为楼栋/楼层/房间筛选，搜索只过滤当前列表，接通绑定/默认恢复及监控设置。

### 主要文件或模块

- backend/services/room、gateway、common/business_worker，默认 Saga 合成集成脚本与阶段文档。

### 验证

- 后端 ruff、90 passed/1 skipped、OpenAPI/内部协议/七域目录检查通过。全新隔离 Docker/MySQL/Redis/MQ 环境的基础、T2、T3 控制和凭据检查通过。
- 实际 MySQL 默认脚本通过：prepare/commit 响应丢失、偏好提交后恢复、迟到租约拒绝、失效目标补偿、版本/归属/并发请求、切换中关闭后仍 disabled。初次发现 Gateway 占位路由遮挡默认入口，已修复并复验。
- 新增目标三级筛选的真实只读检查成功，未执行 batchAdd、邮件或付款。

## 2026-10-01 · T3 默认切换与绑定流程暂停交接

### 已完成

- 凭据协调/撤回、发送许可和 F2-06 已验证，提交 dfff247 并推送 origin/dev。
- 核对 P3b、默认切换 Saga、B04 一次 dispatch/B02 回查与 F3 异步界面的契约和现有表结构。

### 进行中

- 用户明确要求暂停并换对话接续；此后不继续实现或执行业务验证。
- 已在工作区新增 Room 的 preference_store.py、mirror.py、defaults.py、control_jobs.py、default_saga.py 草稿：偏好锁、B02 镜像抽取、默认受理/提交、控制任务租约与恢复/补偿编排。尚未接入现有 repository/worker/API，未格式化、未测试、未提交，不应作为已交付功能使用。
- 学校绑定候选校验、Adapter 一次 dispatch/unknown 回查、绑定操作受理和前端 F3/F5 尚未实现。本轮用户明确要求默认切换和绑定流程也必须完成，新对话须保留这个完整范围。

### 阻塞与风险

- 无实现阻塞；当前为用户主动暂停。真实 batchAdd 未指定新增目标，不执行真实绑定写入；用合成学校和实际 MySQL 验证后保持真实写开关关闭。

### 下一步

- 先复查/格式化上述五份默认草稿，将镜像和偏好锁接入 RoomRepository，增加 Room 默认 API、首次成功同步后的稳定默认初始化与后台控制任务入口；注意统一 preference → operation → sync_state/绑定的锁顺序，并保留只读 sync_tick 供 T2 夹具使用。
- 随后实现绑定：Room 保存 candidate_id/目标/凭据版本/上游操作 ID 和默认子操作，Adapter 保存 prepared/dispatched 台账、加密候选及脱敏 B02 结果；同用户/目标未解决操作阻断换键，POST 后只回查，不因重启或空列表再次 dispatch。
- 接通 F3 绑定/默认/独立查看与刷新恢复、F5 配置草稿/冲突/独立关闭；完成真实 MySQL 竞态、合成学校一次 POST/unknown/各阶段故障及前后端容器验收后，再同步契约/文档、提交推送。不能仅交付凭据一批就结束默认/绑定范围。

### 主要文件或模块

- backend/services/room、school_adapter、gateway、common，Room/Adapter 迁移、部署权限、前端 rooms/monitoring 和合成验收脚本。

### 验证

- 前一批 90 项后端、23 项前端、8 项浏览器及实际 MySQL/Redis 故障与权限检查通过，提交 dfff247 已推送 origin/dev；本批五份草稿未验证。
- 最近验收环境是 `/tmp/elect-t3-credentials-proof/stack.env`、Compose 项目 `elect-test-t3-credentials-proof`；暂停时停止该独立测试项目并保留命名卷。未改动其他服务或真实学校绑定。

## 2026-10-01 · T3 凭据协调与发送许可完成

### 已完成

- 第一批控制基础已提交并推送 origin/dev：5411fb4；本轮独立测试容器已停止并保留命名卷。
- P5a-04：完成 Identity 每用户凭据操作槽、三域登录激活屏障、撤回持久受理/查询/恢复；Adapter 自行读取屏障后激活/撤销，未确认不签发会话或报告撤回成功。
- 撤回保留应用会话、删除密码/DEK/学校身份和全部历史密码暂存，清理旧版本/暂存 token；人工认证前观察版本/撤销时间，token 写入前后复核持久授权，旧登录/旧撤回与迟到认证不能恢复授权。
- P5a-05：完成 job/epoch 唯一持久发送许可、30 秒到期、当前代次/邮箱/序号/最后新鲜低余额样本/冷却检查，与关闭按同一 monitor 锁串行；在途事实保留，尚未运行 SMTP。
- F2-06：账户撤回确认、去重、202 进度、刷新/响应丢失恢复、终态刷新 me/monitor；同账户刷新保留弹窗且丢弃较早的并发响应。
- 新增 identity_0003/school_0003/monitoring_0003，更新 Secret/服务/MQ 升级、内部协议与表目录；项目/契约/前后端和锁文件统一为 0.4.0。同步 README/AGENTS、子目录说明、计划、架构、部署、决策和验收；无 AGENT.md。

### 进行中

- T3 整体继续进行；T3-01/P5a/F2 已完成，Room 默认/绑定 Saga 和 F3/F5 控制界面尚未交付，M1 保持未完成。

### 阻塞与风险

- 本批无实现阻塞。未使用 auth.txt，学校上游为合成夹具，不能将本批描述为新的真实学校联调。
- 真实 batchAdd 尚无指定目标寝室，绑定写开关继续关闭；真实采集、SMTP/投递恢复和支付依赖 T4/T5/T6。

### 下一步

- 按 P3b-04 实现 Room 持久默认切换 Saga 与首次同步默认初始化，补齐 prepare/偏好提交/monitor commit 的崩溃恢复、补偿和切换中关闭竞态；随后推进 P3b-01..03 的绑定一次 dispatch 台账与 F3/F5 界面。

### 主要文件或模块

- backend/services/identity/{application/credential_activation,revocation,sessions,recovery}、school_adapter/{credential_control,application/token_cache,infrastructure/credentials}、monitoring/{credentials,credential_api,permits,permit_api}、Gateway/common 与三域迁移。
- scripts/t3_credential_smoke、t3_credential_faults、t3_permit_smoke，T2/T3 合成公共夹具，deploy/test-stack.sh、provision/upgrade_controls。
- frontend/features/auth 的账户撤回与 SessionProvider、三项组件/两项浏览器检查；docs/decisions/T3凭据协调与发送许可.md、acceptance/T3凭据与许可验收记录.md 和受影响契约/计划/说明。

### 验证

- 将 CredentialActivation 从 LoginSaga 拆出，避免登录文件混合三域控制；新增 token_cache 统一两条认证路径的迟到缓存复核。普通源码均低于 400 行；凭据仓储 338 行、单一仓储职责，保持本批范围。
- `sh deploy/check.sh` 容器检查通过：后端 90 passed / 1 skipped、ruff、OpenAPI/内部协议/七域 head 与离线 DDL；前端 contract/lint/typecheck、23 项单元/组件、build，Playwright 8 项（含 1440/375px 撤回/刷新/会话保留）。
- 末轮增加人工认证观察值后，重新构建后端检查镜像，90 passed / 1 skipped、ruff/契约/DDL 全部通过；前端源码未继续修改。
- 全新 `/tmp/elect-t3-credentials-proof` Docker/MySQL/Redis/MQ 空库、权限、重复/并发迁移、可靠事件、T2 合成隔离/恢复、九组控制基础及凭据/许可故障检查通过；22 个长期服务 healthy，migrate/tls-check 退出 0。
- 实际数据库验证屏障/激活/确认响应丢失恢复、暂存过期补偿、旧执行拒绝、当前及历史密码暂存清除、迟到 Redis token 与迟到人工认证拒绝、旧登录/旧撤回重放、发送许可幂等/过期/取消并发及输入检查。
- 最新脚本在上述容器只读挂载复验：撤回缺版本 428、错误 CSRF 403、旧版本 409、匿名操作查询 401、跨用户操作查询 404；凭据槽与可访问学校的合成同步任务均终结后才恢复真实 Worker。
- 两端版本/锁文件仅同步项目版本；真实凭据、依赖和构建产物忽略/未跟踪检查、219 项本地文档链接、shell 语法与 git diff --check 通过。独立测试项目最终用 down 停止并保留命名卷，不更改其他服务。

## 2026-10-01 · T3 第一批监控控制基础

### 已完成

- P5a-01/02/03：持久 disabled monitor、GET/PATCH、参数与版本校验、generation/epoch、统一提交栅栏、prepare/commit/compensate-retarget；默认提交回查 Room 操作与实际偏好，不接受自报成功。
- 单次取消及凭据更新/撤回的本域原语；关闭、配置/凭据改代阻断旧样本，切换中关闭意图被保留；待认证可保存参数但不会恢复执行。
- 配置/取消/提醒失效/审计 Outbox 同事务；已授权在途提醒保留且摘要显示 sending，间隔变更保留事件已发送计数。
- 独立邮箱 AES-GCM 密钥、owner/email_version 绑定、T2 → T3 Secret/权限保留升级及 monitoring_0002；生成内部协议/数据目录并同步根规范、开发/部署/阶段/验收文档。
- 隔离容器与实际 MySQL 控制检查接入 deploy/test-stack.sh；未使用 auth.txt 或执行真实学校、邮件、支付写入。

### 进行中

- T3-01 整体仍在进行；P5a-04 的 Identity/Adapter 协调和 P5a-05 尚未完成。本批不提前勾选 T3、P5a 整体或 M1。

### 阻塞与风险

- 无控制基础实现阻塞。真实 batchAdd 尚无指定新增寝室，绑定写开关继续关闭。
- 原语验证不等于端到端撤回/默认切换已完成；当前公开默认/绑定/撤回入口和监控页面继续关闭，Scheduler/采集/租约恢复属于 T4。

### 下一步

- 按 P5a-04 将 Identity 凭据更新/撤回接入 Monitoring 屏障和 Adapter 版本确认/密文-token 撤销，补齐持久阶段、崩溃恢复和并发登录/撤回测试；随后接入发送许可、Room 默认 Saga 与绑定台账。

### 主要文件或模块

- backend/services/monitoring/{configuration,repository,queries,fences,runs,barriers,credentials,email_crypto,api} 及 0002 迁移。
- Gateway monitor_api、Room control_api、common 内部 DTO/版本错误、deployment/upgrade_controls、scripts/t3_control_*、后端单元测试与 deploy/Compose。
- docs/decisions/T3监控控制基础.md、acceptance/T3控制基础验收记录.md、契约/表目录、总/后端计划及根/子目录说明。无 AGENT.md；前端源码/依赖无变更。

### 验证

- 后端 ruff、89 passed / 1 skipped（显式临时 root 测试默认跳过）、OpenAPI/内部 DTO/七域 head 与离线 DDL 检查通过；实际数据库由容器独立验证。
- 容器前端 contract/lint/typecheck、20 项单元/组件、build 和 6 项 Playwright 回归通过。
- 全新 `/tmp/elect-t3-controls-final` Docker 空库初始化、七域权限、TLS/JWT/Redis ACL、Outbox/Inbox/Audit 与 T2 合成隔离/恢复回归通过；新 Monitoring/Room 镜像已构建。
- 最新 API/恢复进程重建后 22 个长期服务全部 healthy，migrate/tls-check 均退出 0。
- 最新 T3 镜像的真实 MySQL 验证九组通过：失效样本拒绝、并发 prepare/配置、关闭意图、实际 Room 偏好证明/对象归属、结果与关闭串行、凭据原语、补偿终态、Outbox 回滚、未授权/在途提醒边界。
- 初次新增 Room 偏好证明夹具遗漏 rooms 必填楼栋/门牌，已修正并复验通过；未将失败运行记录为成功。核对后补充实际偏好一致性和在途发送优先显示。
- 182 项本地文档链接、git diff --check 与真实凭据/依赖/构建产物忽略检查通过。

## 2026-10-01 · T3 开始实施

### 已完成

- 核对总计划、P5a/P3b、F2/F3/F5 和监控/绑定架构；dev 与 origin/dev 同步，工作区无既有改动。
- 确认先实现 MySQL 控制屏障，再接入默认切换、凭据协调与绑定写台账；真实采集引擎仍属于 T4。

### 进行中

- T3-01：disabled monitor、版本检查、generation/epoch、取消和持久 retarget 屏障。

### 阻塞与风险

- 无控制屏障实现阻塞。真实 batchAdd 验收尚无指定新增寝室，保持学校绑定写开关关闭；合成学校验证不能替代真实写入验收。

### 下一步

- 完成监控控制事务与真实 MySQL 竞态验证，再接入 Room 默认切换 Saga 和 Identity 凭据撤回。

### 主要文件或模块

- backend/services/monitoring、common、gateway，监控迁移及定向集成检查。

### 验证

- 已检查 Git 状态、阶段依赖和现有迁移/路由；本批代码尚未验收。

## 2026-10-01 · T2 交付与验收完成

### 已完成

- T2-01..04、P2-01..06、P3a-01..04 完成；F2 登录/协议/会话/账户/学校重认证、F3 本人列表与候选只读范围完成，版本统一为 0.3.0。
- 生产前端验证码、协议阅读/版本重置、独立授权、重复提交保护与密码清理；手机/桌面账户、退出失败处理、学校修复；列表 empty/failed/stale/loading 和候选防抖/限频/乱序/过期处理。
- 补齐登录/验证码全链路预算、人工保留资源、安全 GET 两次上限、持续学校失效状态与广播；生产镜像只保留服务/必要迁移，合成与烟测脚本使用独立 test 镜像。
- 全新 Docker 22 长期服务/两项一次性作业与实际 MySQL/Redis 隔离/故障验证完成；合成校务验收期间暂停真实 Worker，完成后恢复健康，不让 CI 合成任务访问学校。
- 正式后端、生产前端浏览器和本人授权密文后台恢复均完成真实学校复验：1 条本人绑定、候选第一页 10 条、刷新/手机账户/退出正常，浏览器存储未保存认证材料。
- 同步计划完成范围、README/AGENTS、版本/契约/锁文件、部署与升级说明；保存 T2 验收、三份真实分类记录与四张合成界面截图。

### 进行中

- 暂无本阶段实现任务进行中；T2 本地/真实学校/云端容器验证和主分支交付均完成。

### 阻塞与风险

- 无 T2 实施阻塞。B03 筛选精度、学校真实 TTL/完整错误码未确认，保持 unverified/应用 TTL；仅一个真实账号，双用户故障验证采用合成学校与真实基础服务。
- F2-06 撤回、默认初始化/绑定写依赖 T3；监控/历史/提醒/支付仍未开放，四项真实副作用开关 false。

### 下一步

- 按 T3-01/P5a-01 建立每用户 disabled monitor、配置版本/generation/execution_epoch、取消与 prepare/commit-retarget 屏障，再实现凭据撤回协调和绑定台账。

### 主要文件或模块

- frontend/src/features/{auth,rooms}、hooks/useNow、lib/abortableDelay、组件/浏览器测试与 scripts/t2-live-browser.mjs。
- backend/services/school_adapter、三域服务/迁移、common 认证/工作设施、scripts/t2_*、两端镜像/依赖锁与 deploy/Compose。
- docs/acceptance/T2验收记录.md、school/2026-10-01-T2-*.json、frontend/t2、T2 决策与总/前后端计划、根/子目录文档。

### 验证

- 容器后端 ruff、82 passed / 1 skipped、三类契约/当前 head 检查及七域离线 DDL 通过。
- 容器前端 contract/lint/typecheck、20 passed、build 通过；容器 Playwright 6 passed，1440/375px 截图已查看，无横向溢出。
- 全新 `/tmp/elect-t2-release-proof` 仅 Docker 构建/初始化与内部 TLS/JWT/域权限、Outbox/Inbox/Audit、共享限流/Redis 失败、登录恢复/同步租约等检查全部通过；22 长期 healthy，migrate/tls-check 退出 0。
- 最新生产前端真实浏览器与后台恢复记录均 passed，不存原始页面/trace 或输出真实认证材料；源码/文档的本地凭据扫描通过。
- 三批实现 50bc0ec、bcd7f16、713a000 已推送 origin/dev；已快进合并并推送 origin/main。工作区回到 dev；本轮测试容器停止，保留命名卷，不影响原有服务。
- [GitHub CI](https://github.com/ChaceQC/elect/actions/runs/36805828351) 对交付代码 713a000 实际 success，离线/浏览器与全新隔离容器检查均通过。

## 2026-10-01 · T2 后端真实学校闭环

### 已完成

- 正式学校 Adapter、Redis 原子验证码/单飞/共享限流、AES-GCM 暂存/激活、持久登录恢复、应用会话/CSRF/退出与本人寝室读取接口。
- Room 持久同步/租约接管、失败 stale/空列表复核、本人操作权限、候选分页与脱敏加密缓存；不提前初始化默认或开放学校写入。
- 内部认证 TLS、独立认证 Secret、三个恢复/同步进程与 T1 → T2 保留既有凭据的离线升级入口。
- 使用 auth.txt 完成正式 Gateway 到学校的真实登录、密文激活、应用恢复、1 条本人绑定、10 条候选第一页和退出；清除 token 后，已授权密文后台恢复与本人读取也通过。
- 修复真实联调发现的压缩内容二次解压、CAS text/plain JSON、透明代理 DNS 解析；修复并发首次登录 gap lock 冲突，运行事务使用 READ COMMITTED。

### 进行中

- 前端登录/协议/授权、账户修复、本人列表/候选页面已接入，组件检查通过，正在完成浏览器与完整容器验收。

### 阻塞与风险

- 无实施阻塞。B03 筛选精度、学校真实 TTL/完整错误码仍未确认，返回 unverified 并采用应用 TTL。
- 本次只有一个真实指定账号；双账号/故障竞态使用合成学校与真实 MySQL/Redis 验证，未将其描述为两真实账号联调。

### 下一步

- 完成桌面/375px 浏览器登录、协议阅读、刷新恢复、学校认证修复与退出失败验证，再通过生产前端进行真实学校登录/本人读取。
- 随后执行全新 Docker 验收与安全/故障检查，形成 T2 验收记录并核对任务完成范围。

### 主要文件或模块

- backend/services/{gateway,identity,school_adapter,room,common,deployment}，三域 0002 迁移、锁文件与 scripts/t2_*。
- deploy/Compose/Secret；docs/decisions/T2认证与读取.md、契约、数据结构及两份真实分类记录。

### 验证

- 后端 ruff、75 passed / 1 skipped，OpenAPI/内部协议/当前七域迁移 head 目录检查通过。
- 全新实际 MySQL/Redis、内部 TLS/JWT/领域 ACL、T1 Outbox/Inbox/Audit 基础通过；T2 合成学校实际数据库烟测六组隔离/恢复/幂等/权限/空/stale/租约检查通过。
- 正式链路真实学校与后台恢复记录均 passed，不包含原始账号、密码、token 或寝室标识。
- 前端 lint/typecheck/build 与 18 项单元/组件测试通过；完整阶段容器/浏览器检查尚在进行。

## 2026-10-01 · T2 开始实施

### 已完成

- 阅读总实施计划、P2/P3a、F2/F3、学校 A01–A04/B01–B03 与现有 T1 运行基础；确认 dev 工作区干净。
- 确认本阶段只开放认证与本人读取，默认初始化、绑定写入及撤回屏障继续由 T3 交付。

### 进行中

- T2-01 第一批协议/加密模块已实现：A01–A04/B01，学校兼容 RSA、逐跳白名单/公网 DNS 校验、响应上限、分阶段超时与总预算。
- Redis 原子 challenge/共享账号锁/全局 5 并发与 AES-GCM 信封已建立，实际 Redis 竞态与 API 接入在下一批验证；尚未开放登录。
- 为避免寝室仓储混合查询组装与同步事务，将读取/DTO 组装与任务领取/镜像提交拆到独立模块；影响仅为新增 T2 模块职责，不改变公开契约。

### 阻塞与风险

- 无实施阻塞；学校真实 TTL、完整错误码和 B03 搜索精度仍未确认，按应用上限和 unverified 处理。
- 现有 Redis ACL 需补充原子脚本权限；认证服务需独立 Secret 与内部 TLS，不能用 T1 骨架的关闭接口代替验收。

### 下一步

- 接入受限 Secret、内部 TLS 与正式验证码 API，在实际 Redis 验证刷新/单次消费/浏览器归属；随后实现加密暂存/激活与持久登录 Saga。

### 主要文件或模块

- backend/services/school_adapter、identity、room、gateway；frontend/src/features/auth、rooms；deploy 与相关契约/验收文档。

### 验证

- 新增 13 项协议/密码/图片/信封定向测试通过，覆盖独立 CAS/SDGL Cookie、回调参数、多块与 Latin-1、跨用户/版本 AAD、旧密钥读取和恶意跳转拒绝。
- 新模块 ruff check/format 通过；以上为离线合成验证，尚未进行正式 Adapter 学校联调。

## 2026-10-01 · T1/M0 完成

### 已完成

- T1-01..04、P1-01..08、F1-01..06 交付与验证完成；版本统一为 0.2.0，28 个公开 API 结构保持契约，学校业务仍明确关闭。
- 前端四页路由/AppShell、初始化/认证守卫、同源客户端、Query/会话隔离、幂等恢复、202/unknown 轮询与草稿冲突保护；公共 Modal/状态/Toast/金额/上海日期工具与显式开发 MSW。
- Docker 规则/契约/构建/Playwright 入口与 GitHub Actions；测试可挂载 docs/合成夹具，生产构建只使用各自源码/锁文件，排除递归 Python 缓存。
- 新的独立项目仅用 Docker 构建两端、生成 Secret、自签证书、启动 19 个长期服务和两项一次性作业，实际空库/事件/权限检查通过。
- 实际 MQ 中断/恢复、数据库拒绝 ready、三种基础服务重建后保留审计/Inbox、新证书预检/替换和错误 SAN 拒绝通过。
- 同步根/子目录 README、AGENTS、总/前后端计划、架构/部署/开发/运行文档；保存 T1 验收与生产关闭状态的桌面/手机截图。
- 四批实现提交 9d07793、405b7a0、4eaad25、743a98e 均已推送 origin/dev；实现已从 dev 快进合并并推送 origin/main。

### 进行中

- 暂无本阶段实现任务进行中；T1 本地与 GitHub CI 已通过，实现已快进合并到 main，T2 待执行。

### 阻塞与风险

- 无 T1 实现阻塞。测试仅使用 elect.test.local 自签证书，公网域名、受信任证书及完整运维演练留待 T7/T8。
- T2 学校会话/登录、T3–T6 绑定/监控/邮件/支付及业务 Worker 未实现；四种副作用开关仍默认关闭。

### 下一步

- 按 T2-01/P2-01 抽取学校 RSA/CAS/SDGL 到正式 httpx Adapter，落实验证码会话隔离、重定向白名单、分阶段超时/总 deadline、每账号单飞和全局限流。
- 随后推进 P2-02 验证码代理与 P2-03 加密凭据暂存/激活，不提前开放学校写入或邮件。

### 主要文件或模块

- frontend/src/app、api、features/auth、hooks、lib、components、mocks/browser 与 unit/component/e2e 测试。
- deploy/check.sh、test-stack.sh、compose*.yaml；.github/workflows/check.yaml；两端 Dockerfile/锁文件与版本。
- docs/acceptance/T1验收记录.md、frontend/T1公共层验收.md、t1 截图及根/子目录说明/计划。

### 验证

- `sh deploy/check.sh` 在容器实际通过：后端 ruff/60 passed/1 skipped、三类契约目录检查、七域离线 DDL；前端 contract/lint/typecheck/15 passed/build，Playwright 3 passed。
- `sh deploy/test-stack.sh /tmp/elect-t1-docker-proof elect-test-proof` 全新空卷/Secret 实际通过；19 长期 healthy，migrate/tls-check 退出 0。
- 实际 HTTPS 生产前端/Nginx/Gateway：直达/刷新、持久 FEATURE_DISABLED、跨站 ORIGIN_REJECTED、无注册 MSW；两种宽度截图已检查。
- MQ 停止期间持久事件未标 published，恢复后自动投递且审计一条；MySQL 停止时 ready 503；重建 MySQL/Redis/MQ 后唯一审计与 Inbox 保留。
- 新证书经 tls-check/nginx -t 后重建入口，实际 DER 与新证书一致；错误 SAN 在无网络一次性容器退出 1。
- 最终 v0.2.0 两端镜像实际构建/启动通过，后端 UID/GID 10001，前端无 node_modules/worker 资源；迁移重复与审计持久状态保持。
- [GitHub 容器 CI](https://github.com/ChaceQC/elect/actions/runs/36790577543) 实际 success（代码 743a98e），离线/浏览器和全新空库集成两步均通过。
- 140 个文档本地链接、shell 语法、Git/镜像忽略与 git diff --check 通过；测试容器已停止，保留命名卷，不影响已有无关服务。
- 修复并复验浏览器发现的弹窗反向 Tab 焦点循环；修复 Docker 检查缺失前端合成夹具只读挂载后完整通过。

## 2026-10-01 · T1 容器与可靠事件基础

### 已完成

- deploy/compose.yaml：MySQL 8.4.8、Redis 7.4.7、RabbitMQ 4.1.4、八个 API、六域 Relay、Audit Worker、migrate 与 tls-check；基础镜像固定摘要，只有 Nginx 发布正式 80/443。
- 无网络 Secret 生成器、空卷 probe/七域 app/ddl provisioning、本库 GET_LOCK 同连接迁移、UTC 和最小账号；文件 0400/目录 0700，已有 Secret 拒绝覆盖。
- 本域事务 Outbox、30 秒发布租约/到期接管、确认后标记、退避；签名持久消息、事务 Inbox 与提交后 ACK，Audit 只保存脱敏登记字段。
- 域名渲染、只读 TLS、Nginx 静态缓存/SPA 回退、HTTPS 跳转、健康依赖与资源上限；API 缓存/队列降级、数据库/迁移失效拒绝 ready。
- 同步运行决策、Secret 清单、事件 actor 字段/签名协议与架构/部署文档。P1-01..05/07/08 基础范围已完成，P1-06 CI 待下一批。

### 进行中

- 前端 F1 公共数据层、路由/初始化守卫和容器 CI；T1 尚未整体完成。

### 阻塞与风险

- 无实现阻塞。验收使用 elect.test.local 两天自签证书和本机 18080/18443；未配置正式公网域名/证书，不声称公网或学校业务验收。
- 监控、支付、邮件业务 Worker 及业务恢复器未实现，未用空循环冒充健康。

### 下一步

- 实现前端 API 客户端、Query/会话隔离、四页路由、202 操作恢复与版本冲突草稿保护，然后加入 Docker CI 和浏览器验收。

### 主要文件或模块

- deploy/compose*.yaml、nginx、mysql、redis、公开配置；backend/services/common、audit/receiver、deployment/provision、migrate_all_mysql、scripts/deployment_smoke.py。
- backend/tests、docs/contracts/internal/schemas.json、events/registry.yaml、运行/部署/架构说明及各 README。

### 验证

- 全量后端 ruff、内部协议生成校验和 pytest：60 passed / 1 skipped。
- 独立 Compose 首次空库实际启动，migrate/tls-check 均退出 0，所有 API/Relay/Audit 与基础服务 healthy。
- 容器 smoke：七域空业务、UTC、跨库/DDL 拒绝；每库两次并发持锁迁移；并发领取/租约接管/迟到写回拒绝/退避、Inbox 事务回滚与并发去重；实际 JWT 用户上下文、Redis 前缀 ACL 均通过。
- 同一合成签名事件两次直接发布并由真实 Relay 再发布：Audit 和 Inbox 各一条，Outbox 已确认发布；无外部副作用。
- nginx -t、/details 直达 200/no-cache、HTTP 308 固定配置域名和 query 保留均通过；初始 Nginx tmpfs 权限缺少 CHOWN 已修复并重启验证。

## 2026-10-01 · T1 服务认证

### 已完成

- 每服务独立 Ed25519/EdDSA 短期 JWT，校验签名、算法、key_id、iss/sub/aud/iat/exp/jti、命令权限与用户会话版本；启动检查签名公私钥一致。
- 内部诊断只返回验证后的上下文；任意 X-User-Id 不参与身份，对象归属不符返回 404。
- HTTPS Origin/会话 CSRF 公共校验与内部身份拒绝信封；新增 PyJWT 锁定依赖及运行决策文档。

### 进行中

- Outbox/Inbox、Audit 消费者、正式 Secret/provisioning 与 Compose。

### 阻塞与风险

- 无阻塞；应用会话 introspection 和真实业务 CSRF 接入留待 T2，当前业务关闭。

### 下一步

- 实现本域事务 Outbox、发布租约/退避、RabbitMQ confirm/手动 ACK 与签名事件，并在空库 Compose 验证重复事件只落一条审计。

### 主要文件或模块

- backend/services/common/security.py、browser_security.py、app.py、http.py、pyproject.toml/uv.lock、tests/unit。
- docs/decisions/T1运行基础.md。

### 验证

- ruff 通过；服务身份/应用基础定向测试 15 passed，覆盖伪造头、错误算法、过期、错误 audience/issuer/scope、超长 TTL、非法 jti/用户版本与 Origin/CSRF。
- 上一批完整 pytest 实际为 46 passed / 1 skipped；提交 9d07793 已推送 origin/dev。

## 2026-10-01 · T1 第一批：镜像与服务入口

### 已完成

- 两端独立多阶段 Dockerfile；Node 22.23.2 编译后仅输出 Nginx 静态站点，Python 3.12.10/uv 锁定安装后以 UID/GID 10001 运行。
- 八个 FastAPI 骨架、运行 Secret 的身份/领域连接校验、上限连接池与 UTC 会话、请求 UUID、白名单 JSON 日志和脱敏错误；公开业务暂返回 FEATURE_DISABLED。
- 无网络 TLS 预检入口，检查域名、整条链有效期、SAN（含单层通配符）与公私钥匹配。
- 为当前开发环境补齐 Docker Compose 2.39.4 与 uv 0.8.22；正式交付仍仅需 Docker Engine/Compose。

### 进行中

- T1-02/04：正式 provisioning、持锁迁移、Compose、服务认证、Outbox/Inbox/审计和前端路由/数据层。

### 阻塞与风险

- 无实现阻塞。宿主机 80 端口已有无关服务，验收使用独立项目与临时端口，不停止现有服务。
- 尚未进行 Compose 空库启动与真实域名证书验收，不将独立构建视为 M0 已完成；学校业务仍未开放。

### 下一步

- 创建 Ed25519 短期 JWT 与可信用户上下文、租约 Outbox/事务 Inbox 和 Audit 幂等消费者，然后以 Compose 验证重复事件与 MQ 故障恢复。

### 主要文件或模块

- backend/Dockerfile、services/common、services/deployment/check_tls.py、各域 app/__main__、tests/unit；frontend/Dockerfile。
- 根与子工程 README、AGENTS、docs/开发说明.md。

### 验证

- 两端 `docker build` 实际成功；后端 ruff 通过，新增 TLS/运行入口测试 8 passed。
- 新增应用入口测试前的全量 pytest 为 43 passed / 1 skipped；完整 Compose 验收留待下一批。

## 2026-10-01 · T0 完成

### 已完成

- T0-01..04、后端 P0-01..05、前端 F0-01..05 的交付与验证完成，计划清单已勾选；项目/契约版本为 0.1.0。
- 独立 Python/uv 与 React/Vite/npm 工程；正式源码/构建不引用 example，两端锁文件和镜像忽略规则已提交基线。
- 冻结 28 个公开 API、后端 DTO、前端 generated.d.ts；补齐 preference_version、credential_version、run.version、待完成摘要、邮件状态、未解决订单和快照失效。
- 定义内部命令、9 类事件及 8 类状态模型；版本、幂等、未知状态和恢复入口具有可执行校验。
- 建立七域独立 Alembic 初始链与 47 张领域/事件表（另有各库 alembic_version），增加调度锚点、运行版本、持久历史窗口/Saga/支付步骤/快照成员；实际 MySQL 验证通过。
- 固化数据库 app/ddl 账号、Secret/服务身份、域名/证书、四类外部副作用开关、邮箱和支付保护政策与学校待确认门禁。
- 交付 10 个 MSW 合成场景、三种宽度共 27 张参考截图、组件/字段/按钮/API 追踪与真实验收模板。
- 用户提供的 auth.txt 已加入 Git/镜像忽略且未跟踪，开发规范/说明已同步；实际只读 A01–A04/B01/B02 通过，返回 1 条本人绑定，记录不含真实凭据/token/寝室标识。

### 进行中

- 暂无业务实现任务进行中；T0 验收已完成，正式业务留待 T1–T6。

### 阻塞与风险

- T0 无阻塞。宿主机 Docker Engine 可用但 Compose 插件尚缺，T1 部署验收前需准备。
- 真实绑定写入、支付金额/状态/到账、SMTP 与学校限频仍未验收；能力开关默认关闭，不将参考烟测或模拟测试描述为正式业务完成。

### 下一步

- 按 T1-01 创建 frontend/Dockerfile、backend/Dockerfile 和 API/后台进程/预检入口。
- 随后按 T1-02 创建 deploy/compose.yaml、probe/provision、持锁 migrate、tls-check 及基础服务健康依赖；完成 M0 后再进入 T2 正式认证闭环。

### 主要文件或模块

- backend/services/* 的 DTO、状态与 migrations；backend/scripts、tests、pyproject.toml/uv.lock。
- frontend/src/api/generated.d.ts、src/mocks、tests/unit、scripts，以及 docs/acceptance/frontend/reference。
- docs/contracts、database、decisions、T0需求追踪表、acceptance/T0验收记录与学校记录；deploy/.env.example、secrets.example.yaml。
- 根/子工程 README、AGENTS、PROJECT_PROGRESS 和受影响计划/架构/部署/学校文档。

### 验证

- Python 3.12.10、固定 Node 22.23.2/npm 10.9.8；uv sync --locked、领域包加载及前端独立构建通过。
- backend：ruff 与 OpenAPI/内部协议/表目录一致性检查通过，pytest 38 passed / 1 skipped（临时库项默认跳过）。
- 显式临时 MySQL 8.4.8 集成检查 1 passed：七域升级各两次、业务表空、无跨库 FK、app 无 DDL/跨库权限；非法间隔、重复计划/样本、未知订单换键重复建单被数据库拒绝。
- frontend：contract:check、lint、typecheck、3 项 Vitest/MSW 分支检查、build 全部通过；生产入口无 mock 导入。
- Playwright/Chromium 对 example 实际交互，27 张参考截图已保存并抽查；学校只读参考烟测通过且不执行外部业务写入。
- auth.txt 忽略/未跟踪检查、122 个本地文档链接、27 张截图清单、T0/P0/F0 任务范围、生产产物无场景数据与 git diff --check 均通过。

## 2026-10-01 · T0-01 独立工程

### 已完成

- 建立 Python 3.12.10/uv 后端工程和七个领域包、无业务数据库的 Gateway 及 common 包。
- 建立独立 React/Vite 前端入口，固定 Node.js 22.23.2/npm 10.9.8，定义构建、lint、类型、契约和测试脚本。
- 建立两端 `.dockerignore`，补充浏览器测试产物忽略规则，更新根说明、子工程说明与开发规范的当前阶段。

### 进行中

- T0-01 工程建立与验证完成。
- 准备 T0-02/T0-03 的 28 个公开接口、DTO、内部命令/事件与状态场景。

### 阻塞与风险

- 无 T0 实现阻塞；当前 Docker Engine 可用，但宿主机未安装 Compose 插件，T1 部署验收前需补齐。
- 业务接口、真实学校访问与后台任务尚未实现。

### 下一步

- 生成 `docs/contracts/openapi.yaml`、后端 DTO、前端 `generated.d.ts`，并验证 28 个公开接口和补充字段。

### 主要文件或模块

- `backend/pyproject.toml`、`.python-version`、`services/`、`frontend/package.json`、入口与工具配置。
- `.gitignore`、两端 `.dockerignore`、README、AGENTS 与 `docs/开发说明.md`。

### 验证

- 已检查仓库：开始时 `dev` 与 `origin/dev` 同步，工作区干净；无 `AGENT.md` 或子目录规范。
- 已在固定 Node 22.23.2/npm 10.9.8 容器生成 package-lock；`uv lock`、`uv sync --locked` 通过。
- Python 3.12.10 加载全部领域包通过，`ruff check .` 通过；前端 `lint`、`typecheck`、`build` 通过。
- 已运行 `git diff --check`，确认没有空白格式问题；依赖和构建产物均被忽略。
- 更正初次验证记录：第一次前端 `typecheck` 因缺少 jsdom 类型声明失败，初次提交前过早记录了通过；已补入 `@types/jsdom` 并重新运行 `lint/typecheck/build`，三项实际通过。
- T0-01 基线提交 `bd8d7fb` 已推送 `origin/dev`；类型依赖修正在独立提交中记录。
- 用户新增根目录 `auth.txt` 作为可持续使用的本地真实测试凭据；已同步 Git/镜像忽略规则和开发规范，正文不进入日志、文档或夹具。

## 2026-10-01

### 已完成

- 初始化本地 Git 仓库，补充正式前后端空目录的 `.gitkeep` 占位文件。
- 建立 `AGENTS.md`，保留指定的位图生成工具与模型，补充版本、分支、提交推送、进度维护、代码规模、重构与文档同步规范。
- 建立根目录 `README.md` 和 `PROJECT_PROGRESS.md`，同步项目文档入口及当前实施阶段。
- 补充 `.gitignore` 的上传与备份规则，保留配置模板和依赖锁文件。
- 已确认 GitHub CLI 登录账号为 `ChaceQC`，具备仓库管理权限。
- 按用户本次明确要求创建 GitHub 公开仓库 [ChaceQC/elect](https://github.com/ChaceQC/elect)，本仓库提交署名使用该账号的 GitHub 隐私邮箱。
- 配置 `origin`，切换至日常开发分支 `dev`。
- 文档链接、规范字段、文件格式及忽略规则检查通过。
- 创建中文初始提交 `deb9353`（`chore: 初始化项目仓库并补充开发管理规范`），并推送至 GitHub 的 `dev` 与 `main`。
- 设置 GitHub 默认主分支为 `main`，本地 `dev` 与 `main` 分别跟踪 `origin/dev` 与 `origin/main`。

### 进行中

- 暂无业务开发任务进行中；本次规范补充与仓库初始化已完成。

### 阻塞与风险

- 当前无已确认阻塞；正式应用、契约与部署工程尚未实现，不能按已交付业务功能验收。

### 下一步

- 按 T0-01，先建立 `backend/pyproject.toml`、`backend/.python-version`、`backend/uv.lock` 和后端 `services/` 包骨架，锁定 Python 3.12.10 并验证工程可加载。
- 随后建立 `frontend/package.json`、`frontend/package-lock.json`、`frontend/index.html` 与 `frontend/src/main.jsx`，验证独立工程可构建。

### 主要文件或模块

- `AGENTS.md`、`README.md`、`PROJECT_PROGRESS.md`、`.gitignore`。
- `docs/README.md`、`docs/总实施计划.md` 的仓库文档入口。
- `backend/.gitkeep`、`frontend/.gitkeep`。
- 初始化纳入版本管理的 `docs/` 设计文档与 `example/` 界面参考（含 `example/package-lock.json`）。

### 验证

- 已检查 `git status --short --branch`，确认此前尚无提交与远程。
- 已运行 `gh auth status` 和 GitHub 用户查询，确认账号与访问能力。
- 已检查 `AGENTS.md`、`.gitignore`、现有项目文档与参考说明，确认当前实现阶段。
- 已检查 16 项忽略规则和 12 项保留规则，确认环境文件、私钥、依赖、构建产物、上传与备份排除，配置模板、迁移 SQL 与锁文件可提交。
- 已检查 22 个本地文档链接、要求的规范与进度字段、末尾换行和尾随空白，检查通过。
- 已查询 GitHub 仓库，确认 `ChaceQC/elect` 为公开仓库，当前账号具有管理权限。
- 提交前已运行 `git status --short --branch`、`git diff --cached --check` 和暂存差异统计，确认本次初始化文件范围且无格式问题。
- 已查询 GitHub 仓库，确认公开可见性和默认分支 `main`；`git ls-remote` 确认初始提交 `deb9353` 在远程 `dev` 与 `main` 一致。
- 初始推送后已检查 `git status --short --branch`、`git branch -vv` 与 `git diff --check`，确认工作区干净、分支跟踪正确。
