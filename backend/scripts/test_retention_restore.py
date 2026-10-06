"""Docker独立七库dump→既有AES-GCM→新MySQL恢复；不读取本机Secret。"""

import io
import secrets
import subprocess
import time
from pathlib import Path

from services.common.domains import DATABASES
from services.deployment.backup_crypto import decrypt, encrypt

ROOT = Path(__file__).resolve().parents[2]


def docker(*args, data=None):
    result = subprocess.run(["docker", *args], input=data, capture_output=True, check=False)
    if result.returncode:
        # 合成环境也不把dump、密文、密钥或SQL参数放进公开日志。
        raise RuntimeError("独立R4 Docker检查失败，步骤=" + args[0])
    return result.stdout


def main():
    name = "elect-r4-restore-" + secrets.token_hex(5)
    network = name + "-net"
    nodes = [name + "-source", name + "-target"]
    try:
        docker("network", "create", "--internal", network)
        for node, alias in zip(nodes, ("r4-source", "r4-target"), strict=True):
            docker("run", "-d", "--name", node, "--network", network, "--network-alias", alias,
                "--memory", "512m", "--tmpfs", "/var/lib/mysql:rw,size=384m",
                "-e", "MYSQL_ALLOW_EMPTY_PASSWORD=yes", "mysql:8.4.6",
                "--innodb-buffer-pool-size=64M", "--innodb-redo-log-capacity=32M",
                "--performance-schema=OFF")
            for _ in range(60):
                try:
                    docker("exec", node, "mysqladmin", "ping", "--silent")
                    break
                except RuntimeError:
                    time.sleep(1)
            else:
                raise RuntimeError("独立MySQL启动超时")
        def fixture(mode, host):
            return docker("run", "--rm", "--network", network,
                "-e", f"ELECT_R4_RESTORE_HOST={host}", "-e", "PYTHONUTF8=1",
                "-e", "PYTHONPATH=/app:/app/tests/integration",
                "-v", f"{ROOT}/backend/services:/app/services:ro",
                "-v", f"{ROOT}/backend/scripts:/app/scripts:ro",
                "-v", f"{ROOT}/backend/tests:/app/tests:ro", "elect-backend-check",
                "python", "tests/integration/retention_restore_fixture.py", mode)
        print(fixture("seed", "r4-source").decode().strip())
        dump = docker("exec", nodes[0], "mysqldump", "-uroot", "--single-transaction",
                      "--hex-blob", "--no-tablespaces", "--databases", *DATABASES.values())
        key, encrypted = secrets.token_bytes(32), io.BytesIO()
        encrypt(io.BytesIO(dump), encrypted, key)
        restored = io.BytesIO()
        decrypt(io.BytesIO(encrypted.getvalue()), restored, key)
        assert restored.getvalue() == dump
        damaged = bytearray(encrypted.getvalue())
        damaged[-1] ^= 1
        try:
            decrypt(io.BytesIO(damaged), None, key)
        except Exception:
            pass
        else:
            raise AssertionError("损坏归档未被拒绝")
        docker("exec", "-i", nodes[1], "mysql", "-uroot", "--binary-mode=1",
               data=restored.getvalue())
        print(fixture("verify", "r4-target").decode().strip())
        print("R4 encrypted seven-database restore: duplicate effects=0; "
              "D01/E02/E03 and DATA unknown retained; old Outbox isolated; corruption rejected")
    finally:
        for node in nodes:
            subprocess.run(["docker", "rm", "-f", "-v", node], capture_output=True)
        subprocess.run(["docker", "network", "rm", network], capture_output=True)


if __name__ == "__main__":
    main()
