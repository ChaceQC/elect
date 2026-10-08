# 寝室电费系统

通过学校账号查询和管理寝室电费的 Web 应用，提供寝室绑定、余额查询、消费明细、定时监控和低余额邮件提醒，支持桌面与手机使用。

本地应用会话与学校资料使用独立接口；学校资料暂时不可用时的缓存访问与兼容规则见[本地会话与学校资料](docs/runbooks/本地会话与学校资料.md)。

当前版本：`0.22.7`（开发版）。学校缴费列表在HTTPS和私网HTTP入口使用50秒超时，与45秒查询、55秒浏览器等待衔接，见[缴费入口预算](docs/decisions/缴费列表入口超时.md)。付款后绑定失效会明确结束余额刷新并保留已付款状态，见[余额受理失败规则](docs/decisions/付款后余额受理失败终结.md)。付款后的余额刷新独立读取学校余额，避免复用付款前查询，见[付款后余额规则](docs/decisions/付款后余额独立读取.md)。排队建单遇凭据变化时，可证明未发送的订单明确终结，已发送订单保留未知保护，见[建单发送边界](docs/decisions/建单凭据失效与发送边界.md)。监控采集下新增学校缴费列表及同范围总缴费，见[缴费明细规则](docs/decisions/学校缴费明细列表.md)。登录或重载后自动刷新总览/明细的余额与历史，复用原请求和限流恢复，见[自动查询规则](docs/decisions/登录与页面重载自动查询.md)。消费趋势合并学校历史与监控余额变化估算，当天首次余额减少归前一天，后续归当天；学校金额为0但监控有减少时也可补充，金额日期全部覆盖即显示完整，估算来源独立标注；来源与去重规则见[消费趋势合并](docs/decisions/消费趋势合并监控估算.md)。监控明细显示电表止码与较上次成功采集的差值，规则见[电表口径](docs/decisions/电表读数与缴费结果确认.md)。Identity将身份提交前的认证拒绝与暂存缺失终结为失败，真实依赖错误仍保留恢复健康预算，见[登录拒绝与恢复健康](docs/decisions/登录拒绝与恢复健康隔离.md)。隔离恢复校验跨库观测水位，见[集成恢复手册](docs/runbooks/审计修复集成与恢复.md)。会话续期减写、监控一致性读取、样本索引与双槽公平读取已实现，见[读取与有界调度](docs/runbooks/读取与有界调度.md)。开启监控、修改间隔后的立即采集与手动采集共享额度，拒绝不改原状态，见[配置采集规则](docs/decisions/监控配置采集统一计额.md)。余额、手动采集和二维码新键按用户计额，原键可恢复；快照公平连续回收，见[请求预算与保留规则](docs/runbooks/请求预算与保留归档.md)。core与独立服务提供可关联的脱敏诊断和统一健康判定；后台持续失败时协调退出，由既有容器策略恢复，见[诊断与恢复规则](docs/runbooks/后台健康与协调退出.md)。OCR计算使用独立有界执行器；余额按持久观测序号更新，历史窗口拥有独立预算和续租，支付后失败余额任务结束自动跟踪，见[执行与余额规则](docs/runbooks/余额观测与历史执行边界.md)。历史合并终态与登录执行门见[历史修复与登录资源](docs/runbooks/历史合并修复与登录执行门.md)。协议阅读和浏览器记忆见[登录规则](docs/decisions/界面状态与登录授权.md)；快照和历史受理预算见[查询资源规则](docs/decisions/查询资源受理与快照清理.md)。沿用三个Python进程的7容器组合及13容器回退，见[核心组合](docs/decisions/七容器核心组合.md)。正常支付/解绑2秒自动更新与公共能力开关保持。

## 功能

- **学校登录**：使用学校账号和验证码登录；阅读并同意协议后，登录及重新认证统一授权后台使用加密凭据。账户提供重新认证和退出，监控开关保存后生效。
- **寝室管理**：同步学校绑定，搜索、新增或解除绑定，设置默认寝室。
- **电费查询**：查看寝室余额、消费趋势、指定日期范围的历史明细与采集记录。
- **定时监控**：按设定间隔采集余额及学校最新电表日记录，读数标明日期与质量；支持立即采集、取消本次采集和关闭监控。
- **邮件提醒**：配置收件邮箱、低余额阈值和提醒次数。

学校绑定写入和真实邮件投递默认关闭，需要按部署说明显式启用。支付功能暂未对外开放，页面可用操作以服务端返回的能力为准。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 前端 | React、Vite、JavaScript/JSX、ECharts |
| 后端 | Python 3.12.10、FastAPI、Pydantic、SQLAlchemy、Alembic、uv |
| 数据与消息 | MySQL 8.4、Redis、RabbitMQ |
| 部署 | Docker Compose、Nginx |

浏览器通过同源 `/api/v1` 访问后端，学校认证和接口请求由后端处理。学校凭据加密保存，监控任务与业务状态持久化到数据库。

## 部署

目标机器需要 Docker Engine 和 Docker Compose 2.24.4 或更新版本。使用发布的固定摘要镜像，目标机只拉取、初始化和运行；源码构建在开发机或 CI 完成。

默认采用 HTTPS。按 [固定镜像发布与启动](docs/runbooks/固定镜像发布与启动.md) 下载开发版部署包和 `release.env`，配置服务 Secret、域名和证书并完成首次 Secret 初始化后执行：

```sh
sh deploy/start.sh /absolute/stack.env elect
sh deploy/status.sh /absolute/stack.env elect
```

私网 HTTP 模式使用独立配置，见 [私网部署说明](docs/runbooks/本机私网部署.md)。数据使用 Docker 命名卷持久化；启停、升级和备份恢复按对应运行手册执行。

设置 `ELECT_DEPLOYMENT_MODE=core` 选择7容器组合。核心保留各领域账号/连接池、事务与后台心跳，内部直接调用仍校验权限和DTO，Adapter与邮件发送保持独立。切换/回退使用同一 `upgrade.sh`，先停止全部旧应用角色；不要直接启动两套组合。迁移版本清单在构建时生成，MySQL保留Performance Schema诊断但限制容量，Nginx使用1个worker。

在公开配置中设置 `ELECT_DEPLOYMENT_MODE=combined` 可选择 13 个长期容器的轻量组合；默认 `standalone` 保留独立角色。轻量组合采用每池 `2+1`、MySQL 128MiB/40连接、Redis 32MiB、普通 RabbitMQ 和 30秒探针；参数与兼容方式见 [第三步资源说明](docs/decisions/Docker低资源资源参数.md)。0.17.0引入事务提交后Outbox唤醒、有界消息推送、空闲退避及两个监控执行槽，邮件保持单槽，见[执行效率说明](docs/decisions/Docker低资源执行效率.md)。首次和已有部署升级分别使用 `deploy/start.sh` / `deploy/upgrade.sh`，校验并拉取摘要后停止全部旧角色，按依赖串行启动。开发机在 `ELECT_IMAGE_MODE=local` 时使用 `compose.sh up -d --build`。2核2GB/50人容量仍需按优化方案验收。

## 本地开发

开发环境使用 Node.js 22.23.2、npm 10.9.8、Python 3.12.10 和 uv。

在仓库根目录启动前端开发服务器：

```sh
cd frontend
npm ci
npm run dev
```

在仓库根目录安装后端依赖：

```sh
cd backend
uv sync --locked
```

真实登录与查询需要已配置的后端服务。服务启动、契约生成和验证命令见 [开发说明](docs/开发说明.md)。

## 界面演示

`example/` 提供使用模拟数据的独立界面演示。需要 Node.js 22 或更新版本，在仓库根目录执行：

```sh
cd example
npm ci
npm run dev
```

打开终端显示的本地地址。演示不连接学校，不执行真实监控、邮件或支付，也不参与正式系统构建。详细说明见 [示例文档](example/README.md)。

## 目录

```text
frontend/              # React 学生端、测试与 Dockerfile
backend/               # Python 业务服务、后台任务、迁移与测试
deploy/                # Compose、Nginx 配置与运维脚本
docs/                  # 设计、接口契约、部署、验收与运维文档
example/               # 独立界面演示
AGENTS.md              # 开发规范
PROJECT_PROGRESS.md    # 开发进度与验证记录
```

## 文档

- [文档索引](docs/README.md)
- [后端架构](docs/后端架构详细设计.md)
- [接口契约](docs/contracts/README.md)
- [学校接口](docs/学校对接API文档.md)
- [备份恢复](docs/runbooks/备份恢复与隔离对账.md)
- [运行状态与容量](docs/runbooks/运行状态与容量.md)
- [Docker 低资源部署优化方案](docs/Docker低资源部署优化方案.md)（13容器组合；2核2GB容量待验收）
- [开发规范](AGENTS.md) · [GitHub 协作流程](docs/GitHub协作与合并流程.md)
- [项目进度与验证记录](PROJECT_PROGRESS.md)

本地配置、测试凭据、Secret 和证书私钥不纳入版本管理；公开配置模板位于 `deploy/`。
