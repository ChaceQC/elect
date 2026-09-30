"""UUIDv7 的 API/BINARY(16) 编解码；不包含领域模型。"""

from uuid import UUID

from uuid6 import uuid7


def new_id() -> UUID:
    return uuid7()


def encode_id(value: UUID) -> bytes:
    return value.bytes


def decode_id(value: bytes) -> UUID:
    return UUID(bytes=value)
