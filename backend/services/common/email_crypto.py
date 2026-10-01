"""邮箱使用独立多版本密钥加密，AAD 绑定用户和邮箱版本。"""

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services.common.runtime import read_secret


class EmailCrypto:
    def __init__(self, current, keys):
        if current not in keys or any(len(value) != 32 for value in keys.values()):
            raise RuntimeError("邮箱加密密钥格式错误")
        self.current, self.keys = current, keys

    @classmethod
    def load(cls, path):
        try:
            value = json.loads(read_secret(path))
            return cls(
                value["current"],
                {key: base64.b64decode(raw, validate=True) for key, raw in value["keys"].items()},
            )
        except Exception:
            raise RuntimeError("邮箱加密密钥缺失或格式错误") from None

    @staticmethod
    def aad(owner, version):
        return f"elect:monitor-email:{owner}:{version}".encode()

    def seal(self, value, owner, version):
        if value is None:
            return None
        nonce = os.urandom(12)
        encrypted = AESGCM(self.keys[self.current]).encrypt(
            nonce, value.encode(), self.aad(owner, version)
        )
        return json.dumps(
            {
                "key": self.current,
                "data": base64.b64encode(nonce + encrypted).decode(),
            }
        ).encode()

    def open(self, value, owner, version):
        if value is None:
            return None
        try:
            envelope = json.loads(value)
            raw = base64.b64decode(envelope["data"], validate=True)
            return (
                AESGCM(self.keys[envelope["key"]])
                .decrypt(raw[:12], raw[12:], self.aad(owner, version))
                .decode()
            )
        except Exception:
            raise RuntimeError("邮箱无法解密，请检查密钥版本") from None
