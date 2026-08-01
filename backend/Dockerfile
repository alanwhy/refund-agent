ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
RUN mkdir -p src/refund_agent && touch src/refund_agent/__init__.py
RUN pip install --no-cache-dir -e ".[dev]"

COPY src ./src
COPY prompts ./prompts
COPY tests ./tests
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

RUN id -u appuser >/dev/null 2>&1 || useradd --create-home --uid 10001 appuser
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "refund_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
