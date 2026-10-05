# Docker低资源优化第三步验收

日期：2026-10-03（Asia/Shanghai）；版本：0.16.0。

对应[优化方案](../Docker低资源部署优化方案.md)第三步与[资源决策](../decisions/Docker低资源资源参数.md)。原业务环境保持停止，只创建本轮隔离项目，学校/SMTP/支付均为合成服务，不读取auth.txt/email_auth.txt。

## 交付范围

- combined八个共享池固定2+1，理论应用连接40→24、MySQL上限200→40；等待3秒、UTC、READ COMMITTED、pre-ping和回收保留，Gateway无库，Notification发送Worker独立。
- MySQL Buffer Pool128MiB、table/definition cache256/400、TempTable RAM32MiB/单表8MiB、容器640MiB；原UTF8/UTC、binlog及两项事务持久性实际核对通过。
- Redis32MiB/noeviction/AOF与96MiB限额；普通固定摘要RabbitMQ 4.1.4、核心定义导入、1调度/2异步/各1脏线程、128MiB绝对水位/256MiB限额。旧RabbitMQ Secret无需覆写，复用账号/权限/队列，原卷切回management通过。
- 13个长期容器探针30秒、启动期5秒，失败发现约60/120秒；原20/45秒角色心跳窗口保持，Redis/Nginx补15秒启动宽限。
- OCR延迟加载、单次推理锁及人工验证码流程保留；锁定已有ddddocr1.6.1，直接声明ONNX1.30依赖，单会话计算/跨算子各1线程、顺序执行、禁自旋及BLAS/OMP各1线程，Adapter限额384MiB。
- 两段uv sync新增BuildKit共享锁定依赖缓存，仍--locked且缓存不进入运行镜像；未形成固定镜像发布或替代第五步。

## 功能与故障验证

- `sh deploy/check.sh`通过：后端ruff、207 passed / 1 skipped、公开/内部契约/数据库目录、七域离线DDL；前端契约/规则/类型/构建、49项单元组件、32项Playwright。新增9项单位用例校验有限池配置、脱敏失败、真实OCR会话参数/缓存及全局ONNX工厂未替换；既有provision用例扩展核心定义导入检查。
- 实际MySQL满池测试：三条均占用时第4条等待，归还后约0.20秒取得；继续满池在约3.00秒超时；归还后零借出连接，migration ready与UTC再次成功。
- 实际32个并发HTTP健康请求跨八个API全部ready，末次批次0.119秒；实际签名事件经Relay重复发布、Audit/Inbox各一条，confirm和提交后ACK保持。
- 同进程合并角色使用2+1池，单合成账号50个并发监控读取全部200，批次0.604秒；学校请求等待时租约真实续期、后台角色/健康持续推进。该场景不是50个真实账号或NAT登录容量。
- `test-low-resource.sh`通过：MQ中断仍持久扫描/API degraded，restore覆盖的八个API无后台，合并/独立入口均拒绝；采集单样本、在途取消无样本、角色故障可见、旧epoch拒绝、恢复接管、统一退出/连接释放、七域同步/默认Saga、SMTP DATA后unknown及支付丢失D01响应仍只一次写。
- 本轮旧0.15.0 Secret/原卷以13→30→13切换通过，切换基础参数和RabbitMQ镜像时保持权限/队列，17个旧角色最终全部exited。
- `test-resource-parameters.sh`在最终空库回归后的项目再次通过：所有MySQL参数实际读取符合配置，最高19条连接、连接上限错误0；RabbitMQ实际读取1/2线程、无management插件和128MiB水位。临时1MiB告警时，Relay已经尝试发布的Outbox仍未published且审计/Inbox为空；恢复128MiB后三方唯一完成。
- 独立无网络Redis写满测试实际收到OOM写入拒绝、evicted_keys为0，合成session/account-lock/global-slot均保留；AOF重写明确启动并与更新并发、最终状态ok，进程重启后上述键仍在。不是模拟Redis响应；测试管理员ACL仅用于该无网络实例，正式ACL未修改。
- 最终`test-stack.sh ... combined`全新空库通过：七域权限/并发迁移、可靠事件及T2–T6合成回归、真实MySQL/Redis/MQ中断，内部TLS/Nginx配置通过；13个长期容器最终全部healthy。

- T7实际加密快照/封存binlog与隔离恢复最终通过，62张表计数/密文保留，快照后合成邮件/建单保持unknown，旧Outbox不重放；重复apply不释放未知占位。补好网段后重入restore的本机合成RTO59秒/RPO4.548秒，不含首次地址池失败/排障，不能外推生产异机/PITR。冻结应用的备份及恢复基础服务零OOM；来源MySQL本次生命期内核峰值见资源JSON，未测持续负载下的并发备份。

## 资源证据

[原始组件与指标汇总](Docker低资源第三步资源.json)来自6核、15.51GiB主机。工作集采用cgroup v2 `memory.current - inactive_file`，每2秒采样；`memory.peak`为各容器生命期内核峰值，含文件页，不能把它们相加作为同一时刻全栈峰值。

| 逐项阶段 | 阶段末次13容器工作集 | 说明 |
| --- | --- | --- |
| 0.15.0基线空库 | 1394.09MiB | 原2+3/基础服务/10秒探针，未加载运行API的OCR |
| 共享池2+1 | 1394.86MiB | 主要降低连接预算，不据末次内存波动宣称收益 |
| MySQL附加参数 | 1238.04MiB | MySQL末次390.69MiB，新实例内核峰值396.33MiB |
| Redis32/96MiB | 1239.78MiB | 空闲数据少，预算收益在写满/AOF独立实例验证 |
| 普通RabbitMQ/线程 | 1246.74MiB | RabbitMQ末次80.54MiB；各次启动波动不作平均收益 |
| 30秒探针 | 1220.30MiB | 理论Python探针54→18次/分钟；不是稳态均值 |
| 最终版本另一全新空库 | 1237.68MiB | 首次13容器全部healthy时结束；采样窗口峰值1257.93MiB |

最终首次空库44次样本、零OOM；单项内核峰值MySQL429.73MiB、RabbitMQ180.69MiB、Redis17.44MiB。与本轮基线末次快照相较总工作集下降约11.2%；MySQL总内存仍约404MiB，不能将128MiB Buffer Pool当总占用。

无网络Redis写满/AOF并发重写的内核峰值72.27MiB、零OOM；与各13容器启动阶段分开记录。OCR在单独1CPU容器使用同一合成图进行10次推理：

| OCR指标 | 旧配置 | 最终镜像受限配置 |
| --- | --- | --- |
| 冷加载 | 0.835秒 | 0.415秒 |
| 进程线程 | 17 | 2 |
| 推理P50 / 最大 | 82.06 / 102.08ms | 12.76 / 14.24ms |
| 2秒空闲CPU时间 | 0.3045秒 | 0秒 |
| 峰值RSS | 115392KiB | 114880KiB |

两次结果摘要相同；线程与CPU改善明显，这个单图样本没有证明学校识别率或多账号恢复容量。阶段末次、各容器内核峰值、全栈采样峰值和OCR RSS是不同口径。未覆盖50人24小时、宿主机、实际运行API加载OCR、多账号恢复、备份并发峰值或2CPU全栈边界，不标记2GB可用。

## 发现与修正

- MySQL首次将新文件嵌套挂载到只读conf.d，运行时创建挂载目标失败；改为目录外附加文件并通过--defaults-extra-file加载，实际生效值/持久性及原卷/新空库重跑通过，没有靠删除卷处理。
- Redis/Nginx原配置无start_period，Docker26要求start_interval同时有启动宽限；补15秒start_period后实际启动通过，API/MySQL/RabbitMQ既有宽限保留。
- 首次正式镜像重建仅锁文件元数据变化仍下载全部OCR依赖且过慢，停止该次构建并加BuildKit缓存；从旧测试镜像中的相同锁定依赖播种后，正式Dockerfile运行/测试镜像、check及全新test-stack均实际构建通过，没有替换锁定版本或复制缓存到生产镜像。
- 本机默认Docker地址池已耗尽，隔离项目预设10.243/10.244小网段。恢复目标初始化也碰到同一问题，补本轮10.245内部网段后从已保存的加密快照继续验证；没有删除历史网络或更改Docker全局地址池。

最终检查104个受影响Markdown本地链接、公开两种模式/所有profile恢复配置、Shell语法、版本/锁文件、资源JSON及Git差异通过。仅down本轮三个隔离项目（其中旧基线/原卷项目已先停止），保留9个命名数据卷及受限测试证据；所有elect运行容器为0，原业务和历史项目继续停止，原5个非elect容器保持运行。

## 未完成范围

第四至六步（事务提交后唤醒/退避/推送消费/有限并发、固定镜像发布/分阶段启动/长期运行、2vCPU/2GB/50人24小时）仍未交付。真实D02映射、生产异机/PITR、T8及既有证书跳过范围保持。下一步先实现本域事务提交后Outbox唤醒和1→2→5→10秒空闲退避，保留低频持久扫描与confirm/租约/幂等，再验证MQ故障与取消边界。
