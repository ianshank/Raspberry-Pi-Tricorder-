# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — builder: compile wheels for all runtime dependencies
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

ARG TARGETPLATFORM

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml ./
COPY setup.py ./
COPY src/ ./src/

# Build base wheels; on arm64 also include the [hardware] extra
RUN pip wheel --no-cache-dir --wheel-dir /wheels . && \
    if [ "${TARGETPLATFORM}" = "linux/arm64" ]; then \
        pip wheel --no-cache-dir --wheel-dir /wheels ".[hardware]" || true; \
    fi

# ---------------------------------------------------------------------------
# Stage 2 — runtime: slim image with only what the server needs
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --find-links=/wheels \
        tricorder-neural && \
    rm -rf /wheels

COPY config/ ./config/
COPY src/ui/static/ ./src/ui/static/

RUN mkdir -p /app/data /app/logs

# --- Default environment --------------------------------------------------
# Override via docker-compose env_file or -e flags.
ENV TRICORDER__ENVIRONMENT=production
ENV TRICORDER__MCP_SERVER__HOST=0.0.0.0
ENV TRICORDER__MCP_SERVER__PORT=8000
ENV TRICORDER__LOGGING__FILE_PATH=""

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "mcp_server.server"]
