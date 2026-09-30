from services.common.state_model import StateModel

ORDER = StateModel(
    transitions={
        "created": ("submitting", "rejected"),
        "submitting": ("awaiting_payment", "submit_unknown", "rejected"),
        "submit_unknown": (
            "awaiting_payment",
            "status_unknown",
            "rejected",
            "paid_confirmed",
            "expired_confirmed",
            "closed_confirmed",
        ),
        "awaiting_payment": (
            "paid_confirmed",
            "status_unknown",
            "expired_confirmed",
            "closed_confirmed",
        ),
        "status_unknown": (
            "awaiting_payment",
            "paid_confirmed",
            "expired_confirmed",
            "closed_confirmed",
        ),
        "paid_confirmed": (),
        "rejected": (),
        "expired_confirmed": (),
        "closed_confirmed": (),
    },
    terminal=("paid_confirmed", "rejected", "expired_confirmed", "closed_confirmed"),
    recovery={
        "created": "使用同一 upstream_operation_id，Adapter 台账先提交再 dispatch",
        "submitting": "dispatch 后崩溃进入 submit_unknown，只查询已有学校订单",
        "submit_unknown": "保留同用户/绑定屏障；空列表不能解除，不二次建单",
        "awaiting_payment": "查询经验证的支付状态；QR 成功不能确认付款",
        "status_unknown": "保存未知；只有已验收映射或人工确证才能终结",
    },
)
