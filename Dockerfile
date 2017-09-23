# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so source edits don't bust the layer cache.
COPY pyproject.toml README.md ./
COPY src/minutes_agent/__init__.py src/minutes_agent/__init__.py
ARG EXTRAS="anthropic,openai"
RUN pip install ".[${EXTRAS}]"

COPY src ./src
RUN pip install --no-deps .

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data
USER app

ENV MINUTES_JOB_STORE=sqlite \
    MINUTES_SQLITE_PATH=/app/data/jobs.sqlite3 \
    MINUTES_UPLOAD_DIR=/app/data/uploads

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status == 200 else 1)"
CMD ["uvicorn", "minutes_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
