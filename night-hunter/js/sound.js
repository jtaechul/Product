// sound.js — 음악/사운드 시스템 (Web Audio API)

const SoundManager = {
    ctx: null,
    masterGain: null,
    bgmGain: null,
    sfxGain: null,
    bgmActive: false,
    bgmType: null,
    bgmTimer: null,
    initialized: false,

    init() {
        if (this.initialized) return;
        try {
            this.ctx = new (window.AudioContext || window.webkitAudioContext)();
            this.masterGain = this.ctx.createGain();
            this.masterGain.gain.value = 0.35;
            this.masterGain.connect(this.ctx.destination);

            this.bgmGain = this.ctx.createGain();
            this.bgmGain.gain.value = 0.4;
            this.bgmGain.connect(this.masterGain);

            this.sfxGain = this.ctx.createGain();
            this.sfxGain.gain.value = 0.6;
            this.sfxGain.connect(this.masterGain);

            this.initialized = true;
        } catch (e) {
            console.warn('Audio API not available');
        }
    },

    playNote(freq, duration, type, gainNode, vol, attack, release) {
        if (!this.ctx) return;
        const now = this.ctx.currentTime;
        const osc = this.ctx.createOscillator();
        const g = this.ctx.createGain();
        osc.type = type || 'sine';
        osc.frequency.value = freq;
        const v = vol || 0.2;
        const a = attack || 0.02;
        const r = release || duration * 0.5;
        g.gain.setValueAtTime(0, now);
        g.gain.linearRampToValueAtTime(v, now + a);
        g.gain.linearRampToValueAtTime(v * 0.7, now + duration - r);
        g.gain.exponentialRampToValueAtTime(0.001, now + duration);
        osc.connect(g);
        g.connect(gainNode || this.sfxGain);
        osc.start(now);
        osc.stop(now + duration + 0.1);
    },

    playSFX(name) {
        if (!this.ctx) return;
        switch (name) {
            case 'collect':
                this.playNote(880, 0.12, 'sine', this.sfxGain, 0.25);
                setTimeout(() => this.playNote(1320, 0.15, 'sine', this.sfxGain, 0.2), 80);
                break;
            case 'arrest_success':
                [523, 659, 784, 1047].forEach((f, i) =>
                    setTimeout(() => this.playNote(f, 0.18, 'triangle', this.sfxGain, 0.3), i * 90));
                break;
            case 'arrest_fail':
                this.playNote(300, 0.3, 'sawtooth', this.sfxGain, 0.15);
                setTimeout(() => this.playNote(180, 0.4, 'sawtooth', this.sfxGain, 0.15), 200);
                break;
            case 'alert':
                this.playNote(600, 0.1, 'square', this.sfxGain, 0.12);
                setTimeout(() => this.playNote(800, 0.1, 'square', this.sfxGain, 0.12), 150);
                break;
            case 'buy':
                this.playNote(500, 0.08, 'sine', this.sfxGain, 0.2);
                setTimeout(() => this.playNote(700, 0.12, 'sine', this.sfxGain, 0.2), 60);
                break;
            case 'victory':
                [523, 659, 784, 1047, 1319, 1568].forEach((f, i) =>
                    setTimeout(() => this.playNote(f, 0.25, 'sine', this.sfxGain, 0.25), i * 130));
                break;
            case 'gameover':
                [440, 392, 349, 294].forEach((f, i) =>
                    setTimeout(() => this.playNote(f, 0.4, 'sawtooth', this.sfxGain, 0.15), i * 180));
                break;
            case 'transition':
                this.playNote(440, 0.4, 'sine', this.sfxGain, 0.1);
                setTimeout(() => this.playNote(330, 0.6, 'sine', this.sfxGain, 0.1), 250);
                break;
        }
    },

    // Day BGM — upbeat, jazzy investigation theme
    // C-major progression: C-Am-F-G with melody
    dayMelody: [
        // [freq, duration]
        [523, 0.4], [659, 0.4], [784, 0.4], [659, 0.4],
        [587, 0.4], [698, 0.4], [880, 0.4], [698, 0.4],
        [523, 0.4], [659, 0.4], [784, 0.6], [659, 0.2],
        [587, 0.8], [523, 0.8],
    ],
    dayBass: [
        [131, 1.6], [110, 1.6], [98, 1.6], [131, 1.6],
    ],

    // Night BGM — moody, suspenseful theme
    // A-minor: Am-Dm-E-Am
    nightMelody: [
        [440, 0.5], [523, 0.5], [659, 0.5], [523, 0.5],
        [494, 0.5], [587, 0.5], [659, 1.0],
        [440, 0.5], [392, 0.5], [349, 1.0],
        [415, 1.0], [440, 1.0],
    ],
    nightBass: [
        [110, 2], [147, 2], [165, 2], [110, 2],
    ],

    playBGM(type) {
        if (!this.ctx) return;
        this.stopBGM();
        this.bgmActive = true;
        this.bgmType = type;

        const melody = type === 'day' ? this.dayMelody : this.nightMelody;
        const bass = type === 'day' ? this.dayBass : this.nightBass;
        const melodyType = type === 'day' ? 'triangle' : 'sine';
        const bassType = 'sine';
        const melodyVol = type === 'day' ? 0.08 : 0.06;
        const bassVol = type === 'day' ? 0.12 : 0.10;

        // Melody loop
        let mIdx = 0;
        const playMelody = () => {
            if (!this.bgmActive || this.bgmType !== type) return;
            const [freq, dur] = melody[mIdx % melody.length];
            this.playNote(freq, dur * 0.9, melodyType, this.bgmGain, melodyVol, 0.05, 0.15);
            mIdx++;
            setTimeout(playMelody, dur * 1000);
        };

        // Bass loop
        let bIdx = 0;
        const playBass = () => {
            if (!this.bgmActive || this.bgmType !== type) return;
            const [freq, dur] = bass[bIdx % bass.length];
            this.playNote(freq, dur * 0.85, bassType, this.bgmGain, bassVol, 0.05, 0.3);
            // Subtle harmony note
            this.playNote(freq * 1.5, dur * 0.85, bassType, this.bgmGain, bassVol * 0.5, 0.05, 0.3);
            bIdx++;
            setTimeout(playBass, dur * 1000);
        };

        // Hi-hat for day (rhythm)
        let hIdx = 0;
        const playHat = () => {
            if (!this.bgmActive || this.bgmType !== type) return;
            if (type === 'day') {
                this.playNote(8000 + Math.random() * 2000, 0.05, 'square', this.bgmGain, 0.02);
            } else {
                if (hIdx % 4 === 0) {
                    this.playNote(60, 0.15, 'sawtooth', this.bgmGain, 0.05);
                }
            }
            hIdx++;
            setTimeout(playHat, 200);
        };

        setTimeout(playMelody, 200);
        setTimeout(playBass, 200);
        setTimeout(playHat, 200);
    },

    stopBGM() {
        this.bgmActive = false;
        this.bgmType = null;
    }
};
