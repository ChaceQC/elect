from services.common.state_model import StateModel

ROOM_OPERATION = StateModel(
    transitions={
        "accepted": ("running", "failed", "cancelled"),
        "running": ("reconciling", "succeeded", "failed"),
        "reconciling": ("unknown", "succeeded", "failed"),
        "unknown": ("reconciling", "succeeded", "failed"),
        "succeeded": (),
        "failed": (),
        "cancelled": (),
    },
    terminal=("succeeded", "failed", "cancelled"),
    recovery={
        "accepted": "从 MySQL 重新唤醒，逻辑操作 ID 不变",
        "running": "根据 dispatch 台账或 retarget Saga 步骤继续",
        "reconciling": "绑定只查 B02，切换按已提交偏好向前完成",
        "unknown": "仅回查/人工核实；保持目标写入屏障，不重新 POST",
    },
)
