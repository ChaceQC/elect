"""真实Payment/Adapter两库与合成学校会话，不加载运行配置或外发。"""

import asyncio
import secrets
from types import SimpleNamespace

from query_resource_support import database

from services.common.ids import new_id
from services.common.internal_dto import DispatchOrder, PaymentProofQuery
from services.common.security import Principal
from services.common.sql import execute, first
from services.payment import jobs, orders
from services.payment.api import CreateCommand
from services.school_adapter.application.payment_orders import SchoolOrders
from services.school_adapter.infrastructure.crypto import EnvelopeCrypto, KeyRing

PAYLOAD = {
    "school_room_id": "synthetic-room", "amount": "1.00", "pay_url": None,
    "prepay_id": None, "sdgl_order_id": None,
}


class Scenario:
    def __init__(self, payment, adapter):
        self.payment, self.adapter = payment, adapter
        self.owner, self.binding, self.credential = new_id(), new_id(), new_id()
        self.principal = Principal("payment", self.owner, 1, new_id())
        self.command = CreateCommand(
            binding_id=self.binding, amount="1.00", idempotency_key=str(new_id()),
        )
        self.posts, self.flows = 0, 0
        self.before_error = self.after_error = None
        client = SimpleNamespace(call=self.call)
        self.app = SimpleNamespace(state=SimpleNamespace(database=payment, service_client=client))
        state = SimpleNamespace(
            database=adapter, service_client=client,
            school_credentials=SimpleNamespace(
                crypto=EnvelopeCrypto(KeyRing("test", {"test": secrets.token_bytes(32)}))),
            school_sessions=SimpleNamespace(write_once=self.write_once),
            side_effect_policy=SimpleNamespace(payment_order_writes=True),
        )
        self.school = SchoolOrders(state)

    async def seed(self):
        async with self.adapter.begin() as conn:
            await execute(conn, "INSERT INTO school_credentials (id,owner_user_id,school_id,"
                "school_user_id_ciphertext,ciphertext,nonce,wrapped_dek,kek_version,algorithm,"
                "version,status,use_allowed,verified_at) VALUES (:id,:owner,'hbue',"
                ":data,:data,:nonce,:data,'test','AES-256-GCM',1,'active',1,UTC_TIMESTAMP(6))",
                id=self.credential.bytes, owner=self.owner.bytes, data=b"synthetic",
                nonce=bytes(12))
        self.order = (await self.create()).order_id

    async def create(self, *, version=1, command=None):
        return await orders.create_order(
            self.payment, self.principal, command or self.command,
            {"display_name": "合成寝室"},
            {"credential_ref": str(self.credential), "credential_version": version},
        )

    async def reauthenticate(self):
        async with self.adapter.begin() as conn:
            await execute(conn, "UPDATE school_credentials SET version=2 WHERE id=:id",
                          id=self.credential.bytes)

    async def read(self):
        return await orders.get_order(self.payment, self.owner, self.order)

    async def operation(self):
        async with self.payment.connect() as conn:
            return await first(conn, "SELECT * FROM payment_operations WHERE order_id=:id",
                               id=self.order.bytes)

    async def claim(self):
        row = await jobs.claim(self.payment, self.order)
        command = DispatchOrder(
            owner_user_id=self.owner, request_id=self.principal.request_id, order_id=self.order,
            upstream_operation_id=row["upstream_operation_id"], operation_id=row["operation_id"],
            lease_owner=row["lease_owner"], credential_ref=self.credential, credential_version=1,
            binding_id=self.binding, amount="1.00", currency="CNY",
        )
        return row, command

    async def call(self, service, path, scope, request, payload=None, *, principal=None):
        if (service, path) == ("payment", "/controls/dispatch-proof"):
            return await jobs.dispatch_proof(
                self.payment, principal.user_id, PaymentProofQuery.model_validate(payload))
        if (service, path) == ("room", "/controls/query-target"):
            return {"school_room_id": PAYLOAD["school_room_id"]}
        if (service, path) == ("school_adapter", "/payments/dispatch"):
            return await self.school.dispatch(DispatchOrder.model_validate(payload), principal)
        if (service, path) == ("school_adapter", "/payments/flow"):
            self.flows += 1
            return {"qr_status": "ready", "error_code": None}
        raise AssertionError(f"未登记的合成调用：{service} {path}")

    async def write_once(self, command, reserve, send):
        if self.before_error:
            raise self.before_error
        async with self.adapter.begin() as conn:
            await self.school.ledger.credential(conn, command)
        if not await reserve():
            return None
        self.posts += 1
        if self.after_error:
            raise self.after_error
        return {"code": 200, "data":
                "http://cwcwx.hbue.edu.cn/zhifu/payAccept.aspx?prePayId=synthetic"}


def run(case, monkeypatch):
    monkeypatch.setenv("ELECT_DB_POOL_SIZE", "2")
    monkeypatch.setenv("ELECT_DB_MAX_OVERFLOW", "1")

    async def scenario():
        async with database("payment", production_pool=True) as payment:
            async with database("school_adapter", production_pool=True) as adapter:
                value = Scenario(payment, adapter)
                await value.seed()
                async with asyncio.timeout(15):
                    await case(value)
    asyncio.run(scenario())
