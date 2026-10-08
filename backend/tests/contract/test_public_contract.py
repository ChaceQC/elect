import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

from scripts.generate_openapi import build_contract
from services.gateway.contract_routes import ENDPOINTS

ROOT = Path(__file__).resolve().parents[3]
SPEC = yaml.safe_load((ROOT / "docs/contracts/openapi.yaml").read_text())


def test_openapi_is_valid_and_matches_backend_dto():
    validate(SPEC)
    assert SPEC == build_contract()
    assert len(ENDPOINTS) == 37
    assert len({entry.name for entry in ENDPOINTS}) == len(ENDPOINTS)
    assert len({(entry.method, entry.path) for entry in ENDPOINTS}) == len(ENDPOINTS)


def test_persistent_acceptance_has_recovery_and_write_guards():
    for entry in ENDPOINTS:
        operation = SPEC["paths"][entry.path][entry.method]
        if 202 in entry.statuses:
            assert operation["x-persistence"]
            recovery = operation["x-result-query"]
            assert "get" in SPEC["paths"][recovery]
        if entry.versioned:
            schema = SPEC["components"]["schemas"][entry.request]
            assert "expected_version" in schema["required"]
            assert "428" in operation["responses"]
        if not entry.anonymous and entry.method != "get":
            assert {"$ref": "#/components/parameters/CSRF"} in operation["parameters"]
        if entry.idempotent:
            assert {"$ref": "#/components/parameters/IdempotencyKey"} in operation["parameters"]


def test_every_synthetic_response_matches_frozen_schema():
    scenarios = json.loads((ROOT / "frontend/src/mocks/scenarios.json").read_text())
    for name, responses in scenarios.items():
        for response in responses:
            schema = SPEC["paths"][response["path"]][response["method"]]["responses"][
                str(response["status"])
            ]["content"]["application/json"]["schema"]
            validator = Draft202012Validator(
                {**schema, "components": SPEC["components"]},
                format_checker=FormatChecker(),
            )
            errors = list(validator.iter_errors(response["body"]))
            assert not errors, f"{name}: {[error.message for error in errors]}"
