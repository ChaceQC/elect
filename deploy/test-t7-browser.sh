#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then echo '用法：sh deploy/test-t7-browser.sh /absolute/test-dir elect-test-project' >&2; exit 2; fi
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_session="$task_dir/t7-browser"
[ ! -e "$task_session" ] || { echo '会话目录已存在，拒绝覆盖' >&2; exit 2; }
mkdir -m 700 "$task_session"
cd "$task_root"
compose() {
  docker compose --env-file "$task_dir/stack.env" -f deploy/compose.yaml \
    -f deploy/compose.test.yaml -f deploy/compose.ops.yaml -f deploy/compose.restore.yaml \
    -f deploy/compose.t7.yaml -p "$task_project" "$@"
}
compose run -T --rm --no-deps --user 0:0 --cap-add DAC_OVERRIDE --cap-add CHOWN \
  -e "ELECT_RESULT_UID=$(id -u)" -e "ELECT_RESULT_GID=$(id -g)" \
  -v "$task_session:/run/test" -v "$task_root/backend/scripts:/app/scripts:ro" smoke \
  python -m scripts.t7_browser_seed --output /run/test/session.json
compose up -d --no-build --wait --wait-timeout 90 gateway identity school-adapter room monitoring payment notification audit nginx
compose run -T --rm --no-deps -v "$task_session/session.json:/run/session.json:ro" \
  -v "$task_root/frontend/scripts:/app/scripts:ro" browser-stack > "$task_session/result.json"
cat "$task_session/result.json"
echo 'T7生产静态站点与真实容器接口回归通过；学校/SMTP出口和所有后台仍隔离。'
