# Stage 1: install the dependencies into a virtualenv with uv
FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
# Only the lockfile first: this layer is reused until dependencies change
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Stage 2: the runtime image, without uv, build caches or compilers
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY app ./app
COPY scripts ./scripts
USER appuser

EXPOSE 8000

# slim has no curl, so the check uses Python's standard library
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" || exit 1

# granian: ASGI server written in Rust. Several workers are safe: the cache and the
# rate-limit counters live in Redis (GRANIAN_WORKERS overrides the count). The schema
# is not touched here: the `migrate` service runs dbmate before the app starts.
ENV GRANIAN_WORKERS=2
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000", "app.main:app"]
