import io
import os

import pytest
from cryptography.exceptions import InvalidTag

from services.deployment.backup_crypto import CHUNK, decrypt, encrypt, key_from


def backup(payload, key):
    output = io.BytesIO()
    encrypt(io.BytesIO(payload), output, key)
    return output.getvalue()


def test_large_backup_round_trip_preserves_binary_and_is_not_plaintext():
    key, payload = os.urandom(32), b"secret-school-material\0" * (CHUNK // 10)
    encrypted = backup(payload, key)
    assert b"secret-school-material" not in encrypted
    recovered = io.BytesIO()
    assert decrypt(io.BytesIO(encrypted), recovered, key)["kind"] == "mysql_logical"
    assert recovered.getvalue() == payload


@pytest.mark.parametrize("corrupt", ["wrong_key", "truncate", "append", "tamper"])
def test_backup_authentication_rejects_corruption(corrupt):
    key = os.urandom(32)
    encrypted = backup(b"database snapshot", key)
    if corrupt == "wrong_key":
        key = os.urandom(32)
    elif corrupt == "truncate":
        encrypted = encrypted[:-16]
    elif corrupt == "append":
        encrypted += b"untrusted append"
    else:
        encrypted = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises((ValueError, InvalidTag)):
        decrypt(io.BytesIO(encrypted), None, key)


def test_backup_key_requires_private_file_permissions(tmp_path):
    path = tmp_path / "backup.key"
    path.write_bytes(os.urandom(32))
    path.chmod(0o600)
    assert key_from(path)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        key_from(path)
