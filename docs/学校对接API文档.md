# 湖北经济学院宿舍水电系统 API 接入文档

更新日期：2026-10-01。

本文面向需要对接湖北经济学院统一认证、宿舍水电管理系统及校园统一支付平台的开发者，包含接口地址、认证步骤、请求参数、响应字段、错误处理和完整 Python 参考实现。仅需本文件和其中列出的 Python 第三方依赖，即可理解协议并运行示例。

接口说明见第 2–6 节，调用顺序见第 7 节，验证状态见第 8 节，Python 实现和运行方法见第 9 节。

## 1. 阅读约定与接口总表

### 1.1 范围与状态说明

本文覆盖学校统一认证、寝室余额、历史用电、统计趋势、电费订单及支付二维码。教务、课表、成绩、退款和设备控制不在本文范围内。

2026-10-01 补充学校移动端绑定寝室的写接口与调用链（B04），并补充 B03 分页容器的只读核验。B04 的请求声明和页面参数已经核对，真实新增绑定尚未执行；第 9 节参考客户端暂未包含 B04 方法。

- **已验证**：在表中标注的日期，指定请求取得了可解析结果；不代表完整参数边界、账号权限及未来可用性都已验证。
- **待验证**：提供请求格式或参考实现，但缺少完整成功响应验证。
- **异常／受限**：出现错误、超时，或返回语义不符合常规预期，具体限制在对应接口内列明。
- JSON 示例为响应结构示意，金额等数值不代表真实账户数据。账号、密码密文、票据、令牌、寝室标识和订单标识均用占位符表示。
- 参数表描述已知的调用方式。未知的必填性、最大长度、限流阈值、状态全集及令牌有效期不会据此推断。
- 本文属于接入参考资料，不能替代学校正式发布的开放接口契约。线上规则变更时应重新确认。

### 1.2 基础地址

| 名称 | 地址 | 说明 |
| --- | --- | --- |
| CAS 统一认证 | `https://rz.hbue.edu.cn/authserver` | 使用 HTTPS；2026-09-30 完整认证链路验证通过 |
| SDGL API | `https://sdgl.hbue.edu.cn/api` | 宿舍水电系统，下表使用完整路径 |
| 校园支付 | `http://cwcwx.hbue.edu.cn/zhifu` | 支付页面及二维码地址，保留已验证的协议与路径 |
| SERVICE | `https://sdgl.hbue.edu.cn/api/sso/callback?targetUrl=https://sdgl.hbue.edu.cn/api/sso/callback&loginType=mobile` | 同一个完整值用于 CAS 初始化、票据申请和回调 |

`http://rz.hbue.edu.cn/authserver` 在 2026-09-30 的票据提交中出现连接错误，本文认证示例统一使用 HTTPS。

### 1.3 接口总表

| 编号 | 系统 | 方法与完整路径 | 用途 | 验证状态 |
| --- | --- | --- | --- | --- |
| [A01](#a01) | CAS | `GET /authserver/login` | 初始化认证会话 | 2026-09-30 通过 |
| [A02](#a02) | CAS | `GET /authserver/kaptcha` | 获取算式验证码 | 2026-09-30 通过 |
| [A03](#a03) | CAS | `POST /authserver/v1/tickets` | 学校账号认证并获取票据 | 2026-09-30 通过 |
| [A04](#a04) | SDGL | `GET /api/sso/callback` | 票据换取 SDGL token | 2026-09-30 通过 |
| [B01](#b01) | SDGL | `GET /api/getInfo` | 当前学校用户信息 | 2026-09-30 通过 |
| [B02](#b02) | SDGL | `GET /api/base/roomUser/selectRoomListByUserId` | 账号绑定寝室及余额 | 2026-09-30 通过 |
| [B03](#b03) | SDGL | `GET /api/base/rooms/queryRoomList` | 分页查询可见房间余额 | 2026-10-01 分页容器通过，筛选语义待验证 |
| [B04](#b04) | SDGL | `POST /api/base/roomUser/batchAdd` | 将选中的房间绑定到当前学校账号 | 2026-10-01 指定枫苑5号-402 的生产前端新增/B02/台账通过 |
| [B05](#b05) | SDGL | `GET /api/base/baseBuildings/getBuildList` | 楼栋筛选列表 | 当前页面声明与指定目标只读核验 |
| [B06](#b06) | SDGL | `GET /api/base/rooms/getAllFoolNumByBuildId` | 按楼栋取得楼层 | 当前页面声明与指定目标只读核验 |
| [B07](#b07) | SDGL | `GET /api/base/rooms/getRoomListByBuildIdAndFloor` | 按楼栋/楼层取得房间 | 当前页面声明与指定目标只读核验 |
| [B08](#b08) | SDGL | `POST /api/base/roomUser/{bruId}` + DELETE 方法覆盖头 | 删除本人学校绑定 | 指定枫苑5号-402 的生产前端/B02/台账真实删除通过 |
| [C01](#c01) | SDGL | `GET /api/base/record/queryUsageByTime` | 查询用量记录 | 有数据，日期窗口语义受限 |
| [C02](#c02) | SDGL | `GET /api/base/record/queryRecordByTime` | 查询扣费／用电记录 | 2026-09-30 返回区间内明细 |
| [C03](#c03) | SDGL | `GET /api/home/queryEleTrendByTimeType` | 统计趋势 | `timeType=0` 通过，单寝室范围未确认 |
| [D01](#d01) | SDGL | `POST /api/base/order/phonePay` | 创建电费支付订单 | 有历史接入记录；金额边界未完整验证 |
| [D02](#d02) | SDGL | `GET /api/water/order/getPayOrderReturnUrl` | 查询支付结果 | 完整响应及状态枚举待验证 |
| [D03](#d03) | SDGL | `GET /api/api/wx/pay` | 微信备用下单 | 2026-09-30 超时；单 `/api` 路径返回 404 |
| [D04](#d04) | SDGL | `GET /api/base/order/page` | 学校订单列表 | 2026-09-30 待支付查询成功、空列表 |
| [E01](#e01) | 校园支付 | `GET /zhifu/payAccept.aspx` | 支付受理页和隐藏字段 | 2026-10-01 流程验证通过 |
| [E02](#e02) | 校园支付 | `POST /zhifu/PayMain.aspx`，`btn_wx` | 确认支付页面 | 普通表单，带 `cb=on` |
| [E03](#e03) | 校园支付 | `POST /zhifu/PayMain.aspx`，`btn_wx_show` | 获取二维码地址 | 普通表单，不使用 AJAX 参数 |
| [E04](#e04) | 校园支付 | `GET /zhifu/MakeQRCode.aspx` | 下载二维码图片 | 2026-10-01 PNG 解码及显示通过 |

### 1.4 认证、超时和响应通则

**CAS 会话**：A01–A04 使用同一 HTTP Session，保存学校返回的 Cookie。Cookie 名称由学校响应决定，不要自行固定。

**SDGL 认证**：B、C、D 类接口使用 A04 获得的 token：

```http
Authorization: Bearer <SDGL_TOKEN>
User-Agent: Mozilla/5.0
```

SDGL 客户端可以使用独立 Session；认证依据是学校 Bearer token，不需要复制 CAS Cookie。应用自己的登录凭据不能代替学校 token。

**校园支付会话**：E01–E04 使用另一独立 Session，依据 `prePayId`、支付 Cookie 和最新隐藏字段连续操作，不附加 SDGL Authorization 头。

| 场景 | 参考代码超时 | 处理方式 |
| --- | --- | --- |
| CAS、普通 SDGL GET | 20 秒 | 验证码识别最多尝试 4 次，普通请求不自动重试 |
| SDGL POST 建单 | 40 秒 | 超时后先核对订单，不自动补单 |
| 房间分页 B03 | 30 秒／页 | 每次调用请求一页，分页和退避由调用端控制 |
| 校园支付 E01–E04 | 15 秒／次 | 使用同一支付 Session；失败后保留已有订单 |

这些值是 Python Requests 的 `timeout` 参数，不是学校服务承诺或业务链路的总耗时上限。

HTTP 状态和 JSON 业务 `code` 需要分别检查。HTTP 200 仍可能返回 `code=500`。参考代码在 HTTP 异常、非 JSON 响应或业务失败时抛出不包含敏感响应内容的 `SchoolAPIError`。CAS 和支付 HTML 页面按各自协议处理，不能套用普通 SDGL JSON 结构。

## 2. 统一认证

<a id="a01"></a>
### A01 初始化 CAS 登录会话

**请求**：`GET https://rz.hbue.edu.cn/authserver/login`

**用途和前置条件**：登录链路第一步，使用一个新的 Session 初始化认证页面和 Cookie；尚不需要 SDGL token。

| 参数 | 位置 | 类型 | 发送情况 | 说明 |
| --- | --- | --- | --- | --- |
| `service` | Query | string | 始终发送 | 1.2 节的完整 SERVICE 值，内嵌 URL 必须作为一个查询参数编码 |

请求结构：

```http
GET /authserver/login?service=<URL_ENCODED_SERVICE> HTTP/1.1
Host: rz.hbue.edu.cn
User-Agent: <BROWSER_UA>
```

**响应**：登录页 HTML、Cookie 或跳转。代码不解析 HTML，也没有消费 JSON 字段；Requests 默认跟随 GET 重定向。

**后续调用**：在同一个 Session 中调用 A02。仅拿到页面不能判断账号登录成功。

**失败处理**：网络错误、HTTP 异常或无法继续验证码流程时停止认证。参考超时 20 秒。

<a id="a02"></a>
### A02 获取算式验证码

**请求**：`GET https://rz.hbue.edu.cn/authserver/kaptcha`

**认证／会话**：沿用 A01 的 Session 和 Cookie。

| 参数 | 位置 | 类型 | 发送情况 | 说明 |
| --- | --- | --- | --- | --- |
| `uid` | Query | string | 始终发送 | 首次为空字符串；再次获取时用上次响应的 `uid` |

附加请求头：

```http
X-Requested-With: XMLHttpRequest
Referer: https://rz.hbue.edu.cn/authserver/login
```

首次请求结构：

```http
GET /authserver/kaptcha?uid= HTTP/1.1
Host: rz.hbue.edu.cn
X-Requested-With: XMLHttpRequest
Referer: https://rz.hbue.edu.cn/authserver/login
Cookie: <SESSION_COOKIES>
```

响应结构示意：

```json
{
  "uid": "<CAPTCHA_UID>",
  "content": "data:image/<FORMAT>;base64,<IMAGE_DATA>"
}
```

| 响应字段 | 代码期待的类型 | 用途 |
| --- | --- | --- |
| `uid` | 可作为表单值的验证码标识 | 下一次 A02 的 `uid`，以及 A03 的 `id` |
| `content` | string，Base64 Data URL | 解码图片并识别算式；实际图片 MIME 子类型未在代码里校验 |

**处理逻辑**：识别单个数字之间的 `+`、`-`、`*`、`/`、`x`、`X` 运算，给 A03 提交计算结果字符串。除法当前使用整除。最多取图并尝试 4 次；无法识别时抛出 `验证码识别失败`。这属于客户端策略，不能据此推断学校验证码规则只允许这些形式。

**失败处理**：非 JSON 或缺少 `uid/content` 时停止认证；无法识别算式时可以重新获取验证码，参考实现最多识别 4 次，每次请求超时 20 秒。

<a id="a03"></a>
### A03 提交学校账号并申请票据

**请求**：`POST https://rz.hbue.edu.cn/authserver/v1/tickets`

**编码**：`application/x-www-form-urlencoded`，不是 JSON。

**会话**：与 A01、A02 相同的 Session；使用 A02 最新的验证码 ID 和答案。

| 字段 | 位置 | 类型 | 发送情况 | 说明 |
| --- | --- | --- | --- | --- |
| `username` | Form | string | 始终发送 | 学校统一认证账号 |
| `password` | Form | string | 始终发送 | `mm_encrypt.encrypt(password)` 产生的十六进制密文，不是直接发送明文 |
| `service` | Form | string | 始终发送 | 1.2 节 SERVICE，须与 A01 保持一致 |
| `loginType` | Form | string | 发送空字符串 | 这是 CAS 表单字段；不要误写为回调查询参数里的 `mobile` |
| `id` | Form | string | 始终发送 | A02 返回的 `uid` |
| `code` | Form | string | 始终发送 | 算式计算结果，例如算式 `1+2` 的结果是 `3` |
| `otpcode` | Form | string | 发送空字符串 | 当前实现未处理动态口令流程 |

表单结构示意，各字段必须由表单编码器编码：

```text
username=<SCHOOL_USERNAME>
password=<RSA_PASSWORD_CIPHERTEXT>
service=<SERVICE>
loginType=
id=<CAPTCHA_UID>
code=<CALCULATED_ANSWER>
otpcode=
```

响应中当前消费的字段：

| 字段 | 处理方式 |
| --- | --- |
| `data.code` | 值为真时判断登录失败；这是 Python 真值判断，没有硬编码具体学校错误码 |
| `ticket` | 成功链路必须取得非空票据，交给 A04 |

最小成功结构示意：

```json
{"ticket": "<SERVICE_TICKET>"}
```

**密码加密细节**：按 `latin-1` 编码密码，每 128 字节一块，尾部补零；每块按小端序转整数，使用学校公开 RSA 模数和指数 `65537` 做模幂，将结果格式化为至少 256 位十六进制并拼接。它不等价于 RSA-OAEP 或 PKCS#1 v1.5，不能直接使用标准库默认填充模式。不能编码为 `latin-1` 的密码不受此算法实现支持。完整算法和公开公钥参数已包含在 9.2 节，不需要任何外部代码文件。

**失败处理**：`data.code` 为真时抛出 `学校账号登录失败`；没有 `ticket` 时抛出 `学校认证未返回票据`。接口超时 20 秒。实际学校错误字段全集、验证码过期时间、票据有效期未知。

<a id="a04"></a>
### A04 用 CAS 票据换取 SDGL token

**请求**：`GET https://sdgl.hbue.edu.cn/api/sso/callback`

| 参数 | 位置 | 类型 | 发送情况 | 说明 |
| --- | --- | --- | --- | --- |
| `targetUrl` | Query | URL string | SERVICE 中已有 | `https://sdgl.hbue.edu.cn/api/sso/callback` |
| `loginType` | Query | string | SERVICE 中已有 | 固定 `mobile` |
| `ticket` | Query | string | 追加发送 | A03 返回的票据 |

请求结构：

```http
GET /api/sso/callback?targetUrl=https%3A%2F%2Fsdgl.hbue.edu.cn%2Fapi%2Fsso%2Fcallback&loginType=mobile&ticket=<SERVICE_TICKET> HTTP/1.1
Host: sdgl.hbue.edu.cn
```

**响应**：代码允许连续重定向，然后从最终 `response.url` 提取 `token=...`，不是从 JSON 响应中读取 token。最终路径、重定向次数和完整查询字段没有固定契约。

最终地址结构示意：

```text
<FINAL_REDIRECT_URL_WITH_QUERY>token=<SDGL_TOKEN>&<OTHER_PARAMETERS>
```

使用 URL 查询参数解析器读取最终地址中的 `token`，避免将后续查询参数一起当成令牌。参考实现使用 `urllib.parse.parse_qs`。

**后续调用**：将 token 放入 B、C、D 类接口的 `Authorization: Bearer ...`。

**失败处理与有效期**：未找到 token 时视为认证未完成，不能继续访问业务接口。单次请求超时 20 秒。学校 token 的有效期未确认，参考实现不设置固定的有效期缓存；遇到失效响应时由调用者重新认证。

## 3. 用户与寝室余额

<a id="b01"></a>
### B01 获取当前学校用户信息

**请求**：`GET https://sdgl.hbue.edu.cn/api/getInfo`

**认证**：SDGL Bearer token。**业务参数**：无。**超时**：20 秒。

```http
GET /api/getInfo HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

所需响应字段：

```json
{
  "user": {
    "userId": "<SCHOOL_USER_ID>"
  }
}
```

| 字段 | 类型／约定 | 说明 |
| --- | --- | --- |
| `user` | object | 顶层字段，不是 `data.user` |
| `user.userId` | 可字符串化的 ID | 用于 B02 和 D01；不应直接将学号当成这个 ID |

**失败处理**：检查响应是否含对象 `user` 和非空 `user.userId`，缺失时停止后续寝室查询或建单。本文只定义接入所需字段，其他用户资料字段不作为稳定契约。

<a id="b02"></a>
### B02 获取账号绑定的寝室及余额

**请求**：`GET https://sdgl.hbue.edu.cn/api/base/roomUser/selectRoomListByUserId`

**认证**：SDGL Bearer token。先调用 B01，使用该 token 对应用户的 ID。

| 参数 | 位置 | 类型 | 发送情况 | 说明 |
| --- | --- | --- | --- | --- |
| `userId` | Query | ID | 始终发送 | B01 的 `user.userId` |

```http
GET /api/base/roomUser/selectRoomListByUserId?userId=<SCHOOL_USER_ID> HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

响应结构示意：

```json
{
  "data": [
    {
      "roomId": "<ROOM_ID>",
      "buildingName": "<BUILDING_NAME>",
      "roomNo": "<ROOM_NUMBER>",
      "meterCode": "<METER_CODE>",
      "balance": "25.50",
      "eleAmount": null,
      "daily": null
    }
  ]
}
```

| 字段 | 建议解析 | 含义与限制 |
| --- | --- | --- |
| `data` | 数组；假值转为空数组 | 学校账号绑定寝室 |
| `roomId` | 转字符串 | 学校寝室 ID，用于查询和下单 |
| `buildingName` | 缺失／空值转空字符串 | 楼栋名称 |
| `roomNo` | 空值转空字符串，再转字符串 | 房号；不要与 `roomId` 混用 |
| `meterCode` | 缺失／空值转空字符串 | 表计编码，历史接口的候选参数之一 |
| `balance` | 尝试转 float，失败为 `None` | 余额，按人民币元解释 |
| `eleAmount` | 尝试转 float，失败为 `None` | 用量候选字段，真实性和统计范围未确认，不用于可靠历史统计 |
| `daily` | 尝试转 float，失败为 `None` | 可用天数候选字段，可能为占位值，不直接用于预测 |

**使用限制**：以 `balance` 作为余额依据，不能将 `eleAmount` / `daily` 直接当作可靠用电量或剩余天数。学校是否允许查询其他 `userId` 未经验证；接入时使用当前登录账号自己的 ID。

**失败处理**：检查业务 `code` 及 `data` 数组；缺字段或结构异常时报告失败，不能误判为“没有绑定寝室”。参考超时 20 秒。

<a id="b03"></a>
### B03 分页查询房间余额

**请求**：`GET https://sdgl.hbue.edu.cn/api/base/rooms/queryRoomList`

**认证**：SDGL Bearer token。用于分页取得学校对当前账号开放的房间，实际可见范围由学校权限决定。

| 参数 | 位置 | 类型 | 当前值 | 说明 |
| --- | --- | --- | --- | --- |
| `size` | Query | integer | `1000` | 当前每页请求条数；学校最大值未知 |
| `current` | Query | integer | 从 `1` 递增 | 页码 |
| `pageTotal` | Query | integer | `1000` | 示例请求保持与 `size` 相同；具体学校语义未知，不能写成已知总页数 |

```http
GET /api/base/rooms/queryRoomList?size=1000&current=1&pageTotal=1000 HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

响应结构示意：

```json
{
  "code": 200,
  "data": {
    "pages": 2,
    "records": [
      {"roomId": "<ROOM_ID>", "balance": "25.50"}
    ]
  }
}
```

| 字段 | 代码期待的类型 | 说明 |
| --- | --- | --- |
| `code` | number | 必须严格等于数值 `200` |
| `data.pages` | number，可与页码比较 | 总页数；缺失或假值按 `1` 处理 |
| `data.records` | array | 当前页记录；缺失或假值按空数组处理 |
| `records[].roomId` | 可字符串化 ID | 房间标识 |
| `records[].balance` | number / 数字字符串 / null | 尝试转 float，失败为 `None` |
| `msg` | 未限定 | 错误时记录的学校消息 |

**分页与失败处理**：当 `current >= pages` 或本页记录为空时停止。参考函数每次只请求指定一页，超时 30 秒。连续翻页应设置间隔；网络错误由调用端决定是否退避重试，认证失败时先重新认证。

**限制**：该请求没有目标寝室筛选参数，可能涉及当前账号可见的整张房间列表。仅查询自己绑定寝室时优先使用 B02，避免不必要的全量翻页。学校发布的限流阈值和最大每页条数未知。

**2026-10-01 补充核验**：使用当前账号发出一次不带业务参数的 GET，返回 HTTP 200、业务 `code=200`，`data` 包含 `records/total/size/current/pages` 等分页字段。本次只确认接口和分页容器可用，没有验证全量数据、筛选精度及账号可见范围。

学校移动端当前绑定页面实际会发送 `size/current/pageTotal/roomId/searchValue`。页面的初始分页值为 `size=10,current=1,pageTotal=100`；响应后将 `pageTotal` 更新为 `data.total`。`roomId` 来自选择房间的页面参数，`searchValue` 来自搜索输入。因此前述“没有目标寝室筛选参数”仅描述旧参考函数，不代表学校接口不支持筛选；筛选字段的服务端语义仍待定向验证，不可把传参本身视为过滤已经生效。

<a id="b04"></a>
### B04 绑定寝室：学校当前页面使用的写接口

**核验日期**：2026-10-01。**证据级别**：学校已发布的移动端请求声明及保存按钮调用链；本次完成账号登录、B02 和 B03 的只读请求，未新增或删除真实绑定关系。

**请求**：`POST https://sdgl.hbue.edu.cn/api/base/roomUser/batchAdd`。

**认证与编码**：当前账号的 SDGL Bearer token；JSON 请求体。公共请求函数将 `baseUrl=https://sdgl.hbue.edu.cn/api` 与相对路径拼接，并将 `data` 传给 `uni.request`。

```http
POST /api/base/roomUser/batchAdd HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
Content-Type: application/json

{
  "roomUsers": [
    {
      "roomId": "<ROOM_ID_FROM_B03>",
      "userId": "<CURRENT_SCHOOL_USER_ID>",
      "<OTHER_FIELDS_FROM_B03_RECORD>": "<ORIGINAL_VALUE>"
    }
  ]
}
```

`<OTHER_FIELDS_FROM_B03_RECORD>` 是结构占位说明，不能作为实际 JSON 字段发送。学校页面不是只提交两个 ID，而是将 B03 选中记录的整个对象加入数组，并覆盖其中的 `userId`：

```javascript
// 学校页面行为的等价摘录，不含真实账号或房间数据。
const roomUsers = selectedRecords.map(record => ({
  ...record,
  userId: currentSchoolUser.userId
}));
batchAdd({ roomUsers });
// batchAdd: request({url: '/base/roomUser/batchAdd', method: 'post', data})
```

| 参数 | 来源 | 约束与已知边界 |
| --- | --- | --- |
| `roomUsers` | 选中的 B03 记录数组 | 学校页面在提交前要求恰好选择 1 个房间；不代表账号累计只能绑定 1 个 |
| `roomUsers[].roomId` | B03 的选中记录 | 不能使用楼栋名称、房号或本应用 UUID 代替 |
| `roomUsers[].userId` | B01 的 `user.userId` | 服务端依据当前用户填入，禁止接受前端指定其他学校用户 |
| 其他记录字段 | B03 的同一条记录 | 页面原样携带；最小必填字段集合尚未通过写请求验证 |

**响应判断**：页面仅在 `response.code == 200` 时显示“添加成功”。缺少本次真实写入的完整成功响应样本，因此不声明 `data` 的类型、返回关系 ID 或重复绑定的行为。业务成功后必须再次调用 B02，确认目标 `roomId` 已出现在当前账号列表中，保存 B02 返回的 `bruId`（若有）作为绑定关系标识。

**同名接口辨别**：主包还声明了 `roomUseradd → POST /base/roomUser/add`，参数通过 `params` 放入 URL 查询串；但当前 `/pages/bindingAccount/accountbind` 保存按钮实际调用的是 `batchAdd`。不能把仅存在的 `/add` 声明误写成当前绑定页面的主路径，也不能在超时后自动尝试另一个写接口。

**接入建议**：后端向前端返回经过精简的候选房间及短期 `candidate_id`，完整 B03 候选记录只在后端短期保管。提交绑定时校验候选属于当前用户搜索会话，重新确认目标房间，覆盖 `userId`，通过上述 JSON 写接口提交；不要信任浏览器回传的完整学校记录。默认寝室是本应用偏好，与学校绑定是两件事。

**重试及结果不确定**：POST 发送后的超时、断连或 5xx 不能证明绑定没有发生。先用 B02 查询目标关系；已存在则完成本地同步，查询失败则保留 `unknown/reconciling`。未验证学校幂等和列表一致性前，不自动重发绑定，不通过解绑再绑定来“修复”。

**可追溯来源**：

- [学校移动端主包](https://sdgl.hbue.edu.cn/mobile/static/js/index.11d65048.js)：`batchAdd`、`roomUseradd`、公共请求函数及基础地址；SHA-256 `b082587be99e6dcede70f4570931c1c24d30b81c35b4035c496d21abf519e71d`。
- [绑定页面](https://sdgl.hbue.edu.cn/mobile/static/js/pages-bindingAccount-accountbind.80ce137c.js)：`baocun`、`chaxun`、单次选择限制及请求体；SHA-256 `f03f31426d7131f49bc30a809499d5c5abff52173c3d36e07af7255736b59201`。
- [绑定列表页面](https://sdgl.hbue.edu.cn/mobile/static/js/pages-bindingAccount-index.0a617094.js)：使用 B02 查询绑定；解绑操作使用关系 `bruId`，不能把它与 `roomId` 混用。解绑不在本次新增接口范围内。

上述脚本名称随学校发版可能变化；路径或结构改变时重新定位调用链。本节为对原接入文档的补充，不把静态调用链核验写成真实绑定验收通过。


<a id="b05"></a>
### B05 楼栋筛选列表 getBuildList

**请求**：`GET https://sdgl.hbue.edu.cn/api/base/baseBuildings/getBuildList`，当前学校账号 Bearer 认证。

| Query | 类型 | 学校页面使用值/来源 |
| --- | --- | --- |
| `size` | integer | `999` |
| `current` | integer | `1` |
| `searchValue` | string | 本系统固定空字符串；前端在返回列表内搜索 |

业务 code 为整数 200，`data.records` 为 `{label,value}` 数组，`data.total` 为总数。label 是楼栋名称，value 是学校楼栋 ID，禁止用名称代替 ID。本系统检查完整列表和 999 条上限，不把部分结果当完整筛选列表。

<a id="b06"></a>
### B06 楼层筛选列表 getAllFoolNumByBuildId

**请求**：`GET https://sdgl.hbue.edu.cn/api/base/rooms/getAllFoolNumByBuildId`。

| Query | 类型 | 来源 |
| --- | --- | --- |
| `buildingId` | string | B05 选中的 value |
| `searchValue` | string | 本系统固定空字符串 |

业务 code 200，`data` 为 `{label,value}` 数组。学校页面使用 `value.split('-')[0]` 取得 floorNum，本系统按相同行为解析，不把显示文字“4层”作为学校参数。

<a id="b07"></a>
### B07 房间筛选列表 getRoomListByBuildIdAndFloor

**请求**：`GET https://sdgl.hbue.edu.cn/api/base/rooms/getRoomListByBuildIdAndFloor`。

| Query | 类型 | 来源 |
| --- | --- | --- |
| `buildingId` | string | B05 选中的 value |
| `floorNum` | string | B06 解析后的楼层值 |
| `searchValue` | string | 本系统固定空字符串 |

业务 code 200，`data` 为 `{label,value}` 数组，value 为学校 roomId。选择后按 B03 `roomId=<value>` 再核对完整候选，只接受与该 ID 一致的记录。B05–B07 只返回 ID/名称，不公开其他住户资料；B03 完整记录在 Adapter 加密缓存，受理后加密保存于台账。

**2026-10-01 证据与范围**：学校 `pages/module/search` 为楼栋 → 楼层 → 房间三级选择，绑定页面接收 roomId。脚本 [pages-module-search.cd6846bf.js](https://sdgl.hbue.edu.cn/mobile/static/js/pages-module-search.cd6846bf.js)，SHA-256 `efc39c0ee773001cbca2ded59637ac8395865ee1648d892986128ac0d8b7206c`；请求声明在前述主包。指定账号只读实测唯一定位到枫苑5号、4 层和 402，B03 roomId 返回唯一匹配、楼栋/房号一致，B02 当时尚无该目标。用户说明直接搜索无效，正式前端改为筛选配合当前列表内搜索，不把非空 searchValue 当作已验证精确搜索。

实际新增 B04 在台账与容器验证后单独执行并记录；本节只读证据不表示已完成新增绑定。

<a id="b08"></a>
### B08 学校页面解绑 roomUserremove

**当前页面实际请求**：`POST https://sdgl.hbue.edu.cn/api/base/roomUser/{bruId}`，带当前学校 Bearer token 和 `X-HTTP-Method-Override: DELETE`。没有业务 JSON 请求体。

学校绑定列表页 `jiebang` 冻结选中关系，确认按钮调用 `roomUserremove([selected.bruId])`；单元素数组拼为路径中的 bruId。主包的 request 声明是 POST + 方法覆盖头。另有 `deleteRoomUser` 的直接 DELETE 声明，本系统遵循当前页面主路径，不把其他写接口作为超时后的备用。

| 参数 | 来源 | 约束 |
| --- | --- | --- |
| 路径 bruId | 本人 B02 的绑定关系 ID | 与 roomId/本应用 Binding UUID 区分；不接受浏览器给出学校 ID |
| Authorization | 当前学校账号 token | 由 Adapter 保管 |
| X-HTTP-Method-Override | 固定 DELETE | 与页面行为一致 |

先校验本应用本人目标和持久凭据版本，再查询 B02 核对同一关系；关系 ID 变化时要求同步，不删除后来新建的关系。首次发送前登记 dispatched；超时/断连/5xx 或重启只回查 B02，不重复 POST。明确业务拒绝终结；code 200 本身不表示关系已消失。连续两次成功缺席、数据库时间至少间隔 2 秒后才确认；一次空列表、查询失败或重新出现都会阻止/重置确认。10 分钟未确认转 unknown，保留目标屏障。

默认目标先建立监控 retarget-to-null 屏障；本地关系 inactive、清空默认与审计 Outbox 同事务，再由 Monitoring 读取偏好证明确认。默认删除后不擅自选择其他寝室，监控等待明确的新默认；关闭意图和已采集历史保留。非默认删除保持原默认与监控目标。

来源：[绑定列表页](https://sdgl.hbue.edu.cn/mobile/static/js/pages-bindingAccount-index.0a617094.js)，SHA-256 `5ecd47fc6bf85992fc1e11e81d25e77101c09fc6bdca2716a621863d1a7ad769`，及 B04 所列主包。本轮 MySQL/合成学校已验证单次写入、缺席/重现、unknown、关闭与默认恢复；用户指定枫苑5号-402 做真实删除，尚待完成该结果验证。

## 4. 历史用电与统计趋势

这三个接口的参数、日期格式和响应结构不同，不能共用一套请求参数或解析规则。业务 `code=200` 不等于日期范围已完整验证。

<a id="c01"></a>
### C01 查询用电记录 queryUsageByTime

**请求**：`GET https://sdgl.hbue.edu.cn/api/base/record/queryUsageByTime`

**认证**：SDGL Bearer token。**超时**：当前客户端 20 秒。

本次成功返回数据的参数组合：

| 参数 | 位置 | 类型 | 已验证的值／格式 | 说明 |
| --- | --- | --- | --- | --- |
| `buildId` | Query | string | 绑定寝室的 `roomId` | 在本次返回数据中，每条 `buildId` 均与请求一致 |
| `startTimeStr` | Query | string | `2026-09-29`，格式 `yyyy-MM-dd` | 可影响返回日期；不能直接解释为区间下界 |
| `endTimeStr` | Query | string | `2026-09-30`，格式 `yyyy-MM-dd` | 本次改变它未改变同一 `startTimeStr` 的结果，具体作用未确认 |

```http
GET /api/base/record/queryUsageByTime?buildId=<ROOM_ID>&startTimeStr=2026-09-29&endTimeStr=2026-09-30 HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

**实测的日期行为**：

| startTimeStr | endTimeStr | 结果 |
| --- | --- | --- |
| `20260928` | `20260930` | `code=500`，日期解析异常 |
| `2026-09-28` | `2026-09-30` | `code=200`，3 条记录；首条 `statTime=20260926`，早于请求开始日期 |
| `2026-09-29` | `2026-09-29` | `code=200`，日期为 `20260927`、`20260928`、`20260929` |
| `2026-09-29` | `2026-09-30` | `code=200`，仍为 `20260927`、`20260928`、`20260929` |
| `2026-09-01` | `2026-09-03` | `code=200`，空数组 |

本次样本呈现“围绕 `startTimeStr` 返回最多近三天记录”的特征，但不足以确立学校服务端算法或最大范围。**不要将本接口直接用作任意起止日期的完整历史查询**；逐条校验 `statTime`，也不要把空数组解释为零用电。

响应结构示意（数值为示例）：

```json
{
  "code": 200,
  "msg": "操作成功",
  "data": [
    {
      "buildId": "<ROOM_ID>",
      "statTime": "20260929",
      "yearly": "2026",
      "monthly": "9",
      "dayly": "29",
      "energyUsage": "2.50",
      "price": "0.60",
      "needAmount": "1.50",
      "trueAmount": "1.50",
      "beforeAmount": "30.00",
      "afterAmount": "28.50",
      "time": ""
    }
  ]
}
```

| 字段 | 本次观察类型 | 解析说明 |
| --- | --- | --- |
| `data` | array | 直接是记录数组 |
| `statTime` | string，`yyyyMMdd` | 实际记录日期，转为日期时用 `%Y%m%d` |
| `yearly` / `monthly` / `dayly` | string | 年、月、日分量；字段确实叫 `dayly`，不是 `daily` |
| `energyUsage` | 数字字符串 | 电能用量，通常按 kWh 展示；以学校电表和计价口径为准 |
| `price` | 数字字符串 | 价格字段；完整计价规则未验证 |
| `needAmount` / `trueAmount` | 数字字符串 | 应扣／实扣金额字段；含义按命名及扣费页面理解，完整扣费规则未验证 |
| `beforeAmount` / `afterAmount` | 数字字符串 | 扣费前／后金额候选字段；不能直接当成当前实时余额 |
| `buildId` | string | 本次样本与请求寝室 ID 一致 |
| `time` / `createTime` | string | 本次首条样本为空，不可用作日期来源 |
| `balance` | 可空字段 | 本次检查的返回记录没有非空余额，不能承诺返回余额历史 |

**接入注意**：

- `roomId + beginDate + endDate + meterCode` 组合在 2026-09-30 返回业务 `code=500`，不要使用这组参数代替上表。
- 日期应读取 `statTime`，用量应读取 `energyUsage`；不能只尝试 `recordDate`、`usageNum` 等不匹配字段。
- 不要假设按 10 天分段即可取得完整历史，也不要仅依据记录条数判断日期范围完整。

**失败处理**：检查 HTTP、业务 `code`、`data` 类型后再处理记录。原始响应中的错误消息可能包含请求值，应脱敏后记录。当前学校参数错误经常以 HTTP 200 + `code=500` 返回。

<a id="c02"></a>
### C02 查询扣费与用电记录 queryRecordByTime

**请求**：`GET https://sdgl.hbue.edu.cn/api/base/record/queryRecordByTime`

**认证**：SDGL Bearer token。**超时**：20 秒。

学校当前移动端页面与本次成功请求均使用：

| 参数 | 位置 | 类型 | 已验证的值／格式 | 说明 |
| --- | --- | --- | --- | --- |
| `buildId` | Query | string | 绑定寝室的 `roomId` | 页面从账号绑定寝室选择器取得 |
| `startTimeStr` | Query | string | `20260928`，格式 `yyyyMMdd` | 开始日期 |
| `endTimeStr` | Query | string | `20260930`，格式 `yyyyMMdd` | 结束日期 |

```http
GET /api/base/record/queryRecordByTime?buildId=<ROOM_ID>&startTimeStr=20260928&endTimeStr=20260930 HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

本次返回 2 条记录，日期为 `2026-09-29`、`2026-09-28`，均落在请求区间内。没有测试日期上限、区间边界包含规则或最大跨度，不能将缺失的 9 月 30 日记录直接补零。

响应结构示意：

```json
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "dailyDaily": 0.0,
    "dailyAmount": 0.0,
    "recordDaily": 2.5,
    "recordAmount": 1.5,
    "list": [
      {
        "time": "2026-09-29",
        "statTime": "20260929",
        "energyUsage": "2.50",
        "trueAmount": "1.50",
        "lastReading": "100.00",
        "reading": "102.50",
        "trueAmountName": "<学校返回的扣费状态文案>",
        "beforeAmount": null,
        "afterAmount": null
      }
    ]
  }
}
```

| 字段 | 本次观察／学校页面用法 | 说明 |
| --- | --- | --- |
| `data.list` | array | 实际记录数组 |
| `data.dailyDaily` / `dailyAmount` | number | 学校页面读取的汇总字段，不能仅按名字推断精确统计范围 |
| `data.recordDaily` / `recordAmount` | number | 学校页面读取的汇总字段；明细与汇总关系需另行核验 |
| `list[].time` | string，`yyyy-MM-dd` | 页面显示“时间”；本次有值，可优先解析 |
| `list[].statTime` | string，`yyyyMMdd` | 同一记录的紧凑日期，可作为替代来源 |
| `list[].energyUsage` | 数字字符串 | 页面显示“用量” |
| `list[].trueAmount` | 数字字符串 | 页面显示“扣费金额” |
| `list[].trueAmountName` | 页面显示文案 | 页面显示“是否扣费”；状态全集未验证 |
| `list[].lastReading` / `reading` | 数字字符串 | 页面显示“起码／止码”，即前后读数 |
| `list[].beforeAmount` / `afterAmount` | 本次为 null | 本次不能据此取得历史余额 |
| `list[].balance` | 可空字段 | 本次记录中没有非空余额 |
| `list[].buildId` | 通用响应对象字段 | 本次不等于请求 ID，不应依赖它回填寝室标识；请求范围依据学校页面传入的 `buildId`，没有做跨账号权限验证 |

**接入注意**：`roomId/current/size/meterCode` 组合在 2026-09-30 返回业务 `code=500`。使用上表日期字段及 `buildId`，不要以分页参数代替日期。成功响应从 `data.list` 读取，并使用 `time/statTime/energyUsage` 解析；不要将 `eleAmount` 误作余额。

<a id="c03"></a>
### C03 查询统计趋势 queryEleTrendByTimeType

**请求**：`GET https://sdgl.hbue.edu.cn/api/home/queryEleTrendByTimeType`

**认证**：SDGL Bearer token。**超时**：20 秒。

| 参数 | 位置 | 类型 | 学校前端值 | 说明 |
| --- | --- | --- | --- | --- |
| `timeType` | Query | integer | `0` 日、`1` 月、`2` 年 | 当前前端用日／月／年选项的索引值；本次实测 `0` 成功 |

学校 `pages-work-index` 页面只传 `timeType`，不传 `roomId`、`buildId` 或 `meterCode`。

```http
GET /api/home/queryEleTrendByTimeType?timeType=0 HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

响应结构示意：

```json
{
  "code": 200,
  "msg": "<学校返回的汇总字符串>",
  "data": [
    {"key": "<横坐标标签>", "value": "2.50"}
  ]
}
```

| 字段 | 已知含义 |
| --- | --- |
| `data` | 数组，本次 `timeType=0` 返回 30 个点 |
| `data[].key` | 学校页面的横坐标分类标签；不能假定都是完整 `yyyy-MM-dd` 日期 |
| `data[].value` | 数字字符串，页面转成数值绘制用电趋势 |
| `msg` | 此接口的学校页面将它赋给汇总值 `sum`，不是统一的“操作成功”文本 |

**范围限制**：这是工作台统计图接口。当前前端调用没有寝室参数，本次也未验证它的账号／楼栋／全校统计范围，**不能把这些点写入某个寝室的历史用电表**。即便额外附加 `roomId`，也没有证据证明服务端会按该字段过滤。

**接入注意**：`timeType=day` 在 2026-09-30 返回业务 `500` 参数错误。使用数字枚举，并按 `key/value` 解析趋势；它不能直接套用 C01/C02 的寝室明细解析器。

## 5. 学校电费订单

<a id="d01"></a>
### D01 主路径：创建电费微信支付订单

**请求**：`POST https://sdgl.hbue.edu.cn/api/base/order/phonePay`

**认证**：SDGL Bearer token。**编码**：JSON。**超时**：40 秒。该接口名称含 `phonePay`，实际当前用途是电费充值，不应据此命名为“话费充值”。

| 字段 | 类型 | 参考客户端发送值 | 来源／含义 |
| --- | --- | --- | --- |
| `userId` | ID | B01 的学校用户 ID | 不是学号或调用方应用的用户 ID |
| `buildId` | string | 目标寝室 `roomId` | 学校当前充值页面使用的房间参数 |
| `orderType` | integer | `0` | 当前电费场景 |
| `payMethod` | integer | `1` | 当前微信场景 |
| `orderAmount` | number | 充值金额，元 | 与 `amount` 保持相同 |
| `roomId` | string | 与 `buildId` 相同 | 兼容字段；学校当前页面的主路径表单未发送它 |
| `amount` | number | 与 `orderAmount` 相同 | 兼容字段；学校当前页面未发送它 |
| `tradeType` | string | `NATIVE` | 示例发送；学校页面调用 `phonePay` 时未发送它 |

参考请求结构：

```http
POST /api/base/order/phonePay HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
Content-Type: application/json

{
  "userId": "<SCHOOL_USER_ID>",
  "roomId": "<ROOM_ID>",
  "buildId": "<ROOM_ID>",
  "orderType": 0,
  "payMethod": 1,
  "orderAmount": 1,
  "amount": 1,
  "tradeType": "NATIVE"
}
```

学校页面的主路径只发送 `{userId, buildId, orderType, payMethod, orderAmount}`；表中额外字段是参考客户端的兼容写法。最小字段组合和全部参数边界没有单独完成验证。

已知响应结构：

```json
{
  "code": 200,
  "data": "http://cwcwx.hbue.edu.cn/zhifu/payAccept.aspx?prePayId=<PREPAY_ID>"
}
```

| 字段 | 约定 |
| --- | --- |
| `code` | 成功值为数值 `200` |
| `data` | 支付页面 URL 字符串，不是二维码图片、不是订单对象 |
| `msg` | 失败时的学校消息，具体错误码和文案全集未知 |

**订单标识**：从支付 URL 中提取字母数字组成的 `prePayId`，作为 `order_id` / `orderId` 保存并用于后续查询。学校 SDGL 内部单号和校园支付 `prePayId` 是否始终一一对应尚未确认。

**调用限制与幂等性**：这是真实建单接口，HTTP 超时不能证明学校未建单。Python 示例限制整数 1–500 元，这是示例的调用限制，不是学校官方上限。学校幂等机制未确认，接入方应独立实现重复提交控制，失败后先核对订单。

**失败处理**：非 `200`、`data` 非 HTTP URL 或 URL 主机不在参考客户端允许列表时抛出错误。允许列表为 `cwcwx.hbue.edu.cn`、`sdgl.hbue.edu.cn`、`pay.hbue.edu.cn`。该列表表示客户端接受规则，不表示所有主机都经过本次可用性验证。

**示例返回值**：Python `phone_pay` 将学校响应整理成 `{pay_url, prepay_id}`，这是参考客户端构造的对象。学校原始 `data` 仍为支付链接字符串，二维码需通过 E01–E04 取得。

<a id="d02"></a>
### D02 查询支付结果

**2026-10-04纠正：此接口属于水费。** 学校移动端成功页`pages-topUpPayment-CN-RechargedSuccessfully.fb39d992.js`对电费调用`/base/order/getRoomInfoByOrderId`，后者返回寝室信息而非已确认支付状态。本系统电费确认改用D04与原支付票据证据，详见[0.18.2规则](decisions/电表读数与缴费结果确认.md)。以下保留早期参考接口记录，不作为电费状态实现依据。

**请求**：`GET https://sdgl.hbue.edu.cn/api/water/order/getPayOrderReturnUrl`

**认证**：SDGL Bearer token，使用下单时同一个学校账号。**超时**：20 秒。

| 参数 | 位置 | 类型 | 发送情况 | 说明 |
| --- | --- | --- | --- | --- |
| `orderId` | Query | string | 始终发送 | 示例传入 D01 支付链接提取的 `prePayId` |

```http
GET /api/water/order/getPayOrderReturnUrl?orderId=<ORDER_ID> HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

**响应**：业务 `code == 200` 后读取 `data`。尚缺完整成功样本，不能保证 `data` 一定是对象，也不能仅按接口名推断必然返回 URL；Python 参考实现原样返回 `data`。

如果后续取得对象形式的 `data`，以下字段和值可作为核对线索；未经实际订单验证前，不应直接用于自动记账：

| 内容 | 当前识别规则 |
| --- | --- |
| 候选字段 | 依次检查 `payStatus`、`status`、`orderStatus`、`payStatusStr` |
| 已支付 | `"2"`、`2`、`"SUCCESS"`、`"PAID"`、`"已支付"`、`"支付成功"` |
| 待支付 | `"0"`、`0`、`"UNPAID"`、`"未支付"`、`"待支付"` |
| 其他情况 | 保留为未知，不能自动认定已支付 |

这些候选值**不是已确认的学校官方状态枚举**，Python 参考实现不会据此自动标记到账。尚未完成已支付／未支付样本的完整验证。

**失败处理**：业务 `code != 200` 抛出 `查询支付结果失败`；只有确认已支付才能标记到账，HTTP 200、二维码生成、用户打开支付页均不能替代支付结果。

<a id="d03"></a>
### D03 微信备用下单 wx/pay（未验证可用）

**学校当前前端构造的请求**：`GET https://sdgl.hbue.edu.cn/api/api/wx/pay`

这个重复的 `/api/api` 来自学校前端：公共 `baseUrl` 是 `https://sdgl.hbue.edu.cn/api`，`wxpay` 声明却是 `url: "/api/wx/pay"`，请求函数直接拼接两者。这是学校页面的请求拼接行为，不表示该路径可用。不要将两个路径作为自动建单重试的候选地址。

**认证**：SDGL Bearer token。**方法**：GET，即使是 GET 也可能建单。

| 参数 | 位置 | 类型／值 | 学校前端来源 |
| --- | --- | --- | --- |
| `userId` | Query | 学校用户 ID | 当前登录用户 |
| `buildId` | Query | 绑定寝室的 `roomId` | 充值页面所选寝室 |
| `orderType` | Query | `0` | 电费 |
| `payMethod` | Query | `1` | 微信 |
| `orderAmount` | Query | 金额，元 | 本次使用 `1` |
| `tradeType` | Query | `NATIVE` 或 `MWEB` | 学校前端在企业微信环境使用 `MWEB`，其他环境使用 `NATIVE`；本次只验证 `NATIVE` |

请求结构：

```http
GET /api/api/wx/pay?userId=<SCHOOL_USER_ID>&buildId=<ROOM_ID>&orderType=0&payMethod=1&orderAmount=1&tradeType=NATIVE HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

**2026-09-30 验证结果**：

| 实际请求路径 | 结果 | 可得结论 |
| --- | --- | --- |
| `/api/api/wx/pay` | 等待 20 秒后 `ReadTimeout` | 没有取得响应数据、订单号或二维码；不能确认后端是否执行过建单 |
| `/api/wx/pay` | HTTP `404` | 此时该地址不可用；响应为 `timestamp/status/error/path` 错误对象 |

两个路径各尝试一次，没有对超时路径连续重试。查询当前绑定寝室当日 `payStatus=0` 的订单列表返回空数组，详见 D04；这不能作为“服务器绝对没有创建任何订单”的保证。

**已知响应信息**：学校前端的 `MWEB` 分支在 `code=200` 时消费 `data.mwebUrl`；其 `NATIVE` 分支没有展示明确的二维码处理逻辑。本次没有成功的 NATIVE 响应，所以不能编造 `code_url`、`codeUrl`、二维码图片字段或可用的返回样例。

**结论**：2026-09-30 未能取得此备用接口的二维码。D01 + E01–E04 是另一条支付链路，其二维码成功不能作为 D03 可用的证明。

**2026-10-05 MWEB 定向试验**：按用户指定的本人绑定寝室、1.00 元，通过项目 `auth.txt` 的正式学校认证/验证码协议取得身份；B02 返回两条绑定，按用户指定目标唯一匹配。调用前 D04 待支付查询（2026-09-30 至 2026-10-05）为空，只请求一次学校前端声明的 `GET /api/api/wx/pay`，传入 `tradeType=MWEB`、本人 userId/目标 buildId、电费和微信参数。采用 Android 浏览器 User-Agent 与学校 mobile Referer，保留 TLS 校验、固定学校出口和零重试；等待响应 30 秒后 `ReadTimeout`，未获得 HTTP 状态、业务响应或 `mwebUrl`。随后的 D04 待支付记录仍为空，不能证明未建单；本次结果保留 unknown，不再尝试另一条路径、NATIVE 或 D01。没有发起付款，也未进行真机唤起。分类记录见[移动支付试验](acceptance/school/2026-10-05-mobile-payment.json)。

本轮只读核对学校公开 `pages-topUpPayment-CN-details.0ae21658.js`：`wxZF()` 的企业微信分支使用 MWEB/mwebUrl，但该文件的“确认支付”按钮绑定 `quzhifu()`，实际走 phonePay；MWEB 回跳域名还写为 `sdgl.hzau.edu.cn`，不能据这段静态分支认定本校 H5 已接通。微信官方[Native 常见问题](https://pay.wechatpay.cn/doc/v3/partner/4013352076)明确不支持点击 code_url 调起支付；增加手机一键付款按钮须先取得有效的[H5 链接及支付域名配置](https://pay.wechatpay.cn/doc/v3/merchant/4012791835)，或由学校提供微信内 JSAPI 所需参数。当前正式二维码和自动查单行为不变。

**2026-10-05 用户要求继续后的补充**：经同一账号认证、目标匹配和待支付查询，再请求一次 `/api/wx/pay` 的 MWEB，实际返回 HTTP 404，没有链接；前后待支付列表仍为空。随后对同一指定寝室、1.00 元执行一次学校当前使用的 D01/phonePay，HTTP/业务码均为 200，取得原支付 URL；E02、E03 各一次后成功取得并在内存解码原生 `weixin://wxpay/` 二维码。对该原单 E01 分别使用安卓、iPhone、微信、企业微信 User-Agent 只读访问，均为 HTTP 200/扫码流程，没有发现 JSAPI 或 H5 参数；这只是请求标识对照，不是真机验收。原生 scheme 和 [Android Intent](https://developer.chrome.com/docs/android/intents) 两种按钮已放入仅本机 WLAN 可访问的临时诊断页，复用同一二维码、不再建单，等待用户手机实测。Intent 只尝试把相同 URI 交给微信，不保证微信支持该付款方式。本次学校票据、页面与会话均仅保留在 Git 忽略目录的 Windows 用户级 DPAPI 密文中；未付款，未接入正式页面。最初超时的 MWEB 结果仍为 unknown，不因 D01 成功而消除。

**本次安卓真机反馈**：用户在安卓系统浏览器/Chrome 点击付款按钮，出现打开微信确认，但确认后没有打开；同一页面新增 `weixin://` 不带订单的对照按钮后，用户确认能正常打开微信，服务端仅分类记录为 Android/Chrome family。已在内存核对网页实际 href 与二维码解码内容完全一致，Intent 保留原 URI，未引入空白或 fragment；因此基本排除当前 IP 页面阻断全部外部跳转和测试页地址编码错误，问题集中在 Native 付款 URI 的处理。本次未走 H5，不能把该现象归因为商户 H5 支付域名配置；没有取得可用收银台，不作为手机支付成功验收。

**完整手机头与源码核对**：按用户追加要求，同一原单E01–E04均使用手机UA及移动标识，四步200、得到新Native码；用户重试仍为确认后未打开。直接下载主包、vendor及55个页面分包（共57份JS），确认唯一MWEB业务调用在未被确认按钮调用的wxZF方法，完整URL来自baseUrl与/api/wx/pay直接相加；没有JSAPI业务调用。逐项证据、源码定位和范围见[手机微信支付源码排查](decisions/手机微信支付源码排查.md)。

<a id="d04"></a>
### D04 查询学校电费订单列表

2026-10-07真实只读补验：省略payMethod可返回学校可见的多个渠道，近30天共17笔、实缴312.40元，渠道代码1/2/3；同范围payMethod=1只返回15笔。新增缴费列表使用不限渠道请求和payAmount精确合计。单查2026-10-05返回2笔且缴费日均为当天；创建日/支付日不同的边界仍未覆盖。生产解析与分类证据见[缴费列表规则](decisions/学校缴费明细列表.md)及[本次真实检查](acceptance/school/2026-10-07-payment-history.json)。不为代码2/3猜测渠道名称。

2026-10-04已取得本人真实明细：orderId为19位字符串，userId/buildId/orderAmount/payAmount/createdTime/payTime均为字符串；已支付payStatus="2"、电费orderType="0"、微信payMethod="1"，tradeOrderNo本次为空。D01的64位prePayId不等于此orderId。原票据付款后E01的可见完整提示为“该订单已支付，无法再次交易,请返回系统重新发起交易”；与唯一本人/寝室/金额/建单后D04记录一起确认原单，不能单凭同金额匹配。指定1元及余额增量证据见[分类记录](acceptance/school/2026-10-04-meter-payment.json)。后文空数组为2026-09-30的历史结果。

**请求**：`GET https://sdgl.hbue.edu.cn/api/base/order/page`

**用途**：查询指定寝室的电费订单，可用于缴费记录展示及超时后的订单核对。

**认证**：SDGL Bearer token。仅查询当前账号绑定寝室。**本次超时设置**：20 秒。

| 参数 | 位置 | 类型／示例 | 说明 |
| --- | --- | --- | --- |
| `buildId` | Query | `<ROOM_ID>` | 学校绑定寝室 ID |
| `startTimeStr` | Query | `2026-09-30` | 开始日期，`yyyy-MM-dd` |
| `endTimeStr` | Query | `2026-09-30` | 结束日期，`yyyy-MM-dd` |
| `current` | Query | `1` | 第一页 |
| `size` | Query | `10` | 每页条数 |
| `pageTotal` | Query | `100` | 学校页面初始值；响应之后页面使用 `data.total` 更新 |
| `orderType` | Query | `0` | 电费 |
| `payMethod` | Query | `1` | 微信 |
| `payStatus` | Query | `0` | 本次查待支付；学校缴费记录页面使用 `2` 查已支付。其他值未核验 |

```http
GET /api/base/order/page?buildId=<ROOM_ID>&startTimeStr=2026-09-30&endTimeStr=2026-09-30&current=1&size=10&pageTotal=100&orderType=0&payMethod=1&payStatus=0 HTTP/1.1
Host: sdgl.hbue.edu.cn
Authorization: Bearer <SDGL_TOKEN>
```

响应结构：

```json
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "records": [],
    "total": 0,
    "size": 10,
    "current": 1,
    "pages": 0
  }
}
```

本次确认了分页容器字段，`records` 为 0 条。因为没有返回订单明细，不为 `records[]` 臆造订单号、金额、状态等明细结构。此查询的可见性、日期包含规则、订单落库延迟及失败订单是否可见都没有完整验证，空列表只能说明此筛选条件下当时没有可见记录。

## 6. 校园支付页面与二维码

E01–E04 是 **D01 返回校园支付链接之后**的 ASP.NET 页面链路，与 D03 的微信备用下单接口不是同一条链路。

2026-10-01 已使用已有 `prePayId` 完成这条链路的真实二维码获取、浏览器解码和显示，样本为 133 × 133 PNG；该验证未重新调用 `phonePay`，也未扫码付款。

下面完整说明已验证的页面流程；对应 Python 参考实现见 9.5 节。Python 版本已做语法与离线流程验证，尚未单独完成线上验收。

<a id="e01"></a>
### E01 获取支付受理页

**请求**：`GET http://cwcwx.hbue.edu.cn/zhifu/payAccept.aspx`

**前置条件**：D01 返回支付链接，并从中取得 `prePayId`。使用独立 Session，以便后续 E02、E03 保留 Cookie。

| 参数 | 位置 | 类型 | 发送情况 | 说明 |
| --- | --- | --- | --- | --- |
| `prePayId` | Query | string | 始终发送 | D01 支付链接中的预支付标识 |

```http
GET /zhifu/payAccept.aspx?prePayId=<PREPAY_ID> HTTP/1.1
Host: cwcwx.hbue.edu.cn
User-Agent: <BROWSER_UA>
```

**响应**：HTML。提取所有 `<input type="hidden" ...>` 的 `name` 和 `value`，留给 E02 提交；其中必须取得 `__VIEWSTATE`。其他返回的隐藏字段也应原样保留，不要只硬编码几个字段名。

HTML 结构示意：

```html
<input type="hidden" name="__VIEWSTATE" value="<CURRENT_VIEWSTATE>">
```

**失败处理**：请求前验证 `prePayId`，检查 HTTP 状态及 `__VIEWSTATE`，不满足时报告错误。缺少页面状态不能单独证明订单过期，需打开原支付页核对。参考超时 15 秒。

<a id="e02"></a>
### E02 普通表单提交，进入微信支付主页面

**请求**：`POST http://cwcwx.hbue.edu.cn/zhifu/PayMain.aspx?prePayId=<PREPAY_ID>`

**编码**：`application/x-www-form-urlencoded`。**会话**：沿用 E01 Session 与 Cookie。**重定向**：允许跟随。

| 字段 | 位置 | 当前发送值 | 说明 |
| --- | --- | --- | --- |
| `prePayId` | Query | D01 的预支付标识 | 不放入 JSON |
| E01 的全部隐藏字段 | Form | 上一页的当前值 | 保持页面状态 |
| `hvalue_pay` | Form | `0` | 学校表单固定值，具体服务端语义未确认 |
| `i_bank` | Form | `1/WX/微信支付` | 当前选择微信支付 |
| `cb` | Form | `on` | 已验证的普通表单字段 |
| `h_cftz` | Form | `0` | 学校表单固定值 |
| `btn_wx` | Form | `确认支付` | 普通表单按钮值 |

表单字段示意，发送时须进行 URL 编码：

```text
__VIEWSTATE=<E01_VIEWSTATE>
<OTHER_HIDDEN_FIELDS_FROM_E01>
hvalue_pay=0
i_bank=1/WX/微信支付
cb=on
h_cftz=0
btn_wx=确认支付
```

**响应**：支付主页面 HTML；跟随后续跳转后，再从这个响应页面提取一组**新的隐藏字段**供 E03 使用。不能把 E01 的旧 VIEWSTATE 直接用于 E03。

**失败处理**：超时 15 秒；当前实现将连接错误、HTTP 异常或缺少新 VIEWSTATE 报告为错误，不在失败后自动重发确认表单。请求会推进学校支付页面流程，不能把它视作纯静态页面下载。

<a id="e03"></a>
### E03 再次普通表单提交，获取二维码图片地址

**请求**：`POST http://cwcwx.hbue.edu.cn/zhifu/PayMain.aspx?prePayId=<PREPAY_ID>`

与 E02 使用同一 URL，仍然是普通表单 POST；提交控件改为 `btn_wx_show`，隐藏字段必须换成 E02 最新返回值。

请求头：

```http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Referer: <E02_FINAL_RESPONSE_URL>
Cookie: <PAYMENT_SESSION_COOKIES>
```

| 字段 | 位置 | 当前发送值 | 说明 |
| --- | --- | --- | --- |
| `prePayId` | Query | 原预支付标识 | 与 E01、E02 相同 |
| E02 返回的全部隐藏字段 | Form | 最新值 | 不能混用其他订单／其他 Session 的页面状态 |
| `hvalue_pay` | Form | `0` | 学校固定表单字段 |
| `i_bank` | Form | `1/WX/微信支付` | 微信支付 |
| `cb` | Form | `on` | 学校表单当前取值 |
| `h_cftz` | Form | `0` | 学校固定表单字段 |
| `btn_wx_show` | Form | 空字符串 | 触发二维码显示控件 |

**不要发送** `ScriptManager1`、`__ASYNCPOST`、`X-Requested-With` 或 `X-MicrosoftAjax`。2026-10-01 的对照验证中，附加这些 AJAX 参数会收到 `0|error|500||`，这不能解释为订单过期。

**响应**：普通 HTML 页面，包含二维码图片地址。先解码 HTML 实体，再从文本中匹配：

```text
MakeQRCode.aspx?data=<ENCODED_QR_DATA>
```

参考匹配正则为 `MakeQRCode\.aspx\?data=([^\s"'<>|]+)`，页面中二维码图片元素为 `PayImg`。之后拼接为 E04 完整图片 URL，保留原有百分号编码。

**返回值**：页面内的图片地址；参考实现继续使用同一支付会话下载 E04，避免仅返回跨域 URL 导致 Cookie 或页面展示问题。

**失败处理**：没有匹配到图片地址时报告“学校支付响应中没有二维码地址”，不能直接判断为订单过期。超时 15 秒。错误中不附带预支付参数、Cookie、VIEWSTATE 或原始响应内容。

<a id="e04"></a>
### E04 加载微信支付二维码图片

**请求**：`GET http://cwcwx.hbue.edu.cn/zhifu/MakeQRCode.aspx`

| 参数 | 位置 | 类型 | 来源 | 说明 |
| --- | --- | --- | --- | --- |
| `data` | Query | 已编码字符串 | E03 响应中的图片地址 | 保留现有百分号编码，不自行编造或重复编码 |

```http
GET /zhifu/MakeQRCode.aspx?data=<ENCODED_QR_DATA> HTTP/1.1
Host: cwcwx.hbue.edu.cn
```

**响应**：图片二进制。2026-10-01 的样本响应头为 `text/html`，内容却是有效 PNG；仅按响应 `Content-Type` 判断会误拒绝真实二维码。

当前实现保持 E01–E03 的支付 Session 下载图片，通过文件头识别 PNG、JPEG、GIF、WebP 或 BMP，限制最大 2 MiB，再构造 `data:<实际图片类型>;base64,...`。这些是客户端校验和展示约定，不是学校 API 字段。真实样本已在浏览器完成解码和显示，Python 示例按文件头识别类型。

**有效期**：学校二维码和订单的有效期未完整验证，也不一定相同。不要将应用缓存时长作为学校保证的有效期；图片仍可加载也不代表二维码仍可支付。

**失败处理**：图片加载失败时不能认定支付失败；仍需结合原支付页面和学校支付结果。取得可解码图片也不能证明订单已支付。

## 7. 调用顺序与接入要点

### 7.1 查询当前绑定寝室余额

1. A01 初始化 CAS 会话，A02 获取验证码。
2. A03 提交账号、密码密文和验证码答案。
3. A04 跟随回调取得 SDGL token。
4. B01 取得学校 `userId`。
5. B02 使用该 `userId` 获取绑定寝室和余额。
6. 只有确有需要时再使用 B03 分页查询账号可见房间。

### 7.2 查询寝室历史

1. 沿用学校 token，使用 B02 得到的寝室 ID。
2. 区间明细优先参考 C02 已确认的 `buildId + startTimeStr + endTimeStr`，日期为 `yyyyMMdd`。
3. 从 `data.list` 读取 `time/statTime` 和 `energyUsage`，确认数据日期后再入库；缺失日期不补零。
4. C01 返回的是另一种用量记录，使用带横线日期，且本次表现不是常规区间语义，不能无条件作为 C02 的等价替代。
5. C03 是工作台趋势数据，未验证单寝室范围，不应作为单寝室历史的兜底数据。
6. 所有历史接口都应保留“缺少历史余额”的状态，不把用量或扣费金额误作余额。

### 7.3 电费充值与二维码

1. 在取得学校 token、学校 `userId` 和正确寝室 ID 后，校验充值金额和用户确认。
2. 调用 D01 创建订单，保存返回支付 URL 和提取的 `prePayId`。
3. 如需直接展示二维码，按 E01 → E02 → E03 顺序保持支付 Session 和最新隐藏字段，再加载 E04。
4. 用户扫码完成付款后，通过 D02 查询结果；当前状态兼容映射仍需学校实际样本确认。
5. 不能拿 D03 的超时结果推断 D01 的状态；本次没有验证主路径付款到账。

### 7.4 常见接入错误

| 场景 | 应采用的处理 |
| --- | --- |
| CAS 票据提交 | 使用 HTTPS 认证地址，不混用不同 Session 的验证码和 Cookie |
| 两种历史日期格式 | C01 使用 `yyyy-MM-dd`；C02 使用 `yyyyMMdd` |
| 历史用量解析 | 从 `energyUsage` 读取用量，从 `time/statTime` 读取日期 |
| 历史余额缺失 | 保留空值，不把用量、扣费金额或扣费后金额直接当作实时余额 |
| 统计趋势 | 使用数字 `timeType=0/1/2`，不擅自归属到单个寝室 |
| 备用微信接口 | 未验证可用，不自动作为下单失败的兜底重试 |
| 二维码表单 | 两次均为普通 POST，带 `cb=on` 和最新隐藏字段，不加入 AJAX 参数 |
| 二维码图片 | 保持支付 Session，按文件头识别真实图片类型，不只看 Content-Type |

## 8. 验证状态与已知限制

### 8.1 已完成的验证

| 日期 | 范围 | 观察结果 |
| --- | --- | --- |
| 2026-09-30 | HTTPS CAS、当前用户、绑定寝室 | 完成认证并取得学校用户 ID 与绑定寝室 |
| 2026-09-30 | C01 用量记录 | 带横线日期组合返回数据，但窗口不同于普通起止日期区间；详见 C01 |
| 2026-09-30 | C02 扣费记录 | `20260928`–`20260930` 返回 9 月 28、29 日两条明细 |
| 2026-09-30 | C03 统计趋势 | `timeType=0` 返回 30 个 `key/value` 点；`day` 返回参数错误 |
| 2026-09-30 | D03 备用下单 | 双 `/api` 地址读超时，单 `/api` 地址 HTTP 404，未取得二维码 |
| 2026-09-30 | D04 待支付订单列表 | 指定绑定寝室当日查询返回空数组；不能据此保证无任何服务端建单 |
| 2026-10-01 | E01–E04 二维码 | 已有 `prePayId` 成功取得有效 PNG，浏览器解码显示为 133 × 133 |
| 2026-10-01 | 本文 Python 实现 | 完成语法和离线流程检查；不等同于该 Python 版本已完成线上验收 |
| 2026-10-01 | T0 本地 auth.txt 只读烟测 | 按本文参考代码 A01–A04/B01/B02 成功，1 条本人绑定；[分类记录](acceptance/school/2026-10-01-readonly.json)不含真实账户、token 或寝室标识；未执行业务写入，正式 Adapter 尚未验收 |

T2 正式 httpx Adapter 在 2026-10-01 完成 A01–A04/B01/B02/B03 真实链路与本人授权密文后台恢复；CAS JSON 实测可使用 text/plain 且响应压缩，仍按 JSON/图片结构校验。见 [正式只读记录](acceptance/school/2026-10-01-T2-readonly.json)与[后台恢复](acceptance/school/2026-10-01-T2-recovery.json)。仅确认候选第一页，搜索精度未确认；未执行绑定/建单/付款/邮件。

备用支付验证使用 1 元和 `NATIVE`，没有扫码付款。二维码验证使用已有订单，没有再次调用 `phonePay`；支付页面确认自身仍可能生成新的支付流水。

### 8.2 尚未确认的行为

学校完整错误码、限流阈值、token 和二维码有效期、最大查询跨度、部分接口的账号权限范围、完整支付状态枚举及付款到账链路，尚未完成验证。C01 的日期窗口和 C03 的统计归属存在明确限制，不能当作稳定的单寝室完整历史来源。

本文的成功记录只对应上述日期和条件。响应结构改变、返回空记录、超时或业务错误时，应保留原始状态并重新确认，不能补造数据、推断支付成功或自动重复建单。

## 9. Python 参考实现

### 9.1 使用方式与接口对应

将 **9.2、9.3、9.4、9.5 四段 Python 代码依次复制到同一个 `school_api_client.py`**，保存在任意工作目录即可。代码所需的加密算法与公钥参数全部在本文中；9.6 的示例脚本与该文件放在同一目录，选择需要的示例运行。

建议使用 **Python 3.12**，示例在 Python 3.12.10 下完成离线检查。基础依赖为 `requests`，自动识别验证码另需 `ddddocr`；其余模块均来自 Python 标准库。仅使用已有 `prePayId` 获取二维码时可以不安装 `ddddocr`。

Windows 环境可在保存示例的目录中创建虚拟环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install requests ddddocr
.\.venv\Scripts\python.exe your_example.py
```

macOS / Linux 环境：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install requests ddddocr
./.venv/bin/python your_example.py
```

将 `your_example.py` 替换为自己保存的调用示例文件名。只运行二维码示例时，安装命令可仅保留 `requests`。

历史参数采用 2026-09-30 的核验结果，二维码流程依据 2026-10-01 的页面验证。代码能够独立运行不等于所有接口当前均可用；`wx_pay` 默认拒绝调用，需要显式启用排查模式，且不会自动切换到主路径建单。

| 接口 | Python 实现 |
| --- | --- |
| A01–A04 | `cas_login`，函数内逐步标注 A01、A02、A03、A04 |
| B01 | `SchoolClient.get_info` |
| B02 | `SchoolClient.bound_rooms` |
| B03 | `SchoolClient.rooms_page`，按需翻页 |
| C01 | `SchoolClient.usage_records`，不承诺任意区间完整性 |
| C02 | `SchoolClient.record_history`；`normalize_records` 解析明细 |
| C03 | `SchoolClient.trend`，不关联到单寝室 |
| D01 | `SchoolClient.phone_pay` |
| D02 | `SchoolClient.pay_result`，保留学校原始 `data` |
| D03 | `SchoolClient.wx_pay`，默认拒绝，显式启用仅用于排查 |
| D04 | `SchoolClient.orders` |
| E01–E03 | `CampusPayment.get_qr`，保留 Cookie、两次普通 POST、最新隐藏字段 |
| E04 | `CampusPayment.download_image`，按文件头识别；`get_qr` 返回图片 Data URL |

代码定义时不发起请求、不读取 `auth.txt`，也不自动下单。调用者只应输出摘要，不能打印 token、Cookie、完整 API 响应或异常链中的原始请求内容。

### 9.2 公共工具和凭据载入

```python
from __future__ import annotations

import base64
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

# 学校登录页使用的公开 RSA 公钥参数；不是私钥或账号凭据。
RSA_MODULUS = int(
    "00b5eeb166e069920e80bebd1fea4829d3d1f3216f2aabe79b6c47a3c18dcee5"
    "fd22c2e7ac519cab59198ece036dcf289ea8201e2a0b9ded307f8fb704136eaeb6"
    "70286f5ad44e691005ba9ea5af04ada5367cd724b5a26fdb5120cc95b6431604bd"
    "219c6b7d83a6f8f24b43918ea988a76f93c333aa5a20991493d4eb1117e7b1",
    16,
)
RSA_EXPONENT = 65537
RSA_BLOCK_SIZE = 128


def encrypt_password(password):
    """与学校登录协议一致的分块、小端 RSA；不使用 OAEP/PKCS#1 填充。"""
    data = password.encode("latin-1")
    data += b"\x00" * (-len(data) % RSA_BLOCK_SIZE)
    encrypted = []
    for offset in range(0, len(data), RSA_BLOCK_SIZE):
        number = int.from_bytes(data[offset:offset + RSA_BLOCK_SIZE], "little")
        encrypted.append(f"{pow(number, RSA_EXPONENT, RSA_MODULUS):0256x}")
    return "".join(encrypted)


CAS = "https://rz.hbue.edu.cn/authserver"
API = "https://sdgl.hbue.edu.cn/api"
SERVICE = f"{API}/sso/callback?targetUrl={API}/sso/callback&loginType=mobile"
PAY_BASE = "http://cwcwx.hbue.edu.cn/zhifu"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/132.0.0.0 Safari/537.36"
)


class SchoolAPIError(RuntimeError):
    """消息只包含操作名和错误类别，不包含凭据或学校原始响应。"""


def send(session, method, url, *, label, timeout=20, **kwargs):
    try:
        response = session.request(method, url, timeout=timeout, **kwargs)
    except requests.Timeout:
        raise SchoolAPIError(
            f"{label}超时；若为支付操作，执行结果不确定，请先核对订单"
        ) from None
    except requests.RequestException:
        raise SchoolAPIError(f"{label}连接失败") from None
    if not 200 <= response.status_code < 300:
        raise SchoolAPIError(f"{label}返回 HTTP {response.status_code}")
    return response


def read_json(response, *, label, check_code=True):
    try:
        result = response.json()
    except ValueError:
        raise SchoolAPIError(f"{label}返回非 JSON 内容") from None
    if not isinstance(result, dict):
        raise SchoolAPIError(f"{label}返回结构异常")
    if check_code and "code" in result and result["code"] != 200:
        # 不直接输出 msg，其中可能包含账号、SQL 或请求参数。
        raise SchoolAPIError(f"{label}业务请求失败")
    return result


def load_auth_file(path):
    """仅在调用时读入内存；支持 JSON、账号/密码标签或两行文本。"""
    try:
        raw = Path(path).read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        raise SchoolAPIError("无法以 UTF-8 载入凭据文件") from None
    try:
        values = json.loads(raw)
    except ValueError:
        values = None
    if not isinstance(values, dict):
        values = {}
        for line in raw.splitlines():
            match = re.fullmatch(
                r"\s*(username|account|sdgl_username|账号|学号|"
                r"password|pwd|sdgl_password|密码)\s*[:=：]\s*(.*?)\s*",
                line, re.I,
            )
            if match:
                values[match[1].lower()] = match[2]
    user = next((values[k] for k in
                 ("username", "account", "sdgl_username", "账号", "学号")
                 if k in values), None)
    password = next((values[k] for k in
                     ("password", "pwd", "sdgl_password", "密码")
                     if k in values), None)
    if user is None or password is None:
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not values and len(lines) == 2:
            user, password = lines
    if not isinstance(user, str) or not isinstance(password, str) or not user or not password:
        raise SchoolAPIError("凭据格式不符合约定")
    return user, password


def date_params(start, end, *, compact=False):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        raise SchoolAPIError("日期请使用 YYYY-MM-DD") from None
    if first > last:
        raise SchoolAPIError("开始日期不能晚于结束日期")
    fmt = "%Y%m%d" if compact else "%Y-%m-%d"
    return {"startTimeStr": first.strftime(fmt), "endTimeStr": last.strftime(fmt)}


def payment_amount(value):
    """示例限制整数 1–500 元；不是学校官方上限。"""
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise SchoolAPIError("金额格式错误") from None
    if not amount.is_finite() or not 1 <= amount <= 500 or amount != amount.to_integral_value():
        raise SchoolAPIError("金额必须为 1–500 元之间的整数")
    return int(amount)
```

JSON 凭据格式为 `{"username": "<账号>", "password": "<密码>"}`，两行格式为第一行账号、第二行密码。若密码包含首尾空格，应使用 JSON 字符串格式保留它们。不要将真实值写进调用脚本或文档。

### 9.3 A01–A04：统一认证完整流程

```python
def make_ocr_solver():
    # 延迟导入：只使用已有 prePayId 获取二维码时不需要 OCR。
    import ddddocr
    ocr = ddddocr.DdddOcr(show_ad=False)

    def solve(data_url):
        try:
            image = base64.b64decode(data_url.split(",", 1)[1], validate=True)
            raw = "".join(c for c in ocr.classification(image) if c.isprintable()).strip()
        except (ValueError, IndexError, TypeError):
            return None
        match = re.fullmatch(r"(\d)\s*([+\-*/xX])\s*(\d)\s*=?\s*", raw)
        if not match:
            return None
        a, operator, b = int(match[1]), match[2].lower(), int(match[3])
        if operator == "+":
            return a + b
        if operator == "-":
            return a - b
        if operator in ("*", "x"):
            return a * b
        return a // b if b else None

    return solve


def cas_login(username, password, *, solve_captcha=None):
    """返回学校 token；不落盘、不打印，账号和密码由调用者显式提供。"""
    if not username or not password:
        raise SchoolAPIError("请提供学校账号和密码")
    solver = solve_captcha or make_ocr_solver()
    with requests.Session() as session:
        session.headers["User-Agent"] = UA

        # A01：初始化 Cookie，同一 Session 完成整个认证链路。
        send(session, "GET", CAS + "/login", label="认证初始化",
             params={"service": SERVICE})

        # A02：最多尝试识别 4 次；只在识别失败时重新取图。
        uid, answer = "", None
        for _ in range(4):
            captcha = read_json(send(
                session, "GET", CAS + "/kaptcha", label="验证码",
                params={"uid": uid},
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": CAS + "/login"},
            ), label="验证码", check_code=False)
            uid, content = captcha.get("uid"), captcha.get("content")
            if not uid or not isinstance(content, str):
                raise SchoolAPIError("验证码响应缺少必要字段")
            answer = solver(content)
            if answer is not None:
                break
        if answer is None:
            raise SchoolAPIError("验证码未识别成功")

        # A03：表单字段 password 使用学校兼容 RSA 算法。
        try:
            encrypted = encrypt_password(password)
        except UnicodeEncodeError:
            raise SchoolAPIError("学校加密实现仅支持 Latin-1 密码字符") from None
        tickets = read_json(send(
            session, "POST", CAS + "/v1/tickets", label="认证票据",
            data={"username": username, "password": encrypted,
                  "service": SERVICE, "loginType": "", "id": uid,
                  "code": str(answer), "otpcode": ""},
        ), label="认证票据", check_code=False)
        details = tickets.get("data")
        if isinstance(details, dict) and details.get("code"):
            raise SchoolAPIError("学校账号认证失败")
        ticket = tickets.get("ticket")
        if not isinstance(ticket, str) or not ticket:
            raise SchoolAPIError("学校认证未返回票据")

        # A04：跟随回调，从最终 URL 的查询参数提取 token。
        response = send(
            session, "GET", SERVICE + "&" + urlencode({"ticket": ticket}),
            label="认证回调", allow_redirects=True,
        )
        token = parse_qs(urlparse(response.url).query).get("token", [""])[0]
        if not token:
            raise SchoolAPIError("学校回调未返回登录令牌")
        return token
```

`solve_captcha` 也可以传入自己的函数：接收验证码 Data URL，返回算式结果或 `None`。返回 `0` 是有效答案。函数不含无限重试、验证码提交失败重试或全局 token 缓存；学校拒绝认证时由调用者处理。

### 9.4 B、C、D：寝室、历史与订单接口

```python
class SchoolClient:
    def __init__(self, token):
        if not isinstance(token, str) or not token:
            raise SchoolAPIError("缺少学校登录令牌")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Authorization": "Bearer " + token})

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _get(self, path, *, label, timeout=20, **params):
        return read_json(send(self.session, "GET", API + path,
                              label=label, params=params, timeout=timeout), label=label)

    def get_info(self):
        return self._get("/getInfo", label="当前学校用户")

    def bound_rooms(self, user_id):
        result = self._get("/base/roomUser/selectRoomListByUserId",
                           label="绑定寝室", userId=user_id)
        rooms = result.get("data")
        if not isinstance(rooms, list):
            raise SchoolAPIError("绑定寝室响应不是数组")
        return rooms

    def rooms_page(self, current=1, size=1000):
        if current < 1 or size < 1:
            raise SchoolAPIError("页码和每页条数必须大于零")
        return self._get("/base/rooms/queryRoomList", label="房间分页", timeout=30,
                         current=current, size=size, pageTotal=size)

    def usage_records(self, room_id, reference_date, end_date):
        # C01：带横线日期；成功不代表任意区间的完整查询。
        return self._get("/base/record/queryUsageByTime", label="用量记录",
                         buildId=room_id, **date_params(reference_date, end_date))

    def record_history(self, room_id, start, end):
        # C02：由 YYYY-MM-DD 输入转换为学校需要的 YYYYMMDD。
        return self._get("/base/record/queryRecordByTime", label="扣费记录",
                         buildId=room_id, **date_params(start, end, compact=True))

    def trend(self, time_type=0):
        if type(time_type) is not int or time_type not in (0, 1, 2):
            raise SchoolAPIError("time_type 必须为整数 0、1 或 2")
        # C03：学校前端没有传寝室 ID，不能假定此结果属于单寝室。
        return self._get("/home/queryEleTrendByTimeType", label="统计趋势", timeType=time_type)

    def phone_pay(self, user_id, room_id, amount, *, confirmed=False):
        if confirmed is not True:
            raise SchoolAPIError("需要先确认充值寝室和金额")
        amount = payment_amount(amount)
        body = {"userId": user_id, "roomId": room_id, "buildId": room_id,
                "orderType": 0, "payMethod": 1, "orderAmount": amount,
                "amount": amount, "tradeType": "NATIVE"}
        result = read_json(send(
            self.session, "POST", API + "/base/order/phonePay",
            label="电费建单", json=body, timeout=40,
        ), label="电费建单")
        pay_url = result.get("data")
        if not isinstance(pay_url, str):
            raise SchoolAPIError("学校未返回支付链接；请先核对是否已建单")
        parsed = urlparse(pay_url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in {
            "cwcwx.hbue.edu.cn", "sdgl.hbue.edu.cn", "pay.hbue.edu.cn",
        }:
            raise SchoolAPIError("学校支付链接不符合预期；请先核对订单")
        prepay_id = parse_qs(parsed.query).get("prePayId", [""])[0]
        # 这些字段由参考函数整理，不代表学校响应原本就是这个结构。
        return {"pay_url": pay_url, "prepay_id": prepay_id}

    def pay_result(self, order_id):
        if not isinstance(order_id, str) or not order_id:
            raise SchoolAPIError("缺少学校订单标识")
        result = self._get("/water/order/getPayOrderReturnUrl",
                           label="支付结果", orderId=order_id)
        # 不把 HTTP 200、未知 data 或 URL 擅自转换成“已支付”。
        return result.get("data")

    def wx_pay(self, user_id, room_id, amount, *, enable_probe=False, confirmed=False):
        if enable_probe is not True or confirmed is not True:
            raise SchoolAPIError("备用接口尚未验证可用，只允许显式确认的排查调用")
        # API 自带 /api，此处 /api/wx/pay 会形成学校前端实际的 /api/api/wx/pay。
        # 不自动改用单 /api，不重试，也不回退 phonePay。
        return self._get("/api/wx/pay", label="备用微信建单",
                         userId=user_id, buildId=room_id, orderType=0,
                         payMethod=1, orderAmount=payment_amount(amount), tradeType="NATIVE")

    def orders(self, room_id, start, end, *, pay_status=0, current=1):
        if type(pay_status) is not int or pay_status not in (0, 2) or current < 1:
            raise SchoolAPIError("这里只支持待支付/已支付查询，页码从 1 开始")
        return self._get("/base/order/page", label="学校订单",
                         buildId=room_id, **date_params(start, end),
                         current=current, size=10, pageTotal=100,
                         orderType=0, payMethod=1, payStatus=pay_status)


def normalize_records(payload, room_id, *, source):
    """只解析 C01/C02，保留真实日期，不补零、不推断历史余额。"""
    if source not in ("usage", "record"):
        raise SchoolAPIError("未知历史来源")
    data = payload.get("data")
    rows = data if source == "usage" else (data.get("list") if isinstance(data, dict) else None)
    if not isinstance(rows, list):
        raise SchoolAPIError("历史记录结构异常")

    def numeric(value):
        try:
            result = float(value)
            return result if math.isfinite(result) else None
        except (ValueError, TypeError, OverflowError):
            return None

    points, skipped = [], 0
    for row in rows:
        if not isinstance(row, dict):
            skipped += 1
            continue
        parsed_date = None
        for key, fmt in (("time", "%Y-%m-%d"), ("statTime", "%Y%m%d")):
            try:
                parsed_date = datetime.strptime(str(row.get(key) or ""), fmt).date().isoformat()
                break
            except ValueError:
                pass
        if parsed_date is None:
            skipped += 1
            continue
        points.append({
            # 采用调用者传入的寝室上下文，不依赖 C02 的行 buildId。
            "room_id": str(room_id), "date": parsed_date,
            "usage": numeric(row.get("energyUsage")),
            "deducted_amount": numeric(row.get("trueAmount")),
            "balance": numeric(row.get("balance")),
        })
    return {"records": sorted(points, key=lambda item: item["date"]), "skipped": skipped}
```

`rooms_page` 只请求指定一页；需要翻页时依据学校返回的 `data.pages` 和空记录停止，保留合理间隔。`normalize_records` 不把 `trueAmount`、`energyUsage` 或 `afterAmount` 当作余额，也不会强行裁剪 C01 的日期异常；调用者应显式检查返回日期是否在业务要求的区间内。

参考客户端负责学校 HTTP 调用；应用层仍需实现寝室归属校验、订单持久化和重复提交控制。先确认寝室属于当前账号，再调用建单函数；`confirmed=True` 表示调用端已完成确认。任何支付请求失败后都不会自动补发。

### 9.5 E01–E04：从已有 prePayId 取得真实二维码

以下代码实现第 6 节的完整二维码流程：**两次普通表单提交**，每一步使用最新隐藏字段，携带 `cb=on`，保持独立支付 Cookie，并按实际图片文件头识别类型。

```python
class HiddenInputs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "input":
            return
        attributes = {key.lower(): value for key, value in attrs}
        if (attributes.get("type") or "").lower() == "hidden" and attributes.get("name"):
            # HTMLParser 已解码属性中的 &amp; 等实体；保留同名字段顺序。
            self.fields.append((attributes["name"], attributes.get("value") or ""))


def payment_form(html, overrides):
    parser = HiddenInputs()
    parser.feed(html)
    if not any(name == "__VIEWSTATE" for name, _ in parser.fields):
        raise SchoolAPIError("支付页面未返回 VIEWSTATE，请打开原支付页面核对")
    # 普通提交不能携带旧实现人为加入的 AJAX 字段。
    excluded = set(overrides) | {"ScriptManager1", "__ASYNCPOST"}
    return [(key, value) for key, value in parser.fields if key not in excluded] + list(overrides.items())


def image_mime(content):
    if content.startswith(bytes.fromhex("89504e470d0a1a0a")):
        return "image/png"
    if content.startswith(bytes.fromhex("ffd8ff")):
        return "image/jpeg"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"BM"):
        return "image/bmp"
    return None


class CampusPayment:
    def __init__(self):
        # 和 CAS、SDGL 分开，绝不携带 SDGL 的 Bearer token。
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA, "Connection": "close"})

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def download_image(self, url, *, referer):
        # E04：限制为学校二维码地址，不接受调用者任意图片域名。
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc != "cwcwx.hbue.edu.cn" or parsed.path != "/zhifu/MakeQRCode.aspx":
            raise SchoolAPIError("二维码地址不符合学校接口约定")
        response = send(self.session, "GET", url, label="二维码图片", timeout=15,
                        headers={"Referer": referer})
        content = response.content
        mime = image_mime(content)
        # 学校已出现 PNG 字节 + Content-Type: text/html，不能据 MIME 头拒绝。
        if not mime or not content or len(content) > 2 * 1024 * 1024:
            raise SchoolAPIError("学校返回的二维码图片无效")
        return content, mime

    def get_qr(self, prepay_id):
        """只推进已有订单的支付页，不调用 phonePay 建立新电费订单。"""
        if not isinstance(prepay_id, str) or not re.fullmatch(r"[A-Za-z0-9]{1,256}", prepay_id):
            raise SchoolAPIError("请输入支付链接中有效的 prePayId")
        # 每次提取都使用干净支付 Cookie；一次调用内保持会话连续。
        self.session.cookies.clear()
        query = urlencode({"prePayId": prepay_id})
        accept_url = PAY_BASE + "/payAccept.aspx?" + query
        main_url = PAY_BASE + "/PayMain.aspx?" + query

        # E01：取得受理页隐藏字段。
        accept = send(self.session, "GET", accept_url, label="支付受理页", timeout=15)
        accept.encoding = "utf-8"
        first_form = payment_form(accept.text, {
            "hvalue_pay": "0", "i_bank": "1/WX/微信支付", "cb": "on",
            "h_cftz": "0", "btn_wx": "确认支付",
        })

        # E02：第一次普通表单 POST，Requests 对中文字段做 UTF-8 表单编码。
        main = send(self.session, "POST", main_url, label="支付确认页", timeout=15,
                    data=first_form, headers={
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "Referer": accept.url,
                    })
        main.encoding = "utf-8"
        second_form = payment_form(main.text, {
            "hvalue_pay": "0", "i_bank": "1/WX/微信支付", "cb": "on",
            "h_cftz": "0", "btn_wx_show": "",
        })

        # E03：仍为普通 POST。没有 ScriptManager1、__ASYNCPOST 或 AJAX 头。
        result = send(self.session, "POST", main_url, label="二维码页面", timeout=15,
                      data=second_form, headers={
                          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                          "Referer": main.url,
                      })
        result.encoding = "utf-8"
        match = re.search(r"MakeQRCode\.aspx\?data=([^\s\"'<>|]+)", unescape(result.text), re.I)
        if not match:
            raise SchoolAPIError("学校支付响应中没有二维码地址，不能据此判断订单过期")
        # data 已经编码过，不能再 urlencode 一次，也不把它打印到日志。
        image_url = PAY_BASE + "/MakeQRCode.aspx?data=" + match[1]
        content, mime = self.download_image(image_url, referer=result.url)
        return {
            "image": f"data:{mime};base64," + base64.b64encode(content).decode("ascii"),
            "mime": mime,
            "content": content,
        }
```

返回值是客户端构造的字典：`image` 可交给前端 `<img src>`，`mime` 为文件头识别的类型，`content` 为图片二进制。通过 JSON 接口返回时只取 `image/mime`，不要直接序列化 bytes 类型的 `content`。

该代码通过文件头识别图片类型，不包含完整图片解码器。2026-10-01 的线上 PNG 样本已在浏览器成功解码；本文 Python 实现的验证范围为语法和离线模拟流程。

支付页确认本身可能生成新的支付流水；“复用已有 `prePayId`”只表示不会再次调用 `phonePay` 新建电费订单。超时不要自动重复提交确认页。

### 9.6 调用示例

#### 示例一：登录、绑定寝室和扣费历史

保存为 `your_example.py`，与按本文生成的 `school_api_client.py` 放在同一目录。另创建 UTF-8 编码的 `auth.txt`，填写自己的学校账号和密码，格式见 9.2 节。示例只输出条数，不输出账号、token、寝室 ID、余额或完整响应。

```python
from pathlib import Path

from school_api_client import (
    SchoolAPIError, SchoolClient, cas_login, load_auth_file, normalize_records,
)


def main():
    username, password = load_auth_file(Path(__file__).with_name("auth.txt"))
    try:
        token = cas_login(username, password)
    finally:
        # 去除本函数引用；Python 字符串不提供可靠的物理内存清零保证。
        del username, password
    with SchoolClient(token) as client:
        info = client.get_info()
        user_id = (info.get("user") or {}).get("userId")
        if user_id is None:
            raise SchoolAPIError("学校未返回用户 ID")
        rooms = client.bound_rooms(user_id)
        print(f"登录成功，绑定寝室数量：{len(rooms)}")
        if not rooms:
            return
        # 此处只演示第一个绑定寝室；多个寝室时应让使用者选择。
        if rooms[0].get("roomId") is None:
            raise SchoolAPIError("学校未返回寝室 ID")
        room_id = str(rooms[0]["roomId"])
        start, end = "2026-09-28", "2026-09-30"
        raw = client.record_history(room_id, start, end)
        parsed = normalize_records(raw, room_id, source="record")
        outside = sum(not start <= row["date"] <= end for row in parsed["records"])
        print(f"历史条数：{len(parsed['records'])}，未解析条数：{parsed['skipped']}，区间外条数：{outside}")


if __name__ == "__main__":
    try:
        main()
    except SchoolAPIError as error:
        print(str(error))
```

示例日期来自原实测，实际使用时按查询需要修改。用量接口可调用 `client.usage_records(room_id, start, end)`，随后使用 `source="usage"` 解析并检查日期；不要据此声称已查询完整区间。趋势使用 `client.trend(0)`，原始 `data` 按 `key/value` 展示，不调用寝室历史解析器。

#### 示例二：只用已有 prePayId 获取并保存二维码

这个例子不登录 CAS，也不读取 `auth.txt`。`prePayId` 从已有支付链接取得并通过隐藏输入交给脚本；不要把真实值写在命令行、脚本或文档里。

```python
from getpass import getpass
from pathlib import Path

from school_api_client import CampusPayment, SchoolAPIError


def main():
    prepay_id = getpass("请输入已有支付链接的 prePayId（隐藏输入）：").strip()
    with CampusPayment() as payment:
        result = payment.get_qr(prepay_id)
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
              "image/webp": ".webp", "image/bmp": ".bmp"}[result["mime"]]
    output = Path("school-payment-qr" + suffix)
    output.write_bytes(result["content"])
    print(f"二维码已保存：{output.name}")
    # 接入网页时返回 {"image": result["image"]}，由 <img> 展示。


if __name__ == "__main__":
    try:
        main()
    except SchoolAPIError as error:
        print(str(error))
```

图片文件是二进制，使用 `write_bytes`；脚本和凭据使用 UTF-8。二维码可以承载有效支付信息，应按临时支付材料处理，不能公开当作通用示例。

#### 示例三：已确认的新订单 → 二维码

下面定义的是调用函数，不会在导入时建单。调用前已取得学校 token、学校 `userId`、当前账号的绑定寝室 ID，并已完成金额确认。

```python
from school_api_client import CampusPayment, SchoolAPIError


def create_order_and_qr(client, user_id, room_id, amount, *, confirmed=False):
    order = client.phone_pay(user_id, room_id, amount, confirmed=confirmed)
    # 到这一步电费订单已创建。业务系统应先保存 order，再做二维码提取。
    if not order["prepay_id"]:
        return {"order": order, "qr": None, "qr_error": "支付链接没有 prePayId，请打开原支付页"}
    try:
        with CampusPayment() as payment:
            qr = payment.get_qr(order["prepay_id"])
        return {"order": order, "qr": {"image": qr["image"], "mime": qr["mime"]}}
    except SchoolAPIError as error:
        # 二维码失败不能触发重新建单；保留已有支付链接和标识。
        return {"order": order, "qr": None, "qr_error": str(error)}
```

如果 `phone_pay` 自身超时，函数会抛出结果不确定的错误；不要再次调用此函数自动补单，应先用 `orders` 或学校页面核对。二维码生成成功仍不代表支付完成，后续查询 `pay_result` 的原始返回，不能把未知状态改为已支付。

### 9.7 验证范围

本文的 Python 实现已检查代码块语法、独立导入、登录密码加密一致性，并使用离线响应模拟核对日期转换、历史解析和二维码的 GET → POST → POST → GET 顺序。二维码检查包括最新 VIEWSTATE、`cb=on`、不发送 AJAX 参数，以及错误 Content-Type 下的 PNG 文件头识别。

这些检查没有读取真实账号、请求学校服务、创建电费订单或使用真实 `prePayId`。线上接口的已知验证日期与限制见第 8 节。

## T3 真实新增补充（2026-10-01）

用户明确授权的枫苑5号-402 已通过生产前端执行 B05–B07 筛选、B03 精确核验与 B04 单次写入，并经 B02 和持久台账确认。绑定数 1 → 2，原默认保留，临时写开关恢复 false；记录见 [真实分类结果](acceptance/school/2026-10-01-T3-binding.json)。本例仍不证明学校累计上限、重复写入行为、最小必填字段或其他目标均可绑定。用户追加了同一目标的删除验收，删除尚未执行。

## T3 真实删除补充（2026-10-01）

用户指定的同一枫苑5号-402 已通过生产前端执行 B08。一次上游方法覆盖写入、正常间隔30秒的两次 B02 缺席及本域 inactive/缓存保留通过，绑定数2→1、原默认保留，写开关恢复 false；[真实分类证据](acceptance/school/2026-10-01-T3-removal.json)。此为指定账号/目标的删除验收，学校全量错误码、任意目标权限与其他接口仍不自动视为已验证。

## T4 真实本人只读补充（2026-10-01）

生产前端/正式Adapter通过本人B02持久余额刷新、最近7天C02同步（6个已知记录日、partial覆盖）和Scheduler/Worker的一次balance_only采集。原监控配置恢复且应用退出，无绑定/支付/SMTP、无真实截图/trace，证据见 [分类记录](acceptance/school/2026-10-01-T4-query.json)。账号当前仅1个绑定，不宣称真实多房间隔离或学校全日完整覆盖、稳定来源ID、频率上限已确认。

## 2026-10-02学校验证码核查

本次同一指定账号的对照：完全省略A03的id/code认证被拒绝；取得有效学校uid后留空code也被拒绝；在T5真实链路使用正常学校验证码认证及B02成功。因此当前CAS链路需要验证码，保留学校验证码获取/后台OCR，不以应用自生成验证码替代学校校验。该结论限定当前账号/协议；分类证据见 [空答案记录](acceptance/school/T5-captcha-empty-answer.json)，不记录账号/密码/uid/token。

## 2026-10-02 T6指定真实增量

使用auth.txt本人账号与应用默认寝室，生产Adapter执行一次10元D01、E01–E04取得可解码学校二维码；URL/prePayId与Cookie/VIEWSTATE保留在Adapter密文，SDGL内部单号仍未知。D02未取得可确认结果，错误分类SCHOOL_INVALID_RESPONSE；本地awaiting_payment仅表示建单后等待，不能当成已验证学校枚举。用户要求本轮先交付代码、暂不扫码；未付款、未核对到账、未建第二笔，公共支付保持关闭。见[T6记录](acceptance/T6验收记录.md)及[分类证据](acceptance/school/2026-10-02-T6-order.json)。

## 2026-10-02指定1元增量

用户将真实范围改为默认寝室1元并要求本地取消原10元。应用保留原D01/E02/E03台账、本地取消释放占位后一次1元D01/E链路；用户明确确认付款。精确匹配同一学校roomId的新鲜B02余额较付款前增加1.00元。D02仍为HTTP200、业务500、data=null，没有可验收的已支付枚举；不按空结果或余额差自动捏造支付状态，不开放D03备用写入。本地取消不表示学校撤单或二维码失效。
