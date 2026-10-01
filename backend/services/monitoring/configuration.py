"""配置意图和失效屏障在一次本域事务中提交；不访问学校或消息服务。"""

import re

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.common.sql import execute, first

from .queries import MonitorQueries
from .repository import audit, invalidate, lock_monitor, require_version


def validate_config(config, monitor, *, activating=True):
    email = config["email"]
    if email is not None and (
        len(email) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email)
    ):
        raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "请输入有效邮箱地址")
    if config["enabled"]:
        if activating and (monitor["state"] == "retargeting" or monitor["credential_operation_id"]):
            raise ApiError(409, ErrorCode.OPERATION_IN_PROGRESS, "目标或凭据正在切换，请稍后重试")
        if activating and not monitor["binding_id"]:
            raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "请先设置有效默认寝室")
        if activating and (not monitor["credential_allowed"] or not monitor["credential_ref"]):
            raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "请先重新认证并授权后台使用")
        if not email:
            raise ApiError(422, ErrorCode.INVALID_ARGUMENT, "开启监控需要填写提醒邮箱")


class MonitorConfiguration(MonitorQueries):
    async def patch(self, owner, command, request_id):
        async with self.engine.begin() as conn:
            monitor = await lock_monitor(conn, owner)
            require_version(monitor["version"], command.expected_version)
            old = self.config(monitor)
            config = {**old, **command.model_dump(exclude_unset=True, exclude={"expected_version"})}
            changed = {key for key in old if old[key] != config[key]}
            if not changed:
                return await self.view(conn, monitor)
            # 纯关闭不依赖旧邮箱是否可用；切换中也可以提交关闭意图。
            if changed != {"enabled"} or config["enabled"]:
                validate_config(
                    config, monitor, activating=config["enabled"] and not old["enabled"]
                )
            if monitor["state"] == "retargeting" and changed != {"enabled"}:
                raise ApiError(
                    409, ErrorCode.OPERATION_IN_PROGRESS, "切换中可关闭监控，其他设置请稍后保存"
                )
            close = bool(changed & {"enabled", "threshold", "email"})
            await invalidate(conn, monitor, close_episode=close)
            email_version = monitor["email_version"] + ("email" in changed)
            ciphertext = (
                self.crypto.seal(config["email"], owner, email_version)
                if "email" in changed
                else monitor["email_ciphertext"]
            )
            state = self.next_state(monitor, config)
            immediate = config["enabled"] and bool(changed & {"enabled", "interval_minutes"})
            await execute(
                conn,
                "UPDATE monitors SET desired_enabled=:enabled,state=:state,"
                "interval_minutes=:interval,"
                "repeat_limit=:repeat,threshold=:threshold,email_ciphertext=:email,email_version=:ev,"
                "version=version+1,generation=generation+1,"
                "next_run_at=IF(:state<>'active',NULL,IF(:immediate,UTC_TIMESTAMP(6),next_run_at)),"
                "schedule_anchor_at=IF(:immediate,UTC_TIMESTAMP(6),schedule_anchor_at),"
                "first_enabled_at=IF(:enabled,COALESCE(first_enabled_at,UTC_TIMESTAMP(6)),first_enabled_at),"
                "updated_at=UTC_TIMESTAMP(6) WHERE id=:id",
                id=monitor["id"],
                enabled=config["enabled"],
                state=state,
                interval=config["interval_minutes"],
                repeat=config["repeat_limit"],
                threshold=config["threshold"],
                email=ciphertext,
                ev=email_version,
                immediate=immediate,
            )
            await audit(conn, monitor, request_id, "monitor.configured")
            updated = await first(conn, "SELECT * FROM monitors WHERE id=:id", id=monitor["id"])
            return await self.view(conn, updated)

    @staticmethod
    def next_state(monitor, config):
        if monitor["state"] == "retargeting":
            return "retargeting"
        if not config["enabled"]:
            return "disabled"
        if not monitor["credential_allowed"] or monitor["credential_operation_id"]:
            return "requires_reauth"
        if not monitor["binding_id"] or monitor["state"] == "blocked_room":
            return "blocked_room"
        return "active"
