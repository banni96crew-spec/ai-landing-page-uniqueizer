# syntax=docker/dockerfile:1.7

##############################
# 1️⃣ Builder stage
##############################
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# System dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy only the requirements for the caching layer
COPY requirements.txt .

# Use BuildKit cache for pip
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip==24.0 && \
    pip install --no-cache-dir -r requirements.txt

############################
#2️⃣ Runtime stage
############################
FROM python:3.12-slim AS runtime

LABEL maintainer="Nikolay Isakov"
LABEL project="AI-Landing-Page-Uniqueizer"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1\
    PATH="/opt/venv/bin:$PATH" \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app

# Install tini + minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    # Playwright Chromium minimal deps
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxcb1 libxkbcommon0 libx11-6 libxcomposite1 \
    libxdamage1 libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create a non-root user
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

# Copy the application
COPY --chown=appuser:appuser . .

# Permissions
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Healthcheck without curl
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

# tini for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Production server (FastAPI)
CMD ["gunicorn", "main:app", \
    "-k", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--workers", "4", \
    "--timeout", "60"]