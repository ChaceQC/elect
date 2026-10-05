#!/bin/sh
# 已准备健康combined的独立空库；合成数据由本脚本生成，不作为2GB容量验收。
set -eu
if [ "$#" -ne 2 ]; then echo '用法：sh deploy/test-low-resource.sh /absolute/test-dir elect-test-project' >&2; exit 2; fi
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sh "$task_root/deploy/test-state.sh" "$task_dir" "$task_project" combined
compose() {
  ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/compose.sh" \
    "$task_dir/stack.env" "$task_project" --test "$@"
}
restored() {
  ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/compose.sh" \
    "$task_dir/stack.env" "$task_project" --test --restore "$@"
}
smoke() {
  compose run -T --rm --no-deps -e ELECT_DB_POOL_SIZE=2 -e ELECT_DB_MAX_OVERFLOW=1 \
    -e ELECT_TEST_DEBUG_FRAMES=1 smoke "$@"
}
count_running() {
  task_count=$(compose --profile '*' ps --status running --services | wc -l | tr -d ' ')
  [ "$task_count" -eq "$1" ] || { echo '运行容器数不符合组合预期' >&2; exit 1; }
}
snapshot() {
  task_ids=$(compose --profile '*' ps -q --status running)
  docker stats --no-stream --format '{{json .}}' $task_ids > "$task_dir/$1-stats.jsonl"
}
ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/upgrade.sh" "$task_dir/stack.env" "$task_project" --test
count_running 13
compose run -T --rm --no-deps smoke python -m scripts.combined_status ready
compose exec -T rabbitmq rabbitmqctl -q list_connections user channels
snapshot combined
compose stop rabbitmq
compose run -T --rm --no-deps smoke python -m scripts.combined_status mq-down
compose up -d --no-build --no-deps --wait --wait-timeout 90 rabbitmq
compose stop gateway identity school-adapter room monitoring notification payment audit notification-worker
restored up -d --no-build --no-deps --wait --wait-timeout 90 gateway identity school-adapter room monitoring notification payment audit
restored run -T --rm --no-deps smoke python -m scripts.combined_status restored
restored exec -T payment python -c '
from services.common.background import background_enabled, require_standalone
assert not background_enabled()
try:
    require_standalone()
except RuntimeError:
    print("恢复组合同时拒绝合并/独立入口：通过")
else:
    raise SystemExit("独立后台未被禁用")
'
restored stop gateway identity school-adapter room monitoring notification payment audit
smoke python -m scripts.monitoring_combined_smoke
smoke python -m scripts.domain_combined_smoke
# 原卷与Secret不变，验证双向模式升级及旧profile角色全部停止。
ELECT_DEPLOYMENT_MODE=standalone sh "$task_root/deploy/upgrade.sh" "$task_dir/stack.env" "$task_project" --test
count_running 30
snapshot standalone
ELECT_DEPLOYMENT_MODE=combined sh "$task_root/deploy/upgrade.sh" "$task_dir/stack.env" "$task_project" --test
count_running 13
compose run -T --rm --no-deps smoke python -m scripts.combined_status ready
echo '13容器、七域角色、MQ降级扫描、恢复禁用与原卷双向升级通过；未进行2GB/50人24小时验收。'
