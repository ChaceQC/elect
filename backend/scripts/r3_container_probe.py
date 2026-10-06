"""R3一次性容器自动重启检查；所有数据库和副作用计数均为合成。"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from scripts.r3_process_probe import Probe
from scripts.r3_recovery_state import RecoveryState
from services.common.job import pause


class ContainerProbe(Probe):
    def __init__(self, mode, prefix):
        super().__init__(mode, "restart")
        self.prefix = prefix
        self.marker = Path("/tmp/r3-restart.json")

    async def role(self, selected, app, stop, beat, hub=None):
        if not selected:
            while not stop.is_set():
                beat.write(healthy=True)
                await pause(stop, 1)
            return
        state = RecoveryState(self.prefix)
        try:
            saved = json.loads(self.marker.read_text(encoding="utf-8")) \
                if self.marker.exists() else None
            if saved:
                assert saved["phase"] == "before", "不能用额外重启掩盖恢复故障"
                result = await state.after(saved["old"])
                self.marker.write_text(json.dumps({"phase": "passed", **result}), encoding="utf-8")
                while not stop.is_set():
                    await state.scan()
                    beat.write(healthy=True)
                    await pause(stop, 0.1)
                return
            old = await state.before()
            self.marker.write_text(json.dumps({"phase": "before", "old": old}), encoding="utf-8")
            beat.document["failure_budget"] = 2  # 加速故障注入；生产60秒由可控时钟测试覆盖。
            started = time.monotonic()
            while not stop.is_set():
                try:
                    await state.scan(fail=time.monotonic() - started >= 10)
                    beat.write(healthy=True)
                except Exception:
                    beat.write(healthy=False)
                await pause(stop, 0.1)
        finally:
            await state.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--mode", choices=["core", "combined", "standalone"])
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        value = json.loads(Path("/tmp/r3-restart.json").read_text(encoding="utf-8"))
        assert value["phase"] == "passed"
        print(json.dumps(value))
    elif args.prepare:
        async def prepare():
            state = RecoveryState(args.prefix)
            try:
                await state.prepare()
            finally:
                await state.close()
        asyncio.run(prepare())
    else:
        assert args.mode
        ContainerProbe(args.mode, args.prefix).run()


if __name__ == "__main__":
    main()
