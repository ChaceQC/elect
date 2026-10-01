# 学生端工程

当前工程版本 0.6.0。T0 契约/场景与 T1 路由、会话初始化、API 客户端、Query 缓存、异步操作/草稿保护及公共组件已实现。T2 已接入真实学校验证码/协议/明确授权、学校重认证与账户退出、本人绑定同步/分页搜索、候选查询与过期/乱序处理。T3 账户撤回支持确认、202 进度、刷新恢复和完成后更新账户/monitor；同账户刷新保留弹窗，并发读取不覆盖较新的响应。T3 已接通楼栋/楼层/房间筛选、当前列表内搜索、绑定/默认的 202/unknown/刷新恢复和独立查看；监控页维护草稿/已保存摘要/版本核对，关闭独立提交。总览/明细/立即采集依赖 T4，删除绑定为用户本轮追加范围。

Node.js 22.23.2 / npm 10.9.8：

```sh
cd frontend
npm ci
npm run dev
npm run lint
npm run typecheck
npm run contract:check
npm test
npm run build
```

依赖与源码均独立于 example。锁文件使用固定 Node 容器生成；T1 已建立 Node 编译 → Nginx 运行镜像，在仓库根执行 `docker build -t elect-frontend:v0.6.0 frontend`。生产入口不注册 MSW；仅显式开发配置 `VITE_ENABLE_MSW=true` 可启动场景，worker 脚本只在 Vite 开发服务器提供。详细开发、契约与测试入口见 [开发说明](../docs/开发说明.md)。

容器检查在仓库根执行 `sh deploy/check.sh`，包含锁定构建、规则/类型/契约、单元和浏览器检查。T2 新增的真实浏览器脚本 scripts/t2-live-browser.mjs 仅在显式 --auth-file 时调用真实学校，不进入 CI。实际范围与截图见 [T1 前端验收](../docs/acceptance/frontend/T1公共层验收.md)。
