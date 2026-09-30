# 项目进度

日期按 `Asia/Shanghai` 记录；完成、验证、阻塞与下一步随任务更新。

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
