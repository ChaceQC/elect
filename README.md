# 寝室电费系统

面向学生的寝室电费系统，目标提供学校登录、寝室绑定、电费查询、持久监控、低余额邮件与缴费能力。

当前版本：0.1.0。T0 工程与契约基线已完成：独立前后端、28 个 API 契约、七域初始迁移、状态模型和前端场景/参考截图已验证。业务功能与 Docker 部署从 T1 开始实施，当前不提供可使用的学校业务服务。任务进度与验证结果见 [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md)。

GitHub 公开仓库：[ChaceQC/elect](https://github.com/ChaceQC/elect)。

## 项目入口

- [开发规范](AGENTS.md)：版本、Git/GitHub 工作流、代码规模、文档同步与验证要求。
- [项目文档](docs/README.md)：总实施计划、前后端设计、学校 API 与 Docker 部署说明。
- [界面参考](example/README.md)：独立 React 演示的启动方式与模拟功能。
- [开发说明](docs/开发说明.md)：正式工程的环境、构建和验证入口。
- [T0 验收](docs/acceptance/T0验收记录.md)：交付物、测试结果及后续阶段边界。

## 目录

```text
AGENTS.md              # 开发规范
PROJECT_PROGRESS.md    # 持续更新的任务进度
frontend/              # 独立 React/Vite 入口、依赖锁与验证工具
backend/               # Python 3.12.10/uv 工程与领域包
docs/                  # 设计、实施、契约、验收和运维文档
deploy/                # 公开变量与Secret/领域库所有权约定，Compose待T1
example/               # 独立界面与交互参考
```

部署变量与 Secret 约定已在 `deploy/` 建立，Dockerfile/Compose 待 T1；生产源码与镜像构建不依赖 `example/`。

## 启动界面参考

需要 Node.js 22 或更新版本：

```sh
cd example
npm ci
npm run dev
```

打开终端显示的本地地址。构建使用 `npm run build`。此演示使用模拟数据，不请求学校 API；详细限制见 [参考说明](example/README.md)。

正式系统的目标环境仅需 Docker Engine/Compose，启动入口将在部署工程实施后提供。

正式前端开发使用 `cd frontend && npm ci && npm run dev`，当前显示服务准备页面；后端开发使用 `cd backend && uv sync --locked`。详细环境与验证见 [开发说明](docs/开发说明.md)。

## 开发与版本

项目使用 Git 和 GitHub 管理，远程名称为 `origin`。主分支为 `main`，日常开发在 `dev`。每完成一个可验证小步，同步受影响文档及进度后使用中文说明 commit 并 push；完整功能验证通过且已推送后，再从 `dev` 合并到 `main`。

项目版本采用 `X.Y.Z`，Git tag 与发布名称采用 `vX.Y.Z`。非正式版使用 `v0.y.z`，正式稳定发布从 `v1.0.0` 开始。详细规则见 [AGENTS.md](AGENTS.md)。
