"""T2 → T3 控制基础的离线 Secret/ACL 升级，保留现有连接凭据与密钥。"""

import argparse
import base64
import json
import secrets
from pathlib import Path

from services.monitoring.email_crypto import EmailCrypto

from .provision import write_file
from .upgrade_auth import replace_secret

SCOPES = {
    "gateway": ["monitor:browser", "payment:browser"],
    "identity": ["monitor:credential", "credential:control-read", "credential:revoke"],
    "room": ["monitor:retarget", "school:binding", "school:history", "credential:control-read"],
    "monitoring": ["room:control", "room:query", "school:collect", "credential:control-read"],
    "school_adapter": [
        "monitor:credential-read",
        "monitor:retarget-read",
        "room:remove-read",
        "room:query",
        "room:balance-commit",
    ],
    "notification": ["monitor:authorize-send", "monitor:alert-read"],
    "payment": ["room:browser", "room:query", "credential:control-read", "school:payment"],
}


def upgrade(directory):
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("目录必须是现有 Secret 绝对目录")
    files = sorted(
        p for p in directory.glob("*_runtime.json") if p.name != "migration_runtime.json"
    )
    if len(files) != 8 or not (directory / "internal_ca.pem").is_file():
        raise ValueError("需要完整的 T2 Secret 目录")
    documents = [json.loads(path.read_text()) for path in files]
    key = directory / "monitoring_encryption_key_bundle"
    if key.is_symlink():
        raise ValueError("Secret 不能是符号链接")
    if key.exists():
        EmailCrypto.load(key)
    else:
        write_file(
            directory,
            key.name,
            {"current": "v1", "keys": {"v1": base64.b64encode(secrets.token_bytes(32)).decode()}},
        )
    for path, value in zip(files, documents, strict=True):
        for entry in value["trust_bundle"].values():
            entry["scopes"] = sorted(set(entry["scopes"] + SCOPES.get(entry["issuer"], [])))
        replace_secret(path, value)
    from .notification_secrets import provision_notifications
    provision_notifications(directory)
    definitions = directory / "rabbitmq_definitions.json"
    value = json.loads(definitions.read_text())
    for permission in value["topic_permissions"]:
        if permission["user"] == "school_adapter":
            permission["write"] = (
                "^(audit\\.recorded|credential\\.(updated|requires_reauth|revoked))$"
            )
    from .query_queues import configure

    configure(value)
    replace_secret(definitions, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        upgrade(args.directory)
    except Exception:
        raise SystemExit("T3 Secret 升级失败；检查 T2 目录完整性与权限，未输出敏感信息") from None
    print("T3 控制密钥/服务权限升级完成；请重建应用服务并执行迁移。")


if __name__ == "__main__":
    main()
