import pytest
from pydantic import ValidationError

from services.common.config_contract import DeploymentConfig, SideEffectPolicy


@pytest.mark.parametrize(
    "domain", ["https://elect.example.edu", "elect.example.edu:443", "a/b", "a;return 200"]
)
def test_domain_rejects_scheme_port_path_and_template_injection(domain):
    with pytest.raises(ValidationError):
        DeploymentConfig(
            domain=domain,
            tls_cert_file="/cert.pem",
            tls_key_file="/key.pem",
            secrets_dir="/secrets",
        )


def test_origin_derived_and_secret_paths_absolute():
    config = DeploymentConfig(
        domain="elect.example.edu",
        tls_cert_file="/cert.pem",
        tls_key_file="/key.pem",
        secrets_dir="/secrets",
    )
    assert config.public_origin == "https://elect.example.edu"
    with pytest.raises(ValidationError):
        DeploymentConfig(
            domain="elect.example.edu",
            tls_cert_file="cert.pem",
            tls_key_file="/key.pem",
            secrets_dir="/secrets",
        )


def test_effects_default_closed_and_payment_needs_acceptance():
    policy = SideEffectPolicy()
    assert not any(policy.model_dump().values())
    assert not policy.payments_enabled
    assert not SideEffectPolicy(
        payment_order_writes=True, payment_form_writes=True
    ).payments_enabled
    assert SideEffectPolicy(
        payment_order_writes=True, payment_form_writes=True, payment_acceptance_passed=True
    ).payments_enabled
