-- 신고를 확인·처리했는지 표시. 지금까지는 아이들이 신고를 보내기만 하고
-- 아무도 읽을 수 없었다(관리자 화면이 없었다). 읽는 화면을 만들면서
-- "이건 봤다 / 고쳤다"를 남길 자리가 필요하다.
ALTER TABLE feedback ADD COLUMN handled_at TEXT;      -- 처리한 시각 (NULL이면 아직 안 봄)
ALTER TABLE feedback ADD COLUMN handled_by TEXT REFERENCES users(id);
CREATE INDEX idx_feedback_handled ON feedback(handled_at);
