#!/bin/sh
# CI最后一步发布已经通过本次集成的实际runtime镜像；不重新构建。
set -eu
[ "$#" -eq 3 ] || exit 2
task_tag=$1 task_registry=$2 task_output=$3
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
case "$task_registry" in ghcr.io/*) ;; *) exit 2;; esac
case "$task_output" in /*) ;; *) exit 2;; esac
task_revision=$(git -C "$task_root" rev-parse HEAD)
docker run --rm --network none -v "$task_root:/source:ro" elect-backend:test \
  python -m services.deployment.release check-version --source-root /source --tag "$task_tag"
docker image inspect elect-backend:test elect-frontend:test | \
  docker run --rm --network none -i elect-backend:test python -m services.deployment.release \
  check-images --version "$task_tag" --revision "$task_revision"
task_error=$(mktemp)
trap 'rm -f "$task_error"' EXIT HUP INT TERM
for task_part in backend frontend; do
  task_image="$task_registry-$task_part:$task_tag"
  if docker manifest inspect "$task_image" > /dev/null 2> "$task_error"; then
    docker pull "$task_image"
    task_remote=$(docker image inspect --format '{{.Id}}' "$task_image")
    task_local=$(docker image inspect --format '{{.Id}}' "elect-$task_part:test")
    if [ "$task_remote" != "$task_local" ]; then
      echo '此版本已有其他镜像，拒绝覆盖；使用新版本标签' >&2; exit 2
    fi
  elif ! grep -Eq 'manifest unknown|no such manifest|not found' "$task_error"; then
    echo '无法确认版本是否已存在，停止发布' >&2; exit 2
  fi
done
mkdir -p "$task_output"
for task_part in backend frontend; do
  task_image="$task_registry-$task_part:$task_tag"
  docker tag "elect-$task_part:test" "$task_image"
  docker push "$task_image"
  docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$task_image" | \
    awk -v prefix="$task_registry-$task_part@sha256:" 'index($0,prefix)==1 {print}' > "$task_output/$task_part.digest"
  [ "$(wc -l < "$task_output/$task_part.digest")" -eq 1 ] || exit 2
done
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$task_root:/source:ro" -v "$task_output:/output" elect-backend:test \
  python -m services.deployment.release manifest --source-root /source --output /output \
  --tag "$task_tag" --revision "$task_revision" \
  --backend "$(cat "$task_output/backend.digest")" --frontend "$(cat "$task_output/frontend.digest")" \
  --run-url "https://github.com/${GITHUB_REPOSITORY:?}/actions/runs/${GITHUB_RUN_ID:?}"
# 只打包受版本管理的部署文件，真实.env/Secret不可能进入发布包。
git -C "$task_root" archive --format=tar HEAD deploy docs/runbooks/固定镜像发布与启动.md | \
  gzip > "$task_output/deploy-$task_tag.tar.gz"
