// ===== HoleDash 설정 / 데이터 =====
// 수치는 한곳에 모아 플레이 테스트로 미세 조정.

// MediaPipe Pose 33 랜드마크 인덱스 중 주요 부위
export const LM = {
  NOSE: 0,
  L_SHOULDER: 11, R_SHOULDER: 12,
  L_ELBOW: 13, R_ELBOW: 14,
  L_WRIST: 15, R_WRIST: 16,
  L_HIP: 23, R_HIP: 24,
  L_KNEE: 25, R_KNEE: 26,
  L_ANKLE: 27, R_ANKLE: 28,
};

// 뼈대 연결(몸통/팔/다리). 손가락·얼굴 세부는 생략 → 충돌 판정용 굵은 막대 사람.
export const POSE_CONNECTIONS = [
  // 몸통
  [11, 12], [11, 23], [12, 24], [23, 24],
  // 왼팔
  [11, 13], [13, 15],
  // 오른팔
  [12, 14], [14, 16],
  // 왼다리
  [23, 25], [25, 27],
  // 오른다리
  [24, 26], [26, 28],
  // 머리(어깨 중심 → 코)
  [11, 0], [12, 0],
];

// 등급 테이블 (충돌률 기준). rate 0 = 완벽 통과, 1 = 완전 충돌.
export const GRADES = [
  { grade: 'PERFECT', max: 0.03, score: 100, color: '#57e389', label: '완벽!' },
  { grade: 'GREAT',   max: 0.10, score: 70,  color: '#4dd0ff', label: '훌륭해!' },
  { grade: 'GOOD',    max: 0.20, score: 40,  color: '#ffffff', label: '통과!' },
  { grade: 'OUCH',    max: 0.40, score: 10,  color: '#ffd23f', label: '아슬아슬!' },
  { grade: 'CRASH',   max: 1.01, score: 0,   color: '#ff5c5c', label: '쾅!' },
];

export function gradeFromRate(rate) {
  for (const g of GRADES) if (rate <= g.max) return g;
  return GRADES[GRADES.length - 1];
}

// 콤보 배수: 연속 GREAT 이상 횟수 → 배수
export function comboMultiplier(streak) {
  if (streak >= 5) return 2.0;
  if (streak >= 3) return 1.5;
  if (streak >= 2) return 1.2;
  return 1.0;
}

// 마스크 해상도(연산 절감용). 화면보다 작게.
export const MASK_W = 256;
export const MASK_H = 144;

// 라이프(스테이지 모드)
export const START_LIFE = 3;

// 벽 접근 시간(초) — approachSpeed로 나눔
export const BASE_APPROACH_SEC = 4.2;

// 판정 후 다음 벽까지 텀(초)
export const INTER_WALL_SEC = 1.4;

// 몸 막대 두께(어깨너비 대비 비율). 충돌 판정 마스크에 사용.
export const BODY_THICKNESS_RATIO = 0.55;

// ===== 벽(스테이지) 정의 =====
// holeShape: 구멍 모양. holeParams: 모양별 파라미터(어깨너비/키 기준 상대값).
// margin: 구멍 여유(클수록 쉬움). approachSpeed: 접근 속도 배수. variant: 변형.
export const STAGE_WALLS = [
  { id: 'w01', level: 1, holeShape: 'rect_vertical', holeParams: { w: 1.7, h: 2.3 }, margin: 0.35, approachSpeed: 0.9,  variant: 'normal' },
  { id: 'w02', level: 1, holeShape: 'rect_vertical', holeParams: { w: 1.5, h: 2.2 }, margin: 0.28, approachSpeed: 1.0,  variant: 'normal' },
  { id: 'w03', level: 2, holeShape: 'tpose',         holeParams: { span: 2.4, h: 1.7 }, margin: 0.30, approachSpeed: 1.0,  variant: 'normal' },
  { id: 'w04', level: 2, holeShape: 'tpose',         holeParams: { span: 2.2, h: 1.6 }, margin: 0.24, approachSpeed: 1.1,  variant: 'normal' },
  { id: 'w05', level: 3, holeShape: 'side_left',     holeParams: { w: 1.9, h: 1.9 }, margin: 0.28, approachSpeed: 1.1,  variant: 'normal' },
  { id: 'w06', level: 3, holeShape: 'side_right',    holeParams: { w: 1.9, h: 1.9 }, margin: 0.24, approachSpeed: 1.2,  variant: 'normal' },
  { id: 'w07', level: 4, holeShape: 'cross',         holeParams: { span: 2.5, h: 2.3 }, margin: 0.26, approachSpeed: 1.2,  variant: 'normal' },
  { id: 'w08', level: 4, holeShape: 'cross',         holeParams: { span: 2.3, h: 2.2 }, margin: 0.20, approachSpeed: 1.3,  variant: 'normal' },
  { id: 'w09', level: 5, holeShape: 'tilt_left',     holeParams: { w: 1.8, h: 2.0 }, margin: 0.24, approachSpeed: 1.3,  variant: 'normal' },
  { id: 'w10', level: 5, holeShape: 'tilt_right',    holeParams: { w: 1.8, h: 2.0 }, margin: 0.20, approachSpeed: 1.4,  variant: 'normal' },
  { id: 'w11', level: 6, holeShape: 'crouch',        holeParams: { w: 1.9, h: 1.25 }, margin: 0.26, approachSpeed: 1.3,  variant: 'normal' },
  { id: 'w12', level: 4, holeShape: 'cross',         holeParams: { span: 2.4, h: 2.2 }, margin: 0.22, approachSpeed: 1.4,  variant: 'rotate' },
  { id: 'w13', level: 5, holeShape: 'side_left',     holeParams: { w: 1.8, h: 1.9 }, margin: 0.20, approachSpeed: 1.5,  variant: 'moving' },
  { id: 'w14', level: 6, holeShape: 'crouch',        holeParams: { w: 1.8, h: 1.2 },  margin: 0.20, approachSpeed: 1.5,  variant: 'normal' },
  { id: 'w15', level: 6, holeShape: 'tpose',         holeParams: { span: 2.5, h: 1.7 }, margin: 0.16, approachSpeed: 1.6,  variant: 'rotate' },
];

// 각 구멍 모양 안내 문구(플레이어에게 무슨 포즈인지)
export const POSE_HINTS = {
  rect_vertical: '🧍 차렷! 가만히 서기',
  tpose: '🤸 양팔 쫙! T자',
  side_left: '👈 왼쪽으로 몸 기울이기',
  side_right: '👉 오른쪽으로 몸 기울이기',
  cross: '⭐ 팔다리 모두 벌려 X자!',
  tilt_left: '↖️ 몸을 왼쪽으로 비스듬히',
  tilt_right: '↗️ 몸을 오른쪽으로 비스듬히',
  crouch: '🦔 웅크려 작아지기!',
};

// 연습 벽(점수 미반영)
export const PRACTICE_WALL = { id: 'practice', level: 1, holeShape: 'rect_vertical', holeParams: { w: 1.9, h: 2.4 }, margin: 0.45, approachSpeed: 0.75, variant: 'normal' };

// 순위 칭호
export const RANK_TITLES = ['구멍의 제왕 👑', '날쌘 통과러 ⚡', '구멍 마스터 🎯'];
export const CONSOLATION_TITLE = '용감한 도전상 🎖️';
