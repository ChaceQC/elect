#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_image=${ELECT_QUERY_TEST_IMAGE:-elect-backend-check}
if [ "${ELECT_SKIP_BUILD:-0}" != 1 ]; then
  docker build --target test -t "$task_image" "$task_root/backend"
fi
docker run --rm --network none -v "$task_root/docs:/docs:ro" \
  -v "$task_root/deploy:/deploy:ro" \
  -v "$task_root/frontend/src/mocks/scenarios.json:/frontend/src/mocks/scenarios.json:ro" \
  "$task_image" sh -c '
  uv run ruff check . && uv run pytest -q &&
  uv run python -m scripts.generate_openapi --check &&
  uv run python -m scripts.generate_protocols --check &&
  uv run python -m scripts.schema_catalog --check &&
  uv run python -m scripts.migration_manifest --check &&
  uv run python -m scripts.migrations --domain all --sql --output-dir /tmp/elect-ddl
'
