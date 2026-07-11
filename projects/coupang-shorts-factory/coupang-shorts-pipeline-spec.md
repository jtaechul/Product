# 쿠팡 어필리에이트 쇼츠 자동화 파이프라인 기획서

> Claude Code 실행용 마스터 스펙 · v1.0 · 2026-07-11
> 벤치마크: 썰피자(@ssul_pizza) 포맷 — 신기한 물건 큐레이션 쇼츠

---

## 0. Claude Code 수행 지침

- 이 문서는 단일 진실 원천(SSOT)이며, §8 로드맵의 Phase 순서대로 구현할 것
- 각 Phase의 완료 기준(DoD, Definition of Done)을 충족한 뒤에만 다음 Phase 진행
- §3 준수 가드레일은 모든 코드·산출물에 무조건 적용 (협상 불가 항목)
- 스펙이 모호하면 임의 구현하지 말고 사용자에게 질문 후 진행
- 모든 코드는 GitHub Actions(ubuntu-latest) 실행을 전제로 작성 (로컬 실행 가정 금지 — 사용자는 iPad 환경)

---

## 1. 프로젝트 개요

### 1.1 목표
- 상품 발굴 → 대본 → TTS → 영상 렌더링 → 유튜브 업로드까지 사람 개입 최소화 파이프라인 구축
- 수익 모델: 쿠팡 파트너스 제휴 수수료 (조회수 광고수익 아님)
  - 핵심 이점: 유튜브 파트너 프로그램(YPP, 구독 1,000명 + 쇼츠 조회 1,000만/90일) 승인 불필요 → **1일차부터 수익 발생 가능 구조**

### 1.2 채널 컨셉
- 니치: 신기한 물건 / 아이디어 상품 / 테크 가젯 큐레이션
- 페르소나: "미래에서 온 화자"가 현재인에게 신문물을 소개하는 세계관 (채널명은 config 변수로 관리, 미확정)
- 포맷: 45~59초 세로 쇼츠, 단어 팝업 자막, 빠른 템포 나레이션, 상품 이미지 줌인 오버레이

### 1.3 KPI (초기 3개월)
- 산출량: 주 5편 이상 자동 생산
- 파이프라인 안정성: 렌더 성공률 95% 이상
- 수익 선행지표: 영상당 링크 클릭수, 쿠팡 파트너스 클릭→구매 전환율
- 손익분기: §9 참조

---

## 2. 원안(첨부 기획서) 대비 변경 사항 — 필독

| # | 원안 | 변경 | 사유 |
|---|------|------|------|
| 1 | 경쟁 영상 원본 스크립트 추출 → LLM 재작성 | **상품 데이터 기반 오리지널 대본 생성** | 타인 대본의 재작성물은 저작권법상 2차적저작물 → Content ID·스트라이크 시 수익화 자체 붕괴. 상품 스펙 기반 생성이 품질 통제·일관성에서도 우위 |
| 2 | 마인크래프트 파쿠르·GTA 등 타인 게임플레이 배경영상 | **CC0 스톡(Pexels/Pixabay) 또는 자체 생성 에셋** | 타인이 녹화한 게임플레이는 녹화자 저작물. CC0 화이트리스트 원칙으로 일원화 |
| 3 | BeautifulSoup/Selenium 크롤링 | **YouTube Data API v3** | 스크래핑은 유튜브 ToS 위반. API 무료 쿼터(일 10,000유닛)로 리서치 충분 |
| 유지 | 아웃라이어(돌연변이) 영상 벤치마킹 | 유지 — 단 **소재(제품·주제) 발굴 목적으로만** 사용, 대본 추출 금지 | 무엇이 터지는지 관측은 합법·유효 |
| 유지 | 훅 3초, 루프 구조, 도발 질문, 단어 팝업 자막, 쉐이크 | 전부 유지 | 포맷·연출 기법은 저작권 대상 아님. 이것이 진짜 카피 대상 |
| 추가 | (없음) | **공정위 고지 문구 자동 삽입** | §3.1, 표시광고법 의무 |

---

## 3. 준수 가드레일 (모든 산출물 공통)

### 3.1 제휴 고지 (필수)
- 근거: 표시·광고의 공정화에 관한 법률 + 공정거래위원회 「추천·보증 등에 관한 표시·광고 심사지침」 + 쿠팡 파트너스 운영정책
- 문구(고정): `이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다`
- 삽입 위치: ① 영상 설명란 **최상단 첫 줄** ② 고정 댓글 링크 바로 옆 — 업로드 모듈(M7)에서 코드로 강제, 누락 시 업로드 중단(assert)

### 3.2 에셋 라이선스 화이트리스트
- 허용: CC0(Pexels·Pixabay 스톡), 자체 생성물(AI 생성 포함), 쿠팡 파트너스 API가 제공하는 상품 이미지(제휴 홍보 목적 범위 내 — 운영정책 재확인 필요, 확실하지 않음)
- 금지: 타 유튜브 영상의 클립·오디오·대본, 출처 불명 GIF, 스크래핑 이미지

### 3.3 대본 표현 규제
- 표시광고법 저촉 우려 표현 금지: "최고" "유일" "100% 효과" "질병 치료" 류 절대적·의학적 단정 표현
- 프롬프트(§7)에 금지어 규칙 내장 + 생성 후 금지어 필터 통과 필수

### 3.4 유튜브 정책 대응
- 2025년 7월 개정 YPP 수익화 정책: 대량생산·반복(inauthentic) 콘텐츠 제한 → 대응: 영상마다 고유 상품·고유 대본·고유 이미지 사용으로 반복성 회피 (본 설계는 구조적으로 충족)
- 링크 스팸 회피: 영상당 제휴 링크 1개(고정 댓글), 설명란 1개로 제한

---

## 4. 시스템 아키텍처

### 4.1 실행 환경 결정
- **런타임: GitHub Actions (ubuntu-latest)**
  - 근거: 사용자 환경 = iPad + 사내망 SSL 제약 → 로컬 렌더 불가. MoviePy/FFmpeg 렌더링은 Actions 러너에서 수행
  - 무료 한도: private repo 월 2,000분 (편당 렌더 ~5분 × 주 5편 = 월 100분 내외 → 여유 충분)
- 코드 관리: GitHub repo, Claude Code(웹/클라우드)로 개발
- 산출물 보관: Actions Artifacts(기본) + Cloudflare R2 백업(선택, Phase 3)

### 4.2 파이프라인 흐름

```
[M1 소재 리서치]──topics.json──┐
                               ▼
[M2 상품 데이터]──product.json──▶[M3 대본 생성]──script.json──▶[M4 TTS]──audio.mp3 + timestamps.json
                                                                              ▼
                                              [M7 업로드]◀──video.mp4──[M6 렌더링]
                                                   ▲
                                          (M5 타임스탬프는 M4 폴백 전용)
```

### 4.3 저장소 구조

```
coupang-shorts-factory/
├── CLAUDE.md                      # Claude Code용 프로젝트 컨텍스트 (본 문서 요약)
├── config/
│   ├── settings.yaml              # 채널명, 자막 스타일, 렌더 파라미터
│   ├── competitors.yaml           # 벤치마크 채널 ID 시드 리스트
│   └── prompts/script_gen.md      # §7 프롬프트 템플릿
├── src/
│   ├── research/outlier_finder.py # M1
│   ├── product/coupang_api.py     # M2 (HMAC 서명 포함)
│   ├── product/manual_queue.py    # M2 폴백 (CSV 큐)
│   ├── script/generate.py         # M3
│   ├── script/sanitize.py         # M3 금지어·특수기호 필터
│   ├── audio/tts.py               # M4
│   ├── audio/align_fallback.py    # M5
│   ├── video/render.py            # M6
│   ├── upload/youtube.py          # M7
│   └── pipeline.py                # M8 오케스트레이터
├── assets/
│   ├── fonts/GmarketSansBold.ttf  # 무료 폰트, 상업적 사용 허용
│   └── backgrounds/               # CC0 세로 배경영상 (라이선스 기록 licenses.csv 동봉)
├── data/
│   ├── products_manual.csv        # 수동 상품 큐 (Phase 1 입력)
│   └── jobs/{job_id}/             # 작업별 산출물 (json, mp3, mp4)
├── .github/workflows/produce.yml  # cron + 수동 트리거
└── requirements.txt
```

---

## 5. 모듈별 상세 스펙

### M1. 소재 리서치 (아웃라이어 탐지)
- 도구: YouTube Data API v3 (google-api-python-client)
- 로직:
  1. `competitors.yaml`의 채널별 업로드 재생목록에서 최근 30개 영상 조회 (`playlistItems.list` → `videos.list` 통계)
  2. 채널 최근 중앙값 조회수 대비 배수 = 아웃라이어 점수, **점수 ≥ 3.0** 필터
  3. 산출: `topics.json` — 영상 제목에서 추출한 제품 키워드·카테고리만 기록 (스크립트·오디오 추출 절대 금지)
- 쿼터: `search.list`(100유닛) 사용 금지, playlist 경유(1~2유닛/채널)로 절약 → 채널 20개 스캔 ≈ 60유닛
- 주기: 주 1회, 결과는 소재 후보 풀로 M2에 공급

### M2. 상품 데이터 확보 (쿠팡 파트너스)
- 1안: 쿠팡 파트너스 Open API
  - 인증: HMAC(Hash-based Message Authentication Code, 키 기반 요청 서명) 방식 — ACCESS_KEY/SECRET_KEY
  - 사용 엔드포인트: 상품 검색, 딥링크(제휴 추적 링크) 생성
  - **리스크: API 키 발급에 파트너스 실적 요건이 존재하는 것으로 알려짐 — 정확한 기준 확실하지 않음, 가입 후 콘솔에서 확인 필요**
- 2안(폴백, Phase 1 기본): 수동 큐 `products_manual.csv`
  - 컬럼: `product_name, price, key_specs(;구분), image_urls(;구분), affiliate_url, category`
  - 사용자가 파트너스 웹에서 링크 수동 생성 → CSV 1행 추가 → 파이프라인이 소비
- 산출 스키마 `product.json`:

```json
{
  "product_id": "job_20260711_001",
  "name": "접이식 무선 미니 세탁기",
  "price": 49900,
  "specs": ["3분 초고속 모드", "무게 1.2kg", "USB-C 충전"],
  "image_urls": ["https://..."],
  "affiliate_url": "https://link.coupang.com/...",
  "category": "생활가전"
}
```

### M3. 대본 생성
- 엔진: Anthropic API `claude-sonnet-4-6`
- 입력: `product.json` + §7 프롬프트 템플릿 → 출력: `script.json` (JSON only 강제)
- 후처리(`sanitize.py`): 특수기호·이모지 제거, §3.3 금지어 검사(실패 시 1회 재생성), 낭독 길이 검증(공백 제외 350~450자 = 약 40~55초)
- 출력 스키마:

```json
{
  "title": "혁신템 | 3분만에 빨래 끝내는 미니 세탁기",
  "lines": [
    {"text": "빨래를 3분 만에 끝낸다면 믿으시겠습니까", "image_cue": 0, "price_shock": false},
    {"text": "무게는 고작 1.2킬로그램", "image_cue": 1, "price_shock": false},
    {"text": "가격은 4만 9천 9백원", "image_cue": 1, "price_shock": true},
    {"text": "이래도 손빨래 하시겠습니까", "image_cue": 0, "price_shock": false}
  ],
  "hashtags": ["#채널브랜드", "#아이디어상품", "#자취꿀템"],
  "pinned_comment": "제품 정보는 여기서 확인 → {affiliate_url}\n이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다",
  "description_body": "상세 스펙 문단 + 파생 검색어 자연문"
}
```

- `image_cue`: 해당 라인 시작 시점에 오버레이할 상품 이미지 인덱스 / `price_shock`: 렌더 쉐이크 트리거

### M4. TTS(Text-to-Speech, 문자→음성 변환)
- **1안(권장): ElevenLabs `with-timestamps` 엔드포인트**
  - 오디오와 문자 단위 타임스탬프를 **한 번의 호출로 동시 반환** → 원안의 Whisper STT 단계 자체를 삭제 (비용·오류·처리시간 동시 절감)
  - 문자 타임스탬프 → 단어 경계로 병합하는 유틸 포함
  - 파라미터: 한국어 지원 보이스, 속도 1.1~1.15배(빠른 템포), 하이톤 계열 보이스 선택
  - 비용: Starter 약 $5/월 ≈ 오디오 30분 분량(대략치) → 월 40편(편당 45초=총 30분)이면 상한 근접, 초과 시 Creator 플랜
- 2안: Typecast — 한국어 특화, 에너지 있는 톤 다수 (가격·API 조건 확인 필요)
- 3안(저비용 폴백): Google Cloud TTS — 무료 티어 월 100만 자 수준(등급별 상이, 확인 필요)

### M5. 타임스탬프 폴백 (조건부)
- M4에서 타임스탬프 미제공 TTS 사용 시에만 활성화
- faster-whisper(오픈소스 Whisper 고속 구현)를 Actions 러너에서 직접 실행, `word_timestamps=True` → API 비용 0원
- 산출: `timestamps.json` — `[{"word": "빨래를", "start": 0.00, "end": 0.42}, ...]`

### M6. 영상 렌더링
- 라이브러리: **MoviePy 2.x** (버전 고정 필수)
  - 주의: 2.x에서 API 대격변 — `set_position → with_position`, `fontsize → font_size`, TextClip이 PIL 기반으로 변경되어 ImageMagick 불필요, **font 인자에 ttf 파일 경로 직접 지정 필수**(한글 깨짐 방지)
- 캔버스: 1080×1920(9:16), 30fps
- 레이어 구성(하→상):
  1. 배경: `assets/backgrounds/` CC0 세로영상 랜덤 선택, 오디오 길이에 맞춰 트림/루프
  2. 상품 이미지: `image_cue` 라인 시작 타임스탬프에 등장, 화면 상단 중앙, **줌인 1.00→1.08 선형 보간** (lambda 스케일 함수)
  3. 자막: 단어 단위 팝업 — GmarketSansBold, font_size 80, 색 `#FFE400`(노랑), stroke 검정 width 6, 위치 (center, y=1250)
  4. 쉐이크: `price_shock=true` 라인 구간 0.3초간 ±8px 랜덤 오프셋
  5. 오디오: TTS 트랙 (+선택: CC0 BGM -18dB)
- 인코딩: H.264, CRF 20, AAC 128k → `video.mp4`
- 목표 길이 45~59초 (쇼츠 상한은 3분이나 루프율 극대화 위해 60초 미만 유지)
- 성능: MoviePy 단어별 TextClip 루프는 느림 → **Phase 3 최적화 경로: ASS 자막 파일 생성 + FFmpeg 직접 번인(5~10배 단축)**. MVP는 개발속도 우선으로 MoviePy 유지

### M7. 유튜브 업로드
- 도구: YouTube Data API v3 `videos.insert`
- **핵심 제약 2가지 (설계에 반영)**
  1. 쿼터: 업로드 1건 = 1,600유닛, 기본 일일 쿼터 10,000유닛 → **일 최대 6편** (현재 계획 주 5편이므로 무관)
  2. **미인증(unverified) API 프로젝트로 업로드한 영상은 자동으로 비공개(private) 잠금** → 대응: 초기엔 private 업로드 + 사용자가 앱에서 공개 전환(반자동), 병행하여 Google API 감사(audit) 신청으로 완전 자동화 확보
- 메타데이터 자동 규칙:
  - 제목: `{타겟키워드} | {제품 요약}` — 키워드 풀: 혁신템, 자취꿀템, 삶의질템, 신박템 (config에서 로테이션)
  - 설명란: 1행 고지문(§3.1) → 스펙 요약 → 파생 검색어 자연문 → 제휴 링크
  - 해시태그: 브랜드 1 + 카테고리 2 (총 3개 고정)
  - `madeForKids=false`, 카테고리 28(과학기술)
- 고정 댓글: `commentThreads.insert`로 `pinned_comment` 자동 등록 (링크 + 고지문 세트)
- 멀티플랫폼(인스타 릴스·틱톡): Phase 3 — 인스타는 Graph API 릴스 게시 지원, 틱톡은 승인 절차 필요 → 초기 수동 업로드

### M8. 오케스트레이션
- `pipeline.py`: M2→M3→M4→(M5)→M6→M7 순차 실행, 단계별 산출물을 `data/jobs/{job_id}/`에 저장, 실패 시 해당 단계에서 중단 + Artifacts 업로드(디버깅용)
- GitHub Actions `produce.yml`:
  - 트리거: `workflow_dispatch`(수동) + `schedule` cron 주 5회 (Phase 3에서 활성화)
  - Secrets: `ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN`
- OAuth 부트스트랩: 유튜브 refresh token 1회 발급 필요 → **iPad 제약 대응: Google Colab에서 1회성 OAuth 스크립트 실행**으로 토큰 확보 후 Secrets 등록

---

## 6. 데이터 계약 (job 폴더)

```
data/jobs/job_20260711_001/
├── product.json      # M2 산출
├── script.json       # M3 산출
├── audio.mp3         # M4 산출
├── timestamps.json   # M4 또는 M5 산출
├── video.mp4         # M6 산출
└── upload_result.json # M7 산출 (videoId, url, status)
```

---

## 7. 대본 생성 프롬프트 템플릿 (config/prompts/script_gen.md)

```
당신은 쇼츠 채널 "{channel_name}"의 전속 대본 작가다
페르소나: 미래에서 온 화자가 2026년 사람들에게 "이 시대에 벌써 이런 게 있다니"라는 톤으로 신문물을 소개한다

입력으로 상품 데이터 JSON이 주어진다
출력은 아래 스키마의 JSON만 반환한다. 다른 텍스트, 마크다운 백틱 절대 금지

작성 규칙
1 훅(첫 라인): 소리내어 3초 내 낭독 가능(15자 내외), 다음 중 택1 — 상식파괴형("빨래가 3분 컷?") / 가격반전형 / 의문형
2 본문: 셀링포인트 2~3개, 라인당 20자 내외 구어체, 스펙은 반드시 숫자로 말한다
3 가격 라인: 반드시 1개 포함하고 해당 라인에 "price_shock": true
4 루프 설계: 마지막 라인의 어미가 첫 라인의 주어로 자연스럽게 이어지도록 작성 (무한 반복 시청 유도)
5 마지막 직전 라인: 시청자의 가치 판단을 묻는 질문 1개 (댓글 유도, 예: "이 가격이면 사시겠습니까")
6 금지: 절대적 표현(최고, 유일, 100프로), 의학적 효능 단정, 특수기호, 이모지, 영어 남용
7 전체 낭독 분량: 공백 제외 350~450자 (40~55초)
8 image_cue: 각 라인에 어울리는 상품 이미지 인덱스(0부터) 지정

출력 스키마
{"title": "...", "lines": [{"text": "...", "image_cue": 0, "price_shock": false}], "hashtags": ["...", "...", "..."], "pinned_comment": "...", "description_body": "..."}
```

---

## 8. 개발 로드맵

### Phase 0 — 렌더 스파이크 (1일)
- 범위: 하드코딩 대본 1건으로 M4+M6만 검증
- 작업: repo 생성 → 폰트·배경 1개 커밋 → TTS 1회 → MoviePy 렌더 → Actions Artifacts로 mp4 다운로드
- DoD: 한글 자막 정상 표시, 자막-음성 싱크 체감 오차 없음, 렌더 시간 측정 기록

### Phase 1 — 반자동 MVP (1주)
- 범위: M2(수동 CSV) + M3 + M4 + M6 + M7(private 업로드)
- DoD: CSV 1행 추가 → 무개입으로 private 영상 업로드 완료, 설명란 1행에 고지문 존재, 고정 댓글 자동 등록
- 이 시점부터 실운영 시작 가능 (공개 전환만 수동)

### Phase 2 — 데이터 연동 (2주차)
- 범위: M1 아웃라이어 리서치 주간 리포트 + M2 쿠팡 API 연동(승인 시) + 금지어 필터 강화
- DoD: 주간 소재 후보 10건 자동 리포트, API 딥링크 자동 생성 성공(또는 폴백 유지 결정)

### Phase 3 — 전자동·최적화 (3~4주차)
- 범위: cron 주 5회 가동, 실패 알림(텔레그램 봇 또는 이메일), FFmpeg+ASS 렌더 최적화, YouTube 감사 신청, 릴스 확장, R2 백업
- DoD: 2주 연속 무개입 가동률 90% 이상

---

## 9. 비용·수익 구조 (월 40편 기준)

| 항목 | 월 비용 | 비고 |
|------|---------|------|
| Claude API (대본 40건) | ~$1 | 건당 입력 1k+출력 1k 토큰 수준 |
| ElevenLabs Starter | $5 | 30분 상한 근접, 초과 시 $22 플랜 |
| Whisper | $0 | with-timestamps 채택으로 단계 삭제 |
| GitHub Actions | $0 | 무료 한도 내 (월 ~200분 사용) |
| YouTube/쿠팡 API | $0 | 무료 |
| **합계** | **$6~23** | 원화 약 8천~3만원 |

- 수익 측: 쿠팡 파트너스 수수료율은 카테고리별 상이(대략 1~10% 구간, 정확 수치 확인 필요), 24시간 쿠키 어트리뷰션(클릭 후 24시간 내 구매 귀속)
- 손익분기 시나리오: 평균 수수료 3%·객단가 3만원 가정 시 구매 1건 ≈ 900원 → 월 비용 회수에 구매 10~30건 필요
- **냉정한 전망: 쇼츠 UI에서 링크 동선은 고정 댓글 의존 → 클릭 전환율 낮음. 초기 3개월 수익 미미 가능성 높음, 볼륨(편수)과 소재 적중률 싸움임을 전제할 것**

---

## 10. 리스크 매트릭스

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| YouTube API 미인증 private 잠금 | 확정(초기) | 중 | 반자동 공개 전환 + 감사 신청 병행 |
| 쿠팡 API 승인 요건 미충족 | 중 | 저 | 수동 CSV 폴백으로 전 기능 동작 |
| YPP 대량생산 정책에 의한 노출 저하 | 중 | 중 | 영상별 고유 상품·대본·훅으로 반복성 회피, 성과 데이터로 소재 다변화 |
| 쿠팡 파트너스 계정 제재(고지 누락 등) | 저 | 상 | 고지문 코드 강제(assert), 자가구매 금지 준수 |
| ElevenLabs 비용 초과 | 중 | 저 | Google TTS 폴백 스위치 config화 |
| MoviePy 렌더 지연/불안정 | 중 | 중 | Phase 3 FFmpeg+ASS 전환 |

---

## 11. Claude Code 첫 세션 체크리스트

1. GitHub repo `coupang-shorts-factory` 생성, §4.3 구조 스캐폴딩
2. `CLAUDE.md` 작성 (본 문서 §0, §3 요약 수록)
3. GmarketSansBold.ttf 다운로드·커밋, Pexels에서 세로 CC0 배경 2개 확보 (`licenses.csv`에 출처 기록)
4. `requirements.txt`: moviepy(2.x 고정), google-api-python-client, google-auth-oauthlib, anthropic, requests, faster-whisper(폴백), pyyaml
5. Secrets 등록 안내를 사용자에게 출력 (사용자가 GitHub UI에서 직접 등록)
6. Phase 0 실행 → 렌더 결과 검수 요청

---

*변경 이력: v1.0 초안 — 원안 기획서 3개 항목 대체(§2), 나머지 골격 계승*
