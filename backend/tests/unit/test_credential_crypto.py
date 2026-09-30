import os

import pytest

from services.school_adapter.infrastructure.crypto import (
    EnvelopeCrypto,
    KeyRing,
    credential_aad,
    lookup_aliases,
)


def test_envelope_binds_owner_version_and_keeps_old_key_readable():
    old, new = os.urandom(32), os.urandom(32)
    crypto = EnvelopeCrypto(KeyRing("v1", {"v1": old}))
    aad = credential_aad("synthetic", "user-a", 1)
    payload = {"student_id": "synthetic", "password": " a password "}
    first, second = crypto.encrypt(payload, aad), crypto.encrypt(payload, aad)
    assert first["ciphertext"] != second["ciphertext"] and first["nonce"] != second["nonce"]
    assert payload["password"].encode() not in first["ciphertext"]
    rotated = EnvelopeCrypto(KeyRing("v2", {"v1": old, "v2": new}))
    assert rotated.decrypt(first, aad) == payload
    for wrong in [
        credential_aad("synthetic", "user-b", 1),
        credential_aad("synthetic", "user-a", 2),
    ]:
        with pytest.raises(RuntimeError):
            rotated.decrypt(first, wrong)
    with pytest.raises(RuntimeError):
        EnvelopeCrypto(KeyRing("v2", {"v2": new})).decrypt(first, aad)
    value = rotated.seal(payload, "school_adapter:test")
    assert rotated.open(value, "school_adapter:test") == payload
    with pytest.raises(RuntimeError):
        rotated.open(value, "school_adapter:other-user")


def test_lookup_keys_are_independent_and_multiple_versions_preserved():
    ring = KeyRing("v2", {"v1": os.urandom(32), "v2": os.urandom(32)})
    aliases = lookup_aliases(ring, "hbue", "000123")
    assert set(aliases) == {"v1", "v2"} and aliases["v1"] != aliases["v2"]
    assert aliases != lookup_aliases(ring, "another-school", "000123")
