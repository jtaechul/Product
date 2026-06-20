// SPOTLIGHT 전역 상수 + 디자인 토큰 (기획서 4·6·16번)

// 세로(9:16) 기준 설계 해상도. 실제 화면은 이 비율로 맞춰 스케일한다.
export const DESIGN_WIDTH = 720;
export const DESIGN_HEIGHT = 1280;

// 진행 구조
export const TOTAL_TURNS = 36; // 36개월 = 3년
export const SLOTS_PER_TURN = 2;

// 난이도 모드 (기획서 8번): 시작 돈 · 스탯 상승 배율 · 마일스톤(어려움만 필수)
export const DIFFICULTY = {
  easy:   { id: "easy",   label: "쉬움",   money: 150000, gain: 1.2, milestone: false, desc: "여유로운 자금 · 빠른 성장" },
  normal: { id: "normal", label: "보통",   money: 100000, gain: 1.0, milestone: false, desc: "기준 밸런스 · 경고만" },
  hard:   { id: "hard",   label: "어려움", money: 70000,  gain: 0.9, milestone: true,  desc: "빠듯한 자금 · 목표 미달 시 방출" },
};
export const DEFAULT_DIFFICULTY = "normal";

// 마일스톤 (기획서 6번): 학년 말 목표. 어려움 모드에서 미달 시 방출(배드엔딩).
export const MILESTONES = {
  13: { grade: "고1", fans: 15, need: "팬 15 이상" },   // 고1 말
  25: { grade: "고2", fans: 40, need: "팬 40 이상" },   // 고2 말
};


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
