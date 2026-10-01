"""T4可靠唤醒队列及最小资源/Topic权限，支持重复升级。"""


def configure(definitions):
    queues = {
        "monitoring": ("elect.monitoring.runs", "monitor.run_ready"),
        "room": ("elect.room.history", "room.history_sync_requested"),
    }
    for permission in definitions["permissions"]:
        service = permission["user"]
        if service not in queues:
            continue
        queue, _ = queues[service]
        resources = "^elect\\.(events|" + queue.removeprefix("elect.").replace(".", "\\.") + ")$"
        permission.update(configure=resources, read=resources, write=resources)
    for permission in definitions["topic_permissions"]:
        service = permission["user"]
        if service in queues:
            _, event = queues[service]
            permission["write"] = "^(audit\\.recorded|" + event.replace(".", "\\.") + ")$"
            permission["read"] = "^" + event.replace(".", "\\.") + "$"
    for queue, event in queues.values():
        if not any(row["name"] == queue for row in definitions["queues"]):
            definitions["queues"].append(
                {
                    "name": queue,
                    "vhost": "elect",
                    "durable": True,
                    "auto_delete": False,
                    "arguments": {},
                }
            )
        if not any(
            row["destination"] == queue and row["routing_key"] == event
            for row in definitions["bindings"]
        ):
            definitions["bindings"].append(
                {
                    "source": "elect.events",
                    "vhost": "elect",
                    "destination": queue,
                    "destination_type": "queue",
                    "routing_key": event,
                    "arguments": {},
                }
            )
