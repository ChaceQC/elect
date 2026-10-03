FROM ghcr.io/astral-sh/uv:0.8.22@sha256:9874eb7afe5ca16c363fe80b294fe700e460df29a55532bbfea234a0f12eddb1 AS uv
FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db AS base
ENV PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=UTC
WORKDIR /app

FROM base AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=elect-uv,target=/root/.cache/uv,sharing=locked uv sync --locked --no-dev

FROM dependencies AS test
RUN --mount=type=cache,id=elect-uv,target=/root/.cache/uv,sharing=locked uv sync --locked
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uv", "run", "pytest", "-q"]

FROM base AS runtime
RUN groupadd --gid 10001 elect && useradd --uid 10001 --gid elect --no-create-home elect
COPY --from=dependencies /app/.venv /app/.venv
COPY services ./services
COPY scripts/migrations.py ./scripts/migrations.py
ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
CMD ["python", "-m", "services.gateway"]
