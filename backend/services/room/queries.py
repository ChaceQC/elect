from datetime import UTC, datetime
from uuid import UUID

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import aware, execute, first

from .dto import Bindings


class RoomQueries:
    async def list(self, owner, q, page, page_size):
        async with self.engine.connect() as conn:
            state = await first(
                conn, "SELECT * FROM room_sync_state WHERE owner_user_id=:owner", owner=owner.bytes
            )
            preference = await first(
                conn, "SELECT * FROM room_preferences WHERE owner_user_id=:owner", owner=owner.bytes
            )
            predicate = "b.owner_user_id=:owner"
            if q:
                predicate += " AND (LOCATE(:q,r.building_name)>0 OR LOCATE(:q,r.room_no)>0)"
            params = dict(owner=owner.bytes, q=q, offset=(page - 1) * page_size, size=page_size)
            count = await first(
                conn,
                f"SELECT COUNT(*) AS n FROM room_bindings b JOIN rooms r "
                f"ON r.id=b.room_id WHERE {predicate}",
                **params,
            )
            rows = (
                (
                    await execute(
                        conn,
                        "SELECT b.*,r.building_name,r.room_no,c.balance,c.fetched_at,"
                        "c.school_observed_at,c.quality,c.error_code FROM room_bindings b "
                        "JOIN rooms r ON r.id=b.room_id LEFT JOIN room_balance_cache c "
                        f"ON c.binding_id=b.id WHERE {predicate} ORDER BY "
                        "r.building_name,r.room_no,b.id LIMIT :size OFFSET :offset",
                        **params,
                    )
                )
                .mappings()
                .all()
            )
            pending = (
                (
                    await execute(
                        conn,
                        "SELECT * FROM room_operations WHERE owner_user_id=:owner "
                        "AND state IN ('accepted','running','reconciling','unknown') "
                        "ORDER BY created_at DESC,id DESC LIMIT 21",
                        owner=owner.bytes,
                    )
                )
                .mappings()
                .all()
            )
        sync_state = state["state"] if state else "loading"
        return Bindings(
            items=[self.binding(row, sync_state) for row in rows],
            page=page,
            page_size=page_size,
            total=count["n"],
            default_binding_id=UUID(bytes=preference["default_binding_id"])
            if preference and preference["default_binding_id"]
            else None,
            preference_version=preference["version"] if preference else 1,
            default_switch_operation_id=UUID(bytes=preference["switch_operation_id"])
            if preference and preference["switch_operation_id"]
            else None,
            sync_status=sync_state,
            last_synced_at=aware(state["last_synced_at"]) if state else None,
            pending_operations=[
                {
                    "id": UUID(bytes=row["id"]),
                    "type": row["type"],
                    "state": row["state"],
                    "target_binding_id": UUID(bytes=row["target_binding_id"])
                    if row["target_binding_id"]
                    else None,
                    "created_at": aware(row["created_at"]),
                }
                for row in pending[:20]
            ],
            pending_operations_truncated=len(pending) > 20,
        )

    @staticmethod
    def binding(row, sync_state):
        fetched = aware(row["fetched_at"])
        stale = (
            sync_state != "ready"
            or not fetched
            or (datetime.now(UTC) - fetched).total_seconds() > 300
        )
        return {
            "id": UUID(bytes=row["id"]),
            "room_id": UUID(bytes=row["room_id"]),
            "building": row["building_name"],
            "number": row["room_no"],
            "display_name": " ".join(filter(None, [row["building_name"], row["room_no"]]))
            or "学校寝室",
            "status": row["status"],
            "balance": None
            if not fetched
            else {
                "amount": format(row["balance"], ".2f") if row["balance"] is not None else None,
                "currency": "CNY",
                "source": "school_bound_rooms",
                "fetched_at": fetched,
                "school_observed_at": aware(row["school_observed_at"]),
                "stale": stale,
                "refresh_state": "pending"
                if sync_state == "loading"
                else "failed"
                if sync_state in {"failed", "stale"}
                else "ready",
                "error_code": row["error_code"],
            },
        }

    async def operation(self, owner, operation):
        async with self.engine.connect() as conn:
            row = await first(
                conn,
                "SELECT * FROM room_operations WHERE id=:id AND owner_user_id=:owner",
                id=operation.bytes,
                owner=owner.bytes,
            )
        if not row:
            raise ApiError(404, ErrorCode.NOT_FOUND, "对象不存在")
        return {
            "id": str(operation),
            "type": row["type"],
            "state": row["state"],
            "target_binding_id": str(UUID(bytes=row["target_binding_id"]))
            if row["target_binding_id"]
            else None,
            "created_at": aware(row["created_at"]),
            "binding_status": None,
            "default_status": (
                "confirmed"
                if row["state"] == "succeeded"
                else "failed"
                if row["state"] == "failed"
                else "switching"
            )
            if row["type"] == "switch_default"
            else None,
            "retryable": bool(row["error_code"]) and row["type"] == "binding_sync",
            "error_code": row["error_code"],
            "next_reconcile_at": aware(row["next_reconcile_at"]),
            "result_binding_id": str(UUID(bytes=row["target_binding_id"]))
            if row["type"] == "switch_default" and row["state"] == "succeeded"
            else None,
            "result_order_id": None,
        }

    async def bound_school_ids(self, owner):
        async with self.engine.connect() as conn:
            rows = await execute(
                conn,
                "SELECT r.school_room_id FROM rooms r JOIN room_bindings b "
                "ON r.id=b.room_id WHERE b.owner_user_id=:owner "
                "AND b.status IN ('active','rechecking')",
                owner=owner.bytes,
            )
            return set(rows.scalars())
