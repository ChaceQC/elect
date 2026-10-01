"""专用进程内存解析 auth，以匿名 stdin 进入明确的验收容器。"""

import argparse
import json
import subprocess
from pathlib import Path

from scripts.auth_file import read_auth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-file", type=Path, required=True)
    parser.add_argument("--test-dir", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--phase", choices=["readonly", "create", "check"], required=True)
    parser.add_argument("--relation", choices=["lower", "higher"], default="lower")
    parser.add_argument("--order-id")
    parser.add_argument("--qr-output", type=Path)
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
    ]
    if args.qr_output:
        args.qr_output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        command += ["-v", f"{args.qr_output.parent.resolve()}:/run/live-output"]
    command += [
        "smoke",
        "python",
        "-m",
        "scripts.t6_live",
        "--phase",
        args.phase,
        "--relation",
        args.relation,
    ]
    if args.order_id:
        command += ["--order-id", args.order_id]
    if args.qr_output:
        command += ["--qr-output", "/run/live-output/" + args.qr_output.name]
    result = subprocess.run(
        command,
        input=json.dumps({"student": student, "password": password}),
        text=True,
        capture_output=True,
        cwd=root,
    )
    del student, password
    records = [line for line in result.stdout.splitlines() if line.startswith('{"date":')]
    if not records:
        raise SystemExit("验收未返回分类记录；未输出凭据或原始异常")
    record = json.loads(records[-1])
    args.record.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    args.record.chmod(0o600)
    print(json.dumps(record, ensure_ascii=False))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
