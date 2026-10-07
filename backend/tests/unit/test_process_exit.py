"""退出码来自独立Python进程；硬退出只作用于子进程，验证主进程始终存活。"""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="部署使用POSIX信号，在Linux检查")


@pytest.mark.parametrize("mode,fault,expected", [
    (mode, fault, 1) for mode in ("core", "combined", "standalone")
    for fault in ("return", "raise", "cancel", "business", "only_tick")
] + [
    ("combined", "blocked_loop", 1), ("combined", "ocr", 1),
    ("core", "normal", 0), ("combined", "normal", 0), ("standalone", "normal", 0),
    ("core", "disabled", 0), ("combined", "disabled", 0),
])
def test_real_process_stops_and_exits(mode, fault, expected):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.r3_process_probe", "--mode", mode, "--fault", fault],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    output = result.stdout + result.stderr
    assert result.returncode == expected, output
    assert "R3_SECRET_SENTINEL" not in output
    assert "Task exception was never retrieved" not in output
    if expected == 0:
        assert "process_fatal" not in output
    elif fault != "blocked_loop":
        assert output.count('"event": "process_fatal"') == 1


@pytest.mark.parametrize("service", [
    "identity", "room", "monitoring", "payment", "notification", "relay", "audit",
])
def test_all_standalone_entry_families_propagate_fatal(service):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.r3_process_probe", "--mode", "standalone",
         "--fault", "return", "--service", service],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "AssertionError" not in output and "R3_SECRET_SENTINEL" not in output
    assert output.count('"event": "process_fatal"') == 1
