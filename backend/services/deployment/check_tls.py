"""无网络 TLS 预检，输出分类结果，不打印证书、私钥或路径。"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from services.common.config_contract import DeploymentConfig


def matches_dns(pattern: str, domain: str) -> bool:
    pattern = pattern.lower()
    if pattern.startswith("*."):
        return domain.count(".") == pattern.count(".") and domain.endswith(pattern[1:])
    return pattern == domain


def check_tls(domain: str, cert_file: Path, key_file: Path, now=None):
    DeploymentConfig(
        domain=domain, tls_cert_file=cert_file, tls_key_file=key_file, secrets_dir=Path("/unused")
    )
    certs = x509.load_pem_x509_certificates(cert_file.read_bytes())
    if not certs:
        raise ValueError("missing_certificate")
    instant = now or datetime.now(UTC)
    for cert in certs:
        if not cert.not_valid_before_utc <= instant < cert.not_valid_after_utc:
            raise ValueError("certificate_outside_validity")
    leaf = certs[0]
    names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    if not any(matches_dns(name, domain) for name in names.get_values_for_type(x509.DNSName)):
        raise ValueError("san_mismatch")
    key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    encoding, format_ = serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    if key.public_key().public_bytes(encoding, format_) != leaf.public_key().public_bytes(
        encoding,
        format_,
    ):
        raise ValueError("key_mismatch")


def main():
    try:
        check_tls(
            os.environ["ELECT_DOMAIN"], Path("/run/secrets/tls_cert"), Path("/run/secrets/tls_key")
        )
    except Exception:
        print("TLS 预检失败：检查域名、文件、有效期、SAN 与密钥配对", file=sys.stderr)
        sys.exit(1)
    print("TLS 预检通过")


if __name__ == "__main__":
    main()
