# 4linux-downloader — imagem única (FastAPI + Playwright/Chromium + yt-dlp + ffmpeg)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# ffmpeg: necessário pro yt-dlp juntar vídeo+áudio (HLS/DASH do Vimeo)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# dependências Python (yt-dlp entra aqui e vira binário no PATH)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Chromium + libs de sistema exigidas pelo Playwright
RUN playwright install --with-deps chromium

# código da aplicação
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
