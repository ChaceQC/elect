"""本地连接诊断：只检查 TLS/响应，不认证、不发送，不输出配置内容。"""

import argparse
import asyncio
import json
import ssl
from pathlib import Path

from scripts.email_auth_file import read_email_auth
from services.notification.smtp import command, response


async def probe(path, mode=None):
    config, _ = read_email_auth(path)
    if mode:
        config = config.model_copy(update={"tls": mode})
    writer = None
    try:
        async with asyncio.timeout(10):
            context = ssl.create_default_context()
            reader, writer = await asyncio.open_connection(
                config.host,
                config.port,
                ssl=context if config.tls == "implicit" else None,
                server_hostname=config.host if config.tls == "implicit" else None,
            )
            if await response(reader) != 220:
                raise RuntimeError("非SMTP欢迎响应")
            await command(writer, reader, "EHLO elect.invalid", {250})
            if config.tls == "starttls":
                await command(writer, reader, "STARTTLS", {220})
                await writer.start_tls(context, server_hostname=config.host)
            return {"smtp_connection": "passed", "tls_verified": True, "tls_mode": config.tls}
    except Exception as error:
        return {
            "smtp_connection": "failed",
            "failure_class": type(error).__name__,
            "tls_mode": config.tls,
        }
    finally:
        if writer:
            writer.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email-auth-file", type=Path, required=True)
    parser.add_argument("--tls-mode", choices=["implicit", "starttls"])
    args = parser.parse_args()
    print(json.dumps(asyncio.run(probe(args.email_auth_file, args.tls_mode))))


if __name__ == "__main__":
    main()
