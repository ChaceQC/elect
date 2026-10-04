"""验证恢复组合、隐藏旧角色检查和不执行dotenv代码的运维边界。"""

import os
import subprocess
from pathlib import Path

import pytest

DEPLOY = (
    Path("/deploy") if Path("/deploy").is_dir() else Path(__file__).resolve().parents[3] / "deploy"
)


@pytest.fixture
def docker_stub(tmp_path, monkeypatch):
    for key in ("ELECT_DEPLOYMENT_MODE", "ELECT_ALLOW_LOCAL_HTTP", "ELECT_SMTP_DIRECT_ENABLED",
                "ELECT_IMAGE_MODE"):
        monkeypatch.delenv(key, raising=False)
    record = tmp_path / "arguments"
    stub = tmp_path / "docker"
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$COMPOSE_ARGUMENT_FILE"\n')
    stub.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("COMPOSE_ARGUMENT_FILE", str(record))
    return tmp_path / "stack.env", record


def invoke(env, *args):
    return subprocess.run(
        ["/bin/sh", str(DEPLOY / "compose.sh"), str(env), "elect-test-selector", *args],
        capture_output=True, text=True,
    )


def test_restore_is_last_and_cannot_include_host_smtp(docker_stub):
    env, record = docker_stub
    env.write_text("ELECT_DEPLOYMENT_MODE='combined'\nELECT_ALLOW_LOCAL_HTTP=true\n"
                   'ELECT_SMTP_DIRECT_ENABLED="true"\n')
    assert invoke(env, "--test", "--restore", "--profile", "*", "config").returncode == 0
    args = record.read_text().splitlines()
    files = [Path(args[index + 1]).name for index, value in enumerate(args) if value == "-f"]
    assert files == ["compose.yaml", "compose.build.yaml", "compose.local.yaml",
                     "compose.test.yaml",
                     "compose.low-resource.yaml", "compose.ops.yaml", "compose.restore.yaml"]
    assert "*" in args


def test_selector_never_sources_or_evaluates_dotenv(docker_stub):
    env, record = docker_stub
    marker = env.parent / "must-not-exist"
    env.write_text(f"UNRELATED=$(touch '{marker}')\nELECT_DEPLOYMENT_MODE=standalone\n")
    assert invoke(env, "config").returncode == 0
    assert record.exists() and not marker.exists()


@pytest.mark.parametrize("content", [
    "ELECT_DEPLOYMENT_MODE=invalid\n",
    "ELECT_DEPLOYMENT_MODE=combined\nELECT_DEPLOYMENT_MODE=standalone\n",
    "ELECT_ALLOW_LOCAL_HTTP=1\n",
    "ELECT_SMTP_DIRECT_ENABLED=yes\n",
    "ELECT_IMAGE_MODE=invalid\n",
])
def test_invalid_or_ambiguous_selection_fails_before_docker(docker_stub, content):
    env, record = docker_stub
    env.write_text(content)
    assert invoke(env, "config").returncode != 0
    assert not record.exists()


def test_published_mode_has_no_source_build_overlay(docker_stub):
    env, record = docker_stub
    env.write_text("ELECT_IMAGE_MODE=published\nELECT_DEPLOYMENT_MODE=combined\n")
    assert invoke(env, "config").returncode == 0
    assert "compose.build.yaml" not in record.read_text()


def test_production_start_refuses_unpublished_images_before_docker(docker_stub):
    env, record = docker_stub
    env.write_text("ELECT_IMAGE_MODE=local\n")
    result = subprocess.run(["/bin/sh", str(DEPLOY / "start.sh"), str(env), "elect-selector"],
                            capture_output=True, text=True)
    assert result.returncode == 2 and not record.exists()


def test_restore_checks_profile_workers_before_verifying_or_importing_backup(docker_stub):
    env, record = docker_stub
    env.write_text("ELECT_DEPLOYMENT_MODE=combined\n")
    (env.parent / "docker").write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$COMPOSE_ARGUMENT_FILE"\n'
        'printf "audit-worker\\n"\n'
    )
    result = subprocess.run(
        ["/bin/sh", str(DEPLOY / "restore.sh"), str(env), "elect-restore-selector",
         "/unused/key", "/unused/backup"], capture_output=True, text=True,
    )
    assert result.returncode == 2 and "应用或后台进程运行" in result.stderr
    args = record.read_text().splitlines()
    assert args[args.index("--profile") + 1] == "*" and "ps" in args and "run" not in args
