from services.common.state_model import StateModel

LOGIN_ATTEMPT = StateModel(
    transitions={
        "created": ("authenticating", "failed", "expired"),
        "authenticating": ("staged", "failed", "expired"),
        "staged": ("identity_committed", "failed", "expired"),
        "identity_committed": ("activating", "failed"),
        "activating": ("activated", "failed"),
        "activated": ("session_issued",),
        "session_issued": (),
        "failed": (),
        "expired": (),
    },
    terminal=("session_issued", "failed", "expired"),
    recovery={
        "authenticating": "按 attempt 查询 Adapter；未 dispatch 可失败，已验证凭据不得被失败覆盖",
        "staged": "暂存到期未激活则清理；已登记 Identity 的 attempt 优先对账",
        "identity_committed": "按 attempt 幂等激活，保留已有 user_id",
        "activating": "查询激活结果，不能重写未经验证的凭据",
        "activated": "持久确认后签发会话；重认证保持当前 user_id",
    },
)
