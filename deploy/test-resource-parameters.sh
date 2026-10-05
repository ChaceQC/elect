#!/bin/sh
# 健康combined隔离项目；资源探针自建事件，不是2GB容量验收。
set -eu
if [ "$#" -ne 2 ]; then echo '用法：test-resource-parameters.sh /absolute/test-dir elect-test-name' >&2; exit 2; fi
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sh "$task_root/deploy/test-state.sh" "$task_dir" "$task_project" combined
compose() {
  ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/compose.sh" "$task_dir/stack.env" \
    "$task_project" --test "$@"
}
smoke() {
  compose run -T --rm --no-deps -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 smoke "$@"
}
compose config --quiet
smoke python -m scripts.database_pool_probe
smoke python -m scripts.resource_parameters_smoke ready
task_settings=$(compose exec -T rabbitmq rabbitmqctl -q eval \
  '{erlang:system_info(schedulers_online),erlang:system_info(thread_pool_size),lists:keymember(rabbitmq_management,1,application:which_applications()),vm_memory_monitor:get_memory_limit()}.')
printf '%s\n' "$task_settings" | grep -qx '{1,2,false,134217728}'
# 真实流控后恢复；没有将未confirm事件标成已发布。
restore_watermark() {
  compose exec -T rabbitmq rabbitmqctl -q set_vm_memory_high_watermark absolute 128MiB >/dev/null 2>&1 || true
}
trap restore_watermark EXIT HUP INT TERM
compose exec -T rabbitmq rabbitmqctl -q set_vm_memory_high_watermark absolute 1MiB
task_attempt=0
until compose exec -T rabbitmq rabbitmqctl -q eval 'rabbit_alarm:get_alarms().' | grep -q resource_limit; do
  task_attempt=$((task_attempt + 1)); [ "$task_attempt" -lt 10 ] || exit 1; sleep 1
done
task_event=$(compose run -T --rm --no-deps smoke python -c 'from uuid import uuid4; print(uuid4())')
pressure() {
  compose run -T --rm --no-deps -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 \
    -e "ELECT_RESOURCE_EVENT_ID=$task_event" smoke python -m scripts.resource_parameters_smoke "$1"
}
pressure enqueue
pressure blocked
restore_watermark
pressure delivered
trap - EXIT HUP INT TERM
task_redis_id=$(compose ps -q redis)
task_redis_image=$(docker inspect "$task_redis_id" --format '{{.Config.Image}}')
sh "$task_root/deploy/test-redis-budget.sh" "$task_dir" "$task_project" "$task_redis_image"
compose exec -T mysql mysql --defaults-extra-file=/run/secrets/mysql_probe -Nse \
  'SHOW GLOBAL STATUS WHERE Variable_name IN ("Threads_connected","Max_used_connections","Connection_errors_max_connections")'
echo '共享池/健康、数据库持久性、MQ核心导入/流控和Redis预算回归通过；2GB/50人24小时未验收。'
