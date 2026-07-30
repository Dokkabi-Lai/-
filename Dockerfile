FROM python:3.11-slim

# Playwright system deps + curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl fonts-wqy-zenhei fonts-noto-cjk \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 \
    libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libxshmfence1 libx11-xcb1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better caching)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium --with-deps

# Copy application code
COPY backend/ ./

# Use example config as default (can be overridden by env vars or mounted volume)
RUN if [ ! -f config.yaml ]; then cp config.yaml.example config.yaml; fi

# Create data directories
RUN mkdir -p /app/data/resumes /app/logs

EXPOSE 8000

# PORT env var is set by ClawCloud/Railway/Render
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
