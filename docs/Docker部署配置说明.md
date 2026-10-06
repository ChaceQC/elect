# Docker 全栈部署与域名证书配置

0.19.1部署须由统一upgrade执行`monitoring_0006`、`room_0005`后再启动应用。原Secret不变；Monitoring recovery承担每60秒的小批快照清理，关闭后台时不清理，存量配额仍限制新写入。只清理到期快照成员/父行，不清理原始采集、学校历史、订单或operation。见[查询资源规则](decisions/查询资源受理与快照清理.md)。

0.19.0新增`ELECT_DEPLOYMENT_MODE=core`，统一入口在low-resource后加入core覆盖，7个常驻容器、3个Python进程；combined保留13容器回退。核心使用原Identity内部TLS证书与`identity`网络别名，Nginx与外部Worker校验证书；各域签名身份不变。restore额外最后覆盖core/mail-worker，关闭所有后台和副作用。见[七容器方案](decisions/七容器核心组合.md)。

版本：1.2；更新日期：2026-10-04；状态：T1 基础已实现并通过独立验收。

本文统一[后端架构](后端架构详细设计.md)、[后端实施计划](后端实施计划.md)和[前端实施计划](前端实施计划.md)中的部署方式。T0 已建立 [公开变量模板](../deploy/.env.example)、[Secret/账号清单](../deploy/secrets.example.yaml)与七域迁移；T1 已建立两端镜像、Compose、Secret 生成、空卷 provisioning、持锁迁移、TLS 预检和公共运行设施，并通过独立容器基础验收。前端公共数据层及 Docker CI 也已实现；学校业务不在本阶段开放。

面向50人、2核2GB的改造见[Docker低资源部署优化方案](Docker低资源部署优化方案.md)。0.15.0提供七域合并的13容器轻量组合，使用方式与恢复禁用见[生命周期决策](decisions/Docker低资源后台生命周期.md)。默认仍保留独立角色模式，0.16.0增加第三步资源参数，值与兼容升级见[资源决策](decisions/Docker低资源资源参数.md)；2GB容量尚未验收。

0.17.0第四步接通成功提交后Outbox提示、空闲退避、有界basic.consume及两个监控执行槽，邮件发送仍单槽；无新增迁移、密钥或公共API字段。补齐既有room.binding_confirmed的MQ最小权限/路由/Inbox消费；已有Secret须在停应用后重复离线upgrade_controls，再重建RabbitMQ加载定义，详见[执行效率决策](decisions/Docker低资源执行效率.md)。原模式切换与恢复隔离入口继续适用。

## 固定镜像交付（0.18.0）

CI将前后端检查/构建和三组容器验证拆到独立运行器；每组各自创建Secret、数据库卷和网络，跨组只传带提交/版本/镜像ID/SHA-256的镜像包。环境准备可按依赖分组启动，无源码和原卷切换仍调用真实start/upgrade逐容器入口。标签发布依赖严格check，只加载本次受测runtime，恢复演练不重建ops。非main分支push仅快速检查且不导出镜像；2026-10-06追加纯Markdown push不触发CI，含代码/配置/契约JSON或YAML仍检查。main PR/版本标签和默认手动运行完整，手动分支可选quick。详见[CI并行验证](decisions/CI并行验证.md)。main push不触发CI，PR合并后不重复运行。

目标机使用开发版发布的摘要镜像和仅deploy包，不执行构建；首次/原卷升级用start.sh/upgrade.sh逐个等待基础服务、迁移、领域、后台和入口。发布与元数据/入口预检、私有registry登录及失败边界见[固定镜像手册](runbooks/固定镜像发布与启动.md)。第五步页面刷新/数据清理和2核2GB/50人24小时仍未完成。

基础compose.yaml不再含build，开发机的ELECT_IMAGE_MODE=local通过compose.sh加载compose.build.yaml。下面源码构建命令只供开发机/历史升级参考；目标机以固定镜像手册为准。

## 轻量组合与统一入口

在公开env中设置`ELECT_DEPLOYMENT_MODE=combined`后，`deploy/compose.sh`自动加入`compose.low-resource.yaml`；默认standalone为原30个长期容器。七域API与后台各共用一个Python进程，邮件发送独立；Gateway无数据库。可选SMTP定向通道另加1个，须先配置Secret并显式设`ELECT_SMTP_DIRECT_ENABLED=true`，不能自动照搬本机网络。

```sh
sh deploy/compose.sh /absolute/stack.env elect config --quiet
sh deploy/upgrade.sh /absolute/stack.env elect
sh deploy/status.sh /absolute/stack.env elect
```

升级入口要求镜像已构建，使用`--no-build`。已有卷切换先停止全部旧API/后台（包括非默认profile），再启动基础服务、迁移、TLS预检与应用；不重建Secret或删除卷。失败时应用保持停止，修正后重入。首次本地构建仍可使用`compose.sh ... up -d --build`，固定镜像发布流程留待方案第五步；2GB目标机不承担现场构建/测试。

统一入口按`ELECT_ALLOW_LOCAL_HTTP`选择本机覆盖，按显式SMTP开关选择通道，随后选择轻量和ops覆盖；restore最后应用并完全排除host网络SMTP通道。status/backup/restore采用同一配置，恢复同时禁止合并和独立后台且检查全部profile。原本机业务env/部署本轮未切换、未启动；第一次采用统一入口时，原三文件SMTP部署须明确补入通道选择字段。普通up不代替已有卷模式切换流程。

combined的MySQL附加配置挂载在只读conf.d目录之外，通过`--defaults-extra-file`在原配置后加载，保留UTC、binlog及事务刷盘。RabbitMQ使用固定摘要普通镜像、核心定义导入和独立公开配置，旧`rabbitmq.conf`可保留；不重新生成账号/Secret。切回standalone恢复原基础参数与management镜像。资源验收入口见[第三步验收](acceptance/Docker低资源第三步验收.md)。

## 本机私网 HTTP 部署

0.13.0增加显式免域名/入口证书的私网部署，本轮仅发布 `http://10.8.0.88:6874`，内部 TLS 与 SMTP TLS 保留。使用 compose.local.yaml 和独立 Secret/业务卷；用户指定的本地邮件文件由专用进程导入，TUN 环境使用指定 SMTP 的物理网卡定向出口。配置、Cookie/Origin、地址池与启停见 [本机私网部署](runbooks/本机私网部署.md)。以下域名/证书章节用于默认 HTTPS 模式。

## T3 控制基础升级

T3 启用 Monitoring 配置/屏障/发送许可和 Identity 持久撤回，当前 head 为 `identity_0003`、`school_0005`、`room_0004`、`monitoring_0003`。`monitoring_encryption_key_bundle` 是独立 AES-256-GCM 多版本邮箱密钥，只挂载 Monitoring API，不与学校 KEK 共用。首次 provision 自动生成；已有 T2/第一批 T3 Secret 目录必须保留，按以下顺序重复升级：

```sh
docker build -t elect-backend:local backend
docker run --rm --network none --user 0:0 \
  -v /opt/elect/secrets:/run/upgrade elect-backend:local \
  python -m services.deployment.upgrade_controls --directory /run/upgrade
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
sh deploy/compose.sh "$PWD/deploy/.env" elect build
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

deploy/.env.example 已列出 ELECT_IMAGE、ELECT_WEB_IMAGE、MYSQL_IMAGE、REDIS_IMAGE、RABBITMQ_IMAGE 等镜像变量；基础服务固定摘要，CI版本标签发布受测应用镜像/摘要。ELECT_IMAGE_MODE=published时ELECT_IMAGE/ELECT_WEB_IMAGE为repo@sha256引用；local时为开发构建的镜像名称。

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
sh deploy/compose.sh "$PWD/deploy/.env" elect up -d --build
docker compose --env-file deploy/.env -f deploy/compose.yaml ps -a
```

config --quiet 校验配置引用；up --build 构建 frontend/backend 镜像，启动基础服务，等待数据库健康、migrate 和 tls-check 完成，再按依赖启动应用。一次性作业成功退出属于正常完成，不能将它们要求为长期 running。

当前运行八个 API、六个本域 Relay、Audit Worker及Identity/Room/Adapter后台进程；监控Scheduler/Worker/恢复器、提醒、邮件Worker/恢复器和Payment Worker/恢复器已加入，共30个长期服务。业务健康来自持久扫描/租约，不使用空循环。MQ/Redis 故障在领域 API readiness 显示 degraded（HTTP 200），MySQL/结构异常返回 503；后台健康反映实际扫描/领取/持久提交心跳。

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

## T6支付升级

保留原Secret与卷，重复运行upgrade_controls补充payment:browser/school:payment/payment:proof及签名支付队列权限，重建RabbitMQ加载定义。升级school_0006与payment_0002/0003，Payment/Gateway/Adapter重建，新增payment-worker/payment-recovery挂载Payment runtime和internal_ca；Worker在app/data网络，学校出口仍只由Adapter持有。30个长期服务含两个新增进程，心跳反映真实数据库扫描/续租。普通环境两项支付写开关和PAYMENT_ACCEPTANCE_PASSED保持false；完整真实建单/状态/到账验收后再开放。Worker退出宽限180秒，每10秒续租90秒，恢复器不重放已发送的D01/E02/E03。见[T6决策](decisions/T6支付与二维码.md)。

## 支付取消升级

0.11.0先运行payment_0004，再重建Payment/Gateway和Payment Worker/恢复器。取消意图与学校状态分开；不能回改迁移或删除学校台账，旧键不重发。测试端口可使用ELECT_TEST_HTTP_PORT/ELECT_TEST_HTTPS_PORT启动第二个独立项目，默认18080/18443。T7本轮按用户要求跳过部署证书/更换演练，现有测试HTTPS与内部TLS保留。

## T7运维与集中验证

0.12.0提供deploy/compose.ops.yaml、backup.sh、restore.sh和status.sh，详细命令/安全门禁见[备份恢复](runbooks/备份恢复与隔离对账.md)、[运行状态](runbooks/运行状态与容量.md)。独立完成test-stack后运行test-t7-recovery.sh，再以ELECT_TEST_IMAGE=elect-backend-smoke:ops运行test-t7-browser.sh；已纳入Actions。模拟容量为同一隔离smoke中的scripts.t7_capacity --plans 100 --workers 8；任何普通运行不自动产生测试数据。

compose.restore.yaml必须和base/ops一起使用；学校/SMTP出口及全部副作用/后台默认隔离。恢复后按原ID逐项对账，不盲重放Outbox或学校写。本轮[RPO/RTO及范围](acceptance/T7验收记录.md)只指本机合成数据，生产异机复制与PITR/持续频率尚未部署，生产证书步骤按用户要求跳过。
