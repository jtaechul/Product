// ===== 사운드 레이어 (Web Audio · 에셋 0개, 절차적 생성) =====

export class Sfx {
  constructor() {
    this.ctx = null;
    this.enabled = true;
  }
  _ensure() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AC();
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }
  resume() { try { this._ensure(); } catch (e) {} }

  _tone(freq, dur, type = 'sine', gain = 0.18, startAt = 0) {
    const ctx = this._ensure();
    const t = ctx.currentTime + startAt;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + dur + 0.02);
    return osc;
  }
  _sweep(f0, f1, dur, type = 'sawtooth', gain = 0.18) {
    const ctx = this._ensure();
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(f0, t);
    osc.frequency.exponentialRampToValueAtTime(f1, t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g).connect(ctx.destination);
    osc.start(t); osc.stop(t + dur + 0.02);
  }
  _noise(dur, gain = 0.25) {
    const ctx = this._ensure();
    const t = ctx.currentTime;
    const n = Math.floor(ctx.sampleRate * dur);
    const buf = ctx.createBuffer(1, n, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const g = ctx.createGain();
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(g).connect(ctx.destination);
    src.start(t);
  }

  beep() { if (!this.enabled) return; this._tone(880, 0.12, 'square', 0.12); }
  go() { if (!this.enabled) return; this._tone(1320, 0.25, 'square', 0.16); }
  // 장애물 날아옴(슉~) / 회피 성공(딩↑, 콤보 높을수록 음↑)
  whoosh() { if (!this.enabled) return; this._sweep(720, 150, 0.32, 'sawtooth', 0.10); this._noise(0.22, 0.08); }
  ding(level = 0) {
    if (!this.enabled) return;
    const base = 760 + Math.min(level, 6) * 110;
    this._tone(base, 0.11, 'triangle', 0.16);
    this._tone(base * 1.5, 0.14, 'triangle', 0.12, 0.05);
  }

  grade(name, comboStreak = 0) {
    if (!this.enabled) return;
    switch (name) {
      case 'PERFECT': {
        const base = 660 + Math.min(comboStreak, 6) * 60;
        [0, 0.08, 0.16].forEach((d, i) => this._tone(base * (1 + i * 0.26), 0.18, 'triangle', 0.16, d));
        break;
      }
      case 'GREAT':
        this._tone(620, 0.14, 'triangle', 0.15);
        this._tone(820, 0.16, 'triangle', 0.13, 0.08);
        break;
      case 'GOOD':
        this._tone(520, 0.16, 'sine', 0.15);
        break;
      case 'OUCH':
        this._tone(360, 0.18, 'sawtooth', 0.13);
        break;
      case 'CRASH':
        this._noise(0.3, 0.28);
        this._sweep(300, 80, 0.35, 'sawtooth', 0.2); // 만화식 "뿌엥~"
        break;
    }
  }
  fanfare() {
    if (!this.enabled) return;
    [523, 659, 784, 1047].forEach((f, i) => this._tone(f, 0.3, 'triangle', 0.16, i * 0.12));
  }

  // ===== 우스꽝스럽고 놀라운 효과음 =====
  _brass(freq, dur, startAt = 0, bendTo = null) {
    const ctx = this._ensure();
    const t = ctx.currentTime + startAt;
    const o = ctx.createOscillator(); o.type = 'sawtooth';
    o.frequency.setValueAtTime(freq, t);
    if (bendTo) o.frequency.exponentialRampToValueAtTime(bendTo, t + dur);
    const lp = ctx.createBiquadFilter(); lp.type = 'lowpass';
    lp.frequency.setValueAtTime(600, t);
    lp.frequency.linearRampToValueAtTime(1700, t + dur * 0.4);
    lp.frequency.linearRampToValueAtTime(500, t + dur);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.22, t + 0.03);
    g.gain.setValueAtTime(0.2, t + dur * 0.7);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(lp).connect(g).connect(ctx.destination);
    o.start(t); o.stop(t + dur + 0.05);
  }
  // 뽕~뽕~뽕~뿌웅 (실망 트롬본)
  sadTrombone() {
    this._brass(311, 0.22, 0); this._brass(277, 0.22, 0.22);
    this._brass(233, 0.24, 0.44); this._brass(220, 0.55, 0.68, 160);
  }
  // 보잉~ (용수철)
  boing() {
    const ctx = this._ensure(); const t = ctx.currentTime;
    const o = ctx.createOscillator(); o.type = 'sine';
    o.frequency.setValueAtTime(520, t); o.frequency.exponentialRampToValueAtTime(130, t + 0.26);
    const lfo = ctx.createOscillator(); lfo.frequency.value = 19;
    const lg = ctx.createGain(); lg.gain.setValueAtTime(130, t); lg.gain.exponentialRampToValueAtTime(2, t + 0.26);
    lfo.connect(lg).connect(o.frequency);
    const g = ctx.createGain(); g.gain.setValueAtTime(0.26, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.34);
    o.connect(g).connect(ctx.destination);
    o.start(t); lfo.start(t); o.stop(t + 0.36); lfo.stop(t + 0.36);
  }
  // 빵빵 (경적)
  honk() {
    const ctx = this._ensure(); const t = ctx.currentTime;
    [0, 0.14].forEach((d) => {
      const o = ctx.createOscillator(); o.type = 'square';
      o.frequency.setValueAtTime(300, t + d); o.frequency.exponentialRampToValueAtTime(175, t + d + 0.1);
      const g = ctx.createGain(); g.gain.setValueAtTime(0.18, t + d); g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.12);
      o.connect(g).connect(ctx.destination); o.start(t + d); o.stop(t + d + 0.14);
    });
  }
  // 철퍼덕 (충격)
  splat() {
    this._noise(0.18, 0.3);
    const ctx = this._ensure(); const t = ctx.currentTime;
    const o = ctx.createOscillator(); o.type = 'sine';
    o.frequency.setValueAtTime(150, t); o.frequency.exponentialRampToValueAtTime(48, t + 0.16);
    const g = ctx.createGain(); g.gain.setValueAtTime(0.3, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
    o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + 0.2);
  }
  slideWhistleDown() { this._sweep(1500, 280, 0.42, 'triangle', 0.14); }

  // 벽에 부딪힘(실패) — 매번 다른 우스운 소리로 놀라게
  crash() {
    if (!this.enabled) return;
    const p = (Math.random() * 3) | 0;
    if (p === 0) { this.sadTrombone(); this.splat(); }
    else if (p === 1) { this.slideWhistleDown(); this.splat(); }
    else { this.boing(); this.honk(); }
  }
  // 장애물에 맞음 — 깜짝 보잉+철퍼덕
  bonk() {
    if (!this.enabled) return;
    this.boing(); this.splat();
    if (Math.random() < 0.5) this.honk();
  }
}

// ===== 배경음악 (절차적 · 긴장감+밝고 신나는 드라이브) =====
// A단조 진행(Am–F–C–G)의 four-on-the-floor 비트 + 베이스 + 밝은 아르페지오.
export class Music {
  constructor(sfx) {
    this.sfx = sfx;
    this.playing = false;
    this.timer = null;
    this.step = 0; this.bar = 0; this.nextTime = 0;
    this.master = null;
    this.volume = 0.18;
    this.noiseBuf = null;
    // 마디별 화음(루트 베이스 / 아르페지오 4음 = 루트·3도·5도·옥타브)
    this.prog = [
      { bass: 110.00, arp: [220.00, 261.63, 329.63, 440.00] }, // Am
      { bass: 87.31,  arp: [174.61, 220.00, 261.63, 349.23] }, // F
      { bass: 130.81, arp: [261.63, 329.63, 392.00, 523.25] }, // C
      { bass: 98.00,  arp: [196.00, 246.94, 293.66, 392.00] }, // G
    ];
    // 리드 훅(마디마다 반복, 화음에 맞춰 음 바뀜). s=마디 내 16분 위치, i=아르페지오 인덱스
    this.leadRhythm = [
      { s: 0, i: 2 }, { s: 2, i: 3 }, { s: 4, i: 1 }, { s: 7, i: 2 },
      { s: 8, i: 3 }, { s: 10, i: 1 }, { s: 12, i: 0 }, { s: 14, i: 2 },
    ];
  }
  _ctx() { return this.sfx._ensure(); }

  start() {
    if (this.playing) return;
    const ctx = this._ctx();
    this.master = ctx.createGain();
    this.master.gain.setValueAtTime(0.0001, ctx.currentTime);
    this.master.gain.linearRampToValueAtTime(this.volume, ctx.currentTime + 1.4); // 페이드 인
    this.master.connect(ctx.destination);
    this.playing = true; this.step = 0; this.bar = 0;
    this.nextTime = ctx.currentTime + 0.1;
    this.timer = setInterval(() => this._schedule(), 25);
  }
  stop() {
    if (!this.playing) return;
    this.playing = false;
    clearInterval(this.timer); this.timer = null;
    if (this.master) {
      const ctx = this._ctx(); const m = this.master;
      m.gain.cancelScheduledValues(ctx.currentTime);
      m.gain.setValueAtTime(m.gain.value, ctx.currentTime);
      m.gain.linearRampToValueAtTime(0.0001, ctx.currentTime + 0.4);
      setTimeout(() => { try { m.disconnect(); } catch (e) {} }, 600);
      this.master = null;
    }
  }
  setVolume(v) {
    this.volume = v;
    if (this.master) {
      const ctx = this._ctx();
      this.master.gain.cancelScheduledValues(ctx.currentTime);
      this.master.gain.setValueAtTime(this.master.gain.value, ctx.currentTime);
      this.master.gain.linearRampToValueAtTime(Math.max(0.0001, v), ctx.currentTime + 0.2);
    }
  }

  _schedule() {
    const ctx = this._ctx();
    const STEP = (60 / 124) / 4; // 16분음표(BPM 124)
    while (this.nextTime < ctx.currentTime + 0.13) {
      this._playStep(this.step, this.nextTime);
      this.nextTime += STEP;
      this.step += 1;
      if (this.step >= 16) { this.step = 0; this.bar = (this.bar + 1) % 4; }
    }
  }

  _playStep(step, t) {
    if (!this.master) return;
    const ch = this.prog[this.bar];
    // 드럼: 킥(four on the floor) + 스네어(2·4박 백비트)
    if (step % 4 === 0) this._kick(t);
    if (step === 4 || step === 12) this._snare(t);
    // 하이햇: 8분 기본 + 16분 고스트로 촘촘하게, 14에서 오픈햇
    if (step % 2 === 0) this._hat(t, (step % 4 === 2) ? 0.22 : 0.13, false);
    else this._hat(t, 0.05, false); // 16분 고스트
    if (step === 14) this._hat(t, 0.16, true);
    // 베이스(8분, 8스텝에서 5도로 움직임)
    if (step % 2 === 0) this._bass((step === 8) ? ch.bass * 1.5 : ch.bass, t);
    // 아르페지오 받침(8분)
    if (step % 2 === 0) this._note(ch.arp[(step / 2) % 4], t, 0.16, 'triangle', 0.07);
    // 패드(마디 시작 은은한 화음)
    if (step === 0) ch.arp.slice(0, 3).forEach((f) => this._note(f / 2, t, 1.85, 'sawtooth', 0.022));
    // 리드 훅(밝은 멜로디, 옥타브 위)
    const le = this.leadRhythm.find((e) => e.s === step);
    if (le) this._lead(ch.arp[le.i] * 2, t);
  }

  _lead(freq, t) {
    const ctx = this._ctx();
    const o = ctx.createOscillator(); const g = ctx.createGain();
    const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 3200;
    o.type = 'square'; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.12, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.26);
    o.connect(lp).connect(g).connect(this.master);
    o.start(t); o.stop(t + 0.3);
  }
  _snare(t) {
    const ctx = this._ctx();
    const src = ctx.createBufferSource(); src.buffer = this._noise();
    const bp = ctx.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = 1900; bp.Q.value = 0.8;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.3, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.15);
    src.connect(bp).connect(g).connect(this.master);
    src.start(t); src.stop(t + 0.17);
    const o = ctx.createOscillator(); const g2 = ctx.createGain();
    o.type = 'triangle';
    o.frequency.setValueAtTime(210, t); o.frequency.exponentialRampToValueAtTime(140, t + 0.1);
    g2.gain.setValueAtTime(0.0001, t);
    g2.gain.exponentialRampToValueAtTime(0.16, t + 0.005);
    g2.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    o.connect(g2).connect(this.master);
    o.start(t); o.stop(t + 0.14);
  }
  _noise() {
    if (this.noiseBuf) return this.noiseBuf;
    const ctx = this._ctx();
    const n = Math.floor(ctx.sampleRate * 0.2);
    this.noiseBuf = ctx.createBuffer(1, n, ctx.sampleRate);
    const d = this.noiseBuf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    return this.noiseBuf;
  }

  _note(freq, t, dur, type, gain) {
    const ctx = this._ctx();
    const o = ctx.createOscillator(); const g = ctx.createGain();
    o.type = type; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(this.master);
    o.start(t); o.stop(t + dur + 0.03);
  }
  _bass(freq, t) {
    const ctx = this._ctx();
    const o = ctx.createOscillator(); const g = ctx.createGain();
    const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 700;
    o.type = 'sawtooth'; o.frequency.value = freq;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.32, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
    o.connect(lp).connect(g).connect(this.master);
    o.start(t); o.stop(t + 0.2);
  }
  _kick(t) {
    const ctx = this._ctx();
    const o = ctx.createOscillator(); const g = ctx.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(150, t);
    o.frequency.exponentialRampToValueAtTime(45, t + 0.12);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.9, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.19);
    o.connect(g).connect(this.master);
    o.start(t); o.stop(t + 0.22);
  }
  _hat(t, gain, open) {
    const ctx = this._ctx();
    const src = ctx.createBufferSource(); src.buffer = this._noise();
    const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 7500;
    const g = ctx.createGain();
    const dur = open ? 0.14 : 0.045;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(hp).connect(g).connect(this.master);
    src.start(t); src.stop(t + dur + 0.02);
  }
}
