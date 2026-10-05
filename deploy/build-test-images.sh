#!/bin/sh
# 本地Docker入口；CI由BuildKit作业构建同样四个目标。
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_version="v$(awk -F '"' '/^version = / {print $2; exit}' "$task_root/backend/pyproject.toml")"
task_revision=$(git -C "$task_root" rev-parse HEAD)
for task_part in backend frontend; do
  docker build --target runtime --build-arg "ELECT_BUILD_VERSION=$task_version" \
    --build-arg "ELECT_BUILD_REVISION=$task_revision" -t "elect-$task_part:test" "$task_root/$task_part"
done
docker build --target test -t elect-backend-smoke:test "$task_root/backend"
docker build --target browser-test -t elect-frontend-browser-check "$task_root/frontend"
