// ===== 충돌 판정 레이어 (방법 C — 마스크 픽셀 비교) =====
// 스켈레톤을 굵은 선으로 마스크에 그린 뒤, 벽 마스크와 겹친 비율 계산.
// 0 = 완벽 통과, 1 = 완전 충돌.

import { MASK_W, MASK_H, POSE_CONNECTIONS, BODY_THICKNESS_RATIO } from './config.js';

// 몸 마스크를 그린다(미러 좌표). thicknessPx = 막대 두께.
export function drawBodyMask(bodyCtx, landmarks, thicknessPx) {
  bodyCtx.setTransform(1, 0, 0, 1, 0, 0);
  bodyCtx.clearRect(0, 0, MASK_W, MASK_H);
  bodyCtx.strokeStyle = '#fff';
  bodyCtx.fillStyle = '#fff';
  bodyCtx.lineCap = 'round';
  bodyCtx.lineJoin = 'round';
  bodyCtx.lineWidth = thicknessPx;

  const px = (lm) => (1 - lm.x) * MASK_W; // 미러
  const py = (lm) => lm.y * MASK_H;

  for (const [a, b] of POSE_CONNECTIONS) {
    const la = landmarks[a], lb = landmarks[b];
    if (!la || !lb) continue;
    if ((la.visibility ?? 1) < 0.4 || (lb.visibility ?? 1) < 0.4) continue;
    bodyCtx.beginPath();
    bodyCtx.moveTo(px(la), py(la));
    bodyCtx.lineTo(px(lb), py(lb));
    bodyCtx.stroke();
  }
  // 머리(원)
  const head = landmarks[0];
  if (head && (head.visibility ?? 1) >= 0.4) {
    bodyCtx.beginPath();
    bodyCtx.arc(px(head), py(head), thicknessPx * 0.9, 0, Math.PI * 2);
    bodyCtx.fill();
  }
}

// 몸 마스크 vs 벽 마스크 → 충돌률
export function computeCollisionRate(bodyCtx, wallMask) {
  const data = bodyCtx.getImageData(0, 0, MASK_W, MASK_H).data;
  let bodyPixels = 0, collide = 0;
  for (let i = 0, j = 3; i < wallMask.length; i++, j += 4) {
    if (data[j] > 0) {
      bodyPixels++;
      if (wallMask[i] === 1) collide++;
    }
  }
  if (bodyPixels === 0) return 1.0; // 인식 실패 → 최악 처리
  return collide / bodyPixels;
}

// 어깨너비(정규화) → 마스크 두께 픽셀
export function bodyThicknessFromShoulder(shoulderNorm) {
  const shoulderPx = shoulderNorm * MASK_W;
  return Math.max(6, shoulderPx * BODY_THICKNESS_RATIO);
}
