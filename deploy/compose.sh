#!/bin/sh
# 统一配置顺序；只解析公开选择字段，不source配置或展开其中的代码。
set -eu
if [ "$#" -lt 3 ]; then
  echo '用法：sh deploy/compose.sh /absolute/stack.env 项目名 [--test] [--browser] [--restore] compose参数' >&2
  exit 2
fi
task_env=$1 task_project=$2
shift 2
case "$task_env" in /*) ;; *) echo '配置路径必须绝对' >&2; exit 2;; esac
[ -f "$task_env" ] || { echo '配置文件不存在' >&2; exit 2; }
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_test=false task_restore=false task_browser=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --test) task_test=true;;
    --restore) task_restore=true;;
    --browser) task_browser=true;;
    *) break;;
  esac
  shift
done
[ "$#" -gt 0 ] || exit 2
if [ "$task_browser" = true ] && [ "$task_test" = false ]; then exit 2; fi
if [ "$task_test" = true ]; then
  case "$task_project" in elect-test-*|elect-restore-elect-test-*) ;; *) exit 2;; esac
fi
if [ "$task_restore" = true ]; then
  case "$task_project" in elect-restore-*|elect-test-*) ;; *) exit 2;; esac
fi
. "$task_root/deploy/settings.sh"
task_mode=${ELECT_DEPLOYMENT_MODE:-$(setting ELECT_DEPLOYMENT_MODE standalone)}
task_image_mode=${ELECT_IMAGE_MODE:-$(setting ELECT_IMAGE_MODE local)}
task_local=${ELECT_ALLOW_LOCAL_HTTP:-$(setting ELECT_ALLOW_LOCAL_HTTP false)}
task_smtp=${ELECT_SMTP_DIRECT_ENABLED:-$(setting ELECT_SMTP_DIRECT_ENABLED false)}
task_test_network=${ELECT_TEST_NETWORK_PREFIX:-}
if [ -n "$task_test_network" ]; then
  [ "$task_test" = true ] || exit 2
  case "$task_test_network" in 10.[0-9]|10.[0-9][0-9]|10.[12][0-9][0-9]) ;; *) exit 2;; esac
  [ "${task_test_network#10.}" -le 255 ] || exit 2
fi
case "$task_mode" in standalone|combined|core) ;; *) echo '部署模式只允许standalone/combined/core' >&2; exit 2;; esac
case "$task_image_mode" in local|published) ;; *) echo '镜像模式只允许local/published' >&2; exit 2;; esac
case "$task_local:$task_smtp" in true:true|true:false|false:true|false:false) ;; *)
  echo '部署选择开关只允许true/false' >&2; exit 2;; esac
# 从后向前添加，恢复覆盖始终最后；恢复完全不加载host网络SMTP通道。
set -- -p "$task_project" "$@"
if [ "$task_restore" = true ] && [ "$task_mode" = core ]; then
  set -- -f "$task_root/deploy/compose.core-restore.yaml" "$@"
fi
if [ "$task_restore" = true ]; then set -- -f "$task_root/deploy/compose.restore.yaml" "$@"; fi
set -- -f "$task_root/deploy/compose.ops.yaml" "$@"
if [ "$task_mode" = core ] && [ "$task_image_mode" = local ]; then
  set -- -f "$task_root/deploy/compose.core-build.yaml" "$@"
fi
if [ "$task_mode" = core ]; then set -- -f "$task_root/deploy/compose.core.yaml" "$@"; fi
if [ "$task_mode" != standalone ]; then set -- -f "$task_root/deploy/compose.low-resource.yaml" "$@"; fi
if [ "$task_browser" = true ]; then set -- -f "$task_root/deploy/compose.t7.yaml" "$@"; fi
if [ "$task_test" = true ]; then set -- -f "$task_root/deploy/compose.test.yaml" "$@"; fi
if [ -n "$task_test_network" ]; then set -- -f "$task_root/deploy/compose.test-network.yaml" "$@"; fi
if [ "$task_smtp" = true ] && [ "$task_restore" = false ]; then
  set -- -f "$task_root/deploy/compose.smtp-direct.yaml" "$@"
fi
if [ "$task_local" = true ]; then set -- -f "$task_root/deploy/compose.local.yaml" "$@"; fi
if [ "$task_image_mode" = local ]; then set -- -f "$task_root/deploy/compose.build.yaml" "$@"; fi
exec docker compose --env-file "$task_env" -f "$task_root/deploy/compose.yaml" "$@"
