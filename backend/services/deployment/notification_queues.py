"""T5 提醒/回报队列，保留 T4 队列权限；可重复升级。"""


def configure(definitions):
    queues = {
        "notification": ("elect.notification.alerts", "monitor.alert_reserved"),
        "monitoring": ("elect.monitoring.deliveries", "notification.delivery_reported"),
    }
    for permission in definitions["permissions"]:
        service = permission["user"]
        if service in queues:
            resources = (
                "^elect\\.(events|notification\\.alerts)$"
                if service == "notification"
                else "^elect\\.(events|monitoring\\.(runs|deliveries))$"
            )
            permission.update(configure=resources, read=resources, write=resources)
    for permission in definitions["topic_permissions"]:
        if permission["user"] == "monitoring":
            permission.update(
                write="^(audit\\.recorded|monitor\\.(run_ready|alert_reserved))$",
                read="^(monitor\\.run_ready|notification\\.delivery_reported|"
                     "room\\.binding_confirmed)$",
            )
        elif permission["user"] == "notification":
            permission.update(
                write="^(audit\\.recorded|notification\\.delivery_reported)$",
                read="^monitor\\.alert_reserved$",
            )
    for queue, event in [*queues.values(), ("elect.monitoring.runs", "room.binding_confirmed")]:
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
