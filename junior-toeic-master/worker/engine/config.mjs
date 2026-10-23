// 점프리시 엔진 상수 — 단일 출처는 docs/engine.md 2절 상수표.
// 이 파일은 그 표를 코드로 옮긴 것이며, 값 변경은 문서와 함께 한다. (M2에서 본격 사용)
export const ENGINE = {
  ELO_SCALE: 400,
  RATING_INIT_BY_LABEL: { 1: 900, 2: 1050, 3: 1200, 4: 1350, 5: 1500 },
  K_SCHEDULE: [
    { maxAttempts: 20, k: 32 },
    { maxAttempts: 50, k: 24 },
    { maxAttempts: Infinity, k: 16 },
  ],
  SHRINK_PIVOT: 8,
  GUESS_MS: 2000,
  GUESS_SKILL_DAMP: 0.5,
  SRS_INTERVALS: [1, 3, 7, 14],
  DAILY_SLOTS_20: { review: 6, weak: 8, fresh: 4, keep: 2 },
  DAILY_SLOTS_12: { review: 4, weak: 5, fresh: 2, keep: 1 },
  P_WEAK: [0.55, 0.75],
  P_WEAK_RELAXED: [0.45, 0.85],
  P_KEEP: 0.8,
  NO_REPEAT_DAYS: 14,
  STALENESS_CAP: 2.0,
  SECTION_MIN_RATIO: 0.3,
  XP_WRONG: 2,
  XP_GUESS: 1,
  XP_SET_BONUS: 30,
  STREAK_MIN_Q: 10,
  DIAG_STAGE_SIZE: { basic: 12, junior: 8 },
  DIAG_START_LABEL: { basic: 3, junior: 2 },
  JUNIOR_PLAYBACK: 0.9,
  DIAG_BANDS: [40, 55, 70, 85],
  DIAG_BAND_RATING: [950, 1075, 1200, 1325, 1450],
  RECALIB_MIN_N: 30,
  RECALIB_K: 8,
};

export const xpCorrect = (label) => Math.round(10 * (1 + 0.2 * (label - 1)));
export const expectedP = (rStudent, rQuestion) =>
  1 / (1 + Math.pow(10, (rQuestion - rStudent) / ENGINE.ELO_SCALE));
