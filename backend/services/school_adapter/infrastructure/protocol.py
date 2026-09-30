"""正式 A01–A04/B01–B03 协议；没有绑定或支付写入口。"""

from dataclasses import dataclass
from urllib.parse import parse_qs

import httpx

from services.common.errors import ErrorCode
from services.common.http import ApiError

from .images import validate_image
from .rsa import encrypt_password
from .transport import Deadline, parse_json

CAS = "https://rz.hbue.edu.cn/authserver"
API = "https://sdgl.hbue.edu.cn/api"
SERVICE = f"{API}/sso/callback?targetUrl={API}/sso/callback&loginType=mobile"


@dataclass(repr=False)
class SchoolChallenge:
    uid: str
    image: str
    cookies: list[dict]


def dump_cookies(client):
    return [
        {
            "name": cookie.name,
            "value": cookie.value,
            "domain": cookie.domain,
            "path": cookie.path,
            "secure": cookie.secure,
        }
        for cookie in client.cookies.jar
    ]


def restore_cookies(client, cookies):
    for cookie in cookies:
        if cookie["domain"].lstrip(".") not in {"rz.hbue.edu.cn", "sdgl.hbue.edu.cn"}:
            raise ApiError(502, ErrorCode.SCHOOL_PROTOCOL_CHANGED, "学校 Cookie 范围不受支持")
        client.cookies.set(
            cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"]
        )


class SchoolProtocol:
    def __init__(self, transport):
        self.transport = transport

    async def challenge(self, *, deadline=None):
        deadline = deadline or Deadline(30)
        async with self.transport.client() as client:
            await self.transport.request(
                client, "GET", f"{CAS}/login", deadline, params={"service": SERVICE}
            )
            return await self.next_challenge(client, "", deadline)

    async def next_challenge(self, client, uid, deadline):
        response = await self.transport.request(
            client,
            "GET",
            f"{CAS}/kaptcha",
            deadline,
            params={"uid": uid},
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{CAS}/login"},
        )
        value = parse_json(response, check_code=False)
        uid = value.get("uid")
        if not isinstance(uid, (str, int)) or isinstance(uid, bool) or not str(uid):
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校验证码标识缺失")
        return SchoolChallenge(str(uid), validate_image(value.get("content")), dump_cookies(client))

    async def authenticate(self, student_id, password, challenge, answer, *, deadline=None):
        deadline = deadline or Deadline(60)
        encrypted = encrypt_password(password)
        async with self.transport.client() as client:
            restore_cookies(client, challenge["cookies"])
            response = await self.transport.request(
                client,
                "POST",
                f"{CAS}/v1/tickets",
                deadline,
                read_timeout=15,
                data={
                    "username": student_id,
                    "password": encrypted,
                    "service": SERVICE,
                    "loginType": "",
                    "id": challenge["uid"],
                    "code": answer,
                    "otpcode": "",
                },
            )
            value = parse_json(response, check_code=False)
            data = value.get("data")
            if isinstance(data, dict) and data.get("code"):
                raise ApiError(
                    401,
                    ErrorCode.SCHOOL_LOGIN_REJECTED,
                    "学校登录未通过，请检查账号、密码与验证码并重新取图",
                )
            ticket = value.get("ticket")
            if not isinstance(ticket, str) or not ticket:
                raise ApiError(401, ErrorCode.SCHOOL_LOGIN_REJECTED, "学校认证未完成，请重新取图")
            response = await self.transport.request(
                client,
                "GET",
                httpx.URL(SERVICE).copy_merge_params({"ticket": ticket}),
                deadline,
                read_timeout=15,
            )
            tokens = parse_qs(response.url.query.decode()).get("token", [])
            if len(tokens) != 1 or not tokens[0] or len(tokens[0]) > 8192:
                raise ApiError(502, ErrorCode.SCHOOL_PROTOCOL_CHANGED, "学校认证未返回有效令牌")
            token = tokens[0]
        # SDGL 不继承 CAS CookieJar。
        info = await self.read("/getInfo", token, {}, deadline=deadline)
        user = info.get("user")
        uid = user.get("userId") if isinstance(user, dict) else None
        if not isinstance(uid, (str, int)) or isinstance(uid, bool) or not str(uid):
            raise ApiError(502, ErrorCode.SCHOOL_INVALID_RESPONSE, "学校用户信息缺少必要标识")
        return token, str(uid)

    async def read(self, path, token, params, *, deadline=None):
        deadline = deadline or Deadline(25)
        async with self.transport.client() as client:
            response = await self.transport.request(
                client,
                "GET",
                f"{API}{path}",
                deadline,
                params=params,
                authenticated=True,
                headers={"Authorization": f"Bearer {token}"},
            )
            return parse_json(response, authenticated=True)
