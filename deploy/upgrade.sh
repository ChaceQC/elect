#!/bin/sh
# 使用已构建镜像升级/切换模式；先停止所有旧角色，保留Secret和数据卷。
set -eu
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo '用法：sh deploy/upgrade.sh /absolute/stack.env 项目名 [--test]' >&2; exit 2
fi
task_env=$1 task_project=$2
task_test=${3:-}
case "$task_test" in ''|--test) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose() { sh "$task_root/deploy/compose.sh" "$task_env" "$task_project" ${task_test:+--test} "$@"; }
compose config --quiet
# profile中的旧容器也必须停止，不能只up合并API后留下正在领取的旧Worker。
compose --profile '*' stop nginx gateway identity school-adapter room monitoring notification \
  notification-worker payment audit identity-relay school-relay room-relay monitoring-relay \
  notification-relay payment-relay audit-worker identity-recovery room-sync-worker \
  school-maintenance monitor-scheduler monitor-worker monitor-recovery monitor-alerts \
  notification-recovery payment-worker payment-recovery
compose up -d --no-build --wait --wait-timeout 180 mysql redis rabbitmq
compose run -T --rm --no-deps migrate
if compose config --services | grep -qx tls-check; then compose run -T --rm --no-deps tls-check; fi
compose up -d --no-build --wait --wait-timeout 180
compose ps -a
