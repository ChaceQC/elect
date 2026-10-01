from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.common.ids import new_id
from services.room.queries import RoomQueries


@pytest.mark.parametrize("quality,stale", [("fresh", False), ("stale", True), ("unknown", True)])
def test_independent_binding_read_preserves_explicit_cache_quality(quality, stale):
    row = {
        "id": new_id().bytes,
        "room_id": new_id().bytes,
        "building_name": "合成楼",
        "room_no": "402",
        "status": "active",
        "fetched_at": datetime.now(UTC),
        "school_observed_at": None,
        "balance": Decimal("25.50"),
        "quality": quality,
        "error_code": None,
    }
    binding = RoomQueries.binding(row, "ready")
    assert binding["balance"]["stale"] is stale
    assert binding["balance"]["amount"] == "25.50"
