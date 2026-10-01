import json
import stat

import pytest

from services.common.runtime import Runtime
from services.common.security import validate_keys
from services.deployment.provision import provision
from services.deployment.upgrade_auth import upgrade


def test_new_secret_bundle_is_isolated_and_never_overwritten(tmp_path):
    target = tmp_path / "secrets"
    provision(target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    runtime = Runtime.model_validate_json((target / "identity_runtime.json").read_text())
    validate_keys(runtime)
    assert "elect_identity_app" in runtime.db_url.get_secret_value()
    gateway = Runtime.model_validate_json((target / "gateway_runtime.json").read_text())
    assert gateway.db_url is None
    assert gateway.signing_key != runtime.signing_key
    definitions = json.loads((target / "rabbitmq_definitions.json").read_text())
    assert all("password" not in user and user["tags"] == [] for user in definitions["users"])
    before = (target / "mysql_root_password").read_bytes()
    with pytest.raises(ValueError, match="拒绝覆盖"):
        provision(target)
    assert (target / "mysql_root_password").read_bytes() == before


def test_auth_upgrade_is_repeatable_and_preserves_all_existing_credentials(tmp_path):
    target = tmp_path / "secrets"
    provision(target)
    names = [
        "school_kek_bundle",
        "school_lookup_hmac_bundle",
        "identity_session_pepper",
        "mysql_root_password",
        "identity_tls_key.pem",
        "internal_ca_key.pem",
    ]
    previous = {name: (target / name).read_bytes() for name in names}
    runtime = json.loads((target / "identity_runtime.json").read_text())
    for _ in range(2):
        upgrade(target)
    assert previous == {name: (target / name).read_bytes() for name in names}
    updated = json.loads((target / "identity_runtime.json").read_text())
    for field in ["db_url", "redis_url", "amqp_url", "signing_key"]:
        assert updated[field] == runtime[field]
