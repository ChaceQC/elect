#!/bin/sh
# 已准备并健康的独立环境；合成驱动前停止后台，结束恢复原模式。
set -eu
[ "$#" -ge 2 ] && [ "$#" -le 3 ] || exit 2
task_dir=$1 task_project=$2 task_mode=${3:-standalone}
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
case "$task_mode" in standalone|combined) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$task_root"
compose() { sh deploy/compose.sh "$task_dir/stack.env" "$task_project" --test "$@"; }
if [ "$task_mode" = combined ]; then
  sh deploy/test-state.sh "$task_dir" "$task_project" combined
fi
compose run --rm --no-deps smoke
# 合成学校的事务/恢复验收由同进程驱动；真实 Worker 不得消费合成任务并访问学校。
if [ "$task_mode" = combined ]; then
  compose stop identity school-adapter room monitoring notification payment audit notification-worker
else
  compose stop identity-recovery room-sync-worker monitor-scheduler monitor-worker monitor-recovery monitoring-relay monitor-alerts notification-worker notification-recovery notification-relay payment-worker payment-recovery payment-relay
fi
compose run --rm --no-deps smoke python -m scripts.t2_smoke
compose run --rm --no-deps smoke python -m scripts.t3_control_smoke
compose run --rm --no-deps smoke python -m scripts.t3_credential_smoke
compose run --rm --no-deps smoke python -m scripts.t3_default_smoke
compose run --rm --no-deps smoke python -m scripts.t7_sync_smoke
compose run --rm --no-deps smoke python -m scripts.t3_binding_smoke
compose run --rm --no-deps smoke python -m scripts.t3_removal_smoke
compose run --rm --no-deps smoke python -m scripts.t4_query_smoke
compose run --rm --no-deps smoke python -m scripts.t4_monitor_smoke
compose run --rm --no-deps smoke python -m scripts.t5_alert_smoke
compose run --rm --no-deps smoke python -m scripts.t5_delivery_smoke
compose run --rm --no-deps smoke python -m scripts.t6_smoke
sh deploy/test-t4-dependencies.sh "$task_dir" "$task_project"
if [ "$task_mode" = combined ]; then
  compose up -d --no-build --no-deps --wait --wait-timeout 90 identity school-adapter room monitoring notification payment audit notification-worker
else
  compose up -d --no-build --no-deps --wait --wait-timeout 60 identity-recovery room-sync-worker monitor-scheduler monitor-worker monitor-recovery monitoring-relay monitor-alerts notification-worker notification-recovery notification-relay payment-worker payment-recovery payment-relay
fi
compose exec -T nginx nginx -t
compose run --rm --no-deps tls-check
compose ps -a
echo '一次性容器验收通过；使用同一 env/项目执行 down，保留命名卷供恢复检查。'
