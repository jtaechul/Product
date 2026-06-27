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

  // 고정된 구멍 — 가로 중앙 + '발끝을 바닥선(groundY)에' 맞춰 세움(플레이어는 늘 바닥에 발이 닿음).
  // 위쪽으로 올린 손까지 화면 안에 들어오게 크기를 맞춘다.
  wallGeom(groundY = 0.90) {
    const TOP = 0.12, FIG = 4.8, FOOT = 2.2; // S 단위: 위(손)~중심 2.6, 중심~발 2.2
    const S = Math.max(40, (groundY - TOP) * this.H / FIG);
    const cy = groundY * this.H - FOOT * S;  // 발끝을 바닥선에
    return { cx: this.W / 2, cy, S, VH: S * 1.7 };
  }

  // 플레이어 실제 몸 중심(화면 px) — 장애물 조준·이펙트 위치에 사용
  playerCenter(landmarks) {
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

  // 다가오는 벽: progress 0→1 (1=판정).
  // 화면 전체가 항상 반투명 회색으로 덮이고, 사람 모양 '구멍'만 작게 시작해 커지며 다가온다.
  drawWall(wall, geom, progress, timeSec) {
    const eased = progress * progress; // easeIn
    const holeScale = 0.20 + 0.80 * eased; // 구멍이 점점 커지며 다가옴
    const alpha = 0.66 + 0.06 * eased;     // 반투명 회색(거의 일정)
    let extraRot = 0, extraDX = 0;
    if (wall.variant === 'rotate') extraRot = (1 - progress) * 1.4;
    if (wall.variant === 'moving') extraDX = Math.sin(timeSec * 2.2) * geom.S * 1.2 * (1 - progress * 0.3);
    // 구멍 좌표(어깨너비 단위) 자체를 접근 스케일만큼 키운다 → 회색은 전체 유지, 구멍만 성장
    const hgeom = { cx: geom.cx, cy: geom.cy, S: geom.S * holeScale, extraRot, extraDX: extraDX * holeScale };
    const outline = Math.max(0.10, 0.17 / holeScale); // 작을 땐 선이 너무 가늘어지지 않게 보정

    const wc = this.wallCtx;
    wc.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    wc.clearRect(0, 0, this.W, this.H);
    // 벽 = 화면 전체 반투명 회색
    const grad = wc.createLinearGradient(0, 0, 0, this.H);
    grad.addColorStop(0, 'rgba(72,72,76,1)');
    grad.addColorStop(1, 'rgba(54,54,58,1)');
    wc.globalCompositeOperation = 'source-over';
    wc.fillStyle = grad;
    wc.fillRect(0, 0, this.W, this.H);
    // 사람 모양 구멍의 굵은 흰색 외곽선
    wc.save();
    wc.shadowColor = 'rgba(255,255,255,0.45)';
    wc.shadowBlur = 8;
    wc.fillStyle = '#ffffff';
    fillHole(wc, wall, { ...hgeom, thickBoost: outline });
    wc.restore();
    // 실제 사람 모양 구멍 펀칭(완전 투명 → 카메라 그대로)
    wc.globalCompositeOperation = 'destination-out';
    wc.fillStyle = '#000';
    fillHole(wc, wall, { ...hgeom, thickBoost: 0 });
    wc.globalCompositeOperation = 'source-over';

    // 회색 벽 전체를 1:1로 올림(스케일 없음) — 구멍만 hgeom으로 성장
    this.ctx.save();
    this.ctx.globalAlpha = alpha;
    this.ctx.drawImage(this.wallLayer, 0, 0, this.W, this.H);
    this.ctx.restore();
  }

  // 노래 제목이 옆에서 날아 들어와 가운데에 잠깐 떴다가 사라짐(댄스 벽)
  drawSongTitle(title, artist, elapsed) {
    let alpha = 1, slide = 0;
    if (elapsed < 0.45) { const k = elapsed / 0.45; slide = (1 - k) * (1 - k); alpha = Math.min(1, elapsed / 0.18); }
    else if (elapsed > 1.7) { alpha = Math.max(0, 1 - (elapsed - 1.7) / 0.6); }
    if (alpha <= 0) return;
    const ctx = this.ctx;
    const m = Math.min(this.W, this.H);
    const cx = this.W / 2 + slide * this.W * 0.6;
    const cy = this.H * 0.4;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.textAlign = 'center';
    ctx.shadowColor = 'rgba(0,0,0,0.85)'; ctx.shadowBlur = 18;
    // 제목
    ctx.font = `900 ${m * 0.085}px Trebuchet MS, sans-serif`;
    ctx.fillStyle = '#ffffff';
    ctx.fillText('♪ ' + title, cx, cy);
    // 아티스트
    ctx.font = `800 ${m * 0.042}px Trebuchet MS, sans-serif`;
    ctx.fillStyle = '#ffd23f';
    ctx.fillText(artist, cx, cy + m * 0.07);
    ctx.restore();
  }

  // 날아오는 장애물 — 미니멀한 타깃 레티클 + 매끈한 에너지 오브(꼬리 포함)
  drawObstacle(ob, progress, t) {
    const ctx = this.ctx;
    const R = ob.S * (0.34 + 0.5 * progress);
    const startY = -this.H * 0.14;
    const startX = (ob.sx !== undefined) ? ob.sx : ob.tx;
    const x = startX + (ob.tx - startX) * progress;
    const y = startY + (ob.ty - startY) * (progress * progress);
    const RED = '#ff4d57';

    // --- 타깃 레티클(맞으면 안 되는 자리): 얇은 회전 링 + 십자선 ---
    ctx.save();
    ctx.translate(ob.tx, ob.ty);
    const rr = ob.S * 1.15;
    // 바깥 점선 링(회전)
    ctx.rotate(t * 0.9);
    ctx.strokeStyle = `rgba(255,77,87,${0.5 + 0.25 * Math.sin(t * 6)})`;
    ctx.lineWidth = 2.5;
    ctx.setLineDash([rr * 0.5, rr * 0.32]);
    ctx.beginPath(); ctx.arc(0, 0, rr, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);
    ctx.rotate(-t * 0.9);
    // 안쪽 얇은 링
    ctx.strokeStyle = 'rgba(255,255,255,0.5)';
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(0, 0, rr * 0.62, 0, Math.PI * 2); ctx.stroke();
    // 십자선 틱
    ctx.strokeStyle = RED; ctx.lineWidth = 2;
    for (let i = 0; i < 4; i++) {
      ctx.rotate(Math.PI / 2);
      ctx.beginPath(); ctx.moveTo(rr * 0.78, 0); ctx.lineTo(rr * 1.02, 0); ctx.stroke();
    }
    ctx.restore();

    // --- 꼬리(테이퍼 모션 트레일) ---
    ctx.save();
    for (let i = 1; i <= 4; i++) {
      const tp = i / 5;
      const ty2 = y - tp * R * 3.2;
      ctx.globalAlpha = 0.18 * (1 - tp);
      ctx.fillStyle = '#ffb15a';
      ctx.beginPath(); ctx.arc(x, ty2, R * (1 - tp * 0.6), 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();

    // --- 오브 본체: 어두운 코어 + 밝은 림 라이트(이클립스 느낌) ---
    ctx.save();
    ctx.shadowColor = 'rgba(255,90,60,0.7)'; ctx.shadowBlur = R * 0.9;
    const g = ctx.createRadialGradient(x, y, R * 0.2, x, y, R);
    g.addColorStop(0, '#2a1410');
    g.addColorStop(0.62, '#5e241c');
    g.addColorStop(0.86, '#ff6a3d');
    g.addColorStop(1, '#ffd27a');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(x, y, R, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    // 상단 스펙큘러 하이라이트(매끈함)
    ctx.save();
    ctx.globalAlpha = 0.5;
    const hg = ctx.createRadialGradient(x - R * 0.32, y - R * 0.42, 0, x - R * 0.32, y - R * 0.42, R * 0.5);
    hg.addColorStop(0, 'rgba(255,255,255,0.9)');
    hg.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = hg;
    ctx.beginPath(); ctx.arc(x - R * 0.32, y - R * 0.42, R * 0.5, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  // 캘리브레이션 UI: 사람 모양 가이드 + 코너 프레임 + 진행 링 + 상태문구
  drawCalibUI(progress, status, t, groundY = 0.90) {
    const ctx = this.ctx;
    const accent = progress >= 1 ? '#57e389' : (progress > 0 ? '#57e389' : '#ffffff');
    // 살짝 어둡게(집중)
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,0.28)';
    ctx.fillRect(0, 0, this.W, this.H);

    // 가운데 사람 모양 가이드 — 게임의 고정 구멍과 똑같은 위치/크기 + '별 모양'(양팔·양다리 벌림)
    // 여기에 맞춰 팔다리를 벌리고 서면, 게임 중 팔을 뻗어도 경계를 벗어나지 않는다.
    const wg = this.wallGeom(groundY);
    const frameH = this.H * 0.84;
    const frameW = Math.min(this.W * 0.92, frameH);
    const cx = wg.cx, cy = wg.cy;
    ctx.save();
    ctx.globalAlpha = 0.9;
    ctx.shadowColor = 'rgba(255,255,255,0.5)';
    ctx.shadowBlur = 16;
    ctx.fillStyle = `rgba(255,255,255,${0.14 + 0.06 * Math.sin(t * 3)})`;
    fillHole(ctx, { pose: 'star', rot: 0, margin: 0.45 }, { cx, cy, S: wg.S, thickBoost: 0 });
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
