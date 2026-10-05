import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.common.internal_dto import RoomQuery
from services.room.api import bindings
from services.room.dto import Bindings
from services.room.repository import RoomRepository


@pytest.mark.parametrize("enabled", [True, False])
def test_bindings_exposes_actual_write_policy(monkeypatch, enabled):
    result = Bindings(items=[], page=1, page_size=10, total=0, default_binding_id=None,
                      preference_version=1, default_switch_operation_id=None,
                      sync_status="empty", last_synced_at=None, pending_operations=[],
                      pending_operations_truncated=False)
    monkeypatch.setattr(RoomRepository, "list", AsyncMock(return_value=result))
    state = SimpleNamespace(database=None, side_effect_policy=SimpleNamespace(
        school_binding_writes=enabled))
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    value = asyncio.run(bindings(RoomQuery(), request, SimpleNamespace(user_id=uuid4())))
    assert value.binding_write_enabled is enabled
