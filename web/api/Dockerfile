FROM python:3.12-slim

ARG PIP_INDEX_URL
ARG UV_LOCK_FILE=uv.lock

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir uv==0.8.3

COPY pyproject.toml README.md alembic.ini ./
COPY ${UV_LOCK_FILE} ./uv.lock
COPY alembic ./alembic
COPY catalog ./catalog
COPY examples ./examples
COPY harness_factory ./harness_factory
COPY web ./web

RUN python -m venv .venv \
    && .venv/bin/python -m pip install --no-cache-dir setuptools==80.9.0 \
    && uv sync --frozen --no-dev --no-config --no-build-isolation

EXPOSE 8000

CMD ["uvicorn", "web.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
