# AI 숏폼 동화 스튜디오

주제 한 줄로 한국 전래동화 쇼츠(9:16)를 반자동 제작한다. 휴대폰만으로 조작한다.

```
관리자 페이지에서 주제 입력
  → GitHub Actions가 대본 + 씬별 영상 프롬프트 생성
  → (프롬프트를 복사해 Runway·Pika 등에서 씬 영상 제작)
  → 관리자 페이지에서 씬 영상 업로드
  → GitHub Actions가 나레이션 + 가라오케 자막 입혀 최종 MP4
  → 관리자 페이지에서 바로 재생·다운로드
```

무료다. 화면은 GitHub Pages, 무거운 영상 작업은 GitHub Actions, 파일 보관은
GitHub Release가 맡는다. **GitHub 하나로 끝나고 다른 서비스가 필요 없다.**

관리자 페이지: [jtaechul.github.io/Product/shorts-studio/](https://jtaechul.github.io/Product/shorts-studio/)

## 구조

```
shorts_studio/
├── webapp/index.html       관리자 페이지 (GitHub Pages · 서버 없음)
│                           주제입력·프롬프트복사·영상업로드·완성본재생
├── core/                   제작 엔진 (Actions와 로컬이 공유)
│   ├── llm.py              대본 + 툴별 영문 프롬프트 (Gemini)
│   ├── tts.py              Edge-TTS 합성 + 단어 타임스탬프
│   ├── subtitle.py         가라오케 ASS 자막
│   └── video.py            FFmpeg 규격변환·합성·자막번인
├── content/<id>.json       작품 기록 (대본·상태·완성본 주소) — Actions가 커밋
├── run_script.py           ① 주제 → 대본
├── run_render.py           ② 영상 + 대본 → 최종 MP4
└── app.py                  (선택) 로컬 PC에서 쓰는 Streamlit 단독 실행판
```

워크플로: `.github/workflows/shorts-studio-script.yml` · `shorts-studio-render.yml`
(페이지 자체는 `deploy-pages.yml` 이 main 푸시마다 함께 올린다)

## 처음 한 번만 하는 준비

저장소 시크릿은 `GEMINI_API_KEY` 하나면 된다(이미 등록돼 있다). 대본 생성에만 쓰인다.

관리자 페이지에 처음 들어가면 GitHub 개인 토큰을 한 번 넣는다.
권한은 **Contents = Read and write**, **Actions = Read and write** 두 가지.
토큰은 그 기기의 브라우저에만 남고 어디로도 전송되지 않는다.

## 설계 메모

**단어 타임스탬프는 Whisper가 아니라 Edge-TTS에서 직접 받는다.**
Edge-TTS는 음성을 만들면서 "몇 초에 어떤 단어를 발음했는지"(`WordBoundary`)를 알려준다.
받아쓰기(STT)로 되짚는 방식보다 정확하고, 추가 비용·대기시간·한국어 오인식이 없다.
(로직 출처: `short-movie-generator/src/core/narration_sync.py`)

**나레이션은 씬별로 따로 만든다.** 씬 영상 길이를 그 씬의 나레이션 길이에 정확히 맞추기
위해서다. 전체를 한 덩어리로 만들면 말과 화면이 뒤로 갈수록 밀린다.

**왜 Cloudflare 를 안 쓰나.** 처음엔 `verdict-theater` 처럼 Cloudflare Workers 에 올려
토큰을 서버에 숨기려 했다. 그런데 이 계정의 Cloudflare API 토큰이 만료돼 배포 자체가
되지 않았고(`9109 Invalid access token`), 그건 계정 주인만 고칠 수 있는 문제였다.
GitHub Pages 는 이미 main 푸시마다 자동 배포되고 있어 새로 준비할 것이 없다.
대가로 GitHub 토큰이 서버가 아니라 브라우저에 저장된다.

**완성본은 통째로 받아서 재생한다.** GitHub Release 주소는 `attachment` 로 내려와
아이폰 사파리가 인라인 재생을 거부한다(검은 화면). 서버가 없어 중계할 수 없으므로,
파일을 받아 `blob` 으로 바꿔 물린다. 쇼츠라 용량이 작아 이 방식으로 충분하다.

## 알려진 제약

| 항목 | 내용 |
|---|---|
| 워크플로 위치 | GitHub 규칙상 `workflow_dispatch`는 **기본 브랜치(main)에 있는 워크플로만** 실행된다. |
| Edge-TTS 차단 | 일부 데이터센터 IP에서 마이크로소프트가 403을 낼 수 있다. Actions에서 막히면 성우 합성이 실패한다. |
| 인물 일관성 | 씬마다 영상 AI가 따로 생성하므로 얼굴·의상이 완전히 같지는 않다. 프롬프트에 인물 묘사를 반복해 최대한 맞춘다. |
| 토큰 보관 | 서버가 없어 GitHub 토큰이 브라우저(localStorage)에 남는다. 공용 기기에서는 쓰지 않는다. |

## 로컬에서 직접 돌리기 (선택)

```bash
pip install -r requirements.txt
sudo apt-get install -y ffmpeg fonts-nanum fonts-nanum-extra
streamlit run app.py
```
