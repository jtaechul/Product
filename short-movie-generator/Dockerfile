# 쇼츠/릴스 자동 제작 대시보드 — Cloudflare Containers 이미지
# 무거운 처리(FFmpeg·Playwright/Chromium·Veo 폴링)는 Workers 불가 → Containers (CLAUDE.md 하드 제약)
FROM python:3.11-slim

# FFmpeg + 한국어 폰트(PIL 폴백용) + 인증서
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fonts-noto-cjk ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 파이썬 의존성 (pytest 제외 — 런타임 불필요)
RUN pip install --no-cache-dir \
        google-genai==2.10.0 python-dotenv==1.2.2 pillow==12.3.0 \
        requests==2.34.2 anthropic==0.116.0 playwright==1.61.0

# Chromium + 시스템 의존성 (HTML HUD 렌더용)
RUN playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# 앱 소스 (.dockerignore로 산출물·venv 제외)
COPY . /app

# 컨테이너 밖(워커)에서 접근 가능하도록 0.0.0.0 바인드
ENV HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["python", "-m", "webapp.server"]
