# 쿠팡 어필리에이트 쇼츠 팩토리

상품 발굴 → 대본 → TTS → 영상 렌더링 → 유튜브 업로드를 자동화하는 파이프라인.
마스터 스펙은 [coupang-shorts-pipeline-spec.md](./coupang-shorts-pipeline-spec.md) (SSOT),
프로젝트 규칙은 [CLAUDE.md](./CLAUDE.md) 참고.

**현재 구현 단계: Phase 0 — 렌더 스파이크** (하드코딩 대본 1건 → TTS → 자막 싱크 렌더 검증)

---

## 실행 방법 (GitHub Actions — iPad에서 가능)

1. GitHub 저장소 → **Actions** 탭 → 왼쪽 목록에서 **shorts-produce** 선택
2. 오른쪽 **Run workflow** 버튼 → `tts_provider` 선택
   - `auto` (기본): 등록된 API 키를 elevenlabs → typecast → clova 순으로 자동 감지
   - `mock`: **API 키 없이** 렌더만 검증 (단어별 비프음 + 정확한 타임스탬프)
3. 초록색으로 완료되면 실행 페이지 하단 **Artifacts** 섹션에서
   `shorts-phase0-run…` 파일(zip)을 다운로드 → 안에 `video.mp4`, `audio.mp3`,
   `timestamps.json`, `render_stats.json`(렌더 시간 기록)이 들어 있음
4. 실행 페이지의 **Summary** 탭에도 렌더 통계표가 자동 기록됨

## 시크릿 등록 (TTS API 키)

GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 내용 | 필수 여부 |
|---|---|---|
| `SHORTS_ELEVENLABS_API_KEY` | ElevenLabs API 키 — 오디오+타임스탬프 동시 수신(권장) | 셋 중 하나 이상 |
| `SHORTS_TYPECAST_API_KEY` | Typecast API 키 — 오디오만(whisper 폴백 자동) | 〃 |
| `SHORTS_CLOVA_CLIENT_ID` + `SHORTS_CLOVA_CLIENT_SECRET` | 네이버클라우드 CLOVA Voice Premium(2개 한 쌍) | 〃 |
| `SHORTS_PEXELS_API_KEY` | Pexels API 키 — 배경 영상 자동 확보 | 선택 |

- 키가 하나도 없으면 `auto` 실행은 명확한 오류 메시지와 함께 중단됨 (`mock`은 항상 동작)
- 프로바이더 강제 지정: 실행 시 `tts_provider` 입력 또는 `config/settings.yaml`의 `tts.provider`

## 에셋

### 폰트 (커밋됨)
- `assets/fonts/GmarketSansBold.ttf` — 지마켓 공식 무료 폰트(상업적 사용 허용).
  출처·라이선스는 [assets/licenses.csv](./assets/licenses.csv) 기록.
  원본 배포처: [corp.gmarket.com/fonts](https://corp.gmarket.com/fonts/)

### 배경 영상 (선택 — 없으면 자체 생성 그라데이션으로 렌더)
다음 중 편한 방법으로 확보 (스펙 §3.2 화이트리스트: CC0급 스톡 또는 자체 생성물):

1. **자동(권장)**: [Pexels API 키 발급](https://www.pexels.com/api/) 후 `SHORTS_PEXELS_API_KEY`
   시크릿 등록 → 실행 시 세로 영상을 자동 다운로드 (공식 API만 사용, 스크래핑 아님)
2. **수동**: [Pexels 세로 영상 검색](https://www.pexels.com/search/videos/night%20city/?orientation=portrait)
   에서 마음에 드는 영상 다운로드 → GitHub 웹 UI(**Add file → Upload files**)로
   `projects/coupang-shorts-factory/assets/backgrounds/` 에 업로드(1080×1920 근처 세로 mp4, 1~2개)
   → `assets/licenses.csv`에 출처 행 추가
3. **아무것도 안 함**: 렌더러가 딥네이비→퍼플 그라데이션 배경을 자체 생성(라이선스 완전 무위험)

> `.gitignore`가 `*.mp4`를 막지만 `assets/backgrounds/*.mp4`만 예외로 커밋 허용.

## 파이프라인 구조 (Phase 0 범위)

```
src/phase0_spike.py      # 하드코딩 대본 → TTS → 렌더 오케스트레이션 (Phase 0 전용)
src/audio/tts.py         # M4: 멀티 프로바이더(elevenlabs/typecast/clova/mock) 추상화
src/audio/align_fallback.py  # M5: faster-whisper 단어 타임스탬프 폴백
src/video/render.py      # M6: MoviePy 2.x 렌더(단어 팝업 자막·쉐이크·배경)
scripts/fetch_assets.py  # 배경 영상 자동 확보(선택)
config/settings.yaml     # 채널명·TTS·자막·렌더 파라미터
data/jobs/{job_id}/      # 산출물(커밋 금지) — audio.mp3, timestamps.json, video.mp4, render_stats.json
```

- 공통 계약: 어떤 TTS든 최종 산출은 `audio.mp3` + `timestamps.json`
  (`[{"word","start","end"}]`) 으로 동일. 타임스탬프 미제공 프로바이더는 faster-whisper
  폴백이 자동 실행됨.

## 로컬 실행 (참고용 — 운영 기준은 Actions)

```bash
cd projects/coupang-shorts-factory
pip install -r requirements.txt
python -m src.phase0_spike --provider mock   # 키 없이 렌더 검증
```
