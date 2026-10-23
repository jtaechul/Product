-- 신고 자동 검토 (2026-10-21)
--
-- 아이가 "답이 이상해요"를 누르면 매일 밤 검토 로봇(GitHub 작업실 — 앱 서버에는 AI 열쇠를
-- 두지 않는다)이 문항을 다시 본다. AI 두 개가 따로 판정해서 둘 다 맞다고 할 때만 움직인다.
--   fixed  잘못이 맞고 고쳤다            → 아이에게 "고쳤어요" 답장
--   held   잘못이 맞는데 자동으로 못 고친다 → 문항을 내리고 사람이 고친다
--   ok     문항이 맞다                   → 왜 맞는지 아이 눈높이로 답장
--   human  두 판정이 엇갈렸다            → 관리자 화면에서 사람이 정한다
-- NULL 은 아직 검토 전이다.

-- 신고한 순간 아이가 본 문항(JSON). 그 뒤에 문항이 고쳐지면 지금 판본만 봐서는
-- 아이 말이 맞았는지 알 수 없다 — "그때는 틀렸고 지금은 고쳐졌다"를 가려내는 재료다.
ALTER TABLE feedback ADD COLUMN q_snapshot TEXT;
-- 그 문항에서 아이가 마지막으로 고른 보기 (안 풀었으면 NULL). 판정 재료로만 쓴다.
ALTER TABLE feedback ADD COLUMN chosen_idx INTEGER;

ALTER TABLE feedback ADD COLUMN review_status TEXT;   -- 위 표 (NULL = 검토 전)
ALTER TABLE feedback ADD COLUMN review_note TEXT;     -- 관리자용 한 줄 요약 (아이에게 안 보인다)
ALTER TABLE feedback ADD COLUMN review_detail TEXT;   -- 관리자용 자세한 기록(JSON): 두 판정·바꾼 내용
ALTER TABLE feedback ADD COLUMN reviewed_at TEXT;

-- 신고한 아이에게 보일 답장. 앱 홈에 "답장이 왔어요"로 뜬다.
ALTER TABLE feedback ADD COLUMN reply_ko TEXT;
ALTER TABLE feedback ADD COLUMN replied_at TEXT;
ALTER TABLE feedback ADD COLUMN reply_seen_at TEXT;   -- 아이가 답장을 열어 본 시각

CREATE INDEX idx_feedback_review ON feedback(review_status);
CREATE INDEX idx_feedback_user ON feedback(user_id, created_at);
