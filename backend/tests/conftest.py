import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.common.runtime import Runtime


@pytest.fixture
def runtime_factory(tmp_path, monkeypatch):
    def make(service="gateway"):
        key = Ed25519PrivateKey.generate()
        private = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        public = (
            key.public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            .decode()
        )
        document = {
            "service": service,
            "signing_key": private,
            "key_id": f"{service}-v1",
            "trust_bundle": {
                f"{service}-v1": {
                    "issuer": service,
                    "public_key": public,
                    "audiences": [service],
                    "scopes": ["foundation:read"],
                }
            },
        }
        if service != "gateway":
            short = "school" if service == "school_adapter" else service
            document["db_url"] = f"mysql+asyncmy://elect_{short}_app:secret@mysql/elect_{short}"
        path = tmp_path / f"{service}.json"
        path.write_text(json.dumps(document))
        monkeypatch.setenv("ELECT_RUNTIME_FILE", str(path))
        monkeypatch.setenv("ELECT_PUBLIC_ORIGIN", "https://elect.example.edu")
        return Runtime.model_validate(document)

    return make
