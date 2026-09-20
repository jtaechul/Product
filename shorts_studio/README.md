# AI 숏폼 동화 스튜디오

주제 한 줄로 한국 전래동화 쇼츠(9:16)를 반자동 제작하는 모바일 친화 웹앱.

```
주제 입력 → 대본·영상프롬프트 생성 → (외부 툴로 만든) 씬 영상 업로드
        → 나레이션 + 가라오케 자막 자동 생성 → 최종 MP4
```

## 쓰는 법

1. **① 대본·프롬프트** — 주제·컷 수·영상 생성 툴을 고르면 씬별 한국어 나레이션과
   그 툴 문법에 맞춘 영문 프롬프트가 나옵니다. 나레이션은 직접 고칠 수 있습니다.
2. 프롬프트를 복사해 Runway·Pika·Luma·Kling·Sora·Veo 등에서 씬 영상을 만듭니다.
3. **② 영상 업로드** — 만든 영상을 씬 순서대로 올립니다(휴대폰 갤러리에서 바로 가능).
4. **③ 렌더링** — 성우 목소리, 가라오케 자막, 9:16 크롭이 자동 적용된 MP4가 나옵니다.

## 로컬 실행

```bash
pip install -r requirements.txt
sudo apt-get install -y ffmpeg fonts-nanum fonts-nanum-extra   # macOS: brew install ffmpeg
streamlit run app.py
```

## Streamlit Community Cloud 배포

- Main file path를 `shorts_studio/app.py` 로 지정합니다.
- `requirements.txt`(파이썬 패키지)와 `packages.txt`(ffmpeg·한글 폰트)가 자동 설치됩니다.
- OpenAI 키는 앱 사이드바에 직접 넣거나, Secrets에 `OPENAI_API_KEY = "sk-..."` 로 둡니다.

## 설계 메모

**단어 타임스탬프는 Whisper가 아니라 Edge-TTS에서 직접 받습니다.**
Edge-TTS는 음성을 만들면서 "몇 초에 어떤 단어를 발음했는지"(`WordBoundary`)를 알려줍니다.
받아쓰기(STT)로 되짚는 방식보다 정확하고, 추가 비용·대기시간·한국어 오인식이 없습니다.
(로직 출처: `short-movie-generator/src/core/narration_sync.py`)

**나레이션은 씬별로 따로 만듭니다.** 씬 영상 길이를 그 씬의 나레이션 길이에 정확히 맞추기
위해서입니다. 전체를 한 덩어리로 만들면 말과 화면이 뒤로 갈수록 밀립니다.

**씬 영상 길이 처리** — 나레이션보다 짧으면 마지막 프레임을 정지시켜 늘리고, 길면 잘라냅니다.
가로 영상도 9:16으로 자동 크롭됩니다.

## 알려진 제약

| 항목 | 내용 |
|---|---|
| Edge-TTS 차단 | 일부 데이터센터 IP에서 마이크로소프트가 403을 반환할 수 있습니다. 음성 합성이 403으로 실패하면 로컬 실행으로 우회하세요. |
| Streamlit Cloud 자원 | RAM 1GB·업로드 200MB 제한. 720×1280 · 60초 내외를 권장합니다. 1080×1920은 씬이 많으면 실패할 수 있습니다. |
| 인물 일관성 | 씬마다 영상 AI가 따로 생성하므로 얼굴·의상이 완전히 같지는 않습니다. 프롬프트에 인물 묘사를 반복해 최대한 맞춥니다. |

## 구조

```
shorts_studio/
├── app.py              # Streamlit UI + 전체 흐름
├── core/
│   ├── llm.py          # 대본 + 툴별 영문 프롬프트 (OpenAI)
│   ├── tts.py          # Edge-TTS 합성 + 단어 타임스탬프 + 자막 줄 묶기
│   ├── subtitle.py     # 가라오케 ASS 자막
│   └── video.py        # FFmpeg 정규화·합성·번인
├── requirements.txt    # 파이썬 패키지
└── packages.txt        # ffmpeg, 나눔폰트 (Streamlit Cloud용)
```
