# Dockerfile
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps (ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg gcc git && apt-get clean && rm -rf /var/lib/apt/lists/*

# yt-dlp install
RUN pip install --no-cache-dir yt-dlp

# python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app
COPY . .

# Render provides PORT env var; fallback to 10000
ENV PORT=10000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
