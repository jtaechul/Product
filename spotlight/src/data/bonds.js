// 인연(Bond) 데이터 (기획서 12번). 조력 4인 + 활동→인연 매핑.
// lm: 사각 프레임 얼굴 배치(기획서 17) — cx(가로 중심), top(머리끝), throat(목젖)을 이미지 비율(0~1)로.
export const BONDS = [
  { id: "hanjiwon", name: "한지원", role: "매니저",     img: "./assets/manager/hanjiwon.png", bonus: "출연 평가 +10% · 제안 질↑", lm: { cx: 0.3923, top: 0.0393, throat: 0.3986 } },
  { id: "noh",      name: "노교수", role: "연기 선생",  img: "./assets/teacher/noh.png",      bonus: "연기 활동 효율 +20%",      lm: { cx: 0.4690, top: 0.0224, throat: 0.4541 } },
  { id: "haneul",   name: "박하늘", role: "단짝 친구",  img: "./assets/friend/haneul.png",    bonus: "멘탈 회복 +30%",           lm: { cx: 0.4688, top: 0.0333, throat: 0.4375 } },
  { id: "yusea",    name: "유세아", role: "라이벌",     img: "./assets/rivals/yusea.png",     bonus: "출연 시 연기력 자극↑",     lm: { cx: 0.4700, top: 0.0227, throat: 0.4545 } },
];

// 활동 id → 상승하는 인연 (기획서 9·12번)
export const ACT_BOND = { acting: "noh", prep: "hanjiwon", friend: "haneul", family: "haneul" };

// 인연 보너스 발동 임계값
export const BOND_THRESHOLD = 40;
