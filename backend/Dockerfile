# Stage 1: Build dependencies
FROM python:3.11.10-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Stage 2: Minimal runtime
FROM python:3.11.10-slim-bookworm AS runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    UPLOAD_DIR="/app/uploads"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged system user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create uploads directory and set permissions
RUN mkdir -p /app/uploads /uploads && chown -R appuser:appgroup /app /uploads

# Copy application source code
COPY --chown=appuser:appgroup . /app

# Point d'entrée : migrations Alembic puis démarrage d'uvicorn
COPY --chown=appuser:appgroup entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
