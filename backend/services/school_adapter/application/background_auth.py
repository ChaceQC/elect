"""后台恢复的验证码和登录预算；明确拒绝后才尝试第二次登录。"""

import asyncio

from services.common.errors import ErrorCode
from services.common.http import ApiError

from ..infrastructure.protocol import restore_cookies


async def authenticate(protocol, executor, payload, deadline):
    challenge, submissions = None, 0
    async with asyncio.timeout(deadline.remaining()):
        for image_index in range(5):
            if challenge is None:
                challenge = await protocol.challenge(deadline=deadline, pool="background")
            try:
                answer = await executor.solve(challenge.image, deadline)
            except (ApiError, TimeoutError):
                raise
            except Exception:
                raise ApiError(503, ErrorCode.DEPENDENCY_UNAVAILABLE,
                               "自动验证码识别暂不可用，请稍后重试或人工认证", True) from None
            deadline.remaining()
            if answer is not None:
                submissions += 1
                try:
                    return await protocol.authenticate(
                        payload["student_id"], payload["password"],
                        {"uid": challenge.uid, "cookies": challenge.cookies}, str(answer),
                        deadline=deadline, pool="background",
                    )
                except ApiError as error:
                    if error.code != ErrorCode.SCHOOL_LOGIN_REJECTED or submissions >= 2:
                        raise
                    # 明确拒绝后换一组学校会话/验证码，不复用已提交过的图。
                    challenge = None
            if image_index < 4 and challenge is not None:
                async with protocol.transport.client() as client:
                    restore_cookies(client, challenge.cookies)
                    challenge = await protocol.next_challenge(
                        client, challenge.uid, deadline, pool="background",
                    )
    raise ApiError(409, ErrorCode.SCHOOL_REAUTH_REQUIRED, "学校验证码需要人工认证")
