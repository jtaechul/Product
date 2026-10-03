-- 정답 화면의 '한글 해석'. 아이가 문제를 틀렸을 때 정작 지문을 못 읽었으면
-- 해설만으로는 아무것도 남지 않는다 — 무슨 이야기였는지부터 알아야 다음에 맞힌다.
--
-- 지문 묶음(L3·L4·R2·R3)은 지문에, 단독 문항(L1·L2·R1)은 문항에 붙는다.
-- 아이 화면에는 답을 고른 뒤에만 나간다(풀기 전에 보이면 해석 연습이 된다).
ALTER TABLE passages  ADD COLUMN translation_ko TEXT;
ALTER TABLE questions ADD COLUMN translation_ko TEXT;
