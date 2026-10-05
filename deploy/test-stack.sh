#!/bin/sh
# 保留本地一次性构建、准备和完整业务验证入口。
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sh "$task_root/deploy/test-prepare.sh" "$@"
sh "$task_root/deploy/test-business.sh" "$@"
