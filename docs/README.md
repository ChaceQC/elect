# 寝室电费系统文档

更新日期：2026-10-01。

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
| [公开/内部契约](contracts/README.md) | 28 个 API、DTO、版本/幂等、状态模型与恢复规则 |
| [T0 实施决策](decisions/T0实施决策.md) | ID、调度锚点、邮箱、Secret、领域库与能力开关 |
| [数据库基线](database/README.md) | 七域独立初始迁移、约束与空库验证 |
| [T0 需求追踪](T0需求追踪表.md) | 页面字段、按钮、异步能力、模块和实现阶段 |
| [T0 验收](acceptance/T0验收记录.md) | 交付物、测试结果和后续边界 |

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

T0 已完成：frontend 独立入口、依赖锁、类型与模拟场景；backend 独立工程、DTO/状态模型与七域迁移。deploy 已有公开配置与 Secret/账号清单；业务服务、Dockerfile/Compose 从 T1 开始实现。参考材料自己的 README 保留在 example 内。

## 部署约定

- 所有应用与基础服务通过 deploy/compose.yaml 编排，目标机器只安装 Docker Engine/Compose。
- frontend/Dockerfile 在 Node 阶段安装依赖、编译，在 Nginx 阶段提供静态文件和同源 `/api/` 反代。
- backend/Dockerfile 安装 Python 锁定依赖；API、Scheduler、Worker、Relay、恢复器与一次性作业均在容器中运行。
- MySQL、Redis、RabbitMQ 为 Compose 服务，使用命名卷保存必要状态。
- deploy/.env 配置 ELECT_DOMAIN、ELECT_TLS_CERT_FILE、ELECT_TLS_KEY_FILE；证书链和私钥通过只读 Secret 挂载。
- Nginx 唯一发布 80/443；HTTPS 域名、后端可信 Origin 与邮件站内链接使用同一配置。

具体配置和目标命令见 [Docker 部署配置说明](Docker部署配置说明.md)。Dockerfile、Compose 和业务代码尚待实施。
