// ===== 벽 / 구멍 시스템 (사람 모양 실루엣) =====
// 구멍 = "따라 해야 할 포즈의 사람 실루엣". 벽 = 나머지 반투명 패널.
// 실루엣을 플레이어의 현재 어깨너비(S)에 비례시켜 그려 거리(원근)에 무관하게 공정.
// 실루엣이 포즈 자체이므로, 그 포즈를 만들어야만 몸이 구멍 안에 들어간다.

import { MASK_W, MASK_H, POSES } from './config.js';

// 실루엣 관절 연결(굵은 캡슐로 그림)
const LINKS = [
  ['sL', 'sR'], ['neck', 'pelvis'],
  ['sL', 'eL'], ['eL', 'wL'], ['sR', 'eR'], ['eR', 'wR'],
  ['hL', 'hR'], ['hL', 'kL'], ['kL', 'aL'], ['hR', 'kR'], ['kR', 'aR'],
];

// 포즈의 사람 실루엣을 ctx에 채워 그린다.
// geom = { cx, cy, S, extraRot, extraDX, thickBoost }
export function fillHole(ctx, wall, geom) {
  const pose = POSES[wall.pose] || POSES.stand;
  const S = geom.S;
  const dx = geom.extraDX || 0;
  const rot = (wall.rot || 0) + (geom.extraRot || 0);
  // 사지 두께(어깨너비 비례) + 여유(margin) + 시각용 보강(thickBoost)
  const thick = S * (0.6 + (wall.margin || 0.4) * 0.7) * (1 + (geom.thickBoost || 0));
  const headR = S * (0.42 + (wall.margin || 0.4) * 0.35) * (1 + (geom.thickBoost || 0));

  // 파생 관절(목·골반 중심)
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const joints = { ...pose, neck: mid(pose.sL, pose.sR), pelvis: mid(pose.hL, pose.hR) };

  ctx.save();
  ctx.translate(geom.cx + dx, geom.cy);
  ctx.rotate(rot);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = thick;
  ctx.strokeStyle = ctx.fillStyle;

  for (const [a, b] of LINKS) {
    const pa = joints[a], pb = joints[b];
    if (!pa || !pb) continue;
    ctx.beginPath();
    ctx.moveTo(pa[0] * S, pa[1] * S);
    ctx.lineTo(pb[0] * S, pb[1] * S);
    ctx.stroke();
  }
  // 머리
  const h = joints.head;
  ctx.beginPath();
  ctx.arc(h[0] * S, h[1] * S, headR, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

// 충돌 판정용 벽 마스크: Uint8Array(MASK_W*MASK_H), 벽=1 / 구멍(사람 실루엣)=0
export function buildWallMask(maskCanvas, wall, geom) {
  const ctx = maskCanvas.getContext('2d', { willReadFrequently: true });
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, MASK_W, MASK_H);
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, MASK_W, MASK_H);
  // 사람 실루엣 펀칭(thickBoost 없이 = 실제 판정 영역)
  ctx.globalCompositeOperation = 'destination-out';
  ctx.fillStyle = '#000';
  fillHole(ctx, wall, { ...geom, thickBoost: 0 });
  ctx.globalCompositeOperation = 'source-over';

  const img = ctx.getImageData(0, 0, MASK_W, MASK_H).data;
  const mask = new Uint8Array(MASK_W * MASK_H);
  for (let i = 0, j = 3; i < mask.length; i++, j += 4) mask[i] = img[j] > 40 ? 1 : 0;
  return mask;
}
