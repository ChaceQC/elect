#!/bin/sh
# 仅用于隔离test-stack；所有学校HTTP均由脚本中的合成transport处理。
set -eu
task_dir=$1
task_project=$2
case "$task_project" in elect-test-*) ;; *) exit 2 ;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_fault="$task_dir/t4-fault"
# 保留宿主机属主；容器通过 GID 10001 写状态，Runner 仍可写日志/检查就绪文件。
mkdir -m 770 "$task_fault"
compose() {
  docker compose --env-file "$task_dir/stack.env" -f "$task_root/deploy/compose.yaml" \
    -f "$task_root/deploy/compose.test.yaml" -p "$task_project" "$@"
}
fault() {
  compose run --rm --no-deps -e ELECT_TEST_DEBUG_FRAMES=1 \
    -v "$task_fault:/run/fault" -v "$task_root/backend/services:/app/services:ro" \
    -v "$task_root/backend/scripts:/app/scripts:ro" smoke \
    python -m scripts.t4_dependency_smoke --record /run/fault/state.json --mode "$1"
}
compose run --rm --no-deps --user 0:0 --cap-add CHOWN --cap-add DAC_OVERRIDE \
  --entrypoint sh -v "$task_fault:/run/fault" smoke -c 'chgrp 10001 /run/fault'
compose stop identity-recovery room-sync-worker monitor-scheduler monitor-worker monitor-recovery monitoring-relay monitor-alerts notification-worker notification-recovery notification-relay
fault prepare
compose stop redis
fault redis-down
compose up -d --no-build --no-deps --wait --wait-timeout 90 redis
fault hold > "$task_fault/hold.log" 2>&1 &
task_hold_pid=$!
task_ticks=0
while [ ! -f "$task_fault/state.ready" ]; do
  task_ticks=$((task_ticks + 1))
  if [ "$task_ticks" -gt 45 ]; then echo '合成学校请求未进入测试窗口' >&2; exit 1; fi
  sleep 1
done
compose stop mysql
wait "$task_hold_pid"
compose up -d --no-build --no-deps --wait --wait-timeout 90 mysql
fault recover
compose stop rabbitmq
# MQ断开期间真实Worker仍连接MySQL并报告有效扫描心跳，配置/历史不依赖MQ。
compose up -d --no-build --no-deps --wait --wait-timeout 60 monitor-worker
compose exec -T monitor-worker python -m services.common.healthcheck worker
compose stop monitor-worker
compose up -d --no-build --no-deps --wait --wait-timeout 90 rabbitmq
echo 'T4真实Redis/MySQL中断恢复和MQ断开数据库扫描通过；合成监控已关闭。'
