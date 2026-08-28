FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 免费实例默认不安装数百 MB 的 Chromium；需要抓取动态 JD 时构建传
# --build-arg INSTALL_PLAYWRIGHT=true
ARG INSTALL_PLAYWRIGHT=false
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then playwright install chromium --with-deps; fi

COPY backend/ ./

RUN if [ ! -f config.yaml ]; then cp config.yaml.example config.yaml; fi

RUN mkdir -p /app/data/resumes /app/data/avatars /app/logs

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
