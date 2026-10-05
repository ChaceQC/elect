#!/bin/sh
# 仅依赖 Docker，测试镜像可读取 docs；生产镜像不跨构建上下文。
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
docker build --target test -t elect-backend-check "$task_root/backend"
docker run --rm --network none -v "$task_root/docs:/docs:ro" \
  -v "$task_root/deploy:/deploy:ro" \
  -v "$task_root/frontend/src/mocks/scenarios.json:/frontend/src/mocks/scenarios.json:ro" \
  elect-backend-check sh -c '
  uv run ruff check . && uv run pytest -q &&
  uv run python -m scripts.generate_openapi --check &&
  uv run python -m scripts.generate_protocols --check &&
  uv run python -m scripts.schema_catalog --check &&
  uv run python -m scripts.migration_manifest --check &&
  uv run python -m scripts.migrations --domain all --sql --output-dir /tmp/elect-ddl
'
docker build --target test -t elect-frontend-check "$task_root/frontend"
docker run --rm --network none -v "$task_root/docs:/docs:ro" elect-frontend-check sh -c '
  npm run contract:check && npm run lint && npm run typecheck && npm test && npm run build
'
docker build --target browser-test -t elect-frontend-browser-check "$task_root/frontend"
docker run --rm --network none elect-frontend-browser-check
