FROM python:3.11.7-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_LINK_MODE=copy

WORKDIR /app

COPY uv.lock pyproject.toml README.md ./
COPY api ./api

RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --frozen --no-dev

# Creating minimal image
FROM python:3.11.7-slim

COPY --from=builder /app /app

ENV TZ=America/Fortaleza
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "api.main:main", "--host", "0.0.0.0", "--port", "8000", "--factory"]

