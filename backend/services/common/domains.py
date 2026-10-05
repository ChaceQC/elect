"""领域数据库名称；常驻进程不导入迁移工具链。"""

DATABASES = {
    "identity": "elect_identity",
    "school_adapter": "elect_school",
    "room": "elect_room",
    "monitoring": "elect_monitoring",
    "notification": "elect_notification",
    "payment": "elect_payment",
    "audit": "elect_audit",
}

CORE_DOMAINS = tuple(domain for domain in DATABASES if domain != "school_adapter")
