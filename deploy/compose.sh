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
setting() {
  awk -v key="$1" -v fallback="$2" '
    $0 ~ "^[ \t]*(export[ \t]+)?" key "[ \t]*=" {
      count++; sub(/^[^=]*=[ \t]*/, ""); sub(/[ \t]+#.*/, ""); sub(/[ \t\r]+$/, "")
      if ($0 ~ /^"[^"]*"$/ || $0 ~ /^\047[^\047]*\047$/) $0=substr($0,2,length($0)-2)
      value=$0
    }
    END { if (count>1) exit 2; print count ? value : fallback }
  ' "$task_env"
}
task_mode=${ELECT_DEPLOYMENT_MODE:-$(setting ELECT_DEPLOYMENT_MODE standalone)}
task_local=${ELECT_ALLOW_LOCAL_HTTP:-$(setting ELECT_ALLOW_LOCAL_HTTP false)}
task_smtp=${ELECT_SMTP_DIRECT_ENABLED:-$(setting ELECT_SMTP_DIRECT_ENABLED false)}
case "$task_mode" in standalone|combined) ;; *) echo '部署模式只允许standalone/combined' >&2; exit 2;; esac
case "$task_local:$task_smtp" in true:true|true:false|false:true|false:false) ;; *)
  echo '部署选择开关只允许true/false' >&2; exit 2;; esac
# 从后向前添加，恢复覆盖始终最后；恢复完全不加载host网络SMTP通道。
set -- -p "$task_project" "$@"
if [ "$task_restore" = true ]; then set -- -f "$task_root/deploy/compose.restore.yaml" "$@"; fi
set -- -f "$task_root/deploy/compose.ops.yaml" "$@"
if [ "$task_mode" = combined ]; then set -- -f "$task_root/deploy/compose.low-resource.yaml" "$@"; fi
if [ "$task_browser" = true ]; then set -- -f "$task_root/deploy/compose.t7.yaml" "$@"; fi
if [ "$task_test" = true ]; then set -- -f "$task_root/deploy/compose.test.yaml" "$@"; fi
if [ "$task_smtp" = true ] && [ "$task_restore" = false ]; then
  set -- -f "$task_root/deploy/compose.smtp-direct.yaml" "$@"
fi
if [ "$task_local" = true ]; then set -- -f "$task_root/deploy/compose.local.yaml" "$@"; fi
exec docker compose --env-file "$task_env" -f "$task_root/deploy/compose.yaml" "$@"
