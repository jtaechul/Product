// SPOTLIGHT 전역 상수 + 디자인 토큰 (기획서 4·6·16번)

// 세로(9:16) 기준 설계 해상도. 실제 화면은 이 비율로 맞춰 스케일한다.
export const DESIGN_WIDTH = 720;
export const DESIGN_HEIGHT = 1280;

// 진행 구조
export const TOTAL_TURNS = 36; // 36개월 = 3년
export const SLOTS_PER_TURN = 2;

// 마일스톤 (기획서 6번): 학년 말 목표(인지도). 미달 시 경고 안내만(난이도 모드 없음).
export const MILESTONES = {
  13: { grade: "고1", fans: 15, need: "팬 15 이상" },   // 고1 말
  25: { grade: "고2", fans: 40, need: "팬 40 이상" },   // 고2 말
};

// 시작 자금
export const START_MONEY = 100000;


// 디자인 토큰 (디자인 시트/목업 팔레트 기준 — 추후 확정)
export const COLORS = {
  navy: 0x1e2a4a,
  navy2: 0x2c3c63,
  coral: 0xff8a7a,
  mint: 0x7ee0c8,
  gold: 0xf5c451,
  paper: 0xfdfbf7,
  ink: 0x2a2a33,
};
