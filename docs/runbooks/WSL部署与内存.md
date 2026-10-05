# WSL 部署与内存记录

日期：2026-10-05（Asia/Shanghai）；版本：0.18.3；源码提交：`aa7c5ad72c98b28f918dc29a8441a70ff76fd589`。

## 当前部署

本次按用户要求在本机 Ubuntu-24.04 的 Docker Engine 29.1.3 / Compose 2.40.3 中新建 `elect-wsl`，使用 `combined` 组合，共13个长期容器。与原 `10.8.0.88:6874` 环境独立，没有复制原业务数据或改动原部署。

- 当前入口：`http://172.23.107.48:6874`，Windows 侧可访问；仅绑定当前 WSL 私网地址。
- Linux 检出：`/home/cloudhelm/elect-wsl`，上述提交，使用 LF 换行；Windows 工作区的 CRLF Shell 脚本不能直接交给 `sh`。
- 本地配置：`/mnt/e/Project/elect/deploy/.env.wsl`，已被 Git 忽略；仅包含公开参数和 Secret 路径。
- Secret：`/opt/elect-wsl/secrets`；新建的三个卷为 `elect-wsl_mysql_data`、`elect-wsl_redis_data`、`elect-wsl_rabbitmq_data`。
- 镜像：`elect-backend:wsl-v0.18.3-aa7c5ad`、`elect-frontend:wsl-v0.18.3-aa7c5ad`，版本和源提交标签一致。首次本机源码构建补装了 Docker Buildx，没有改动应用源码。

用户本轮明确要求开启绑定、支付、真实邮件，本地五个政策字段 `ELECT_ALLOW_SCHOOL_BINDING_WRITES`、`ELECT_ALLOW_PAYMENT_ORDER_WRITES`、`ELECT_ALLOW_PAYMENT_FORM_WRITES`、`ELECT_ALLOW_REAL_SMTP`、`ELECT_PAYMENT_ACCEPTANCE_PASSED` 均为 true，已核对运行容器。支付仍要求有效学校认证和本人有效绑定；本轮开关授权不代替全部真实支付终态验收。公共模板及原部署配置保持原值。

邮件通过已有 `configure_smtp` 在无网络容器中将 `email_auth.txt` 导入新 Secret，不打印地址或密码。当前使用普通直连，未启用额外 `smtp-direct` 容器。Worker 连接及已有 DoH/eth0 定向连接均在 connect 阶段返回 `ConnectionResetError`，尚未完成 TLS/认证，不能将开关开启描述为已可投递；没有发送测试邮件。

## 启停与 WSL 会话

本轮观察到 WSL 会话结束后 systemd 整体退出，Docker 收到正常终止信号，所有容器一起停止；不是应用 OOM。按用户再次明确要求，已启动隐藏的 `wsl.exe --distribution Ubuntu-24.04 --exec sleep infinity` 保持本次 WSL 会话，启动时 Windows PID 为20488。此进程不读取业务凭据，也不是开机自启任务。

Windows 重启或主动 `wsl --shutdown` 后，需要重新保持 WSL 会话；容器采用现有 restart 策略。WSL 地址可能变化，先核对地址，再同步本地配置中的 `ELECT_HTTP_BIND` 和 `ELECT_PUBLIC_ORIGIN` 并重建受影响容器；不要改成通配地址。

在 WSL 中使用同一个配置和项目名：

```sh
cd /home/cloudhelm/elect-wsl
sh deploy/compose.sh /mnt/e/Project/elect/deploy/.env.wsl elect-wsl ps -a
sh deploy/status.sh /mnt/e/Project/elect/deploy/.env.wsl elect-wsl
sh deploy/compose.sh /mnt/e/Project/elect/deploy/.env.wsl elect-wsl stop
sh deploy/compose.sh /mnt/e/Project/elect/deploy/.env.wsl elect-wsl start
```

以上 start/stop 针对已经完成初始化的现有容器。后续升级需先构建新镜像、按部署手册迁移并分阶段启动；不要重新 provision 已有 Secret 或使用 `down -v`。新环境需要用户登录并配置监控，本轮未导入示例业务数据或主动执行学校写操作。

## 内存实测

13个容器全部健康后，在2026-10-05 01:23:56至01:25:12连续采样7次，每次间隔为10秒等待加命令耗时。统计 `docker stats --no-stream` 的 Linux 工作集口径，扣除 inactive file cache，不包含 WSL、Docker 守护进程、镜像构建及其他项目。原始逐项数据见[采样记录](../acceptance/WSL内存2026-10-05.json)。

| 组件 | 平均内存（MiB） |
| --- | ---: |
| MySQL | 426.31 |
| School Adapter | 106.66 |
| RabbitMQ | 106.63 |
| Gateway | 91.75 |
| Monitoring | 85.90 |
| Room | 85.83 |
| Payment | 84.11 |
| Identity | 83.86 |
| Notification API | 82.40 |
| Audit | 81.46 |
| Notification Worker | 78.03 |
| Nginx | 16.02 |
| Redis | 7.12 |
| **全栈** | **1336.08** |

全栈范围为1332.31–1339.84 MiB，平均约1.305 GiB；9个 Python 容器合计平均约780.00 MiB。这里的最高值仅为采样窗口最大值，不是容器生命期峰值或业务高峰保证。

采样后的 Linux `free -b` 记录 used 2090307584 bytes、buff/cache 1959620608 bytes、available 5807206400 bytes，Swap使用0；Windows `vmmemWSL` 工作集另测为3977.37 MiB。这些是包含系统、Docker及缓存的不同口径，不能当成项目本身占用。

本轮是空业务库启动基线，无活跃监控、订单或邮件任务；没有执行登录/OCR及并发负载，不代表2核2GB/50人/24小时验收。页面、健康入口、登录协议接口均为200，采样结束时13/13健康、OOM为false，保活后容器启动时间保持一致。只执行部署必要的镜像构建、迁移、健康/网络检查和采样，未运行全量测试。

## 待处理

下一步在保持 TLS 校验与指定 SMTP 目标限制的前提下，处理这台 Windows/WSL 的 SMTP 出口连接重置，再从正式 Worker 验证 TLS 与认证。只有用户另行指定收件目标和测试投递后，才执行真实发送并区分服务器接受与最终收件。
