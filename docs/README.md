# 寝室电费系统文档

更新日期：2026-10-02。

正式前端在 frontend/，后端在 backend/，设计、实施与部署文档统一在 docs/。仓库根目录维护 [项目总览](../README.md)、[开发规范](../AGENTS.md) 和 [项目进度](../PROJECT_PROGRESS.md)。example/ 是独立参考材料，供查看界面和交互；生产源码和镜像不依赖它。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [总实施计划](总实施计划.md) | 统一目标、前后端依赖、里程碑、联调顺序与整体交付标准 |
| [后端架构详细设计](后端架构详细设计.md) | 服务边界、数据模型、API、持久任务、部署设计 |
| [后端实施计划](后端实施计划.md) | P0–P8 的详细任务、交付物与定向验收 |
| [前端实施计划](前端实施计划.md) | F0–F8 的页面、组件、API 接入与定向验收 |
| [学校对接 API 文档](学校对接API文档.md) | 学校认证、寝室、历史、支付协议及验证范围 |
| [Docker 部署配置说明](Docker部署配置说明.md) | 全栈容器部署、域名、证书、预检与更换流程 |
| [开发说明](开发说明.md) | 正式工程的环境、构建、契约和验证入口 |
| [GitHub 协作与合并流程](GitHub协作与合并流程.md) | 当前分支直接提交、main 的 PR 与 Actions 合并门禁 |
| [公开/内部契约](contracts/README.md) | 33 个 API、DTO、版本/幂等、状态模型与恢复规则 |
| [T0 实施决策](decisions/T0实施决策.md) | ID、调度锚点、邮箱、Secret、领域库与能力开关 |
| [数据库基线](database/README.md) | 七域独立初始迁移、约束与空库验证 |
| [T0 需求追踪](T0需求追踪表.md) | 页面字段、按钮、异步能力、模块和实现阶段 |
| [T0 验收](acceptance/T0验收记录.md) | 交付物、测试结果和后续边界 |
| [T1 验收](acceptance/T1验收记录.md) | Docker、TLS、权限、可靠事件与前端公共层 |
| [T2 验收](acceptance/T2验收记录.md) | 真实学校/生产前端登录读取、后台恢复与隔离/故障边界 |
| [T3 控制基础验收](acceptance/T3控制基础验收记录.md) | 第一批配置、执行/切换/凭据屏障原语及 MySQL 竞态；早期控制增量记录 |
| [T3 凭据与许可验收](acceptance/T3凭据与许可验收记录.md) | 三域凭据协调/撤回、发送许可、账户恢复与实际数据库故障检查 |

## 统一目录

```text
README.md                    # 项目总览、入口和启动说明
AGENTS.md                    # 版本与开发规范
PROJECT_PROGRESS.md          # 任务、验证、阻塞和具体下一步
frontend/                    # 正式前端；package.json、src/main.jsx、Dockerfile
backend/                     # 正式后端；pyproject.toml、services/、tests/、Dockerfile
docs/                        # 设计、计划、契约、开发/部署/验收文档
  contracts/                 # OpenAPI、内部 HTTP 与事件协议
  acceptance/
  runbooks/
deploy/                      # Compose、Nginx 模板、基础服务配置和运维入口
example/                     # 页面和交互参考，不参加生产构建
```

T0 已完成：frontend 独立入口、依赖锁、类型与模拟场景；backend 独立工程、DTO/状态模型与七域迁移。deploy 已有公开配置与 Secret/账号清单；T1 的两端 Dockerfile、Compose、运行/认证/事件/Audit、TLS 与 F1 路由/公共数据层已完成验收。T2 认证与本人读取、生产前端已完成真实联调与容器验收；详情见 [T2 决策](decisions/T2认证与读取.md)。参考材料自己的 README 保留在 example 内。

T3 控制事务和内部 retarget 协议见 [第一批决策](decisions/T3监控控制基础.md)，凭据协调/持久撤回/发送许可和账户界面见 [第二批决策](decisions/T3凭据协调与发送许可.md)。Room 默认切换与首次同步初始化见 [默认 Saga 验收](acceptance/T3默认Saga验收记录.md)；随后接入筛选绑定与监控设置界面；监控控制交付不表示已经运行采集或邮件。

## 部署约定

- 所有应用与基础服务通过 deploy/compose.yaml 编排，目标机器只安装 Docker Engine/Compose。
- frontend/Dockerfile 在 Node 阶段安装依赖、编译，在 Nginx 阶段提供静态文件和同源 `/api/` 反代。
- backend/Dockerfile 安装 Python 锁定依赖；API、Scheduler、Worker、Relay、恢复器与一次性作业均在容器中运行。
- MySQL、Redis、RabbitMQ 为 Compose 服务，使用命名卷保存必要状态。
- deploy/.env 配置 ELECT_DOMAIN、ELECT_TLS_CERT_FILE、ELECT_TLS_KEY_FILE；证书链和私钥通过只读 Secret 挂载。
- Nginx 唯一发布 80/443；HTTPS 域名、后端可信 Origin 与邮件站内链接使用同一配置。

具体配置和目标命令见 [Docker 部署配置说明](Docker部署配置说明.md)。Dockerfile 已建立，Compose 与公共运行设施已建立；T2 认证与本人读取已经接入，其他业务按阶段实施。

T3 筛选绑定与界面见 [第三批决策](decisions/T3绑定筛选与异步界面.md) 和 [验收](acceptance/T3绑定与界面验收记录.md)：一次 dispatch/unknown、首次绑定默认、F3/F5 控制与指定目标真实新增已验证；删除绑定增量继续实施。

删除绑定的 [实施决策](decisions/T3删除绑定.md) 与 [验收](acceptance/T3删除绑定验收记录.md) 记录用户补充范围、学校 B08、默认/监控与一次发送/缺席确认。

T3 与 M1 已完成；指定枫苑5号-402 已真实新增并删除，正常时间的 B02/台账与前端验证见 [删除验收](acceptance/T3删除绑定验收记录.md)。下一步 T4 总览/余额/历史与持久采集，未运行 SMTP/支付。

T4查询首批见 [决策](decisions/T4查询与持久采集.md) 和 [增量验收](acceptance/T4查询验收记录.md)，持久运行与F4/F5-05继续实施。

T4持久采集后端见 [采集引擎验收](acceptance/T4采集引擎验收记录.md)，F4/F5-05与完整依赖故障回归继续。

T4整体完成，入口为 [完整验收](acceptance/T4验收记录.md) 与 [前端记录](acceptance/frontend/T4界面验收.md)。M2等待T5低余额邮件；实际阶段与合成/真实证据分开记录。

T5事件规则通过 [增量验收](acceptance/T5事件验收记录.md)，投递与真实指定邮箱验收继续实施；[实施决策](decisions/T5低余额与邮件.md)记录 DATA 边界、序号释放与本轮外发范围。

T5/P6/F5已完成，M2技术闭环完成：[T5验收](acceptance/T5验收记录.md)记录真实B02到指定邮箱一次SMTP接受及用户收件确认、TUN代理原因和学校验证码核查。T6正在实施，能力与幂等本地订单首批已实现；[T6决策](decisions/T6支付与二维码.md)记录金额政策、一次发送/未知屏障与指定真实验收范围，完整支付仍未验收。

T6-01..03已实现并通过合成验证；[T6验收](acceptance/T6验收记录.md)分别记录实现、实际数据库、合成界面与指定真实范围。T6-04/P7-06尚未完成，支付能力默认关闭。

T7集中验收进行中，部署证书步骤按用户要求跳过，见[T7决策](decisions/T7集中验收与恢复.md)。0.11.0增加本地取消与指定1元验收：用户付款和B02增加1.00元已确认，D02业务500仍不自动映射已支付，见[T6记录](acceptance/T6验收记录.md)。
