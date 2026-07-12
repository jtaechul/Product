# 쿠팡 어필리에이트 쇼츠 팩토리 — Claude Code 프로젝트 규칙

> 마스터 스펙(SSOT): 이 폴더의 `coupang-shorts-pipeline-spec.md` — 모든 구현은 스펙 §8 로드맵의
> Phase 순서를 따르고, 각 Phase의 DoD를 충족한 뒤에만 다음 Phase로 진행한다.

## ⭐ 핵심 규칙 — 사용자 노코드 원칙 (항상 적용)

- 사용자는 **코드·설정·CSV·YAML 파일을 직접 입력하거나 편집하지 않는다.** 사용자 입력이 필요한
  모든 조작(상품 등록·삭제, 제작 실행, 벤치마크 채널 관리 등)은 **관리자 페이지 UI**로 제공한다:
  [shorts-admin.jtaechul.workers.dev](https://shorts-admin.jtaechul.workers.dev)
  (`admin/` 폴더, Cloudflare Workers 정적 에셋, `deploy-shorts-admin.yml`로 자동 배포).
- 새 기능이 사용자 입력을 요구하게 되면 **관리자 페이지에 해당 입력 UI를 함께 추가**한다.
  사용자에게 파일 편집·코드 수정을 안내하는 것은 규칙 위반.
  (허용 예외: GitHub 시크릿 등록, 외부 서비스 키 발급처럼 외부 사이트 자체 화면에서만 가능한 작업)

## ⭐ 핵심 규칙 — 비판적 파트너 원칙 (항상 적용)

- **사용자 의견을 무조건 반영하지 않는다.** 모든 지시·의견은 프로젝트의 궁극 목적
  (유튜브 쇼츠 → 쿠팡 어필리에이트 수익)에 비추어 비판적·객관적으로 검토하고,
  특히 **유튜브(구글) 알고리즘·검색 SEO·정책 리스크** 관점에서 문제가 보이면
  반영 전에 이견·대안·개선방안을 근거와 함께 제시한다.
- Claude 자신의 과거 결정도 같은 기준으로 재검토 대상이다. 알고리즘 관련 판단에는
  가능한 한 근거(정책명·지표)를 붙이고, 추측이면 추측이라고 밝힌다.

## 현재 상태

- **Phase 0~3 구현 완료**: M1(아웃라이어 리서치, `shorts-research.yml` 주간) /
  M2(수동 CSV 큐 + 쿠팡 API 모듈은 키 승인 대기) / M3(대본 생성, claude-sonnet-4-6) /
  M4+M5(TTS 멀티 프로바이더+whisper 폴백) / M6(렌더: **상품 사진을 히어로로**(둥근 카드+그림자,
  켄번즈 줌) + **같은 사진 흐리게+어둡게 배경**(항상 상품 관련) + 자막 스크림 + 단어 팝업 자막
  (긴 어절 종결어미 분리)·쉐이크. 상품 사진 없을 때만 Pexels 스톡/그라데이션 폴백) /
  M7(유튜브 private 업로드+고지 댓글, §3.1 assert 강제) / M8(`src/pipeline.py`).
- 자동화: 평일 07:30 KST cron 제작(전제조건 미비 시 soft 통과), 큐 상태는 업로드 성공 시
  CI가 `data/processed.json`을 `[skip ci]` 커밋. 텔레그램 성공/실패 알림(`src/notify.py`).
- 관리자 페이지(노코드): `admin/public/index.html` — 상품 등록/삭제·제작 실행(workflow_dispatch)·
  리서치 실행·실행 기록·채널 관리. 사용자 PAT(Contents/Actions RW, 브라우저 localStorage에만
  저장)로 GitHub API를 직접 호출. 서버 로직·서버 시크릿 없음.
- **수익화 2단계 로드맵 (2026-07-12 확정 — 사용자 스크린샷으로 검증)**:
  ① 지금(채널 0일차~): 쿠팡파트너스 단축링크(`link.coupang.com/a/...`)를 고정 댓글+설명란에.
  ② 자격 달성 후: **유튜브 쇼핑 제휴로 전환/병행** — 한국은 쿠팡이 유튜브 쇼핑 제휴사라서
  영상 위 상품 스티커(`link.coupang.com/re3/AFYOUTUBE...`, "크리에이터에게 수수료 지급")로
  쿠팡 상품 태그 가능(예: 썰피자 채널). 단 YPP 가입 + 구독자 조건 필요(정확 기준은 달성
  시점에 유튜브 공지 재확인). 스티커가 고정 댓글보다 전환이 좋으므로 **구독자 성장이 곧
  수익화 업그레이드 경로**다. 주의: 파트너스 링크를 스티커에 붙이는 방식이 아니라
  유튜브 스튜디오에서 상품을 태그하는 별도 시스템.
  관리자 페이지에 **링크 + 페이지 캡처(PDF·이미지) 또는 텍스트**만 등록(`data/notes/{row_hash}*`) →
  M2.5(`src/product/enrich.py`)가 캡처를 비전으로 읽어 상품명·가격·특징·후기 요점 자동 추출
  (전체 캡처 PDF는 PyMuPDF로 상단·상품평 타일 분할 후 전송), M3가 notes를 대본 재료로 사용.
  업로드 성공 시 소비한 notes 자료는 파이프라인이 삭제하고 워크플로우가 커밋(비대화 방지). **쿠팡 페이지 크롤링·리뷰 자동 수집은 봇 차단 + 스펙 §2·§3.2 위반이라
  구현 금지** (붙여넣기가 공식 대체 경로, API 승인 후 상품 데이터 자동화).
- 남은 사용자 작업: **유튜브 채널 생성(시작 시 이름·핸들·설정 컨설팅 + 완성 후 피드백을 제공하기로
  예약됨)**, `SHORTS_YT_*` 인증 3종 등록, 관리자 페이지에서 실상품 등록·벤치마크 채널 추가,
  쿠팡 API 키 승인 시 M2 1안 전환 검증 → `docs/setup-guide.md` 참조.
  (`SHORTS_YT_API_KEY`는 2026-07-12 등록 완료 — 리서치 M1 사용 가능)

## 수행 지침 요약 (스펙 §0)

1. 스펙 문서가 단일 진실 원천(SSOT). §8 Phase 순서대로 구현.
2. 각 Phase의 완료 기준(DoD) 충족 후에만 다음 Phase 진행.
3. §3 준수 가드레일은 모든 코드·산출물에 무조건 적용 (협상 불가).
4. 스펙이 모호하면 임의 구현하지 말고 사용자에게 질문 후 진행.
5. 모든 코드는 GitHub Actions(ubuntu-latest) 실행 전제 — 로컬 실행 가정 금지 (사용자는 iPad 환경).

## 준수 가드레일 요약 (스펙 §3 — 절대 위반 금지)

- **제휴 고지(§3.1)**: 고정 문구 `이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의
  수수료를 제공받습니다` 를 ① 영상 설명란 최상단 첫 줄 ② 고정 댓글 링크 옆에 코드로 강제
  (M7에서 누락 시 assert로 업로드 중단).
- **에셋 화이트리스트(§3.2)**: CC0(Pexels·Pixabay), 자체 생성물(AI 생성 포함), 쿠팡 파트너스 API
  제공 상품 이미지만 허용. **타 유튜브 영상의 클립·오디오·대본, 출처 불명 GIF, 스크래핑 이미지 금지.**
- **대본 표현 규제(§3.3)**: "최고", "유일", "100% 효과", 질병 치료 등 절대적·의학적 단정 표현 금지.
  생성 후 금지어 필터 통과 필수.
- **유튜브 정책(§3.4)**: 영상마다 고유 상품·대본·이미지(반복성 회피). 제휴 링크는 고정 댓글 1개 +
  설명란 1개로 제한.
- **원안 대비 변경(§2)**: 타 영상 대본 추출 금지(상품 데이터 기반 오리지널 대본만),
  CC0/자체 생성 에셋만 사용, 스크래핑 금지(YouTube Data API v3만).

## 폴더 격리 (저장소 공통 규칙)

- 이 프로젝트의 모든 파일은 `projects/coupang-shorts-factory/` 하위에만 둔다.
- 유일한 예외: `.github/workflows/shorts-produce.yml`·`shorts-research.yml`·`deploy-shorts-admin.yml`
  (GitHub가 워크플로우 위치를 루트로 강제).
  - 트리거는 `workflow_dispatch` + `requests/*.json` 전용 push(paths 필터 적용됨).
    push 트리거를 확장할 때도 반드시 `paths: ['projects/coupang-shorts-factory/**']`
    필터를 유지한다.
- 저장소의 다른 프로젝트 폴더·파일·워크플로우는 읽기만 하고 절대 수정하지 않는다.
- 한 커밋은 한 프로젝트 폴더만 수정한다(`.github/`만 공용 허용) — 루트의
  `project-isolation-guard.yml`이 모든 푸시에서 자동 검사한다.

## Git 운영 규칙 — 핵심 5줄

1. main에서 직접 작업한다 (브랜치·PR 금지, 브랜치가 강제되면 세션 내 main 머지까지 완료).
2. 의미 단위마다 커밋하고 커밋 즉시 push 한다.
3. push 직후 `git log origin/main --oneline -1` 로 원격 반영을 확인한다.
4. force push·이력 재작성·커밋 되돌리기 금지.
5. push 실패 시 우회하지 말고 오류 원문을 보고하고 멈춘다.

상세 근거·절차는 `coupang-shorts-pipeline-spec.md` 참조.

## 시크릿 (GitHub Actions Secrets — 코드에 하드코딩 금지)

| 이름 | 용도 |
|---|---|
| `SHORTS_ELEVENLABS_API_KEY` | ElevenLabs TTS (문자 타임스탬프 동시 수신) |
| `SHORTS_TYPECAST_API_KEY` | Typecast TTS (오디오만 → faster-whisper 폴백) |
| `SHORTS_CLOVA_CLIENT_ID` / `SHORTS_CLOVA_CLIENT_SECRET` | 네이버클라우드 CLOVA Voice Premium (오디오만 → 폴백) |
| `SHORTS_PEXELS_API_KEY` (선택) | 배경 영상 자동 확보(`scripts/fetch_assets.py`) — 없어도 동작(그라데이션 폴백) |

- TTS 프로바이더는 `config/settings.yaml`의 `tts.provider`로 선택 (`auto` = 키 자동 감지).
- 어느 프로바이더든 최종 산출은 `audio.mp3` + `timestamps.json` 으로 동일해야 한다 (공통 계약).

## 산출물 규칙

- 영상·음성 산출물(`data/jobs/`, `*.mp4`, `*.mp3`)은 커밋 금지 — Actions Artifacts로만 전달.
- 예외: `assets/backgrounds/*.mp4` (CC0 배경 원본, `.gitignore` 부정 패턴으로 커밋 허용).
- 에셋을 추가하면 반드시 `assets/licenses.csv`에 출처·라이선스를 기록한다.
