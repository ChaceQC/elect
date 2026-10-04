# 学生端工程

当前版本 `0.18.1`。React / Vite / JavaScript 学生端，提供学校登录、总览、电费明细、寝室绑定、监控预警与按服务端能力开放的缴费弹窗。

登录/重新认证的后台授权包含在使用协议中，账户不再提供撤回按钮。监控开关统一保存生效；绑定/缴费限制在入口展示，余额随时间标记过期，异步进度暂停后可恢复自动更新。行为与验证见[界面修复记录](../docs/acceptance/frontend/0.18.1界面问题修复.md)。

界面和文案以 `example/nature.html` 的浅蓝主题为基准。正式源码、依赖及镜像构建独立于 `example/`；所有业务数据来自同源 `/api/v1`，不会用演示数据填补错误或空状态。

## 开发与验证

使用 Node.js 22.23.2 / npm 10.9.8，在本目录执行：

```sh
npm ci
npm run dev
npm run lint
npm run typecheck
npm run contract:check
npm test
npm run test:e2e
npm run build
```

真实登录需要已配置的同源后端。生产入口不注册 MSW；仅显式开发配置 `VITE_ENABLE_MSW=true` 可启动开发场景。浏览器测试自行拦截合成响应，不访问学校、邮件或支付服务。

视觉回归在生产 build/preview 上执行，在本目录保存桌面和手机截图：

```sh
ELECT_UI_SCREENSHOT_DIR="$PWD/../docs/acceptance/frontend/ui-rewrite" \
  npm run test:e2e -- tests/e2e/visual-reference.spec.js
```

使用本机 Chromium 时设置 `ELECT_BROWSER_PATH`，否则先通过 Playwright 安装测试浏览器。参考截图、并排对照、文案规则及验证边界见 [界面验收](../docs/acceptance/frontend/0.13.2界面还原.md)。

## 源码组织

- `src/components/`：品牌、页面标题、公共布局、弹窗与反馈。
- `src/features/`：认证、寝室、余额与历史、监控和支付。
- `src/styles/`：基础、布局、登录、总览、历史、日历、寝室与监控样式。
- `src/api/`、`src/hooks/`：请求、幂等操作、轮询与恢复。
- `tests/`：规则/组件、业务旅程、响应式和视觉回归；合成数据只用于测试。

## Docker

在仓库根目录构建：

```sh
docker build -t elect-frontend:v0.18.0 frontend
```

开发机/CI 的 Node 阶段编译，目标机拉取本次受测的固定摘要 Nginx 镜像；[发布与启动](../docs/runbooks/固定镜像发布与启动.md)记录两端版本/源提交校验。Nginx 阶段提供静态文件；域名和反代由部署配置提供。完整检查入口是根目录的 `sh deploy/check.sh`。部署、公开配置和真实验收边界见 [前端开发与部署](../docs/前端开发与部署.md) 和 [开发说明](../docs/开发说明.md)。
