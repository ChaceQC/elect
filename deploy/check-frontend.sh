#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_image=${ELECT_BROWSER_IMAGE:-elect-frontend-browser-check}
if [ "${ELECT_SKIP_BUILD:-0}" != 1 ]; then
  docker build --target browser-test -t "$task_image" "$task_root/frontend"
fi
docker run --rm --network none -v "$task_root/docs:/docs:ro" "$task_image" sh -c '
  npm run contract:check && npm run lint && npm run typecheck && npm test && npm run build
'
docker run --rm --network none "$task_image"
