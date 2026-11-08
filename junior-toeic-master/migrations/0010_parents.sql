-- 학부모 계정 — B2C 전환(2026-08-11). 고객이 학원에서 학부모로 바뀌면서
-- '돈 내는 사람'에게 진짜 계정이 필요해졌다.
--
-- 왜 0009와 다른 걸 또 만드는가:
--   0009는 아이 행에 parent_pin_hash 칸을 하나 더 단 구조였다. 학원이 모든 걸 발급하고
--   부모는 읽기만 하던 시절엔 그게 가장 단순했다. 그런데 학부모가 결제자가 되면
--   ① 결제·영수증에 쓸 연락처가 필요하고 ② 아이가 여럿일 수 있고
--   ③ 법정대리인 동의를 언제 누가 했는지 남겨야 한다.
--   아이 행에 칸을 더 다는 방식으로는 셋 다 안 된다.
--
-- 개인정보 원칙은 그대로 지킨다: 이메일·연락처는 **이 표에만** 있고,
-- users(아이) 표에는 지금처럼 개인정보 컬럼이 하나도 없다.
--
-- 0009의 parent_pin_hash 는 지우지 않는다 — 학원이 발급한 기존 가정이 그대로 쓰고 있다.
-- 두 경로가 당분간 공존한다 (학원 경유 = 유통 채널, 직접 가입 = 주 경로).

CREATE TABLE parents (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,        -- 항상 소문자로 저장 (대소문자만 다른 중복 가입 방지)
    password_hash TEXT NOT NULL,               -- p2$<반복횟수>$<salt>$<hex> (PBKDF2)
    display_name  TEXT NOT NULL,
    phone         TEXT,                        -- 선택. 결제·연락용, 지금은 안 받는다
    consent_at    TEXT NOT NULL,               -- 법정대리인 동의 시각 (만 14세 미만 필수)
    consent_ver   TEXT NOT NULL,               -- 동의서 버전 — 문구가 바뀌면 재동의 판단에 쓴다
    created_at    TEXT NOT NULL
);

-- 아이가 어느 학부모에게 속하는지. NULL이면 학원이 발급한 기존 계정.
ALTER TABLE users ADD COLUMN parent_id TEXT REFERENCES parents(id);
CREATE INDEX idx_users_parent ON users(parent_id);
