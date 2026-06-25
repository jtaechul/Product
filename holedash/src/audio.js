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

  beep() { this._tone(880, 0.12, 'square', 0.12); }
  go() { this._tone(1320, 0.25, 'square', 0.16); }

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
