-- 점프리시(Jumplish) 초기 스키마 — docs/ERD.md 기준 (18테이블)
-- 표준 SQL 유지 (PostgreSQL 이전 가능), PK는 앱 생성 ULID 문자열

-- 1) 조직·계정
CREATE TABLE academies (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    join_code  TEXT NOT NULL UNIQUE,
    status     TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
    created_at TEXT NOT NULL
);

CREATE TABLE classes (
    id         TEXT PRIMARY KEY,
    academy_id TEXT NOT NULL REFERENCES academies(id),
    name       TEXT NOT NULL,
    grade      TEXT,
    set_size   INTEGER NOT NULL DEFAULT 20,
    created_at TEXT NOT NULL
);

CREATE TABLE users (
    id           TEXT PRIMARY KEY,
    role         TEXT NOT NULL CHECK (role IN ('student','teacher','academy_admin','super')),
    login_id     TEXT NOT NULL UNIQUE,
    pin_hash     TEXT NOT NULL,
    display_name TEXT NOT NULL,
    academy_id   TEXT REFERENCES academies(id),
    class_id     TEXT REFERENCES classes(id),
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_users_academy ON users(academy_id);
CREATE INDEX idx_users_class   ON users(class_id);

-- 2) 콘텐츠 (문제 은행)
CREATE TABLE concept_tags (
    id          TEXT PRIMARY KEY,            -- 태그 code를 그대로 id로 사용 (예: G.tense)
    code        TEXT NOT NULL UNIQUE,
    name_ko     TEXT NOT NULL,
    section     TEXT NOT NULL CHECK (section IN ('LC','RC','ALL')),  -- V.* 어휘 태그는 ALL
    part        TEXT,
    exam_weight REAL NOT NULL DEFAULT 1.0,
    parent_id   TEXT REFERENCES concept_tags(id)
);

CREATE TABLE passages (
    id         TEXT PRIMARY KEY,
    section    TEXT NOT NULL CHECK (section IN ('LC','RC')),
    part       TEXT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('photo','dialogue','talk','text')),
    content    TEXT,
    image_url  TEXT,
    audio_url  TEXT,
    accent     TEXT CHECK (accent IN ('US','UK','AU')),
    created_at TEXT NOT NULL
);

CREATE TABLE questions (
    id               TEXT PRIMARY KEY,
    passage_id       TEXT REFERENCES passages(id),
    section          TEXT NOT NULL CHECK (section IN ('LC','RC')),
    part             TEXT NOT NULL CHECK (part IN ('L1','L2','L3','L4','R1','R2','R3')),
    stem             TEXT,
    choices          TEXT NOT NULL,
    answer_idx       INTEGER NOT NULL,
    explanation_ko   TEXT NOT NULL,
    difficulty_label INTEGER NOT NULL CHECK (difficulty_label BETWEEN 1 AND 5),
    rating           REAL NOT NULL,
    times_answered   INTEGER NOT NULL DEFAULT 0,
    times_correct    INTEGER NOT NULL DEFAULT 0,
    audio_url        TEXT,
    image_url        TEXT,
    accent           TEXT CHECK (accent IN ('US','UK','AU')),
    script           TEXT,                     -- LC 단독 문항의 낭독 원문 (검수·음원 준비 전 열람용)
    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','retired')),
    created_at       TEXT NOT NULL
);
CREATE INDEX idx_questions_pool   ON questions(status, section, part);
CREATE INDEX idx_questions_rating ON questions(status, rating);

CREATE TABLE question_tags (
    question_id TEXT NOT NULL REFERENCES questions(id),
    tag_id      TEXT NOT NULL REFERENCES concept_tags(id),
    PRIMARY KEY (question_id, tag_id)
);
CREATE INDEX idx_question_tags_tag ON question_tags(tag_id, question_id);

-- 3) 과제 (B2B)
CREATE TABLE assignments (
    id           TEXT PRIMARY KEY,
    academy_id   TEXT NOT NULL REFERENCES academies(id),
    class_id     TEXT REFERENCES classes(id),
    created_by   TEXT NOT NULL REFERENCES users(id),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','closed')),
    question_ids TEXT NOT NULL,
    spec         TEXT,
    due_at       TEXT,
    created_at   TEXT NOT NULL
);

-- 4) 학습 기록
CREATE TABLE sessions (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id),
    type          TEXT NOT NULL CHECK (type IN ('diagnostic','daily','assignment','review')),
    assignment_id TEXT REFERENCES assignments(id),
    question_ids  TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    summary       TEXT
);
CREATE INDEX idx_sessions_user ON sessions(user_id, started_at);

CREATE TABLE answers (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id),
    user_id     TEXT NOT NULL REFERENCES users(id),
    question_id TEXT NOT NULL REFERENCES questions(id),
    chosen_idx  INTEGER NOT NULL,
    is_correct  INTEGER NOT NULL CHECK (is_correct IN (0,1)),
    time_ms     INTEGER NOT NULL,
    answered_at TEXT NOT NULL
);
CREATE INDEX idx_answers_session   ON answers(session_id);
CREATE INDEX idx_answers_user_time ON answers(user_id, answered_at);
CREATE INDEX idx_answers_question  ON answers(question_id);

CREATE TABLE user_daily_stats (
    user_id     TEXT NOT NULL REFERENCES users(id),
    date        TEXT NOT NULL,
    answered    INTEGER NOT NULL DEFAULT 0,
    correct     INTEGER NOT NULL DEFAULT 0,
    time_ms_sum INTEGER NOT NULL DEFAULT 0,
    xp_gained   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

-- 5) 추천·복습 상태
CREATE TABLE user_tag_skills (
    user_id           TEXT NOT NULL REFERENCES users(id),
    tag_id            TEXT NOT NULL REFERENCES concept_tags(id),
    rating            REAL NOT NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    correct           INTEGER NOT NULL DEFAULT 0,
    last_practiced_at TEXT,
    PRIMARY KEY (user_id, tag_id)
);

CREATE TABLE review_queue (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id),
    question_id  TEXT NOT NULL REFERENCES questions(id),
    box          INTEGER NOT NULL DEFAULT 1 CHECK (box BETWEEN 1 AND 4),
    due_at       TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    graduated_at TEXT,
    UNIQUE (user_id, question_id)
);
CREATE INDEX idx_review_due ON review_queue(user_id, due_at) WHERE graduated_at IS NULL;

CREATE TABLE daily_sets (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id),
    date         TEXT NOT NULL,
    session_id   TEXT REFERENCES sessions(id),
    question_ids TEXT NOT NULL,
    slots        TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (user_id, date)
);

-- 6) 과제 이행·게임화
CREATE TABLE assignment_targets (
    assignment_id TEXT NOT NULL REFERENCES assignments(id),
    user_id       TEXT NOT NULL REFERENCES users(id),
    session_id    TEXT REFERENCES sessions(id),
    status        TEXT NOT NULL DEFAULT 'assigned'
                  CHECK (status IN ('assigned','in_progress','completed')),
    correct_count INTEGER NOT NULL DEFAULT 0,
    total_count   INTEGER NOT NULL DEFAULT 0,
    completed_at  TEXT,
    PRIMARY KEY (assignment_id, user_id)
);
CREATE INDEX idx_assignment_targets_user ON assignment_targets(user_id, status);

CREATE TABLE user_stats (
    user_id          TEXT PRIMARY KEY REFERENCES users(id),
    xp               INTEGER NOT NULL DEFAULT 0,
    level            INTEGER NOT NULL DEFAULT 1,
    streak_days      INTEGER NOT NULL DEFAULT 0,
    best_streak      INTEGER NOT NULL DEFAULT 0,
    last_streak_date TEXT
);

CREATE TABLE badges (
    id          TEXT PRIMARY KEY,             -- 뱃지 code를 그대로 id로 사용
    code        TEXT NOT NULL UNIQUE,
    name_ko     TEXT NOT NULL,
    description TEXT NOT NULL,
    icon        TEXT
);

CREATE TABLE user_badges (
    user_id   TEXT NOT NULL REFERENCES users(id),
    badge_id  TEXT NOT NULL REFERENCES badges(id),
    earned_at TEXT NOT NULL,
    PRIMARY KEY (user_id, badge_id)
);
