import json
import re
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
    config = (target / "rabbitmq.conf").read_text()
    assert "definitions.import_backend = local_filesystem" in config
    assert "definitions.local.path = /run/secrets/rabbitmq_definitions" in config
    assert "management.load_definitions" not in config
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


def test_controls_upgrade_adds_only_its_key_and_preserves_existing_secrets(tmp_path):
    from services.deployment.upgrade_controls import SCOPES
    from services.deployment.upgrade_controls import upgrade as upgrade_controls

    target = tmp_path / "secrets"
    provision(target)
    # 还原为没有控制密钥/权限的 T2 Secret 目录。
    (target / "monitoring_encryption_key_bundle").unlink()
    files = [p for p in target.glob("*_runtime.json") if p.name != "migration_runtime.json"]
    before = {}
    for path in files:
        value = json.loads(path.read_text())
        for entry in value["trust_bundle"].values():
            entry["scopes"] = [
                x for x in entry["scopes"] if x not in SCOPES.get(entry["issuer"], [])
            ]
        path.chmod(0o600)
        path.write_text(json.dumps(value))
        before[path.name] = value
    upgrade_controls(target)
    key = (target / "monitoring_encryption_key_bundle").read_bytes()
    upgrade_controls(target)
    assert (target / "monitoring_encryption_key_bundle").read_bytes() == key
    for path in files:
        value = json.loads(path.read_text())
        for field, previous in before[path.name].items():
            if field != "trust_bundle":
                assert value[field] == previous
        for entry in value["trust_bundle"].values():
            assert set(SCOPES.get(entry["issuer"], [])) <= set(entry["scopes"])


def test_room_binding_hint_has_minimal_publish_route_and_repeatable_upgrade(tmp_path):
    from services.deployment.upgrade_controls import upgrade as upgrade_controls

    target = tmp_path / "secrets"
    provision(target)
    path = target / "rabbitmq_definitions.json"
    fresh = json.loads(path.read_text())
    # 模拟旧Secret中缺失的权限/路由，复用原用户密码hash和全部密钥。
    old = json.loads(path.read_text())
    old["bindings"] = [row for row in old["bindings"]
                       if row["routing_key"] != "room.binding_confirmed"]
    for permission in old["topic_permissions"]:
        if permission["user"] == "room":
            permission["write"] = "^(audit\\.recorded|room\\.history_sync_requested)$"
    path.chmod(0o600)
    path.write_text(json.dumps(old))
    upgrade_controls(target)
    upgrade_controls(target)
    updated = json.loads(path.read_text())
    assert updated == fresh
    assert updated["users"] == old["users"]
    topics = {row["user"]: row for row in updated["topic_permissions"]}
    assert re.fullmatch(topics["room"]["write"], "room.binding_confirmed")
    assert not re.fullmatch(topics["room"]["write"], "payment.order_requested")
    assert re.fullmatch(topics["monitoring"]["read"], "room.binding_confirmed")
    assert not re.fullmatch(topics["monitoring"]["write"], "room.binding_confirmed")
    routes = [row for row in updated["bindings"]
              if row["routing_key"] == "room.binding_confirmed"]
    assert len(routes) == 1 and routes[0]["destination"] == "elect.monitoring.runs"
