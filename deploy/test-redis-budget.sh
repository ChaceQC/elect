#!/bin/sh
# 96MiB、32MiB/noeviction/AOF真实Redis；独立无网络实例，仅合成键。
set -eu
if [ "$#" -ne 3 ]; then echo '用法：test-redis-budget.sh /absolute/test-dir elect-test-name redis-image' >&2; exit 2; fi
task_dir=$1 task_project=$2 task_image=$3
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_name=$task_project-redis-budget
task_data=$task_dir/redis-budget
[ ! -e "$task_data" ] || { echo 'Redis预算目录已存在，拒绝覆盖' >&2; exit 2; }
if docker inspect "$task_name" >/dev/null 2>&1; then exit 2; fi
mkdir -m 700 "$task_data"
# 仅此无网络测试实例使用公开无密码账号，正式ACL从不修改。
printf '%s\n' 'user default on nopass ~* +@all' > "$task_data/test.acl"
cleanup() { docker rm -f "$task_name" >/dev/null 2>&1 || true; }
trap cleanup EXIT HUP INT TERM
docker run -d --name "$task_name" --network none --memory 96m --cpus 0.5 --pids-limit 128 \
  -v "$task_root/deploy/redis.conf:/etc/redis/redis.conf:ro" \
  -v "$task_data/test.acl:/run/secrets/redis_acl:ro" \
  -v "$task_data/data:/data" "$task_image" \
  redis-server /etc/redis/redis.conf --maxmemory 32mb >/dev/null
redis() { docker exec -i "$task_name" redis-cli --raw "$@"; }
task_attempt=0
until [ "$(redis PING 2>/dev/null || true)" = PONG ]; do
  task_attempt=$((task_attempt + 1)); [ "$task_attempt" -lt 30 ] || exit 1; sleep 1
done
[ "$(redis CONFIG GET maxmemory | tail -n 1)" = 33554432 ]
[ "$(redis CONFIG GET maxmemory-policy | tail -n 1)" = noeviction ]
[ "$(redis CONFIG GET appendonly | tail -n 1)" = yes ]
redis SET synthetic:session preserved >/dev/null
redis SET synthetic:account-lock preserved >/dev/null
redis SET synthetic:global-slot preserved >/dev/null
generate() {
  awk -v count="$1" 'BEGIN {
    for (j=0;j<32768;j++) value=value "x"
    for (i=1;i<=count;i++) {
      key="synthetic:pressure:" i
      printf "*3\r\n$3\r\nSET\r\n$%d\r\n%s\r\n$%d\r\n%s\r\n",length(key),key,length(value),value
    }
  }'
}
# 填满数据预算，检查拒绝写入而非淘汰；日志只有合成键/错误计数。
generate 1400 | redis --pipe > "$task_data/fill.log" 2>&1 || true
grep -q OOM "$task_data/fill.log"
redis BGREWRITEAOF > "$task_data/rewrite.txt"
grep -qx 'Background append only file rewriting started' "$task_data/rewrite.txt"
# 覆盖重写与更新并发的COW窗口。
generate 400 | redis --pipe > "$task_data/rewrite-writes.log" 2>&1 || true
task_attempt=0
while redis INFO persistence | tr -d '\r' | grep -qx 'aof_rewrite_in_progress:1'; do
  task_attempt=$((task_attempt + 1)); [ "$task_attempt" -lt 30 ] || exit 1; sleep 1
done
redis INFO persistence | tr -d '\r' | grep -qx 'aof_last_bgrewrite_status:ok'
redis INFO memory | tr -d '\r' | grep -E '^(used_memory:|used_memory_peak:|used_memory_rss:)' > "$task_data/memory.txt"
redis INFO stats | tr -d '\r' | grep -qx 'evicted_keys:0'
for task_key in session account-lock global-slot; do
  [ "$(redis GET "synthetic:$task_key")" = preserved ]
done
docker exec "$task_name" cat /sys/fs/cgroup/memory.peak > "$task_data/cgroup-peak-bytes.txt"
docker exec "$task_name" cat /sys/fs/cgroup/memory.events > "$task_data/cgroup-events.txt"
grep -qx 'oom_kill 0' "$task_data/cgroup-events.txt"
docker restart "$task_name" >/dev/null
task_attempt=0
until [ "$(redis PING 2>/dev/null || true)" = PONG ]; do
  task_attempt=$((task_attempt + 1)); [ "$task_attempt" -lt 30 ] || exit 1; sleep 1
done
for task_key in session account-lock global-slot; do
  [ "$(redis GET "synthetic:$task_key")" = preserved ]
done
echo 'Redis 32MiB/noeviction、AOF重写并发、零OOM与重启保留合成会话/锁/槽：通过'
