from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from services.deployment.check_tls import check_tls, matches_dns


def certificate(tmp_path, *, domain="elect.example.edu", expired=False, future=False):
    now = datetime.now(UTC)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + timedelta(days=1) if future else now - timedelta(days=2))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=3))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path


def test_valid_and_wildcard_certificates(tmp_path):
    paths = certificate(tmp_path, domain="*.example.edu")
    check_tls("elect.example.edu", *paths)
    assert not matches_dns("*.example.edu", "deep.elect.example.edu")
    assert not matches_dns("*.example.edu", "example.edu")


@pytest.mark.parametrize(
    "options",
    [
        {"expired": True},
        {"future": True},
        {"domain": "other.example.edu"},
    ],
)
def test_reject_invalid_certificates(tmp_path, options):
    with pytest.raises(ValueError):
        check_tls("elect.example.edu", *certificate(tmp_path, **options))


def test_reject_mismatched_key_and_invalid_domain(tmp_path):
    cert_path, key_path = certificate(tmp_path)
    key_path.write_bytes(
        rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    with pytest.raises(ValueError, match="key_mismatch"):
        check_tls("elect.example.edu", cert_path, key_path)
    with pytest.raises(ValueError):
        check_tls("elect.example.edu; return 200", cert_path, key_path)
