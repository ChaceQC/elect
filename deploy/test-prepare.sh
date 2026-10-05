#!/bin/sh
# 仅准备独立空库，不执行业务用例；CI使用本次已校验的镜像。
set -eu
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo '用法：sh deploy/test-prepare.sh /absolute/new-test-directory elect-test-project [standalone|combined]' >&2
  exit 2
fi
task_dir=$1
task_project=$2
task_mode=${3:-standalone}
case "$task_mode" in standalone|combined) ;; *) exit 2;; esac
case "$task_dir" in /*) ;; *) echo '测试目录必须是绝对路径' >&2; exit 2 ;; esac
case "$task_project" in elect-test-*) ;; *) echo '项目名称须以 elect-test- 开头' >&2; exit 2 ;; esac
if [ -e "$task_dir" ]; then echo '测试目录已存在，拒绝覆盖' >&2; exit 2; fi
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sh "$task_root/deploy/test-state.sh" "$task_dir" "$task_project" absent
mkdir -m 700 -p "$task_dir/secrets"
printf '%s\n' "$task_project" > "$task_dir/test-project"
cd "$task_root"
if [ "${ELECT_SKIP_BUILD:-0}" != 1 ]; then
  sh deploy/build-test-images.sh
fi
task_version="v$(awk -F '"' '/^version = / {print $2; exit}' backend/pyproject.toml)"
task_revision=$(git rev-parse HEAD)
docker image inspect elect-backend:test elect-frontend:test |
  docker run --rm --network none -i elect-backend:test python -m services.deployment.release \
  check-images --version "$task_version" --revision "$task_revision"
docker image inspect "${ELECT_TEST_IMAGE:-elect-backend-smoke:test}" >/dev/null
docker run --rm --network none --user 0:0 -v "$task_dir/secrets:/run/provision" \
  elect-backend:test python -m services.deployment.provision \
  --output-dir /run/provision --test-tls-domain elect.test.local
# 全部为公开字段；sed 不读取/展开 Secret。
sed -e 's/elect.example.edu/elect.test.local/' \
  -e "s|/opt/elect/secrets|$task_dir/secrets|g" \
  -e 's/elect-backend:v[0-9.]*/elect-backend:test/' \
  -e 's/elect-frontend:v[0-9.]*/elect-frontend:test/' \
  -e "s/^ELECT_DEPLOYMENT_MODE=.*/ELECT_DEPLOYMENT_MODE=$task_mode/" \
  deploy/.env.example > "$task_dir/stack.env"
compose() {
  sh deploy/compose.sh "$task_dir/stack.env" "$task_project" --test "$@"
}
compose config --quiet
if [ "${ELECT_TEST_GROUP_START:-0}" = 1 ] && [ "$task_mode" = combined ]; then
  # 测试准备可分组启动；部署演练仍调用未经修改的start/upgrade入口。
  compose up -d --no-build --no-deps --wait --wait-timeout 180 mysql redis rabbitmq
  compose run -T --rm --no-deps migrate
  compose run -T --rm --no-deps tls-check
  compose up -d --no-build --no-deps --wait --wait-timeout 180 school-adapter monitoring identity room notification payment audit gateway
  compose up -d --no-build --no-deps --wait --wait-timeout 180 notification-worker nginx
else
  sh deploy/start.sh "$task_dir/stack.env" "$task_project" --test
fi
if [ "$task_mode" = combined ]; then
  sh deploy/test-state.sh "$task_dir" "$task_project" combined
fi
