-- 실력 지도의 '2주 전 모습'을 겹쳐 그리려면 과거 값이 있어야 한다.
-- user_tag_skills는 현재 값만 들고 있어서, 하루 한 줄 스냅샷을 남긴다.
-- (학생 1명당 하루 1행 — 별도 배치 없이 실력 지도를 열 때 그날 것이 없으면 남긴다)
CREATE TABLE user_skill_daily (
    user_id  TEXT NOT NULL REFERENCES users(id),
    date     TEXT NOT NULL,          -- KST 날짜
    axes     TEXT NOT NULL,          -- {"listen":62,"read":48,...} 값이 없는 축은 빠짐
    PRIMARY KEY (user_id, date)
);
