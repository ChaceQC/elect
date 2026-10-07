#!/bin/sh
# 三个独立运行器各准备自己的空库，不跨组共享业务状态。
set -eu
[ "$#" -eq 3 ] || exit 2
task_group=$1 task_dir=$2 task_project=$3
case "$task_group" in business|compatibility|delivery) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$task_root"
export ELECT_SKIP_BUILD=1 ELECT_TEST_GROUP_START=1
export ELECT_TEST_IMAGE=elect-backend-smoke:test ELECT_BROWSER_IMAGE=elect-frontend-browser-check
sh deploy/test-prepare.sh "$task_dir" "$task_project" combined
case "$task_group" in
  business)
    sh deploy/test-business.sh "$task_dir" "$task_project" combined
    sh deploy/test-resource-parameters.sh "$task_dir" "$task_project"
    sh deploy/test-execution-efficiency.sh "$task_dir" "$task_project"
    task_apps=$(docker ps --filter "label=com.docker.compose.project=$task_project" \
      --format '{{.ID}} {{.Label "com.docker.compose.service"}}' | \
      awk '$2 != "mysql" && $2 != "redis" && $2 != "rabbitmq" {print $1}')
    if [ -n "$task_apps" ]; then docker stop $task_apps >/dev/null; fi
    sh deploy/test-state.sh "$task_dir" "$task_project" stopped
    sh deploy/compose.sh "$task_dir/stack.env" "$task_project" --test run -T --rm --no-deps \
      -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 smoke python -m scripts.t7_capacity --plans 100 --workers 8
    sh deploy/test-t7-browser.sh "$task_dir" "$task_project";;
  compatibility)
    sh deploy/test-low-resource.sh "$task_dir" "$task_project"
    ELECT_QUERY_TEST_IMAGE=elect-backend-smoke:test sh deploy/test-r3-processes.sh;;
  delivery)
    sh deploy/test-image-delivery.sh "$task_dir" "$task_project"
    sh deploy/test-core.sh "$task_dir" "$task_project"
    sh deploy/test-t7-recovery.sh "$task_dir" "$task_project";;
esac
