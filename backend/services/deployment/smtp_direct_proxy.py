"""仅指定 SMTP 的认证 CONNECT 通道；出口绑定物理网卡，正文 TLS 由 Worker 验证。"""

import argparse
import asyncio
import base64
import ipaddress
import os
import secrets
import socket
from typing import Annotated

import httpx
from pydantic import Field, SecretStr, model_validator

from services.common.dto import DTO
from services.common.runtime import read_secret


class DirectProxyConfig(DTO):
    host: Annotated[str, Field(pattern=r"^[a-zA-Z0-9.-]{1,253}$")]
    port: Annotated[int, Field(ge=1, le=65535)]
    interface: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_.-]{1,15}$")]
    listen_host: str
    listen_port: Annotated[int, Field(ge=1, le=65535)]
    token: SecretStr

    @model_validator(mode="after")
    def restricted_listener(self):
        if ipaddress.IPv4Address(self.listen_host) not in ipaddress.ip_network("172.16.0.0/12"):
            raise ValueError("SMTP 通道仅监听本机 Docker 私网地址")
        if len(self.token.get_secret_value()) < 32:
            raise ValueError("SMTP 通道需要独立的随机认证")
        return self


def load_config():
    try:
        return DirectProxyConfig.model_validate_json(
            read_secret(os.environ["ELECT_SMTP_DIRECT_CONFIG_FILE"])
        )
    except Exception:
        raise RuntimeError("SMTP 直连 Secret 缺失或校验失败") from None


async def authorized(reader, config):
    expected = f"CONNECT {config.host}:{config.port} HTTP/1.1\r\n".encode()
    if await reader.readline() != expected:
        return False
    authentication = b"Basic " + base64.b64encode(
        f"elect:{config.token.get_secret_value()}".encode()
    )
    valid = False
    for _ in range(20):
        header = await reader.readline()
        if header == b"\r\n":
            return valid
        if not header:
            return False
        name, separator, value = header.partition(b":")
        if separator and name.lower() == b"proxy-authorization":
            valid = secrets.compare_digest(value.strip(), authentication)
    return False


async def open_direct(config):
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        answer = (await client.get(
            "https://dns.alidns.com/resolve", params={"name": config.host, "type": "A"}
        )).json()
    address = next(
        row["data"] for row in answer.get("Answer", [])
        if row.get("type") == 1 and ipaddress.ip_address(row["data"]).is_global
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_BINDTODEVICE, config.interface.encode() + b"\x00"
        )
        sock.setblocking(False)
        await asyncio.get_running_loop().sock_connect(sock, (address, config.port))
        return await asyncio.open_connection(sock=sock)
    except BaseException:
        sock.close()
        raise


async def copy(source, target):
    while data := await source.read(65536):
        target.write(data)
        await target.drain()


async def handle(reader, writer, config):
    remote, tasks = None, []
    try:
        async with asyncio.timeout(40):
            if not await authorized(reader, config):
                writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                await writer.drain()
                return
            upstream, remote = await open_direct(config)
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            tasks = [asyncio.create_task(copy(reader, remote)),
                     asyncio.create_task(copy(upstream, writer))]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except Exception:
        # 目标、认证、协议与正文不能进入日志。
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        writer.close()
        if remote:
            remote.close()


async def serve(config):
    server = await asyncio.start_server(
        lambda reader, writer: handle(reader, writer, config),
        config.listen_host, config.listen_port, limit=8192,
    )
    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--healthcheck", action="store_true")
    args = parser.parse_args()
    config = load_config()
    if args.healthcheck:
        with socket.create_connection((config.listen_host, config.listen_port), timeout=3):
            return
    asyncio.run(serve(config))


if __name__ == "__main__":
    main()
