"""仅清理已永久失效七天且无恢复引用的会话；同意与登录防重放记录保留。"""

from datetime import datetime

from services.common.sql import execute


async def cleanup(engine, *, apply=True, limit=200, cutoff=None):
    limit = max(1, min(limit, 200))
    async with engine.begin() as conn:
        attempts = (await execute(conn, "SELECT id FROM login_attempts WHERE "
            "state IN ('session_issued','failed','expired') AND "
            "expires_at<DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 7 DAY) "
            "AND issued_session_id IS NOT NULL AND expires_at<=:cutoff ORDER BY expires_at,id "
            "LIMIT :limit FOR UPDATE SKIP LOCKED", limit=limit,
            cutoff=cutoff or datetime.max)).mappings().all()
        if apply:
            for row in attempts:
                await execute(conn, "UPDATE login_attempts SET issued_session_id=NULL "
                              "WHERE id=:id", id=row["id"])
        sessions = (await execute(conn, "SELECT s.id FROM app_sessions s WHERE "
            "LEAST(s.expires_at,s.absolute_expires_at,COALESCE(s.revoked_at,s.expires_at)) "
            "<DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 7 DAY) AND s.expires_at<=:cutoff "
            "AND NOT EXISTS (SELECT 1 FROM login_attempts a WHERE a.issued_session_id=s.id) "
            "ORDER BY s.expires_at,s.id LIMIT :limit FOR UPDATE SKIP LOCKED",
            limit=limit, cutoff=cutoff or datetime.max)).mappings().all()
        if apply:
            for row in sessions:
                await execute(conn, "DELETE FROM app_sessions WHERE id=:id", id=row["id"])
    return {"candidates": len(attempts)+len(sessions), "detached": len(attempts),
            "sessions": len(sessions), "applied": apply}
