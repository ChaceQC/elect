"""显式导入本机邮件凭据到受限 Secret；不发送邮件或输出地址。"""

import argparse
import secrets
from pathlib import Path

from .email_auth import read_email_auth
from .provision import write_file
from .smtp_direct_proxy import DirectProxyConfig
from .upgrade_auth import replace_secret


def configure(args):
    directory = args.directory
    target = directory / "smtp_credentials"
    if (
        not directory.is_absolute() or directory.is_symlink()
        or target.is_symlink() or not target.is_file()
    ):
        raise ValueError("需要已有受限 SMTP Secret 目录")
    config, _ = read_email_auth(args.email_auth_file)
    document = config.model_dump(mode="json")
    document["password"] = config.password.get_secret_value()
    if args.direct_interface:
        target_proxy = directory / "smtp_direct_proxy"
        if target_proxy.exists() or target_proxy.is_symlink():
            raise ValueError("已有直连 Secret，拒绝覆盖")
        proxy = DirectProxyConfig(
            host=config.host, port=config.port, interface=args.direct_interface,
            listen_host=args.proxy_bind, listen_port=args.proxy_port,
            token=secrets.token_urlsafe(32),
        )
        proxy_document = proxy.model_dump(mode="json")
        proxy_document["token"] = proxy.token.get_secret_value()
        write_file(directory, target_proxy.name, proxy_document, uid=0)
        document["proxy_url"] = (
            f"http://elect:{proxy.token.get_secret_value()}@{proxy.listen_host}:{proxy.listen_port}"
        )
    replace_secret(target, document)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email-auth-file", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--direct-interface")
    parser.add_argument("--proxy-bind", default="172.17.0.1")
    parser.add_argument("--proxy-port", type=int, default=16874)
    try:
        configure(parser.parse_args())
    except Exception:
        raise SystemExit("SMTP Secret 配置失败；检查文件、格式和权限，未输出敏感信息") from None
    print("SMTP Secret 已配置；未输出凭据，请重建邮件服务后检查 TLS/认证。")


if __name__ == "__main__":
    main()
