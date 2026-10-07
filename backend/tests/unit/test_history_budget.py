import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from services.common.http import ApiError
from services.common.ids import new_id
from services.common.internal_dto import HistoryExecutionQuery
from services.common.security import Principal
from services.school_adapter.query_api import history


def test_target_lookup_and_school_read_share_remaining_window_budget():
    async def verify():
        budgets = []

        async def call(*args, **kwargs):
            budgets.append(kwargs["budget"])
            await asyncio.sleep(.03)
            return {"school_room_id": "synthetic"}

        async def read(*args, **kwargs):
            budgets.append(kwargs["budget"])
            assert kwargs["read_timeout"] == 20
            return {"data": {"list": []}}

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            service_client=SimpleNamespace(call=call), school_sessions=SimpleNamespace(read=read))))
        command = HistoryExecutionQuery(binding_id=new_id(), start_date=date(2026, 9, 1),
                                        end_date=date(2026, 9, 7), budget_seconds=.15)
        result = await history(command, request, Principal("room", new_id(), 1, new_id()))
        assert result["items"] == [] and 0 < budgets[1] < budgets[0] <= .15
        command.budget_seconds = .01
        with pytest.raises(ApiError) as timeout:
            await history(command, request, Principal("room", new_id(), 1, new_id()))
        assert timeout.value.code == "SCHOOL_TIMEOUT"
        assert len(budgets) == 3  # 到期的目标回查不进入学校读取。
    asyncio.run(verify())
