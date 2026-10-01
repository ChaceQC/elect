"""SMTP 直连或显式 HTTP CONNECT；TLS 始终验证最终 SMTP 服务证书。"""

import asyncio
import base64
import ssl
from urllib.parse import unquote, urlsplit


async def connect(config):
    context = ssl.create_default_context()
    if config.proxy_url is None:
        return await asyncio.open_connection(
            config.host,
            config.port,
            ssl=context if config.tls == "implicit" else None,
            server_hostname=config.host if config.tls == "implicit" else None,
            happy_eyeballs_delay=0.25,
        )
    proxy = urlsplit(config.proxy_url.get_secret_value())
    reader, writer = await asyncio.open_connection(proxy.hostname, proxy.port or 80)
    try:
        address = f"{config.host}:{config.port}"
        headers = [f"CONNECT {address} HTTP/1.1", f"Host: {address}"]
        if proxy.username:
            auth = base64.b64encode(
                f"{unquote(proxy.username)}:{unquote(proxy.password or '')}".encode()
            ).decode()
            headers.append("Proxy-Authorization: Basic " + auth)
        writer.write(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
        await writer.drain()
        status = await reader.readline()
        if status.split()[1:2] != [b"200"]:
            raise OSError("SMTP 代理拒绝连接")
        for _ in range(100):
            if await reader.readline() == b"\r\n":
                break
        else:
            raise OSError("SMTP 代理响应无效")
        if config.tls == "implicit":
            await writer.start_tls(context, server_hostname=config.host)
        return reader, writer
    except BaseException:
        writer.close()
        raise
