#!/bin/sh
# 在已完成test-stack的隔离项目验证试点；失败保持业务进程停止。
set -eu
if [ "$#" -ne 2 ]; then
  echo '用法：sh deploy/test-monitoring-combined.sh /absolute/test-dir elect-test-project' >&2
  exit 2
fi
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose() {
  docker compose --env-file "$task_dir/stack.env" -f "$task_root/deploy/compose.yaml" \
    -f "$task_root/deploy/compose.test.yaml" -p "$task_project" "$@"
}
combined() {
  docker compose --env-file "$task_dir/stack.env" -f "$task_root/deploy/compose.yaml" \
    -f "$task_root/deploy/compose.test.yaml" -f "$task_root/deploy/compose.monitoring-combined.yaml" \
    -p "$task_project" "$@"
}
restored() {
  docker compose --env-file "$task_dir/stack.env" -f "$task_root/deploy/compose.yaml" \
    -f "$task_root/deploy/compose.test.yaml" -f "$task_root/deploy/compose.monitoring-combined.yaml" \
    -f "$task_root/deploy/compose.ops.yaml" -f "$task_root/deploy/compose.restore.yaml" \
    -p "$task_project" "$@"
}
combined config --quiet
compose stop monitoring monitoring-relay monitor-scheduler monitor-worker monitor-recovery \
  monitor-alerts identity-recovery room-sync-worker notification-worker notification-recovery \
  notification-relay payment-worker payment-recovery payment-relay
combined up -d --no-build --no-deps --wait --wait-timeout 90 monitoring
combined exec -T monitoring python -m services.common.healthcheck
combined exec -T monitoring python -c '
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8000/health/ready") as response:
    value = json.load(response)
assert set(value["background_roles"]) == {"relay", "scheduler", "worker", "recovery", "alerts"}
assert value["status"] == "ready"
print("容器内API/五角色健康：通过")
'
# 已建立的共享连接断线，也必须在有界等待后回到MySQL扫描。
combined stop rabbitmq
combined exec -T monitoring python -c '
import json, time, urllib.request
started = time.time()
for attempt in range(35):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=4) as response:
            value = json.load(response)
        if value["status"] == "degraded" and all(
            value["background_roles"][role]["last_success"] > started
            for role in ("scheduler", "worker", "recovery", "alerts")
        ):
            print("共享MQ连接断线后API降级、四角色仍推进持久扫描：通过")
            break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit("MQ中断后角色没有继续推进")
'
combined up -d --no-build --no-deps --wait --wait-timeout 90 rabbitmq
# 真正应用恢复组合，API可启动，但不得自动运行任何后台角色。
restored up -d --no-build --no-deps --wait --wait-timeout 90 monitoring
restored exec -T monitoring python -c '
import json, urllib.request
from services.common.background import background_enabled, require_standalone
with urllib.request.urlopen("http://127.0.0.1:8000/health/ready") as response:
    value = json.load(response)
assert value["background_roles"] == {} and not background_enabled()
try:
    require_standalone()
except RuntimeError:
    print("恢复组合启动API但禁用合并/独立后台：通过")
else:
    raise SystemExit("恢复组合没有禁止独立入口")
'
# 合成学校/数据库任务由同进程驱动，生产容器不得领取测试账号。
combined stop monitoring
compose run --rm --no-deps -e ELECT_TEST_DEBUG_FRAMES=1 smoke \
  python -m scripts.monitoring_combined_smoke
# 两种入口共享租约/屏障；试点验证后恢复本测试项目的原编排。
compose up -d --no-build --no-deps --wait --wait-timeout 90 monitoring monitoring-relay \
  monitor-scheduler monitor-worker monitor-recovery monitor-alerts
echo 'Monitoring生命周期试点通过；没有访问真实学校/SMTP/支付，未进行2GB容量验收。'
