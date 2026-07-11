# 쿠팡 어필리에이트 쇼츠 팩토리 — Claude Code 프로젝트 규칙

> 마스터 스펙(SSOT): 이 폴더의 `coupang-shorts-pipeline-spec.md` — 모든 구현은 스펙 §8 로드맵의
> Phase 순서를 따르고, 각 Phase의 DoD를 충족한 뒤에만 다음 Phase로 진행한다.

## 현재 상태

- **Phase 0 (렌더 스파이크) 완료**: 하드코딩 대본 1건 → TTS → `timestamps.json` → MoviePy 렌더
  → Actions Artifacts 업로드까지 동작. 실행: GitHub Actions `shorts-produce` 워크플로우(수동).
- 다음 단계: Phase 1 (반자동 MVP — M2 수동 CSV + M3 대본 생성 + M7 private 업로드)

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
- 유일한 예외: `.github/workflows/shorts-produce.yml` (GitHub가 워크플로우 위치를 루트로 강제).
  - 트리거는 `workflow_dispatch` + `requests/*.json` 전용 push(paths 필터 적용됨).
    push 트리거를 확장할 때도 반드시 `paths: ['projects/coupang-shorts-factory/**']`
    필터를 유지한다.
- 저장소의 다른 프로젝트 폴더·파일·워크플로우는 읽기만 하고 절대 수정하지 않는다.
- 한 커밋은 한 프로젝트 폴더만 수정한다(`.github/`만 공용 허용) — 루트의
  `project-isolation-guard.yml`이 모든 푸시에서 자동 검사한다.

## Git 운영 규칙 — 오류 예방 핵심 (전문)

- 브랜치 생성과 PR 금지, main에서 직접 작업한다.
  환경 제약으로 브랜치가 강제되는 경우에도 이 세션 안에서 main 머지와
  푸시까지 완료해야 한다.
- 의미 단위마다 커밋하고, 커밋 직후 반드시 `git push origin main` 실행.
- 푸시 직후 `git log origin/main --oneline -1` 로 원격 반영을 확인하고
  미반영이면 재시도해라.
- 이유: workflow_dispatch 수동 실행 버튼은 워크플로우 파일이 기본
  브랜치(main)에 존재해야만 GitHub UI에 나타난다. 푸시 누락 시
  Actions에서 아무것도 실행할 수 없다.
- `git push --force`, 이력 재작성, 기존 커밋 되돌리기 금지.
- 푸시 실패(권한, 충돌 등) 시 우회하지 말고 오류 메시지 원문을 보고해라.
- 세션 종료 전 `git status` clean 상태와 로컬/원격 HEAD 일치를 확인해
  결과를 보고해라.

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
