-- 데모 학원·계정 (M2 개발/시연용 — 실제 학원 계정은 M4 관리자 화면에서 발급)
-- PIN은 데모 공개값: JUMP-1/111222, JUMP-2/333444, JUMP-T1/777888
INSERT OR IGNORE INTO academies (id, name, join_code, status, created_at) VALUES ('ACAD-DEMO', '점프리시 데모학원', 'JUMP', 'active', '2026-08-09T04:12:36.158Z');
INSERT OR IGNORE INTO classes (id, academy_id, name, grade, set_size, created_at) VALUES ('CLASS-DEMO', 'ACAD-DEMO', '데모반', '초5', 12, '2026-08-09T04:12:36.158Z');
INSERT OR IGNORE INTO users (id, role, login_id, pin_hash, display_name, academy_id, class_id, created_at) VALUES ('U-DEMO-1', 'student', 'JUMP-1', 's1$demo1a2b$cadd89d1ffce39314bb85b3d32cbcd053a49c5db13e5dd9e7193e8ab69e31a94', '김점프', 'ACAD-DEMO', 'CLASS-DEMO', '2026-08-09T04:12:36.158Z');
INSERT OR IGNORE INTO users (id, role, login_id, pin_hash, display_name, academy_id, class_id, created_at) VALUES ('U-DEMO-2', 'student', 'JUMP-2', 's1$demo3c4d$b0e24dccd3a6745ecc3ad258080f1120b006f8c1556290a7b8495181bd13d6b8', '이리시', 'ACAD-DEMO', 'CLASS-DEMO', '2026-08-09T04:12:36.158Z');
INSERT OR IGNORE INTO users (id, role, login_id, pin_hash, display_name, academy_id, class_id, created_at) VALUES ('U-DEMO-T1', 'teacher', 'JUMP-T1', 's1$demot5e6$4e6523eab50055e4eacd611f75091501c4a4ac94bf46e605a6b463648246182e', '박선생', 'ACAD-DEMO', 'CLASS-DEMO', '2026-08-09T04:12:36.158Z');
