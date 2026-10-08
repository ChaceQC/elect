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
        "created": "使用同一 upstream_operation_id；未发送凭据拒绝持久化为 rejected",
        "submitting": "未发送凭据拒绝按 Adapter 台账终结；dispatch 后崩溃进入 submit_unknown",
        "submit_unknown": "凭据拒绝且台账证明未发送才终结；已发送保留屏障，空列表不解除",
        "awaiting_payment": "查询经验证的支付状态；QR 成功不能确认付款",
        "status_unknown": "保存未知；只有已验收映射或人工确证才能终结",
    },
)
