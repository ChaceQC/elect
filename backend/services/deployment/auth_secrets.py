"""首次离线 provisioning 的认证 Secret 与内部服务器证书。"""

import base64
import secrets
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def provision_auth(directory, write):
    from .notification_secrets import provision_notifications
    provision_notifications(directory)
    for name in [
        "school_kek_bundle",
        "school_lookup_hmac_bundle",
        "monitoring_encryption_key_bundle",
    ]:
        write(
            directory,
            name,
            {"current": "v1", "keys": {"v1": base64.b64encode(secrets.token_bytes(32)).decode()}},
        )
    write(directory, "identity_session_pepper", base64.b64encode(secrets.token_bytes(32)).decode())
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ELECT internal CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, True, True, False, False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    write(directory, "internal_ca.pem", ca.public_bytes(serialization.Encoding.PEM).decode())
    # CA 私钥仅保存到受限离线目录，不挂载到任何运行服务。
    write(
        directory,
        "internal_ca_key.pem",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode(),
        0,
    )
    for service in ["identity", "school-adapter"]:
        server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, service)])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(name)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=90))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(service), x509.DNSName("localhost")]),
                False,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .sign(key, hashes.SHA256())
        )
        write(
            directory,
            f"{service}_tls_cert.pem",
            cert.public_bytes(serialization.Encoding.PEM).decode(),
        )
        write(
            directory,
            f"{service}_tls_key.pem",
            server_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
        )
