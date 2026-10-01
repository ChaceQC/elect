"""应用保护政策；不是经过学校验收的金额上限。"""

from decimal import Decimal

from services.common.errors import ErrorCode
from services.common.http import ApiError

MINIMUM, MAXIMUM, STEP = Decimal("1.00"), Decimal("500.00"), Decimal("1.00")
UNRESOLVED = ("created", "submitting", "awaiting_payment", "submit_unknown", "status_unknown")


def validate_amount(amount):
    value = Decimal(amount)
    if not value.is_finite() or not MINIMUM <= value <= MAXIMUM or (value - MINIMUM) % STEP:
        raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "充值金额须为 1–500 元整数")
    return value


def unavailable(policy, credential, binding):
    if binding["status"] != "active":
        return "绑定关系尚未确认或已失效"
    if credential["state"] != "active" or not credential["use_allowed"]:
        return "请先修复学校认证并允许后台使用凭据"
    if not policy.payment_acceptance_passed:
        return "支付尚未完成真实验收，暂未开放"
    if not policy.payments_enabled:
        return "支付暂未开放"
    return None
