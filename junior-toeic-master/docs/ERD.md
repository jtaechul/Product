# DB 설계 (ERD) — Junior TOEIC Master

> Cloudflare **D1(SQLite)** 기준. 단, **표준 SQL만** 사용해 추후 PostgreSQL 이전이 가능하도록
> 설계한다. 이 문서의 DDL이 M1 `migrations/0001_init.sql`의 원본이 된다.
> 상위 문서: [PRD.md](../PRD.md) · 알고리즘: [engine.md](engine.md)

## 설계 원칙

1. **표준 SQL·이식성**: `AUTOINCREMENT` 미사용 — PK는 앱에서 생성하는 **ULID 문자열(TEXT)**
   (시간순 정렬 가능, 분산 생성 안전, PG 이전 시 그대로 사용).
2. **JSON은 TEXT 컬럼**에 저장하고 앱에서 파싱 (SQLite·PG 공통으로 동작하는 최소 공배수).
3. **날짜·시각은 ISO 8601 TEXT**: 시각은 `YYYY-MM-DDTHH:MM:SSZ`(UTC), 날짜형(일일 세트·복습
   예정일·스트릭)은 KST 기준 `YYYY-MM-DD`.
4. **집계 우선 조회**: D1은 *읽은 행 수*로 과금되므로, 리포트·대시보드는 반드시 집계 테이블
   (`user_daily_stats`, `user_tag_skills`, `assignment_targets`)만 읽는다. 원본 `answers`는
   채점 기록·재보정 배치 전용.
5. **개인정보 최소화가 스키마에 내장**: `users`에 이메일·전화 컬럼이 존재하지 않는다.
6. 열거값은 `CHECK` 제약으로 고정(이식 가능), 상태 머신은 문서에 명시.

## ERD (관계 개요)

```mermaid
erDiagram
    academies ||--o{ classes : "학원-반"
    academies ||--o{ users : "소속"
    classes |o--o{ users : "배정"
    passages |o--o{ questions : "지문 묶음"
    questions ||--o{ question_tags : ""
    concept_tags ||--o{ question_tags : ""
    users ||--o{ sessions : "학습 세션"
    assignments |o--o{ sessions : "과제 세션"
    sessions ||--o{ answers : "풀이"
    questions ||--o{ answers : ""
    users ||--o{ user_tag_skills : "태그별 실력"
    concept_tags ||--o{ user_tag_skills : ""
    users ||--o{ review_queue : "오답 복습"
    questions ||--o{ review_queue : ""
    users ||--o{ daily_sets : "일일 세트"
    academies ||--o{ assignments : "과제"
    assignments ||--o{ assignment_targets : "대상 학생"
    users ||--o{ assignment_targets : ""
    users ||--|| user_stats : "게임화 상태"
    users ||--o{ user_badges : ""
    badges ||--o{ user_badges : ""
    users ||--o{ user_daily_stats : "일별 집계"

    users {
        TEXT id PK
        TEXT role "student·teacher·academy_admin·super"
        TEXT login_id UK "가입코드-순번"
        TEXT pin_hash
        TEXT display_name
        TEXT academy_id FK
        TEXT class_id FK
    }
    questions {
        TEXT id PK
        TEXT passage_id FK
        TEXT part "L1~L4 R1~R3"
        TEXT choices "JSON"
        INTEGER answer_idx "서버 전용"
        INTEGER difficulty_label "1~5"
        REAL rating "Elo"
        TEXT status "draft·active·retired"
    }
    user_tag_skills {
        TEXT user_id PK,FK
        TEXT tag_id PK,FK
        REAL rating
        INTEGER attempts
    }
    review_queue {
        TEXT user_id FK
        TEXT question_id FK
        INTEGER box "1~4"
        TEXT due_at "YYYY-MM-DD"
    }
```

(가독성을 위해 다이어그램에는 핵심 컬럼만 표기 — 전체 정의는 아래 DDL이 기준.)

## 테이블 정의 (DDL, 18개)

FK 의존 순서대로 배치되어 있어 그대로 실행 가능하다.

### 1) 조직·계정

```sql
CREATE TABLE academies (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    join_code  TEXT NOT NULL UNIQUE,          -- 학생 로그인ID 접두어 (예: HAPPY01)
    status     TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
    created_at TEXT NOT NULL
);

CREATE TABLE classes (
    id         TEXT PRIMARY KEY,
    academy_id TEXT NOT NULL REFERENCES academies(id),
    name       TEXT NOT NULL,
    grade      TEXT,                          -- 표시용 (예: 초6, 중1)
    set_size   INTEGER NOT NULL DEFAULT 20,   -- 일일 세트 크기 (초등 반 12 권장)
    created_at TEXT NOT NULL
);

CREATE TABLE users (
    id           TEXT PRIMARY KEY,
    role         TEXT NOT NULL CHECK (role IN ('student','teacher','academy_admin','super')),
    login_id     TEXT NOT NULL UNIQUE,        -- '{join_code}-{순번}' 전역 유일 (예: HAPPY01-0007)
    pin_hash     TEXT NOT NULL,               -- 6자리 PIN의 PBKDF2 해시 (원문 미저장)
    display_name TEXT NOT NULL,               -- 이름 또는 별명 (이메일·전화 컬럼 없음 — PIPA)
    academy_id   TEXT REFERENCES academies(id),
    class_id     TEXT REFERENCES classes(id),
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_users_academy ON users(academy_id);   -- 학원 단위 목록·격리 스코프
CREATE INDEX idx_users_class   ON users(class_id);     -- 반 리포트 조인
```

### 2) 콘텐츠 (문제 은행)

```sql
CREATE TABLE concept_tags (
    id          TEXT PRIMARY KEY,             -- 태그 code를 그대로 id로 사용 (안정적·가독적)
    code        TEXT NOT NULL UNIQUE,         -- 예: G.tense, V.school, LS.gist (2단계 트리 관례)
    section     TEXT NOT NULL CHECK (section IN ('LC','RC','ALL')),  -- V.* 어휘 태그는 양 섹션 공통(ALL)
    name_ko     TEXT NOT NULL,
    part        TEXT,                         -- 파트 전용 태그면 L1~L4·R1~R3, 섹션 공통이면 NULL
    exam_weight REAL NOT NULL DEFAULT 1.0,    -- 시험 출제 비중 (약점 점수 가중; SEC.* 의사 태그는 0)
    parent_id   TEXT REFERENCES concept_tags(id)
);

CREATE TABLE passages (
    id         TEXT PRIMARY KEY,
    section    TEXT NOT NULL CHECK (section IN ('LC','RC')),
    part       TEXT NOT NULL,                 -- L3·L4·R2·R3 등 묶음 파트
    kind       TEXT NOT NULL CHECK (kind IN ('photo','dialogue','talk','text')),
    content    TEXT,                          -- RC 지문 본문 / LC 스크립트(검수·재생성용)
    image_url  TEXT,
    audio_url  TEXT,                          -- R2 경로 (LC)
    accent     TEXT CHECK (accent IN ('US','UK','AU')),
    created_at TEXT NOT NULL
);

CREATE TABLE questions (
    id               TEXT PRIMARY KEY,
    passage_id       TEXT REFERENCES passages(id),   -- 단독 문항이면 NULL
    section          TEXT NOT NULL CHECK (section IN ('LC','RC')),
    part             TEXT NOT NULL CHECK (part IN ('L1','L2','L3','L4','R1','R2','R3')),
    stem             TEXT,                    -- 발문 (L1 등 일부 유형은 NULL)
    choices          TEXT NOT NULL,           -- JSON 배열 (Bridge 표준 4지선다, 3지도 허용)
    answer_idx       INTEGER NOT NULL,        -- 정답 인덱스 — 클라이언트로 절대 전송 금지
    explanation_ko   TEXT NOT NULL,           -- 한국어 해설 — 채점 응답에서만 반환
    difficulty_label INTEGER NOT NULL CHECK (difficulty_label BETWEEN 1 AND 5),
    rating           REAL NOT NULL,           -- Elo 문항 레이팅 (라벨로 초기화, 배치 재보정)
    times_answered   INTEGER NOT NULL DEFAULT 0,
    times_correct    INTEGER NOT NULL DEFAULT 0,
    audio_url        TEXT,                    -- 단독 LC 문항용 (L1·L2)
    image_url        TEXT,                    -- 단독 이미지 문항용 (L1)
    accent           TEXT CHECK (accent IN ('US','UK','AU')),
    script           TEXT,                    -- LC 단독 문항의 낭독 원문 (검수·음원 준비 전 열람용, 학생 모드에선 음원 재생 시 미노출)
    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','retired')),
    created_at       TEXT NOT NULL
);
CREATE INDEX idx_questions_pool   ON questions(status, section, part);  -- 세트 생성 후보 스캔
CREATE INDEX idx_questions_rating ON questions(status, rating);         -- p-윈도우 난이도 샘플링

CREATE TABLE question_tags (
    question_id TEXT NOT NULL REFERENCES questions(id),
    tag_id      TEXT NOT NULL REFERENCES concept_tags(id),
    PRIMARY KEY (question_id, tag_id)
);
CREATE INDEX idx_question_tags_tag ON question_tags(tag_id, question_id); -- 태그→문항 방향 조인
```

### 3) 과제 (B2B)

```sql
CREATE TABLE assignments (
    id           TEXT PRIMARY KEY,
    academy_id   TEXT NOT NULL REFERENCES academies(id),
    class_id     TEXT REFERENCES classes(id),          -- NULL이면 개별 학생 지정 과제
    created_by   TEXT NOT NULL REFERENCES users(id),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','closed')),
    question_ids TEXT NOT NULL,               -- 발행 시 확정된 문항 스냅샷(JSON) — 학생 간 동일 세트
    spec         TEXT,                        -- 생성 조건 JSON (유형·파트·문항 수) — 재현·감사용
    due_at       TEXT,
    created_at   TEXT NOT NULL
);
```

### 4) 학습 기록

```sql
CREATE TABLE sessions (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id),
    type          TEXT NOT NULL CHECK (type IN ('diagnostic','daily','assignment','review')),
    assignment_id TEXT REFERENCES assignments(id),
    question_ids  TEXT NOT NULL,              -- 출제 문항·순서 스냅샷(JSON) — 이어하기·재현
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    summary       TEXT                        -- 종료 시 요약 JSON (정답수·XP·파트별 결과)
);
CREATE INDEX idx_sessions_user ON sessions(user_id, started_at);  -- 최근 세션 조회

CREATE TABLE answers (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    user_id     TEXT NOT NULL REFERENCES users(id),
    question_id TEXT NOT NULL REFERENCES questions(id),
    chosen_idx  INTEGER NOT NULL,
    is_correct  INTEGER NOT NULL CHECK (is_correct IN (0,1)),
    time_ms     INTEGER NOT NULL,             -- 풀이 시간 (찍기 판정·리포트)
    answered_at TEXT NOT NULL
);
CREATE INDEX idx_answers_session   ON answers(session_id);            -- 세션 요약 산출
CREATE INDEX idx_answers_user_time ON answers(user_id, answered_at);  -- 노출 이력(14일 제외)·보존 정리
CREATE INDEX idx_answers_question  ON answers(question_id);           -- 문항 레이팅 재보정 배치

CREATE TABLE user_daily_stats (
    user_id     TEXT NOT NULL REFERENCES users(id),
    date        TEXT NOT NULL,                -- 'YYYY-MM-DD' (KST)
    answered    INTEGER NOT NULL DEFAULT 0,
    correct     INTEGER NOT NULL DEFAULT 0,
    time_ms_sum INTEGER NOT NULL DEFAULT 0,
    xp_gained   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)               -- 리포트·스트릭 검증·보존 정책의 기반 집계
);
```

### 5) 추천·복습 상태

```sql
CREATE TABLE user_tag_skills (
    user_id           TEXT NOT NULL REFERENCES users(id),
    tag_id            TEXT NOT NULL REFERENCES concept_tags(id),
    rating            REAL NOT NULL,          -- 태그별 Elo 레이팅 (진단으로 초기화)
    attempts          INTEGER NOT NULL DEFAULT 0,
    correct           INTEGER NOT NULL DEFAULT 0,
    last_practiced_at TEXT,
    PRIMARY KEY (user_id, tag_id)
);

CREATE TABLE review_queue (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id),
    question_id  TEXT NOT NULL REFERENCES questions(id),
    box          INTEGER NOT NULL DEFAULT 1 CHECK (box BETWEEN 1 AND 4),  -- 라이트너 박스
    due_at       TEXT NOT NULL,               -- 다음 복습 예정일 'YYYY-MM-DD' (KST)
    created_at   TEXT NOT NULL,
    graduated_at TEXT,                        -- 박스4 정답으로 졸업한 시각
    UNIQUE (user_id, question_id)             -- 같은 문항 중복 등록 방지 (재오답 시 UPDATE)
);
CREATE INDEX idx_review_due ON review_queue(user_id, due_at) WHERE graduated_at IS NULL;
-- 오늘 복습분 조회 전용 부분 인덱스 (SQLite·PG 공통 지원)

CREATE TABLE daily_sets (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id),
    date         TEXT NOT NULL,               -- 'YYYY-MM-DD' (KST)
    session_id   TEXT REFERENCES sessions(id),
    question_ids TEXT NOT NULL,               -- 생성된 세트 스냅샷(JSON)
    slots        TEXT NOT NULL,               -- 구성 내역 JSON {review,weak,fresh,keep}
    generated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (user_id, date)                    -- 하루 1세트 (재접속 시 재생성 방지)
);
```

### 6) 과제 이행·게임화

```sql
CREATE TABLE assignment_targets (
    assignment_id TEXT NOT NULL REFERENCES assignments(id),
    user_id       TEXT NOT NULL REFERENCES users(id),
    session_id    TEXT REFERENCES sessions(id),
    status        TEXT NOT NULL DEFAULT 'assigned'
                  CHECK (status IN ('assigned','in_progress','completed')),
    correct_count INTEGER NOT NULL DEFAULT 0, -- 완료 시 비정규화 저장 —
    total_count   INTEGER NOT NULL DEFAULT 0, -- 반 리포트가 answers를 읽지 않게 함
    completed_at  TEXT,
    PRIMARY KEY (assignment_id, user_id)
);
CREATE INDEX idx_assignment_targets_user ON assignment_targets(user_id, status); -- 학생 "내 숙제" 뷰

CREATE TABLE user_stats (
    user_id          TEXT PRIMARY KEY REFERENCES users(id),
    xp               INTEGER NOT NULL DEFAULT 0,
    level            INTEGER NOT NULL DEFAULT 1,
    streak_days      INTEGER NOT NULL DEFAULT 0,
    best_streak      INTEGER NOT NULL DEFAULT 0,
    last_streak_date TEXT                     -- 마지막 출석 인정일 (스트릭 판정)
);

CREATE TABLE badges (
    id          TEXT PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,         -- 판정 로직은 코드(engine)에 있음 — 표시 카탈로그만 DB
    name_ko     TEXT NOT NULL,
    description TEXT NOT NULL,
    icon        TEXT                          -- 커스텀 아이콘 경로 (OS 이모지 금지)
);

CREATE TABLE user_badges (
    user_id   TEXT NOT NULL REFERENCES users(id),
    badge_id  TEXT NOT NULL REFERENCES badges(id),
    earned_at TEXT NOT NULL,
    PRIMARY KEY (user_id, badge_id)
);
```

> M5에서 `subscriptions`(학원 좌석제 정산) 테이블을 추가한다 — MVP 범위 제외.

## 인덱스 요약 (조회 경로별)

| 인덱스 | 지원하는 쿼리 |
|---|---|
| `idx_users_academy` / `idx_users_class` | 학원·반 단위 학생 목록, 반 리포트 조인 |
| `idx_questions_pool` (status,section,part) | 일일 세트 후보 문항 스캔 |
| `idx_questions_rating` (status,rating) | 예상 정답률 p-윈도우 난이도 샘플링 |
| `idx_question_tags_tag` (tag_id,question_id) | 약점 태그 → 문항 후보 조인 |
| `idx_sessions_user` (user_id,started_at) | 최근 세션·이어하기 |
| `idx_answers_user_time` (user_id,answered_at) | 최근 14일 노출 문항 제외, 보존 정리 배치 |
| `idx_answers_question` (question_id) | 문항 레이팅 재보정 배치 |
| `idx_review_due` (user_id,due_at) partial | 오늘 복습 예정 문항 조회 (미졸업만) |
| `idx_assignment_targets_user` (user_id,status) | 학생 "내 숙제" 목록 |

## 데이터 볼륨과 보존 정책 (D1 10GB 한도 대응)

전제(만석 기준): 1만 학생 × 일 20문항 × 월 22일 ≈ **월 440만 answers 행**.
행당 실효 용량(데이터+인덱스 3개) ≈ 380B → **월 약 1.7GB**.

| 항목 | 정책 |
|---|---|
| `answers` 원본 | **최근 3개월만 보존** (만석 기준 ≈ 5GB). 그 이전은 월 배치로 삭제 |
| 삭제 전 보장 | `user_daily_stats`(일별 집계)·`sessions.summary`(세션 요약)·`user_tag_skills`(실력 상태)가 이미 리포트를 담당하므로 **리포트·스트릭·실력 데이터는 손실 없음** |
| 오답노트 | `review_queue`는 answers와 독립 — 원본 삭제와 무관하게 유지 |
| 손실 항목 | 3개월 이전의 "문항 단위 상세 풀이 이력"만 사라짐 (허용 가능한 트레이드오프로 명시) |
| 이전 트리거 | DB 크기 7GB 도달 시 PostgreSQL(예: Supabase/Neon) 이전 착수 — 표준 SQL이라 스키마 재사용, 필요시 학원 단위 DB 분할(D1 다중 DB)도 대안 |

초기(수백~수천 학생)에는 월 수십~수백 MB 수준이므로 여유가 크다. 보존 개월 수는 운영 설정값으로 둔다.

## 마이그레이션 운영 (M1)

- 본 DDL을 `junior-toeic-master/migrations/0001_init.sql`로 옮겨 시작한다.
- 적용: `npx wrangler d1 migrations apply <DB> --local`(개발) / `--remote`(운영).
- 규칙: 적용된 마이그레이션 파일은 **불변** — 스키마 변경은 항상 새 번호 파일로 추가한다.
- 시드(태그 카탈로그·뱃지 카탈로그)는 마이그레이션이 아닌 [임포트 도구](content-pipeline.md)로 넣는다.
