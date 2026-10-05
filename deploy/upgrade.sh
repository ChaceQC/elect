#!/bin/sh
# 与首次启动共用摘要校验/拉取、旧角色停止和分阶段启动，不删除卷。
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec sh "$task_root/deploy/start.sh" "$@"
