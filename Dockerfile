# ==============================================================================
# PaveSentry Production Dockerfile (Multi-Stage Build)
# Conforms to CIS Docker Benchmark & Government Cyber Hardening Norms
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Dependency Builder
# ------------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build-time native compilation dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment for clean layer extraction
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: Hardened Minimal Production Runner
# ------------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ENVIRONMENT=production \
    PORT=9005

# Install only minimal runtime shared libraries (GEOS for PostGIS, GLib/GL for OpenCV)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libgeos-c1v5 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create dedicated unprivileged system group & user (UID/GID 1001)
RUN groupadd -g 1001 pavesentry && \
    useradd -u 1001 -g pavesentry -s /bin/false -m pavesentry

# Copy project source code with unprivileged ownership
COPY --chown=pavesentry:pavesentry . /app

# Ensure writable directories for uploads and sqlite database fallback
RUN mkdir -p /app/uploads/potholes /app/data && \
    chown -R pavesentry:pavesentry /app/uploads /app/data

# Switch to hardened non-root user
USER pavesentry

# Expose internal service port
EXPOSE 9005

# Liveness probe conforming to Kubernetes / Docker health standards
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:9005/healthz || exit 1

# Launch production ASGI server with multi-worker concurrency
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "9005", "--workers", "4"]
