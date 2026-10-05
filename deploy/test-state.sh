#!/bin/sh
# 只检查明确测试项目的公开容器元数据，不读取Secret或容器环境变量。
set -eu
[ "$#" -eq 3 ] || exit 2
task_dir=$1 task_project=$2 task_state=$3
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
case "$task_state" in absent)
  [ -z "$(docker ps -aq --filter "label=com.docker.compose.project=$task_project")" ] || {
    echo '测试项目已有容器，拒绝当作空环境' >&2; exit 1;
  }
  for task_kind in volume network; do
    [ -z "$(docker "$task_kind" ls -q --filter "label=com.docker.compose.project=$task_project")" ] || {
      echo '测试项目已有资源，拒绝当作空环境' >&2; exit 1;
    }
  done
  exit 0;;
esac
[ -f "$task_dir/stack.env" ] || exit 2
task_running=$(docker ps --filter "label=com.docker.compose.project=$task_project" \
  --format '{{.ID}} {{.Label "com.docker.compose.service"}}')
case "$task_state" in
  combined)
    [ "$(printf '%s\n' "$task_running" | wc -l)" -eq 13 ] || {
      echo '前置状态要求combined的13个运行容器' >&2; exit 1;
    }
    task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
    ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/compose.sh" "$task_dir/stack.env" \
      "$task_project" --test run -T --rm --no-deps smoke python -m scripts.combined_status ready;;
  stopped)
    [ -z "$(printf '%s\n' "$task_running" | awk 'NF && $2 != "mysql" && $2 != "redis" && $2 != "rabbitmq"')" ] || {
      echo '合成驱动要求本项目全部应用/profile角色停止' >&2; exit 1;
    };;
  *) exit 2;;
esac
