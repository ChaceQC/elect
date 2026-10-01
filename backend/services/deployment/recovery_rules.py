"""备份窗口可能发生副作用：保留 unknown 和台账，暂停旧工作，要求人工对账。"""

RULES = {
    "identity": [
        "UPDATE app_sessions SET revoked_at=UTC_TIMESTAMP(6) WHERE revoked_at IS NULL",
        "UPDATE login_attempts SET next_reconcile_at=NULL "
        "WHERE state NOT IN ('session_issued','failed','expired')",
        "UPDATE credential_operations SET next_reconcile_at=NULL "
        "WHERE state IN ('accepted','running','reconciling','unknown')",
    ],
    "school_adapter": [
        "UPDATE school_credentials SET status='requires_reauth',use_allowed=0 "
        "WHERE status='active'",
        "UPDATE upstream_operations SET state='unknown',error_code='BACKUP_WINDOW_UNCERTAIN' "
        "WHERE state IN ('prepared','dispatched','reconciling','unknown')",
        "UPDATE payment_sessions SET lease_owner=NULL,lease_until=NULL,"
        "state=IF(flow_step='ready',state,'unknown')",
    ],
    "room": [
        "UPDATE room_operations SET state='reconciling',lease_owner=NULL,lease_until=NULL,"
        "next_reconcile_at=NULL,error_code='BACKUP_WINDOW_UNCERTAIN' "
        "WHERE type<>'binding_sync' AND state IN ('accepted','running','reconciling','unknown')",
        "UPDATE room_operations SET state='failed',lease_owner=NULL,lease_until=NULL,"
        "next_reconcile_at=NULL WHERE type='binding_sync' AND state IN ('accepted','running')",
        "UPDATE room_sync_state SET state='stale' WHERE state='loading'",
    ],
    "monitoring": [
        "UPDATE monitors SET state=IF(desired_enabled,'requires_reauth','disabled'),"
        "credential_allowed=0,generation=generation+1,version=version+1,"
        "active_run_id=NULL,next_run_at=NULL "
        "WHERE credential_allowed=1 OR active_run_id IS NOT NULL",
        "UPDATE monitor_runs SET state='cancelled',execution_epoch=execution_epoch+1,"
        "version=version+1,lease_owner=NULL,lease_until=NULL,next_attempt_at=NULL,"
        "finished_at=UTC_TIMESTAMP(6) WHERE state IN "
        "('pending','running','retry_wait','cancel_requested')",
        "UPDATE alert_slots SET state='delivery_unknown',send_lease_until=NULL "
        "WHERE state IN ('reserved','authorized')",
        "UPDATE send_permits SET expires_at=UTC_TIMESTAMP(6) WHERE expires_at>UTC_TIMESTAMP(6)",
    ],
    "notification": [
        "UPDATE notification_jobs SET state='delivery_unknown',version=version+1,"
        "execution_epoch=execution_epoch+1,lease_owner=NULL,lease_until=NULL,next_attempt_at=NULL,"
        "last_error_code='BACKUP_WINDOW_UNCERTAIN' "
        "WHERE state IN ('pending','sending','retry_wait')",
    ],
    "payment": [
        "UPDATE payment_orders SET state='submit_unknown',version=version+1,"
        "error_code='BACKUP_WINDOW_UNCERTAIN' WHERE cancelled_at IS NULL AND state IN "
        "('created','submitting','awaiting_payment','status_unknown')",
        "UPDATE payment_orders SET next_check_at=NULL,"
        "check_lease_owner=NULL,check_lease_until=NULL",
        "UPDATE payment_operations SET state='unknown',execution_epoch=execution_epoch+1,"
        "lease_owner=NULL,lease_until=NULL,next_attempt_at=NULL,"
        "error_code='BACKUP_WINDOW_UNCERTAIN' "
        "WHERE state IN ('accepted','running','reconciling') OR "
        "(state='unknown' AND COALESCE(error_code,'')<>'BACKUP_WINDOW_UNCERTAIN')",
    ],
}

OUTBOX_HOLD = (
    "UPDATE outbox_events SET available_at='9999-12-31 00:00:00',"
    "publish_lease_owner=NULL,publish_lease_until=NULL WHERE published_at IS NULL"
)
