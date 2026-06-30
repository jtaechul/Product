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

// ===== 장애물 피하기(벽 사이 미니 이벤트) =====
export const DODGE_TRAVEL_SEC = 1.45;    // 공이 날아오는 시간
export const DODGE_HIT_UNITS = 1.1;      // 충돌 반경(어깨너비 배수) — 이만큼 안 비키면 맞음
export const DODGE_SCORE = 30;           // 성공 기본 점수(콤보로 증가)
export const DODGE_FROM_WALL = 1;        // 이 벽 이후부터 등장
export const DODGE_CHANCE = 0.6;         // 벽 통과 후 등장 확률
export const DODGE_GAP_SEC = 0.42;       // 연속 장애물 사이 간격

// 몸 막대 두께(어깨너비 대비 비율). 충돌 판정 마스크에 사용.
export const BODY_THICKNESS_RATIO = 0.55;

// ===== 사람 모양(포즈) 실루엣 정의 =====
// 구멍 = "따라 해야 할 포즈의 사람 실루엣". 관절 좌표는 어깨너비(S) 단위,
// 몸 중심 기준 상대좌표(오른쪽 +x, 아래 +y). 플레이어가 이 포즈를 만들어야 통과.
// 관절: head, sL/sR(어깨), eL/eR(팔꿈치), wL/wR(손목), hL/hR(골반), kL/kR(무릎), aL/aR(발목)
// ⚠️ 모든 포즈의 '발(ankle)'은 바닥 높이(y≈1.7)에 둔다. 플레이어는 늘 바닥에 발을 딛고 있으므로,
// 웅크려도/다리를 벌려도 발끝은 바닥에 있다. (발이 떠 있으면 실제 발이 구멍 밖으로 벗어남)
const TORSO = { head: [0, -1.5], sL: [-0.5, -1.12], sR: [0.5, -1.12], hL: [-0.26, 0.18], hR: [0.26, 0.18] };
const LEGS_STRAIGHT = { kL: [-0.28, 0.95], kR: [0.28, 0.95], aL: [-0.3, 1.7], aR: [0.3, 1.7] };
const LEGS_SPREAD = { kL: [-0.5, 1.05], kR: [0.5, 1.05], aL: [-0.92, 1.66], aR: [0.92, 1.66] }; // 발은 바닥 근처

export const POSES = {
  // 차렷: 팔 내림
  stand: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.6, -0.5], eR: [0.6, -0.5], wL: [-0.62, 0.1], wR: [0.62, 0.1] },
  // T자: 양팔 수평
  tpose: { ...TORSO, ...LEGS_STRAIGHT, eL: [-1.05, -1.12], eR: [1.05, -1.12], wL: [-1.7, -1.12], wR: [1.7, -1.12] },
  // 별(X)자: 양팔 위로 벌리고 다리 벌림(발은 바닥)
  star: { ...TORSO, ...LEGS_SPREAD, eL: [-0.95, -1.7], eR: [0.95, -1.7], wL: [-1.45, -2.1], wR: [1.45, -2.1] },
  // 한 손 들기(오른팔 위)
  oneup: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.6, -0.5], wL: [-0.62, 0.1], eR: [0.7, -1.7], wR: [0.95, -2.2] },
  // 웅크리기: 상체를 낮추고 무릎을 굽히되 발은 바닥에 그대로(세로로 압축)
  crouch: {
    head: [0, -0.22], sL: [-0.5, 0.0], sR: [0.5, 0.0], hL: [-0.26, 0.79], hR: [0.26, 0.79],
    eL: [-0.6, 0.38], eR: [0.6, 0.38], wL: [-0.62, 0.74], wR: [0.62, 0.74],
    kL: [-0.28, 1.25], kR: [0.28, 1.25], aL: [-0.3, 1.7], aR: [0.3, 1.7],
  },

  // ===== K-POP 댄스 시그니처 포즈(몸 실루엣 재현) =====
  // 블랙홀(아이브): 양팔 위로 둥글게 모아 동그라미
  blackhole: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.72, -1.65], eR: [0.72, -1.65], wL: [-0.3, -2.1], wR: [0.3, -2.1] },
  // 뱅뱅(아이브): 양팔 위로 쫙 벌려 V
  bangbang: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.95, -1.55], eR: [0.95, -1.55], wL: [-1.45, -2.0], wR: [1.45, -2.0] },
  // 에프터라이크(아이브): 한 팔 위로 가리키고 한 손 허리
  afterlike: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.72, -0.5], wL: [-0.33, 0.05], eR: [0.78, -1.55], wR: [1.05, -2.05] },
  // it's me(아일릿): 양 팔꿈치 넓게, 양손 가슴 앞으로
  itsme: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.95, -0.7], eR: [0.95, -0.7], wL: [-0.18, -0.62], wR: [0.18, -0.62] },
  // 빌려온 고양이(아일릿): 양손 머리 옆 고양이 손
  cat: { ...TORSO, ...LEGS_STRAIGHT, eL: [-0.78, -0.85], eR: [0.78, -0.85], wL: [-0.78, -1.5], wR: [0.78, -1.5] },
  // 마그넷(아일릿): 한 팔 위·한 팔 아래 대각선 + 다리 살짝 벌림
  magnet: {
    ...TORSO, eR: [0.8, -1.5], wR: [1.1, -1.95], eL: [-0.72, -0.3], wL: [-1.0, 0.25],
    kL: [-0.4, 0.98], kR: [0.4, 0.98], aL: [-0.55, 1.68], aR: [0.55, 1.68],
  },

  // ===== 상급자 아크로바틱 포즈 =====
  // 플라밍고: 한 다리(오른발) 딛고, 왼다리 옆으로 들기 + 양팔 균형
  flamingo: {
    ...TORSO, eL: [-1.0, -1.12], eR: [1.0, -1.12], wL: [-1.6, -1.12], wR: [1.6, -1.12],
    kR: [0.12, 0.95], aR: [0.12, 1.7], kL: [-0.7, 0.5], aL: [-1.05, 0.78],
  },
  // 런지: 다리를 크게 벌려 낮춘 자세 + 양팔 벌림(아크로바틱)
  lunge: {
    head: [0, -1.2], sL: [-0.5, -0.85], sR: [0.5, -0.85], hL: [-0.3, 0.48], hR: [0.3, 0.48],
    eL: [-0.95, -0.85], eR: [0.95, -0.85], wL: [-1.6, -0.85], wR: [1.6, -0.85],
    kL: [-0.95, 1.0], kR: [0.95, 1.0], aL: [-1.25, 1.7], aR: [1.25, 1.7],
  },
  // 트위스트: 상체 비틀기(한 팔 위 대각선, 다리 모음) — rot과 함께 쓰면 역동적
  twist: {
    ...TORSO, eR: [0.5, -1.6], wR: [0.75, -2.1], eL: [-0.85, -0.2], wL: [-1.15, 0.35],
    kL: [-0.2, 0.95], kR: [0.2, 0.95], aL: [-0.22, 1.7], aR: [0.22, 1.7],
  },
};

// ===== 벽(스테이지) 정의 =====
// pose: 위 POSES 키. rot: 실루엣 전체 기울임(라디안). margin: 여유(클수록 두껍게=쉬움).
// approachSpeed: 접근 속도. variant: normal/rotate(회전 접근)/moving(좌우 이동).
// ⚠️ 연속으로 같은 모양(pose)이 나오지 않도록 배열함(바로 옆 벽과 항상 다른 포즈).
export const STAGE_WALLS = [
  // ── 스테이지 1: 입문 (느리고 넉넉) ──
  { id: 'w01', level: 1, pose: 'stand',  rot: 0,     margin: 0.60, approachSpeed: 0.9,  variant: 'normal' },
  { id: 'w02', level: 1, pose: 'tpose',  rot: 0,     margin: 0.56, approachSpeed: 1.0,  variant: 'normal' },
  { id: 'w03', level: 1, pose: 'oneup',  rot: 0,     margin: 0.54, approachSpeed: 1.0,  variant: 'normal' },
  { id: 'w04', level: 1, pose: 'star',   rot: 0,     margin: 0.54, approachSpeed: 1.05, variant: 'normal' },
  { id: 'w05', level: 2, pose: 'crouch', rot: 0,     margin: 0.54, approachSpeed: 1.05, variant: 'normal' },
  { id: 'w06', level: 2, pose: 'stand',  rot: -0.32, margin: 0.50, approachSpeed: 1.1,  variant: 'normal' },
  { id: 'w07', level: 2, pose: 'tpose',  rot: 0,     margin: 0.48, approachSpeed: 1.1,  variant: 'normal' },
  { id: 'd01', level: 2, pose: 'blackhole', rot: 0,  margin: 0.54, approachSpeed: 1.1,  variant: 'normal', title: '블랙홀', artist: '아이브' },
  { id: 'w08', level: 3, pose: 'star',   rot: 0,     margin: 0.50, approachSpeed: 1.15, variant: 'normal' },
  { id: 'w09', level: 3, pose: 'oneup',  rot: 0,     margin: 0.50, approachSpeed: 1.15, variant: 'normal' },
  { id: 'w10', level: 3, pose: 'crouch', rot: 0,     margin: 0.46, approachSpeed: 1.2,  variant: 'normal' },
  { id: 'd02', level: 3, pose: 'bangbang', rot: 0,   margin: 0.52, approachSpeed: 1.2,  variant: 'normal', title: '뱅뱅', artist: '아이브' },
  // ── 스테이지 2: 성장 ──
  { id: 'w11', level: 4, pose: 'stand',  rot: 0.5,   margin: 0.46, approachSpeed: 1.25, variant: 'normal' },
  { id: 'w12', level: 4, pose: 'tpose',  rot: 0,     margin: 0.44, approachSpeed: 1.25, variant: 'normal' },
  { id: 'w13', level: 4, pose: 'star',   rot: 0,     margin: 0.42, approachSpeed: 1.3,  variant: 'rotate' },
  { id: 'd03', level: 4, pose: 'itsme',  rot: 0,     margin: 0.52, approachSpeed: 1.25, variant: 'normal', title: "it's me", artist: '아일릿' },
  { id: 'w14', level: 5, pose: 'oneup',  rot: 0,     margin: 0.44, approachSpeed: 1.3,  variant: 'moving' },
  { id: 'w15', level: 5, pose: 'crouch', rot: 0,     margin: 0.44, approachSpeed: 1.3,  variant: 'normal' },
  { id: 'w16', level: 5, pose: 'stand',  rot: -0.55, margin: 0.42, approachSpeed: 1.35, variant: 'normal' },
  { id: 'd04', level: 5, pose: 'cat',    rot: 0,     margin: 0.52, approachSpeed: 1.3,  variant: 'normal', title: '빌려온 고양이', artist: '아일릿' },
  { id: 'w17', level: 6, pose: 'tpose',  rot: 0,     margin: 0.40, approachSpeed: 1.35, variant: 'normal' },
  { id: 'w18', level: 6, pose: 'star',   rot: 0,     margin: 0.40, approachSpeed: 1.4,  variant: 'rotate' },
  { id: 'w19', level: 6, pose: 'oneup',  rot: 0,     margin: 0.40, approachSpeed: 1.4,  variant: 'normal' },
  { id: 'd05', level: 6, pose: 'afterlike', rot: 0,  margin: 0.50, approachSpeed: 1.4,  variant: 'normal', title: '에프터라이크', artist: '아이브' },
  // ── 스테이지 3: 결전 (빠르고 변형 多) ──
  { id: 'w20', level: 7, pose: 'crouch', rot: 0,     margin: 0.40, approachSpeed: 1.45, variant: 'normal' },
  { id: 'w21', level: 7, pose: 'stand',  rot: 0.5,   margin: 0.40, approachSpeed: 1.5,  variant: 'normal' },
  { id: 'w22', level: 7, pose: 'tpose',  rot: 0,     margin: 0.38, approachSpeed: 1.5,  variant: 'normal' },
  { id: 'd06', level: 7, pose: 'magnet', rot: 0,     margin: 0.48, approachSpeed: 1.45, variant: 'normal', title: '마그넷', artist: '아일릿' },
  { id: 'w23', level: 8, pose: 'star',   rot: 0,     margin: 0.38, approachSpeed: 1.55, variant: 'rotate' },
  { id: 'w24', level: 8, pose: 'crouch', rot: 0,     margin: 0.40, approachSpeed: 1.55, variant: 'normal' },
  { id: 'w25', level: 8, pose: 'oneup',  rot: 0,     margin: 0.38, approachSpeed: 1.6,  variant: 'moving' },
  { id: 'w26', level: 8, pose: 'tpose',  rot: 0,     margin: 0.34, approachSpeed: 1.7,  variant: 'rotate' },
];

// ── 초보자: 느리고 넉넉, 변형·장애물 적음, 기본 포즈 위주 ──
export const BEGINNER_WALLS = [
  { id: 'b01', level: 1, pose: 'stand',  rot: 0, margin: 0.66, approachSpeed: 0.8, variant: 'normal' },
  { id: 'b02', level: 1, pose: 'tpose',  rot: 0, margin: 0.64, approachSpeed: 0.85, variant: 'normal' },
  { id: 'b03', level: 1, pose: 'oneup',  rot: 0, margin: 0.62, approachSpeed: 0.85, variant: 'normal' },
  { id: 'b04', level: 1, pose: 'stand',  rot: 0, margin: 0.64, approachSpeed: 0.9, variant: 'normal' },
  { id: 'b05', level: 2, pose: 'star',   rot: 0, margin: 0.62, approachSpeed: 0.9, variant: 'normal' },
  { id: 'b06', level: 2, pose: 'crouch', rot: 0, margin: 0.62, approachSpeed: 0.95, variant: 'normal' },
  { id: 'bd1', level: 2, pose: 'blackhole', rot: 0, margin: 0.62, approachSpeed: 0.9, variant: 'normal', title: '블랙홀', artist: '아이브' },
  { id: 'b07', level: 3, pose: 'tpose',  rot: 0, margin: 0.60, approachSpeed: 0.95, variant: 'normal' },
  { id: 'b08', level: 3, pose: 'oneup',  rot: 0, margin: 0.60, approachSpeed: 1.0, variant: 'normal' },
  { id: 'b09', level: 3, pose: 'stand',  rot: 0, margin: 0.62, approachSpeed: 1.0, variant: 'normal' },
  { id: 'bd2', level: 3, pose: 'cat',    rot: 0, margin: 0.60, approachSpeed: 0.95, variant: 'normal', title: '빌려온 고양이', artist: '아일릿' },
  { id: 'b10', level: 4, pose: 'star',   rot: 0, margin: 0.58, approachSpeed: 1.0, variant: 'normal' },
  { id: 'b11', level: 4, pose: 'crouch', rot: 0, margin: 0.60, approachSpeed: 1.05, variant: 'normal' },
  { id: 'b12', level: 4, pose: 'tpose',  rot: 0, margin: 0.58, approachSpeed: 1.05, variant: 'normal' },
  { id: 'b13', level: 5, pose: 'oneup',  rot: 0, margin: 0.58, approachSpeed: 1.1, variant: 'normal' },
  { id: 'b14', level: 5, pose: 'stand',  rot: 0, margin: 0.60, approachSpeed: 1.1, variant: 'normal' },
];

// ── 상급자: 기본자세 없음, 아크로바틱/역동(이동·회전), 타이트, 빠름 ──
export const ADVANCED_WALLS = [
  { id: 'a01', level: 1, pose: 'star',     rot: 0,    margin: 0.44, approachSpeed: 1.2, variant: 'rotate' },
  { id: 'a02', level: 1, pose: 'flamingo', rot: 0,    margin: 0.44, approachSpeed: 1.2, variant: 'normal' },
  { id: 'a03', level: 2, pose: 'tpose',    rot: 0,    margin: 0.40, approachSpeed: 1.25, variant: 'moving' },
  { id: 'a04', level: 2, pose: 'lunge',    rot: 0,    margin: 0.44, approachSpeed: 1.25, variant: 'normal' },
  { id: 'a05', level: 2, pose: 'oneup',    rot: 0,    margin: 0.40, approachSpeed: 1.3, variant: 'moving' },
  { id: 'a06', level: 3, pose: 'twist',    rot: 0,    margin: 0.42, approachSpeed: 1.3, variant: 'normal' },
  { id: 'ad1', level: 3, pose: 'blackhole', rot: 0,   margin: 0.46, approachSpeed: 1.25, variant: 'normal', title: '블랙홀', artist: '아이브' },
  { id: 'a07', level: 3, pose: 'crouch',   rot: 0,    margin: 0.40, approachSpeed: 1.35, variant: 'normal' },
  { id: 'a08', level: 4, pose: 'star',     rot: 0,    margin: 0.38, approachSpeed: 1.35, variant: 'rotate' },
  { id: 'a09', level: 4, pose: 'flamingo', rot: 0.2,  margin: 0.42, approachSpeed: 1.4, variant: 'normal' },
  { id: 'ad2', level: 4, pose: 'bangbang', rot: 0,    margin: 0.46, approachSpeed: 1.3, variant: 'normal', title: '뱅뱅', artist: '아이브' },
  { id: 'a10', level: 5, pose: 'lunge',    rot: 0,    margin: 0.38, approachSpeed: 1.4, variant: 'normal' },
  { id: 'a11', level: 5, pose: 'tpose',    rot: 0,    margin: 0.36, approachSpeed: 1.45, variant: 'moving' },
  { id: 'ad3', level: 5, pose: 'cat',      rot: 0,    margin: 0.46, approachSpeed: 1.35, variant: 'normal', title: '빌려온 고양이', artist: '아일릿' },
  { id: 'a12', level: 6, pose: 'twist',    rot: -0.2, margin: 0.38, approachSpeed: 1.45, variant: 'rotate' },
  { id: 'a13', level: 6, pose: 'oneup',    rot: 0,    margin: 0.36, approachSpeed: 1.5, variant: 'moving' },
  { id: 'a14', level: 6, pose: 'crouch',   rot: 0,    margin: 0.38, approachSpeed: 1.5, variant: 'normal' },
  { id: 'ad4', level: 6, pose: 'magnet',   rot: 0,    margin: 0.44, approachSpeed: 1.4, variant: 'normal', title: '마그넷', artist: '아일릿' },
  { id: 'a15', level: 7, pose: 'star',     rot: 0,    margin: 0.36, approachSpeed: 1.55, variant: 'rotate' },
  { id: 'a16', level: 7, pose: 'flamingo', rot: -0.2, margin: 0.38, approachSpeed: 1.55, variant: 'normal' },
  { id: 'a17', level: 7, pose: 'lunge',    rot: 0,    margin: 0.36, approachSpeed: 1.6, variant: 'normal' },
  { id: 'ad5', level: 7, pose: 'itsme',    rot: 0,    margin: 0.44, approachSpeed: 1.45, variant: 'normal', title: "it's me", artist: '아일릿' },
  { id: 'a18', level: 8, pose: 'twist',    rot: 0.2,  margin: 0.36, approachSpeed: 1.6, variant: 'rotate' },
  { id: 'a19', level: 8, pose: 'tpose',    rot: 0,    margin: 0.34, approachSpeed: 1.65, variant: 'moving' },
  { id: 'ad6', level: 8, pose: 'afterlike', rot: 0,   margin: 0.44, approachSpeed: 1.5, variant: 'normal', title: '에프터라이크', artist: '아이브' },
  { id: 'a20', level: 8, pose: 'star',     rot: 0,    margin: 0.32, approachSpeed: 1.8, variant: 'rotate' },
];

// ===== 난이도 모드 =====
// walls: 사용할 벽 목록 / lives: 라이프 / approachSecMul: 접근 시간 배수(클수록 느림=쉬움)
// marginAdd: 모든 벽 여유 가감 / music: 배경음악 인덱스(0/1/2) / dodge: 장애물 설정
export const MODES = {
  beginner: {
    key: 'beginner', name: '초보자', emoji: '🌱', walls: 'BEGINNER',
    lives: 5, approachSecMul: 1.3, marginAdd: 0.10, music: 0, hitUnits: 0.95,
    dodge: { from: 4, chance: 0.25, maxCount: 1, spread: false },
  },
  intermediate: {
    key: 'intermediate', name: '중급자', emoji: '🔥', walls: 'STAGE',
    lives: 3, approachSecMul: 1.0, marginAdd: 0.0, music: 1, hitUnits: 1.1,
    dodge: { from: 1, chance: 0.6, maxCount: 3, spread: false },
  },
  advanced: {
    key: 'advanced', name: '상급자', emoji: '💀', walls: 'ADVANCED',
    lives: 3, approachSecMul: 0.82, marginAdd: -0.04, music: 2, hitUnits: 1.15,
    dodge: { from: 0, chance: 0.85, maxCount: 4, spread: true },
  },
};

// 포즈별 안내 문구(기울임은 rot로 좌/우 구분)
export const POSE_HINTS = {
  stand: '🧍 차렷! 가만히 서기',
  tpose: '🤸 양팔 쫙! T자',
  star: '⭐ 팔다리 모두 벌려 별 모양!',
  oneup: '🙋 오른손 번쩍 들기',
  crouch: '🦔 웅크려 작아지기!',
  // K-POP 댄스 포즈
  blackhole: '🕳️ 양팔 위로 모아 동그라미!',
  bangbang: '✌️ 양팔 위로 쫙 V!',
  afterlike: '👉 한 팔 위로 가리키기!',
  itsme: '😎 양손 가슴 앞으로!',
  cat: '🐱 양손 머리 옆 고양이!',
  magnet: '🧲 한 팔 위·한 팔 아래 대각선!',
  // 상급 아크로바틱
  flamingo: '🦩 한 발 들고 양팔 균형!',
  lunge: '🤸 다리 크게 벌려 낮추기!',
  twist: '🌀 상체 비틀어 한 팔 위로!',
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
