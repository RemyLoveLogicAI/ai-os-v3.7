FROM python:3.11-slim

LABEL org.opencontainers.image.title="AI OS v3.7"
LABEL org.opencontainers.image.description="LoveLogicAI — LLM Router + Skill Marketplace"
LABEL org.opencontainers.image.vendor="LoveLogicAI LLC"
LABEL org.opencontainers.image.version="3.7.0"

# Build args for metadata
ARG BUILD_VERSION=dev
ARG BUILD_DATE=unknown
ENV BUILD_VERSION=${BUILD_VERSION}
ENV BUILD_DATE=${BUILD_DATE}

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AI_OS_ENV=production \
    PORT=8000 \
    PYTHONPATH=/app/src

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy source
COPY src/ ./src/
RUN mkdir -p ./skills

# Create non-root user
RUN useradd -m -u 1000 aios && chown -R aios:aios /app
USER aios

EXPOSE ${PORT}

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn src.api.server:app --host 0.0.0.0 --port ${PORT} --workers 1 --log-level info"]
