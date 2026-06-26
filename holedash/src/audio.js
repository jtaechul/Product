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
    this.volume = 0.16;
    this.noiseBuf = null;
    // 마디별 화음(루트 베이스 / 아르페지오 4음)
    this.prog = [
      { bass: 110.00, arp: [220.00, 261.63, 329.63, 440.00] }, // Am
      { bass: 87.31,  arp: [174.61, 220.00, 261.63, 349.23] }, // F
      { bass: 130.81, arp: [261.63, 329.63, 392.00, 523.25] }, // C
      { bass: 98.00,  arp: [196.00, 246.94, 293.66, 392.00] }, // G
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
    // 킥(four on the floor)
    if (step % 4 === 0) this._kick(t);
    // 하이햇(8분 오프비트 강조)
    if (step % 2 === 0) this._hat(t, (step % 4 === 2) ? 0.22 : 0.12);
    // 베이스(8분, 약간 통통 튀게)
    if (step % 2 === 0) {
      const oct = (step % 4 === 0) ? 1 : 1; // 루트
      this._bass(ch.bass * oct, t);
    }
    // 아르페지오(8분, 밝은 리드)
    if (step % 2 === 0) {
      const n = ch.arp[(step / 2) % 4];
      this._note(n, t, 0.17, 'triangle', 0.10);
      if (step % 8 === 0) this._note(n * 2, t, 0.22, 'triangle', 0.045); // 옥타브 반짝
    }
    // 마디 시작에 패드(은은한 화음)
    if (step === 0) {
      ch.arp.slice(0, 3).forEach((f) => this._note(f / 2, t, 1.85, 'sawtooth', 0.025));
    }
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
  _hat(t, gain) {
    const ctx = this._ctx();
    if (!this.noiseBuf) {
      const n = Math.floor(ctx.sampleRate * 0.12);
      this.noiseBuf = ctx.createBuffer(1, n, ctx.sampleRate);
      const d = this.noiseBuf.getChannelData(0);
      for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    }
    const src = ctx.createBufferSource(); src.buffer = this.noiseBuf;
    const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 7500;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.045);
    src.connect(hp).connect(g).connect(this.master);
    src.start(t); src.stop(t + 0.06);
  }
}
