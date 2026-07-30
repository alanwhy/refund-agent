FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
RUN mkdir -p src/refund_agent && touch src/refund_agent/__init__.py
RUN pip install --no-cache-dir -e ".[dev]"

COPY src ./src
COPY prompts ./prompts
COPY tests ./tests

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "refund_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
