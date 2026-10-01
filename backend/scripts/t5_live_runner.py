"""宿主专用测试进程：私有 auth 文件仅在内存经匿名 stdin 交给容器。"""

import argparse
import asyncio
import json
import subprocess
from pathlib import Path

from scripts.auth_file import read_auth
from scripts.email_auth_file import read_email_auth
from scripts.smtp_direct_tunnel import DirectTunnel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-file", type=Path, required=True)
    parser.add_argument("--email-auth-file", type=Path, required=True)
    parser.add_argument("--test-dir", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--direct-interface")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if not args.project.startswith("elect-test-") or not args.test_dir.is_absolute():
        raise SystemExit("仅允许明确隔离的验收项目")
    student, password = read_auth(args.auth_file.resolve())
    command = [
        "docker",
        "compose",
        "--env-file",
        str(args.test_dir / "stack.env"),
        "-f",
        str(root / "deploy/compose.yaml"),
        "-f",
        str(root / "deploy/compose.test.yaml"),
        "-f",
        str(args.test_dir / "live.override.yaml"),
        "-p",
        args.project,
        "run",
        "-T",
        "--rm",
        "--no-deps",
        "-v",
        f"{root / 'backend/services'}:/app/services:ro",
        "-v",
        f"{root / 'backend/scripts'}:/app/scripts:ro",
        "-v",
        f"{args.email_auth_file.resolve()}:/run/local/email_auth.txt:ro",
        "smoke",
        "python",
        "-m",
        "scripts.t5_live_delivery",
        "--school-auth-stdin",
        "--email-auth-file",
        "/run/local/email_auth.txt",
        "--record",
        "/tmp/t5-live.json",
    ]

    async def run_container(school_credentials, proxy_url=None):
        payload = dict(school_credentials)
        if proxy_url:
            payload["proxy_url"] = proxy_url
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate(json.dumps(payload).encode())
        return process.returncode, stdout.decode()

    async def run(school_credentials):
        if not args.direct_interface:
            return await run_container(school_credentials)
        config, _ = read_email_auth(args.email_auth_file.resolve())
        gateway = subprocess.check_output(
            [
                "docker",
                "network",
                "inspect",
                args.project + "_data",
                "--format",
                "{{(index .IPAM.Config 0).Gateway}}",
            ],
            text=True,
        ).strip()
        async with DirectTunnel(config, gateway, args.direct_interface) as tunnel:
            return await run_container(school_credentials, tunnel.url)

    returncode, stdout = asyncio.run(run({"student": student, "password": password}))
    del student, password
    # 容器只输出分类 JSON；过滤数据库重复事件提示，不转发 stderr 或原始异常。
    records = [line for line in stdout.splitlines() if line.startswith('{"date":')]
    if not records:
        raise SystemExit("验收容器未返回分类结果，未输出凭据或原始错误")
    record = json.loads(records[-1])
    args.record.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False))
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()
