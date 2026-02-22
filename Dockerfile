# UniFi Toolkit — Application Dockerfile
#
# Multi-stage build:
#   builder  — installs all dependencies (including native libs for python3-saml)
#   runtime  — lean final image

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed for python3-saml (lxml + xmlsec1) and SQLite
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a prefix we'll copy to runtime
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime system libs (only what's needed to load the native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxmlsec1 \
    libxmlsec1-openssl \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data /app/logs \
    && chmod 777 /app/data /app/logs

# Non-root user for security
RUN useradd -m -u 1000 toolkit \
    && chown -R toolkit:toolkit /app
USER toolkit

EXPOSE 8000

# Startup: run Alembic migrations then start uvicorn
CMD ["sh", "-c", \
     "alembic upgrade head && \
      uvicorn app.main:app \
        --host ${APP_HOST:-0.0.0.0} \
        --port ${APP_PORT:-8000} \
        --workers 1 \
        --log-level ${LOG_LEVEL:-info} \
        --access-log \
        --proxy-headers \
        --forwarded-allow-ips='*'"]
