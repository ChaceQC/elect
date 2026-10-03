#!/bin/sh
# 已完成test-stack的隔离项目；第四步回归，不作为2GB容量验收。
set -eu
if [ "$#" -ne 2 ]; then echo '用法：test-execution-efficiency.sh /absolute/test-dir elect-test-name' >&2; exit 2; fi
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose() {
  ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/compose.sh" "$task_dir/stack.env" \
    "$task_project" --test "$@"
}
smoke() {
  compose run -T --rm --no-deps -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 smoke "$@"
}
compose config --quiet
compose stop gateway identity school-adapter room monitoring notification payment audit notification-worker
smoke python -m scripts.outbox_efficiency_smoke relay
task_ipc=$(mktemp -d "$task_dir/efficiency.XXXXXX")
# 同T4故障入口：宿主用户保有写入权限，容器组可写，其他用户无权访问。
docker run --rm --network none --user 0:0 -v "$task_ipc:/run/efficiency" \
  --entrypoint sh "${ELECT_TEST_IMAGE:-elect-backend-smoke:test}" \
  -c 'chgrp 10001 /run/efficiency && chmod 0770 /run/efficiency'
compose run -T --rm --no-deps -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 \
  -v "$task_ipc:/run/efficiency" smoke python -m scripts.outbox_efficiency_smoke push \
  > "$task_ipc/push.log" 2>&1 &
task_pid=$!
recover_mq() {
  compose up -d --no-build --no-deps --wait --wait-timeout 90 rabbitmq >/dev/null 2>&1 || true
}
trap recover_mq EXIT HUP INT TERM
task_attempt=0
until [ -f "$task_ipc/ready" ]; do
  kill -0 "$task_pid" 2>/dev/null || { cat "$task_ipc/push.log"; exit 1; }
  task_attempt=$((task_attempt + 1)); [ "$task_attempt" -lt 60 ] || exit 1; sleep 1
done
compose stop rabbitmq
compose up -d --no-build --no-deps --wait --wait-timeout 90 rabbitmq
touch "$task_ipc/reconnected"
if ! wait "$task_pid"; then cat "$task_ipc/push.log"; exit 1; fi
cat "$task_ipc/push.log"
smoke python -m scripts.monitoring_parallel_smoke
compose stop rabbitmq
compose run -T --rm --no-deps -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 \
  -e ELECT_EFFICIENCY_MQ_DOWN=1 smoke python -m scripts.monitoring_parallel_smoke
recover_mq
trap - EXIT HUP INT TERM
compose up -d --no-build --no-deps --wait --wait-timeout 90 gateway identity school-adapter room monitoring notification payment audit notification-worker
smoke python -m scripts.combined_status ready
echo '提交后提示/退避、推送重投与并发取消/持久扫描回归通过；2GB/50人24小时未验收。'
