import json
import stat

import pytest

from services.common.runtime import Runtime
from services.common.security import validate_keys
from services.deployment.provision import provision


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
