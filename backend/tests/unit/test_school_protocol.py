import asyncio
import base64
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

import httpx
import pytest

from services.common.http import ApiError
from services.school_adapter.infrastructure.images import validate_image
from services.school_adapter.infrastructure.protocol import SchoolProtocol
from services.school_adapter.infrastructure.rsa import MODULUS, encrypt_password
from services.school_adapter.infrastructure.transport import SchoolTransport

IMAGE = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nsynthetic").decode()


class Limiter:
    @asynccontextmanager
    async def global_slot(self, deadline):
        deadline.remaining()
        yield


def test_school_rsa_keeps_spaces_blocks_and_latin1_rules():
    raw = "  synthetïc  "
    expected = f"{pow(int.from_bytes(raw.encode('latin-1'), 'little'), 65537, MODULUS):0256x}"
    assert encrypt_password(raw) == expected
    assert encrypt_password(raw) != encrypt_password(raw.strip())
    assert len(encrypt_password("a" * 129)) == 512
    with pytest.raises(ApiError) as error:
        encrypt_password("不支持")
    assert error.value.status == 422


@pytest.mark.parametrize(
    "value",
    [
        "data:image/svg+xml;base64,PHN2Zz4=",
        "data:image/png;base64,AAAA",
        "data:image/png;base64,@@@@",
        IMAGE + " ",
    ],
)
def test_invalid_mime_signature_or_base64_is_rejected(value):
    with pytest.raises(ApiError):
        validate_image(value)


def test_cas_cookies_callbacks_and_sdgl_are_isolated():
    seen = []

    def handler(request):
        seen.append(request)
        path = request.url.path
        if path == "/authserver/login":
            return httpx.Response(200, text="CAS", headers={"set-cookie": "CAS=synthetic; Path=/"})
        if path == "/authserver/kaptcha":
            assert request.headers["cookie"] == "CAS=synthetic"
            return httpx.Response(200, json={"uid": "synthetic", "content": IMAGE})
        if path == "/authserver/v1/tickets":
            form = parse_qs(request.content.decode(), keep_blank_values=True)
            assert form["code"] == ["3"] and form["loginType"] == [""]
            assert form["password"] == [encrypt_password(" test ")]
            return httpx.Response(200, json={"ticket": "synthetic-ticket"})
        if path == "/api/sso/callback":
            assert request.url.params["loginType"] == "mobile"
            assert request.url.params["ticket"] == "synthetic-ticket"
            return httpx.Response(302, headers={"location": "/?token=synthetic-token&x=1"})
        if path == "/":
            return httpx.Response(200, text="app")
        assert path == "/api/getInfo" and "cookie" not in request.headers
        assert request.headers["authorization"] == "Bearer synthetic-token"
        return httpx.Response(200, json={"code": 200, "user": {"userId": "0007"}})

    async def run():
        protocol = SchoolProtocol(
            SchoolTransport(Limiter(), transport=httpx.MockTransport(handler), resolve=False)
        )
        challenge = await protocol.challenge()
        assert await protocol.authenticate(
            "synthetic", " test ", {"uid": challenge.uid, "cookies": challenge.cookies}, "3"
        ) == ("synthetic-token", "0007")

    asyncio.run(run())
    assert len(seen) == 6


@pytest.mark.parametrize(
    "target",
    [
        "http://sdgl.hbue.edu.cn/",
        "https://127.0.0.1/",
        "https://rz.hbue.edu.cn.evil.test/",
        "https://user@sdgl.hbue.edu.cn/",
    ],
)
def test_disallowed_redirect_is_never_requested(target):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": target})

    async def run():
        protocol = SchoolProtocol(
            SchoolTransport(Limiter(), transport=httpx.MockTransport(handler), resolve=False)
        )
        with pytest.raises(ApiError):
            await protocol.challenge()

    asyncio.run(run())
    assert len(calls) == 1


def test_non_json_authenticated_read_does_not_become_empty_data():
    async def run():
        protocol = SchoolProtocol(
            SchoolTransport(
                Limiter(),
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(200, text="<html>login</html>")
                ),
                resolve=False,
            )
        )
        with pytest.raises(ApiError) as error:
            await protocol.read("/getInfo", "synthetic", {})
        assert error.value.code == "SCHOOL_REAUTH_REQUIRED"

    asyncio.run(run())
