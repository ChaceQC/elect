#!/bin/sh
# 保留仅Docker的本地完整离线检查入口。
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sh "$task_root/deploy/check-backend.sh"
sh "$task_root/deploy/check-frontend.sh"
