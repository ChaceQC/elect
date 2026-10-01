"""本机 TUN 路由诊断：配置只在内存，输出路由类别与连接分类。"""

import argparse
import asyncio
import ipaddress
import json
import socket
import ssl
from pathlib import Path

import httpx
import yaml

from scripts.email_auth_file import read_email_auth
from scripts.smtp_connection_probe import probe
from services.notification.smtp import command, response


async def physical_probe(config, interface):
    writer, sock = None, None
    try:
        async with asyncio.timeout(12):
            async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
                answer = (
                    await client.get(
                        "https://dns.alidns.com/resolve", params={"name": config.host, "type": "A"}
                    )
                ).json()
            address = next(
                row["data"]
                for row in answer.get("Answer", [])
                if row.get("type") == 1 and ipaddress.ip_address(row["data"]).is_global
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode() + b"\x00")
            sock.setblocking(False)
            await asyncio.get_running_loop().sock_connect(sock, (address, config.port))
            context = ssl.create_default_context()
            reader, writer = await asyncio.open_connection(
                sock=sock,
                ssl=context if config.tls == "implicit" else None,
                server_hostname=config.host if config.tls == "implicit" else None,
            )
            sock = None
            if await response(reader) != 220:
                raise RuntimeError()
            await command(writer, reader, "EHLO elect.invalid", {250})
            if config.tls == "starttls":
                await command(writer, reader, "STARTTLS", {220})
                await writer.start_tls(context, server_hostname=config.host)
            return {"physical_smtp_connection": "passed", "tls_verified": True}
    except Exception as error:
        return {"physical_smtp_connection": "failed", "failure_class": type(error).__name__}
    finally:
        if writer:
            writer.close()
        if sock:
            sock.close()


async def diagnose(args):
    smtp, _ = read_email_auth(args.email_auth_file)
    config = yaml.safe_load(args.proxy_config.read_text())
    result = {"tun_enabled": config.get("tun", {}).get("enable"), "mode": config.get("mode")}
    uds = config.get("external-controller-unix")
    if uds:
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(uds=uds),
            base_url="http://local",
            headers={"Authorization": "Bearer " + config.get("secret", "")},
            timeout=2,
        ) as client:
            task = asyncio.create_task(probe(args.email_auth_file))
            for _ in range(20):
                try:
                    connections = (await client.get("/connections")).json().get("connections", [])
                    for item in connections:
                        metadata = item.get("metadata", {})
                        if metadata.get("host") == smtp.host and str(
                            metadata.get("destinationPort")
                        ) == str(smtp.port):
                            chains = item.get("chains", [])
                            result["smtp_route"] = (
                                "DIRECT"
                                if "DIRECT" in chains
                                else "REJECT"
                                if "REJECT" in chains
                                else "PROXY"
                            )
                            result["matched_rule_type"] = item.get("rule")
                except (httpx.HTTPError, ValueError):
                    result["controller_read"] = "unavailable"
                if task.done():
                    break
                await asyncio.sleep(0.1)
            result["ordinary_connection"] = await task
    if args.interface:
        result.update(await physical_probe(smtp, args.interface))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email-auth-file", type=Path, required=True)
    parser.add_argument("--proxy-config", type=Path, required=True)
    parser.add_argument("--interface")
    args = parser.parse_args()
    try:
        result = asyncio.run(diagnose(args))
    except Exception as error:
        result = {"proxy_diagnosis": "failed", "failure_class": type(error).__name__}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
