#!/bin/sh
# 使用已通过test-stack的明确一次性项目；不触及其他项目/卷。
set -eu
if [ "$#" -ne 2 ]; then echo '用法：sh deploy/test-t7-recovery.sh /absolute/test-dir elect-test-project' >&2; exit 2; fi
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_recovery="$task_dir/recovery"
task_restore_project="elect-restore-$task_project"
[ ! -e "$task_recovery" ] || { echo '恢复演练目录已存在，拒绝覆盖' >&2; exit 2; }
mkdir -m 700 "$task_recovery" "$task_recovery/secrets"
cd "$task_root"
docker build -t elect-backend:ops backend
docker build --target test -t elect-backend-smoke:ops backend
export ELECT_IMAGE=elect-backend:ops ELECT_TEST_IMAGE=elect-backend-smoke:ops
source_compose() {
  docker compose --env-file "$task_dir/stack.env" -f deploy/compose.yaml \
    -f deploy/compose.test.yaml -f deploy/compose.ops.yaml -p "$task_project" "$@"
}
target_compose() {
  docker compose --env-file "$task_recovery/restore.env" -f deploy/compose.yaml \
    -f deploy/compose.test.yaml -f deploy/compose.ops.yaml -f deploy/compose.restore.yaml \
    -p "$task_restore_project" "$@"
}
probe() {
  task_target=$1 task_mode=$2
  "$task_target" run -T --rm --no-deps --user 0:0 --cap-add DAC_OVERRIDE --cap-add CHOWN \
    -e "ELECT_RESULT_UID=$(id -u)" -e "ELECT_RESULT_GID=$(id -g)" \
    -v "$task_recovery:/run/recovery" smoke \
    python -m scripts.t7_recovery_probe "$task_mode" --state-file /run/recovery/state.json
}
# 冻结本测试项目写进程，再由同进程模拟学校和SMTP；没有真实出口。
source_compose stop
source_compose up -d --no-build --wait --wait-timeout 90 mysql redis rabbitmq
probe source_compose seed
source_compose run -T --rm --no-deps recovery-guard inventory > "$task_recovery/before.json"
source_compose run -T --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$task_recovery:/backup" backup-crypto keygen --key-file /backup/backup.key
sh deploy/backup.sh "$task_dir/stack.env" "$task_project" "$task_recovery/backup.key" "$task_recovery/snapshot.electbackup"
source_compose run -T --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$task_recovery:/backup:ro" backup-crypto verify --key-file /backup/backup.key \
  --file /backup/snapshot.electbackup > "$task_recovery/metadata.json"
probe source_compose after-backup
sh deploy/backup.sh "$task_dir/stack.env" "$task_project" "$task_recovery/backup.key" \
  "$task_recovery/logs.binlogbackup" mysql_binlogs
source_compose run -T --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$task_recovery:/backup:ro" backup-crypto verify --key-file /backup/backup.key \
  --file /backup/logs.binlogbackup --kind mysql_binlogs > /dev/null
# Secret独立传递，仅用于本次合成隔离；加密快照自身不包含密钥。
docker run --rm --network none --user 0:0 -v "$task_dir/secrets:/source:ro" \
  -v "$task_recovery/secrets:/target" elect-backend:ops sh -c 'cp -a /source/. /target/'
sed "s|$task_dir/secrets|$task_recovery/secrets|g" "$task_dir/stack.env" > "$task_recovery/restore.env"
task_started=$(date +%s)
sh deploy/restore.sh "$task_recovery/restore.env" "$task_restore_project" \
  "$task_recovery/backup.key" "$task_recovery/snapshot.electbackup"
target_compose run -T --rm --no-deps recovery-guard inventory > "$task_recovery/after.json"
probe target_compose restored
# 可重入；不重新释放未知占位或启动任何外部请求。
target_compose run -T --rm --no-deps recovery-guard apply > /dev/null
probe target_compose restored
task_elapsed=$(($(date +%s) - task_started))
source_compose run -T --rm --no-deps --user 0:0 --cap-add DAC_OVERRIDE \
  -v "$task_recovery:/run/recovery:ro" smoke python -m scripts.t7_recovery_report \
  --directory /run/recovery --rto-seconds "$task_elapsed" > "$task_recovery/result.json"
cat "$task_recovery/result.json"
echo 'T7加密快照/封存binlog、隔离恢复和副作用窗口验证通过；来源与目标均保留基础服务及卷。'
