// sound.js — 음악 & 사운드 (Web Audio API, 정교한 멜로디+화음+드럼)

const SoundManager = {
    ctx: null,
    masterGain: null,
    bgmGain: null,
    sfxGain: null,
    bgmActive: false,
    bgmType: null,
    bgmTimers: [],
    initialized: false,
    reverb: null,

    init() {
        if (this.initialized) return;
        try {
            this.ctx = new (window.AudioContext || window.webkitAudioContext)();
            this.masterGain = this.ctx.createGain();
            this.masterGain.gain.value = 0.4;
            this.masterGain.connect(this.ctx.destination);

            this.bgmGain = this.ctx.createGain();
            this.bgmGain.gain.value = 0.5;
            this.bgmGain.connect(this.masterGain);

            this.sfxGain = this.ctx.createGain();
            this.sfxGain.gain.value = 0.7;
            this.sfxGain.connect(this.masterGain);

            // Convolver reverb
            this.reverb = this.ctx.createConvolver();
            this.reverb.buffer = this._makeImpulseResponse(2, 2, false);
            const reverbWet = this.ctx.createGain();
            reverbWet.gain.value = 0.25;
            this.reverb.connect(reverbWet);
            reverbWet.connect(this.masterGain);
            this.reverbSend = this.ctx.createGain();
            this.reverbSend.gain.value = 0.15;
            this.reverbSend.connect(this.reverb);
            this.bgmGain.connect(this.reverbSend);

            this.initialized = true;
        } catch (e) {
            console.warn('Audio API not available', e);
        }
    },

    _makeImpulseResponse(duration, decay, reverse) {
        const rate = this.ctx.sampleRate;
        const length = rate * duration;
        const impulse = this.ctx.createBuffer(2, length, rate);
        for (let ch = 0; ch < 2; ch++) {
            const data = impulse.getChannelData(ch);
            for (let i = 0; i < length; i++) {
                const n = reverse ? length - i : i;
                data[i] = (Math.random() * 2 - 1) * Math.pow(1 - n / length, decay);
            }
        }
        return impulse;
    },

    _playOsc(freq, duration, type, gainNode, opts) {
        if (!this.ctx) return null;
        const o = opts || {};
        const now = this.ctx.currentTime + (o.delay || 0);
        const osc = this.ctx.createOscillator();
        const g = this.ctx.createGain();

        osc.type = type || 'sine';
        osc.frequency.setValueAtTime(freq, now);
        if (o.glide) {
            osc.frequency.exponentialRampToValueAtTime(o.glide, now + duration);
        }

        const peak = o.vol || 0.2;
        const attack = o.attack || 0.02;
        const release = o.release || duration * 0.4;
        g.gain.setValueAtTime(0, now);
        g.gain.linearRampToValueAtTime(peak, now + attack);
        g.gain.linearRampToValueAtTime(peak * 0.6, now + duration - release);
        g.gain.exponentialRampToValueAtTime(0.001, now + duration);

        // Optional filter
        if (o.filter) {
            const f = this.ctx.createBiquadFilter();
            f.type = o.filter.type || 'lowpass';
            f.frequency.value = o.filter.freq || 2000;
            f.Q.value = o.filter.q || 1;
            osc.connect(f);
            f.connect(g);
        } else {
            osc.connect(g);
        }
        g.connect(gainNode || this.sfxGain);
        osc.start(now);
        osc.stop(now + duration + 0.1);
        return { osc, gain: g };
    },

    _playKick(time) {
        if (!this.ctx) return;
        const now = this.ctx.currentTime + (time || 0);
        const osc = this.ctx.createOscillator();
        const g = this.ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(110, now);
        osc.frequency.exponentialRampToValueAtTime(40, now + 0.1);
        g.gain.setValueAtTime(0.4, now);
        g.gain.exponentialRampToValueAtTime(0.001, now + 0.2);
        osc.connect(g); g.connect(this.bgmGain);
        osc.start(now); osc.stop(now + 0.25);
    },

    _playSnare(time) {
        if (!this.ctx) return;
        const now = this.ctx.currentTime + (time || 0);
        // Noise
        const bufSize = this.ctx.sampleRate * 0.15;
        const buf = this.ctx.createBuffer(1, bufSize, this.ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < bufSize; i++) d[i] = Math.random() * 2 - 1;
        const noise = this.ctx.createBufferSource();
        noise.buffer = buf;
        const f = this.ctx.createBiquadFilter();
        f.type = 'highpass'; f.frequency.value = 1000;
        const g = this.ctx.createGain();
        g.gain.setValueAtTime(0.18, now);
        g.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
        noise.connect(f); f.connect(g); g.connect(this.bgmGain);
        noise.start(now); noise.stop(now + 0.15);
    },

    _playHihat(time, open) {
        if (!this.ctx) return;
        const now = this.ctx.currentTime + (time || 0);
        const bufSize = this.ctx.sampleRate * (open ? 0.15 : 0.05);
        const buf = this.ctx.createBuffer(1, bufSize, this.ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < bufSize; i++) d[i] = Math.random() * 2 - 1;
        const noise = this.ctx.createBufferSource();
        noise.buffer = buf;
        const f = this.ctx.createBiquadFilter();
        f.type = 'highpass'; f.frequency.value = 7000;
        const g = this.ctx.createGain();
        g.gain.setValueAtTime(open ? 0.06 : 0.04, now);
        g.gain.exponentialRampToValueAtTime(0.001, now + (open ? 0.12 : 0.04));
        noise.connect(f); f.connect(g); g.connect(this.bgmGain);
        noise.start(now); noise.stop(now + 0.16);
    },

    // === Day BGM: Detective-style jazz noir ===
    // C minor blues progression with walking bass and ride pattern
    // Cm - Fm - G7 - Cm
    dayChords: [
        { root: 130.81, notes: [261.63, 311.13, 392.0] },     // Cm
        { root: 174.61, notes: [349.23, 415.30, 523.25] },    // Fm
        { root: 196.0, notes: [392.0, 493.88, 587.33, 698.46] }, // G7
        { root: 130.81, notes: [261.63, 311.13, 392.0] },     // Cm
    ],
    dayMelody: [
        // detective bossa-style descending lines
        [523.25, 0.5], [466.16, 0.5], [392.0, 0.5], [349.23, 0.5],
        [415.30, 0.75], [349.23, 0.25], [311.13, 0.5], [261.63, 0.5],
        [415.30, 0.5], [466.16, 0.5], [523.25, 1.0],
        [466.16, 0.25], [415.30, 0.25], [392.0, 0.5], [261.63, 1.0],
    ],

    // === Night BGM: Suspenseful dark ambient ===
    nightChords: [
        { root: 110.0, notes: [220.0, 261.63, 329.63] },  // Am
        { root: 146.83, notes: [293.66, 349.23, 440.0] }, // Dm
        { root: 164.81, notes: [329.63, 415.30, 493.88] }, // E
        { root: 110.0, notes: [220.0, 261.63, 329.63] },  // Am
    ],
    nightMelody: [
        [440.0, 1.0], [523.25, 1.0], [415.30, 1.0], [493.88, 1.0],
        [329.63, 1.5], [293.66, 0.5], [261.63, 2.0],
        [440.0, 1.0], [392.0, 1.0], [349.23, 2.0],
    ],

    playBGM(type) {
        if (!this.ctx) return;
        this.stopBGM();
        this.bgmActive = true;
        this.bgmType = type;

        if (type === 'day') {
            this._playDayBGM();
        } else {
            this._playNightBGM();
        }
    },

    _playDayBGM() {
        const beatLen = 0.45;
        let measure = 0;

        const playMeasure = () => {
            if (!this.bgmActive || this.bgmType !== 'day') return;
            const chord = this.dayChords[measure % 4];

            // Bass walking pattern (4 quarter notes per measure)
            const bassNotes = [chord.root, chord.root * 1.125, chord.root * 1.25, chord.root * 1.5];
            for (let i = 0; i < 4; i++) {
                this._playOsc(bassNotes[i], beatLen * 0.95, 'triangle', this.bgmGain, {
                    delay: i * beatLen, vol: 0.18, attack: 0.02, release: 0.1
                });
            }
            // Chord pad (held)
            chord.notes.forEach((n, idx) => {
                this._playOsc(n, beatLen * 4 * 0.95, 'sine', this.bgmGain, {
                    delay: 0, vol: 0.04, attack: 0.4, release: 1.0
                });
            });

            // Hi-hat pattern (8th notes)
            for (let i = 0; i < 8; i++) {
                this._playHihat(i * beatLen * 0.5, i % 2 === 1);
            }
            // Kick + snare
            this._playKick(0);
            this._playKick(beatLen * 2);
            this._playSnare(beatLen * 1);
            this._playSnare(beatLen * 3);

            measure++;
        };
        playMeasure();
        const measureLen = beatLen * 4 * 1000;
        this.bgmTimers.push(setInterval(playMeasure, measureLen));

        // Melody (separate loop, slightly offset)
        let mIdx = 0;
        const playMelodyNote = () => {
            if (!this.bgmActive || this.bgmType !== 'day') return;
            const [freq, dur] = this.dayMelody[mIdx % this.dayMelody.length];
            this._playOsc(freq, dur * beatLen * 0.95, 'triangle', this.bgmGain, {
                vol: 0.1, attack: 0.05, release: 0.2,
                filter: { type: 'lowpass', freq: 3000, q: 1 }
            });
            mIdx++;
            this.bgmTimers.push(setTimeout(playMelodyNote, dur * beatLen * 1000));
        };
        setTimeout(playMelodyNote, beatLen * 1000);
    },

    _playNightBGM() {
        const beatLen = 0.55;
        let measure = 0;

        const playMeasure = () => {
            if (!this.bgmActive || this.bgmType !== 'night') return;
            const chord = this.nightChords[measure % 4];

            // Deep bass drone
            this._playOsc(chord.root, beatLen * 4 * 0.95, 'sawtooth', this.bgmGain, {
                vol: 0.06, attack: 0.5, release: 1.5,
                filter: { type: 'lowpass', freq: 400, q: 2 }
            });
            this._playOsc(chord.root * 0.5, beatLen * 4 * 0.95, 'sine', this.bgmGain, {
                vol: 0.12, attack: 0.3, release: 1.5
            });

            // Chord pads (slow attack)
            chord.notes.forEach((n) => {
                this._playOsc(n, beatLen * 4 * 0.95, 'sine', this.bgmGain, {
                    vol: 0.03, attack: 0.8, release: 1.5
                });
            });

            // Subtle heartbeat-like kick on beat 1
            this._playKick(0);
            this._playKick(beatLen * 0.5);

            measure++;
        };
        playMeasure();
        const measureLen = beatLen * 4 * 1000;
        this.bgmTimers.push(setInterval(playMeasure, measureLen));

        // Eerie melody
        let mIdx = 0;
        const playMelodyNote = () => {
            if (!this.bgmActive || this.bgmType !== 'night') return;
            const [freq, dur] = this.nightMelody[mIdx % this.nightMelody.length];
            this._playOsc(freq, dur * beatLen * 0.9, 'sine', this.bgmGain, {
                vol: 0.07, attack: 0.15, release: 0.4,
                filter: { type: 'lowpass', freq: 1500, q: 1.5 }
            });
            // Octave shimmer
            this._playOsc(freq * 2, dur * beatLen * 0.9, 'sine', this.bgmGain, {
                vol: 0.02, attack: 0.2, release: 0.3
            });
            mIdx++;
            this.bgmTimers.push(setTimeout(playMelodyNote, dur * beatLen * 1000));
        };
        setTimeout(playMelodyNote, beatLen * 2 * 1000);
    },

    stopBGM() {
        this.bgmActive = false;
        this.bgmType = null;
        this.bgmTimers.forEach(t => { clearTimeout(t); clearInterval(t); });
        this.bgmTimers = [];
    },

    playSFX(name) {
        if (!this.ctx) return;
        switch (name) {
            case 'collect':
                this._playOsc(880, 0.1, 'triangle', this.sfxGain, { vol: 0.3 });
                this._playOsc(1320, 0.18, 'sine', this.sfxGain, { vol: 0.25, delay: 0.08 });
                this._playOsc(1760, 0.12, 'sine', this.sfxGain, { vol: 0.2, delay: 0.18 });
                break;
            case 'arrest_success':
                // C major arpeggio + flourish
                [523, 659, 784, 1047, 1319].forEach((f, i) => {
                    this._playOsc(f, 0.2, 'triangle', this.sfxGain, { vol: 0.3, delay: i * 0.08 });
                });
                this._playOsc(523, 0.5, 'sine', this.sfxGain, { vol: 0.15, delay: 0.5 });
                this._playOsc(784, 0.5, 'sine', this.sfxGain, { vol: 0.15, delay: 0.5 });
                this._playOsc(1047, 0.5, 'sine', this.sfxGain, { vol: 0.15, delay: 0.5 });
                break;
            case 'arrest_fail':
                this._playOsc(220, 0.4, 'sawtooth', this.sfxGain, { vol: 0.2, glide: 110 });
                this._playOsc(140, 0.6, 'sawtooth', this.sfxGain, { vol: 0.15, delay: 0.2 });
                break;
            case 'alert':
                this._playOsc(800, 0.1, 'square', this.sfxGain, { vol: 0.15 });
                this._playOsc(1200, 0.1, 'square', this.sfxGain, { vol: 0.15, delay: 0.15 });
                this._playOsc(800, 0.1, 'square', this.sfxGain, { vol: 0.15, delay: 0.3 });
                break;
            case 'buy':
                this._playOsc(500, 0.08, 'sine', this.sfxGain, { vol: 0.2 });
                this._playOsc(700, 0.1, 'sine', this.sfxGain, { vol: 0.2, delay: 0.06 });
                this._playOsc(1000, 0.12, 'sine', this.sfxGain, { vol: 0.15, delay: 0.12 });
                break;
            case 'victory':
                // Major triumphant fanfare
                [523, 659, 784, 1047, 1319, 1568, 2093].forEach((f, i) => {
                    this._playOsc(f, 0.3, 'triangle', this.sfxGain, { vol: 0.25, delay: i * 0.12 });
                });
                // Chord sustain
                [523, 659, 784, 1047].forEach(f => {
                    this._playOsc(f, 2.0, 'sine', this.sfxGain, { vol: 0.12, delay: 1.0, attack: 0.2, release: 0.5 });
                });
                break;
            case 'gameover':
                [440, 392, 349, 294, 220].forEach((f, i) => {
                    this._playOsc(f, 0.4, 'sawtooth', this.sfxGain, { vol: 0.15, delay: i * 0.2 });
                });
                this._playOsc(110, 1.5, 'sawtooth', this.sfxGain, { vol: 0.2, delay: 1.0, attack: 0.3, release: 0.8 });
                break;
            case 'transition':
                this._playOsc(440, 0.5, 'sine', this.sfxGain, { vol: 0.12, glide: 220 });
                this._playOsc(220, 0.8, 'sine', this.sfxGain, { vol: 0.1, delay: 0.3 });
                break;
            case 'footstep':
                this._playOsc(80 + Math.random() * 40, 0.05, 'square', this.sfxGain, { vol: 0.06 });
                break;
        }
    }
};
