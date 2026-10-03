# 寝室电费系统

面向学生的寝室电费系统，目标提供学校登录、寝室绑定、电费查询、持久监控、低余额邮件与缴费能力。

当前版本：0.13.1。T0/T1/T2/T3/T4/T5 已完成，M1/M2 技术闭环已验收；总览/逐寝室余额、C02历史/聚合、持久采集、运行取消与固定快照分页已接通。余额严格按本人Binding/学校roomId匹配，同账号不同房间不混用。生产前端真实本人B02/C02和一次balance_only采集通过；学校写开关默认关闭，真实指定邮箱 SMTP 接受已验证，默认外发开关保持关闭。T6 支付实施中，订单、二维码、持久执行和界面已实现并通过合成验收，指定真实支付验收进行中，见 [T6决策](docs/decisions/T6支付与二维码.md)。任务进度与验证结果见 [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)。

本机私网部署入口：`http://10.8.0.88:6874`，使用独立 elect-local 项目和用户指定 SMTP，暂不配置域名/入口证书。2026-10-03按用户要求已停止全部本项目容器，保留容器与数据卷；当前入口不可用，停机记录见 [运行状态](docs/runbooks/运行状态与容量.md)。配置与启停见 [本机私网部署](docs/runbooks/本机私网部署.md)。本机配置已启用页面明确确认后的绑定/解绑，公共支付因D02终态待验保持关闭。

GitHub 公开仓库：[ChaceQC/elect](https://github.com/ChaceQC/elect)。

T7 集中验收已开始，按本轮要求跳过部署证书与更换演练；跨标签页会话清理、五种屏宽、键盘与图表释放已补齐定向回归，备份恢复和容量检查继续实施。范围见 [T7 决策](docs/decisions/T7集中验收与恢复.md)。

## 项目入口

- [开发规范](AGENTS.md)：版本、Git/GitHub 工作流、代码规模、文档同步与验证要求。
- [项目文档](docs/README.md)：总实施计划、前后端设计、学校 API 与 Docker 部署说明。
- [界面参考](example/README.md)：独立 React 演示的启动方式与模拟功能。
- [开发说明](docs/开发说明.md)：正式工程的环境、构建和验证入口。
- [T0 验收](docs/acceptance/T0验收记录.md)：交付物、测试结果及后续阶段边界。
- [T1 验收](docs/acceptance/T1验收记录.md)：Docker、TLS、事件恢复与前端公共层的实际验证。
- [T2 验收](docs/acceptance/T2验收记录.md)：真实学校/生产前端登录、本人读取、后台恢复与隔离/故障边界。
- [T3 控制基础](docs/acceptance/T3控制基础验收记录.md)：监控配置、取消/切换/凭据屏障原语与实际数据库验证，早期控制增量记录。
- [T3 凭据与许可](docs/acceptance/T3凭据与许可验收记录.md)：持久撤回、激活故障/补偿、token 竞态、发送授权及账户界面，验证使用合成学校。

- [T3 绑定与界面](docs/acceptance/T3绑定与界面验收记录.md)：一次 dispatch/unknown、筛选与操作恢复、监控草稿和指定目标真实新增。

- [T3 删除绑定](docs/acceptance/T3删除绑定验收记录.md)：单次学校解绑、连续缺席/未知恢复、默认屏障、真实指定删除与历史保留。

- [T4 查询增量](docs/acceptance/T4查询验收记录.md)：逐寝室余额隔离、7天历史窗口、内容快照修订与保守覆盖度。

- [T4 采集引擎](docs/acceptance/T4采集引擎验收记录.md)：持久调度、短租约、唯一样本、恢复和固定快照。

- [T4 完整验收](docs/acceptance/T4验收记录.md)：真实只读查询/采集、界面、故障恢复与具体下一步。

## 目录

```text
AGENTS.md              # 开发规范
PROJECT_PROGRESS.md    # 持续更新的任务进度
frontend/              # 独立 React/Vite 入口、依赖锁与验证工具
backend/               # Python 3.12.10/uv 工程与领域包
docs/                  # 设计、实施、契约、验收和运维文档
deploy/                # 公开变量与Secret/领域库所有权约定，Compose、配置模板与运维入口
example/               # 独立界面与交互参考
```

部署变量与 Secret 约定已在 `deploy/` 建立，两端镜像可独立构建，Compose 已提供；生产源码与镜像构建不依赖 `example/`。

## 启动界面参考

需要 Node.js 22 或更新版本：

```sh
cd example
npm ci
npm run dev
```

打开终端显示的本地地址。构建使用 `npm run build`。此演示使用模拟数据，不请求学校 API；详细限制见 [参考说明](example/README.md)。

正式系统的目标环境仅需 Docker Engine/Compose；配置 Secret、域名和证书后使用 [部署入口](docs/Docker部署配置说明.md) 启动当前阶段服务。T2 认证 Secret、内部 TLS 与恢复/同步进程见 [实施决策](docs/decisions/T2认证与读取.md)。

正式前端开发使用 `cd frontend && npm ci && npm run dev`；后端开发使用 `cd backend && uv sync --locked`。详细环境与验证见 [开发说明](docs/开发说明.md)。

本地 `auth.txt` 和 `email_auth.txt` 为测试凭据，禁止提交或进入镜像；邮件文件五行格式与禁止直接读取的约束见 [本地测试说明](docs/开发说明.md#本地真实测试凭据)。文件存在不自动开启真实邮件投递。

## 开发与版本

项目使用 Git 和 GitHub 管理，远程名称为 `origin`。`main` 为主分支，日常默认在 `dev` 开发；当前开发分支可直接 commit 并 push，无需 PR。每完成一个可验证小步，同步文档和进度后用中文说明提交推送；仅合并到 `main` 时必须通过 PR，通常为 `dev → main`。`main` 要求严格必需检查 `容器验证 / check`，对管理员同样生效；只有 PR 最新提交的 Actions 全部成功才能合并。操作与失败处理见 [GitHub 协作与合并流程](docs/GitHub协作与合并流程.md)。

项目版本采用 `X.Y.Z`，Git tag 与发布名称采用 `vX.Y.Z`。非正式版使用 `v0.y.z`，正式稳定发布从 `v1.0.0` 开始。详细规则见 [AGENTS.md](AGENTS.md)。

T5 低余额事件、持久投递/恢复与界面已完成；真实本人 B02 采集到指定 SMTP 的一次投递通过，服务器接受与最终收件分开记录，见 [T5 验收](docs/acceptance/T5验收记录.md)。本机 TUN 的 SMTP 代理路径已确认，验收使用指定服务的临时直连通道；学校仍要求验证码，保留原链路。

支付现已支持本地取消：停止继续处理、保留学校台账，在途请求安全结束后解除占位。指定1元学校二维码及用户付款、同寝室B02余额增加1.00元已验证；D02仍为业务500，自动已支付映射与公共支付开放尚未验收，见 [T6记录](docs/acceptance/T6验收记录.md)。

T7本轮验收与运维入口见[T7记录](docs/acceptance/T7验收记录.md)、[备份恢复](docs/runbooks/备份恢复与隔离对账.md)、[运行状态](docs/runbooks/运行状态与容量.md)；部署证书步骤跳过，生产异机/PITR与自动支付终态仍未验收。
