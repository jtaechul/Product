-- 글이 아닌 해설을 위한 두 가지 보조 자료 (채점 후에만 학생에게 내려간다).
--  why_not  : 오답 보기별 "왜 아닌지" 한 줄. {"0":"...","2":"..."} 형태의 JSON.
--             아이가 실제로 고른 보기 하나만 화면에 뜬다.
--  key_expr : 이 문제에서 챙길 표현 1개. {"en":"...","ko":"..."} 형태의 JSON.
ALTER TABLE questions ADD COLUMN why_not TEXT;
ALTER TABLE questions ADD COLUMN key_expr TEXT;
