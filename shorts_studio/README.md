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
GitHub Release가 맡는다. 저장소의 `book-carousel`·`verdict-theater`와 같은 구조다.

## 구조

```
shorts_studio/
├── admin/                  관리자 페이지 (Cloudflare Workers)
│   ├── public/index.html   모바일 UI — 인물기준이미지·프롬프트복사·영상업로드·재생
│   └── worker/index.mjs    로그인·GitHub 호출·업로드 중계·완성본 재생
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

워크플로: `.github/workflows/shorts-studio-script.yml` · `shorts-studio-render.yml` ·
`deploy-shorts-studio-admin.yml`

## 처음 한 번만 하는 준비

| 이름 | 쓰임 |
|---|---|
| `GEMINI_API_KEY` | 대본 생성 |
| `CF_API_TOKEN` | 관리자 페이지 배포 |
| `CLOUDFLARE_ACCOUNT_ID` | 어느 Cloudflare 계정에 올릴지 |
| `MOVIEGEN_ADMIN_PASSWORD` | 관리자 페이지 로그인 비밀번호 |
| `MOVIEGEN_ADMIN_GH_TOKEN` | 워커가 쓸 GitHub 토큰 (Contents·Actions 모두 Read and write) |
| `MOVIEGEN_SESSION_SECRET` | (선택) 로그인 위조 방지용 |

손님은 관리자 페이지 주소를 열고 비밀번호만 치면 된다. 토큰은 워커 안에만 있다.

## 설계 메모

**단어 타임스탬프는 Whisper가 아니라 Edge-TTS에서 직접 받는다.**
Edge-TTS는 음성을 만들면서 "몇 초에 어떤 단어를 발음했는지"(`WordBoundary`)를 알려준다.
받아쓰기(STT)로 되짚는 방식보다 정확하고, 추가 비용·대기시간·한국어 오인식이 없다.
(로직 출처: `short-movie-generator/src/core/narration_sync.py`)

**나레이션은 씬별로 따로 만든다.** 씬 영상 길이를 그 씬의 나레이션 길이에 정확히 맞추기
위해서다. 전체를 한 덩어리로 만들면 말과 화면이 뒤로 갈수록 밀린다.

**⭐ 인물 일관성 — 이 프로젝트에서 가장 중요한 설계.**
씬마다 영상 AI가 따로 그리면 주인공이 컷마다 다른 사람이 된다. 유일하게 확실한 해법은
**인물 기준 이미지 한 장**을 만들어 모든 씬에 함께 넣는 것이다(image-to-video).
그래서 외모는 `character_image_prompt` 에서만 정하고, **씬 프롬프트에는 외모를 한 글자도
쓰지 않는다** — 참조 이미지와 글이 싸우면 이긴 쪽이 컷마다 달라져 옷이 계속 바뀐다.
`strip_look_words()` 가 씬 프롬프트에 외모 낱말이 새어 들어갔는지 검사해 경고한다.
(`verdict-theater/CLAUDE.md` 의 "루미나 3대 금지" 중 ①을 이식)

**업로드와 재생은 워커가 중계한다.** 브라우저에서 깃허브 업로드 서버로 바로 쏘면
CORS 에 막히고(실제로 "연결이 끊겼습니다" 로 나타났다), 릴리스 주소는 `attachment` 로
내려와 사파리가 인라인 재생을 거부한다(검은 화면). 워커가 둘 다 풀어 준다.

## 알려진 제약

| 항목 | 내용 |
|---|---|
| 워크플로 위치 | GitHub 규칙상 `workflow_dispatch`는 **기본 브랜치(main)에 있는 워크플로만** 실행된다. |
| Edge-TTS 차단 | 일부 데이터센터 IP에서 마이크로소프트가 403을 낼 수 있다. Actions에서 막히면 성우 합성이 실패한다. |
| 인물 일관성 | 기준 이미지를 영상 툴의 **참조 이미지** 칸에 매번 넣어야 효과가 있다. 안 넣으면 컷마다 인물이 달라진다. |
| 업로드 용량 | 무료 Cloudflare 는 한 번에 100MB 까지 받는다. |

## 로컬에서 직접 돌리기 (선택)

```bash
pip install -r requirements.txt
sudo apt-get install -y ffmpeg fonts-nanum fonts-nanum-extra
streamlit run app.py
```
