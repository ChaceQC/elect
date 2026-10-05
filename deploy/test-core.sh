#!/bin/sh
# 在已有一次性combined项目验证原卷13->7->13，不读取真实凭据。
set -eu
[ "$#" -eq 2 ] || exit 2
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sh "$task_root/deploy/test-state.sh" "$task_dir" "$task_project" combined
compose() {
  ELECT_DEPLOYMENT_MODE=core sh "$task_root/deploy/compose.sh" \
    "$task_dir/stack.env" "$task_project" --test "$@"
}
count_running() {
  task_count=$(docker ps --filter "label=com.docker.compose.project=$task_project" --format '{{.ID}}' | wc -l)
  [ "$task_count" -eq "$1" ] || { echo '模式切换后仍有旧角色或缺少容器' >&2; exit 1; }
}
status() {
  compose run -T --rm --no-deps -e ELECT_CORE_URL=https://identity:8000 \
    smoke python -m scripts.core_status "$1"
}
# 无源码发布组合也必须能解析和启动；实际镜像复用本轮受测runtime。
ELECT_IMAGE_MODE=published ELECT_DEPLOYMENT_MODE=core sh "$task_root/deploy/upgrade.sh" "$task_dir/stack.env" "$task_project" --test
count_running 7
status ready
compose exec -T nginx nginx -t
# 构建时版本清单已进入实际runtime，常驻入口不能重新加载Alembic。
compose exec -T core python -c 'import sys; from services.core.app import app; assert "alembic" not in sys.modules'
compose stop rabbitmq
status mq-down
compose up -d --no-build --no-deps --wait --wait-timeout 90 rabbitmq
status ready
compose stop core school-adapter mail-worker nginx
compose --restore up -d --no-build --no-deps --wait --wait-timeout 90 core school-adapter
status restored
compose --restore exec -T core python -c 'from services.common.background import require_standalone; require_standalone()' && exit 1
compose stop core school-adapter
compose run -T --rm --no-deps -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 \
  smoke python -m scripts.core_workload
compose run -T --rm --no-deps -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 \
  smoke python -m scripts.core_capacity
ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/upgrade.sh" "$task_dir/stack.env" "$task_project" --test
count_running 13
compose_combined() {
  ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/compose.sh" \
    "$task_dir/stack.env" "$task_project" --test "$@"
}
compose_combined run -T --rm --no-deps smoke python -m scripts.combined_status ready
echo '核心7容器、TLS/原权限/直接调用、恢复关闭及原卷13容器回退通过。'
