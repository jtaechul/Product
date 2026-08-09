# 점프리시 (Jumplish)

> 저장소 코드네임: `junior-toeic-master` (폴더명·내부 문서용 — 브랜드명과 별개로 유지)

영어학원(B2B) 대상 **TOEIC Bridge 기반 초·중등(초3~중3) 맞춤형 영어 학습 플랫폼**입니다.
학생은 진단 테스트를 받고, 매일 자기 약점에 맞춘 문제 세트를 풀고, 틀린 문제를
자동 복습 일정(SRS)으로 다시 만납니다. 선생님은 반 전체의 진도·정답률·취약 파트를
대시보드에서 확인하고 과제를 배포합니다.

다른 프로젝트와 섞이지 않도록 저장소 내 전용 폴더(`junior-toeic-master/`)에서만
개발합니다 (프로젝트 격리 원칙).

## 핵심 컨셉

- **진단 → 오늘의 맞춤 학습 → 오답 복습**의 학습 루프를 자동화
- **운영 중 외부 API 호출 0회**: LLM·실시간 TTS를 쓰지 않음. 문제와 듣기 음원(미·영·호 발음)은
  개발 단계에 배치로 미리 제작해 정적 파일로 서빙 → 학생이 늘어나도 API 비용이 0원
- 추천은 자체 **규칙 기반 엔진**(Elo-lite 실력 추정 + 라이트너 SRS 복습)으로 계산
- 정답·해설은 서버에만 존재 — 문제 데이터에 정답을 실어 보내지 않아 치팅 차단

## 기술 스택

- **Cloudflare Workers** (Hono 라우터) — API·채점·추천 연산
- **Cloudflare D1** (SQLite, 관계형) — 이 저장소의 **첫 D1 사용 프로젝트**. 표준 SQL만 사용해
  추후 PostgreSQL 이전 가능
- **Cloudflare R2** — 듣기 음원(MP3)·이미지 정적 서빙 (클라이언트 직접 fetch)
- **프론트엔드** — 무빌드 바닐라 ES 모듈 SPA, Workers `[assets]` 바인딩으로 서빙 (모바일 우선)

## 문서 안내

| 문서 | 내용 |
|---|---|
| [PRD.md](PRD.md) | 보완 기획서 v2 — 제품 정의·기능 명세·API·리스크·로드맵 (마스터 문서) |
| [docs/ERD.md](docs/ERD.md) | DB 설계 — 테이블 18개 DDL, 인덱스, 데이터 보존 정책 |
| [docs/engine.md](docs/engine.md) | 추천·실력 추정 엔진 — 수식, 상수표, 의사코드 |
| [docs/content-pipeline.md](docs/content-pipeline.md) | 문항 저작 JSON 스키마, 검수 절차, 배치 TTS 음원 제작 |

## 현재 단계

- **M0 (완료)**: 기획 보완 문서 패키지
- **M1 (완료)**: Workers(Hono)+D1 스캐폴드, 문항 열람·풀어보기 웹, 콘텐츠 도구,
  **시드 120문항 + 듣기 음원 46개(실전 간격) + L1 흑백 선화 그림 32컷** 전부 탑재
- **M2 (완료)**: 학생 코어 루프 — 로그인(학원ID+PIN) → 2단계 적응형 진단 →
  서버 개인화 오늘의 학습(복습+약점+신규 슬롯) → 오답 SRS(1·3·7·14일) → 선택 확정·효과음
- **M3 (진행 중)**: 게임화 "점프 원정대" — 리매치 봉인 · 등반 지도+베이스캠프 · 개인 기록판
- 이후: M3 게이미피케이션 → M4 학원 대시보드 → M5 결제·베타 (상세: [PRD.md 11절](PRD.md#11-로드맵-m0m5))

## 배포 주소

- [점프리시 미리보기 열기](https://jumplish.jtaechul.workers.dev) — 지정 브랜치 push 시
  `.github/workflows/deploy-jumplish.yml`이 Cloudflare Workers로 자동 배포

## 실행 방법 (로컬 개발)

```
cd junior-toeic-master
npm install
npm run db:migrate:local   # 로컬 D1에 스키마 적용
npm run db:seed:local      # 문항 검증 + 시드 주입
npm run dev                # http://localhost:8787 접속
```

## 폴더 구조

```
junior-toeic-master/
├── wrangler.jsonc      # Workers 설정 (D1·assets 바인딩)
├── worker/             # API (Hono) + 엔진 상수
├── migrations/         # D1 스키마 (docs/ERD.md 기준)
├── public/             # 웹 (무빌드 ES 모듈, 모바일 우선)
├── content/            # 문제 은행 원본 JSON (태그·뱃지·문항 120)
├── tools/              # import.mjs(검증·시드) · tts-batch.mjs(음원 배치)
└── docs/               # ERD · 엔진 · 콘텐츠 파이프라인 · TTS 가이드
```

## 주의 (법률·정책)

> ⚠️ **"TOEIC"은 ETS의 등록상표입니다.** 서비스 브랜드명은 **점프리시(Jumplish)**로
> 확정했으며(공개 출시 전 KIPRIS 정식 상표 검색·도메인 확보 예정), "TOEIC Bridge 대비"는
> 상표적 사용이 아닌 설명 문구로만 씁니다.
> 실제 기출문제의 복제·전재는 금지 — 문항은 시험 *형식*만 참고해 100% 자체 창작합니다.
> 학생 개인정보는 스키마 차원에서 최소화(이메일·전화 컬럼 없음)합니다. 상세: [PRD.md 8절](PRD.md#8-법률정책-리스크)
