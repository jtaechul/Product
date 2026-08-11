# 콘텐츠 파이프라인 — 문항 저작 · 검수 · 음원 제작

> 원칙: **콘텐츠 제작은 전부 개발 단계의 1회성 배치 작업**이다. 운영(서비스) 중에는 LLM·TTS를
> 단 한 번도 호출하지 않는다 — 학생이 받는 것은 D1의 문항 데이터와 R2의 정적 MP3뿐이다.
> 상위 문서: [PRD.md](../PRD.md) · 스키마: [ERD.md](ERD.md)

## 1. 파이프라인 개요

```
[저작]   Claude Code로 파트별 문항 배치 생성 (개발 단계 · 구독 요금 내 · 1회성)
   ↓     content/questions/*.json  (아래 2절 스키마, status: draft)
[검수]   사람이 전 문항 검토 (4절 체크리스트) → 통과 문항만 active 승격
   ↓
[TTS]    LC 스크립트 → 배치 TTS (미·영·호 보이스, 5절) → MP3 생성 (1회성)
   ↓
[업로드] tools/tts-batch.mjs 산출물 → R2 업로드 (6절 레이아웃)
   ↓
[임포트] tools/import.mjs → JSON 검증 → D1 INSERT/UPSERT (7절)
```

- ⚠️ **저작권 절대 규칙**: 실제 기출문제·공식 교재·시중 문제집의 문장을 복제·번안하지 않는다.
  시험의 *형식·유형·난이도 감각*만 참고해 소재부터 100% 새로 창작한다.
- 어휘 수준: **초3~중3** (CEFR Pre-A1~A2 중심, 파트 후반 B1 일부) — 주니어(초3~4)도 소화할
  쉬운 문항을 충분히 확보한다.

## 2. 저작 JSON 스키마 (`content/questions/*.json`)

파일 하나에 문항 객체 배열. 두 형태를 지원한다.

### 2-1. 단독 문항형 (`type: "single"`) — L1 · L2 · R1 · R3(단문)

```json
{
  "type": "single",
  "tmp_id": "R1-0001",
  "section": "RC",
  "part": "R1",
  "stem": "The students ______ their homework before dinner every day.",
  "choices": ["finish", "finishes", "finishing", "to finish"],
  "answer_idx": 0,
  "explanation_ko": "students는 여럿이라 뒤에 s 없는 finish를 써요. every day는 늘 하는 일이라는 뜻이에요.",
  "evidence": "The students",
  "difficulty_label": 2,
  "tags": ["G.agreement", "G.tense"],
  "accent": null,
  "tts_script": null
}
```

- LC 단독 문항(L1·L2)은 `tts_script`(성우가 읽을 텍스트)와 `accent`를 필수로 채운다.
  L1은 `image_prompt`(4컷 그림 생성용 설명) 필드를 추가로 갖는다.

### 2-2. 지문 묶음형 (`type: "set"`) — L3 · L4 · R2 · R3(장문)

```json
{
  "type": "set",
  "tmp_id": "L3-0001",
  "section": "LC",
  "part": "L3",
  "passage": {
    "kind": "dialogue",
    "script": "W: Did you watch the soccer game last night?\nM: No, I fell asleep early. Who won?\nW: Our city team! They scored in the last minute.",
    "accent": "UK",
    "tts_voices": { "W": "female", "M": "male" }
  },
  "questions": [
    {
      "stem": "What are the speakers talking about?",
      "choices": ["A soccer game", "A school test", "A new movie", "A music concert"],
      "answer_idx": 0,
      "explanation_ko": "여자가 어젯밤 축구 경기 이야기를 꺼내고, 끝까지 그 경기 이야기예요.",
      "evidence": "Did you watch the soccer game last night?",
      "difficulty_label": 2,
      "tags": ["LS.gist"]
    },
    {
      "stem": "Why did the man miss the game?",
      "choices": ["He fell asleep", "He studied late", "He was traveling", "He lost his ticket"],
      "answer_idx": 0,
      "explanation_ko": "남자가 일찍 잠들었다고 직접 말해요. 들은 내용을 그대로 고르면 돼요.",
      "evidence": "I fell asleep early",
      "difficulty_label": 3,
      "tags": ["LS.detail"]
    }
  ]
}
```

### 2-3. 공통 규칙

| 필드 | 규칙 |
|---|---|
| `tmp_id` | 저작 단계 식별자 `{파트}-{4자리}`. 임포트 시 ULID로 치환되고 tmp_id는 매핑 로그에 보존 |
| `choices` | **파트별로 개수 고정 (실제 시험 규격)** — L2(질의응답)만 **3개(A~C)**, 나머지 파트는 **4개(A~D)**. `import.mjs`가 어긋나면 임포트를 막는다 |
| `answer_idx` | 0-기반. **정답 분포는 파일 단위로 균등**하게 (한 보기 쏠림 금지, 임포트가 검사) |
| `explanation_ko` | 한국어, 초등 고학년이 그대로 읽고 이해할 문장. "왜 정답인지 + 오답 함정 1개" 구조 권장. **100자 이하**, 문법 용어(주어·동사·3인칭·비교급 등) 금지 — 실제 영어 낱말과 쉬운 우리말로 풀어 쓴다. `import.mjs`가 어려운 용어를 발견하면 임포트를 막는다 |
| `evidence` | 정답의 근거가 되는 **원문 그대로의 한 부분**(지문·스크립트·문제 문장). 화면이 그 자리를 형광펜으로 칠해 준다. 한 글자라도 다르면 임포트가 막는다. 채점 후에만 학생에게 내려간다 |
| `why_not` | 오답 보기마다 "왜 아닌지" 한 줄. `{"0": "...", "2": "..."}` — 정답 자리는 넣을 수 없다(임포트가 막음). **40자 이하**, 문법 용어 금지. 아이가 **실제로 고른 보기 하나만** 화면에 뜬다 |
| `miss_type` | **오답 자리마다 실수 유형 딱지 1개** (`why_not`과 같은 보기번호에 짝으로). 이유 문장은 읽을 수만 있고 셀 수 없다 — 딱지가 있어야 "이 아이가 이 실수를 몇 번 했나"를 센다. 13종은 `tools/import.mjs`의 `MISS_TYPES` 참조. 짝이 안 맞으면 임포트가 막는다 |
| `key_expr` | 이 문제에서 챙길 표현 1개. `{"en": "at noon", "ko": "낮 12시에"}` — `ko`는 30자 이하. 틀리면 '표현 주머니'에 담기고, 그 문제를 다시 맞히면 빠진다 |
| `difficulty_label` | 1~5. 시드 목표 분포: 1:15% / 2:30% / 3:35% / 4:15% / 5:5% (저학년 포함으로 쉬운 문항 확충) |
| `tags` | 3절 카탈로그의 code만 사용 (임포트가 검증). 문항당 1~3개 |
| `accent` | LC만: US/UK/AU. 시드 전체에서 US 50% / UK 25% / AU 25% 안팎 유지 |

## 3. 개념 태그 카탈로그 초안 (29개)

파트 자체는 `questions.part` 컬럼이 담당하므로, 태그는 **개념·스킬**만 표현한다.
`exam_weight`는 관련 파트 문항 수 비중에서 도출해 임포트 시드에 포함한다.

| 분류 | code | 이름 |
|---|---|---|
| 섹션(의사 태그) | `SEC.LC` / `SEC.RC` | 듣기 전체 / 읽기 전체 — 수축 블렌드·진단용 ([engine.md](engine.md)) |
| 문법 (RC 중심) | `G.tense` | 시제 |
| | `G.agreement` | 주어-동사 수일치 |
| | `G.pos` | 품사 자리 (형용사/부사/명사) |
| | `G.prep` | 전치사 |
| | `G.conj` | 접속사·연결어 |
| | `G.pronoun` | 대명사 |
| | `G.modal` | 조동사 |
| | `G.compare` | 비교 표현 |
| | `G.toinf` | to부정사·동명사 |
| | `G.passive` | 수동태 기초 |
| 어휘 | `V.daily` | 일상생활 |
| | `V.school` | 학교·수업 |
| | `V.travel` | 여행·교통 |
| | `V.food` | 음식·주문 |
| | `V.shopping` | 쇼핑·가격 |
| | `V.work` | 직장·업무 기초 |
| | `V.leisure` | 취미·여가·스포츠 |
| 듣기 스킬 | `LS.photo` | 사진 상황 파악 |
| | `LS.qr` | 질문 의도 파악 (의문사) |
| | `LS.detail` | 세부 정보 듣기 (시간·장소·숫자) |
| | `LS.gist` | 주제·목적 파악 |
| | `LS.infer` | 화자 의도 추론 |
| | `LS.accent` | 발음 변형 적응 (미·영·호) |
| 독해 스킬 | `RS.scan` | 정보 찾기 (공지·문자·메뉴) |
| | `RS.gist` | 글의 목적·주제 |
| | `RS.context` | 문맥 완성 (연결어·문장 선택) |
| | `RS.vocab` | 문맥 속 어휘 의미 |
| | `RS.infer` | 추론 (다음 행동·화자 관계) |

## 4. 검수 워크플로

- 상태 흐름: `draft`(임포트 직후) → **사람 검수** → `active`(출제 대상) / 폐기는 `retired`.
- 운영 중 오류 발견 시 즉시 `retired` 처리(세트 생성에서 제외됨) 후 수정본을 새 문항으로 등록.
- **검수 체크리스트** (문항당):
  1. 정답이 유일한가? (다른 보기가 정답이 될 여지 없음)
  2. 해설이 정확하고 초등 눈높이인가?
  3. 어휘·소재가 연령에 적합한가? (폭력·상표·시사 민감 소재 배제)
  4. **기출 유사성 자가점검** — 특정 기출·교재 문장이 연상되면 폐기 후 재작성
  5. LC: 스크립트가 자연스러운 구어인가, 성우 배정(남/녀)·국가가 표기됐는가
  6. 정답 위치 쏠림 없는가 (파일 단위 분포는 임포트가 자동 검사)

## 5. 배치 TTS (음원 제작 — 1회성)

### 5-1. 제공자 비교

| 옵션 | 비용 | 판단 |
|---|---|---|
| **Google Cloud TTS** | 뉴럴 보이스 월 100만 자 무료 쿼터 — 시드 규모(수만 자)는 **0원**, 대량 확장 시에도 월 쿼터 내 분할 배치로 0원 유지 가능 | **채택 확정 (2026-08-08)** |
| Amazon Polly (예비) | 뉴럴 약 $16/100만 자, 1회성 소액 | 일괄 대량 생성이 급할 때 |
| edge-tts (비상용) | 무료지만 약관 회색지대 | **상용 배포 전 제외 권고** — 프로토타입 실험까지만 |

어느 경우든 생성은 개발 단계 1회 → MP3는 R2에 영구 보관 → **운영 중 TTS 호출 0회**.

### 5-2. 보이스 매핑 (Google 기준 초안)

| 국가 | 남성 | 여성 |
|---|---|---|
| US | `en-US-Neural2-A` | `en-US-Neural2-C` |
| UK | `en-GB-Neural2-B` | `en-GB-Neural2-A` |
| AU | `en-AU-Neural2-B` | `en-AU-Neural2-A` |

- 말속도: 초등 청취를 고려해 **기본 대비 −5%** (SSML `rate="95%"`), M3에서 실사용 피드백으로 조정.
  음원은 **한 벌만** 제작하고, 주니어(초3~4) 그룹은 플레이어의 0.9배속 "천천히 듣기" 옵션으로
  대응한다(그룹별 음원 이중 제작·저장 없음).
- 대화(L3)는 화자별 보이스 분리 합성 후 무음 0.6초 이어붙임(`tts_voices` 매핑 사용).
- L2(질의응답)는 질문+4개 보기 응답을 하나의 트랙으로 합성(실전 형식).
- 파일 검수: 생성 후 전수 청취는 시드 120문항 규모에서 1~2시간 — 필수로 수행.

## 6. R2 레이아웃

```
r2://jtm-assets/
├── audio/passages/{passage_id}.mp3     # L3·L4 묶음 음원
├── audio/questions/{question_id}.mp3   # L1·L2 단독 음원
└── images/{question_id}.webp           # L1 사진 4컷 등
```

- 공개 읽기 + `Cache-Control: public, max-age=31536000, immutable` (파일은 불변 — 수정 시 새 ID).
- 클라이언트가 R2 공개 URL을 직접 fetch (Worker 경유 없음 — 서버 부하 분산, R2 이그레스 무료).
- 파일명이 ID라 정답 유추 불가(내용 정보 없음).

## 7. 임포트 도구 (`tools/import.mjs` — M1 구현)

- 입력: `content/questions/*.json` (+ `content/tags.json`, `content/badges.json` 시드)
- 검증(실패 시 임포트 중단, 파일·tmp_id 단위 리포트):
  스키마 필수 필드 / `tags` 코드가 카탈로그에 존재 / `answer_idx` 범위 / 파일 단위 정답 분포
  (한 보기 40% 초과 시 경고) / LC 문항의 `tts_script`·`accent` 존재 / 묶음형 part 정합 /
  **해설 난이도**(문법 용어 사용·100자 초과 차단) / **근거 정합**(`evidence`가 원문에 그대로 있는지) /
  **오답 이유**(`why_not` 보기번호 범위·정답 자리 금지·40자·용어) / **실수 유형**(`miss_type`이
  `why_not`과 짝이 맞는지·등록된 13종인지) / **표현 카드**(`key_expr` 형식·30자)

> 실수 유형은 답안에 따로 저장하지 않는다. `answers.chosen_idx`와 문항의 `miss_type`을
> 조인하면 학생별 집계가 나오므로(아래 쿼리), **딱지를 나중에 붙여도 지난 답안까지 소급 분석된다.**
> ```sql
> SELECT json_extract(q.miss_type, '$."' || a.chosen_idx || '"') AS miss, COUNT(*)
>   FROM answers a JOIN questions q ON q.id = a.question_id
>  WHERE a.user_id = ?1 AND a.is_correct = 0 GROUP BY 1 ORDER BY 2 DESC;
> ```
- 변환: `tmp_id` → ULID 발급(매핑을 `content/.idmap.json`에 보존 — 재실행 시 같은 ULID 재사용
  → **멱등 UPSERT**), `difficulty_label` → 초기 `rating` 매핑([engine.md](engine.md) 상수표)

> ⭐ **문항을 추가하면 `.idmap.json`도 같은 커밋에 넣는다** (`node tools/import.mjs` 실행 후 커밋).
> 음원·사진 파일 이름이 이 ULID에서 나오는데, 매핑이 커밋돼 있지 않으면 러너에서 처음 발급된다.
> 2026-08-11에 L1 12문항을 매핑 없이 올렸다가, 음원 워크플로와 사진 워크플로가 **같은 문항에
> 서로 다른 ULID를 붙여** 받아 둔 사진 48컷이 문항과 짝을 잃을 뻔했다.
> 지금은 두 워크플로가 `Check ID map is committed` 단계에서 이 상황을 먼저 잡아 멈춘다.
- 출력: `wrangler d1 execute <DB> --file` 로 실행할 SQL 파일 생성 (로컬 `--local` 우선 검증 후 원격 적용)
- 태그·뱃지 카탈로그도 같은 도구로 시드한다 (마이그레이션과 분리 — [ERD.md](ERD.md)).

## 8. M1 시드 목표 — 120문항

실제 시험 비중(LC 6/20/10/14, RC 15/15/20)을 1.2배 스케일한 배분:

| 파트 | 형태 | 문항 수 | 구성 |
|---|---|---|---|
| L1 사진 고르기 | 단독 | 8 | 이미지 4컷 + 음원 |
| L2 질의응답 | 단독 | 24 | 음원 |
| L3 짧은 대화 | 묶음 | 12 | 대화 6개 × 2문항 |
| L4 짧은 담화 | 묶음 | 16 | 담화 8개 × 2문항 |
| R1 문장 완성 | 단독 | 18 | — |
| R2 지문 완성 | 묶음 | 18 | 지문 6개 × 3문항 |
| R3 독해 | 단독·묶음 | 24 | 단문 12 + 세트 6개 × 2문항 |
| **계** | | **120** | LC 60 · RC 60 |

- 난이도 분포: 라벨 1:15% / 2:30% / 3:35% / 4:15% / 5:5% — 기본 그룹 진단(라벨 2~4)과
  주니어 그룹 진단(라벨 1~3), 초기 세트 생성이 모두 돌아가는 최소 구성.
- 발음 분포: US 50% / UK 25% / AU 25% 안팎.
- 이후 확장 목표: M3까지 400문항, 정식 오픈 전 1,000문항+ (같은 파이프라인 반복).

### 8-1. 현재 문항 수와 '며칠 버티는가' (2026-08-11 실측)

| 파트 | 문항 수 | 매체 |
|---|---|---|
| L1 사진 고르기 | 20 | 사진 4컷 80장 + 음원 |
| L2 질의응답 | 60 | 음원 |
| L3 짧은 대화 | 29 (대화 14개) | 음원 |
| L4 짧은 담화 | 32 (담화 16개) | 음원 |
| R1 문장 완성 | 58 | — |
| R2 지문 완성 | 60 (지문 20개) | — |
| R3 독해 | 61 (지문 36개) | — |
| **계** | **320** | 음원 110개 · 사진 80장, 전부 active |

**문항을 얼마나 더 만들지는 감이 아니라 이 숫자로 정한다.** `node tools/simulate-fortnight.mjs
<일수> <세트크기>` 가 실제 엔진(`composeDailySet`)을 그대로 돌려 하루씩 앞으로 감으며,
매일 세트를 정원만큼 채우는지와 14일 무반복이 지켜지는지를 센다.

| 반 | 120문항 시절 | 285문항 | **320문항 (현재)** |
|---|---|---|---|
| 12문항 반 (초3~4 주니어) | 약 10일 | 120일+ | **120일+ 이상 없음** |
| 20문항 반 (초5~중3 기본) | 6일 | 23일부터 부족 | **120일+ 이상 없음** |

> 계산법: 하루 N문항 × 14일 무반복이면 파트마다 `그 파트의 하루 배정 × 14`개가 필요하다.
> 20문항 반에서 R2·R3·L4가 먼저 바닥났던 이유이고, 그래서 그 파트부터 채웠다.
