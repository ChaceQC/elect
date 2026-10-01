import pytest

from services.common.http import ApiError
from services.school_adapter.infrastructure.rooms import room_record


def test_opaque_room_fields_preserve_leading_zero_and_numeric_zero():
    row = room_record(
        {"roomId": "00001", "roomNo": 0, "meterCode": "00002", "id": "00003", "balance": None}
    )
    assert row["room_id"] == "00001" and row["number"] == "0"
    assert row["meter_code"] == "00002" and row["relation_id"] == "00003"
    assert row["balance"] is None


def test_malformed_nested_fields_and_oversize_ids_are_not_exposed_or_truncated():
    for extra in [{"buildingName": {"resident": "synthetic-private"}}, {"meterCode": "x" * 129}]:
        with pytest.raises(ApiError) as error:
            room_record({"roomId": "synthetic", **extra})
        assert error.value.code == "SCHOOL_INVALID_RESPONSE"
