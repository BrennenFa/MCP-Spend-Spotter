FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .

# Install uv for faster parallel dependency installation
RUN pip install uv

# Install CPU-only PyTorch first to avoid pulling CUDA dependencies
RUN pip install --no-cache-dir torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu

# Install Python dependencies in parallel
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Pre-download models in parallel to avoid first-request timeout
RUN mkdir -p /app/.cache/huggingface
COPY download_models.py .
RUN python download_models.py

# Copy application code
COPY . .

# Make startup script executable
RUN chmod +x start.sh

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

EXPOSE 8000

CMD ["./start.sh"]
