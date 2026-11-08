-- 아이가 막힌 자리를 모으는 곳. 테스터 검증(M3)에서 가장 중요한 데이터다.
-- 어른이 대신 옮겨 적으면 진짜 이유가 사라지므로, 아이가 그 화면에서 바로 누르게 한다.
-- kind: audio(소리) / image(사진) / hard(이해 안 됨) / answer(답이 이상) / etc(그 밖에)
CREATE TABLE feedback (
    id          TEXT PRIMARY KEY,
    user_id     TEXT REFERENCES users(id),      -- 로그인 안 했으면 NULL
    question_id TEXT REFERENCES questions(id),  -- 화면 전체에 대한 신고면 NULL
    kind        TEXT NOT NULL CHECK (kind IN ('audio','image','hard','answer','etc')),
    note        TEXT,                            -- 아이가 직접 쓴 말 (선택)
    screen      TEXT,                            -- 어느 화면에서 눌렀는지
    created_at  TEXT NOT NULL
);
CREATE INDEX idx_feedback_question ON feedback(question_id);
CREATE INDEX idx_feedback_created ON feedback(created_at);
