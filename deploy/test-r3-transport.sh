#!/bin/sh
# 仅在一次性内部网络验证真实MQ停止/恢复与60秒以上合法降级，不挂载业务Secret。
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_image=${ELECT_QUERY_TEST_IMAGE:-elect-backend-check}
task_mq_image=${ELECT_R3_MQ_IMAGE:-rabbitmq@sha256:b736d649308e1b3e1a116c3f36986b605ee3d03e88f10166be2900083d2e63f2}
task_name="elect-test-r3-mq-$$"
task_network="${task_name}-network"
cleanup() {
  docker rm -f -v "$task_name" "${task_name}-mysql" "${task_name}-broker" >/dev/null 2>&1 || true
  docker network rm "$task_network" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM
docker network create --internal "$task_network" >/dev/null
docker run -d --name "${task_name}-mysql" --network "$task_network" --network-alias query-mysql \
  --memory 512m --tmpfs /var/lib/mysql:rw,size=384m -e MYSQL_ALLOW_EMPTY_PASSWORD=yes \
  mysql:8.4.6 --innodb-buffer-pool-size=64M --innodb-redo-log-capacity=32M \
  --performance-schema=OFF >/dev/null
docker run -d --name "${task_name}-broker" --network "$task_network" --network-alias query-mq \
  --memory 512m -e RABBITMQ_DEFAULT_USER=r3synthetic -e RABBITMQ_DEFAULT_PASS=r3synthetic \
  -e RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS='+S 1:1 +A 4' "$task_mq_image" >/dev/null
task_attempt=0
until docker exec "${task_name}-mysql" mysqladmin --protocol=tcp -h 127.0.0.1 ping --silent \
  >/dev/null 2>&1; do
  task_attempt=$((task_attempt + 1)); [ "$task_attempt" -lt 60 ] || exit 1
  sleep 1
done
docker run --rm --network "$task_network" \
  -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 -e PYTHONUTF8=1 \
  -v "$task_root/backend/services:/app/services:ro" \
  -v "$task_root/backend/scripts:/app/scripts:ro" \
  "$task_image" python -m scripts.r3_container_probe --prefix elect_r3_mq --prepare
docker run -d --name "$task_name" --network "$task_network" --restart unless-stopped \
  -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 -e PYTHONUTF8=1 \
  -v "$task_root/backend/services:/app/services:ro" \
  -v "$task_root/backend/scripts:/app/scripts:ro" \
  "$task_image" python -m scripts.r3_transport_probe >/dev/null
wait_status() {
  task_attempt=0
  until docker exec "$task_name" python -m scripts.r3_transport_probe --expect "$1" \
    2>/dev/null; do
    task_attempt=$((task_attempt + 1))
    if [ "$task_attempt" -ge 60 ]; then docker logs --tail 25 "$task_name"; exit 1; fi
    sleep 1
  done
}
wait_status ready
docker stop --time 5 "${task_name}-broker" >/dev/null
wait_status degraded
echo '真实MQ已停止；验证65秒持续降级不会误触发进程重启'
for step in 1 2 3 4 5 6 7 8 9 10 11 12 13; do sleep 5; done
wait_status degraded
test "$(docker inspect --format '{{.RestartCount}}' "$task_name")" = 0
docker start "${task_name}-broker" >/dev/null
wait_status ready
test "$(docker inspect --format '{{.RestartCount}}' "$task_name")" = 0
docker stop --time 40 "$task_name" >/dev/null
test "$(docker inspect --format '{{.State.ExitCode}}' "$task_name")" = 0
echo '真实MQ断连65秒/SQL成功扫描/HTTP200 degraded/恢复ready/重启0次：通过'
