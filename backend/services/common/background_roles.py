"""领域内角色组合；邮件发送保持独立，Gateway没有后台或业务库。"""

from functools import partial

from .background import Role
from .job import transport_loop

BUSINESS_ROLES = {"identity": "recovery", "room": "worker", "school_adapter": "cleanup"}


def roles(service):
    if service == "gateway":
        return []
    if service == "monitoring":
        from services.monitoring.job import roles as monitoring_roles

        return monitoring_roles()
    if service == "audit":
        return [Role("audit", transport_loop, max_age=45)]
    relay = Role("relay", transport_loop, max_age=45)
    if service in BUSINESS_ROLES:
        from .business_worker import business_loop

        return [relay, Role(BUSINESS_ROLES[service], partial(business_loop, service))]
    if service == "notification":
        from services.notification.job import role_loop

        return [relay, Role("recovery", partial(role_loop, "recovery"), max_age=45)]
    if service == "payment":
        from services.payment.process import role_loop

        return [relay, *(Role(role, partial(role_loop, role)) for role in ("worker", "recovery"))]
    raise RuntimeError("未知领域角色组合")
