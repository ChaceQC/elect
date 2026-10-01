#!/bin/sh
# 一次全库一致快照流式加密；明文仅通过FIFO，不落宿主机。
set -eu
if [ "$#" -lt 4 ] || [ "$#" -gt 5 ]; then
  echo '用法：sh deploy/backup.sh /absolute/stack.env 项目名 /absolute/backup.key /absolute/snapshot.electbackup [mysql_logical|mysql_binlogs]' >&2
  exit 2
fi
task_env=$1 task_project=$2 task_key=$3 task_output=$4
task_kind=${5:-mysql_logical}
case "$task_kind" in mysql_logical|mysql_binlogs) ;; *) exit 2;; esac
for task_path in "$task_env" "$task_key" "$task_output"; do
  case "$task_path" in /*) ;; *) echo '路径必须绝对' >&2; exit 2;; esac
done
if [ -e "$task_output" ]; then echo '备份输出已存在，拒绝覆盖' >&2; exit 2; fi
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_parent=$(dirname -- "$task_output")
task_name=$(basename -- "$task_output")
task_temp=$(mktemp -d "$task_parent/.elect-backup.XXXXXX")
task_dump_pid= task_crypto_pid=
cleanup() {
  [ -z "$task_dump_pid" ] || kill "$task_dump_pid" 2>/dev/null || true
  [ -z "$task_crypto_pid" ] || kill "$task_crypto_pid" 2>/dev/null || true
  rm -f "$task_temp/stream" "$task_temp/pending"
  rmdir "$task_temp"
}
trap cleanup EXIT
trap 'exit 1' INT TERM
compose() {
  docker compose --env-file "$task_env" -f "$task_root/deploy/compose.yaml" \
    -f "$task_root/deploy/compose.ops.yaml" -p "$task_project" "$@"
}
mkfifo -m 600 "$task_temp/stream"
compose run -T --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$task_key:/run/backup.key:ro" -v "$task_temp:/backup" backup-crypto \
  encrypt --key-file /run/backup.key --file /backup/pending --kind "$task_kind" < "$task_temp/stream" &
task_crypto_pid=$!
produce() {
if [ "$task_kind" = mysql_logical ]; then
  compose exec -T mysql sh -c '
  export MYSQL_PWD="$(cat /run/secrets/mysql_root_password)"
  exec mysqldump -uroot --single-transaction --source-data=2 --set-gtid-purged=OFF \
    --hex-blob --no-tablespaces --routines --events --triggers --databases \
    elect_identity elect_school elect_room elect_monitoring elect_notification elect_payment elect_audit
'
else
  compose exec -T mysql sh -c '
    export MYSQL_PWD="$(cat /run/secrets/mysql_root_password)"
    mysql -uroot -e "FLUSH BINARY LOGS"
    files=$(mysql -uroot -Nse "SHOW BINARY LOGS" | sed "$ d" | cut -f 1)
    [ -n "$files" ] || exit 1
    for file in $files; do
      case "$file" in elect-bin.*) ;; *) exit 1;; esac
      number=${file#elect-bin.}
      case "$number" in ""|*[!0-9]*) exit 1;; esac
    done
    cd /var/lib/mysql
    tar -cf - $files
  '
fi
}
produce > "$task_temp/stream" &
task_dump_pid=$!
wait "$task_dump_pid"
task_dump_pid=
wait "$task_crypto_pid"
task_crypto_pid=
# 同一文件系统的原子排他发布，不覆盖并发产生的同名备份。
ln "$task_temp/pending" "$task_parent/$task_name"
echo '备份已加密；密钥须通过独立渠道保存，备份须复制到独立存储。'
