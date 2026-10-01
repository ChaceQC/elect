#!/bin/sh
# 只向显式新隔离环境导入；先完整认证，再流式解密入MySQL。
set -eu
if [ "$#" -ne 4 ]; then
  echo '用法：sh deploy/restore.sh /absolute/restore.env elect-restore-项目 /absolute/backup.key /absolute/snapshot.electbackup' >&2
  exit 2
fi
task_env=$1 task_project=$2 task_key=$3 task_backup=$4
case "$task_project" in elect-restore-*) ;; *) echo '恢复项目名必须以elect-restore-开头' >&2; exit 2;; esac
for task_path in "$task_env" "$task_key" "$task_backup"; do
  case "$task_path" in /*) ;; *) echo '路径必须绝对' >&2; exit 2;; esac
done
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose() {
  docker compose --env-file "$task_env" -f "$task_root/deploy/compose.yaml" \
    -f "$task_root/deploy/compose.ops.yaml" -f "$task_root/deploy/compose.restore.yaml" \
    -p "$task_project" "$@"
}
task_running=$(compose ps --status running --services)
for task_service in $task_running; do
  case "$task_service" in mysql|redis|rabbitmq) ;; *)
    echo '恢复目标有应用或后台进程运行，拒绝导入' >&2; exit 2;; esac
done
compose config --quiet
compose run -T --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$task_key:/run/backup.key:ro" -v "$task_backup:/backup/input:ro" backup-crypto \
  verify --key-file /run/backup.key --file /backup/input
compose up -d --no-build --wait --wait-timeout 180 mysql redis rabbitmq
compose run -T --rm --no-deps migrate
compose run -T --rm --no-deps recovery-guard require-empty > /dev/null
task_temp=$(mktemp -d)
task_decrypt_pid= task_import_pid=
cleanup() {
  [ -z "$task_decrypt_pid" ] || kill "$task_decrypt_pid" 2>/dev/null || true
  [ -z "$task_import_pid" ] || kill "$task_import_pid" 2>/dev/null || true
  rm -f "$task_temp/stream"
  rmdir "$task_temp"
}
trap cleanup EXIT
trap 'exit 1' INT TERM
mkfifo -m 600 "$task_temp/stream"
compose run -T --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$task_key:/run/backup.key:ro" -v "$task_backup:/backup/input:ro" backup-crypto \
  decrypt --key-file /run/backup.key --file /backup/input > "$task_temp/stream" &
task_decrypt_pid=$!
compose exec -T mysql sh -c '
  export MYSQL_PWD="$(cat /run/secrets/mysql_root_password)"
  exec mysql -uroot --binary-mode=1
' < "$task_temp/stream" &
task_import_pid=$!
wait "$task_decrypt_pid"
task_decrypt_pid=
wait "$task_import_pid"
task_import_pid=
compose run -T --rm --no-deps recovery-guard apply
echo '隔离恢复完成，后台/出口保持关闭；未知绑定、支付、邮件与旧Outbox须先人工对账。'
