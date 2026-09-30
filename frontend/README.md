# 学生端工程

当前为 T0 独立入口与开发工具基线。页面显示服务准备状态，业务页面、路由和 API 客户端从 T1 开始接入。

Node.js 22.23.2 / npm 10.9.8：

```sh
cd frontend
npm ci
npm run dev
npm run lint
npm run typecheck
npm run build
```

依赖与源码均独立于 example。锁文件使用固定 Node 容器生成；生产 Dockerfile 属于 T1。详细开发、契约与测试入口见 [开发说明](../docs/开发说明.md)。
