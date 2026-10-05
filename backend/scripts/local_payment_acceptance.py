"""WSL专用单笔支付验收：复用锁定解释器及持久业务流程，只启动隔离MySQL/Redis。"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from scripts.auth_file import read_auth

PROJECT = "elect-test-meter-orders"
ROOT = Path(__file__).resolve().parents[2]
STATE = Path.home() / ".local/state" / PROJECT
IMAGE = "python:3.12-slim-bookworm"


def run(command, *, input=None):
    result = subprocess.run(command, input=input, text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        # 不输出命令原始stdout/stderr，避免数据库/请求错误携带凭据或票据。
        raise RuntimeError("本地验收步骤失败: " + command[0])
    return result.stdout


def python_command(network="none"):
    base, environment = Path(sys.base_prefix), Path(sys.prefix)
    return ["docker", "run", "--rm", "-i", "--network", network,
            "-v", f"{base}:{base}:ro", "-v", f"{environment}:{environment}:ro",
            "-v", f"{ROOT / 'backend'}:/app:ro", "-w", "/app", "-e", "PYTHONUTF8=1",
            "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "ELECT_TEST_DISPOSABLE=1"]


def setup():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    secrets = STATE / "secrets"
    secrets.mkdir(exist_ok=True, mode=0o700)
    marker = STATE / "prepared"
    if marker.exists():
        run(["docker", "start", PROJECT + "-mysql", PROJECT + "-redis"])
        wait_mysql()
        return
    if not (secrets / "migration_runtime.json").exists():
        run(python_command() + ["-v", f"{secrets}:/run/provision", IMAGE, sys.executable,
            "-m", "services.deployment.provision", "--output-dir", "/run/provision"])
    networks = run(["docker", "network", "ls", "--format", "{{.Name}}"]).splitlines()
    if PROJECT not in networks:
        run(["docker", "network", "create", "--subnet", "10.253.47.0/28", PROJECT])
    names = run(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines()
    mysql = PROJECT + "-mysql"
    if mysql not in names:
        run(["docker", "run", "-d", "--name", mysql, "--network", PROJECT,
             "--network-alias", "mysql", "--memory", "1g",
             "-e", "MYSQL_ROOT_PASSWORD_FILE=/run/secrets/mysql_root_password",
             "-e", "TZ=UTC", "-v", f"{PROJECT}-mysql-v2:/var/lib/mysql",
             "-v", f"{secrets}/mysql_root_password:/run/secrets/mysql_root_password:ro",
             "-v", f"{secrets}/mysql_probe.cnf:/run/secrets/mysql_probe:ro",
             "-v", f"{secrets}/mysql_bootstrap.sql:/run/secrets/mysql_bootstrap:ro",
             "-v", f"{secrets}/mysql_bootstrap.sql:/docker-entrypoint-initdb.d/01.sql:ro",
             "mysql:8.4.6"])
    redis = PROJECT + "-redis"
    if redis not in names:
        run(["docker", "run", "-d", "--name", redis, "--network", PROJECT,
             "--network-alias", "redis", "--memory", "128m",
             "-v", f"{PROJECT}-redis:/data",
             "-v", f"{secrets}/redis_users.acl:/run/secrets/redis_acl:ro",
             "redis:7-alpine", "redis-server", "--aclfile", "/run/secrets/redis_acl",
             "--appendonly", "yes", "--maxmemory", "64mb", "--maxmemory-policy", "noeviction"])
    wait_mysql()
    run(python_command(PROJECT) + ["-v", f"{secrets}:/run/secrets:ro",
        "-e", "ELECT_RUNTIME_FILE=/run/secrets/migration_runtime.json", IMAGE, sys.executable,
        "-m", "services.migrate_all_mysql"])
    marker.write_text("ready\n", encoding="utf-8")
    print("隔离MySQL/Redis与业务迁移已就绪。", flush=True)


def wait_mysql():
    for _ in range(45):
        ready = subprocess.run(["docker", "exec", PROJECT + "-mysql", "mysql",
                                "--defaults-extra-file=/run/secrets/mysql_probe",
                                "-Nse", "SELECT 1"],
                               capture_output=True)
        if ready.returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError("隔离MySQL未就绪")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["setup", "create", "check", "qr", "paid-proof"],
                        required=True)
    parser.add_argument("--order-id")
    parser.add_argument("--export-dir", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    setup()
    if args.phase == "setup":
        return
    output = STATE / "output"
    output.mkdir(exist_ok=True, mode=0o700)
    if args.phase == "paid-proof":
        result = run(python_command(PROJECT) + ["-v", f"{STATE}/secrets:/run/secrets:ro",
            IMAGE, sys.executable, "-m", "scripts.payment_paid_readonly",
            "--order-id", args.order_id])
        (output / "paid-proof.json").write_text(result, encoding="utf-8")
        print(result)
        return
    if args.phase == "qr":
        destination = args.export_dir or output
        destination.mkdir(parents=True, exist_ok=True)
        print(run(python_command(PROJECT) + ["-v", f"{STATE}/secrets:/run/secrets:ro",
            "-v", f"{output}:/run/private", "-v", f"{destination}:/run/live-output",
            IMAGE, sys.executable, "-m", "scripts.local_payment_qr", "--order-id", args.order_id,
            "--qr-output", "/run/live-output/payment-wechat.png",
            "--journal", "/run/private/qr-recovery.enc"]))
        return
    student, password = read_auth(ROOT / "auth.txt")
    command = python_command(PROJECT) + ["-v", f"{STATE}/secrets:/run/secrets:ro",
        "-v", f"{output}:/run/live-output", IMAGE, sys.executable, "-m", "scripts.t6_live",
        "--phase", args.phase, "--amount", "1.00", "--qr-output", "/run/live-output/payment.png"]
    if args.order_id:
        command += ["--order-id", args.order_id]
    # 永久保存本轮分类记录；原业务台账/学校票据由既有数据库与密文保护。
    result = subprocess.run(command, input=json.dumps({"student": student, "password": password}),
                            text=True, encoding="utf-8", capture_output=True)
    del student, password
    rows = [line for line in result.stdout.splitlines() if line.startswith('{"date":')]
    if not rows:
        raise RuntimeError("验收未返回分类记录，未输出原始错误")
    record = json.loads(rows[-1])
    (output / f"{args.phase}.json").write_text(
        json.dumps(record, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(record, ensure_ascii=False), flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        print(str(error))
        raise SystemExit(1) from None
