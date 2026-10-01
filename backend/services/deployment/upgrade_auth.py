"""T1 → T2 离线 Secret 升级，保留数据库/MQ/Redis凭据和全部既有密钥。"""

import argparse
import json
import os
import tempfile
from pathlib import Path

from .auth_secrets import provision_auth
from .provision import provision_transport, write_file

AUTH_FILES = [
    "school_kek_bundle",
    "school_lookup_hmac_bundle",
    "identity_session_pepper",
    "internal_ca.pem",
    "internal_ca_key.pem",
    "identity_tls_cert.pem",
    "identity_tls_key.pem",
    "school-adapter_tls_cert.pem",
    "school-adapter_tls_key.pem",
]
SCOPES = {
    "gateway": ["identity:browser", "session:introspect", "captcha:create", "room:browser"],
    "identity": ["credential:authenticate", "credential:activate", "credential:read"],
    "room": ["school:rooms"],
}


def replace_secret(path, value):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".t2-")
    try:
        os.fchmod(fd, 0o400)
        os.fchown(fd, path.stat().st_uid, path.stat().st_gid)
        with os.fdopen(fd, "w") as stream:
            stream.write(raw.rstrip() + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def upgrade(directory):
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("目录必须是现有 Secret 绝对目录")
    runtimes = list(directory.glob("*_runtime.json"))
    documents = [
        json.loads(path.read_text()) for path in runtimes if path.name != "migration_runtime.json"
    ]
    if len(documents) != 8:
        raise ValueError("缺少八个现有服务 runtime")
    present = [bool((directory / name).is_file()) for name in AUTH_FILES]
    if any(present) and not all(present):
        raise ValueError("认证 Secret 不完整，拒绝混合新旧密钥")
    if not any(present):
        with tempfile.TemporaryDirectory(dir=directory, prefix=".t2-auth-") as temporary:
            stage = Path(temporary)
            provision_auth(stage, write_file)
            for name in AUTH_FILES:
                os.replace(stage / name, directory / name)
    for path, value in zip(
        [p for p in runtimes if p.name != "migration_runtime.json"], documents, strict=True
    ):
        for entry in value["trust_bundle"].values():
            entry["scopes"] = sorted(set(entry["scopes"] + SCOPES.get(entry["issuer"], [])))
        replace_secret(path, value)
    acl = directory / "redis_users.acl"
    lines = []
    for line in acl.read_text().splitlines():
        if line.startswith("user school_adapter "):
            for permission in ["+eval", "+time"]:
                if permission not in line.split():
                    line += " " + permission
        lines.append(line)
    replace_secret(acl, "\n".join(lines))
    definitions = directory / "rabbitmq_definitions.json"
    value = json.loads(definitions.read_text())
    # 仅复用公开声明，不使用生成出的临时密码；现有 users/permissions 始终保留。
    with tempfile.TemporaryDirectory() as temporary:
        provision_transport(Path(temporary))
        declarations = json.loads((Path(temporary) / definitions.name).read_text())
    for category in ["exchanges", "queues", "bindings"]:
        value.setdefault(category, [])
        for item in declarations[category]:
            if item not in value[category]:
                value[category].append(item)
    for permission in value["topic_permissions"]:
        if permission["user"] == "school_adapter":
            permission["write"] = "^(audit\\.recorded|credential\\.(updated|requires_reauth))$"
    replace_secret(definitions, value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        upgrade(args.directory)
    except Exception:
        raise SystemExit(
            "T2 Secret 升级失败；检查完整的现有目录与文件权限，未输出敏感信息"
        ) from None
    print("T2 Secret/权限升级完成；既有密钥与连接凭据保留，请重建 Redis/RabbitMQ 与应用服务。")


if __name__ == "__main__":
    main()
