// ===== 벽 / 구멍 시스템 =====
// 구멍 = "통과 가능한 빈 영역". 벽 = 나머지 단색 패널.
// 모든 구멍은 플레이어의 현재 어깨너비(S)를 단위로 그려져, 거리(원근)에 무관하게 공정.
// 구멍을 너무 크게 만들지 않고 포즈에 타이트하게 → "그 포즈를 해야 통과"가 성립.

import { MASK_W, MASK_H } from './config.js';

function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
  ctx.fill();
}

// 회전된 둥근 사각형(기울임 포즈용)
function rotatedRect(ctx, cx, cy, w, h, r, angle) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(angle);
  roundRect(ctx, -w / 2, -h / 2, w, h, r);
  ctx.restore();
}

// 구멍 형태를 ctx에 "채워" 그린다(흰색 등). 회전/이동 변형은 geom으로 전달.
// geom = { cx, cy, S, VH, extraRot, extraDX } (모두 mask 좌표계)
export function fillHole(ctx, wall, geom) {
  const { cx, cy, S, VH } = geom;
  const dx = geom.extraDX || 0;
  const rot = geom.extraRot || 0;
  const p = wall.holeParams;
  const M = 1 + (wall.margin || 0.25);
  const X = cx + dx;

  switch (wall.holeShape) {
    case 'rect_vertical': {
      const hw = S * (p.w * 0.5) * M;
      const hh = VH * M;
      if (rot) rotatedRect(ctx, X, cy, hw * 2, hh * 2, hw * 0.7, rot);
      else roundRect(ctx, X - hw, cy - hh, hw * 2, hh * 2, hw * 0.7);
      break;
    }
    case 'tpose': {
      // 몸통+다리(세로) + 양팔(가로 바)
      const bw = S * 0.72 * M;
      const bh = VH * 0.98 * M;
      roundRect(ctx, X - bw, cy - bh * 0.78, bw * 2, bh * 1.78, bw * 0.6);
      const span = S * (p.span * 0.5) * M;
      const armH = S * 0.62 * M;
      const armY = cy - VH * 0.5;
      roundRect(ctx, X - span, armY - armH / 2, span * 2, armH, armH * 0.5);
      break;
    }
    case 'cross': {
      // 별(X)자: 몸통 세로 + 양팔(위쪽 넓게) + 다리(아래 넓게)
      const bw = S * 0.6 * M;
      roundRect(ctx, X - bw, cy - VH * 0.95 * M, bw * 2, VH * 1.9 * M, bw * 0.6);
      const span = S * (p.span * 0.5) * M;
      const armH = S * 0.58 * M;
      roundRect(ctx, X - span, cy - VH * 0.55 - armH / 2, span * 2, armH, armH * 0.5);
      // 다리 벌림(아래 사다리꼴 ~ 넓은 바)
      const legSpan = S * (p.span * 0.42) * M;
      roundRect(ctx, X - legSpan, cy + VH * 0.45, legSpan * 2, VH * 0.55 * M, S * 0.4);
      break;
    }
    case 'side_left':
      rotatedRect(ctx, X, cy, S * p.w * M, VH * 2 * M, S * 0.5 * M, -0.32 + rot);
      break;
    case 'side_right':
      rotatedRect(ctx, X, cy, S * p.w * M, VH * 2 * M, S * 0.5 * M, 0.32 + rot);
      break;
    case 'tilt_left':
      rotatedRect(ctx, X, cy, S * p.w * M, VH * 2 * M, S * 0.5 * M, -0.52 + rot);
      break;
    case 'tilt_right':
      rotatedRect(ctx, X, cy, S * p.w * M, VH * 2 * M, S * 0.5 * M, 0.52 + rot);
      break;
    case 'crouch': {
      // 낮고 넓은 구멍 → 웅크려야 함
      const hw = S * (p.w * 0.5) * M;
      const hh = VH * (p.h * 0.5) * M;
      roundRect(ctx, X - hw, cy + VH * 0.18 - hh, hw * 2, hh * 2, hh * 0.6);
      break;
    }
    default: {
      const hw = S * 0.8 * M;
      roundRect(ctx, X - hw, cy - VH * M, hw * 2, VH * 2 * M, hw * 0.6);
    }
  }
}

// 충돌 판정용 벽 마스크 생성: Uint8Array(MASK_W*MASK_H), 벽=1 / 구멍=0
export function buildWallMask(maskCanvas, wall, geom) {
  const ctx = maskCanvas.getContext('2d', { willReadFrequently: true });
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, MASK_W, MASK_H);
  // 1) 벽 전체 채움
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, MASK_W, MASK_H);
  // 2) 구멍 펀칭(투명)
  ctx.globalCompositeOperation = 'destination-out';
  ctx.fillStyle = '#000';
  fillHole(ctx, wall, geom);
  ctx.globalCompositeOperation = 'source-over';

  const img = ctx.getImageData(0, 0, MASK_W, MASK_H).data;
  const mask = new Uint8Array(MASK_W * MASK_H);
  for (let i = 0, j = 3; i < mask.length; i++, j += 4) {
    mask[i] = img[j] > 40 ? 1 : 0; // 알파 남아있으면 벽
  }
  return mask;
}
