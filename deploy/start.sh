#!/bin/sh
# 目标机只拉取固定摘要；全部预检通过后停止旧应用，按依赖串行启动。
set -eu
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo '用法：sh deploy/start.sh /absolute/stack.env 项目名 [--test]' >&2; exit 2
fi
task_env=$1 task_project=$2 task_test=${3:-}
case "$task_env" in /*) ;; *) exit 2;; esac
case "$task_test" in ''|--test) ;; *) exit 2;; esac
if [ "$task_test" = --test ]; then
  case "$task_project" in elect-test-*) ;; *) exit 2;; esac
fi
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$task_root/deploy/settings.sh"
task_mode=${ELECT_IMAGE_MODE:-$(setting ELECT_IMAGE_MODE local)}
if [ "$task_mode" != published ] && [ "$task_test" != --test ]; then
  echo '部署入口要求ELECT_IMAGE_MODE=published及固定摘要；本地构建使用compose.sh' >&2; exit 2
fi
compose() {
  sh "$task_root/deploy/compose.sh" \
    "$task_env" "$task_project" ${task_test:+--test} --parallel 1 "$@"
}
compose config --quiet
task_backend=${ELECT_IMAGE:-$(setting ELECT_IMAGE '')}
if [ "$task_mode" = published ] && [ "$task_test" != --test ]; then
  # 校验所有角色/基础镜像；拉取失败发生在停止业务之前。
  task_images=$(compose config --images | sort -u)
  for task_image in $task_images; do
    case "$task_image" in *@sha256:*) ;; *) echo '所有发布镜像必须固定sha256摘要' >&2; exit 2;; esac
    task_digest=${task_image##*@sha256:}
    case "$task_digest" in *[!0-9a-f]*) exit 2;; esac
    [ "${#task_digest}" -eq 64 ] || exit 2
    docker pull "$task_image"
  done
fi
task_services=$(compose config --format json | docker run --rm --network none -i "$task_backend" \
  python -m services.deployment.release check-config ${task_test:+--allow-local})
if [ "$task_mode" = published ] && [ "$task_test" != --test ]; then
  task_web=${ELECT_WEB_IMAGE:-$(setting ELECT_WEB_IMAGE '')}
  task_version=${ELECT_RELEASE_VERSION:-$(setting ELECT_RELEASE_VERSION '')}
  task_revision=${ELECT_RELEASE_REVISION:-$(setting ELECT_RELEASE_REVISION '')}
  docker image inspect "$task_backend" "$task_web" | docker run --rm --network none -i "$task_backend" \
    python -m services.deployment.release check-images --version "$task_version" --revision "$task_revision"
fi
if echo "$task_services" | grep -qx tls-check; then compose run -T --rm --no-deps tls-check; fi
compose run -T --rm --no-deps nginx nginx -t
# profile变化/可选通道关闭也要停止本项目旧角色，按各容器原退出宽限处理。
task_old=$(docker ps --filter "label=com.docker.compose.project=$task_project" \
  --format '{{.ID}} {{.Label "com.docker.compose.service"}}' | \
  awk '$2 != "mysql" && $2 != "redis" && $2 != "rabbitmq" {print $1}')
if [ -n "$task_old" ]; then docker stop $task_old > /dev/null; fi
echo '启动基础服务'
for task_service in mysql redis rabbitmq; do
  compose up -d --no-build --no-deps --wait --wait-timeout 180 "$task_service"
done
echo '执行数据库迁移'
compose run -T --rm --no-deps migrate
start_service() {
  if echo "$task_services" | grep -qx "$1"; then
    compose up -d --no-build --no-deps --wait --wait-timeout 180 "$1"
  fi
}
echo '依次启动领域服务'
for task_service in school-adapter monitoring identity room notification payment audit gateway; do
  start_service "$task_service"
done
echo '依次启动后台角色'
for task_service in smtp-direct identity-relay school-relay room-relay monitoring-relay \
  notification-relay payment-relay audit-worker identity-recovery room-sync-worker \
  school-maintenance monitor-scheduler monitor-worker monitor-recovery monitor-alerts \
  notification-worker notification-recovery payment-worker payment-recovery; do
  start_service "$task_service"
done
start_service nginx
compose ps -a
