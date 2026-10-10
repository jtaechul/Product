-- 가족 관리 (2026-08-12) — 관리자에게 '비밀번호 없이' 할 수 있는 관리 수단을 준다.
--
-- 관리자는 여전히 비밀번호를 정하거나 볼 수 없다. 대신:
--   status            일시 정지(suspended) — 로그인만 막고 데이터는 보존 (어뷰징 대응)
--   reset_token_hash  일회용 비밀번호 재설정 토큰의 해시. 관리자가 링크를 만들어
--                     학부모에게 전달하면, 새 비밀번호는 학부모가 그 링크에서 직접 정한다.
--                     평문 토큰은 응답에 한 번 실려 가고 서버에는 해시만 남는다.
--   admin_notes       가족별 운영 메모 — 문의·처리 이력. 정지/해제/링크 발급도
--                     자동으로 한 줄씩 남아 감사 기록이 된다.
-- 탈퇴(삭제)는 컬럼이 필요 없다 — 가족의 모든 행을 지운다(개인정보보호법상 삭제 의무).

ALTER TABLE parents ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE parents ADD COLUMN reset_token_hash TEXT;
ALTER TABLE parents ADD COLUMN reset_expires_at TEXT;

CREATE TABLE admin_notes (
    id         TEXT PRIMARY KEY,
    parent_id  TEXT NOT NULL REFERENCES parents(id),
    body       TEXT NOT NULL,
    created_by TEXT NOT NULL,   -- 남긴 관리자 login_id
    created_at TEXT NOT NULL
);
CREATE INDEX idx_admin_notes_parent ON admin_notes(parent_id, created_at DESC);
