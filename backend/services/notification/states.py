from services.common.state_model import StateModel

JOB = StateModel(
    transitions={
        "pending": ("sending", "cancelled"),
        "sending": ("sent", "retry_wait", "failed", "delivery_unknown", "cancelled"),
        "retry_wait": ("sending", "cancelled", "failed"),
        "sent": (),
        "failed": (),
        "delivery_unknown": (),
        "cancelled": (),
    },
    terminal=("sent", "failed", "delivery_unknown", "cancelled"),
    recovery={
        "pending": "取得投递租约与当前代次许可后发送",
        "sending": "可能已发送正文/发送后崩溃则 delivery_unknown，不重发",
        "retry_wait": "仅明确未接收的临时错误，1/5/15 分钟最多 3 次重试并重新授权",
        "delivery_unknown": "保留 Message-ID 和台账，核实/人工处理",
    },
)
