# ==============================================================================
# Multi-Stage Dockerfile for Adversarial Arena API
# ==============================================================================

# Stage 1: Build dependencies in isolated builder
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./

# Install pip tooling and build wheels
RUN pip install --no-cache-dir --upgrade pip hatchling && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels .

# Stage 2: Runtime image (slim, non-root user)
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    netcat-openbsd \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtualenv and install built wheels
RUN python -m venv /venv
COPY --from=builder /build/wheels /wheels
RUN /venv/bin/pip install --no-cache-dir --upgrade pip && \
    /venv/bin/pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Create unprivileged application user
RUN groupadd -g 1001 arena && \
    useradd -u 1001 -g arena -s /bin/bash -m arena

# Copy application source, migrations and entrypoint
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN chown -R arena:arena /app

USER arena

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
