// ===== 렌더 / 연출 레이어 =====
// 웹캠(거울) + 스켈레톤 + 다가오는 벽 + 파티클/플래시.

import { POSE_CONNECTIONS, LM } from './config.js';
import { fillHole } from './walls.js';

export class Renderer {
  constructor(canvas, video) {
    this.canvas = canvas;
    this.video = video;
    this.ctx = canvas.getContext('2d');
    this.W = 0; this.H = 0; this.dpr = 1;
    this.wallLayer = document.createElement('canvas');
    this.wallCtx = this.wallLayer.getContext('2d');
    this.particles = [];
    this.flash = null; // { color, t }
    this.skelTint = null; // {color, t}
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = window.innerWidth, h = window.innerHeight;
    this.W = w; this.H = h;
    this.canvas.width = w * this.dpr;
    this.canvas.height = h * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.wallLayer.width = w * this.dpr;
    this.wallLayer.height = h * this.dpr;
  }

  // 16:9 cover 변환 계산
  _cover() {
    const vw = this.video.videoWidth || 1280;
    const vh = this.video.videoHeight || 720;
    const scale = Math.max(this.W / vw, this.H / vh);
    const dw = vw * scale, dh = vh * scale;
    const ox = (this.W - dw) / 2, oy = (this.H - dh) / 2;
    return { vw, vh, scale, dw, dh, ox, oy };
  }

  // 정규화 좌표 → 화면 px (거울)
  toScreen(nx, ny, cov) {
    const x = this.W - (cov.ox + nx * cov.dw);
    const y = cov.oy + ny * cov.dh;
    return { x, y };
  }

  drawCamera() {
    const ctx = this.ctx;
    ctx.fillStyle = '#05060c';
    ctx.fillRect(0, 0, this.W, this.H);
    if (this.video.readyState < 2) return;
    const cov = this._cover();
    ctx.save();
    ctx.translate(this.W, 0);
    ctx.scale(-1, 1);
    ctx.globalAlpha = 0.92;
    ctx.drawImage(this.video, cov.ox, cov.oy, cov.dw, cov.dh);
    ctx.restore();
    ctx.globalAlpha = 1;
    // 살짝 어둡게 → 스켈레톤·벽 가독성(중립 회색)
    ctx.fillStyle = 'rgba(0,0,0,0.22)';
    ctx.fillRect(0, 0, this.W, this.H);
  }

  drawSkeleton(landmarks) {
    if (!landmarks) return;
    const ctx = this.ctx;
    const cov = this._cover();
    const sw = this._shoulderPx(landmarks, cov);
    // 얇고 깔끔한 오버레이 — 화면 대비 일정 비율 이상으로 두꺼워지지 않게 캡
    const thick = Math.max(5, Math.min(sw * 0.28, Math.min(this.W, this.H) * 0.04));
    // 기본은 흰색(파란색 미사용). 통과/충돌 시에만 초록/빨강 등으로 틴트.
    const tinted = !!this.skelTint;
    const color = tinted ? this.skelTint.color : '#ffffff';
    ctx.save();
    ctx.globalAlpha = tinted ? 0.95 : 0.85;
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.strokeStyle = color;
    ctx.lineWidth = thick;
    ctx.shadowColor = tinted ? this.skelTint.color : 'rgba(0,0,0,0.55)';
    ctx.shadowBlur = 8;
    for (const [a, b] of POSE_CONNECTIONS) {
      const la = landmarks[a], lb = landmarks[b];
      if (!la || !lb) continue;
      if ((la.visibility ?? 1) < 0.4 || (lb.visibility ?? 1) < 0.4) continue;
      const pa = this.toScreen(la.x, la.y, cov);
      const pb = this.toScreen(lb.x, lb.y, cov);
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }
    // 머리(테두리 원)
    const head = landmarks[0];
    if (head && (head.visibility ?? 1) >= 0.4) {
      const p = this.toScreen(head.x, head.y, cov);
      ctx.beginPath(); ctx.arc(p.x, p.y, thick * 1.5, 0, Math.PI * 2);
      ctx.stroke();
    }
    // 관절 점(작게)
    ctx.shadowBlur = 0;
    ctx.fillStyle = color;
    for (const idx of [LM.L_SHOULDER, LM.R_SHOULDER, LM.L_ELBOW, LM.R_ELBOW, LM.L_WRIST, LM.R_WRIST, LM.L_ANKLE, LM.R_ANKLE, LM.L_KNEE, LM.R_KNEE, LM.L_HIP, LM.R_HIP]) {
      const l = landmarks[idx];
      if (!l || (l.visibility ?? 1) < 0.4) continue;
      const p = this.toScreen(l.x, l.y, cov);
      ctx.beginPath(); ctx.arc(p.x, p.y, thick * 0.5, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
  }

  _shoulderPx(landmarks, cov) {
    const a = landmarks[LM.L_SHOULDER], b = landmarks[LM.R_SHOULDER];
    if (!a || !b) return 60;
    const pa = this.toScreen(a.x, a.y, cov), pb = this.toScreen(b.x, b.y, cov);
    return Math.max(30, Math.hypot(pa.x - pb.x, pa.y - pb.y));
  }

  // 화면 좌표계 hole geom 계산(플레이어 중심·어깨너비 기반)
  screenGeom(landmarks) {
    const cov = this._cover();
    const ls = landmarks[LM.L_SHOULDER], rs = landmarks[LM.R_SHOULDER];
    const lh = landmarks[LM.L_HIP], rh = landmarks[LM.R_HIP];
    const sw = this._shoulderPx(landmarks, cov);
    let cx = this.W / 2, cy = this.H / 2;
    if (ls && rs && lh && rh) {
      const a = this.toScreen(ls.x, ls.y, cov), b = this.toScreen(rs.x, rs.y, cov);
      const c = this.toScreen(lh.x, lh.y, cov), d = this.toScreen(rh.x, rh.y, cov);
      cx = (a.x + b.x + c.x + d.x) / 4;
      cy = (a.y + b.y + c.y + d.y) / 4;
    }
    return { cx, cy, S: sw, VH: sw * 1.7 };
  }

  // 다가오는 벽: progress 0→1 (1=판정). geom=화면 좌표. variant 효과 포함.
  // 벽은 반투명 → 뒤의 카메라(나)가 항상 비치고, 사람 모양 구멍만 완전히 뚫림.
  drawWall(wall, geom, progress, timeSec) {
    const eased = progress * progress; // easeIn
    const appScale = 0.16 + 0.84 * eased;
    const alpha = 0.30 + 0.42 * eased; // 최대 ~0.72 → 반투명 회색 벽(뒤 카메라가 비침)
    let extraRot = 0, extraDX = 0;
    if (wall.variant === 'rotate') extraRot = (1 - progress) * 1.4;
    if (wall.variant === 'moving') extraDX = Math.sin(timeSec * 2.2) * geom.S * 1.2 * (1 - progress * 0.3);
    const hgeom = { ...geom, extraRot, extraDX };

    const wc = this.wallCtx;
    wc.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    wc.clearRect(0, 0, this.W, this.H);
    // 벽 패널 — 반투명 회색
    const grad = wc.createLinearGradient(0, 0, 0, this.H);
    grad.addColorStop(0, 'rgba(70,70,74,0.82)');
    grad.addColorStop(1, 'rgba(52,52,56,0.82)');
    wc.globalCompositeOperation = 'source-over';
    wc.fillStyle = grad;
    wc.fillRect(0, 0, this.W, this.H);
    // 사람 모양 구멍의 흰색 외곽선(선) — 살짝 크게 흰색으로 그린 뒤 가운데를 뚫어 '선'만 남김
    wc.save();
    wc.shadowColor = 'rgba(255,255,255,0.4)';
    wc.shadowBlur = 6;
    wc.fillStyle = '#ffffff';
    fillHole(wc, wall, { ...hgeom, thickBoost: 0.11 });
    wc.restore();
    // 실제 사람 모양 구멍 펀칭(완전 투명 → 지금 촬영 중인 카메라 그대로 보임)
    wc.globalCompositeOperation = 'destination-out';
    wc.fillStyle = '#000';
    fillHole(wc, wall, { ...hgeom, thickBoost: 0 });
    wc.globalCompositeOperation = 'source-over';

    // 메인 캔버스에 접근 스케일 적용
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.translate(geom.cx + extraDX, geom.cy);
    ctx.scale(appScale, appScale);
    ctx.translate(-(geom.cx + extraDX), -geom.cy);
    ctx.drawImage(this.wallLayer, 0, 0, this.W, this.H);
    ctx.restore();
  }

  // 날아오는 장애물(공) — 위에서 잠긴 표적으로 떨어진다. progress 0→1 (1=충돌 판정)
  drawObstacle(ob, progress, t) {
    const ctx = this.ctx;
    const R = ob.S * (0.45 + 0.95 * progress);
    const startY = -this.H * 0.12;
    const x = ob.tx;
    const y = startY + (ob.ty - startY) * (progress * progress);

    // 표적 경고 링(맞으면 안 되는 자리)
    ctx.save();
    ctx.globalAlpha = 0.45 + 0.3 * Math.sin(t * 12);
    ctx.strokeStyle = '#ff5c5c';
    ctx.lineWidth = 5;
    ctx.shadowColor = '#ff3030'; ctx.shadowBlur = 16;
    ctx.beginPath(); ctx.arc(ob.tx, ob.ty, ob.S * (1.1 + 0.15 * Math.sin(t * 8)), 0, Math.PI * 2); ctx.stroke();
    ctx.restore();

    // 잔상
    ctx.save();
    ctx.globalAlpha = 0.28;
    ctx.fillStyle = '#ff9a3d';
    ctx.beginPath(); ctx.arc(x, y - R * 1.3, R * 0.7, 0, Math.PI * 2); ctx.fill();
    ctx.restore();

    // 공
    ctx.save();
    const grad = ctx.createRadialGradient(x - R * 0.3, y - R * 0.3, R * 0.1, x, y, R);
    grad.addColorStop(0, '#ffe27a');
    grad.addColorStop(0.6, '#ff8a3d');
    grad.addColorStop(1, '#ff4d2e');
    ctx.fillStyle = grad;
    ctx.shadowColor = '#ff7a2e'; ctx.shadowBlur = 26;
    ctx.beginPath(); ctx.arc(x, y, R, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  // 캘리브레이션 UI: 사람 모양 가이드 + 코너 프레임 + 진행 링 + 상태문구
  drawCalibUI(progress, status, t) {
    const ctx = this.ctx;
    const accent = progress >= 1 ? '#57e389' : (progress > 0 ? '#57e389' : '#ffffff');
    // 살짝 어둡게(집중)
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.fillRect(0, 0, this.W, this.H);

    // 가운데 사람 모양 가이드(여기에 맞춰 서기)
    const frameH = this.H * 0.84;
    const frameW = Math.min(this.W * 0.9, frameH * 0.62);
    const cx = this.W / 2, cy = this.H * 0.48;
    const S = frameW * 0.17;
    ctx.save();
    ctx.globalAlpha = 0.9;
    ctx.shadowColor = 'rgba(255,255,255,0.5)';
    ctx.shadowBlur = 16;
    ctx.fillStyle = `rgba(255,255,255,${0.12 + 0.06 * Math.sin(t * 3)})`;
    fillHole(ctx, { pose: 'stand', rot: 0, margin: 0.4 }, { cx, cy, S, thickBoost: 0 });
    ctx.restore();

    // 코너 브래킷 프레임(스캐너 느낌)
    const fx = cx - frameW / 2, fy = cy - frameH / 2;
    const L = Math.min(frameW, frameH) * 0.12;
    ctx.lineWidth = 6; ctx.lineCap = 'round';
    ctx.strokeStyle = accent;
    ctx.shadowColor = accent; ctx.shadowBlur = 10;
    const corner = (x, y, sx, sy) => {
      ctx.beginPath();
      ctx.moveTo(x + sx * L, y); ctx.lineTo(x, y); ctx.lineTo(x, y + sy * L);
      ctx.stroke();
    };
    corner(fx, fy, 1, 1);
    corner(fx + frameW, fy, -1, 1);
    corner(fx, fy + frameH, 1, -1);
    corner(fx + frameW, fy + frameH, -1, -1);
    ctx.shadowBlur = 0;

    // 진행 링(하단)
    const rx = this.W / 2, ry = this.H * 0.88, R = Math.min(this.W, this.H) * 0.07;
    ctx.lineWidth = Math.max(8, R * 0.22);
    ctx.strokeStyle = 'rgba(255,255,255,0.22)';
    ctx.beginPath(); ctx.arc(rx, ry, R, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = accent;
    ctx.shadowColor = accent; ctx.shadowBlur = 14;
    ctx.beginPath(); ctx.arc(rx, ry, R, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * progress); ctx.stroke();
    ctx.shadowBlur = 0;
    // 링 가운데 %
    ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = `800 ${R * 0.7}px Trebuchet MS, sans-serif`;
    ctx.fillText(progress >= 1 ? '✓' : `${Math.round(progress * 100)}%`, rx, ry);

    // 상태 문구(링 위)
    ctx.font = `800 ${Math.min(this.W, this.H) * 0.045}px Trebuchet MS, sans-serif`;
    const ty = ry - R - this.H * 0.05;
    const tw = ctx.measureText(status).width + 44;
    ctx.fillStyle = 'rgba(0,0,0,0.5)';
    this._roundFill(ctx, this.W / 2 - tw / 2, ty - 6, tw, Math.min(this.W, this.H) * 0.045 + 20, 12);
    ctx.fillStyle = '#fff';
    ctx.textBaseline = 'top';
    ctx.fillText(status, this.W / 2, ty);
    ctx.restore();
  }

  _roundFill(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.fill();
  }

  // 카운트다운 큰 숫자
  drawBigText(text, sub) {
    const ctx = this.ctx;
    ctx.save();
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = `900 ${Math.min(this.W, this.H) * 0.32}px Trebuchet MS, sans-serif`;
    ctx.fillStyle = '#fff';
    ctx.shadowColor = '#000'; ctx.shadowBlur = 24;
    ctx.fillText(text, this.W / 2, this.H * 0.42);
    if (sub) {
      ctx.font = `800 ${Math.min(this.W, this.H) * 0.045}px Trebuchet MS, sans-serif`;
      ctx.fillStyle = '#ffd23f';
      ctx.fillText(sub, this.W / 2, this.H * 0.62);
    }
    ctx.restore();
  }

  // 포즈 안내(상단)
  drawPoseHint(text) {
    const ctx = this.ctx;
    ctx.save();
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.font = `800 ${Math.min(this.W, this.H) * 0.05}px Trebuchet MS, sans-serif`;
    const y = this.H * 0.09;
    ctx.fillStyle = 'rgba(0,0,0,0.45)';
    const tw = ctx.measureText(text).width + 40;
    ctx.fillRect(this.W / 2 - tw / 2, y - 8, tw, Math.min(this.W, this.H) * 0.05 + 22);
    ctx.fillStyle = '#fff';
    ctx.fillText(text, this.W / 2, y);
    ctx.restore();
  }

  // ===== 이펙트 =====
  burst(x, y, color, n = 26) {
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const sp = 2 + Math.random() * 7;
      this.particles.push({
        x, y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 2,
        life: 1, color, size: 3 + Math.random() * 5,
      });
    }
  }
  setFlash(color) { this.flash = { color, t: 1 }; }
  tintSkeleton(color, dur = 0.8) { this.skelTint = { color, t: dur }; }

  updateEffects(dt) {
    for (const p of this.particles) {
      p.x += p.vx; p.y += p.vy; p.vy += 0.4; p.vx *= 0.98; p.life -= dt * 1.6;
    }
    this.particles = this.particles.filter((p) => p.life > 0);
    if (this.flash) { this.flash.t -= dt * 3; if (this.flash.t <= 0) this.flash = null; }
    if (this.skelTint) { this.skelTint.t -= dt; if (this.skelTint.t <= 0) this.skelTint = null; }
  }
  drawEffects() {
    const ctx = this.ctx;
    for (const p of this.particles) {
      ctx.globalAlpha = Math.max(0, p.life);
      ctx.fillStyle = p.color;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
    if (this.flash) {
      ctx.globalAlpha = Math.max(0, this.flash.t) * 0.55;
      ctx.fillStyle = this.flash.color;
      ctx.fillRect(0, 0, this.W, this.H);
      ctx.globalAlpha = 1;
    }
  }
}
