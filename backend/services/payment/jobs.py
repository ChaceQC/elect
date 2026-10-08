"""持久任务租约、执行 epoch 与迟到结果栅栏。"""

from uuid import UUID

from services.common.ids import new_id
from services.common.sql import execute, first

from .check_window import deadline_sql, expired


async def claim(engine, order_id=None):
    lease = str(new_id())
    async with engine.begin() as conn:
        operation = await first(
            conn,
            "SELECT * FROM payment_operations WHERE state IN "
            "('accepted','running','reconciling','unknown') AND next_attempt_at<=UTC_TIMESTAMP(6) "
            "AND (lease_until IS NULL OR lease_until<=UTC_TIMESTAMP(6)) "
            "AND (:order IS NULL OR order_id=:order) "
            "ORDER BY next_attempt_at,id LIMIT 1 FOR UPDATE SKIP LOCKED",
            order=order_id.bytes if order_id else None,
        )
        if not operation:
            return None
        row = await first(conn, "SELECT *,UTC_TIMESTAMP(6) AS observed_at FROM payment_orders "
                          "WHERE id=:id FOR UPDATE", id=operation["order_id"])
        if row["cancel_requested_at"] or expired(row):
            await execute(
                conn, "UPDATE payment_operations SET next_attempt_at=NULL,"
                "state=IF(state='running','reconciling',state),lease_owner=NULL,lease_until=NULL "
                "WHERE id=:id", id=operation["id"],
            )
            await execute(conn, "UPDATE payment_orders SET next_check_at=NULL WHERE id=:id",
                          id=row["id"])
            return None
        await execute(
            conn,
            "UPDATE payment_operations SET state='running',lease_owner=:lease,"
            "lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 90 "
            "SECOND),execution_epoch=execution_epoch+1 "
            "WHERE id=:id",
            id=operation["id"],
            lease=lease,
        )
        await execute(
            conn,
            "UPDATE payment_orders SET state='submitting',version=version+1 "
            "WHERE id=:id AND state='created'",
            id=operation["order_id"],
        )
        row = await first(
            conn, "SELECT * FROM payment_orders WHERE id=:id", id=operation["order_id"]
        )
    return {
        **row,
        "operation_id": operation["id"],
        "kind": operation["kind"],
        "lease_owner": lease,
        "execution_epoch": operation["execution_epoch"] + 1,
    }


async def renew(engine, row):
    async with engine.begin() as conn:
        result = await execute(
            conn,
            "UPDATE payment_operations SET "
            "lease_until=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 90 SECOND) WHERE id=:id "
            "AND lease_owner=:lease AND execution_epoch=:epoch AND lease_until>UTC_TIMESTAMP(6)",
            id=row["operation_id"],
            lease=row["lease_owner"],
            epoch=row["execution_epoch"],
        )
    return bool(result.rowcount)


async def update(
    engine,
    row,
    *,
    order_state=None,
    qr_status=None,
    error=None,
    qr_error=None,
    operation_state=None,
    delay=30,
):
    async with engine.begin() as conn:
        valid = await first(
            conn,
            "SELECT id FROM payment_operations WHERE id=:id AND "
            "lease_owner=:lease AND execution_epoch=:epoch AND "
            "lease_until>UTC_TIMESTAMP(6) FOR UPDATE",
            id=row["operation_id"],
            lease=row["lease_owner"],
            epoch=row["execution_epoch"],
        )
        if not valid:
            return False
        await execute(
            conn,
            "UPDATE payment_orders SET state=COALESCE(:state,state),"
            "qr_status=COALESCE(:qr,qr_status),error_code=:error,qr_error_code=:qr_error,"
            "next_check_at=IF(cancel_requested_at IS NOT NULL OR "
            "state IN ('paid_confirmed','rejected','expired_confirmed','closed_confirmed') OR "
            f"{deadline_sql()}<=UTC_TIMESTAMP(6),NULL,LEAST(COALESCE(next_check_at,"
            "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL :check_delay SECOND)),"
            "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL :check_delay SECOND))),"
            "version=version+1,updated_at=UTC_TIMESTAMP(6) WHERE id=:id "
            "AND state NOT IN ('paid_confirmed','rejected','expired_confirmed','closed_confirmed')",
            id=row["id"],
            state=order_state,
            qr=qr_status,
            error=error,
            qr_error=qr_error,
            check_delay=30 if error else 2,
        )
        if operation_state:
            await execute(
                conn,
                "UPDATE payment_operations o JOIN payment_orders p ON p.id=o.order_id "
                "SET o.state=:state,o.error_code=:error,o.lease_owner=NULL,o.lease_until=NULL,"
                "o.next_attempt_at=IF(:state IN ('accepted','reconciling','unknown') AND "
                "p.cancel_requested_at IS NULL AND "
                f"{deadline_sql('p.')}>UTC_TIMESTAMP(6),"
                "DATE_ADD(UTC_TIMESTAMP(6),INTERVAL :delay SECOND),NULL),"
                "o.updated_at=UTC_TIMESTAMP(6) WHERE o.id=:id",
                id=row["operation_id"],
                state=operation_state,
                error=qr_error or error,
                delay=delay,
            )
    return True


async def recover(engine):
    from .cancellation import settle_cancellations

    cancelled = await settle_cancellations(engine)
    async with engine.begin() as conn:
        result = await execute(
            conn,
            "UPDATE payment_operations o JOIN payment_orders p ON p.id=o.order_id "
            "SET o.state='reconciling',o.lease_owner=NULL,o.lease_until=NULL,"
            "o.next_attempt_at=IF(p.cancel_requested_at IS NULL AND "
            f"{deadline_sql('p.')}>UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),NULL) "
            "WHERE o.state='running' AND o.lease_until<=UTC_TIMESTAMP(6)",
        )
        await execute(
            conn,
            "UPDATE payment_orders p JOIN payment_operations o ON o.order_id=p.id "
            "SET p.state='submit_unknown',p.error_code='WORKER_INTERRUPTED',p.version=p.version+1 "
            "WHERE p.state='submitting' AND o.kind='create_order' AND o.state='reconciling'",
        )
    return cancelled or bool(result.rowcount)


async def dispatch_proof(engine, owner, command):
    async with engine.connect() as conn:
        row = await first(
            conn,
            "SELECT p.*,o.state AS operation_state,"
            "(o.lease_owner=:lease AND o.lease_until>UTC_TIMESTAMP(6)) AS valid_lease "
            "FROM payment_orders p JOIN payment_operations o ON o.order_id=p.id "
            "WHERE p.id=:order AND p.owner_user_id=:owner AND o.id=:operation",
            order=command.order_id.bytes,
            owner=owner.bytes,
            operation=command.operation_id.bytes,
            lease=command.lease_owner,
        )
    if not row:
        from services.common.errors import ErrorCode
        from services.common.http import ApiError

        raise ApiError(404, ErrorCode.NOT_FOUND, "支付操作不存在")
    return {
        "can_dispatch": bool(
            row["valid_lease"]
            and row["operation_state"] == "running"
            and row["unresolved_binding_id"]
            and not row["cancel_requested_at"]
        ),
        "binding_id": str(UUID(bytes=row["binding_id"])),
        "credential_ref": str(UUID(bytes=row["credential_ref"])),
        "credential_version": row["credential_version"],
        "upstream_operation_id": str(UUID(bytes=row["upstream_operation_id"])),
        "amount": format(row["amount"], ".2f"),
        "currency": row["currency"],
    }
