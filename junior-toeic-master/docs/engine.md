# 추천·실력 추정 엔진 설계 — Junior TOEIC Master

> **외부 API 호출 0회.** 아래 전부가 Cloudflare Worker 안에서 D1 쿼리 + 산수로 계산된다.
> 이 문서가 엔진의 단일 기준이며, 모든 상수는 2절 표에서만 관리한다(코드에서는 `src/engine/config.js`).
> 상위 문서: [PRD.md](../PRD.md) · 스키마: [ERD.md](ERD.md)

## 1. 개요

| 구성 요소 | 역할 | 방식 |
|---|---|---|
| 실력 추정 | 학생이 태그(개념)별로 얼마나 잘하는지 수치화 | Elo-lite 레이팅 |
| 오답 복습 | 틀린 문제를 잊을 때쯤 다시 출제 | 라이트너 SRS (박스 4단계) |
| 세트 생성 | 매일 "복습+약점+신규+유지" 조합 큐레이션 | 슬롯 규칙 + p-윈도우 샘플링 |
| 진단 | 최초 실력치 초기화 | 2단계 24문항, 대역 매핑 |
| 게임화 | XP·레벨·스트릭·뱃지 | 결정적 수식 (난수 없음) |

## 2. 상수표 (단일 출처)

| 상수 | 값 | 의미 |
|---|---|---|
| `RATING_INIT_BY_LABEL` | {1:900, 2:1050, 3:1200, 4:1350, 5:1500} | 난이도 라벨 → 문항 초기 레이팅 |
| `ELO_SCALE` | 400 | 로지스틱 스케일 (체스 Elo 동일) |
| `K_SCHEDULE` | 풀이 수 <20 → 32 / <50 → 24 / 이상 → 16 | 학생 레이팅 갱신 폭 (신규일수록 크게) |
| `SHRINK_PIVOT` | 8 | 태그 레이팅 수축 기준 풀이 수 |
| `GUESS_MS` | 2000 | 이 시간(ms) 미만 답변은 '찍기' 판정 |
| `GUESS_SKILL_DAMP` | 0.5 | 찍기 시 실력 갱신 감쇠 |
| `SRS_INTERVALS` | [1, 3, 7, 14] (일) | 라이트너 박스 1~4의 재출제 간격 |
| `DAILY_SLOTS_20` | 복습 6 / 약점 8 / 신규 4 / 유지 2 | 기본 세트(20문항) 구성 |
| `DAILY_SLOTS_12` | 복습 4 / 약점 5 / 신규 2 / 유지 1 | 초등 프리셋(12문항) 구성 |
| `P_WEAK` | [0.55, 0.75] | 약점 슬롯의 예상 정답률 샘플 구간 |
| `P_WEAK_RELAXED` | [0.45, 0.85] | 부족분 캐스케이드 시 완화 구간 |
| `P_KEEP` | ≥ 0.80 | 유지(자신감) 슬롯의 예상 정답률 |
| `NO_REPEAT_DAYS` | 14 | 최근 노출 문항 제외 기간 (복습 슬롯 예외) |
| `STALENESS_CAP` | 2.0 | 미학습 기간 가중 상한 |
| `SECTION_MIN_RATIO` | 0.30 | 세트 내 LC·RC 각각의 최소 비율 |
| `XP_CORRECT(label)` | 10 × (1 + 0.2 × (label−1)) → 10~18 | 정답 XP (난이도 비례) |
| `XP_WRONG` / `XP_GUESS` | 2 / 1 | 오답 XP / 찍기 XP |
| `XP_SET_BONUS` | 30 | 일일 세트 완주 보너스 |
| `LEVEL_XP(L)` | 100 × L^1.5 (누적) | 레벨 L 도달에 필요한 누적 XP |
| `STREAK_MIN_Q` | 10 | 세트 미완주여도 이 문항 수 이상이면 출석 인정 |
| `DIAG_STAGE_SIZE` | 기본 12 (×2단계 = 24) / **주니어 8 (×2단계 = 16)** | 진단 문항 수 — 학년 그룹별 |
| `DIAG_START_LABEL` | 기본 3 / **주니어 2** | 진단 1단계 시작 난이도 라벨 |
| `JUNIOR_PLAYBACK` | 0.9 | 주니어(초3~4) 듣기 "천천히 듣기" 재생 배속 (음원은 한 벌) |
| `DIAG_BANDS` | <40 / <55 / <70 / <85 / ≥85 (%) | 진단 정확도 대역 |
| `DIAG_BAND_RATING` | {950, 1075, 1200, 1325, 1450} | 대역 → 초기 레이팅 |
| `RECALIB_MIN_N` / `RECALIB_K` | 30 / 8 | 문항 레이팅 재보정 최소 표본 / 갱신 폭 |
| `RETENTION_MONTHS` | 3 | answers 원본 보존 개월 ([ERD.md](ERD.md)) |

시간 경계는 전부 **KST 자정** 기준(날짜 문자열 `YYYY-MM-DD`).

## 3. 실력 추정 (Elo-lite)

### 3-1. 기본 수식

문항 레이팅 `R_q`(저작 라벨로 초기화), 학생×태그 레이팅 `R_s`에 대해:

```
예상 정답률  p = 1 / (1 + 10^((R_q − R_s) / 400))
갱신        R_s ← R_s + K(n) × damp × (score − p)     # score: 정답 1, 오답 0
```

- `K(n)`: 해당 태그 풀이 수 n에 따라 32 → 24 → 16 (새 학생일수록 빨리 수렴, 이후 안정).
- `damp`: 찍기(time_ms < 2000)면 0.5, 아니면 1.0 — 연타 남용이 레이팅을 오염시키지 않게.
- 한 문항이 여러 태그를 가지면 **각 태그를 독립 갱신**하고, 섹션 의사 태그
  (`SEC.LC`/`SEC.RC`)도 항상 함께 갱신한다.

### 3-2. 콜드스타트 수축 (shrinkage)

태그별 풀이 수가 적을 때 개별 태그 레이팅은 소음이 크다. **판단(세트 생성·p 계산)에는
수축된 유효 레이팅**을 쓴다:

```
w = n / (n + SHRINK_PIVOT)            # n = 그 태그의 풀이 수
유효 R_s = w × R_tag + (1 − w) × R_section
```

- n=0이면 섹션 레이팅을 그대로 쓰고, 8문항쯤 풀면 절반씩, 그 후 태그 자체 값이 지배한다.
- 저장은 항상 원본 `R_tag`(user_tag_skills.rating), 수축은 읽을 때 계산.

### 3-3. 진단에 의한 초기화

- 진단 중에는 Elo 갱신을 하지 않는다(문항별 즉시 반영 없음).
- 진단 종료 시 파트별 정확도 → `DIAG_BANDS` 대역 → `DIAG_BAND_RATING`으로
  **결정적 매핑**(강사에게 설명 가능해야 하므로 확률 갱신 대신 고정 규칙):
  - 해당 파트에 속한 개념 태그들의 `R_tag` = 파트 대역 레이팅, `attempts` = 진단에서 그 파트가
    풀린 문항 수(2~4 — 수축 블렌드가 과신하지 않도록 소표본 그대로 기록)
  - `SEC.LC`/`SEC.RC` = 섹션 내 파트 대역 레이팅의 문항수 가중평균, `attempts` = 섹션 문항 수(기본 12·주니어 8)
- 리포트는 파트별 5등급(대역 그대로)만 노출 — 예측 점수 표시 금지.

## 4. 진단 테스트 설계 (기본 24문항 · 주니어 16문항)

학년 그룹은 반(classes) 설정으로 결정한다 — **기본(초5~중3)** / **주니어(초3~4)**.

### 기본 그룹 — 24문항 (12+12, 약 15분)

| | L1 | L2 | L3 | L4 | R1 | R2 | R3 | 계 |
|---|---|---|---|---|---|---|---|---|
| 1단계 (라벨 3 중심) | 1 | 2 | 2 | 2 | 2 | 1 | 2 | 12 |
| 2단계 (난이도 조정) | 1 | 2 | 2 | 2 | 2 | 1 | 2 | 12 |

### 주니어 그룹 — 16문항 (8+8, 약 10분, 라벨 2 시작)

| | L1 | L2 | L3 | L4 | R1 | R2 | R3 | 계 |
|---|---|---|---|---|---|---|---|---|
| 1단계 (라벨 2 중심) | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 8 |
| 2단계 (난이도 조정) | 1 | 2 | 1 | 1 | 2 | 0 | 1 | 8 |
| 합계 | 2 | 3 | 2 | 2 | 3 | 1 | 3 | 16 |

- 주니어는 표본이 작으므로 결과 화면의 파트별 등급에 **"참고용"** 문구를 병기한다.

### 공통 규칙

- 2단계 난이도: 1단계 **섹션 정답률** 기준 — 기본 그룹: ≥ 2/3 → 라벨 4, ≤ 1/3 → 라벨 2, 그 외
  → 라벨 3. 주니어 그룹: ≥ 2/3 → 라벨 3, ≤ 1/3 → 라벨 1, 그 외 → 라벨 2.
  (LC·RC 각각 독립 판정. 파트 단위는 표본 1~2개라 소음이 커서 쓰지 않는다.)
- 단계 사이에 격려 화면 1회. `sessions.question_ids` 스냅샷으로 중단 후 이어하기.
- 문항 선정: 파트·라벨 조건에 맞는 active 문항 중 무작위, 지문 묶음(L3·L4·R2)은 묶음에서
  필요한 수만큼만 사용해도 됨(진단은 예외적으로 묶음 분리 허용 — 배분 우선).

## 5. 오늘의 학습 세트 생성

### 5-1. 약점 점수 (태그 우선순위)

```
weakness(tag) = clamp((1600 − 유효R_s) / 700, 0, 1)     # 실력 부족분 정규화
              × exam_weight(tag)                         # 시험 출제 비중
              × min(1 + days_since_practiced / 14, 2)    # 오래 안 본 태그 가중 (상한 2)
```

### 5-2. 슬롯 규칙

| 슬롯 | 20문항 세트 (기본 그룹) | 12문항 세트 (주니어 기본) | 선정 기준 |
|---|---|---|---|
| 복습 | 6 | 4 | `review_queue`에서 due_at ≤ 오늘, 오래된 순 |
| **축 채우기** | **0~1** | **0~1** | 실력 지도 5축 중 시도 < 3인 축이 있으면 그 축 문항 1개 (쉬운 것부터) |
| 약점 | 8 | 5 | weakness 상위 3개 태그에서, 예상 정답률 0.55~0.75 문항 무작위 |
| 신규 | 4 | 2 | 풀이 수 < 3인 태그에서, 쉬운 난이도부터 (커버리지 확보) |
| 유지 | 2 | 1 | 최강 태그에서 예상 정답률 ≥ 0.8 (자신감·리듬) |

**축 채우기 슬롯 (2026-08-12 추가)** — 부모 화면의 "속뜻 알기"가 몇 주가 지나도 계속
'재는 중'으로만 남는다는 지적에서 나온 규칙이다. 원인은 코드가 아니라 **문항 분포**였다:
속뜻(`LS.infer`·`RS.infer`)은 전체의 7.8%뿐이라 하루 12문항 세트에 0.9문항꼴로만 들어가고,
측정 최소치 3문항을 채우는 데 중앙값 6일·최악 13일이 걸렸다. '신규' 슬롯이 이 역할을
하리라 봤지만 그쪽은 **쉬운 것부터** 담기 때문에 어려운 축일수록 뒤로 밀려 차례가 오지 않았다.
- 시도 < `AXIS_MIN_ATTEMPTS`(3)인 축 중 **시도가 가장 적은 축**, 같으면 **문항이 가장 적은 축**
  (첫날은 모든 축이 0이라 순서만 보면 늘 맨 앞 '듣고 알기'가 뽑히는데, 그 축은 문항이 많아
  가만둬도 채워지므로 한 자리가 아깝다)
- 그 축이 처음이니 **쉬운 것부터** — 첫 만남에서 연달아 틀리면 축이 실제보다 낮게 잡힌다
- **모자란 만큼(최대 3문항)을 그날 다 넣는다** (2026-08-23 강화). 처음엔 하루 1문항씩만
  줬는데, 그러면 이미 수십 문제를 푼 아이도 사흘을 더 기다려야 했다 — "30문제를 풀었으면
  평가가 되어야 정상 아니냐"는 지적이 맞았다. 이제 세트 하나만 끝내면 그 축은 당일 켜진다.
- 세 축 모두 3문항을 넘기면 이 슬롯은 사라지고 정원은 원래 배분으로 돌아간다
- 효과(`tools/simulate-axes.mjs`, 학생 30명·21일): 속뜻 알기가 켜지는 날
  중앙값 6일 → 3일(1문항씩) → **1일(모자란 만큼)**. 모든 축이 3일 안에 켜진다.

**⚠ 진단 씨딩 버그 (2026-08-23 수정)** — 속뜻이 안 켜진 진짜 첫 원인은 따로 있었다.
진단 채점이 태그별 시도 수에 **파트 전체 문항 수를 통째로 복사**했다(L3 4문항을 풀면
그중 속뜻 문항이 0개여도 L3에 걸린 모든 태그가 attempts=4). 부풀린 숫자 덕에 다른 축은
진단 직후 "측정 완료"가 되고, 진단에 안 나온 속뜻만 0으로 남아 대비가 도드라졌다.
지금은 태그별로 **그 태그가 실제로 붙은 문항 수만** 센다. (기존 계정의 부풀린 시도 수는
그대로 두었다 — 점수(레이팅)는 정상이었고, 시도 수는 풀수록 저절로 진실에 수렴한다.)

공통 제약:
- 슬롯 합계는 세트 정원을 넘지 않는다 — 축 채우기가 한 자리를 쓰면 뒤 슬롯이 그만큼 줄어든다
- 최근 14일 내 노출 문항 제외 (복습 슬롯 예외)
- 지문 묶음(L3·L4·R2·R3 세트)은 통째로 포함 — 총 문항 수 ±2 허용
- LC·RC 각각 최소 30% — 미달 시 다수 섹션 문항을 소수 섹션 후보로 교체
- 부족분 캐스케이드: 어느 슬롯이든 후보 부족 시 남은 슬롯을 약점 기준 완화 구간
  `P_WEAK_RELAXED`로 채우고, 그래도 부족하면 세트 크기를 줄여서라도 생성(빈 세트 금지)

### 5-3. 의사코드

```js
// GET /api/daily → 없으면 생성. UNIQUE(user_id, date)로 중복 생성 방지.
async function generateDailySet(userId, date) {
  const setSize = classSetSize(userId);              // 반 설정 (기본 그룹 20, 주니어 12)
  const slots   = setSize <= 12 ? DAILY_SLOTS_12 : DAILY_SLOTS_20;
  const picked  = [];

  // 1) 복습: 오늘까지 도래한 오답 큐 (오래된 순)
  picked.push(...dueReviews(userId, date, slots.review));

  // 2) 약점: weakness 상위 태그에서 p-윈도우 샘플
  const skills   = loadSkillsWithShrinkage(userId);          // user_tag_skills + SEC.*
  const weakTags = topTagsByWeakness(skills, 3);
  const recent   = recentQuestionIds(userId, NO_REPEAT_DAYS); // idx_answers_user_time
  picked.push(...sampleByP(weakTags, P_WEAK, slots.weak, { exclude: [recent, picked] }));

  // 3) 신규: 경험 적은 태그를 쉬운 문항부터
  picked.push(...sampleFresh(skills, slots.fresh, { exclude: [recent, picked] }));

  // 4) 유지: 최강 태그에서 쉬운 성공 경험
  picked.push(...sampleByP([strongestTag(skills)], [P_KEEP, 1.0], slots.keep,
                           { exclude: [recent, picked] }));

  // 5) 부족분 캐스케이드 → 6) 지문 묶음 통째 보정(±2) → 7) 섹션 비율 30% 보장
  fillShortfall(picked, setSize, P_WEAK_RELAXED);
  expandPassageGroups(picked);
  enforceSectionRatio(picked, SECTION_MIN_RATIO);

  return insertDailySet(userId, date, picked, slots);  // daily_sets + sessions(type='daily')
}
```

## 6. 오답 복습 SRS (라이트너)

```
오답 발생          → review_queue UPSERT: box=1, due=오늘+1일 (이미 있으면 box=1로 리셋)
정답 (어느 모드든) → 큐에 있고 미졸업이면: box<4 → box+1, due=오늘+간격[box]
                                         box=4 → graduated_at 기록 (졸업)
찍기 정답          → 박스 진급 없음 (due 유지)
간격               → 박스 1~4 = +1 / +3 / +7 / +14일, 날짜는 KST 기준
```

```js
function applySrs(userId, questionId, correct, isGuess, today) {
  const row = getQueueRow(userId, questionId);            // UNIQUE(user,question)
  if (!correct) return upsertQueue(row, { box: 1, due: addDays(today, 1) });
  if (!row || row.graduated_at || isGuess) return null;   // 큐 밖 정답·찍기는 무시
  if (row.box >= 4) return graduate(row, today);
  return upsertQueue(row, { box: row.box + 1, due: addDays(today, SRS_INTERVALS[row.box]) });
}
```

## 7. 채점 파이프라인 (`POST /api/answers`)

한 문항 채점은 **읽기 2문장 + 쓰기 ≤6문장을 `db.batch()` 1왕복**으로 처리한다
(성능 예산: [PRD 7절](../PRD.md#7-비기능-요구)).

```js
async function gradeAnswer({ userId, sessionId, questionId, chosenIdx, timeMs }) {
  // 읽기 1: 문항(+정답+태그) — 세션 스냅샷에 포함된 문항인지 검증
  const q      = loadQuestionWithTags(questionId);
  // 읽기 2: 관련 태그 + SEC.{section} 스킬 행
  const skills = loadSkills(userId, [...q.tags, secTag(q.section)]);

  const correct = chosenIdx === q.answer_idx;
  const isGuess = timeMs < GUESS_MS;
  const damp    = isGuess ? GUESS_SKILL_DAMP : 1.0;

  const skillUpdates = skills.map(s => {
    const p = expectedP(effectiveRating(s, skills), q.rating);
    return { ...s, rating: s.rating + K(s.attempts) * damp * ((correct ? 1 : 0) - p),
             attempts: s.attempts + 1, correct: s.correct + (correct ? 1 : 0) };
  });
  const xp  = correct ? (isGuess ? XP_GUESS : xpCorrect(q.difficulty_label))
                      : (isGuess ? XP_GUESS : XP_WRONG);
  const srs = applySrs(userId, questionId, correct, isGuess, todayKst());

  await db.batch([
    insertAnswer(...),            // answers
    ...upsertSkills(skillUpdates),// user_tag_skills (태그 1~3 + SEC = 최대 4문장)
    srsStatement(srs),            // review_queue (해당 시)
    bumpUserXp(userId, xp),       // user_stats
    bumpDailyStats(userId, xp),   // user_daily_stats UPSERT
  ]);
  // 정답·해설은 이 응답에서만 클라이언트로 나간다
  return { correct, answer_idx: q.answer_idx, explanation: q.explanation_ko, xp, srs };
}
```

`POST /api/sessions/:id/finish`: 세션 요약 저장(`sessions.summary`) → 일일 세트면
`daily_sets.completed_at` + `XP_SET_BONUS` → 스트릭 갱신(오늘 첫 인정 시 +1, 어제와 연속
아니면 1로 리셋 — `user_daily_stats`로 검증 가능) → 뱃지 판정(`badgeChecks[code]` 함수 맵,
DB `badges`는 표시 카탈로그만) → 과제 세션이면 `assignment_targets` 집계 갱신.

## 8. 게임화 수식

- XP: 상수표 그대로. 하루 성실 학습(20문항, 정답률 75%) ≈ 세트 250 XP 안팎.
- 레벨: 누적 XP ≥ `100 × L^1.5` 이면 레벨 L — Lv5 ≈ 1,118 XP(약 5일), Lv10 ≈ 3,162 XP(약 2주).
- 스트릭: "일일 세트 완료" **또는** "아무 모드 합산 10문항"(user_daily_stats.answered ≥ 10).
- 뱃지 8종: [PRD 4-5절](../PRD.md#4-5-게이미피케이션) 카탈로그, 판정은 코드 함수
  (`first-steps`는 진단 완료 시, `streak-*`는 스트릭 갱신 시, 나머지는 세션 종료 시 검사).

## 9. 문항 레이팅 재보정 (배치)

채점 핫패스에서는 문항 레이팅을 건드리지 않는다. 크론(또는 수동 스크립트)이 주기 실행:

```
대상: status='active' AND times_answered ≥ 30 인 문항
재생: 최근 창(예: 90일)의 answers를 시간순으로 읽어
      R_q ← R_q + RECALIB_K × (p_pred − is_correct)     # 학생 갱신의 거울(부호 반전)
효과: 라벨을 잘못 붙인 문항이 실데이터로 교정됨. difficulty_label은 표시용으로 유지.
```

## 10. 튜닝 가이드

모든 상수는 2절 표(코드는 `src/engine/config.js` 한 파일)가 단일 출처다. M2 이후:

| 검증 항목 | 방법 |
|---|---|
| p 예측 보정도 | 예상 정답률 구간별 실제 정답률 비교(캘리브레이션 곡선) — 어긋나면 `ELO_SCALE`·초기 맵 조정 |
| 세트 체감 난이도 | 일일 세트 정답률 분포가 65~75%에 오는지 — 어긋나면 `P_WEAK` 조정 |
| 복습 효과 | 복습 재정답률 ≥ 60%(KPI) — 낮으면 간격 축소([1,2,5,10]) 검토 |
| 찍기 임계 | time_ms 분포에서 2초 컷 검증 (LC는 음원 길이 보정 필요할 수 있음) |
| 완주율 | 세트 완료율·이탈 지점 — 낮으면 세트 크기·슬롯 비율 조정 |
| 시뮬레이션 | 구현 전후, 가상 학생(고정 실력 확률 모델)으로 세트 생성 분포·레이팅 수렴을 스크립트 검증 |

## 8. 실력 지도 (레이더 5축 + 옆 지표 2개) — `GET /api/skillmap`

캐릭터를 쓰지 않기로 하면서, 홈 화면의 주인공 그래픽 자리를 이 지도가 맡는다.

### 축 5개

| 축 | 화면 이름 | 묶는 태그 |
|---|---|---|
| `listen` | 듣고 알기 | `LS.photo` `LS.qr` `LS.gist` `LS.accent` |
| `read` | 읽고 알기 | `RS.gist` `RS.context` `RS.vocab` |
| `find` | 찾아내기 | `LS.detail` `RS.scan` |
| `grammar` | 문장 규칙 | `G.*` 10종 |
| `infer` | 속뜻 알기 | `LS.infer` `RS.infer` |

- **시험 파트(L1~R3)를 축으로 쓰지 않는다.** "L2가 약해요"는 아이도 부모도 못 알아듣는다.
- **어휘(`V.*`)는 축이 아니다.** 문항 78%에 붙어 있는 *주제 딱지*라(핵심 태그인 문항이 0개)
  축으로 쓰면 전체 평균이 되어 영원히 안 움직인다. 어휘 약점은 오답 유형 `W.meaning`이 잡는다.
- 값 = 축에 속한 태그 레이팅의 **시도 횟수 가중평균** → `(rating − 900) / 600 × 100`.
  점프 점수와 같은 눈금이다 — 100점짜리 점수가 둘인데 서로 다르면 아이가 혼란스럽다.
- **시도 3회 미만이면 값을 내지 않는다**(`measuring: true`). 3문항으로 실력이라 하면 거짓말이다.
- **축은 4일 안에 다 켜져야 한다.** 문항이 적은 축은 그냥 두면 몇 주가 지나도 3문항을 못 채워
  화면에 영영 빈칸으로 남는다(실제로 속뜻 알기가 그랬다). 5-2의 **축 채우기 슬롯**이 이를 막는다.
  `node tools/simulate-axes.mjs 21 12 30` 으로 축마다 며칠에 켜지는지 잰다 —
  **문항을 늘리거나 태그를 손볼 때마다 이 숫자를 다시 확인한다.**
- 축별 문항 수는 고르지 않다(2026-08-12 기준 듣고 알기 34.5% / 문장 규칙 30.1% / 찾아내기 23.5%
  / 읽고 알기 10.0% / **속뜻 알기 7.8%**). 속뜻 문항을 늘리는 것이 콘텐츠 우선순위다 —
  슬롯 규칙은 '켜지는 것'까지만 보장하고, 켜진 뒤 점수가 움직이는 속도는 문항 수가 정한다.

### 옆에 붙는 지표 2개 (레이더에 섞지 않는다 — 성격이 다르다)

- **설욕률** `revive`: 전에 틀렸던 문제를 다시 만나 맞힌 비율.
  정답률보다 정직하다 — 쉬운 새 문제만 받아도 정답률은 오르지만 설욕률은 안 오른다.
  `answers` 자기조인으로 계산하며 별도 저장이 없다.
- **빠르기** `speed`: 맞힌 문항의 평균 풀이 시간(찍기 2초 미만 제외), 최근 7일 vs 그 앞 7일.
  표본 5개 미만이면 `null`.

### 성장 표시

`user_skill_daily`(마이그레이션 0006)에 **하루 한 줄** 스냅샷을 남긴다. 별도 배치 없이
실력 지도를 열 때 그날 것이 없으면 기록한다. 축마다 `was`에 13일 전 값이 실려 오므로,
화면은 옅은 색으로 겹쳐 그려 "전보다 늘었다"를 보여줄 수 있다.
