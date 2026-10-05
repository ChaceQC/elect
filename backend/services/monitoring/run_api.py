"""本人运行、取消与固定样本分页。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from services.common.dto import DTO
from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.internal_dto import CancelRunQuery, RunQuery, SampleQuery
from services.common.security import Principal, require_user_principal
from services.common.sql import first

from .runs import cancel_run, run_view
from .samples import list_samples
from .scheduler import accept_run

router = APIRouter(prefix="/internal/v1/browser")
Browser = Annotated[Principal, Depends(require_user_principal("monitor:browser"))]


class CreateRun(DTO):
    idempotency_key: str = Field(min_length=16, max_length=128)


@router.post("/runs")
async def create(command: CreateRun, request: Request, principal: Browser):
    row = await accept_run(
        request.app.state.database, principal.user_id, command.idempotency_key, principal.request_id
    )
    run_id = str(UUID(bytes=row["id"]))
    return {
        "run_id": run_id,
        "version": row["version"],
        "state": row["state"],
        "poll_url": f"/api/v1/monitor/runs/{run_id}",
    }


@router.post("/run")
async def get(command: RunQuery, request: Request, principal: Browser):
    async with request.app.state.database.connect() as conn:
        row = await first(
            conn,
            "SELECT r.* FROM monitor_runs r JOIN monitors m ON m.id=r.monitor_id WHERE "
            "r.id=:id AND m.owner_user_id=:owner",
            id=command.run_id.bytes,
            owner=principal.user_id.bytes,
        )
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "本人运行不存在")
        return await run_view(conn, row)


@router.post("/cancel")
async def cancel(command: CancelRunQuery, request: Request, principal: Browser):
    return await cancel_run(
        request.app.state.database,
        principal.user_id,
        command.run_id,
        command.expected_version,
        principal.request_id,
    )


@router.post("/samples")
async def samples(command: SampleQuery, request: Request, principal: Browser):
    return await list_samples(
        request.app.state.database, principal.user_id, command,
        request.app.state.runtime.signing_key.get_secret_value().encode(),
    )
