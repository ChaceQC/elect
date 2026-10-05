#!/bin/sh
# 仅清理由test-prepare记录的本次项目及其隔离恢复目标，包括卷。
set -eu
[ "$#" -eq 2 ] || exit 2
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
[ -f "$task_dir/test-project" ] || exit 0
[ "$(cat "$task_dir/test-project")" = "$task_project" ] || exit 2
for task_target in "$task_project" "elect-restore-$task_project"; do
  task_ids=$(docker ps -aq --filter "label=com.docker.compose.project=$task_target")
  if [ -n "$task_ids" ]; then docker rm -f -v $task_ids >/dev/null; fi
  task_ids=$(docker volume ls -q --filter "label=com.docker.compose.project=$task_target")
  if [ -n "$task_ids" ]; then docker volume rm $task_ids >/dev/null; fi
  task_ids=$(docker network ls -q --filter "label=com.docker.compose.project=$task_target")
  if [ -n "$task_ids" ]; then docker network rm $task_ids >/dev/null; fi
done
