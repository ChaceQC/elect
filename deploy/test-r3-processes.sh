#!/bin/sh
# 一次性MySQL/三个真实入口容器；不加载业务Secret、学校、SMTP或现有Compose项目。
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_image=${ELECT_QUERY_TEST_IMAGE:-elect-backend-check}
task_name="elect-test-r3-$$"
task_network="${task_name}-network"
task_mysql="${task_name}-mysql"
cleanup() {
  for mode in core combined standalone; do
    docker rm -f -v "${task_name}-${mode}" >/dev/null 2>&1 || true
  done
  docker rm -f -v "$task_mysql" >/dev/null 2>&1 || true
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
  if [ "$task_attempt" -ge 60 ]; then echo 'R3一次性MySQL启动超时' >&2; exit 1; fi
  sleep 1
done
for mode in core combined standalone; do
  prefix="elect_r3_${mode}"
  docker run --rm --network "$task_network" \
    -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 -e PYTHONUTF8=1 \
    -v "$task_root/backend/services:/app/services:ro" \
    -v "$task_root/backend/scripts:/app/scripts:ro" \
    "$task_image" python -m scripts.r3_container_probe --prefix "$prefix" --prepare
  docker run -d --name "${task_name}-${mode}" --network "$task_network" \
    --restart unless-stopped --health-cmd 'python -m services.common.healthcheck worker' \
    --health-interval 1s --health-timeout 5s --health-start-period 3s --health-retries 1 \
    -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 -e PYTHONUTF8=1 \
    -v "$task_root/backend/services:/app/services:ro" \
    -v "$task_root/backend/scripts:/app/scripts:ro" \
    "$task_image" python -m scripts.r3_container_probe --prefix "$prefix" --mode "$mode" \
    >/dev/null
  task_attempt=0
  until docker exec "${task_name}-${mode}" python -m scripts.r3_container_probe \
    --prefix "$prefix" --status 2>/dev/null; do
    task_attempt=$((task_attempt + 1))
    if [ "$task_attempt" -ge 60 ]; then
      docker logs --tail 30 "${task_name}-${mode}"
      echo 'R3自动重启/恢复未通过' >&2
      exit 1
    fi
    sleep 1
  done
  test "$(docker inspect --format '{{.RestartCount}}' "${task_name}-${mode}")" = 1
  docker logs "${task_name}-${mode}" 2>&1 | \
    grep -F '"error_code": "BUSINESS_FAILURE_BUDGET"' >/dev/null
  docker exec "${task_name}-${mode}" python -m services.common.healthcheck worker
  docker stop --time 5 "${task_name}-${mode}" >/dev/null
  test "$(docker inspect --format '{{.State.ExitCode}}' "${task_name}-${mode}")" = 0
  echo "$mode：真实自动重启1次、旧epoch拒绝、D01/DATA各1次且unknown保留、正常停止0"
done
