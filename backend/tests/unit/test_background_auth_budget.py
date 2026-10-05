import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.common.errors import ErrorCode
from services.common.http import ApiError
from services.school_adapter.application.sessions import SchoolSessions
from services.school_adapter.infrastructure.transport import Deadline


class Protocol:
    def __init__(self, failures):
        self.images, self.submissions, self.fresh = 0, 0, 0
        self.failures, self.submitted_uids = list(failures), []
        self.transport = SimpleNamespace(client=self.client)

    @asynccontextmanager
    async def client(self):
        yield SimpleNamespace()

    async def challenge(self, **kwargs):
        self.fresh += 1
        return await self.next_challenge(None, str(self.fresh), kwargs["deadline"])

    async def next_challenge(self, client, uid, deadline, **kwargs):
        self.images += 1
        return SimpleNamespace(image="synthetic", uid=uid, cookies=[])

    async def authenticate(self, user, password, challenge, answer, **kwargs):
        self.submissions += 1
        self.submitted_uids.append(challenge["uid"])
        if self.failures:
            raise ApiError(401, self.failures.pop(0), "合成拒绝或故障")
        return "synthetic-token", "synthetic-user"


@pytest.mark.parametrize("answers,failures,images,submissions,error", [
    ([None] * 4 + ["3"], [], 5, 1, None),
    ([None] * 5, [], 5, 0, ErrorCode.SCHOOL_REAUTH_REQUIRED),
    (["3", "4"], [ErrorCode.SCHOOL_LOGIN_REJECTED], 2, 2, None),
    (["3", "4", "5"], [ErrorCode.SCHOOL_LOGIN_REJECTED] * 2,
     2, 2, ErrorCode.SCHOOL_LOGIN_REJECTED),
    ([None, None, "3", None, "4"], [ErrorCode.SCHOOL_LOGIN_REJECTED], 5, 2, None),
    (["3", "4"], [ErrorCode.SCHOOL_TIMEOUT], 1, 1, ErrorCode.SCHOOL_TIMEOUT),
])
def test_background_auth_enforces_shared_image_and_submission_budgets(
    answers, failures, images, submissions, error,
):
    protocol = Protocol(failures)
    session = SchoolSessions(None, None, protocol, None, solver=Mock(side_effect=answers))

    async def verify():
        attempt = session.background_auth(
            {"student_id": "synthetic", "password": "synthetic"}, Deadline(5),
        )
        if error:
            with pytest.raises(ApiError) as failure:
                await attempt
            assert failure.value.code == error
        else:
            assert await attempt == ("synthetic-token", "synthetic-user")
        assert (protocol.images, protocol.submissions) == (images, submissions)
        assert len(set(protocol.submitted_uids)) == submissions

    asyncio.run(verify())
