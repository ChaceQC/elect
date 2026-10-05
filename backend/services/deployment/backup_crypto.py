"""有序分块 AES-256-GCM；认证头、块序号和终止块，拒绝截断或追加。"""

import argparse
import json
import os
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"ELECT-BACKUP-1\n"
CHUNK = 1024 * 1024


def key_from(path):
    if not path.is_absolute() or path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("备份密钥必须是受限的绝对文件路径")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("备份需要独立的32字节密钥")
    return key


def encrypt(source, target, key, *, kind="mysql_logical"):
    metadata = json.dumps({"kind": kind, "created_at": datetime.now(UTC).isoformat()}).encode()
    header = MAGIC + struct.pack(">I", len(metadata)) + metadata
    target.write(header)
    cipher, index = AESGCM(key), 0
    while True:
        chunk = source.read(CHUNK)
        nonce = os.urandom(12)
        encrypted = cipher.encrypt(nonce, chunk, header + struct.pack(">Q", index))
        target.write(struct.pack(">I", len(encrypted)) + nonce + encrypted)
        if not chunk:
            break
        index += 1


def read_exact(source, size):
    value = source.read(size)
    if len(value) != size:
        raise ValueError("备份不完整")
    return value


def decrypt(source, target, key):
    if read_exact(source, len(MAGIC)) != MAGIC:
        raise ValueError("备份格式不受支持")
    size_bytes = read_exact(source, 4)
    size = struct.unpack(">I", size_bytes)[0]
    if not 1 <= size <= 16384:
        raise ValueError("备份头损坏")
    metadata = read_exact(source, size)
    header = MAGIC + size_bytes + metadata
    cipher, index = AESGCM(key), 0
    while True:
        size = struct.unpack(">I", read_exact(source, 4))[0]
        if not 16 <= size <= CHUNK + 16:
            raise ValueError("备份块损坏")
        nonce, payload = read_exact(source, 12), read_exact(source, size)
        chunk = cipher.decrypt(nonce, payload, header + struct.pack(">Q", index))
        if not chunk:
            if source.read(1):
                raise ValueError("备份终止后仍有数据")
            return json.loads(metadata)
        if target:
            target.write(chunk)
        index += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["keygen", "encrypt", "verify", "decrypt"])
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--file", type=Path)
    parser.add_argument(
        "--kind", choices=["mysql_logical", "mysql_binlogs"], default="mysql_logical"
    )
    args = parser.parse_args()
    try:
        if args.mode == "keygen":
            if not args.key_file.is_absolute() or args.key_file.is_symlink():
                raise ValueError("密钥输出必须是非符号链接的绝对路径")
            fd = os.open(args.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as target:
                target.write(os.urandom(32))
            return
        key = key_from(args.key_file)
        if not args.file or not args.file.is_absolute() or args.file.is_symlink():
            raise ValueError("备份必须是非符号链接的绝对路径")
        if args.mode == "encrypt":
            fd = os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as target:
                encrypt(sys.stdin.buffer, target, key, kind=args.kind)
        else:
            with args.file.open("rb") as source:
                metadata = decrypt(
                    source, sys.stdout.buffer if args.mode == "decrypt" else None, key
                )
            if metadata.get("kind") != args.kind:
                raise ValueError("备份类型不匹配")
            if args.mode == "verify":
                print(json.dumps(metadata))
    except Exception:
        raise SystemExit("备份处理失败：检查密钥、格式、完整性或输出是否已存在") from None


if __name__ == "__main__":
    main()
