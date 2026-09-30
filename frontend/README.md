# 学生端工程

T0 独立入口、生成 DTO、10 个 MSW 场景与参考截图已完成。页面显示服务准备状态，业务页面、路由和 API 客户端从 T1 开始接入；生产入口不导入模拟场景。

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

依赖与源码均独立于 example。锁文件使用固定 Node 容器生成；T1 已建立 Node 编译 → Nginx 运行镜像，在仓库根执行 `docker build -t elect-frontend:v0.1.0 frontend`。路由与数据层仍在本阶段接入。详细开发、契约与测试入口见 [开发说明](../docs/开发说明.md)。
