"""导出内部 DTO 和各领域状态模型；与生产构建解耦。"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import yaml
from pydantic import BaseModel

from services.common import internal_dto
from services.identity.states import LOGIN_ATTEMPT
from services.monitoring.states import ALERT_SLOT, EPISODE, MONITOR, RUN
from services.notification.states import JOB
from services.payment.states import ORDER
from services.room.states import ROOM_OPERATION

ROOT = Path(__file__).resolve().parents[2] / "docs/contracts"
MODELS = {
    "login_attempt": LOGIN_ATTEMPT,
    "room_operation": ROOM_OPERATION,
    "monitor": MONITOR,
    "run": RUN,
    "episode": EPISODE,
    "alert_slot": ALERT_SLOT,
    "notification_job": JOB,
    "payment_order": ORDER,
}


def artifacts():
    definitions = {}
    for cls in vars(internal_dto).values():
        if not isinstance(cls, type) or not issubclass(cls, BaseModel) or cls is BaseModel:
            continue
        schema = cls.model_json_schema(ref_template="#/$defs/{model}")
        definitions.update(schema.pop("$defs", {}))
        definitions[cls.__name__] = schema
    schemas = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$defs": definitions}
    states = {
        "schema_version": 1,
        "models": {name: asdict(model) for name, model in MODELS.items()},
    }
    return {
        "internal/schemas.json": json.dumps(schemas, ensure_ascii=False, indent=2) + "\n",
        "states.yaml": yaml.safe_dump(
            json.loads(json.dumps(states)), allow_unicode=True, sort_keys=False
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, content in artifacts().items():
        target = ROOT / name
        if args.check:
            if not target.exists() or target.read_text() != content:
                raise SystemExit(f"内部协议/状态模型未同步：{name}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
    print("内部 DTO 与状态模型检查通过" if args.check else "内部 DTO 与状态模型已导出")


if __name__ == "__main__":
    main()
