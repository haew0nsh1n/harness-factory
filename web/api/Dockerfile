FROM python:3.12-slim

ARG PIP_INDEX_URL

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY catalog ./catalog
COPY examples ./examples
COPY harness_factory ./harness_factory
COPY web ./web

RUN python -m pip install --disable-pip-version-check setuptools wheel \
    && if [ -n "$PIP_INDEX_URL" ]; then \
         PIP_INDEX_URL="$PIP_INDEX_URL" python -m pip install --disable-pip-version-check .; \
       else \
         python -m pip install --disable-pip-version-check .; \
       fi

EXPOSE 8000

CMD ["uvicorn", "web.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
