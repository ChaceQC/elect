from services.common.state_model import StateModel

MONITOR = StateModel(
    transitions={
        "disabled": ("active", "retargeting", "requires_reauth", "blocked_room"),
        "active": ("disabled", "retargeting", "requires_reauth", "blocked_room"),
        "requires_reauth": ("active", "disabled", "retargeting", "blocked_room"),
        "blocked_room": ("active", "disabled", "retargeting", "requires_reauth"),
        "retargeting": ("active", "disabled", "requires_reauth", "blocked_room"),
    },
    terminal=(),
    recovery={
        "active": "按 schedule_anchor_at 合并错过的时间槽，仅创建一条补偿采集",
        "retargeting": "按 operation_id 查询 Room 提交结果；尊重 desired_enabled",
        "requires_reauth": "人工重认证后按最新凭据版本和当前 generation 恢复",
        "blocked_room": "本人有效默认绑定确认后按当前意图恢复",
    },
)

RUN = StateModel(
    transitions={
        "pending": ("running", "cancelled"),
        "running": ("succeeded", "retry_wait", "failed", "cancel_requested"),
        "retry_wait": ("running", "cancelled", "failed"),
        "cancel_requested": ("cancelled",),
        "succeeded": (),
        "failed": (),
        "cancelled": (),
    },
    terminal=("succeeded", "failed", "cancelled"),
    recovery={
        "pending": "从 MySQL 重新唤醒，唯一计划键保持不变",
        "running": "租约过期提升 execution_epoch，再进入 retry_wait，拒绝旧结果",
        "retry_wait": "到达持久 next_attempt_at 后领取，不依赖队列 TTL",
        "cancel_requested": "结束在途请求并丢弃结果，不写成功样本",
    },
)

EPISODE = StateModel(
    transitions={"open": ("closed",), "closed": ()},
    terminal=("closed",),
    recovery={"open": "保持计数；间隔/次数变化不清零，未知投递占用序号"},
)

ALERT_SLOT = StateModel(
    transitions={
        "reserved": ("authorized", "cancelled"),
        "authorized": ("reserved", "sent", "delivery_unknown", "failed", "cancelled"),
        "sent": (),
        "delivery_unknown": (),
        "failed": (),
        "cancelled": (),
    },
    terminal=("sent", "delivery_unknown", "failed", "cancelled"),
    recovery={
        "reserved": "幂等创建 notification job；发送前重新验权",
        "authorized": "许可/投递租约过期先核对是否可能发送；可能发送则 delivery_unknown",
        "delivery_unknown": "占用提醒名额，人工核实，不盲重发",
    },
)
