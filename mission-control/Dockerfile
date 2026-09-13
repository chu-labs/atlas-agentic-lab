# Stage 1: build the SPA
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

# Stage 2: the API image, which also serves web/dist.
# One worker on purpose: derived state and the WebSocket fan-out live in process memory.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY mission ./mission
COPY migrations ./migrations
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "mission.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
