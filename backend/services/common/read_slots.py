"""两个读取槽共用领域上下文，各自保留心跳和在途执行身份。"""

import asyncio


async def run_slots(loop, app, stop, heartbeat, hub=None):
    async def run(slot):
        child = heartbeat.child(str(slot))
        try:
            await loop(app, stop, child, hub)
        except asyncio.CancelledError:
            if not stop.is_set():
                raise RuntimeError("读取执行槽意外取消") from None
            raise
        finally:
            child.finish("stopped" if stop.is_set() else "failed")
        if not stop.is_set():
            raise RuntimeError("读取执行槽意外返回")

    async with asyncio.TaskGroup() as tasks:
        for slot in range(2):
            tasks.create_task(run(slot), name=f"read-slot:{slot}")
