# 허깅페이스 Space(Docker) 용 이미지.
# 허깅페이스가 Streamlit SDK 지원을 중단해(gradio/docker/static만 허용) Docker로 직접 띄운다.
# ffmpeg(영상 합성)와 나눔폰트(한글 자막)를 OS 레벨에서 설치한다.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        fontconfig \
        fonts-nanum \
        fonts-nanum-extra \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# 허깅페이스 Space는 UID 1000 사용자로 실행된다.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

EXPOSE 7860

# XSRF 보호를 끄는 이유: Space는 앱을 iframe 안에서 띄우는데, 켜 두면 영상 업로드가 막힌다.
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--browser.gatherUsageStats=false"]
