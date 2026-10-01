"""离线生成全新部署的受限 Secret；已有目录拒绝覆盖。"""

import argparse
import base64
import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID

from services.common.config_contract import DeploymentConfig
from services.common.migration_runtime import DATABASES
from services.common.runtime import SERVICES


def write_file(directory, name, value, uid=10001):
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    # O_EXCL 防止覆写已有凭据；生成容器以 root 运行，仅输出到显式挂载目录。
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(fd, "w") as stream:
        stream.write(raw + "\n")
    os.chown(path, uid, uid)


def rabbitmq_password_hash(password):
    salt = secrets.token_bytes(4)
    return base64.b64encode(salt + hashlib.sha256(salt + password.encode()).digest()).decode()


def keys_and_trust():
    private, trust = {}, {}
    for service in SERVICES:
        key = ed25519.Ed25519PrivateKey.generate()
        private[service] = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        trust[f"{service}-v1"] = {
            "issuer": service,
            "public_key": key.public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            .decode(),
            "audiences": list(SERVICES),
            "scopes": ["foundation:read", "event:audit"]
            + {
                "gateway": [
                    "identity:browser",
                    "session:introspect",
                    "captcha:create",
                    "room:browser",
                    "monitor:browser",
                ],
                "identity": [
                    "credential:authenticate",
                    "credential:activate",
                    "credential:read",
                    "monitor:credential",
                    "credential:control-read",
                    "credential:revoke",
                ],
                "room": [
                    "school:rooms",
                    "school:history",
                    "school:binding",
                    "monitor:retarget",
                    "credential:control-read",
                ],
                "monitoring": [
                    "room:control",
                    "room:query",
                    "school:collect",
                    "credential:control-read",
                ],
                "school_adapter": [
                    "monitor:credential-read",
                    "monitor:retarget-read",
                    "room:remove-read",
                    "room:query",
                    "room:balance-commit",
                ],
                "notification": ["monitor:authorize-send", "monitor:alert-read"],
            }.get(service, []),
        }
    return private, trust


def provision_databases(directory):
    root, probe = secrets.token_hex(24), secrets.token_hex(24)
    write_file(directory, "mysql_root_password", root, 999)
    write_file(
        directory,
        "mysql_probe.cnf",
        f"[client]\nuser=elect_probe\npassword={probe}\nhost=127.0.0.1\n",
        999,
    )
    sql = [f"CREATE USER 'elect_probe'@'%' IDENTIFIED BY '{probe}';"]
    app_urls, ddl_urls = {}, {}
    for domain, database in DATABASES.items():
        short = database.removeprefix("elect_")
        sql.append(
            f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
        )
        for role in ("app", "ddl"):
            password, account = secrets.token_hex(24), f"elect_{short}_{role}"
            sql.append(f"CREATE USER '{account}'@'%' IDENTIFIED BY '{password}';")
            grants = "SELECT, INSERT, UPDATE, DELETE"
            if role == "ddl":
                grants += ", CREATE, ALTER, DROP, INDEX, REFERENCES"
            sql.append(f"GRANT {grants} ON `{database}`.* TO '{account}'@'%';")
            target = app_urls if role == "app" else ddl_urls
            target[domain] = f"mysql+asyncmy://{account}:{password}@mysql:3306/{database}"
    write_file(directory, "mysql_bootstrap.sql", "\n".join(sql), 999)
    write_file(directory, "migration_runtime.json", {"domains": ddl_urls})
    return app_urls


def provision_transport(directory):
    users, permissions, redis_lines = [], [], ["user default off"]
    mq_urls, redis_urls = {}, {}
    for service in DATABASES:
        password = secrets.token_hex(24)
        users.append(
            {
                "name": service,
                "password_hash": rabbitmq_password_hash(password),
                "hashing_algorithm": "rabbit_password_hashing_sha256",
                "tags": [],
            }
        )
        permissions.append(
            {
                "user": service,
                "vhost": "elect",
                "configure": "^elect\\.(events|dead|audit|audit\\.dead)$"
                if service == "audit"
                else "^elect\\.events$",
                "write": "^elect\\.(events|dead|audit|audit\\.dead)$"
                if service == "audit"
                else "^elect\\.events$",
                "read": "^elect\\.(events|dead|audit|audit\\.dead)$"
                if service == "audit"
                else "^$",
            }
        )
        mq_urls[service] = f"amqp://{service}:{password}@rabbitmq:5672/elect"
        password = secrets.token_hex(24)
        redis_lines.append(
            f"user {service} on >{password} ~{service}:* +@read +@write +ping -@dangerous"
            + (" +eval +time" if service == "school_adapter" else "")
        )
        redis_urls[service] = f"redis://{service}:{password}@redis:6379/0"
    probe = secrets.token_hex(24)
    redis_lines.append(f"user probe on >{probe} +ping")
    write_file(directory, "redis_users.acl", "\n".join(redis_lines), 999)
    write_file(directory, "redis_probe", probe, 999)
    write_file(
        directory,
        "rabbitmq.conf",
        "listeners.tcp.default = 5672\n"
        "management.load_definitions = /run/secrets/rabbitmq_definitions\n"
        "loopback_users.guest = true\n",
        100,
    )
    definitions = {
        "vhosts": [{"name": "elect"}],
        "users": users,
        "permissions": permissions,
        "queues": [
            {
                "name": f"elect.{service}.credentials",
                "vhost": "elect",
                "durable": True,
                "auto_delete": False,
                "arguments": {},
            }
            for service in ["identity", "monitoring"]
        ],
        "bindings": [
            {
                "source": "elect.events",
                "vhost": "elect",
                "destination": f"elect.{service}.credentials",
                "destination_type": "queue",
                "routing_key": event,
                "arguments": {},
            }
            for service in ["identity", "monitoring"]
            for event in ["credential.updated", "credential.revoked", "credential.requires_reauth"]
        ],
        "exchanges": [
            {
                "name": "elect.events",
                "vhost": "elect",
                "type": "topic",
                "durable": True,
                "auto_delete": False,
                "internal": False,
                "arguments": {},
            }
        ],
        "topic_permissions": [
            {
                "user": service,
                "vhost": "elect",
                "exchange": "elect.events",
                "write": "^(audit\\.recorded|credential\\.(updated|requires_reauth|revoked))$"
                if service == "school_adapter"
                else "^audit\\.recorded$",
                "read": "^audit\\.recorded$",
            }
            for service in DATABASES
        ],
    }
    from .query_queues import configure

    configure(definitions)
    write_file(directory, "rabbitmq_definitions.json", definitions, 100)
    return mq_urls, redis_urls


def test_certificate(directory, domain):
    DeploymentConfig(
        domain=domain,
        tls_cert_file=Path("/unused"),
        tls_key_file=Path("/unused"),
        secrets_dir=directory,
    )
    key, now = rsa.generate_private_key(public_exponent=65537, key_size=2048), datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ELECT temporary test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    write_file(
        directory, "tls/fullchain.pem", cert.public_bytes(serialization.Encoding.PEM).decode(), 0
    )
    write_file(
        directory,
        "tls/privkey.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        0,
    )


def provision(directory: Path, test_domain=None):
    if not directory.is_absolute() or directory.is_symlink():
        raise ValueError("输出须是非符号链接的绝对目录")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError("输出目录非空，拒绝覆盖 Secret")
    directory.chmod(0o700)
    private, trust = keys_and_trust()
    app_urls = provision_databases(directory)
    amqp_urls, redis_urls = provision_transport(directory)
    from .auth_secrets import provision_auth

    provision_auth(directory, write_file)
    for service in SERVICES:
        runtime = {
            "schema_version": 1,
            "service": service,
            "key_id": f"{service}-v1",
            "signing_key": private[service],
            "trust_bundle": trust,
        }
        if service != "gateway":
            runtime.update(
                db_url=app_urls[service], amqp_url=amqp_urls[service], redis_url=redis_urls[service]
            )
        write_file(directory, f"{service}_runtime.json", runtime)
    if test_domain:
        test_certificate(directory, test_domain)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--test-tls-domain", help="仅显式测试生成两天自签证书，不能用于正式部署")
    args = parser.parse_args()
    try:
        provision(args.output_dir, args.test_tls_domain)
    except Exception:
        raise SystemExit(
            "Secret 生成失败：检查空目录、权限和测试域名；已写文件不自动覆写"
        ) from None
    print("Secret 已生成；未输出凭据。正式部署请配置受信任的证书链与私钥。")


if __name__ == "__main__":
    main()
