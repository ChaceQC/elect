"""由 DTO 与受控端点清单生成冻结契约；不启动 HTTP 服务。"""

import argparse
import importlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel

from services.common.errors import HTTP_ERRORS
from services.gateway.contract_routes import ENDPOINTS

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "docs/contracts/openapi.yaml"
DTO_MODULES = (
    "common.dto",
    "common.operations",
    "identity.dto",
    "room.dto",
    "monitoring.dto",
    "payment.dto",
)
QUERY = {
    "q": {"type": "string", "maxLength": 128},
    "page": {"type": "integer", "minimum": 1, "default": 1},
    "page_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
    "binding_id": {"type": "string", "format": "uuid"},
    "room_id": {"type": "string", "maxLength": 128},
    "start_date": {"type": "string", "format": "date"},
    "end_date": {"type": "string", "format": "date"},
    "granularity": {"type": "string", "enum": ["day", "week", "month"], "default": "day"},
    "snapshot_token": {"type": "string", "maxLength": 512},
}


def schemas():
    result = {}
    for name in DTO_MODULES:
        module = importlib.import_module(f"services.{name}")
        for cls in vars(module).values():
            if not isinstance(cls, type) or not issubclass(cls, BaseModel) or cls is BaseModel:
                continue
            schema = cls.model_json_schema(ref_template="#/components/schemas/{model}")
            result.update(schema.pop("$defs", {}))
            result[cls.__name__] = schema
    return result


def json_content(name, envelope=True):
    schema = {"$ref": f"#/components/schemas/{name}"}
    if envelope:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["data", "meta"],
            "properties": {"data": schema, "meta": {"$ref": "#/components/schemas/Meta"}},
        }
    return {"application/json": {"schema": schema}}


def responses(endpoint):
    result = {}
    for status in endpoint.statuses:
        response = {"description": "持久受理，按查询接口跟踪" if status == 202 else "成功"}
        if status != 204:
            name = (
                "DefaultResult"
                if endpoint.name == "set_default" and status == 200
                else endpoint.result
            )
            response["content"] = json_content(name)
        if endpoint.name == "get_qr" and status == 200:
            response["content"] = {
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
            }
        if status == 202:
            response["headers"] = {"Retry-After": {"schema": {"type": "integer", "minimum": 1}}}
        result[str(status)] = response
    for status, codes in HTTP_ERRORS.items():
        result[str(status)] = {
            "description": ", ".join(codes),
            "content": json_content("ErrorEnvelope", envelope=False),
        }
    return result


def parameters(endpoint):
    result = []
    if "{id}" in endpoint.path:
        result.append(
            {
                "name": "id",
                "in": "path",
                "required": True,
                "schema": {"type": "string", "format": "uuid"},
            }
        )
    for name in endpoint.query:
        required = name in {"start_date", "end_date"} or (
            name == "binding_id" and endpoint.name == "get_capabilities"
        )
        result.append({"name": name, "in": "query", "required": required, "schema": QUERY[name]})
    if endpoint.method != "get":
        result.append(
            {
                "name": "Origin",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "format": "uri"},
            }
        )
        if not endpoint.anonymous:
            result.append({"$ref": "#/components/parameters/CSRF"})
    if endpoint.idempotent:
        result.append({"$ref": "#/components/parameters/IdempotencyKey"})
    return result


def build_contract():
    paths = {}
    for endpoint in ENDPOINTS:
        operation = {
            "operationId": endpoint.name,
            "tags": [endpoint.owner],
            "summary": endpoint.name,
            "x-owner": endpoint.owner,
            "x-stage": endpoint.stage,
            "security": [] if endpoint.anonymous else [{"SessionCookie": []}],
            "parameters": parameters(endpoint),
            "responses": responses(endpoint),
            "x-cache-control": "no-store",
        }
        if endpoint.request:
            operation["requestBody"] = {
                "required": endpoint.name != "create_captcha",
                "content": json_content(endpoint.request, envelope=False),
            }
        if endpoint.versioned:
            operation["x-version-required"] = "expected_version；缺失 428，冲突 409"
        if endpoint.recovery:
            operation.update(
                {"x-result-query": endpoint.recovery, "x-persistence": endpoint.persistence}
            )
        paths.setdefault(endpoint.path, {})[endpoint.method] = operation
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "寝室电费学生端 API",
            "version": "0.5.0",
            "description": "T0 冻结契约。金额为十进制字符串，未知为 null，日期为上海含首尾日期，"
            "时间戳带时区。202 仅表示持久受理。业务服务按 x-stage 实现。",
        },
        "servers": [{"url": "/api/v1"}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "SessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "__Host-elect_session",
                    "description": "Secure; HttpOnly; SameSite=Lax; Path=/；不设置 Domain",
                }
            },
            "parameters": {
                "CSRF": {
                    "name": "X-CSRF-Token",
                    "in": "header",
                    "required": True,
                    "schema": {"type": "string", "minLength": 1},
                },
                "IdempotencyKey": {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "description": "按用户+操作类型分区，原请求摘要一致才能重放，至少保留 180 天",
                    "schema": {"type": "string", "minLength": 16, "maxLength": 128},
                },
            },
            "schemas": schemas(),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    contract = build_contract()
    content = "# 由 backend/scripts/generate_openapi.py 生成；请修改 DTO/端点清单后重新生成。\n"
    content += yaml.safe_dump(json.loads(json.dumps(contract)), allow_unicode=True, sort_keys=False)
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != content:
            raise SystemExit("OpenAPI 与 DTO/端点清单不同步，请重新生成")
        print("OpenAPI 与 DTO/端点清单一致")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(content)
        print("已生成 docs/contracts/openapi.yaml，28 个公开接口")


if __name__ == "__main__":
    main()
