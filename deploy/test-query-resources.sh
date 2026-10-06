#!/bin/sh
# 仅用一次性 MySQL 和 internal 网络验证受理配额；无外部端口或业务 Secret。
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_image=${ELECT_QUERY_TEST_IMAGE:-elect-backend-check}
task_name="elect-test-query-$$"
task_network="${task_name}-network"
task_mysql="${task_name}-mysql"
if [ "$#" -eq 0 ]; then
  set -- tests/integration/test_snapshot_admission.py tests/integration/test_history_admission.py \
    tests/integration/test_history_completion.py tests/integration/test_login_resources.py \
    tests/integration/test_balance_observations.py tests/integration/test_history_execution.py \
    tests/integration/test_paid_balance_terminal.py tests/integration/test_request_admission.py \
    tests/integration/test_snapshot_cleanup_rounds.py tests/integration/test_retention_archive.py \
    tests/integration/test_retention_temporary.py tests/integration/test_retention_payment.py \
    tests/integration/test_read_contention.py tests/integration/test_sample_lookup.py \
    tests/integration/test_read_scheduling.py tests/integration/test_read_mix.py \
    tests/integration/test_local_session.py tests/integration/test_recovery_observations.py \
    tests/integration/test_r7_upgrade.py tests/integration/test_r7_recovery.py
fi
cleanup() {
  docker rm -f -v "$task_name" "$task_mysql" >/dev/null 2>&1 || true
  docker network rm "$task_network" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM
docker network create --internal "$task_network" >/dev/null
docker run -d --name "$task_mysql" --network "$task_network" --network-alias query-mysql \
  --memory 512m --tmpfs /var/lib/mysql:rw,size=384m \
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes mysql:8.4.6 \
  --innodb-buffer-pool-size=64M --innodb-redo-log-capacity=32M --performance-schema=OFF \
  >/dev/null
task_attempt=0
until docker exec "$task_mysql" mysqladmin --protocol=tcp -h 127.0.0.1 ping --silent \
  >/dev/null 2>&1; do
  task_attempt=$((task_attempt + 1))
  if [ "$task_attempt" -ge 60 ]; then echo '一次性 MySQL 启动超时' >&2; exit 1; fi
  sleep 1
done
docker run --rm --name "$task_name" --network "$task_network" \
  -e ELECT_TEST_QUERY_MYSQL_HOST=query-mysql -e PYTHONUTF8=1 \
  -v "$task_root/backend/services:/app/services:ro" \
  -v "$task_root/backend/tests:/app/tests:ro" \
  -v "$task_root/backend/scripts:/app/scripts:ro" \
  "$task_image" python -m pytest -q --tb=short \
  "$@"
