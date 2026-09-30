# 寝室电力 · nature 浅蓝方案

独立 React 前端展示，仅保留 nature 浅蓝方案。首页 / 与 /nature.html 打开同一界面，不依赖原项目的前后端，不请求学校 API。

## 启动

建议使用 Node.js 22 或更新版本。在解压目录运行：

```sh
npm ci
npm run dev
```

打开终端显示的本地地址。Windows PowerShell 如果限制运行 npm.ps1，请改用 npm.cmd ci 和 npm.cmd run dev。

## 功能

- 登录：任意 6–20 位数字学号与非空密码，计算验证码，阅读协议至底部并勾选同意。不要输入真实密码。
- 首次登录绑定寝室，已有绑定则进入总览；支持搜索、新增绑定与切换默认寝室。
- 电费明细默认最近 30 天，支持最近 7／30／90 天、自定义日期范围和浅蓝日历。
- 趋势图与采集明细共用日期范围，按天／周／月汇总，明细分页显示。
- 监控设置：邮箱、余额阈值、60–1440 分钟间隔和 1–5 次提醒；开启并保存后展示采集样例。
- 缴费仅展示确认，不创建订单或扣款。

绑定与设置按学号保存在浏览器 localStorage 中，密码不保存。数据均为模拟，演示日期固定为 2026-10-01，不执行实际监控或发送邮件。

## 构建

```sh
npm run build
npm run preview
```

产物位于 dist/。压缩包不包含 node_modules/ 与 dist/，请先安装依赖再启动，不要直接双击 HTML 文件。

## 源码

- src/nature.jsx：React 入口。
- src/StudentApp.jsx：登录、绑定、总览及监控设置。
- src/DetailsHistory.jsx：消费趋势与采集明细。
- src/DateRangePicker.jsx：日期选择器。
- src/historyData.js：模拟数据和筛选汇总。
- src/Trend.jsx、src/Chart.jsx：趋势图。
- src/*.css：页面、浅蓝主题和日期控件样式。
