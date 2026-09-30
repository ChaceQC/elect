"""公开配置的 T0 校验约定；Secret 读取/Worker 启动检查在 T1 实现。"""

from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, Field, StrictBool

from .dto import DTO


def absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("Secret/TLS 路径须为绝对路径")
    return path


AbsolutePath = Annotated[Path, AfterValidator(absolute_path)]


class DeploymentConfig(DTO):
    domain: Annotated[
        str,
        Field(
            min_length=1,
            max_length=253,
            pattern=r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$",
        ),
    ]
    tls_cert_file: AbsolutePath
    tls_key_file: AbsolutePath
    secrets_dir: AbsolutePath

    @property
    def public_origin(self) -> str:
        return f"https://{self.domain}"


class SideEffectPolicy(DTO):
    school_binding_writes: StrictBool = False
    payment_order_writes: StrictBool = False
    payment_form_writes: StrictBool = False
    real_smtp: StrictBool = False
    payment_acceptance_passed: StrictBool = False

    @property
    def payments_enabled(self) -> bool:
        return (
            self.payment_order_writes
            and self.payment_form_writes
            and self.payment_acceptance_passed
        )
