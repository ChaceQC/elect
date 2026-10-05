## 2026-10-05 · 全程手机请求头与学校支付源码排查

### 已完成

- 根据用户要求将同一原单E01–E04全程保持安卓UA、移动标识和对应页面/图片请求头；四步200，逐步核对真实发出的请求，E02/E03本轮各一次，未再调用phonePay。得到新Native码后更新临时页并核对编码，用户安卓重试仍为出现确认但未打开。
- 直接下载学校入口引用的主包、vendor及主包列出的55个页面分包，共57份JS、无下载失败；忽略大小写并排除base64噪声后，追踪接口声明、请求封装与按钮绑定。
- 唯一MWEB业务调用为中文详情页wxZF：企业微信传MWEB并读取mwebUrl，但确认按钮实际绑定quzhifu/phonePay；baseUrl加/api/wx/pay形成/api/api/wx/pay。未找到JSAPI业务请求，vendor的requestPayment仅为平台API名列表。另一支付展示页仅导航成功页，不作为真实实现证据。
- 新增docs/decisions/手机微信支付源码排查.md，同步学校API与脱敏分类记录。学校完整JS快照和私有票据均保留Git忽略目录，票据继续DPAPI加密；未修改正式前后端/部署/版本。README、AGENTS和子目录README无产品/架构/流程变更，无需同步；无AGENT.md。

### 进行中

- 本轮手机头与源码排查已完成；仍未取得可用H5/JSAPI或安卓收银台，正式产品不接入未经验证的按钮。

### 阻塞与风险

- 学校服务端源码不可见，公开前端只能确认调用和未调用分支，不能证明服务端没有其他接口。学校旧掌上财务说明针对学杂医保费，不直接当作宿舍电费入口。
- 本轮复用同一电费订单，但学校支付表单可能生成不同流水；保留每轮记录，不重放未知请求，不再自动建单或付款。

### 下一步

- 若继续，定位学校真实可用的微信公众号/企业微信电费页面入口，核对其实际下单和唤起链路；已有单仅进行明确范围内的核对，不根据SDK名称、普通手机UA或猜测路径扩展业务写入。

### 主要文件或模块

- docs/decisions/手机微信支付源码排查.md、docs/学校对接API文档.md、docs/acceptance/school/2026-10-05-mobile-payment.json；本地完整手机头和静态源码诊断。

### 验证

- E01–E04全程手机头的真实请求均200，二维码可解码，用户真机反馈仍失败；未自动付款。57份公开JS的接口、模块和模板调用链核对完成，未执行其代码。
- 检查文档、脱敏JSON、路径、Git忽略和git diff --check后提交推送dev；未运行全量测试、创建新电费订单或变更部署。

## 2026-10-05 · 手机支付继续尝试与真机入口

### 已完成

- 用户明确要求继续尝试后，再次用项目身份和指定寝室查询待支付列表；另一条 /api/wx/pay 的 MWEB 请求一次，返回 HTTP 404，前后列表均为空。保留首轮 /api/api/wx/pay 的未知结果。
- 对同一指定寝室、1.00 元调用一次学校在用的 phonePay，成功取得支付页；E02/E03 各一次后取得并解码原生微信付款码。没有自动付款、绑定或邮件操作，各阶段发送标记防止误重跑；成功票据、HTML、支付会话与二维码保存为本地 Windows 用户级 DPAPI 密文。
- 同一原单以安卓、iPhone、微信、企业微信 User-Agent 只读访问，均为扫码页，没有发现 H5/JSAPI 参数；学校 banknh.js 及内联脚本仍走扫码和显示二维码控件。
- 准备只绑定当前 WLAN 的临时页面，提供原生 scheme 与 Android Intent 两种按钮，均复用该原单。随机访问路径、no-store、无原始访问日志、1小时退出；本轮计划于23:04停止。页面只在内存生成，学校凭据不进入页面，未把临时票据/地址写入仓库。
- 用户在安卓系统浏览器/Chrome 实测付款按钮出现打开确认，但确认后未打开；新增同页 `weixin://` 无订单对照后，用户确认能打开微信。核对实际 href 与原生二维码完全一致、Intent 保留原 URI 且无额外空白/fragment；当前 IP 页的普通唤起可用，Native 付款 URI 未能打开收银台，不能归因为本次未使用的 H5 商户域名校验。
- 更新学校 API 与分类记录。正式前后端、版本、README/AGENTS/子目录 README 和部署均无行为变化；仓库无 AGENT.md。

### 进行中

- 本轮接口、原订单二维码及安卓真机对照已完成；付款唤起失败，正式产品暂不接入实验按钮。H5/JSAPI 能力仍待学校有效入口或参数支持。

### 阻塞与风险

- 官方 Native 通道不支持点击 code_url；临时按钮只作实机兼容性验证。H5 两条已知路径分别超时/404，尚无可用官方 H5 链接。最初未知尝试和后来成功的 phonePay 原单分别保留，不混同状态，不重复创建后续订单。

### 下一步

- 在学校提供可用 H5 链接及授权域名，或有效 JSAPI 参数后，继续使用明确关联的订单验证移动付款。当前保持二维码流程；后续如核对本轮原单，仅执行只读查单，不把未知 MWEB 结果清除或自动重新建单。

### 主要文件或模块

- docs/学校对接API文档.md、docs/acceptance/school/2026-10-05-mobile-payment.json；本地 test-results/mobile-payment-20261005/ 诊断与临时服务（Git 忽略）。

### 验证

- 真正的项目凭据认证、D04 查询、直接 MWEB 的404、D01/E01/E02/E03/E04 与二维码解码已完成；四组 UA 只读对照通过。
- 临时页面及二维码本机 HTTP 200，no-store 和按钮存在，页面不含学校 Bearer/prePayId。用户真机证实同页普通微信唤起成功、付款 URI 未打开；没有收银台/付款成功验证。未进行全量测试或部署调整。
- 提交前检查脱敏 JSON、文档差异和 git diff --check，开发分支只提交推送本轮三份文档。

## 2026-10-05 · 手机微信支付入口定向试验

### 已完成

- 按用户“先试试、使用项目身份”和指定寝室的要求，以 auth.txt 在进程内完成学校验证码/认证，B02 确认两条绑定后按用户选择唯一匹配目标。使用 uv 管理的 Python 3.12.10 和现有 SchoolProtocol，不输出账号、密码、token、学校用户/寝室标识或支付票据。
- 以 1.00 元、电费、微信、tradeType=MWEB，仅调用一次学校前端声明的 /api/api/wx/pay；请求前后 D04 待支付列表均为空。MWEB 等待 30 秒后 ReadTimeout，没有返回 HTTP 状态或 mwebUrl；保留学校结果 unknown，没有重试、切换路径或调用 D01/NATIVE，没有付款。
- 本地诊断脚本和发送前持久标记在 Git 忽略的 test-results/mobile-payment-20261005/；已发送标记阻止误重跑建单。首次目标未明确、一次本地时区前置错误均发生在发送之前，修正后只有上述一次 MWEB 请求。
- 核对学校公开脚本的 MWEB 遗留分支及实际 phonePay 按钮调用；同步学校 API 文档和脱敏分类记录。README、AGENTS、子目录 README 无产品、架构、启动或流程变化，无需改写；无 AGENT.md。正式页面、支付开关、版本及现有部署不变。

### 进行中

- 移动端直接唤起微信付款尚未接通；本轮仅交付真实接口试验结论。

### 阻塞与风险

- 学校 MWEB 接口未返回可用链接，无法开展手机唤起与支付域名验证。待支付空列表不证明本次未建单，原试验保留 unknown，禁止据空列表自动重复建单。

### 下一步

- 先只读核对本次 unknown 尝试的后续学校记录；取得学校可用 H5 入口及商户支付域名依据后，再验证一键唤起和返回自动查单。未确认前保留现有二维码流程。

### 主要文件或模块

- docs/学校对接API文档.md、docs/acceptance/school/2026-10-05-mobile-payment.json；本地临时诊断复用 backend/scripts/auth_file.py 和 school_adapter/infrastructure/。

### 验证

- 学校真实身份验证、B02 目标匹配、D04 前后查询成功；一次 MWEB 请求 30 秒 ReadTimeout。没有真机唤起、付款、绑定写入或 SMTP；未运行全量测试、启动 Docker 或升级部署。
- 提交前核对脱敏记录、文档差异、Git 忽略及 git diff --check；仅提交本轮三份文档，按开发分支规范推送。

## 2026-10-05 · CI 触发分层第二轮

### 已完成

- 基于第一轮已通过的五组并行结构，非main分支push改为前后端快速检查，main PR及vX.Y.Z标签保留完整；手动默认full、分支可选quick，手动标签保留完整但不发布。不引入路径分流。 main push按用户追加要求不触发CI，PR合并后不重复运行。
- 快速仍执行全部前后端检查/构建、查询配额数据库及浏览器验证，只跳过三组容器演练与镜像打包上传。完整场景镜像复用、空库隔离、缓存和生产逐容器启动规则保持。
- check根据事件/ref/手动选项独立判断范围，快速严格要求两组success及三组skipped，完整要求五组success；缺失、失败、取消和意外跳过拒绝。发布限定版本标签push且独享写权限。
- 同步AGENTS、CI决策、协作/开发/部署/固定镜像手册及deploy README。根README和前后端README无产品/业务入口变化，无需改写；无AGENT.md。应用版本保持0.19.2，现有部署不升级。

### 进行中

- 第二轮实现4bddd30已提交推送，push 37269750437快速检查及PR #6完整运行37269753792均success；本次补交验收文档，最新文档提交门禁以GitHub实际状态为准。

### 阻塞与风险

- 无已知实施阻塞；手动选项需工作流合入默认分支后在Actions界面可用。2～5分钟快速、12～18分钟完整仍是目标，实际取决于缓存和运行器并发。

### 下一步

- 准备合并时先等待本次验收文档提交的PR完整门禁成功；后续根据13/30兼容组12分1秒的步骤数据决定第三轮优化范围。本轮不合并main、不创建发布标签。

### 主要文件或模块

- .github/workflows/check.yaml、build-check.yaml、deploy/ci/gate.py与定向检查，以及CI/协作/部署文档。

### 验证

- 7项CI定向检查、actionlint及git diff --check通过。实现提交push实测4分8秒，前后端/check成功，三组完整验证及发布跳过，无images-*镜像产物；保留四份BuildKit默认构建记录。
- 同提交PR完整16分28秒，五组及check全部成功，发布跳过；业务消息6分58秒、13/30兼容12分1秒、七容器交付恢复8分45秒。镜像复核与清理通过，详见docs/acceptance/CI触发分层第二轮.md及JSON。
- main push排除通过静态/语法核对；未实际合并、手动调度或发布标签。不重复执行本机全套业务/容器验证，不读取真实凭据或调用学校/SMTP/支付。

## 2026-10-05 · CI 并行验证第一轮

### 已完成

- 在docs/decisions/CI并行验证.md先记录拆分原因、覆盖矩阵、前置状态与验收计划；旧PR完整作业30分55秒，13／30兼容步骤11分29秒。
- 拆分前后端检查/构建，三组完整容器验证分别从独立空库开始；恢复复用本次runtime/test，不再重建ops。保留本地check/test-stack入口及生产start.sh逐容器规则。
- 新增镜像版本/检出提交/镜像ID/SHA-256清单、BuildKit按端/目标缓存、打包/上传/下载/加载计时，以及只允许五组全部success的check；标签发布独立且仅其拥有写权限。
- 同步AGENTS、协作/开发/部署/固定镜像手册和deploy README；根README及前后端README无产品/业务入口变化，无需更新。无AGENT.md；应用版本保持0.19.2，现有部署不升级。
- 实现955eb9b已提交推送，草稿PR #6的完整Actions 37266567115及push 37266563648全部success；PR五组及清理通过，发布按预期跳过。完整工作流30分59秒→15分46秒（约减少49.1%），覆盖/镜像传输和逐组耗时见docs/acceptance/CI并行验证第一轮.md及JSON。

### 进行中

- 第一轮实现与完整验证已完成，本次补充验收记录；最新文档提交的正常PR门禁以PR #6实际状态为准。全部push/PR/标签仍完整验证，第二轮触发分层未实施。

### 阻塞与风险

- 无已知阻塞；15分46秒为本次托管运行器实测，不能保证所有并发/缓存情况下同样耗时。标签发布分支尚需实际标签验证，本轮不发布版本。

### 下一步

- 跟进验收记录提交后的PR #6完整门禁；第二轮按已确定方案切换push快速检查、PR/标签完整和手动默认完整可选。本轮不合并main。

### 主要文件或模块

- .github/workflows/、deploy/ci/、check与test-*脚本、docs/decisions/CI并行验证.md及协作部署文档。

### 验证

- 5项CI定向检查通过，覆盖五组结果失败/取消/跳过/缺失、错误提交/版本/镜像标记/ID和包损坏；actionlint、全部deploy Shell语法检查通过。
- 本次PR：后端288项/查询数据库16项、前端单元56项/浏览器43项通过；业务消息6分8秒、13/30兼容10分45秒、七容器交付恢复8分52秒。镜像包合计约1.40GB，三组下载9～43秒、校验加载36～52秒。
- 未重复执行本机全套容器测试，未读取或输出真实密钥，未调用学校/SMTP/支付；最终容器验收以本次PR Actions结果为准。

## 2026-10-05 · 0.19.2 主分支合并准备

### 已完成

- 按用户要求执行docs/GitHub协作与合并流程.md，核对dev/ac7b7a6、origin/dev一致，工作区干净，dev已包含最新origin/main/65ce8eb；待合并4个提交包含安全审计、SEC-03/SEC-05修复及登录协议交互，版本0.19.2。
- 已确认[0.19.1完整Actions](https://github.com/ChaceQC/elect/actions/runs/37259006403)与[0.19.2完整Actions](https://github.com/ChaceQC/elect/actions/runs/37260965336)均success。main实际保护为严格必需check/App15368、要求PR、管理员受约束、禁止强推/删除；dev无PR/状态检查要求并禁止强推/删除。
- 检查全量待合并差异、受影响文档和git diff --check；本次仅补进度，README/AGENTS/子目录README无新产品、架构、启动或流程规则变化，无需重复修改，仓库无AGENT.md。不重复运行本地业务/浏览器测试。

### 进行中

- 当前dev提交推送后创建dev→main PR，等待该PR最新提交全部Actions成功；合并时匹配head SHA并使用merge commit，不能用此前提交的绿色结果替代新检查。

### 阻塞与风险

- 无已知合并阻塞；PR检查运行中/失败/取消/跳过均不允许合并。SEC-01/SEC-02/SEC-04保持用户指定忽略，现有部署、真实学校/SMTP/支付及目标机长期容量不由源码合并视为完成。

### 下一步

- PR最新提交检查全部成功且包含最新main后合并，核对main push检查，再将合并提交同步回dev；本轮不打标签、不发布镜像、不升级elect-wsl。

### 主要文件或模块

- PROJECT_PROGRESS.md；实际合并范围为安全审计、Room/Monitoring受理与迁移、登录协议前端及0.19.2相关文档/版本。

### 验证

- Git状态/祖先关系、待合并差异、两次完整Actions和服务器分支保护已核对；最终PR与main检查结果以GitHub记录为准。

## 2026-10-05 · 登录协议提示与浏览器阅读记忆

### 已完成

- 按用户要求，未阅读当前协议时点击勾选框，在协议行下一行显示红色“请先阅读协议”，保持未勾选；阅读确认后提示消失。使用aria-disabled保留不可勾选语义，同时接收鼠标/键盘操作反馈。
- 成功学校登录并接入应用会话后，才将协议版本与正文摘要写入localStorage；同浏览器下次可以直接勾选同意，无需重新打开协议。协议版本/内容变化重新要求阅读；失败登录不写入，存储不可用不阻止本次登录，不保存账号、密码或会话材料。
- 9项登录/重新认证组件定向验证已在项目Node22.23.2容器通过，typecheck和改动文件ESLint通过。Windows Node24下原有模拟请求未取得会话，使用固定版本容器复核通过，未为该环境差异改变业务逻辑。
- Edge/Playwright CLI实测未阅读点击保持未选、下一行红字、确认阅读消除提示；成功登录前无已读记录、成功后写入、退出并刷新后无需打开协议即可勾选。1440×1000及375×1000截图与同视口参考并排核对，提示无遮挡，375px无横向溢出。
- 0.19.2版本、前后端锁文件项目版本、协议规则/前端计划/README/AGENTS及契约版本同步；新增忽略CLI与截图临时产物目录。仅前端交互变化，无后端业务/API字段/数据库变更；检查后端与部署README为既有版本实施记录，无需改写，无AGENT.md。

### 进行中

- 本轮实现、定向验证和文档同步已完成，按dev工作流提交推送；远端完整Actions以本次提交实际状态为准。

### 阻塞与风险

- 无实施阻塞；浏览器清理站点数据或禁止持久存储后需要重新阅读。已读记忆只影响客户端阅读步骤，每次仍需明确勾选同意，后端授权与协议校验保持。

### 下一步

- 推送后核对本次Actions；若后续要求更新现有部署，使用统一upgrade入口部署对应版本，再在用户浏览器确认首次与再次登录行为。

### 主要文件或模块

- frontend/src/features/auth/LoginForm.jsx、agreementStorage.js、styles/auth.css、登录组件测试、协议决策及版本入口。

### 验证

- 9项Node22容器组件验证、类型检查与定向ESLint通过；浏览器使用合成学校响应，不调用真实学校/SMTP/支付，不读取真实凭据。
- Node22容器生产构建、OpenAPI一致性和uv锁文件离线检查通过；git diff --check通过。浏览器本地截图保存在output/playwright/的1440-login-hint.png、375-login-hint.png、375-login-remembered.png，按.gitignore排除，不提交合成浏览器状态。未运行全量业务/浏览器测试，未更新现有部署。

## 2026-10-05 · SEC-03 / SEC-05 查询资源修复

### 已完成

- 确认 dev/30ce551 工作区干净，按用户要求忽略 SEC-02，沿用 SEC-01/SEC-04 忽略结论，只修复 SEC-03/SEC-05。已阅读开发计划、后端设计和真实受理/快照/后台调用链。
- 先记录[修复方案](docs/decisions/查询资源受理与快照清理.md)。拆分原因：快照创建与清理需集中配额规则，历史受理需与执行分开；影响 Monitoring 快照/恢复角色、Room 查询受理及两域增量迁移，保留外部 DTO、原分页与学校执行边界。
- 0.19.1完成快照有序成员摘要复用、同用户锁内6次/分钟与12快照/60,000成员配额、单集合20,000成员上限；HMAC用途隔离重建token，库内仍只存hash，旧token及密钥轮换保持兼容。recovery每60秒清理最多4快照/共1,000成员，分页共享锁防止清理竞态，原始样本不删除。
- 历史同步受理前检查每用户6个新operation/分钟、24个/24小时、8个非终态操作（含合并别名）、2个未完成sync和64个未完成窗口。幂等重放不扣额；完整覆盖范围合并，部分重叠按独立请求受配额约束；超限429且不留持久记录。
- 新增monitoring_0006、room_0005，更新迁移清单、表结构目录、前后端版本/锁文件、OpenAPI版本及受影响README/AGENTS/计划/部署文档。SEC-02更新为忽略，SEC-03/SEC-05标为源码已修复；依赖/CI权限/浏览器响应头等独立建议不扩大到本轮。
- 新增Docker-only定向验证入口并接入CI，使用internal网络/无发布端口/临时MySQL与随机新库，不读取业务Secret。检查仓库无AGENT.md；前端源码与布局无需调整。

### 进行中

- 修复、定向验证与文档同步已完成，按当前dev分支提交推送；完整远端Actions以该提交实际状态为准。

### 阻塞与风险

- 无源码实施阻塞。现有elect-wsl仍需单独升级才会应用修复，本轮不修改其镜像、配置、Secret或业务库；忽略项保留原风险，不写作已修复。未执行全量业务/浏览器回归、真实学校/SMTP/支付及长期容量验证。
- 首次隔离验证因WSL无持久会话而自动停止测试MySQL，恢复隐藏保持会话进程后重跑通过；沿用此前保持WSL的要求。未将连接失败当作业务测试结果。

### 下一步

- 本次提交推送后检查对应GitHub Actions；若后续要求部署，先通过统一upgrade应用两域迁移，再核对现有快照清理计数和正常历史同步，保持真实学校验收边界。

### 主要文件或模块

- backend/services/monitoring、backend/services/room、两域迁移、docs/contracts、docs/security 及版本入口。

### 验证

- 独立MySQL8.4.6/Python3.12.10的16项数据库定向验证通过，入口`deploy/test-query-resources.sh`实际运行通过：8并发相同首页仅1快照/3成员、不同范围预算、迟到样本/旧分页、旧token与轮换、过期/归属/共享锁/并行小批清理、历史幂等/合并/跨绑定预算/366天53窗口/释放待办/事务失败回滚。部分配额缩小以用小夹具覆盖边界，不将结果当作压力容量。
- 16项既有T4查询/调度及迁移清单测试通过；改动范围ruff、OpenAPI生成一致性、schema-catalog、迁移head清单和git diff --check通过。仅同步锁文件项目版本，依赖解析内容未升级。
- 首次测试辅助模块相对导入收集失败已修正；WSL会话终止造成的连接失败后，使用持续会话和独立环境通过上述验证。没有连接真实学校、支付或SMTP，也没有显形读取真实凭据/密钥。
- 定向脚本及手工隔离测试的容器/网络已清理；只读确认原elect-wsl仍为13个健康容器，继续保持WSL会话，未升级原环境。

## 2026-10-05 · 全量代码安全审计（修复前历史记录，最新结论见上）

### 已完成

- 基于dev/65ce8eb、0.19.0和干净工作区审计当前Git跟踪代码、公开配置、运维/CI及独立example；检查814个跟踪文件清单、371个Python文件与34个Gateway路由，结合全量规则扫描和关键调用链人工复核。
- 初始记录5项发现。按用户后续结论，SEC-01因学校上游限制无法解决而忽略；SEC-04属于正常账号限流行为，忽略并撤出问题清单。当前保留SEC-02匿名验证码nonce限流绕过、SEC-03采集快照持久写入放大及缺少清理、SEC-05历史同步受理配额不足，共3项。详见docs/security/全量代码安全审计-2026-10-05.md及同名JSON证据。
- 为SEC-03补充每页10条/范围1000条的例子，说明快照只保存记录ID和顺序、翻页复用、重新查询新建，以及30分钟到期不自动删除；同步两项忽略状态、整改清单与文档导航，不调整源码。
- 核对后端66个PyPI锁定包与前端/example依赖公告，区分cryptography/ECharts当前未触发的API用法、pytest/Vitest开发依赖风险，不将包版本命中直接当成生产漏洞。
- 只新增审计报告/证据和文档导航，业务代码、配置、版本、能力开关及现有运行环境未调整。已检查README、AGENTS及前后端/deploy README，无产品总览、架构、启动规则或开发规范变化，无需同步；仓库无AGENT.md。

### 进行中

- 本轮审计已完成，报告按当前dev分支提交推送；源码整改尚未开始。

### 阻塞与风险

- 无审计交付阻塞；当前保留2项P1、1项P2。SEC-01与SEC-04不再安排整改，原始复现证据保留，不将忽略写成修复完成。现存私网HTTP、部分内部HTTP及core共享进程Secret范围按已批准部署的信任边界列出，不冒充本轮新增回归。
- 未审计实际运行Secret、主机网络/证书状态、完整Git历史或容器OS漏洞，未证明现有环境已遭攻击或完成安全验收。

### 下一步

- 进入安全修复时，先处理SEC-02：为两种Nginx入口和服务端增加稳定来源的匿名预算，保留现有账号限流顺序和次数；随后处理SEC-03快照配额/复用/过期清理和SEC-05历史受理预算。本轮仅按用户要求解释SEC-03，不启动修复，不处理已忽略的SEC-01/SEC-04。

### 主要文件或模块

- docs/security/全量代码安全审计-2026-10-05.md、同名JSON、docs/README.md、PROJECT_PROGRESS.md；审查范围覆盖backend/services、backend/scripts/tests、frontend、example、deploy及.github/workflows。

### 验证

- Python AST解析无错误；Bandit全后端30823行有效代码，0 high/22 medium/1053 low，规则命中按上下文复核，测试断言和固定SQL片段不计为确认漏洞。services定向复核0 high/7 medium/7 low。
- OSV查询66个后端锁定包，2个包命中；frontend npm audit为3个moderate包节点、example为1个，均无high/critical。npm退出码1代表发现公告，未升级依赖。
- 4项小型合成复现完成：更换nonce的6次取图均受理、同nonce第6次429；5次无效challenge后目标账号第6次429；HTTPS支付地址降级到HTTP并接受合成PNG；3条样本/page_size=1的2次首页查询创建2快照及6成员。快照首次导入受Windows虚拟环境缺tzdata影响，改为验证进程使用系统已有tzdata目录后完成，未修改项目依赖。
- 未运行全量业务/浏览器测试或压力测试；未读取真实学校/邮件凭据或实际Secret，未连接真实学校、支付、SMTP、现有数据库及部署服务。提交前核对报告路径、JSON解析、git diff --check与仅文档差异。
- 用户结论同步仅复核快照源码与前端每60秒刷新规则、检查Markdown/JSON状态一致性和Git差异；不重复执行审计扫描或业务测试。总览/架构/开发规范未变，README、AGENTS及各工程README无需调整，无AGENT.md。

## 2026-10-05 · 七容器核心组合实施

### 已完成

- 核对dev/e881c93干净工作区、13容器combined运行状态、统一启停/恢复及CI入口；先落地docs/decisions/七容器核心组合.md。
- 重构原因：独立Python运行时与MySQL预留占用较高；影响公共运行上下文、内部调用、生命周期、邮件入口、迁移版本清单、Compose与运维/CI，保持数据库与外部API边界。
- 第一轮参数已落实：日志缓冲16MiB、key buffer 1MiB，保留Performance Schema并限制实例/摘要/历史容量；combined Nginx单worker，其他持久性与连接池预算不变。
- 0.19.0实现核心运行入口、52个现有内部接口直接分派、统一停止/独立心跳、无Web邮件上下文，以及构建迁移清单。保留原签名权限、DTO、数据库池/事务和外部TLS；同步版本/锁文件与受影响总览、架构、计划、开发和部署手册。
- 新增core Compose及local构建/restore覆盖，解析得到7个常驻服务与迁移/证书一次性作业。保留combined回退，CI增加原卷13→7→13和直接调用/故障检查。
- 定位任务开始前e881c93的CI收集失败为unit/integration的test_payment_polling同名，重命名单元文件；修正旧组合健康脚本漏列Room control和Payment reconciliation角色。

### 进行中

- 代码、定向验证、实际7容器运行与回退、内存和50合成监控交付已完成；源码提交8460c27的完整CI已成功。按用户要求准备dev→main PR，合并前仍须等待PR最新提交全部Actions成功。

### 阻塞与风险

- 无代码实施阻塞；700 MiB为目标，合并后故障和Secret访问范围扩大，真实学校/OCR/支付高峰不能由空闲数据推断。
- 现有elect-wsl正在运行，验证使用独立项目、合成凭据与数据，避免重复触发原监控/邮件/支付。

### 下一步

- 先按GitHub协作流程完成dev→main PR最新提交检查，以merge commit合入main并核对主分支push检查。后续在指定真实环境采用core时，按同一upgrade入口切换并实测完整Adapter首轮OCR、集中监控和支付/SMTP恢复峰值；原elect-wsl本轮继续保留13容器供用户使用。

### 主要文件或模块

- backend/services/common、core、notification、deployment；deploy及.github/workflows/check.yaml；相关部署/架构与验收文档。

### 验证

- 已只读核对13个elect-wsl容器健康；MySQL8.4.6无网络容器以全部公开参数执行validate-config通过，Nginx无网络配置检查通过，git diff --check通过。首次MySQL默认entrypoint要求初始化且Windows挂载文件被视为全局可写，因此最终改为直接mysqld参数验证；未将忽略配置的结果计为成功。未修改运行配置或加载真实凭据。
- Linux/Python3.12.10下34项定向验证通过，覆盖直接调用/HTTP的响应与拒绝一致性、身份和参数、迁移清单、独立心跳/退出；全后端ruff通过。Windows执行既有生命周期测试受到Linux绝对路径/时区前提限制，改用正式Linux容器验证，未为测试改变业务语义。
- 后端完整收集已恢复：277通过、4个数据库集成按环境跳过；6个运维Shell用例因Windows挂载CRLF失败，需在Linux LF检出重跑这6项。尚未将这一轮视为全绿或完成实际容器验收。
- Linux LF检出中12项运维选择/启动用例全部通过；CI后端已通过，继续发现旧账户组件测试仍点击已移除的查询按钮，改为验证自动更新。首次core入口预检暴露Nginx主进程无权读原应用UID的0400 CA，增加仅用于读取现有证书的DAC_READ_SEARCH，不修改Secret/私钥权限。
- 7容器实际启动全部健康，公开协议接口经Nginx/core返回200，内部TLS/身份/各领域角色检查通过；首次空闲快照约575MiB，持续采样中。3项核心部分启动失败/统一停止/任务失败健康检查通过。CI继续暴露旧T2手工夹具缺少side_effect_policy，补齐默认关闭策略，与正式上下文一致。
- 7次空闲采样平均577.39MiB（574.14–586.62），MySQL平均254.23MiB；保留128MiB Buffer Pool/40连接及事务刷盘。独立OCR合成图加载0.5328秒、峰值RSS118632KiB。实际7容器MQ降级/恢复禁用及原卷回退13健康容器通过。
- 50个合成监控集中到期，由真实领域后台的2个槽运行，伴随5并发150次页面读取；恰好50个成功run/样本，5.855秒，验证进程峰值RSS114484KiB。学校使用合成transport，独立进程峰值不当作完整7容器峰值。采样与验收范围已归档，CI新增此门禁并给新增有界步骤45分钟总预算。
- 追加退出异常检查：一个领域关闭失败仍等待其他领域结束后才释放资源，4项核心生命周期验证通过；11项Compose选择/恢复验证通过。CI此前已完成前后端、空库集成、无源码发布包、旧组合双向切换和资源参数，完整门禁仍以最终提交Actions为准。
- 本轮elect-test-core-local的所有profile容器与测试网络已清理，保留隔离Secret/命名卷供复查；没有删除原业务卷。原elect-wsl仍为13个健康容器，运行已持续6小时，本轮未停止或升级它。
- bcd2371的CI已通过全部前后端、数据库/消息、资源、备份恢复和新增7容器/50监控门禁；最后旧100计划容量用例失败，定位为新增回退步骤恢复13容器后，后台Worker与独立合成驱动争抢同一任务。修正CI串接：按本测试项目标签停尽应用/profile角色，再以统一compose入口和2+1池运行容量及隔离前端联调；不改业务领取/租约逻辑。
- 上述修复已用保留的隔离卷定向验证：100计划/8并发、100个签名唤醒与Inbox、每run唯一样本通过；真实生产前端/Nginx/领域容器8页面读取、无模拟路由、跨来源/CSRF/越权拒绝、跨标签退出和会话吊销均通过、页面错误0。再次清理全部测试容器/网络；原elect-wsl13容器仍健康、运行持续7小时。
- 2026-10-05核对[8460c27完整CI](https://github.com/ChaceQC/elect/actions/runs/37246348924)为success，check于北京时间08:35:21完成。合并准备时dev已包含origin/main（4ac0127），工作区干净，全部待合并差异git diff --check通过；main严格必需check/App15368、PR及管理员保护、禁止强推/删除均由GitHub API确认。本次仅补齐进度记录，README、AGENTS、前后端及deploy README无总览、规则或启动方式变化，无需修改，仓库无AGENT.md；不重复执行本地全量测试，合并结果以PR和main的实际Actions状态为准。

## 2026-10-05 · WSL 部署与内存采样（0.18.3）

### 已完成

- 在本机 Ubuntu-24.04/Docker29.1.3/Compose2.40.3 新建 elect-wsl，使用 aa7c5ad 源码构建前后端 runtime、combined 组合及独立 Secret/三个卷，13个长期容器健康；入口 http://172.23.107.48:6874。原10.8.0.88环境不在本机WSL，未改动它或其他项目容器。
- 按用户追加要求开启本地绑定、支付建单/表单/能力门槛及真实SMTP；专用无网络进程导入 email_auth.txt，未输出凭据。未登录学校、建单、付款或发送测试邮件。
- 补装缺失的Docker Buildx；Windows脚本CRLF不适用于sh，因此在/home/cloudhelm/elect-wsl检出同一提交的LF副本。本地deploy/.env.wsl被Git忽略，真实Secret只保存在WSL受限目录。
- 定位容器一起停止为WSL/systemd整体退出、Docker正常终止，非OOM；用户明确要求自行保持运行后，成功启动隐藏WSL保活进程（启动时Windows PID20488），未设置开机计划任务。
- 稳定运行后7次采样：全栈1332.31–1339.84MiB，平均1336.08MiB（约1.305GiB），不计WSL/Docker守护进程；逐项原始数据和启停方式已落文档。
- 同步AGENTS、文档导航和deploy README。根/前后端README无产品能力、目录或通用启动规则变化，无需修改；仓库无AGENT.md。

### 进行中

- 运行环境保留供用户使用；本轮部署记录按当前dev提交推送。

### 阻塞与风险

- SMTP开关和凭据已生效，但正式Worker直连以及既有DoH/eth0定向检查均在connect阶段ConnectionResetError，尚未通过TLS/认证；不描述为邮件可投递。
- 当前采样为空业务库/无活跃监控、订单和邮件任务的启动基线，未加载登录OCR或施加并发负载，不能替代2核2GB/50人/24小时容量验收。
- WSL保活仅适用于当前Windows会话；重启/主动关闭WSL后需恢复会话并核对可能变化的私网IP。

### 下一步

- 处理本机Windows/WSL至指定SMTP的出口连接重置，再从正式Worker验证TLS/认证；不关闭TLS验证、不自动扩大真实发送范围。后续开发仍按第五步页面稳定刷新与引用安全清理推进。

### 主要文件或模块

- docs/runbooks/WSL部署与内存.md、docs/acceptance/WSL内存2026-10-05.json、docs/README.md、deploy/README.md、AGENTS.md；本地忽略配置deploy/.env.wsl及WSL运行环境。

### 验证

- 前后端runtime构建、镜像版本/源提交一致性、Compose配置、Nginx预检、七域迁移通过；页面/healthz/登录协议接口均200；采样结束13/13健康，OOMKilled均false，保活后无容器重启。
- 7次docker stats、Linux free和Windows vmmemWSL分别记录；后者约3977.37MiB，包含系统/Docker/缓存，不计入项目总量。
- SMTP首次普通连接及保活后的普通/定向连接未通过，未发送正文。定向探针最初以去除DAC权限的root读取应用所属0400文件失败，改为文件所属UID后完成检查，未修改Secret权限。
- 未运行全量测试或压力测试；未读取学校凭据、未触发学校写或真实邮件发送。此前后台保活命令曾被自动审批拒绝，用户再次明确授权后执行成功。

## 2026-10-05 · 搜索焦点与采集明细更新修复（0.18.3）

### 已完成

- 定位搜索粗边框仅落在内部input的问题，改为整个搜索容器的focus-within，覆盖图标并保留键盘焦点反馈。
- 确认采集查询没有50条上限，total来自当前日期范围的固定快照；旧页面没有定时更新，重新查询仍带旧token。
- 第一页可见时每60秒重新获取最新快照、隐藏暂停、恢复可见时刷新过期查询；后续页沿用原快照，缓存加入token防止新旧分页混用。保留刷新回到第一页与错误恢复入口。
- 同步学生端README与快照契约说明；根README、AGENTS及后端README无总览/架构/启动规则变化，无需修改；无AGENT.md。

### 进行中

- 本轮源码与定向验证完成，按dev提交推送交付；现有运行环境尚未升级。

### 阻塞与风险

- 无实施阻塞；截图不能证明后台采集停止，本轮不读取真实凭据或修改现有运行环境。

### 下一步

- 后续升级前端后，核对真实账号首页的最新采集时间与总数是否随成功采集增长；若仍不增长，读取对应monitor/run状态与错误分类定位采集端，不修改历史数据。

### 主要文件或模块

- frontend/src/styles/rooms.css、features/history/SamplesPanel.jsx、tests/e2e/search-samples.spec.js、frontend/README.md、docs/contracts/README.md。

### 验证

- WSL隔离Node22.23.2容器执行lint/typecheck/生产构建通过；6项定向浏览器场景通过，覆盖1440/375px焦点、既有日期/寝室/深链接分页、50→51→52→53条增长、分页token隔离、隐藏暂停与恢复。首次隐藏恢复场景因合成visibilitychange没有冒泡而失败，按浏览器事件语义修正夹具后两项通过，未为测试更改业务实现。
- 桌面与手机焦点截图已与同视口参考核对，图标包含在粗边框内、移出焦点恢复且无横向溢出；证据见docs/acceptance/frontend/0.18.3搜索与明细.md。
- git diff --check通过。未运行全量测试，未读取真实凭据，未执行学校、SMTP、支付或运行环境部署操作；不以合成增长证明真实后台持续采集。

## 2026-10-05 · 解绑缺席确认间隔纠正（0.18.3）

### 已完成

- 修正此前只将回查改为2秒、却保留30秒缺席确认窗口的遗漏：School Adapter确认SQL改为两次有效B02缺席、数据库时间至少间隔2秒。重现/查询失败重置观察、unknown不重发与失败30秒退避保持。
- 同步真实台账证明脚本的最小间隔断言、合成烟测的回拨间隔，以及AGENTS、学校API文档、开发说明和两份决策文档；历史30秒真实验收记录保留。
- 已检查根/后端README，无总览、启动或目录变更，无需修改；仓库无AGENT.md。

### 进行中

- 当前dev源码交付；现有运行环境尚未升级。

### 阻塞与风险

- 无实施阻塞；实际完成仍受学校响应与账号排队影响，2秒窗口不代表整个解绑2秒完成。

### 下一步

- 后续升级运行环境时更新School Adapter及既有前端/Room改动，核对指定解绑操作的两次缺席确认与页面自动完成。

### 主要文件或模块

- backend/services/school_adapter/application/removal_writes.py、backend/scripts/t3_live_removal_proof.py、backend/scripts/t3_removal_smoke.py及相关规则文档。

### 验证

- WSL/Python3.12.10执行既有test_removal_polling.py，3项通过，覆盖控制独立调度及正常2秒/异常30秒回查；静态核对确认SQL和证明脚本阈值均为2秒；三个受影响Python文件ruff及git diff --check通过。
- 本轮未运行数据库集成/全量测试，未调用真实学校、未读取凭据、未部署；不将历史30秒真实验收作为新窗口验收。

## 2026-10-05 · 自动确认、后台认证与刷新反馈修复（0.18.3）

### 已完成

- 核对支付回查与建单/取码共用执行循环、回查完成后等待30秒及页面120秒停止轮询的延迟来源。

- 按用户要求拆分支付回查异步角色，保持同域上下文、独立心跳、持久租约和原学校并发限制；不增加常驻容器。
- 按用户最终指定间隔，正常支付/解绑后台回查与可见页面刷新统一为2秒，异常回查退避30秒。页面隐藏暂停，终态停止，余额待刷新继续读取。
- 重构原因：慢建单/取码阻塞支付确认；影响Payment调度/提交竞争、公共后台角色和支付页面轮询，不改变学校付款证据要求。
- 用户追加解绑卡住：Room控制任务从同步/余额/历史循环拆分为独立异步角色；仍要求两次成功B02缺席，按用户再次纠正将确认间隔由30秒改为至少2秒，解绑页面持续自动更新并在终态刷新绑定列表。
- 用户追加刷新反馈：共享余额/历史刷新入口用旋转图标代替重复受理/读取/完成与同步范围文字，绑定同步和采集明细刷新同样使用动画；错误、未知、取消和无障碍状态保留。
- 用户追加后台认证：每轮最多取5张验证码、最多提交2次登录；只有学校明确拒绝才换新验证码重试提交，OCR失败消耗取图预算，超时/不确定错误不重放，沿用总deadline与账号限流。拆出小型后台认证模块以保持sessions职责清晰。
- 同步前后端版本与锁文件、OpenAPI版本、公开镜像模板、根/前后端README、AGENTS、计划/决策和验收；无AGENT.md，未改真实配置。

### 进行中

- 本轮源码与定向验证已完成，按当前dev提交推送交付；运行环境尚未升级。

### 阻塞与风险

- 无实施阻塞；查询间隔不包含学校响应耗时和账号锁等待，不能承诺2秒内确认到账。
- 本轮仅源码与隔离合成验证，不自动升级当前运行环境或开放支付。

### 下一步

- 后续升级运行环境时同时更新前端、Payment、Room和School Adapter，核对现存支付/解绑操作的自动完成与5图/2次认证上限；项目下一开发项仍为第五步稳定页面刷新和引用安全清理。

### 主要文件或模块

- backend/services/payment、room、school_adapter/application/background_auth.py与公共后台生命周期；frontend支付/解绑轮询、QueryAction、绑定同步/采集明细刷新及样式。

### 验证

- WSL/Python3.12.10下39项后端定向单位验证通过（调度隔离/生命周期29项、认证预算及会话10项）；一次性MySQL8.4.6下3项并发验证通过，覆盖单回查租约、QR不推迟回查、确认与QR并发、迟到写入/取消及余额刷新。测试容器执行后删除，不触及已有卷。
- Node22.23.2隔离容器中16项前端规则/组件验证通过；最终2秒规则下7项支付/解绑/页面场景、6项查询场景和2项动画场景通过。1440×1000及375×1000截图已对照同视口参考核对，刷新图标无重复文字或横向溢出；动画停止、错误可见和减少动态效果均通过。
- 受影响Python ruff、前端lint/typecheck/生产构建、OpenAPI/内部协议与uv锁一致性、git diff --check通过。新动画测试最初把屏幕阅读器隐藏文字当成可见文字，修正为隐藏样式/按钮尺寸检查后通过；没有为测试改动业务行为。
- 未运行全量回归、未调用真实学校/SMTP/支付、未读取真实凭据、未部署现有环境；截图与范围见docs/acceptance/frontend/0.18.3自动更新.md。

## 2026-10-04 · 移除手动查询进度入口

### 已完成

- 移除寝室操作、余额/历史同步、旧凭据操作和支付订单的手动查询进度按钮，支付相关提示同步改为自动更新。
- 保留现有自动轮询、终态更新、错误提示和120秒暂停后的恢复入口；实际学校查询与未知受理的原请求恢复不变。
- 同步既有绑定/解绑/认证/支付验证，改为等待自动更新；同步前端README、AGENTS、前端计划与界面决策。根README无总览/启动/目录变化，无AGENT.md。

### 进行中

- 源码与定向验证已完成，按当前dev提交推送交付；部署待后续升级。

### 阻塞与风险

- 无实施阻塞；本轮为前端源码调整，尚未部署到现有环境。

### 下一步

- 后续部署升级时核对寝室、账户和支付弹窗中按钮移除及自动更新；本轮不扩展第五步稳定刷新/数据清理任务。

### 主要文件或模块

- frontend/src/features/rooms、history、auth、payments及对应既有测试；前端README、AGENTS、前端计划与界面决策。

### 验证

- Node22.23.2下6项绑定/解绑组件测试通过；14项浏览器场景通过，覆盖1440/375px绑定、解绑、认证、支付自动查询及两分钟暂停恢复。前端lint、typecheck、生产构建和git diff --check通过。
- 首次系统Node24.13.0下6项组件测试在会话初始化失败，改用项目指定Node22.23.2后原用例全部通过；未为运行环境修改业务代码。浏览器使用本机Edge与合成接口，未执行真实学校、SMTP或支付，未运行后端全量测试。

## 2026-10-04 · 电表采集与缴费订单回查修复（0.18.2）

### 已完成

- 根据用户截图定位：采集入口只读B02，样本写入固定balance_only，前端已有电表展示字段；支付取得prePayId后仅查D02，D02失败会跳过D04。
- C02辅助读数/加密缓存/原栅栏内持久字段已实现，新鲜余额失败不伪造、辅助失败保留balance_only；旧样本不回填。真实本人最新采集返回2026-10-03日读数、meter_not_realtime。
- 支付移除误用水费D02，接入D04精确标识，或唯一同学校用户/寝室/金额/建单后记录加原支付页完整已支付提示。原票据64位、学校订单号19位，没有强行伪造编号对应。
- 按用户追加授权，本轮只执行一次1元D01，应用订单01a1074f-fe9f-7bfd-ad03-eed901ad6144。用户于学校记录的22:38:13扫码付款；D04本人/寝室/金额匹配、余额增加1.00元；正式回查自动更新paid_confirmed，持久余额刷新succeeded，没有手工改状态。
- 付款码实际解码为weixin://wxpay/。原自动E02超时unknown保留；根据用户要求同原单显式恢复取码，用独立加密阶段日志防重，不再创建D01。生产表单对齐UTF-8与Connection close，默认不自动重放未知表单。
- 55项定向验证通过；同步版本/锁文件、契约说明、根与前后端README、AGENTS、架构/计划、学校文档和真实分类证据，无AGENT.md。

### 进行中

- 实现和指定真实验收已完成，交付提交e2e66fa已推送origin/dev；已保留远端6df7c05的0.18.1运行部署记录。尚未部署0.18.2到截图对应的既有环境。
- 重构原因/范围：将C02读数选择和学校订单确认拆到独立模块，保持原采集/支付持久栅栏，不扩展其他业务。

### 阻塞与风险

- 无实施阻塞。公共支付开关保持关闭；一笔真实付款不代表全部过期/关闭状态、生产容量或T8验收，原自动QR超时台账保留。
- 首次误交订单页面入口码已按用户纠正换成学校原生微信付款码；入口码生成分支已删除，不以入口码作为支付二维码验收。

### 下一步

- 交付dev后，在后续部署升级时复核新采样的电表展示与本次支付确认逻辑；本轮不自动发布镜像、合并main或升级截图环境。项目下一阶段仍为第五步页面稳定刷新与引用安全清理。

### 主要文件或模块

- backend/services/school_adapter/、monitoring/results.py/worker.py、payment/reconciliation.py；定向测试、专用验收脚本与docs/decisions/电表读数与缴费结果确认.md。

### 验证

- WSL Ubuntu-24.04/Python3.12.10：最终55项定向验证通过；真实最新B02/C02及指定1元D04/原票据/正式Payment状态与余额刷新均通过。分类证据见docs/acceptance/school/2026-10-04-meter-payment.json。
- 受影响源码ruff、公开/内部契约生成检查、uv锁一致性与git diff --check通过。前端源码/布局未改，本轮没有重跑全量前端构建或浏览器套件。
- 单笔验收使用宿主uv锁定解释器和Docker隔离MySQL/Redis、七域正式迁移；首次NTFS挂载初始化脚本被当作可执行文件，调整为直接挂载SQL后完成。仅移除本轮失败的空容器，旧初始化卷保留，新业务卷为elect-test-meter-orders-mysql-v2。
- WSL会话结束会停止本轮容器，验收入口已增加仅启动本轮MySQL/Redis并等待就绪；不重启其他项目。持久证据在WSL /home/cloudhelm/.local/state/elect-test-meter-orders，Secret与订单票据均不提交；需要回查时使用local_payment_acceptance的check阶段和上面的原订单ID，禁止再建新单。

## 2026-10-04 · 拉取最新dev并重新部署本机（0.18.1）

### 已完成

- 干净dev从cf7365a快进拉取origin/dev至7dfdadf80d6b0329482e66c5cbf45586b183728f；按用户本次要求恢复原elect-local部署。
- 从该源提交构建elect-backend:v0.18.1与elect-frontend:v0.18.1，两张OCI镜像版本v0.18.1/源提交一致并通过实际元数据校验；使用local源码模式，未将本次部署描述为0.18.1的CI镜像发布。
- 升级前保留受限原env/Secret副本，并完成七域MySQL一致快照加密和完整性校验；离线重复upgrade_controls补齐既有MQ权限，19项既有密码/密钥/证书/SMTP配置文件逐项保持。
- 保留三个elect-local命名卷及私网10.8.0.88:6874入口，显式选择combined与既有SMTP定向通道，按基础服务→迁移→八API→通道/发送Worker→Nginx串行等待。14个长期容器全部healthy，17个旧独立后台角色保持停止；原5个其他项目容器保持运行。
- 同步本机运行边界与部署手册，保留既有SMTP/页面确认绑定开关，支付建单/表单及验收开关仍false。部署恢复原1个启用监控，不新增监控、订单或测试邮件。

### 进行中

- 本次拉取和重部署已完成，原业务保持运行；本轮只同步部署记录，不扩展实施第五步页面请求/留存清理任务。

### 阻塞与风险

- 无重部署阻塞。服务健康与本机运行检查通过，不代表2核2GB/50人24小时容量、真实D02映射、生产异机/PITR或T8验收；域名/入口证书仍按既有范围跳过。
- 0.18.1为本机源码构建；本轮未创建版本标签、发布GHCR或合并main。自然恢复的后台监控仍可能按既有授权访问学校及满足条件时发送邮件，不能将恢复运行描述为完全无外发的隔离验证。

### 下一步

- 保持本机业务运行；下一具体开发任务仍为第五步稳定页面30–60秒刷新/隐藏暂停与50人共享出口登录防护，完成后实现样本12个月、尝试90天、台账至少180天的引用安全小批清理。

### 主要文件或模块

- 本机受限deploy/.env.local、/opt/elect-local/secrets及原MySQL/Redis/RabbitMQ卷；统一compose.sh与combined/local/SMTP覆盖。
- AGENTS.md、PROJECT_PROGRESS.md、docs/runbooks/本机私网部署.md；根与各子目录README的版本、结构及入口无需变更，无AGENT.md。
- 受限备份/运行证据：/opt/elect-local/redeploy-0.18.1-20261004T211934/；备份密钥单独保存于/opt/elect-local/backup-keys/，均未纳入Git。

### 验证

- 前后端Docker构建通过，前端Vite生产构建成功；两张运行镜像通过release check-images版本/源提交校验，Compose配置及Nginx预检通过。
- 七域迁移全部migration_completed，升级前后revision相同；加密快照verify通过，三个原数据卷保持，既有Secret不可变文件比较通过。
- 14/14运行容器healthy、0重启/0OOM；唯一发布端口为10.8.0.88:6874。健康入口/首页/实际协议API均200，协议版本2026-10-04.1、内容hash及no-store正确，首页JS/CSS与新Nginx镜像字节hash一致。
- status读取通过：七域未发布Outbox均0，原Room积压1条已消化；1个监控继续active、调度延迟0，成功run由40增至41，无待重新认证/学校写未知/绑定未知。通知台账仍为原5条sent（仅表示SMTP接受），支付订单仍为空；本轮未人工学校登录、绑定/解绑、建单/付款或测试投递。
- 4个文档本地链接及4段Shell示例语法通过；真实env/测试凭据忽略规则、受影响README/AGENT检查和git diff --check通过。部署记录按仓库规范在当前dev直接提交推送。

## 2026-10-04 · 界面问题修复与登录协议授权（0.18.1）

### 已完成

- 核对用户提供的13项静态问题、当前dev与干净工作区，确认登录/重新认证统一同意后台授权，移除单独授权和撤回按钮。
- 协议2026-10-04.1、登录请求true约束、Room绑定写能力字段及生成契约/类型完成，版本同步为0.18.1。后端9项、前端31项定向检查通过。
- 13项修复已完成，25项受影响浏览器场景分批通过；1440/375px截图及10张同视口并排对照完成，分页回退同步刷新旧缓存，支付能力关闭仍可恢复原订单。
- 协议/授权与绑定能力小步eee8015已推送origin/dev；根/子README、AGENTS、计划、契约与验收同步，无AGENT.md。真实凭据/依赖/构建产物均仍被忽略。
- 按用户追加要求删除登录页额外授权长说明及阅读提示，保留协议入口/同意勾选，授权条款只在协议正文中展示。

### 进行中

- 本轮实现与WSL验证已完成，按当前dev提交推送交付；原业务未启动，未部署新镜像。
- 调整原因及范围：公共轮询暂停状态需要在操作/采集/订单一致展示，抽取共用轮询计时；其余保持现有页面结构和持久操作语义。

### 阻塞与风险

- 无实施阻塞；仅使用合成接口验证，不读取真实凭据，不启动原业务或调用真实学校、SMTP、支付。第五步其余留存/容量任务不在本轮范围。

### 下一步

- 完成本轮dev交付后，下一具体项目任务仍为第五步稳定页面30–60秒刷新/隐藏暂停与50人共享出口登录防护，然后实现样本12个月、尝试90天、台账至少180天的引用安全小批清理。本轮不自动扩展实施范围。

### 主要文件或模块

- frontend/src/features/、frontend/src/hooks/、Identity协议与Room能力、docs/contracts/及相关测试/文档。

### 验证

- WSL后端协议/契约7项和绑定能力2项、前端31项定向验证通过；前端lint/typecheck/契约生成检查和生产构建通过。25项浏览器场景分批通过，截图/可见限制/键盘/无横向溢出已核对，未执行真实学校/SMTP/支付。
- 最后按用户反馈删去登录页长说明与阅读提示，追加复验仅覆盖登录/视觉6项并更新截图，全部通过；协议中的后台授权条款和登录true提交保持。
- 检查时WSL无运行容器，原Tianxin12个/CloudHelm2个保持停止；验证容器均--rm且不开放网络，保留原容器和卷。详细范围及截图见docs/acceptance/frontend/0.18.1界面问题修复.md。

## 2026-10-04 · Docker低资源优化第五步镜像批（0.18.0）

### 已完成

- 核对前四步交付、当前dev/干净工作区及最新Actions成功；原业务/历史elect项目保持停止。
- 完成基础运行/本地构建配置拆分、固定摘要与OCI版本/源提交校验、首次/原卷串行无构建入口和标签CI受测runtime发布/部署包/开发版资产。
- 本地231后端回归及18项相关验证通过，固定脚本后原卷13容器全部healthy，可靠事件smoke/仅deploy包原卷启动均通过；标签CI完整通过并已实际发布GHCR镜像及3项开发版资产，公开摘要证据保存在docs/acceptance/Docker低资源第五步镜像发布.json。

### 进行中

- 第五步镜像发布/启动批已完成；页面稳定刷新、校园共享出口登录防护与引用安全小批留存清理待实施，第五步整体仍未完成。
- 重构原因：基础Compose混入构建入口、升级同时启动全部应用；拆出仅本地构建覆盖，统一首次/升级的预检、摘要拉取、旧角色停止和按依赖启动。范围仅部署配置/脚本与发布元数据，不改变副作用授权。

### 阻塞与风险

- 镜像批无阻塞。第五步页面请求/留存及2核2GB/50人24小时、真实D02、生产异机/PITR和T8仍未验收；当前镜像仅linux/amd64。真实凭据和学校/SMTP/支付不参与本轮。

### 下一步

- 将稳定监控页面刷新改为30–60秒并保留操作后刷新/隐藏暂停，验证50人共享校园出口的登录防护；随后接样本12个月、尝试90天、台账至少180天的引用安全小批清理，完成第五步后再做第六步目标机24小时验收。

### 主要文件或模块

- deploy/compose.yaml、compose.build.yaml、compose.sh、settings.sh、start.sh、upgrade.sh及CI/镜像发布元数据。

### 验证

- 已确认Docker/Compose可用、最新既有Actions成功。后端ruff、231 passed / 1 skipped、OpenAPI及七域表目录检查通过；18项发布/选择器/启动边界测试通过。
- 新空库首轮13容器healthy，但运行中编辑脚本造成shell读取偏移，未计整轮通过；固定脚本后同原卷start/upgrade成功。仅deploy的Git归档无frontend/backend、published选择无构建启动13容器/七域角色ready、零OOMKilled/零重启通过；可靠事件smoke通过。
- 源码提交2e130f1已推送origin/dev，v0.18.0标签CI 37198320789为success：231后端/49前端/32浏览器、新空库合成T2–T6、无源码包、13→30→13、池/MQ/Redis、推送双槽/取消、加密隔离恢复及模拟容量/生产前端均通过。
- GHCR实际后端/前端摘要、源提交2e130f199691664dd004980f715aaebe6f934e52和check链接已核对；GitHub开发版3个资产已下载核验，51个归档成员只含部署/手册，所有默认副作用false、容量验收false。
- 本机仅down本轮测试项目，保留3个命名卷/受限Secret和证据；所有elect运行容器为0，其余原5个容器仍运行，未重启原业务。

## 2026-10-04 · Docker低资源优化第四步（0.17.0，2026-10-03开始）

### 已完成

- 完成DomainEngine成功COMMIT后Outbox提示、连接标记清除及1→2→5→10秒空闲退避/每批16条/故障抖动；发布租约、confirm后条件标记、持久重试和扫描保持。首小步2be809f已提交并推送origin/dev。
- 接通basic.consume/prefetch=1、有界本地缓冲、重连失效与未ACK重投；Monitoring两个TaskGroup槽共用上下文/独立channel，邮件独立单槽，学校5/4/1共享限制及原续租/取消/退出预算不变。
- 按角色保留控制/调度/恢复周期，执行/回报空闲退避；Adapter60秒、每批100清理，积压继续小批/10秒实际读库健康。
- 修复既有room.binding_confirmed缺MQ权限：补最小Topic写/读和既有运行队列路由，消费只记Inbox、不据提示建run；重复离线upgrade_controls保留密码/密钥/原卷。新增13项必要回归、第四步隔离入口及CI步骤，兼容已有容量脚本两类提示。
- 同步0.17.0版本、锁文件/公开模板/契约元数据、根/子README、AGENTS、架构/计划/部署及方案；新增执行效率决策/第四步验收，第四步已勾选，无AGENT.md。
- 验证后只down本轮来源/恢复项目，保留6个命名数据卷和加密/受限证据；所有elect运行容器为0，原业务/历史项目停机，原5个其他容器保持运行。

### 进行中

- 第四步实现与隔离验证已完成，在当前dev提交推送交付；第五至六步未交付，原业务部署保持停止。
- 重构原因及范围：降低Relay空闲扫描/basic.get/串行执行开销，涉及公共事务/消息、各域提示及Monitoring并发/Adapter清理；公共业务API、数据库结构与副作用开关不变。

### 阻塞与风险

- 第四步无实现阻塞。2核2GB/50人24小时、固定镜像发布/长期运行、真实D02、生产异机/PITR与T8仍未验收；既有证书跳过边界保持。未读取真实凭据或调用真实学校/SMTP/支付。
- 初始两轮同栈误重叠；顺序复测定位已登记Room事件缺权限，旧首小步Actions也失败于ready。补最小权限/路由和Inbox消费后，最终各轮按顺序通过，没有放宽健康检查。双槽使旧瞬时空闲连接数断言失效，改实际借满池容量及API/续租验证。
- 资源复测继承umask077，公开测试ACL600使独立Redis无法启动；显式设置该公开ACL644（受限目录/正式Secret规则不变），保留失败证据、新目录重跑通过。默认地址池耗尽仅为本轮使用10.247/10.248小网段，不清历史网络或改全局配置。

### 下一步

- 按第五步先为后端/前端镜像增加CI构建/测试/固定版本与摘要发布，提供目标机只拉取、无构建、基础服务→迁移→应用的分阶段启动及限制启动并行度；随后实现稳定页面请求和按既有留存政策的小批清理，再进行第六步2CPU/2GB长期验收。

### 主要文件或模块

- backend/services/common/database.py/outbox.py/scheduling.py/push_consumer.py/broker.py/job.py/business_worker.py；Monitoring/Notification/Room/Payment任务及deployment/query_queues.py/notification_queues.py。
- backend/scripts/outbox_efficiency_smoke.py/monitoring_parallel_smoke.py/monitoring_combined_smoke.py/domain_combined_smoke.py/t7_capacity.py、相关单位回归；deploy/test-execution-efficiency.sh/test-redis-budget.sh及CI。
- docs/decisions/Docker低资源执行效率.md、acceptance/Docker低资源第四步验收.md、方案、受影响文档与版本/锁文件。

### 验证

- 最终sh deploy/check.sh通过：后端ruff、220 passed / 1 skipped、公开/内部契约/表目录/七域离线DDL；前端规则/类型/契约/构建、49项单元组件、32项Playwright通过。
- 新空库test-stack combined通过七域权限/并发迁移、可靠事件、T2–T6合成学校/SMTP/支付、真实MySQL/Redis/MQ故障及TLS/Nginx。最终旧Secret修复/原卷13→30→13全部healthy、17旧角色退出，restore八API无后台、独立入口拒绝。
- 最终第四步专项通过：11秒空闲4次Relay扫描，约0.107秒提交到confirm；回滚无提示、另一engine无跨进程提示仍持久发布；实际MQ停机未ACK重投/Inbox回滚重投/提交后ACK、两次重复最终审计与Inbox各一条。
- 3个合成账号、两个学校请求/Redis后台槽、第三个pending，36个控制请求全200、两租约真实续期；取消/关闭阻断迟到样本，第三个单样本；同场景实际无MQ再次通过。50旧/重复提示、旧epoch拒绝、崩溃接管/重启、在途统一退出及合成SMTP/支付unknown不重发通过。
- 2+1池实际借满3条、50个同账号读取2.2105秒并真实续租；满池等待0.2013秒/超时3.0004秒/归还0/UTC。32个健康请求0.1226秒全ready，MySQL最高20连接/0上限错误；MQ流控期间已尝试的Outbox未published，解除后唯一完成，Redis写满/noeviction/AOF/重启零OOM通过。
- T7加密快照/封存binlog、62表计数/密文保留、快照后学校建单/邮件unknown与旧Outbox不重放、重复apply通过；本机合成RPO4.703秒/RTO69秒，不外推生产灾备。已有容量脚本100计划/8脚本执行器/30ms学校、100提示与样本唯一/共享学校峰值5通过，不能当双槽或目标机容量。

## 2026-10-03 · Docker低资源优化第三步（0.16.0）

### 已完成

- 在combined八个持库入口固定2+1，理论应用连接40→24，Gateway无库、发送Worker仍独立；3秒等待/回收、UTC、READ COMMITTED与原租约/控制语义保持。
- MySQL附加参数40连接/128MiB Buffer Pool、256/400 cache、32MiB TempTable与8MiB单表/640MiB限额，实际核对binlog/两项事务刷盘均为1；standalone保留原配置。
- Redis32MiB/noeviction/AOF与96MiB限额，实际写满拒绝而不淘汰、重写并发/重启保留合成会话/锁/槽；普通RabbitMQ固定摘要、核心定义导入/1调度2异步各1脏线程/128MiB绝对水位/256MiB限额，兼容旧Secret/账号/队列和原卷双向切换。
- 13容器Docker探针30秒/启动5秒、约60/120秒故障判定，原20/45秒后台心跳不变；OCR锁定已有ddddocr1.6.1/ONNX1.30，单会话各1线程/顺序执行/禁自旋、BLAS/OMP各1，保留冷加载/推理锁/人工验证码，Adapter384MiB限额。
- 增加满池/健康/MQ流控/Redis真实预算/OCR探针与9项必要单位用例，合并采集补单合成账号50次并发控制读取及实际续租；CI增加第三步入口。两段uv sync复用BuildKit锁定依赖缓存，生产镜像不包含缓存，固定镜像发布仍待第五步。
- 同步0.16.0版本/锁文件/契约元数据、根/子目录README、AGENTS/架构/总与后端计划/部署/恢复/容量/本机手册及优化方案；新增资源决策、第三步验收与逐项/cold/OCR/Redis/恢复资源JSON，无AGENT.md。

### 进行中

- 第三步实现和隔离验证已完成，交付在当前dev提交并推送；第四至六步尚未交付，原业务环境保持停机。

### 阻塞与风险

- 第三步无阻塞。2核2GB/50人/24小时、实际运行API加载OCR、多账号恢复、持续负载备份峰值及生产灾备仍未验收；真实D02、生产异机/PITR、T8和既有证书跳过边界保留，没有读取真实凭据/调用真实学校/SMTP/支付。
- 首次MySQL嵌套只读conf.d挂载失败，改目录外defaults-extra-file后生效值/原卷/空库通过；Redis/Nginx补Docker要求的start_period后30秒探针启动通过。
- 首次依赖下载过慢，停止该次构建，加BuildKit缓存并从旧测试镜像中相同锁定依赖播种，正式Dockerfile运行/测试/check/空库镜像通过。没有改变依赖实际锁定版本或将缓存放入运行镜像。
- Docker默认地址池耗尽，新测试项目仅使用10.243/10.244小网段；恢复首次失败后补10.245内部网段并从已存加密快照继续，未删历史网络/修改全局地址池。恢复RTO59秒只计成功重入，不含首次失败/排障。
- 本轮基线末次13容器1394.09MiB，最终另一空库首次healthy末次1237.68MiB（约降11.2%），2秒采样窗口峰值1257.93MiB/零OOM。各容器memory.peak与OCR RSS另列，不相加作全栈同一时刻峰值；不作为2GB可用结论。

### 下一步

- 按第四步先实现本域事务成功提交后Outbox唤醒和1→2→5→10秒空闲退避，保留可靠扫描、confirm后标记与发布租约；用MQ断线/重连、重复提示和取消/授权撤回验证，再接推送消费及有限业务并发。

### 主要文件或模块

- backend/services/common/database.py、school_adapter/infrastructure/ocr.py、deployment/provision.py/operations_status.py、Dockerfile与依赖锁。
- backend/scripts/database_pool_probe.py/resource_parameters_smoke.py/ocr_resource_probe.py/monitoring_combined_smoke.py、tests/unit/test_database_pool.py/test_ocr_resources.py/test_provision.py。
- deploy/compose.low-resource.yaml、mysql/low-resource.cnf、rabbitmq/low-resource.conf、公开模板、test-low-resource.sh/test-resource-parameters.sh/test-redis-budget.sh及CI。
- docs/decisions/Docker低资源资源参数.md、acceptance/Docker低资源第三步验收.md/资源.json、方案及受影响的计划/架构/部署/运维和根/子README/AGENTS。

### 验证

- sh deploy/check.sh通过：后端ruff、207 passed / 1 skipped、公开/内部契约/目录/七域离线DDL；前端规则/类型/契约/49项单元组件/构建、32项Playwright通过。资源压力脚本最后加强“Relay已尝试发布”断言后ruff与最终真实基础服务验收通过。
- 满池三条，第4条等待归还约0.20秒；饱和约3.00秒超时、归还后0借出/ready/UTC；32个真实HTTP健康请求约0.119秒全部ready。2+1下单合成账号50个并发监控读取约0.604秒全部200，学校等待期间实际续租/后台健康保持；不是50名账号容量。
- test-low-resource旧Secret/原卷MQ故障降级与持久扫描、恢复无后台、取消/单样本/旧epoch/接管/退出及七域合成unknown通过；13→30→13双向切换全部healthy，17旧角色全部exited。
- 最终新空库test-stack combined通过七域权限/并发迁移、签名/Inbox去重、T2–T6合成学校/SMTP/支付与实际MySQL/Redis/MQ中断、内部TLS/Nginx，13长期容器全部healthy。
- test-resource-parameters两次通过，最后一次是最终空库/镜像；MySQL生效值/持久性、最高19连接/0上限错误；MQ实际1/2线程/无management/128MiB水位，内存告警时已尝试Outbox未published，解除后Audit/Inbox与Outbox唯一完成。
- 无网络Redis实际OOM写入拒绝、0淘汰，AOF明确开始/并发更新/终态ok/重启保留会话锁槽，96MiB限额下实测内核峰值72.27MiB、0OOM。单独1CPU OCR同图10次结果摘要不变，线程17→2、P50约82.06→12.76ms、2秒空闲CPU0.3045→0秒；不是学校验证码识别率验收。
- T7加密快照/封存binlog与隔离恢复最终通过，62张表计数/密文保留、快照后合成邮件/建单unknown、旧Outbox无自动重放、重复apply通过；RPO4.548秒、成功重入RTO59秒，未外推生产。冻结应用后的备份/恢复基础服务0OOM。
- 最终104个受影响Markdown本地链接、版本/锁文件/资源JSON、Shell语法、公开standalone/combined/all-profile restore配置、真实凭据忽略与git diff --check通过。仅down本轮来源/恢复项目，保留9个命名数据卷和受限证据；所有elect运行容器0，其余原5个容器保持运行。

## 2026-10-03 · Docker低资源优化第二步（0.15.0）

### 已完成

- 将Monitoring试点推广到七域，共用本域engine、按需复用ServiceClient和一条AMQP连接；独立channel/角色心跳，统一退出。Gateway无库，Notification发送Worker独立，领域权限/TLS/持久屏障与副作用开关不变。
- 交付compose.low-resource.yaml：基础长期容器30→13，Python进程26→9；17个旧后台放入非默认profile并拒绝独立combined入口。Room/Identity逐项停止新领取，Payment唤醒后再次检查；保留120/90/170秒在途窗口，统一退出125/100/180秒及对应容器宽限。
- 新增严格解析公开字段的compose.sh，统一HTTP/SMTP/模式/test/ops/restore选择；status/backup/restore/upgrade与集成/前端恢复共用组合。已有卷升级先停止全部旧角色，恢复最后覆盖且不加载host SMTP通道，停机门禁检查全部profile。
- 修正实际MQ断线时Room/Payment的Robust channel.ready无限等待，完整唤醒8秒总预算；Notification取消息/建队列和Audit初始化有界。持久扫描、签名/提交后ACK/租约/幂等/unknown语义保留，新增挂起channel回归。
- 新增20项必要单位用例和实际容器/七域合成验收、CI第二步入口；修正前端恢复脚本的0.13.2过时标题定位器，保留原安全/退出断言，生产页面不改。
- 同步0.15.0版本/锁文件/契约元数据、根/前后端/deploy README、AGENTS、总/后端计划/架构/部署/恢复/容量及本机手册。方案第二步勾选，新增验收和两次CLI资源汇总；无AGENT.md。
- 第一小步源码提交3c64651已推送origin/dev；第二步交付在当前dev提交/推送，不创建或合并main PR。
- 交付提交737f406已推送；跟进GitHub Actions确认两个旧head均在Monitoring采集入口超时，定位到旧/重复MQ提示使本轮跳过SQL扫描。修正为处理提示后仍扫描、停止信号后不再领取；追加两项先失败后通过的回归，以及真实基础设施50条旧/重复签名消息的合并采集/取消/接管/重启/退出验收。
- 验证结束只down本轮新建的两个隔离项目，保留六个命名数据卷与受限证据；Docker中无elect项目运行，原业务/历史项目保持停机，其余五个容器仍运行。

### 进行中

- 第二步实现与验证已完成；第三至六步待推进，2核2GB/50人/24小时尚未验收。原业务部署保持停机。

### 阻塞与风险

- 第二步无阻塞。真实D02、生产异机/PITR和T8未完成边界保持；未读取auth.txt/email_auth.txt或访问真实学校/SMTP/支付。
- 首次MQ中断检查因Payment唤醒阻塞失败，健康正确503；修正后重跑通过。前端恢复首次因过时标题失败，更新定位器后通过。本机默认Docker地址池耗尽，仅为新测试项目创建显式未占用小网段，没有改全局配置/清理历史网络。
- 同一隔离项目两次启动后CLI快照：30容器2623.91MiB、13容器1376.16MiB，约减少47.6%；未加载OCR、无持续业务/备份/冷启动峰值、未含宿主机开销，不能作为2GB容量结论。

### 下一步

- 按方案第三步，以8个共享池为基础将2+3验证为2+1（理论40→24条应用连接），先验证控制/API/续租连接等待和峰值，再调整MySQL max_connections/Buffer Pool、Redis/AOF、RabbitMQ定义导入/线程、探针和OCR参数，逐项记录前后与冷启动峰值。

### 主要文件或模块

- backend/services/common/background_roles.py/background.py/business_worker.py/server.py/job.py、identity/recovery.py、room/worker.py/query_worker.py/wakeups.py、notification/job.py/consumer.py、payment/process.py/worker.py/wakeups.py、audit/app.py。
- backend/tests/unit/test_domain_background.py/test_compose_entry.py、scripts/combined_status.py/domain_combined_smoke.py；deploy/compose.low-resource.yaml/compose.sh/upgrade.sh及status/backup/restore/集成、CI和frontend/scripts/t7-stack-browser.mjs。
- docs/acceptance/Docker低资源第二步验收.md/资源.json、低资源方案/生命周期决策及受影响README/计划/运维；版本元数据及两端锁文件。

### 验证

- sh deploy/check.sh通过：前端49项单元组件、32项浏览器、规则/类型/契约和构建；后端单位/契约/目录/离线迁移通过。最后MQ积压修正后本机及实际测试容器ruff、198 passed / 1 skipped、公开/内部契约/数据库目录再次通过；前端验收脚本node语法通过。
- test-stack combined空库/七域权限/并发迁移、实际签名Relay/Audit去重及T2–T6合成回归通过，真实Redis/MySQL/MQ故障通过；13长期容器全部healthy，内部TLS预检通过。
- test-low-resource最终通过：实际七域健康/8条AMQP连接、MQ断线持续扫描/API degraded；restore组合八API无后台、独立入口拒绝；合成监控取消/租约接管/旧epoch/重启/在途退出、Room自动同步/默认Saga、Adapter清理、Notification DATA后unknown及Payment重复受理/未知回查仍一次D01；原卷13→30→13双向upgrade全部healthy，17旧角色全部exited。
- test-t7-recovery通过：MySQL加密快照/封存binlog、隔离恢复、62张表计数和密文保留，快照后合成邮件/订单保持unknown、旧Outbox不重放；本机合成RPO4.631秒/RTO77秒，不外推生产灾备。
- 统一前端恢复入口最终通过：1440/375px四页8次实际生产API读取、账户弹窗、同源/CSRF/对象归属/双标签退出，零浏览器错误，无mock路由，合成学校预置会话。
- 公开standalone/combined/完整restore配置、逐文件Shell语法、版本/锁文件、真实凭据忽略、244个受影响Markdown本地链接及git diff --check通过；实际前端脚本额外lint通过。测试清理已完成，六个数据卷保留，所有elect运行容器为0，其余五个容器状态保持。

## 2026-10-03 · Docker低资源优化第一步（0.14.0）

### 已完成

- 按用户要求开始优化方案，完成第一步公共后台生命周期和Monitoring试点：API/Relay/Scheduler/Worker/恢复/提醒回报共用本域engine、ServiceClient与一条AMQP连接，发布和两个消费者使用独立channel，保留confirm/ACK、持久租约及原代次屏障。
- 抽取可监督的异步角色，保留独立入口；心跳改为角色独立文件并在启动清零。API健康返回各角色状态，意外结束/异常/取消/停滞可见；Uvicorn统一信号先停止领取，再按100秒总预算等待或取消在途任务，最后释放资源。新增重复启动拒绝。
- 新增Monitoring试点覆盖，五个旧角色默认禁用且即使手动指定也拒绝独立启动，基础长期容器30→25、Python进程26→21。后台开关接入公开模板和基础编排；恢复覆盖强制false，API和所有独立入口均禁止自动后台。
- 新增生命周期单位用例、实际MySQL/Redis/MQ合成验收脚本及CI阶段。修正T4旧夹具的默认寝室假设：通过正式默认接口显式选择合成001并等待终态，生产0.13.1的学校顺序规则保留。
- 同步0.14.0版本/锁文件/公开契约元数据、根及前后端/deploy README、AGENTS、架构/实施/部署/运维说明、方案第一步完成状态与验收。无AGENT.md；业务接口字段、数据库迁移、真实副作用授权不变。
- 测试完成后仅down本轮新建的两个隔离项目，保留测试卷和受限证据；原elect-local及历史业务/测试环境保持停机，其他五个运行容器保留。

### 进行中

- 第一批实现与验证已完成；低资源方案第二至六步待推进，尚未交付13容器正式轻量组合。

### 阻塞与风险

- 第一批无阻塞。2核2GB/50人/24小时、OCR/冷启动/备份峰值尚未验收，不把进程数变化或本机合成RPO/RTO称为目标容量或生产灾备通过。
- 首次测试因宿主机默认Docker地址池耗尽失败，仅为新测试项目创建显式未占用网段后继续；没有删除历史网络或改动Docker全局配置。T4夹具首次失败已修正并复验。
- 真实D02终态映射、生产异机/PITR与T8仍未完成；未读取auth.txt/email_auth.txt或访问真实学校/SMTP/支付。

### 下一步

- 按方案第二步先将Identity/Room/School Adapter推广到共享生命周期，再合并Notification API/Relay/恢复、Payment和Audit；保持邮件发送Worker独立，形成13个长期容器的正式轻量组合，并统一升级/状态/备份/恢复配置与角色启停。完成共享池后再进入第三步重算连接数和基础服务参数。

### 主要文件或模块

- backend/services/common/background.py、app.py、broker.py、heartbeat.py、job.py、server.py及独立入口；services/monitoring/job.py、worker.py、alert_recovery.py。
- backend/tests/unit/test_background_lifecycle.py、scripts/monitoring_combined_smoke.py、room_test_setup.py、t4_monitor_smoke.py；deploy/compose.monitoring-combined.yaml、compose.yaml/compose.restore.yaml、test-monitoring-combined.sh、公开env与CI。
- docs/Docker低资源部署优化方案.md、decisions/Docker低资源后台生命周期.md、acceptance/Docker低资源第一步验收.md及受影响导航/架构/部署/运维文档；版本元数据与锁文件。

### 验证

- sh deploy/check.sh通过：后端ruff、176 passed / 1 skipped、公开/内部契约、数据库目录与七域离线迁移；前端规则/类型/契约、49项单元组件、32项浏览器及构建通过。最后重复启动保护后后端176项再验通过，源码最终镜像实际构建通过。
- 独立test-stack空库/权限/事件和T2–T6各阶段复验通过；T4首次夹具失败后修正复验并继续其余阶段，实际Redis/MySQL/MQ中断、未知SMTP/支付边界、取消/切换/凭据与消息去重均通过。最新镜像在原测试卷重建独立模式，30个长期服务全部healthy，迁移与内部TLS预检正常。
- sh deploy/test-monitoring-combined.sh最终通过：真实容器API/五角色健康、共享MQ断线后四角色继续数据库扫描/API degraded、恢复组合API可运行但无后台；合成学校验证调度单样本、在途取消、角色故障可见、恢复接管/旧epoch拒绝、停止领取后在途提交、统一退出与连接释放。
- sh deploy/test-t7-recovery.sh通过：加密快照/封存binlog、隔离空库导入、62张表计数和密文保留、快照后模拟写/邮件保持unknown、旧Outbox不自动重放；本机合成RPO 4.577秒、RTO 65秒，不能外推生产频率/异机/PITR。
- 公开基础/试点/恢复Compose解析通过：默认30个、试点25个长期服务，五个旧Monitoring角色不在默认profile；统一后台false传入26个API/独立角色，恢复组合八个API保持false。
- 15份受影响文档210个本地链接、末尾换行、版本/锁文件、脚本语法、真实凭据忽略及git diff --check通过。最终Docker仅原有五个非elect容器运行，原业务部署未启动；未进行2GB容量验收。

## 2026-10-03 · 记录50人、2核2GB的Docker优化方案

### 已完成

- 按用户先只读审查、后写入文档的要求，新增Docker低资源部署优化方案，覆盖历史基线、16项优化、26个Python进程向9个收敛、13个基础长期容器目标、连接与内存预算、实施顺序和目标机验收。
- 区分0.13.1历史35秒资源样本、0.13.2当前代码配置和未实施预算；2核2GB/50人尚未通过容量验收，未将30ms模拟吞吐外推为真实学校容量。
- 同步根README与docs/deploy文档入口、Docker部署说明和运行状态交叉引用；修正deploy README开头仍为22个长期服务的过时数量，当前基础编排为30个。
- 已检查AGENTS、前后端README及AGENT.md适用性：无AGENT.md，开发规范与应用使用方式未变化，无需修改AGENTS或前后端README。应用版本、源码、Compose、Secret及业务停机状态不变。

### 进行中

- 本次方案文档交付已完成；尚未开始优化实现、轻量编排、镜像发布或目标机验收。

### 阻塞与风险

- 本次文档交付无阻塞。历史运行约2.74GiB，现有编排不能直接视为满足2GB；进程合并须同时解决固定心跳路径、统一退出和恢复模式后台禁用，不能仅下调容器限额。
- 真实学校50人频率、2核2GB长期容量及原有D02/PITR/T8未验范围仍未确认；本轮不恢复部署或执行学校、支付、SMTP操作。

### 下一步

- 后续进入优化实施时，先抽取同域角色运行接口和共享上下文，为Monitoring实现独立角色心跳、统一退出及后台禁用模式，并验证取消/租约/恢复隔离，再推广至13容器编排。

### 主要文件或模块

- docs/Docker低资源部署优化方案.md、docs/README.md、docs/Docker部署配置说明.md、docs/runbooks/运行状态与容量.md。
- README.md、deploy/README.md、PROJECT_PROGRESS.md。

### 验证

- 前序只读审查已用公开.env.example解析基础Compose，确认32个配置服务、30个长期服务、7680MiB长期服务内存限额合计；26个Python进程、25个持库进程及125条理论应用连接与源码/运行文档一致。
- 本轮7份Markdown中的115个本地链接有效；16项优化、6个未完成实施步骤、容器/连接/内存预算和频率计算检查通过，公开Compose解析复核通过。
- Git差异、末尾换行及git diff --check通过；Docker查询确认本项目无运行容器。未执行启动、构建或业务测试，未进行2核2GB容量验收。

## 2026-10-03 · 按 example 重写正式前端（0.13.2）

### 已完成

- 按用户要求，以example/nature.html浅蓝主题重写侧栏/手机顶部导航、双栏登录、总览卡片、明细与日历、绑定弹窗和监控双列表单；组件与样式独立于example。
- 按追加要求删去装饰介绍、重复说明和常驻技术文案；运行详情默认折叠，错误/未知/过期状态、授权、操作结果与独立关闭监控仍可见。发生监控设置冲突时自动展开已保存值供核对。
- 修复手机明细缴费按钮换行导致的余额卡过高；校正日历字重、手机提示字号，补齐空绑定与键盘/布局检查，保存同视口全页和局部并排证据。
- 同步0.13.2版本、根/前后端README、AGENTS、前端计划/开发文档及验收；后端仅更新版本元数据，API字段及数据库未改动。

### 进行中

- 本次界面重写与最终验证已完成，无进行中的界面实现任务；原业务Docker部署继续停机。

### 阻塞与风险

- 本次无实施阻塞。未恢复真实部署，未访问学校或执行绑定、支付、SMTP；截图全部使用合成数据。Firefox/Safari、屏幕阅读器与真实后端联调不在本轮范围。

### 下一步

- 保持原Docker业务停机；用户要求恢复部署时，使用原.env.local与三份编排校验配置，将前端镜像更新至0.13.2并核对入口/服务健康。

### 主要文件或模块

- frontend/src/components、features、styles、tests；docs/acceptance/frontend/0.13.2界面还原.md、design-qa.md与ui-rewrite截图；版本元数据与受影响README/规范。

### 验证

- sh deploy/check.sh通过：后端ruff、166 passed / 1 skipped、公开/内部协议和表目录检查、七域离线迁移；前端规则/类型/契约、49项单元组件、32项浏览器及构建通过。
- 最后手机样式修正后，在无网络Docker中重新完整复验前端49项单元组件、32项浏览器、规则/类型/契约及构建；elect-frontend:v0.13.2生产镜像构建通过。
- 最终本机Chromium视觉场景3项通过，1440/375px共16张页面/弹窗截图与参考并排检查通过；跨月日历、未来日期、366天限制、设置冲突核对、空绑定、未知支付恢复、双标签退出和图表资源释放通过。
- 初次收尾回归发现旧支付文案断言、空绑定夹具缺少meta.request_id，修正后复验通过。原测试断言的业务范围保留。

## 2026-10-03 · 重写项目README与明确文档职责

### 已完成

- 按用户要求重写根README，面向使用者与初次接触项目的开发者介绍功能、技术栈、Docker部署、本地开发、独立界面演示、目录和文档入口。
- 移除README中的阶段流水、个人联调/付款细节、临时停机记录和逐项验收链接；相关证据仍由既有进度、验收及运行文档维护，功能范围保留默认开关与支付未开放说明。
- 在AGENTS明确README职责和维护方式，进度、日期操作记录与临时部署状态写入进度或对应专项文档；本次无代码、接口、版本或部署配置变更。

### 进行中

- 本次文档重写与职责规范已完成；Docker部署保持停机。

### 阻塞与风险

- 本次无阻塞。支付功能仍未对外开放，本次文档整理不改变既有功能与验收边界。

### 下一步

- 保持Docker停机状态；用户要求恢复部署时，先使用原.env.local与三份编排校验配置，再启动并核对服务健康，停机/恢复过程仅记录在专项文档。

### 主要文件或模块

- README.md、AGENTS.md、PROJECT_PROGRESS.md。

### 验证

- README的13个本地文档链接全部有效，项目版本与前后端配置/锁文件一致，Node/npm/Python运行环境及依赖锁、启动入口检查通过。
- 四段Shell示例经bash -n语法检查通过，Docker部署命令与现有部署说明逐行一致；未执行启动命令，未启动容器或新增业务测试。
- README已无阶段流水、日期记录和本机地址；审查Git差异、文档分工、末尾换行及git diff --check通过。已检查子目录README与文档索引，无需因根README整理修改其入口，无AGENT.md。

## 2026-10-03 · 停止当前Docker部署

### 已完成

- 按用户要求确认当前部署为elect-local，使用原.env.local、compose.yaml/compose.local.yaml/compose.smtp-direct.yaml和项目名正常停止全部31个长期服务。
- 保留32个容器（含已完成的migrate）及MySQL、Redis、RabbitMQ三个原数据卷；历史测试/恢复环境继续停止，所有elect项目运行容器数为0。
- 同步README与运行状态文档，明确当前网页入口和SMTP定向通道已关闭。此次仅记录运维状态，版本、业务规则、Secret与部署配置无变化；已检查AGENTS及前后端/deploy README，无需同步修改，无AGENT.md。

### 进行中

- 本次停机已完成；elect-local与本项目历史测试/恢复环境保持停止，等待用户安排下一项任务。

### 阻塞与风险

- 本次无阻塞。停机期间网页、后台采集和邮件处理不可用；配置、待处理任务及订单台账保留，停机不改变持久业务状态。

### 下一步

- 保持当前停机状态；用户要求恢复部署时，先对原env与三份编排执行config --quiet，再显式up --wait并核对31个长期服务及/healthz。

### 主要文件或模块

- Docker项目elect-local；README.md、PROJECT_PROGRESS.md、docs/runbooks/运行状态与容量.md。

### 验证

- `docker compose ... -p elect-local stop --timeout 30`返回码0；`docker ps -a`确认32个保留容器全部exited，`docker ps`确认所有elect项目运行数0。
- 停机前后数据卷名称逐项一致，三个原卷全部保留；其他五个运行中的非本项目容器ID逐项一致。
- `ss`确认6874/16874均无TCP监听；原入口/healthz连接失败，curl返回码7、HTTP 000，符合停机状态。

## 2026-10-02 · 部署资源检查与停止全部测试容器

### 已完成

- 按用户要求检查已部署elect-local v0.13.1的CPU、内存、网络、块设备I/O、容器限额、重启/OOM、数据卷、日志和宿主机磁盘。
- 根据用户追加指令，显式停止全部30个运行中的elect-test-t6测试容器；保留容器、三个数据卷和原真实验收/订单记录。结束时所有elect测试容器均未运行，elect-local的31个容器仍全部healthy，其他项目运行状态保留。
- 停止前后分别进行35秒cgroup采样：测试环境原平均占用2.59 GiB内存和整机13.11% CPU；停止后elect-local平均2.74 GiB、整机13.39% CPU（6核口径），整机平均CPU由34.25%降至18.89%，期末可用内存由5.23 GiB增至8.04 GiB。
- 将测量口径、采样时段、主要组件、磁盘内容和停止状态同步至运行状态与容量文档；此次为运维状态记录，未修改应用版本或业务规则。提交前检查README、AGENTS及子目录README，项目总览、架构、启动入口与开发规范无变化，无AGENT.md。

### 进行中

- 本次资源检查和测试容器停机已完成；真实D02自动终态、生产异机/PITR与T8发布继续按既有计划保留未验状态。

### 阻塞与风险

- 本次无阻塞。当前部署无容器重启、OOM kill或容器Swap占用，宿主机磁盘仍有约100 GiB余量。
- 35秒短时采样不能替代并发压测或全天容量评估；保留的测试卷/历史镜像仍占磁盘，停止测试容器没有删除验收证据，也未进行学校、支付或邮件外发测试。

### 下一步

- T8发布容量评估时，在独立目标机采集elect-local的24小时CPU/内存峰值及MySQL/binlog日增量，形成上线资源预算；当前测试环境保持停止，后续有验收需要时再显式启动。

### 主要文件或模块

- Docker项目elect-local/elect-test-t6；PROJECT_PROGRESS.md、docs/runbooks/运行状态与容量.md。

### 验证

- `docker stop --time 30`成功停止30个指定测试容器，返回码0；`docker ps`与Compose项目列表确认测试运行数0，elect-local运行数31/健康数31/重启计数0。
- `docker volume ls`确认elect-test-t6的MySQL、Redis、RabbitMQ三个原数据卷保留；入口与healthz均HTTP 200。
- cgroup v2停止前14:43:41–14:44:16及停止后14:46:51–14:47:26（Asia/Shanghai）采样完成；本机free/proc、df、Docker镜像/缓存、数据卷和日志用量检查完成，结果见运行文档。
- 用户询问口径后，原生`docker stats --no-stream`复核31个当前容器合计2.73 GiB；26个独立Python业务容器在35秒样本中平均合计2.01 GiB，memory.stat快照匿名驻留内存约2.67 GiB，主要开销为多进程常驻内存。文档分别记录平均值与快照值，扣除inactive_file，不把限额/测试/镜像磁盘量当作内存占用。
- 采样数值与文档各自记录精度、末尾换行、测试卷保留及`git diff --check`检查通过；仅更新两份相关运行记录文档，无业务代码改动。

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
