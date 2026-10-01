import pytest
from pydantic import ValidationError

from services.common.config_contract import SideEffectPolicy
from services.common.http import ApiError
from services.common.ids import new_id
from services.payment.dto import OrderRequest
from services.payment.policy import unavailable, validate_amount


@pytest.mark.parametrize("value", ["1.00", "25.00", "500.00"])
def test_application_integer_amount_policy(value):
    assert format(validate_amount(value), ".2f") == value


@pytest.mark.parametrize("value", ["0.00", "0.99", "1.01", "500.01", "501.00", "NaN", "Infinity"])
def test_outside_policy_is_rejected(value):
    with pytest.raises(ApiError):
        validate_amount(value)


@pytest.mark.parametrize("amount", [1, 1.0, "1", "1.1", "01.00"])
def test_public_amount_requires_an_exact_decimal_string(amount):
    with pytest.raises(ValidationError):
        OrderRequest(binding_id=new_id(), amount=amount)


def test_payment_acceptance_is_required_in_addition_to_write_flags():
    credential = {"state": "active", "use_allowed": True}
    binding = {"status": "active"}
    policy = SideEffectPolicy(payment_order_writes=True, payment_form_writes=True)
    assert unavailable(policy, credential, binding) is not None
    enabled = policy.model_copy(update={"payment_acceptance_passed": True})
    assert unavailable(enabled, credential, binding) is None
    assert unavailable(enabled, {**credential, "use_allowed": False}, binding) is not None
    assert unavailable(enabled, credential, {"status": "rechecking"}) is not None
