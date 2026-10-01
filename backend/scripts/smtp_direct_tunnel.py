"""一次性本地验收专用直连通道：仅一个 SMTP 目标、随机认证，不修改系统代理。"""

import asyncio
import base64
import ipaddress
import secrets
import socket

import httpx


class DirectTunnel:
    def __init__(self, config, gateway, interface):
        self.config, self.gateway, self.interface = config, gateway, interface
        self.token = secrets.token_urlsafe(32)
        self.opened = False

    async def __aenter__(self):
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            value = (
                await client.get(
                    "https://dns.alidns.com/resolve", params={"name": self.config.host, "type": "A"}
                )
            ).json()
        self.address = next(
            row["data"]
            for row in value.get("Answer", [])
            if row.get("type") == 1 and ipaddress.ip_address(row["data"]).is_global
        )
        self.server = await asyncio.start_server(self.handle, self.gateway, 0)
        port = self.server.sockets[0].getsockname()[1]
        self.url = f"http://elect:{self.token}@{self.gateway}:{port}"
        return self

    async def __aexit__(self, *args):
        self.server.close()
        await self.server.wait_closed()

    async def handle(self, reader, writer):
        remote, sock = None, None
        try:
            async with asyncio.timeout(40):
                line = await reader.readline()
                expected = f"CONNECT {self.config.host}:{self.config.port} HTTP/1.1\r\n".encode()
                headers = []
                for _ in range(20):
                    header = await reader.readline()
                    if header == b"\r\n":
                        break
                    headers.append(header)
                auth = (
                    b"Proxy-Authorization: Basic "
                    + base64.b64encode(f"elect:{self.token}".encode())
                    + b"\r\n"
                )
                if line != expected or auth not in headers or self.opened:
                    writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                    await writer.drain()
                    return
                self.opened = True
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(
                    socket.SOL_SOCKET, socket.SO_BINDTODEVICE, self.interface.encode() + b"\x00"
                )
                sock.setblocking(False)
                await asyncio.get_running_loop().sock_connect(
                    sock, (self.address, self.config.port)
                )
                upstream, remote = await asyncio.open_connection(sock=sock)
                sock = None
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()

                async def copy(source, target):
                    while data := await source.read(65536):
                        target.write(data)
                        await target.drain()

                a = asyncio.create_task(copy(reader, remote))
                b = asyncio.create_task(copy(upstream, writer))
                await asyncio.wait({a, b}, return_when=asyncio.FIRST_COMPLETED)
                a.cancel()
                b.cancel()
                await asyncio.gather(a, b, return_exceptions=True)
        except Exception:
            # 禁止输出目标、令牌、协议内容或认证材料。
            pass
        finally:
            writer.close()
            if remote:
                remote.close()
            if sock:
                sock.close()
