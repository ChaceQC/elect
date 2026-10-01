#!/bin/sh
# 仅用于新的、明确命名的一次性环境；失败保留该项目便于查看脱敏日志。
set -eu
if [ "$#" -ne 2 ]; then
  echo '用法：sh deploy/test-stack.sh /absolute/new-test-directory elect-test-project' >&2
  exit 2
fi
task_dir=$1
task_project=$2
case "$task_dir" in /*) ;; *) echo '测试目录必须是绝对路径' >&2; exit 2 ;; esac
case "$task_project" in elect-test-*) ;; *) echo '项目名称须以 elect-test- 开头' >&2; exit 2 ;; esac
if [ -e "$task_dir" ]; then echo '测试目录已存在，拒绝覆盖' >&2; exit 2; fi
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -m 700 -p "$task_dir/secrets"
cd "$task_root"
docker build -t elect-backend:test backend
docker build -t elect-frontend:test frontend
docker run --rm --network none --user 0:0 -v "$task_dir/secrets:/run/provision" \
  elect-backend:test python -m services.deployment.provision \
  --output-dir /run/provision --test-tls-domain elect.test.local
# 全部为公开字段；sed 不读取/展开 Secret。
sed -e 's/elect.example.edu/elect.test.local/' \
  -e "s|/opt/elect/secrets|$task_dir/secrets|g" \
  -e 's/elect-backend:v[0-9.]*/elect-backend:test/' \
  -e 's/elect-frontend:v[0-9.]*/elect-frontend:test/' deploy/.env.example > "$task_dir/stack.env"
compose() {
  docker compose --env-file "$task_dir/stack.env" -f deploy/compose.yaml \
    -f deploy/compose.test.yaml -p "$task_project" "$@"
}
compose config --quiet
compose up -d --no-build --wait --wait-timeout 180
compose run --rm --no-deps smoke
compose run --rm --no-deps smoke python -m scripts.t2_smoke
compose exec -T nginx nginx -t
compose run --rm --no-deps tls-check
compose ps -a
echo '一次性容器验收通过；使用同一 env/项目执行 down，保留命名卷供恢复检查。'
