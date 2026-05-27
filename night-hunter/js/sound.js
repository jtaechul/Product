// sound.js — 사운드 시스템 (9단계)
// Web Audio API 절차적 사운드 (외부 파일 없음)

const SoundManager = {
    ctx: null,
    masterGain: null,
    bgmGain: null,
    sfxGain: null,
    currentBGM: null,
    initialized: false,

    init() {
        if (this.initialized) return;
        try {
            this.ctx = new (window.AudioContext || window.webkitAudioContext)();
            this.masterGain = this.ctx.createGain();
            this.masterGain.gain.value = 0.3;
            this.masterGain.connect(this.ctx.destination);

            this.bgmGain = this.ctx.createGain();
            this.bgmGain.gain.value = 0.15;
            this.bgmGain.connect(this.masterGain);

            this.sfxGain = this.ctx.createGain();
            this.sfxGain.gain.value = 0.5;
            this.sfxGain.connect(this.masterGain);

            this.initialized = true;
        } catch (e) {
            console.warn('Audio not available');
        }
    },

    playTone(freq, duration, type, gainNode, vol) {
        if (!this.ctx) return;
        const osc = this.ctx.createOscillator();
        const g = this.ctx.createGain();
        osc.type = type || 'sine';
        osc.frequency.value = freq;
        g.gain.setValueAtTime(vol || 0.3, this.ctx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + duration);
        osc.connect(g);
        g.connect(gainNode || this.sfxGain);
        osc.start();
        osc.stop(this.ctx.currentTime + duration);
    },

    playSFX(name) {
        if (!this.ctx) return;
        switch (name) {
            case 'collect':
                this.playTone(880, 0.1, 'sine', this.sfxGain, 0.3);
                setTimeout(() => this.playTone(1100, 0.15, 'sine', this.sfxGain, 0.3), 80);
                break;
            case 'arrest_success':
                [523, 659, 784, 1047].forEach((f, i) => {
                    setTimeout(() => this.playTone(f, 0.2, 'sine', this.sfxGain, 0.3), i * 100);
                });
                break;
            case 'arrest_fail':
                this.playTone(300, 0.3, 'sawtooth', this.sfxGain, 0.2);
                setTimeout(() => this.playTone(200, 0.4, 'sawtooth', this.sfxGain, 0.2), 200);
                break;
            case 'alert':
                this.playTone(600, 0.1, 'square', this.sfxGain, 0.15);
                setTimeout(() => this.playTone(800, 0.1, 'square', this.sfxGain, 0.15), 150);
                break;
            case 'buy':
                this.playTone(500, 0.08, 'sine', this.sfxGain, 0.2);
                setTimeout(() => this.playTone(700, 0.12, 'sine', this.sfxGain, 0.2), 60);
                break;
            case 'victory':
                [523, 659, 784, 1047, 1319].forEach((f, i) => {
                    setTimeout(() => this.playTone(f, 0.3, 'sine', this.sfxGain, 0.25), i * 150);
                });
                break;
            case 'gameover':
                [400, 350, 300, 200].forEach((f, i) => {
                    setTimeout(() => this.playTone(f, 0.4, 'sawtooth', this.sfxGain, 0.15), i * 200);
                });
                break;
            case 'transition':
                this.playTone(440, 0.5, 'sine', this.sfxGain, 0.1);
                setTimeout(() => this.playTone(330, 0.8, 'sine', this.sfxGain, 0.1), 300);
                break;
        }
    },

    playBGM(type) {
        if (!this.ctx) return;
        this.stopBGM();

        const now = this.ctx.currentTime;

        if (type === 'day') {
            this._bgmLoop([ 262, 294, 330, 349, 330, 294 ], 0.4, 'sine', 0.08);
        } else {
            this._bgmLoop([ 165, 175, 185, 175, 165, 155 ], 0.6, 'triangle', 0.06);
        }
    },

    _bgmLoop(notes, noteLen, type, vol) {
        if (!this.ctx) return;
        let i = 0;
        const play = () => {
            if (!this.currentBGM) return;
            this.playTone(notes[i % notes.length], noteLen * 0.8, type, this.bgmGain, vol);
            i++;
            this.currentBGM = setTimeout(play, noteLen * 1000);
        };
        this.currentBGM = setTimeout(play, 100);
    },

    stopBGM() {
        if (this.currentBGM) {
            clearTimeout(this.currentBGM);
            this.currentBGM = null;
        }
    }
};
