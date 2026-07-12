# 쿠팡 어필리에이트 쇼츠 팩토리 — Claude Code 프로젝트 규칙

> 마스터 스펙(SSOT): 이 폴더의 `coupang-shorts-pipeline-spec.md` — 모든 구현은 스펙 §8 로드맵의
> Phase 순서를 따르고, 각 Phase의 DoD를 충족한 뒤에만 다음 Phase로 진행한다.

## 현재 상태

- **Phase 0~3 구현 완료**: M1(아웃라이어 리서치, `shorts-research.yml` 주간) /
  M2(수동 CSV 큐 + 쿠팡 API 모듈은 키 승인 대기) / M3(대본 생성, claude-sonnet-4-6) /
  M4+M5(TTS 멀티 프로바이더+whisper 폴백) / M6(렌더: 단어 팝업 자막(긴 어절은 종결어미 분리)·
  상품 이미지 줌인·쉐이크·상품 연관 Pexels 배경 검색 `src/video/backgrounds.py`) /
  M7(유튜브 private 업로드+고지 댓글, §3.1 assert 강제) / M8(`src/pipeline.py`).
- 자동화: 평일 07:30 KST cron 제작(전제조건 미비 시 soft 통과), 큐 상태는 업로드 성공 시
  CI가 `data/processed.json`을 `[skip ci]` 커밋. 텔레그램 성공/실패 알림(`src/notify.py`).
- 남은 사용자 작업: **유튜브 채널 생성(시작 시 이름·핸들·설정 컨설팅 + 완성 후 피드백을 제공하기로
  예약됨)**, `SHORTS_YT_*` 인증 3종·`SHORTS_YT_API_KEY` 등록, 실제 제휴 링크로 CSV 갱신,
  쿠팡 API 키 승인 시 M2 1안 전환 검증 → `docs/setup-guide.md` 참조.

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
- 유일한 예외: `.github/workflows/shorts-produce.yml`·`shorts-research.yml` (GitHub가 워크플로우 위치를 루트로 강제).
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
