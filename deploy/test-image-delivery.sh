#!/bin/sh
# 同一隔离项目/原卷，用仅含deploy的发布包验证无源码启动，不访问registry。
set -eu
[ "$#" -eq 2 ] || exit 2
task_dir=$1 task_project=$2
case "$task_dir" in /*) ;; *) exit 2;; esac
case "$task_project" in elect-test-*) ;; *) exit 2;; esac
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_bundle="$task_dir/deploy-only"
[ ! -e "$task_bundle" ] || exit 2
mkdir -m 700 "$task_bundle"
git -C "$task_root" archive HEAD deploy | tar -x -C "$task_bundle"
[ ! -e "$task_bundle/backend" ] && [ ! -e "$task_bundle/frontend" ]
compose() {
  ELECT_IMAGE_MODE=published sh "$task_bundle/deploy/compose.sh" \
    "$task_dir/stack.env" "$task_project" --test "$@"
}
compose config --format json | docker run --rm --network none -i elect-backend:test \
  python -c 'import json,sys; assert all(not v.get("build") for v in json.load(sys.stdin)["services"].values())'
ELECT_IMAGE_MODE=published sh "$task_bundle/deploy/upgrade.sh" "$task_dir/stack.env" "$task_project" --test
task_count=$(compose ps --status running --services | wc -l | tr -d ' ')
[ "$task_count" -eq 13 ]
compose run -T --rm --no-deps smoke python -m scripts.combined_status ready
echo '仅deploy发布包、原卷13容器与串行无构建启动通过；registry摘要另由标签CI验证。'
