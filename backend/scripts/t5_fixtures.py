"""T5 隔离数据库与本机 SMTP 模拟器，无公网外发。"""

import asyncio
from uuid import UUID

from scripts.t2_smoke import browser, fixture_apps, login, prepare
from services.common.app import create_app
from services.common.database import create_database
from services.common.ids import new_id
from services.common.internal_dto import EventEnvelope
from services.common.runtime import Runtime, read_secret
from services.common.service_client import ServiceClient
from services.common.sql import first
from services.monitoring.configuration import MonitorConfiguration
from services.monitoring.dto import MonitorPatch
from services.notification.consumer import consume_alert
from services.notification.email_crypto import EmailCrypto
from services.notification.smtp import SmtpConfig, SmtpTransport
from services.room.worker import control_tick, sync_tick


async def notification_app(apps):
    app = create_app("notification", business=True)
    runtime = Runtime.model_validate_json(read_secret("/run/secrets/notification_runtime.json"))
    app.state.runtime, app.state.public_origin = runtime, "https://elect.test.local"
    app.state.database = create_database(runtime.db_url.get_secret_value())
    app.state.email_crypto = EmailCrypto.load("/run/secrets/notification_encryption_key_bundle")
    app.state.smtp = None
    app.state.service_client = ServiceClient(
        runtime, transport=apps["monitoring"].state.service_client.client._transport
    )
    apps["notification"] = app
    return app


async def setup():
    apps, _ = await fixture_apps()
    await notification_app(apps)
    return apps


async def owner_with_monitor(apps):
    async with browser(apps["gateway"]) as client:
        user = await login(client, await prepare(client, "synthetic-t5-" + str(new_id())))
        owner = UUID(user["id"])
        await client.post("/api/v1/room-bindings/sync", headers={"Idempotency-Key": str(new_id())})
        assert await sync_tick(apps["room"])
        for _ in range(5):
            await control_tick(apps["room"])
    config = MonitorConfiguration(
        apps["monitoring"].state.database, apps["monitoring"].state.email_crypto
    )
    saved = await config.get(owner)
    await config.patch(
        owner,
        MonitorPatch(
            expected_version=saved.version, enabled=True, email="synthetic@example.invalid"
        ),
        new_id(),
    )
    return owner


async def event_for_sample(app, sample):
    async with app.state.database.connect() as conn:
        slot = await first(conn, "SELECT * FROM alert_slots WHERE sample_id=:id", id=sample.bytes)
        row = await first(
            conn,
            "SELECT payload FROM outbox_events WHERE type='monitor.alert_reserved' "
            "AND JSON_UNQUOTE(JSON_EXTRACT(payload,'$.payload.alert_slot_id'))=:id "
            "ORDER BY event_id LIMIT 1",
            id=str(UUID(bytes=slot["id"])),
        )
    return (
        EventEnvelope.model_validate_json(row["payload"])
        if isinstance(row["payload"], str)
        else EventEnvelope.model_validate(row["payload"])
    )


async def make_job(apps, sample):
    event = await event_for_sample(apps["monitoring"], sample)
    await consume_alert(apps["notification"], event)
    async with apps["notification"].state.database.connect() as conn:
        row = await first(
            conn,
            "SELECT * FROM notification_jobs WHERE alert_slot_id=:id",
            id=event.payload.alert_slot_id.bytes,
        )
    return row, event


async def close_apps(apps):
    from scripts.t4_monitor_smoke import cleanup

    await cleanup(apps["monitoring"])
    for app in apps.values():
        await app.state.service_client.close()
        if hasattr(app.state, "redis"):
            await app.state.redis.aclose()
        if app.state.database:
            await app.state.database.dispose()


class SmtpSimulator:
    def __init__(self, mode="accepted"):
        self.mode, self.connections, self.messages = mode, 0, []

    async def __aenter__(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        port = self.server.sockets[0].getsockname()[1]
        self.transport = SmtpTransport(
            SmtpConfig(
                host="127.0.0.1",
                port=port,
                sender="sender@example.invalid",
                username="",
                password="",
                tls="test_plain",
            ),
            test=True,
        )
        return self

    async def __aexit__(self, *args):
        self.server.close()
        await self.server.wait_closed()

    async def handle(self, reader, writer):
        self.connections += 1
        writer.write(b"220 test\r\n")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                if line.startswith(b"RCPT") and self.mode == "permanent":
                    writer.write(b"550 rejected\r\n")
                elif (
                    line.startswith(b"RCPT") and self.mode == "temporary" and self.connections == 1
                ):
                    writer.write(b"451 temporary\r\n")
                elif line == b"DATA\r\n":
                    writer.write(b"354 body\r\n")
                    await writer.drain()
                    lines = []
                    while (line := await reader.readline()) != b".\r\n":
                        if not line:
                            return
                        lines.append(line)
                    self.messages.append(b"".join(lines))
                    if self.mode == "disconnect":
                        return
                    writer.write(b"250 accepted\r\n")
                else:
                    writer.write(b"250 ok\r\n")
                await writer.drain()
        finally:
            writer.close()
