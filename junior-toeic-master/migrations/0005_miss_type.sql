-- 오답 보기별 '실수 유형' 딱지. {"0":"A.wrongkind","2":"M.notsaid"} 형태의 JSON.
-- 이유 문장(why_not)은 읽을 수만 있고 셀 수 없다. 딱지가 있어야
-- "이 아이가 이 실수를 2주에 몇 번 했나"를 셀 수 있고, 그 유형만 모아
-- 다시 내보내는 추천도 가능해진다.
ALTER TABLE questions ADD COLUMN miss_type TEXT;
