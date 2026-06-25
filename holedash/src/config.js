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

// ===== 사람 모양(포즈) 실루엣 정의 =====
// 구멍 = "따라 해야 할 포즈의 사람 실루엣". 관절 좌표는 어깨너비(S) 단위,
// 몸 중심 기준 상대좌표(오른쪽 +x, 아래 +y). 플레이어가 이 포즈를 만들어야 통과.
// 관절: head, sL/sR(어깨), eL/eR(팔꿈치), wL/wR(손목), hL/hR(골반), kL/kR(무릎), aL/aR(발목)
const TORSO = { head: [0, -1.5], sL: [-0.5, -1.12], sR: [0.5, -1.12], hL: [-0.26, 0.18], hR: [0.26, 0.18] };
const LEGS_STRAIGHT = { kL: [-0.28, 0.95], kR: [0.28, 0.95], aL: [-0.3, 1.7], aR: [0.3, 1.7] };
const LEGS_SPREAD = { kL: [-0.62, 0.85], kR: [0.62, 0.85], aL: [-1.05, 1.5], aR: [1.05, 1.5] };

export const POSES = {
  // 차렷: 팔 내림
  stand: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.6, -0.5], eR: [0.6, -0.5], wL: [-0.62, 0.1], wR: [0.62, 0.1] },
  // T자: 양팔 수평
  tpose: { ...TORSO, ...LEGS_STRAIGHT, eL: [-1.05, -1.12], eR: [1.05, -1.12], wL: [-1.7, -1.12], wR: [1.7, -1.12] },
  // 별(X)자: 양팔 위로 벌리고 다리 벌림
  star: { ...TORSO, ...LEGS_SPREAD, eL: [-0.95, -1.7], eR: [0.95, -1.7], wL: [-1.45, -2.15], wR: [1.45, -2.15] },
  // 한 손 들기(오른팔 위)
  oneup: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.6, -0.5], wL: [-0.62, 0.1], eR: [0.7, -1.7], wR: [0.95, -2.2] },
  // 웅크리기: 전체적으로 낮고 무릎 굽힘
  crouch: {
    head: [0, -0.95], sL: [-0.5, -0.55], sR: [0.5, -0.55], hL: [-0.28, 0.1], hR: [0.28, 0.1],
    eL: [-0.6, -0.2], eR: [0.6, -0.2], wL: [-0.42, 0.25], wR: [0.42, 0.25],
    kL: [-0.5, 0.5], kR: [0.5, 0.5], aL: [-0.28, 0.9], aR: [0.28, 0.9],
  },
};

// ===== 벽(스테이지) 정의 =====
// pose: 위 POSES 키. rot: 실루엣 전체 기울임(라디안). margin: 여유(클수록 두껍게=쉬움).
// approachSpeed: 접근 속도. variant: normal/rotate(회전 접근)/moving(좌우 이동).
export const STAGE_WALLS = [
  { id: 'w01', level: 1, pose: 'stand',  rot: 0,     margin: 0.55, approachSpeed: 0.9, variant: 'normal' },
  { id: 'w02', level: 1, pose: 'stand',  rot: 0,     margin: 0.45, approachSpeed: 1.0, variant: 'normal' },
  { id: 'w03', level: 2, pose: 'tpose',  rot: 0,     margin: 0.50, approachSpeed: 1.0, variant: 'normal' },
  { id: 'w04', level: 2, pose: 'tpose',  rot: 0,     margin: 0.40, approachSpeed: 1.1, variant: 'normal' },
  { id: 'w05', level: 3, pose: 'oneup',  rot: 0,     margin: 0.48, approachSpeed: 1.1, variant: 'normal' },
  { id: 'w06', level: 3, pose: 'stand',  rot: -0.32, margin: 0.48, approachSpeed: 1.2, variant: 'normal' },
  { id: 'w07', level: 3, pose: 'stand',  rot: 0.32,  margin: 0.44, approachSpeed: 1.2, variant: 'normal' },
  { id: 'w08', level: 4, pose: 'star',   rot: 0,     margin: 0.46, approachSpeed: 1.3, variant: 'normal' },
  { id: 'w09', level: 4, pose: 'star',   rot: 0,     margin: 0.38, approachSpeed: 1.3, variant: 'normal' },
  { id: 'w10', level: 5, pose: 'stand',  rot: -0.55, margin: 0.42, approachSpeed: 1.4, variant: 'normal' },
  { id: 'w11', level: 5, pose: 'crouch', rot: 0,     margin: 0.50, approachSpeed: 1.3, variant: 'normal' },
  { id: 'w12', level: 5, pose: 'star',   rot: 0,     margin: 0.40, approachSpeed: 1.4, variant: 'rotate' },
  { id: 'w13', level: 6, pose: 'oneup',  rot: 0,     margin: 0.40, approachSpeed: 1.5, variant: 'moving' },
  { id: 'w14', level: 6, pose: 'crouch', rot: 0,     margin: 0.42, approachSpeed: 1.5, variant: 'normal' },
  { id: 'w15', level: 6, pose: 'tpose',  rot: 0,     margin: 0.34, approachSpeed: 1.6, variant: 'rotate' },
];

// 포즈별 안내 문구(기울임은 rot로 좌/우 구분)
export const POSE_HINTS = {
  stand: '🧍 차렷! 가만히 서기',
  tpose: '🤸 양팔 쫙! T자',
  star: '⭐ 팔다리 모두 벌려 별 모양!',
  oneup: '🙋 오른손 번쩍 들기',
  crouch: '🦔 웅크려 작아지기!',
};
export function poseHint(wall) {
  if (wall.pose === 'stand' && wall.rot < -0.1) return '↖️ 몸을 왼쪽으로 기울이기';
  if (wall.pose === 'stand' && wall.rot > 0.1) return '↗️ 몸을 오른쪽으로 기울이기';
  return POSE_HINTS[wall.pose] || '구멍에 몸을 맞춰요!';
}

// 연습 벽(점수 미반영) — 가장 쉬운 차렷, 여유 크게
export const PRACTICE_WALL = { id: 'practice', level: 1, pose: 'stand', rot: 0, margin: 0.7, approachSpeed: 0.7, variant: 'normal' };

// 순위 칭호
export const RANK_TITLES = ['구멍의 제왕 👑', '날쌘 통과러 ⚡', '구멍 마스터 🎯'];
export const CONSOLATION_TITLE = '용감한 도전상 🎖️';
