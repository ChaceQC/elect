# 项目进度

日期按 `Asia/Shanghai` 记录；完成、验证、阻塞与下一步随任务更新。

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
