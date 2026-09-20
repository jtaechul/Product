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

무료다. 화면은 Cloudflare Workers, 무거운 영상 작업은 GitHub Actions, 파일 보관은
GitHub Release가 맡는다. 저장소의 `book-carousel`·`short-movie-generator`와 같은 구조다.

## 구조

```
shorts_studio/
├── admin/                  관리자 페이지 (Cloudflare Workers)
│   ├── public/index.html   모바일 UI — 주제입력·프롬프트복사·영상업로드·완성본재생
│   ├── worker/index.mjs    로그인·GitHub 호출·보관함(KV) 업로드·완성본 재생
│   └── kv_id.py            배포 때 보관함 번호를 찾는 도우미
├── core/                   제작 엔진 (Actions와 로컬이 공유)
│   ├── llm.py              대본 + 툴별 영문 프롬프트 (OpenAI)
│   ├── tts.py              Edge-TTS 합성 + 단어 타임스탬프
│   ├── subtitle.py         가라오케 ASS 자막
│   └── video.py            FFmpeg 규격변환·합성·자막번인
├── content/<id>.json       작품 기록 (대본·상태·완성본 주소) — Actions가 커밋
├── run_script.py           ① 주제 → 대본
├── run_render.py           ② 영상 + 대본 → 최종 MP4
└── app.py                  (선택) 로컬 PC에서 쓰는 Streamlit 단독 실행판
```

워크플로: `.github/workflows/shorts-studio-script.yml` · `shorts-studio-render.yml` ·
`deploy-shorts-studio-admin.yml`

## 처음 한 번만 하는 준비

저장소 → Settings → Secrets and variables → Actions 에 아래를 등록한다.

이 저장소엔 프로젝트가 여럿이라, 이 프로젝트 전용 값에는 `MOVIEGEN_` 을 붙인다.
여러 프로젝트가 같이 쓰는 API 키는 접두어 없이 그대로 쓴다.

| 이름 | 쓰이는 곳 | 상태 |
|---|---|---|
| `CF_API_TOKEN` | 관리자 페이지 배포 | 이미 등록돼 있다 |
| `MOVIEGEN_ADMIN_PASSWORD` | 관리자 페이지 로그인 비밀번호 (직접 정한다) | 필수 |
| `MOVIEGEN_ADMIN_GH_TOKEN` | 워커가 쓸 GitHub 토큰 — Contents = Read, Actions = Read and write | 필수 |
| `OPENAI_API_KEY` | 대본 생성 | 필수 |
| `MOVIEGEN_SESSION_SECRET` | 로그인 위조 방지용 문자열 | 선택 (없으면 비밀번호를 쓴다) |
| `CLOUDFLARE_ACCOUNT_ID` | 토큰이 여러 계정에 닿을 때만 | 선택 |

그다음 관리자 페이지 주소를 열고 `ADMIN_PASSWORD` 로 들어가면 끝이다.
**손님이 폰에서 토큰을 다룰 일은 없다** — GitHub 토큰은 워커 안에만 있다.

## 설계 메모

**단어 타임스탬프는 Whisper가 아니라 Edge-TTS에서 직접 받는다.**
Edge-TTS는 음성을 만들면서 "몇 초에 어떤 단어를 발음했는지"(`WordBoundary`)를 알려준다.
받아쓰기(STT)로 되짚는 방식보다 정확하고, 추가 비용·대기시간·한국어 오인식이 없다.
(로직 출처: `short-movie-generator/src/core/narration_sync.py`)

**나레이션은 씬별로 따로 만든다.** 씬 영상 길이를 그 씬의 나레이션 길이에 정확히 맞추기
위해서다. 전체를 한 덩어리로 만들면 말과 화면이 뒤로 갈수록 밀린다.

**씬 영상은 보관함(KV)을 거쳐 간다.** 브라우저에서 깃허브로 바로 올리면 CORS에 막히고,
관리자 토큰에 쓰기 권한까지 줘야 한다. 대신 워커가 8MB씩 조각내어 클라우드플레어
보관함에 넣고, 워크플로가 자기 열쇠로 받아 간다(14일 보관). 열쇠에 임의 번호를 붙이는
이유는, 같은 이름을 다시 쓰면 보관함이 전 세계에 퍼지는 1분 사이에 워크플로가 **옛 영상**을
받아 갈 수 있기 때문이다.

**완성본 재생에 프록시를 쓰는 이유.** GitHub Release 주소는 `attachment`로 내려와
아이폰 사파리가 인라인 재생을 거부한다(검은 화면). 워커가 `video/mp4` + `inline`으로
바꿔 중계하고, Range(몇 번째 바이트부터)를 그대로 넘겨 탐색도 되게 한다.

(위 두 가지와 로그인 구조는 `verdict-theater/admin` 의 검증된 구현을 이식했다.)

## 알려진 제약

| 항목 | 내용 |
|---|---|
| 워크플로 위치 | GitHub 규칙상 `workflow_dispatch`는 **기본 브랜치(main)에 있는 워크플로만** 실행된다. |
| Edge-TTS 차단 | 일부 데이터센터 IP에서 마이크로소프트가 403을 낼 수 있다. Actions에서 막히면 성우 합성이 실패한다. |
| 인물 일관성 | 씬마다 영상 AI가 따로 생성하므로 얼굴·의상이 완전히 같지는 않다. 프롬프트에 인물 묘사를 반복해 최대한 맞춘다. |
| 업로드 용량 | Release 자산은 넉넉하지만, 휴대폰 회선으로 큰 영상을 올리면 시간이 걸린다. |

## 로컬에서 직접 돌리기 (선택)

```bash
pip install -r requirements.txt
sudo apt-get install -y ffmpeg fonts-nanum fonts-nanum-extra
streamlit run app.py
```
