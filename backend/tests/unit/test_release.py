"""发布元数据防错与合并/独立启动配置；不触发真实registry操作。"""

import json

import pytest

from services.deployment.release import SOURCE, check_config, check_images, check_version

BACKEND = "ghcr.io/chaceqc/elect-backend@sha256:" + "a" * 64
WEB = "ghcr.io/chaceqc/elect-frontend@sha256:" + "b" * 64


def config():
    return {"services": {"gateway": {"image": BACKEND}, "identity": {"image": BACKEND},
                         "nginx": {"image": WEB},
                         "identity-recovery": {"image": BACKEND, "profiles": ["standalone"]}}}


def test_published_config_excludes_old_profile_roles():
    assert check_config(config()) == ["gateway", "identity", "nginx"]


@pytest.mark.parametrize("change", [
    {"image": "elect-backend:latest"}, {"build": {"context": "../backend"}},
    {"image": "ghcr.io/chaceqc/elect-backend@sha256:" + "c" * 64},
])
def test_published_config_rejects_moving_tags_builds_and_mixed_backend(change):
    value = config()
    value["services"]["identity"].update(change)
    with pytest.raises(ValueError):
        check_config(value)


def test_version_mismatch_cannot_publish(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend/pyproject.toml").write_text('[project]\nversion="0.18.0"\n')
    (tmp_path / "frontend/package.json").write_text(json.dumps({"version": "0.18.0"}))
    check_version(tmp_path, "v0.18.0")
    for tag in ("latest", "v0.17.0", "v00.18.0"):
        with pytest.raises(ValueError):
            check_version(tmp_path, tag)


def test_images_must_share_release_revision():
    labels = {"org.opencontainers.image.version": "v0.18.0",
              "org.opencontainers.image.revision": "a" * 40,
              "org.opencontainers.image.source": SOURCE}
    check_images([{"Config": {"Labels": labels}}] * 2, "v0.18.0", "a" * 40)
    with pytest.raises(ValueError):
        check_images([{"Config": {"Labels": labels}}] * 2, "v0.18.0", "b" * 40)
