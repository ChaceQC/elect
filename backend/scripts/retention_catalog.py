"""由实际迁移声明生成R4表/主键/外键/敏感字段清单，不读取业务库。"""

import argparse
from pathlib import Path

from scripts.schema_catalog import catalog

TARGET = Path(__file__).resolve().parents[2] / "docs/database/保留与归档引用清单.md"
POLICIES = {
    "app_sessions": "永久失效7天且无login_attempts.issued_session_id恢复引用才清理；会话验证入口",
    "login_attempts": "终态/过期7天可解联旧会话；challenge与摘要作为防重放索引保留；LoginSaga入口",
    "credential_staging": ("到期staged/expired/activated只擦除敏感载荷；"
                           "激活回执和版本保留；Adapter认证入口"),
    "room_operations": ("仅balance_refresh/history_sync终态180天；无FK/稳定upstream引用才转冷；"
                        "operation与原键支持冷读"),
    "monitor_run_requests": ("终态run及创建180天后转冷；旧七天expires取created+180天较晚值；"
                             "原键返回原run"),
    "payment_qr_requests": "映射/操作180天且订单明确终态、无在途回查才转冷；原键返回原operation",
    "monitor_attempts": "终态run/attempt180天后转冷；run_view热冷合并、按id去重",
    "monitor_runs": "保留轻量行作为逻辑槽唯一键及样本/手动请求/最近运行索引；不破坏长期查询",
    "outbox_events": "已published180天且无发布租约可归档；未发布/重试不清理；恢复隔离旧未发布消息",
    "inbox_events": "processed180天后与永久cold_inbox_events同事务转换；消费先插热唯一键再检查冷键",
    "sample_snapshots": "30分钟TTL；分页共享锁优先；最多4父行和1000成员/批，父行完成才释放配额",
    "sample_snapshot_items": "仅已过期父行下按position顺序小批删除；原始sample外键不反向删除",
    "archive_records": "永久保留格式版本/单行数/压缩载荷/SHA256；既有领域DB访问边界与全库加密备份",
    "cold_request_keys": "永久owner/type/key摘要及结果引用；缺失/损坏503，不降级成新请求",
    "cold_inbox_events": "永久consumer/event唯一标识；缺失表导致事务失败，保留原去重语义",
}
SOFT = {
    "room_operations": ("upstream_operation_id合并根；"
                        "Payment.balance_refresh_operation_id跨域只经API访问"),
    "monitor_runs": ("monitors.active_run_id、逻辑槽(monitor_id,generation,scheduled_for)"
                     "和最近运行查询"),
    "notification_jobs": ("alert_slot_id/send_permits、body_started_at、message_id；"
                          "DATA/unknown不可因年龄解除"),
    "upstream_operations": "D01/E02/E03 dispatched/unknown及adapter_payment_orders；不自动删除",
    "school_credentials": "Identity.credential_ref仅通过内部API引用；当前凭据不得由暂存清理删除",
    "balance_observation_counters": "Room余额序号高水位；恢复不可归零",
}


def render():
    lines = ["# 保留与归档引用清单", "", "由实际迁移声明生成；只包含结构，不含业务数据。",
             "未列自动归档策略的表默认完整保留，尤其原始样本/学校历史/订单/同意/审计/未知发送证据。",
             "复合外键与自引用由schema catalog完整给出；"
             "运行时归档复核本库information_schema实际约束。",
             "存量维护仅运行登记类别、固定安全状态和截止时间，不接受任意表名/SQL或跨库查询。", ""]
    for domain, data in catalog()["databases"].items():
        lines.extend([f"## {domain} / {data['revision']}", ""])
        for table, definition in data["tables"].items():
            columns = definition["columns"]
            keys = [name for name, col in columns.items() if col["primary_key"]]
            sensitive = [name for name in columns if any(word in name for word in
                         ("ciphertext", "payload", "token", "nonce", "wrapped", "hash", "digest"))]
            foreign = ["("+",".join(fk["columns"])+")→("+",".join(fk["targets"])+")"
                       for fk in definition["foreign_keys"]]
            lines.extend([f"### {table}", "", f"- 主键：{', '.join(keys)}。",
                f"- 唯一约束：{definition['unique']}。",
                f"- 实际外键：{'; '.join(foreign) or '无'}。",
                f"- 敏感/摘要字段：{', '.join(sensitive) or '无此类字段'}；不打印原值。",
                "- 查询/状态/保留："
                f"{POLICIES.get(table, '当前领域业务/API与恢复仍依赖，默认保留全部状态')}。",
                "- 恢复/软引用："
                f"{SOFT.get(table, '保持原领域读写和恢复规则；不因归档解除授权或未知台账')}。", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = render()
    if args.check:
        if TARGET.read_text(encoding="utf-8") != content:
            raise SystemExit("保留引用清单未同步")
    else:
        TARGET.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
