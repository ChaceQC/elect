# Docker 全栈部署与域名证书配置

版本：1.1；编写日期：2026-10-01；状态：T1 基础已实现并通过独立验收。

本文统一[后端架构](后端架构详细设计.md)、[后端实施计划](后端实施计划.md)和[前端实施计划](前端实施计划.md)中的部署方式。T0 已建立 [公开变量模板](../deploy/.env.example)、[Secret/账号清单](../deploy/secrets.example.yaml)与七域迁移；T1 已建立两端镜像、Compose、Secret 生成、空卷 provisioning、持锁迁移、TLS 预检和公共运行设施，并通过独立容器基础验收。前端公共数据层及 Docker CI 也已实现；学校业务不在本阶段开放。

## T3 控制基础升级

T3 启用 Monitoring 配置/屏障/发送许可和 Identity 持久撤回，当前 head 为 `identity_0003`、`school_0005`、`room_0004`、`monitoring_0003`。`monitoring_encryption_key_bundle` 是独立 AES-256-GCM 多版本邮箱密钥，只挂载 Monitoring API，不与学校 KEK 共用。首次 provision 自动生成；已有 T2/第一批 T3 Secret 目录必须保留，按以下顺序重复升级：

```sh
docker build -t elect-backend:local backend
docker run --rm --network none --user 0:0 \
  -v /opt/elect/secrets:/run/upgrade elect-backend:local \
  python -m services.deployment.upgrade_controls --directory /run/upgrade
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml build
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm migrate
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --force-recreate
```

将 `/opt/elect/secrets` 替换为实际受限目录；离线升级不输出 Secret，重复运行保留邮箱密钥、连接凭据及既有签名私钥，增加所需服务 scope 与 credential.revoked 的 MQ 写权限。数据库须已运行，迁移完成后再启动新 API；健康检查核对各域当前 head。MQ 与应用服务须重建以加载新权限。备份需包含新邮箱密钥及历史版本。升级前备份流程仍按本文对应章节执行。

`school:binding` 仅授 Room，用于候选核验/一次绑定/已登记操作回查；`monitor:browser` 仅授 Gateway，`monitor:retarget` 授 Room，`monitor:credential`/`credential:revoke` 授 Identity；`credential:control-read` 授 Identity/Monitoring，`monitor:credential-read` 授 Adapter，`monitor:authorize-send` 授 Notification，`room:control` 授 Monitoring。内部控制事务只使用本域 MySQL；沿用 Identity 恢复器，没有新增采集/邮件 Worker，22 个长期服务数量不变。独立验收入口包含 T3 控制与凭据/许可竞态脚本，真实绑定/邮件/支付开关仍关闭。

## 1. 整套部署方式

目标机器只需要 Docker Engine/Compose 和可用的磁盘、网络、域名/证书文件。依赖安装、前端编译、数据库初始化及运行均在容器中完成。

| 组件 | 构建/运行方式 |
| --- | --- |
| 前端 | frontend/Dockerfile：Node 阶段执行 npm ci/build；Nginx 阶段复制 dist 静态文件 |
| Python 后端 | backend/Dockerfile：根据 pyproject.toml/uv.lock 安装依赖，工作目录 /app，模块为 services.* |
| API 与后台进程 | Gateway、Identity、Room、Monitoring、Adapter、Payment、Notification、Audit、Scheduler、各域 Worker/Relay/恢复器使用后端镜像 |
| 数据与消息 | MySQL 8.4、Redis、RabbitMQ 由 Compose 启动，配置健康检查、账号与持久卷 |
| migrate | 后端镜像的一次性建表/表结构升级作业，数据库健康后持锁执行 |
| tls-check | 后端镜像的一次性证书检查，无网络，仅读取配置域名、证书链与私钥 |
| 公网入口 | Nginx 容器发布 80/443，提供 HTTPS、静态页面和 `/api/` 反代 |

Compose 文件为 deploy/compose.yaml。前后端的 build.context 分别是相对该文件的 `../frontend`、`../backend`，各自 Dockerfile 名称为 Dockerfile。example 与 docs 不作为生产构建上下文；OpenAPI 生成的前端类型提前提交在 frontend 内。

## 2. 域名与证书配置

在 deploy/.env 中提供以下公开配置。示例域名与路径需替换为实际值，证书内容不放进 .env：

```dotenv
ELECT_DOMAIN=elect.example.edu
ELECT_TLS_CERT_FILE=/opt/elect/secrets/tls/fullchain.pem
ELECT_TLS_KEY_FILE=/opt/elect/secrets/tls/privkey.pem
ELECT_SECRETS_DIR=/opt/elect/secrets
```

| 变量 | 规则 |
| --- | --- |
| ELECT_DOMAIN | 单个站点 DNS 名称，不含协议、端口或路径；Nginx server_name 和跳转域名使用该值 |
| ELECT_TLS_CERT_FILE | 宿主机 PEM 证书链文件绝对路径，叶子证书在前，包含所需中间证书 |
| ELECT_TLS_KEY_FILE | 配套 PEM 私钥文件绝对路径；一期使用可非交互读取的无口令私钥，由文件权限保护 |
| ELECT_SECRETS_DIR | 其他数据库、服务认证、学校密钥等 Secret 文件所在的受限目录 |

deploy/.env.example 已列出 ELECT_IMAGE、ELECT_WEB_IMAGE、MYSQL_IMAGE、REDIS_IMAGE、RABBITMQ_IMAGE 等镜像变量；版本和基础镜像摘要由实施阶段验证后固定。ELECT_IMAGE/ELECT_WEB_IMAGE 是 Compose 构建后端/前端时使用的镜像名称。

域名 DNS 应指向部署入口，证书 SAN 应覆盖域名，证书在有效期内，私钥与证书公钥必须匹配。证书文件通过 Docker Secret 只读挂载，私钥限制文件读取权限。

后端可信来源由 Compose 从同一域名生成：

```yaml
environment:
  ELECT_PUBLIC_ORIGIN: https://${ELECT_DOMAIN:?set-domain}
```

Gateway/Identity 的 Origin/CSRF 检查、可信跳转和 Notification 的站内链接采用该值。前端使用同源相对 `/api/v1`，浏览器 JS 不写死域名；更换域名或证书无需重新编译前端。

## 3. Nginx 模板与证书挂载

模板为 deploy/nginx/default.conf.template，挂到 `/etc/nginx/templates/default.conf.template`。frontend/Dockerfile 的 Nginx 运行阶段保留官方 entrypoint，在启动时渲染到 `/etc/nginx/conf.d/default.conf`。

关键 Compose 配置如下；完整的卷、权限、健康依赖与资源限制见 [compose.yaml](../deploy/compose.yaml)：

```yaml
services:
  nginx:
    image: ${ELECT_WEB_IMAGE:?set-reviewed-web-image}
    build: {context: ../frontend, dockerfile: Dockerfile}
    ports: ["80:80", "443:443"]
    networks: [edge, app]
    environment:
      ELECT_DOMAIN: ${ELECT_DOMAIN:?set-domain}
      NGINX_ENVSUBST_FILTER: "^ELECT_DOMAIN$$"
    volumes:
      - ./nginx/default.conf.template:/etc/nginx/templates/default.conf.template:ro
    secrets: [tls_cert, tls_key]
    depends_on:
      gateway: {condition: service_healthy}
      tls-check: {condition: service_completed_successfully}

secrets:
  tls_cert: {file: "${ELECT_TLS_CERT_FILE:?set-fullchain-pem-path}"}
  tls_key: {file: "${ELECT_TLS_KEY_FILE:?set-private-key-pem-path}"}
```

Compose 的 `$$` 使容器得到过滤表达式 `^ELECT_DOMAIN$`。模板只替换 ELECT_DOMAIN，保留 `$uri/$host/$gateway/$request_id` 等 Nginx 运行时变量。

80 端口返回配置域名的 HTTPS 308 跳转，443 从 `/run/secrets/tls_cert`、`/run/secrets/tls_key` 读取证书。正式入口是 index.html，SPA 回退 `/index.html`；完整反代模板见架构设计第 13.4 节。

tls-check 的入口为 backend/services/deployment/check_tls.py，在无网络、只读文件系统的容器中检查域名格式、有效期、SAN 和公私钥配对，不初始化业务服务，不输出私钥/证书正文。失败时阻止 Nginx 启动；Nginx 本身继续校验配置语法及证书可加载性。

## 4. 首次部署

先复制 `deploy/.env.example` 为 `deploy/.env` 并配置域名、证书与受限 Secret 目录。完整首次生成流程只依赖 Docker：

```sh
docker build -t elect-backend:v0.2.0 backend
# 先创建目标空目录；生成器拒绝覆盖已有 Secret。
mkdir -p /opt/elect/secrets
chmod 700 /opt/elect/secrets
docker run --rm --network none --user 0:0 \
  -v /opt/elect/secrets:/run/provision \
  elect-backend:v0.2.0 python -m services.deployment.provision --output-dir /run/provision
```

生成器创建随机数据库/缓存/消息账号、每服务独立 Ed25519 私钥、公钥 trust bundle 和 runtime JSON，文件按接收容器 UID 设为 0400，目录 0700。MySQL 首次初始化从 SQL Secret 先创建 probe/七域库/app/ddl；已有卷不重复 provisioning，不可重新生成随机账号替换原 Secret。学校 KEK/SMTP 等后续业务密钥按阶段补齐。

正式证书由管理员放到配置路径；生成器默认不生成 TLS。仅独立验收可显式使用 `--test-tls-domain elect.test.local` 生成两天自签证书，不能将其描述为受信任公网证书。Compose 要求 2.24.4 或更新版本（测试端口覆盖使用 `!override`）。

随后从仓库根执行：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --build
docker compose --env-file deploy/.env -f deploy/compose.yaml ps -a
```

config --quiet 校验配置引用；up --build 构建 frontend/backend 镜像，启动基础服务，等待数据库健康、migrate 和 tls-check 完成，再按依赖启动应用。一次性作业成功退出属于正常完成，不能将它们要求为长期 running。

当前默认运行八个 API 骨架、六个本域 Relay 和 Audit Worker；监控 Scheduler/Worker/业务恢复器、支付 Worker、邮件 Worker 随 T3–T6 实现后加入，不启动空循环冒充业务健康。MQ/Redis 故障在领域 API readiness 显示 degraded（HTTP 200），MySQL/结构异常返回 503；后台健康反映实际扫描/领取/持久提交心跳。

随后验证域名的 HTTPS 跳转、证书链、SPA 直达路由、同源登录 Cookie/CSRF 和 API，并检查后台进程心跳。验收机器不预装 Node/npm、Python/uv、MySQL、Redis、RabbitMQ 或 Nginx，也不预先生成宿主机 dist。

## 5. 更换证书或域名

### 5.1 更换证书

将新证书链和私钥放到受限目录，可采用带版本的新文件名；更新 deploy/.env 的文件路径。只有 TLS 和临时 Nginx 检查都通过后，才替换正在服务的入口：

```sh
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps tls-check
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps nginx nginx -t
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --no-deps --force-recreate nginx
```

临时 nginx run 不发布宿主机端口。文件挂载可能仍引用被替换前的 inode，因此默认重建 Nginx 容器，重新挂载文件并渲染模板，确保读取新证书。随后核对实际入口提供的证书，无需重建前端镜像或数据库；记录单机入口重建的短暂中断时间。

一期支持配置已有证书文件。若后续采用自动签发/续期，将 ACME 工具作为 Compose 服务纳入实施，并在续期成功后执行相同预检/重载流程；当前计划不依赖自动签发服务。

### 5.2 更换域名

更新 ELECT_DOMAIN，准备覆盖新域名的证书及 DNS。先执行 TLS/Nginx 预检，再执行完整 `docker compose --env-file deploy/.env -f deploy/compose.yaml up -d`，使 Nginx 和使用 ELECT_PUBLIC_ORIGIN 的后端同步应用配置。新域名下验证登录、CSRF、站内链接和二维码；用户在新域名重新建立应用会话。

## 6. 验收条件

- 全栈在仅安装 Docker Engine/Compose 的目标机完成构建与首次启动。
- 更换指定域名后，页面、API、HTTPS 跳转和可信 Origin 一致，无需修改前端源码。
- 指定路径能加载证书/私钥；错误路径、SAN 不符、过期或配对错误在预检中被拒绝。
- 模板保留 Nginx 自身变量，密钥不进入镜像、日志或浏览器产物。
- 证书替换后入口提供新证书，数据库状态与后台监控配置保留。
- 命名卷、Secret、备份、镜像升级和回滚均有 docs 下的运维记录。

## 7. 独立容器检查

```sh
sh deploy/check.sh
sh deploy/test-stack.sh /absolute/new-test-directory elect-test-local
```

check 在容器中执行后端单元/契约/迁移 SQL、前端规则/类型/单元/构建和 Playwright；test-stack 创建明确命名的新项目，容器生成 Secret/临时自签证书，空库启动并执行可靠事件 smoke。测试端口绑定本机 18080/18443，须空闲；默认 `.env` 仍仅由 Nginx 发布 80/443。测试作业拒绝未声明一次性环境和已有输出目录。

CI 位于 `.github/workflows/check.yaml`，对所有分支 push 和目标为 `main` 的 PR 执行，不依赖宿主机语言环境、真实学校或 SMTP。当前开发分支直接提交推送，无需 PR；同一 PR 新提交会取消旧运行。完整作业 `check` 是 `main` 的严格必需检查，仅合并到 `main` 时必须通过 PR，并确保最新提交的 Actions 全部成功，见 [GitHub 协作与合并流程](GitHub协作与合并流程.md)。操作完可用相同 env/Compose/项目名执行 `down` 停止本次环境，保留命名卷。真实恢复、备份、公网域名/受信任证书和业务容器联调留待 T7/T8。

T4 依赖故障脚本的 `t4-fault` 共享目录保留宿主机用户属主，组设为容器的 GID 10001、权限为 0770；容器可写状态，普通 Runner 可写 `hold.log` 并检查就绪文件，其他用户无权限。不能将整个目录改为容器 UID 的 0700，否则普通 Runner 会报 `Permission denied`，而 root 本地运行会掩盖错误。正式 Secret 的属主、0700 目录与0400文件规则不受影响。

## T2 认证升级

T2 新增 identity-recovery、room-sync-worker、school-maintenance，长期进程从 19 个增加到 22 个。Identity/Adapter API 使用内部 TLS，只挂载本人服务器私钥；Gateway/Room/Identity 以内部 CA 验证服务器。仅 Adapter 新增 school_egress 外部网络，内存上限 1024 MiB 支持延迟 OCR。KEK、独立 lookup HMAC 与会话 pepper 分域挂载，内部 CA 私钥仅离线保管。服务器证书 90 天、CA 365 天，到期前须更换。

全新部署使用新版 provision 生成全部 Secret。已有 T1 数据卷升级时，停应用并备份现有 Secret，然后在无网络的一次性 root 容器执行 python -m services.deployment.upgrade_auth --directory /run/provision（只读镜像、显式挂载现有 Secret 目录为 /run/provision）。升级保留原 db_url/MQ/Redis 密码、服务签名私钥与已有认证密钥，补充缺失认证文件和命令/消息权限；部分认证文件缺失会拒绝混用。随后用原 env/项目名重建 Redis/RabbitMQ 使 ACL/definitions 生效，执行一次 migrate 作业升级三个领域 head，再启动新版应用。不能重新生成数据库连接 Secret 或删除旧卷。

T2 新增应用恢复字段、学校账号占位/授权与 Room 同步租约/状态表；运行事务采用 READ COMMITTED。认证与读取实现及真实边界见 [T2 决策](decisions/T2认证与读取.md)。四项副作用开关仍默认关闭。

## T3 绑定与默认增量

Room 既有 Worker 同时扫描同步、默认和绑定，无新增进程。已有第二批 T3 部署重复执行上述 upgrade_controls 后迁移 room_0003/school_0004，再重建服务加载新 scope；不能回改已发布迁移或删除未知台账。deploy/test-stack.sh 增加默认 Saga 与绑定一次 dispatch/unknown/Outbox 故障验证，均使用隔离基础服务和合成学校。真实新增仅在明确指定目标的验收项目临时开启 ELECT_ALLOW_SCHOOL_BINDING_WRITES，验收后关闭，支付/SMTP 始终保持 false。

## T3 删除增量升级

保留原 Secret 和卷，重复 upgrade_controls 增加 Room 的凭据证明读取、Adapter 的 Room 租约/默认屏障读取；迁移 room_0004/school_0005 后重建 Gateway/Room/Adapter/Monitoring 及 Room Worker，读取新 head 与 scope。学校删除仍受 ELECT_ALLOW_SCHOOL_BINDING_WRITES 控制，普通值 false；指定验收临时 true，完成后重建 Room/Adapter 恢复 false。脚本 t3_removal_smoke 只在显式隔离环境运行，并在恢复真实 Worker 前终结合成待执行任务。

## T4 采集引擎升级

新增三个独立监控进程，长期进程增至25个；monitoring_0004保存采集时的间隔。保留原Secret与卷，重复upgrade_controls后重建RabbitMQ和全部相关应用以加载新文件挂载/权限，运行migrate，再启动新Scheduler/Worker/恢复器。不要重新provision已有Secret。

monitor.run_ready和room.history_sync_requested为持久签名唤醒；任务以MySQL为准，MQ失效时仍扫描。采集Worker每10秒续租，最长90秒，退出宽限100秒；Room/Identity长请求期间验证数据库并更新心跳。仅balance_only，SMTP/支付开关仍默认false。

`test-stack.sh`合成阶段暂停Identity/Room与监控三个进程、Monitoring Relay，运行t4_query_smoke/t4_monitor_smoke；合成监控全部关闭后再恢复。新验收见 [T4采集引擎](acceptance/T4采集引擎验收记录.md)。

## T5邮件部署增量

新增monitor-alerts（提醒唤醒重建/结果消费）、notification-worker（Inbox/job/发送）、notification-recovery（正文边界后的租约恢复）；长期进程共28个。Notification独立邮箱密钥与smtp_credentials JSON Secret，仅发送Worker追加notification_egress。已有部署重复upgrade_controls后迁移monitoring_0005/notification_0002，再重建RabbitMQ和受影响应用；Secret原子替换后旧挂载不会自动更新。SMTP默认false，公开模板不含真实配置；proxy_url可选择显式HTTP CONNECT代理且SMTP TLS保持验证。测试环境真实收件已确认，生产网络/全旅程/恢复演练仍属T7。见 [邮件运行说明](runbooks/邮件投递与代理排查.md)。
