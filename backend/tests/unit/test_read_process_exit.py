"""R5三种真实入口下，停止后双槽drain且正常退出0。"""

import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="服务容器采用Linux信号入口")
@pytest.mark.parametrize("mode", ["core", "combined", "standalone"])
@pytest.mark.parametrize("service", ["room", "payment"])
def test_read_slots_stop_and_drain_in_real_process(mode, service):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.r5_read_process_probe", "--mode", mode,
         "--service", service], capture_output=True, text=True, encoding="utf-8", timeout=12,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "R5_READ_DRAIN_OK" in result.stdout
