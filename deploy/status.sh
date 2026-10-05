#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then echo '用法：sh deploy/status.sh /absolute/stack.env 项目名' >&2; exit 2; fi
task_env=$1 task_project=$2
case "$task_env" in /*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose() {
  sh "$task_root/deploy/compose.sh" "$task_env" "$task_project" "$@"
}
compose ps --format json
compose run -T --rm --no-deps operations-status
compose exec -T rabbitmq rabbitmqctl -q list_queues name messages_ready messages_unacknowledged consumers
compose exec -T mysql df -Pk /var/lib/mysql
task_ids=$(compose ps -q)
if [ -n "$task_ids" ]; then
  docker stats --no-stream --format '{{json .}}' $task_ids
fi
