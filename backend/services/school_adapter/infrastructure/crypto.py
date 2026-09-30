"""Adapter 独占的 AES-256-GCM 信封与多版本账号 HMAC。"""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services.common.runtime import read_secret


@dataclass(repr=False)
class KeyRing:
    current: str
    keys: dict[str, bytes] = field(repr=False)

    @classmethod
    def load(cls, path):
        try:
            value = json.loads(read_secret(path))
            keys = {
                name: base64.b64decode(raw, validate=True) for name, raw in value["keys"].items()
            }
            if value["current"] not in keys or not all(len(key) == 32 for key in keys.values()):
                raise ValueError()
            return cls(value["current"], keys)
        except Exception:
            raise RuntimeError("加密密钥文件缺失或格式错误") from None


class EnvelopeCrypto:
    def __init__(self, ring: KeyRing):
        self.ring = ring

    def encrypt(self, payload, aad: str):
        dek, nonce, wrap_nonce = os.urandom(32), os.urandom(12), os.urandom(12)
        version = self.ring.current
        return {
            "ciphertext": AESGCM(dek).encrypt(nonce, json.dumps(payload).encode(), aad.encode()),
            "nonce": nonce,
            "wrapped_dek": wrap_nonce
            + AESGCM(self.ring.keys[version]).encrypt(wrap_nonce, dek, ("dek:" + aad).encode()),
            "kek_version": version,
            "algorithm": "AES-256-GCM",
        }

    def decrypt(self, envelope, aad: str):
        try:
            if envelope["algorithm"] != "AES-256-GCM":
                raise ValueError()
            wrapped = envelope["wrapped_dek"]
            dek = AESGCM(self.ring.keys[envelope["kek_version"]]).decrypt(
                wrapped[:12], wrapped[12:], ("dek:" + aad).encode()
            )
            return json.loads(
                AESGCM(dek).decrypt(envelope["nonce"], envelope["ciphertext"], aad.encode())
            )
        except Exception:
            raise RuntimeError("凭据解密失败，请检查密钥版本与认证数据") from None

    def seal(self, payload, aad: str) -> bytes:
        value = self.encrypt(payload, aad)
        for key in ("ciphertext", "nonce", "wrapped_dek"):
            value[key] = base64.b64encode(value[key]).decode()
        return json.dumps(value).encode()

    def open(self, raw: bytes, aad: str):
        try:
            value = json.loads(raw)
            for key in ("ciphertext", "nonce", "wrapped_dek"):
                value[key] = base64.b64decode(value[key], validate=True)
            return self.decrypt(value, aad)
        except Exception:
            raise RuntimeError("加密缓存无法解密") from None


def lookup_aliases(ring: KeyRing, school: str, student_id: str):
    value = json.dumps([school, student_id], separators=(",", ":")).encode()
    return {
        version: hmac.new(key, value, hashlib.sha256).hexdigest()
        for version, key in ring.keys.items()
    }


def credential_aad(credential, owner, version):
    return json.dumps(["hbue", str(credential), str(owner), version], separators=(",", ":"))
