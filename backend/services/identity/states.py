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
        "authenticating": "前台明确认证拒绝含429终结failed；恢复查询暂存404终结failed，"
        "查询429/5xx继续恢复；不重提密码",
        "staged": "Identity尚未提交且暂存404则终结failed；终结须按持久状态条件更新，"
        "不能覆盖并发身份提交",
        "identity_committed": "按 attempt 幂等激活，保留已有 user_id",
        "activating": "查询激活结果，不能重写未经验证的凭据",
        "activated": "持久确认后签发会话；重认证保持当前 user_id",
    },
)
