# Docker低资源资源参数

日期：2026-10-03（Asia/Shanghai）；版本：0.16.0。对应[优化方案](../Docker低资源部署优化方案.md)第三步，延续[后台生命周期](Docker低资源后台生命周期.md)。本轮在新隔离项目验证，原业务部署继续停机。

## 参数与适用组合

所有调小参数仅由`compose.low-resource.yaml`应用到combined，standalone保留原参数。Gateway无库；七域API与Notification发送Worker共8个池，分别使用本领域账号，发送仍独立。公开镜像模板新增`RABBITMQ_LOW_RESOURCE_IMAGE`固定版本/摘要；旧env省略时使用同一固定摘要的默认值。

| 项目 | standalone | combined |
| --- | --- | --- |
| 每个数据库池 | 2+3 / 等待3秒 | 2+1 / 等待3秒 |
| 应用理论连接总数 | 25×5=125 | 8×3=24 |
| MySQL连接上限 / Buffer Pool | 200 / 512MiB | 40 / 128MiB |
| table_open_cache / definition_cache | 原默认 | 256 / 400 |
| TempTable RAM / 单表内存 | 原默认 | 32MiB / 8MiB |
| MySQL容器限额 | 1536MiB | 640MiB |
| Redis数据上限 / 容器限额 | 128 / 256MiB | 32 / 96MiB |
| RabbitMQ镜像 / Erlang调度/异步线程 | management / 2 / 4 | 普通镜像 / 1 / 2 |
| RabbitMQ脏CPU/IO调度线程 | 原默认 | 各1 |
| RabbitMQ绝对内存水位 / 容器限额 | 原默认 / 768MiB | 128 / 256MiB |
| 长期容器Docker探针 | 10秒 | 30秒，启动阶段5秒 |
| Adapter容器限额 | 1024MiB | 384MiB |
| OCR模型 | 延迟加载、进程推理锁 | 保留上述规则，ONNX计算/跨算子各1线程、顺序执行、禁自旋，BLAS/OMP各1线程 |

40条MySQL连接中留16条给迁移、备份、运维和有限测试；不能在此组合另启动25个旧持库进程。`upgrade.sh`先停止全部旧角色再切换，禁止直接up已有部署绕过这一步。

`ELECT_DB_POOL_SIZE`只接受1..10，`ELECT_DB_MAX_OVERFLOW`只接受0..10；未配置时仍为2+3。combined为八个持库入口显式固定2/1，不以发送Worker的standalone角色标记误判部署预算。池仍保留3秒等待、UTC、READ COMMITTED、pre-ping与回收规则；没有把连接数减少转成无限等待。

## 持久性与旧卷升级

- MySQL小内存配置放在`/etc/mysql/low-resource.cnf`，通过首参数`--defaults-extra-file`在原全局配置后读取。未在只读`conf.d`内创建新嵌套挂载，原UTF8/UTC、binlog、保留期及事务刷盘继续生效；不关闭持久性。128MiB Buffer Pool不等于MySQL总占用，640MiB限额覆盖已验证的启动窗口，目标机/备份峰值仍需验收。
- 新Secret生成器使用RabbitMQ 4.1核心`definitions.import_backend/local.path`。combined另选公开`low-resource.conf`，保留现有JSON Secret导入账号、虚拟主机、权限与队列；旧Secret里的`management.load_definitions`配置文件保留但不加载。因此旧卷切换不需要重写Secret或密码，切回management也继续可用。持久消息、confirm、签名、Inbox与提交后ACK不变，管理面不发布。
- Redis复用正式ACL、TTL、AOF/everysec和noeviction，仅覆盖maxmemory；内存不足应拒绝写入，不丢认证/锁/槽，也不退回进程字典。独立无网络合成实例验证写满、AOF重写并发及重启，不修改正式ACL。
- Docker探针降频不降低业务扫描或真实角色心跳。API/Redis/Nginx两次失败约60秒判定，MySQL/RabbitMQ四次约120秒；启动期5秒检测，API15秒、MySQL60秒、RabbitMQ30秒的宽限保留，Redis/Nginx补15秒启动宽限。后台活跃角色仍按20秒、Relay/Audit等按45秒失效。

## OCR与验证边界

锁定已有ddddocr 1.6.1，并把ONNX Runtime 1.30作为直接依赖，没有下载新模型。该版本不提供SessionOptions构造参数，因此只为本实例的OCREngine加载器创建受限会话，不替换全局InferenceSession，也不先加载默认模型再重复加载。单位检查校验实际会话参数、缓存与全局工厂未改变，合成图前后结果摘要比较和CPU/延迟/线程实测另记。人工学校验证码仍由用户回答。

`sh deploy/test-resource-parameters.sh /absolute/test-dir elect-test-name`在已经完成test-stack的combined隔离项目运行，要求新Redis预算目录。入口只依赖Docker/系统Shell，验证MySQL生效值和持久性、满池等待/超时/回收、真实API健康/重复签名事件、MQ内存流控与Outbox恢复，以及独立无网络Redis预算。`test-low-resource.sh`的合并采集进程显式使用2+1，覆盖50次控制读取、学校等待期间实际续租、取消/旧epoch/统一退出和原卷双向模式切换。

结果和逐项样本见[第三步验收](../acceptance/Docker低资源第三步验收.md)。全程样本来自6核/15.51GiB主机，内存限额之和不是全机保证；完整2vCPU/2GB/50人24小时、OCR多账号恢复及备份峰值仍按第六步验证，不据短时样本恢复原部署。
