from hashlib import sha256

import pytest
from pydantic import ValidationError

from services.identity.agreement import agreement
from services.identity.dto import LoginRequest


def test_login_requires_agreement_background_authorization():
    policy = agreement()
    values = dict(student_id="synthetic", password="synthetic-only", challenge_id="a" * 43,
                  captcha_answer="3", agreement_version=policy.version, agreement_accepted=True,
                  credential_use_allowed=True)
    assert LoginRequest(**values).credential_use_allowed is True
    for field in ("agreement_accepted", "credential_use_allowed"):
        with pytest.raises(ValidationError):
            LoginRequest(**{**values, field: False})
    assert policy.content_hash == sha256(policy.content.encode("utf-8")).hexdigest()
    assert "登录或重新认证" in policy.content
    assert "2026-10-04.1" == policy.version
