"""保证摘要/拉取失败不停止业务，目标机按依赖无构建启动。"""

import json
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY = (
    Path("/deploy") if Path("/deploy").is_dir() else Path(__file__).resolve().parents[3] / "deploy"
)


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    for key in ("ELECT_IMAGE_MODE", "ELECT_IMAGE", "ELECT_WEB_IMAGE", "ELECT_DEPLOYMENT_MODE",
                "ELECT_ALLOW_LOCAL_HTTP", "ELECT_SMTP_DIRECT_ENABLED", "ELECT_TEST_NETWORK_PREFIX"):
        monkeypatch.delenv(key, raising=False)
    backend, web = "ghcr.io/chaceqc/elect-backend@sha256:" + "a" * 64, "nginx@sha256:" + "b" * 64
    env = tmp_path / "stack.env"
    env.write_text(f"ELECT_IMAGE_MODE=published\nELECT_IMAGE={backend}\nELECT_WEB_IMAGE={web}\n"
                   "ELECT_RELEASE_VERSION=v0.18.0\nELECT_RELEASE_REVISION=" + "c" * 40 + "\n")
    record = tmp_path / "calls.jsonl"
    stub = tmp_path / "docker"
    stub.write_text('''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['START_RECORD'], 'a') as stream:
    stream.write(json.dumps(args) + '\\n')
if args[0] == 'pull' and os.environ.get('FAIL_PULL'):
    sys.exit(9)
if args[0] == 'compose' and 'config' in args:
    if '--images' in args:
        print(os.environ['START_BACKEND'] + '\\n' + os.environ['START_WEB'])
    elif '--format' in args:
        print('{}')
elif args[0] == 'run' and 'check-config' in args:
    sys.stdin.read()
    print('mysql\\nredis\\nrabbitmq\\nmigrate\\ntls-check\\nschool-adapter\\nmonitoring'
          '\\nidentity\\nroom\\nnotification\\npayment\\naudit\\ngateway\\nnotification-worker\\nnginx')
elif args[:2] == ['image', 'inspect']:
    print('[]')
elif args[0] == 'run' and 'check-images' in args:
    sys.stdin.read()
elif args[0] == 'ps':
    print('old-worker monitor-worker')
''')
    stub.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    for key, value in {"START_RECORD": str(record), "START_BACKEND": backend,
                       "START_WEB": web}.items():
        monkeypatch.setenv(key, value)
    return env, record


def invoke(env):
    return subprocess.run(["/bin/sh", str(DEPLOY / "start.sh"), str(env), "elect-staged"],
                          text=True, capture_output=True)


def test_failed_pull_keeps_running_application(deployment, monkeypatch):
    env, record = deployment
    monkeypatch.setenv("FAIL_PULL", "1")
    assert invoke(env).returncode != 0
    calls = [json.loads(line) for line in record.read_text().splitlines()]
    assert not any("stop" in call or "up" in call for call in calls)


def test_start_serializes_services_and_never_builds(deployment):
    env, record = deployment
    assert invoke(env).returncode == 0
    calls = [json.loads(line) for line in record.read_text().splitlines()]
    stop = next(index for index, call in enumerate(calls) if call[0] == "stop")
    preflight = next(index for index, call in enumerate(calls) if call[-2:] == ["nginx", "-t"])
    assert preflight < stop
    ups = [call for call in calls if "up" in call]
    assert [call[-1] for call in ups] == [
        "mysql", "redis", "rabbitmq", "school-adapter", "monitoring", "identity", "room",
        "notification", "payment", "audit", "gateway", "notification-worker", "nginx",
    ]
    assert all("--no-build" in call and "--no-deps" in call and "--wait" in call for call in ups)
    assert all(call[call.index("--parallel") + 1] == "1" for call in ups)
    assert not any("build" in call for call in calls)
