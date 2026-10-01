"""仅从受限文件读取本服务配置；禁止通过环境变量传递凭据。"""

import os
from ipaddress import IPv4Address
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from sqlalchemy.engine import make_url

from .config_contract import DeploymentConfig, SideEffectPolicy
from .dto import DTO
from .migration_runtime import DATABASES

SERVICES = (*DATABASES, "gateway")


class TrustedKey(DTO):
    issuer: str
    public_key: str
    audiences: list[str]
    scopes: list[str]


class Runtime(DTO):
    schema_version: Literal[1] = 1
    service: str
    db_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    amqp_url: SecretStr | None = None
    signing_key: SecretStr
    key_id: str
    trust_bundle: dict[str, TrustedKey]

    @model_validator(mode="after")
    def isolated_database(self):
        if self.service not in SERVICES:
            raise ValueError("未知服务")
        if self.service == "gateway":
            if self.db_url is not None:
                raise ValueError("Gateway 不得持有业务库连接")
        else:
            if self.db_url is None:
                raise ValueError("领域服务需要本库连接")
            url = make_url(self.db_url.get_secret_value())
            short = DATABASES[self.service].removeprefix("elect_")
            if (
                url.drivername != "mysql+asyncmy"
                or url.database != DATABASES[self.service]
                or url.username != f"elect_{short}_app"
            ):
                raise ValueError("运行连接必须使用本领域 app 账号")
        if self.key_id not in self.trust_bundle:
            raise ValueError("签名 key_id 未登记")
        if self.trust_bundle[self.key_id].issuer != self.service:
            raise ValueError("签名密钥与服务身份不匹配")
        return self


def read_secret(path: str | Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute() or not candidate.is_file():
        raise RuntimeError("Secret 必须是可读取的绝对文件路径")
    if candidate.stat().st_size > 1024 * 1024:
        raise RuntimeError("Secret 文件过大")
    return candidate.read_text(encoding="utf-8").strip()


def load_runtime(expected_service: str) -> Runtime:
    try:
        runtime = Runtime.model_validate_json(read_secret(os.environ["ELECT_RUNTIME_FILE"]))
        if runtime.service != expected_service:
            raise ValueError("服务身份不匹配")
        return runtime
    except Exception:
        # Pydantic/SQLAlchemy 的原始错误可能包含输入 URL、密码或私钥。
        raise RuntimeError("运行 Secret 缺失、不可读取或校验失败") from None


def public_origin() -> str:
    origin = os.environ["ELECT_PUBLIC_ORIGIN"]
    local_http = os.environ.get("ELECT_ALLOW_LOCAL_HTTP", "false")
    if local_http not in {"true", "false"}:
        raise RuntimeError("本机 HTTP 开关只允许 true/false")
    if local_http == "true":
        try:
            address = IPv4Address(os.environ["ELECT_HTTP_BIND"])
            port = int(os.environ["ELECT_HTTP_PORT"])
            if (
                not address.is_private or address.is_unspecified or address.is_reserved
                or not 1 <= port <= 65535 or origin != f"http://{address}:{port}"
            ):
                raise ValueError()
        except (KeyError, ValueError):
            raise RuntimeError("本机 HTTP 来源必须匹配指定的私网 IPv4 和端口") from None
        return origin
    domain = origin.removeprefix("https://")
    config = DeploymentConfig(
        domain=domain,
        tls_cert_file=Path("/unused"),
        tls_key_file=Path("/unused"),
        secrets_dir=Path("/unused"),
    )
    if origin != config.public_origin:
        raise RuntimeError("PUBLIC_ORIGIN 必须由单个 HTTPS 域名派生")
    return origin


def side_effect_policy() -> SideEffectPolicy:
    names = {
        "school_binding_writes": "SCHOOL_BINDING_WRITES",
        "payment_order_writes": "PAYMENT_ORDER_WRITES",
        "payment_form_writes": "PAYMENT_FORM_WRITES",
        "real_smtp": "REAL_SMTP",
        "payment_acceptance_passed": "PAYMENT_ACCEPTANCE_PASSED",
    }
    values = {}
    for field, suffix in names.items():
        value = os.environ.get(
            f"ELECT_ALLOW_{suffix}"
            if field != "payment_acceptance_passed"
            else "ELECT_PAYMENT_ACCEPTANCE_PASSED",
            "false",
        )
        if value not in {"true", "false"}:
            raise RuntimeError("副作用开关只允许 true/false")
        values[field] = value == "true"
    return SideEffectPolicy(**values)
