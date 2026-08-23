-- 내 단어장 (2026-08-23)
--
-- 아이가 정답 화면에서 눌러 본 낱말을 모은다. "몰라서 눌렀다"는 것 자체가
-- 그 아이에게 어려운 낱말이라는 가장 정직한 신호다 — 저자가 고른 목록보다 낫다.
--
-- 기기(localStorage)가 아니라 서버에 둔다: 기기를 바꾸면 통째로 사라지고,
-- 태블릿을 형제가 돌려 쓰면 기록이 섞인다(파트별 기록에서 이미 겪은 문제).
CREATE TABLE user_words (
    user_id   TEXT NOT NULL REFERENCES users(id),
    word      TEXT NOT NULL,          -- 항상 소문자 원형
    meaning   TEXT NOT NULL,          -- 누른 시점의 뜻 (사전이 바뀌어도 그때 본 뜻이 남는다)
    times     INTEGER NOT NULL DEFAULT 1,   -- 몇 번 눌렀나 = 얼마나 안 외워졌나
    first_at  TEXT NOT NULL,
    last_at   TEXT NOT NULL,
    PRIMARY KEY (user_id, word)
);
CREATE INDEX idx_user_words_recent ON user_words(user_id, last_at DESC);
