"""合成验收等待本人默认终态；不假设全局队列长度。"""

from services.room.worker import control_tick


async def ready_default(client, room_app):
    for _ in range(100):
        response = await client.get("/api/v1/room-bindings?page_size=100")
        assert response.status_code == 200
        data = response.json()["data"]
        if data["default_binding_id"] and not data["default_switch_operation_id"]:
            return data
        assert await control_tick(room_app), "默认寝室仍未确认，队列当前没有可执行任务"
    raise AssertionError("默认寝室未在有限任务预算内完成")


async def select_default(client, room_app, number):
    data = await ready_default(client, room_app)
    target = next(item["id"] for item in data["items"] if item["number"] == number)
    if data["default_binding_id"] != target:
        response = await client.put(
            "/api/v1/room-preferences/default",
            json={"binding_id": target, "expected_version": data["preference_version"]},
        )
        assert response.status_code == 202
        data = await ready_default(client, room_app)
    assert data["default_binding_id"] == target
    return data
