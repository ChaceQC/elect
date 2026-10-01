"""有界 SMTP 传输；仅明确未接收可重试，正文边界后断连为 unknown。"""

import asyncio
import base64
import re
import ssl
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, SecretStr, model_validator

from services.common.dto import DTO
from services.common.runtime import read_secret

from .connection import connect


class SmtpConfig(DTO):
    host: Annotated[str, Field(min_length=1, max_length=253, pattern=r"^[a-zA-Z0-9.-]+$")]
    port: Annotated[int, Field(ge=1, le=65535)]
    sender: Annotated[str, Field(min_length=3, max_length=254)]
    username: str
    password: SecretStr
    tls: Literal["implicit", "starttls", "test_plain"] = "implicit"
    proxy_url: SecretStr | None = None

    @model_validator(mode="after")
    def headers(self):
        if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", self.sender):
            raise ValueError("发件地址格式错误")
        self.sender.encode("ascii")
        if any(character in self.username for character in "\r\n\x00"):
            raise ValueError("SMTP 用户名格式错误")
        if self.proxy_url:
            from urllib.parse import urlsplit

            proxy = urlsplit(self.proxy_url.get_secret_value())
            if (
                proxy.scheme != "http"
                or not proxy.hostname
                or proxy.path not in {"", "/"}
                or proxy.query
                or proxy.fragment
            ):
                raise ValueError("SMTP 代理只接受固定 HTTP CONNECT 地址")
        return self

    @classmethod
    def load(cls, path):
        try:
            config = cls.model_validate_json(read_secret(path))
            if config.tls == "test_plain" or config.host.endswith(".invalid"):
                raise ValueError("正式 SMTP 必须验证 TLS")
            return config
        except Exception:
            raise RuntimeError("SMTP Secret 缺失或格式错误") from None


@dataclass(frozen=True)
class DeliveryOutcome:
    state: str
    error_code: str | None = None


class BodyDenied(Exception):
    pass


class SmtpRejected(Exception):
    def __init__(self, code):
        self.code = code


async def response(reader):
    for _ in range(100):
        line = await reader.readline()
        if len(line) < 4 or not line[:3].isdigit():
            raise OSError("无效 SMTP 响应")
        code = int(line[:3])
        if line[3:4] == b" ":
            return code
        if line[3:4] != b"-":
            raise OSError("无效 SMTP 多行响应")
    raise OSError("SMTP 响应过多")


async def command(writer, reader, value, expected):
    writer.write(value.encode("ascii") + b"\r\n")
    await writer.drain()
    code = await response(reader)
    if code not in expected:
        raise SmtpRejected(code)


class SmtpTransport:
    def __init__(self, config, *, test=False):
        if config.tls == "test_plain" and (
            not test or config.host not in {"127.0.0.1", "localhost"}
        ):
            raise ValueError("明文 SMTP 仅允许显式本机测试模拟器")
        self.config = config

    async def send(self, recipient, message, before_body):
        if (
            not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", recipient)
            or not recipient.isascii()
        ):
            return DeliveryOutcome("failed", "SMTP_INVALID_RECIPIENT")
        writer, body_started, phase = None, False, "CONNECT"
        try:
            async with asyncio.timeout(20):
                context = ssl.create_default_context()
                reader, writer = await connect(self.config)
                code = await response(reader)
                if code != 220:
                    raise SmtpRejected(code)
                await command(writer, reader, "EHLO elect.invalid", {250})
                if self.config.tls == "starttls":
                    phase = "TLS"
                    await command(writer, reader, "STARTTLS", {220})
                    await writer.start_tls(context, server_hostname=self.config.host)
                    await command(writer, reader, "EHLO elect.invalid", {250})
                if self.config.username:
                    phase = "AUTH"
                    auth = base64.b64encode(
                        b"\x00"
                        + self.config.username.encode()
                        + b"\x00"
                        + self.config.password.get_secret_value().encode()
                    ).decode()
                    try:
                        await command(writer, reader, "AUTH PLAIN " + auth, {235})
                    except SmtpRejected as error:
                        if error.code not in {500, 502, 504}:
                            raise
                        await command(writer, reader, "AUTH LOGIN", {334})
                        await command(
                            writer,
                            reader,
                            base64.b64encode(self.config.username.encode()).decode(),
                            {334},
                        )
                        await command(
                            writer,
                            reader,
                            base64.b64encode(
                                self.config.password.get_secret_value().encode()
                            ).decode(),
                            {235},
                        )
                phase = "ENVELOPE"
                await command(writer, reader, f"MAIL FROM:<{self.config.sender}>", {250})
                await command(writer, reader, f"RCPT TO:<{recipient}>", {250, 251})
                await command(writer, reader, "DATA", {354})
                await before_body()
                body_started = True
                # EmailMessage 已规范 CRLF；SMTP dot-stuffing 不修改持久 Message-ID。
                stuffed = b"\r\n".join(
                    b"." + line if line.startswith(b".") else line
                    for line in message.split(b"\r\n")
                )
                writer.write(stuffed.rstrip(b"\r\n") + b"\r\n.\r\n")
                await writer.drain()
                code = await response(reader)
                if code != 250:
                    raise SmtpRejected(code)
                return DeliveryOutcome("sent")
        except BodyDenied:
            return DeliveryOutcome("cancelled", "SEND_PERMIT_EXPIRED")
        except SmtpRejected as error:
            return DeliveryOutcome(
                "retry_wait" if 400 <= error.code < 500 else "failed", f"SMTP_{error.code}"
            )
        except ValueError:
            return DeliveryOutcome(
                "delivery_unknown" if body_started else "failed", "SMTP_INVALID_RESPONSE"
            )
        except (OSError, TimeoutError) as error:
            return DeliveryOutcome(
                "delivery_unknown" if body_started else "retry_wait",
                "SMTP_CONNECTION_LOST"
                if body_started
                else f"SMTP_{phase}_{type(error).__name__.upper()}",
            )
        finally:
            if writer:
                writer.close()
                # 不等 QUIT 确认，避免把已明确接受误判为连接未知。
