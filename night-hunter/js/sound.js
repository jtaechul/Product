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
            // Mobile browsers start AudioContext in 'suspended' state — resume on user gesture
            if (this.ctx.state === 'suspended') {
                this.ctx.resume().catch(e => console.warn('AudioCtx resume failed:', e));
            }
            this.masterGain = this.ctx.createGain();
            this.masterGain.gain.value = 0.85;
            this.masterGain.connect(this.ctx.destination);

            this.bgmGain = this.ctx.createGain();
            this.bgmGain.gain.value = 0.95;
            this.bgmGain.connect(this.masterGain);

            this.sfxGain = this.ctx.createGain();
            this.sfxGain.gain.value = 0.9;
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
            // Register global gesture/visibility listeners ONCE for ctx unlock + BGM restart
            this._registerRecoveryListeners();
        } catch (e) {
            console.warn('Audio API not available', e);
        }
    },

    // Aggressive AudioContext unlock + BGM auto-restart
    _registerRecoveryListeners() {
        if (this._recoveryArmed) return;
        this._recoveryArmed = true;

        const tryUnlock = () => {
            if (!this.ctx) return;
            if (this._isHidden) return;  // 백그라운드에서는 BGM 재개 금지
            if (this.ctx.state === 'suspended' || this.ctx.state === 'interrupted') {
                this.ctx.resume().then(() => {
                    if (this._isHidden) return;
                    this._playSilentTick();
                    if (this._pendingBGMType && !this.bgmActive) {
                        this._actuallyPlayBGM(this._pendingBGMType);
                    } else if (this.bgmActive && this.bgmType) {
                        // Re-kick: BGM was thought running but ctx was suspended; restart cleanly
                        this._actuallyPlayBGM(this.bgmType);
                    }
                }).catch(() => {});
            } else {
                // Already running: if BGM should be playing but isn't, start it
                if (this._pendingBGMType && !this.bgmActive) {
                    this._actuallyPlayBGM(this._pendingBGMType);
                }
            }
        };

        // Unlock on ANY user gesture
        ['click', 'touchstart', 'touchend', 'keydown', 'pointerdown'].forEach(ev => {
            window.addEventListener(ev, tryUnlock, { passive: true });
        });
        // 게임이 백그라운드로 가면 BGM pause, 다시 돌아오면 resume
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this._handleHide();
            } else {
                this._handleShow();
                tryUnlock();
            }
        });
        window.addEventListener('blur', () => this._handleHide());
        window.addEventListener('focus', () => { this._handleShow(); tryUnlock(); });
        window.addEventListener('pagehide', () => this._handleHide());
        window.addEventListener('pageshow', () => { this._handleShow(); tryUnlock(); });
        window.addEventListener('orientationchange', () => setTimeout(tryUnlock, 200));
        window.addEventListener('resize', () => setTimeout(tryUnlock, 200));

        // Heartbeat watchdog: every 2s, if BGM should be playing but ctx is dead, recover
        setInterval(() => {
            if (!this.ctx) return;
            if (this._isHidden) return;  // 백그라운드에서는 자동 복구 금지
            if (this._pendingBGMType && !this.bgmActive && this.ctx.state === 'running') {
                this._actuallyPlayBGM(this._pendingBGMType);
            }
            if (this.bgmActive && this.ctx.state !== 'running') {
                this.ctx.resume().catch(() => {});
            }
        }, 2000);
    },

    // 페이지가 백그라운드로 갈 때 — BGM 즉시 정지 + 재개 타입 기억
    _handleHide() {
        this._isHidden = true;
        if (!this.bgmActive) return;
        this._resumeOnShowType = this.bgmType;
        // procedural BGM scheduler 즉시 종료
        this.bgmTimers.forEach(t => { clearTimeout(t); clearInterval(t); });
        this.bgmTimers = [];
        this.bgmActive = false;
        // MP3 일시정지 (현재 위치 보존)
        if (this.dayAudio && !this.dayAudio.paused) {
            try { this.dayAudio.pause(); } catch (e) {}
        }
        // AudioContext도 일시정지 (CPU/배터리 절약 + 안전)
        if (this.ctx && this.ctx.state === 'running') {
            this.ctx.suspend().catch(() => {});
        }
    },

    // 페이지가 포그라운드로 돌아올 때 — 멈췄던 BGM 재개
    _handleShow() {
        const wasHidden = this._isHidden;
        this._isHidden = false;
        if (!wasHidden || !this._resumeOnShowType) return;
        const type = this._resumeOnShowType;
        this._resumeOnShowType = null;
        if (type === 'day' && this.dayAudio) {
            // MP3는 pause된 위치에서 이어 재생
            this.bgmActive = true;
            this.bgmType = 'day';
            if (this.ctx && this.ctx.state !== 'running') {
                this.ctx.resume().catch(() => {});
            }
            try {
                const p = this.dayAudio.play();
                if (p && typeof p.catch === 'function') {
                    p.catch(() => {
                        // 자동재생 정책 차단 시 다음 제스처에서 재생되도록 pending에 등록
                        this._pendingBGMType = 'day';
                        this.bgmActive = false;
                    });
                }
            } catch (e) {
                this._pendingBGMType = 'day';
                this.bgmActive = false;
            }
        } else {
            // procedural BGM은 처음부터 다시 재생
            this.playBGM(type);
        }
    },

    // Play a near-silent ultrashort sample to force iOS audio pipeline alive
    _playSilentTick() {
        if (!this.ctx) return;
        try {
            const buf = this.ctx.createBuffer(1, 1, this.ctx.sampleRate);
            const src = this.ctx.createBufferSource();
            src.buffer = buf;
            src.connect(this.ctx.destination);
            src.start(0);
        } catch (e) {}
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

    // === Day BGM: MP3 파일 재생 (assets/day-bgm.mp3) ===
    // Web Audio MediaElementSource로 bgmGain 경유 — BGM 토글/믹스 그대로 사용
    _loadDayBGMAudio() {
        if (this.dayAudio) return this.dayAudio;
        try {
            const a = new Audio('assets/day-bgm.mp3');
            a.loop = true;
            a.preload = 'auto';
            this.dayAudio = a;
            // bgmGain 경유 라우팅 (한번만 연결 가능)
            try {
                const src = this.ctx.createMediaElementSource(a);
                src.connect(this.bgmGain);
                this.dayAudioRouted = true;
            } catch (e) {
                console.warn('Day BGM MediaElementSource failed, falling back to native playback:', e);
                this.dayAudioRouted = false;
            }
            return a;
        } catch (e) {
            console.warn('Day BGM audio load failed:', e);
            return null;
        }
    },

    // === Day BGM: Detective-style jazz noir (LEGACY procedural, MP3 로드 실패 시 fallback) ===
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
        this._pendingBGMType = type;
        // Ensure pipeline alive (no-op if already running)
        this._playSilentTick();
        if (this.ctx.state === 'suspended' || this.ctx.state === 'interrupted') {
            this.ctx.resume().then(() => {
                this._playSilentTick();
                this._actuallyPlayBGM(type);
            }).catch(() => {
                // Recovery listeners will retry on next gesture
            });
        } else {
            this._actuallyPlayBGM(type);
        }
    },

    _actuallyPlayBGM(type) {
        if (this._isHidden) {
            // 백그라운드: 즉시 재생 대신 visible 복귀 시 재생되도록 큐잉
            this._resumeOnShowType = type;
            return;
        }
        this.stopBGM();
        this.bgmActive = true;
        this.bgmType = type;
        this._pendingBGMType = null;
        try {
            if (type === 'day') this._playDayBGM();
            else this._playNightBGM();
        } catch (err) {
            console.warn('BGM start error:', err);
        }
    },

    _playDayBGM() {
        // MP3 우선 — 파일 로드 성공 시 procedural 코드는 실행하지 않음
        const a = this._loadDayBGMAudio();
        if (a) {
            try {
                a.currentTime = 0;
                // dayAudioRouted=true면 native volume은 1로 두고 bgmGain으로 제어
                // 라우팅 실패한 경우 element volume으로 직접 제어
                a.volume = this.dayAudioRouted ? 1.0 : 0.8;
                const p = a.play();
                if (p && typeof p.catch === 'function') {
                    p.catch(err => {
                        console.warn('Day BGM autoplay blocked — will retry on next gesture:', err);
                    });
                }
                return;
            } catch (err) {
                console.warn('Day BGM play error, falling back to procedural:', err);
            }
        }
        // === Fallback: procedural jazz noir (MP3 실패 시) ===
        const beatSec = 0.55;

        // Walking bass: Dm7 - G7 - Cmaj7 - Am7 (classic ii-V-I-vi)
        const bass = [
            73.4, 87.3, 110.0, 130.8,   // Dm7 bar 1 (D-F-A-C)
            98.0, 116.5, 146.8, 174.6,  // G7 bar 2 (G-B-D-F)
            65.4, 82.4, 98.0, 130.8,    // Cmaj7 bar 3 (C-E-G-C)
            55.0, 65.4, 82.4, 98.0,     // Am7 bar 4 (A-C-E-G)
        ];

        // Melody — singable detective theme (in C major)
        const melody = [
            // Bar 1 (Dm7)
            [587, 0.5], [659, 0.5], [698, 1], [659, 1], [587, 1],
            // Bar 2 (G7)
            [523, 0.5], [659, 0.5], [784, 1], [698, 0.5], [659, 0.5], [587, 1],
            // Bar 3 (Cmaj7) — main motif
            [523, 0.75], [659, 0.25], [784, 1], [880, 0.5], [784, 0.5], [659, 1],
            // Bar 4 (Am7) — resolve with descend
            [659, 0.5], [587, 0.5], [523, 0.5], [440, 0.5], [523, 2],
        ];

        // Chord voicings (3-note jazz voicings)
        const chordVoicings = [
            [293.7, 349.2, 440.0],  // Dm7 (D-F-A)
            [392.0, 493.9, 587.3],  // G7 (G-B-D)
            [261.6, 329.6, 392.0],  // Cmaj7 (C-E-G)
            [220.0, 261.6, 329.6],  // Am7 (A-C-E)
        ];

        let beat = 0;  // 0..15 within 4-bar loop
        const swing = 0.66;  // swing 8th delay ratio

        // Bass + comping scheduler (called every beat)
        const playBeat = () => {
            try {
                if (!this.bgmActive || this.bgmType !== 'day') return;
                const bar = Math.floor(beat / 4);
                const inBar = beat % 4;

                // Walking bass
                this._playOsc(bass[beat], beatSec * 0.9, 'triangle', this.bgmGain, {
                    vol: 0.16, attack: 0.02, release: 0.1
                });

                // Drum kit
                if (inBar === 0) this._playKick(0);
                if (inBar === 2) this._playSnare(0);
                this._playHihat(0, false);
                this._playHihat(beatSec * swing, true);  // swing 8th

                // Chord stabs (comping) — beats 2 and 4 only
                if (inBar === 1 || inBar === 3) {
                    const voicing = chordVoicings[bar];
                    voicing.forEach(f => {
                        this._playOsc(f, beatSec * 0.4, 'sawtooth', this.bgmGain, {
                            vol: 0.03, attack: 0.01, release: 0.15,
                            filter: { type: 'lowpass', freq: 1800, q: 0.8 }
                        });
                    });
                }

                beat = (beat + 1) % 16;
            } catch (err) {
                console.warn('Day BGM beat error:', err);
            }
        };
        playBeat();
        this.bgmTimers.push(setInterval(playBeat, beatSec * 1000));

        // Melody scheduler — independent timing
        let mIdx = 0;
        const playMelodyNote = () => {
            try {
                if (!this.bgmActive || this.bgmType !== 'day') return;
                const [freq, dur] = melody[mIdx % melody.length];
                if (freq !== null) {
                    this._playOsc(freq, dur * beatSec * 0.85, 'triangle', this.bgmGain, {
                        vol: 0.13, attack: 0.04, release: 0.15,
                        filter: { type: 'lowpass', freq: 2400, q: 1 }
                    });
                    // Octave shimmer for jazz character
                    this._playOsc(freq * 2, dur * beatSec * 0.4, 'sine', this.bgmGain, {
                        vol: 0.03, attack: 0.02, release: 0.1
                    });
                }
                mIdx++;
                this.bgmTimers.push(setTimeout(playMelodyNote, dur * beatSec * 1000));
            } catch (err) {
                console.warn('Day BGM melody error:', err);
            }
        };
        // Melody starts after 1 bar of intro
        this.bgmTimers.push(setTimeout(playMelodyNote, beatSec * 4 * 1000));
    },

    _playNightBGM() {
        // Single-track: eerie melody with bass drone only (no overlapping chord pad)
        const beatLen = 0.55;
        let mIdx = 0;
        let beatCount = 0;

        const playMelodyNote = () => {
            if (!this.bgmActive || this.bgmType !== 'night') return;
            const [freq, dur] = this.nightMelody[mIdx % this.nightMelody.length];
            this._playOsc(freq, dur * beatLen * 0.9, 'sine', this.bgmGain, {
                vol: 0.12, attack: 0.15, release: 0.4,
                filter: { type: 'lowpass', freq: 1500, q: 1.5 }
            });
            // Bass drone matching root note
            this._playOsc(freq / 4, dur * beatLen * 0.95, 'sawtooth', this.bgmGain, {
                vol: 0.06, attack: 0.2, release: 0.3,
                filter: { type: 'lowpass', freq: 350, q: 2 }
            });

            beatCount++;
            // Heartbeat kick every 8 beats
            if (beatCount % 6 === 1) {
                this._playKick(0);
                this._playKick(beatLen * 0.4);
            }

            mIdx++;
            this.bgmTimers.push(setTimeout(playMelodyNote, dur * beatLen * 1000));
        };
        playMelodyNote();
    },

    stopBGM() {
        this.bgmActive = false;
        this.bgmType = null;
        this.bgmTimers.forEach(t => { clearTimeout(t); clearInterval(t); });
        this.bgmTimers = [];
        if (this.dayAudio) {
            try { this.dayAudio.pause(); } catch (e) {}
        }
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
            case 'jump':
                this._playOsc(280, 0.15, 'sine', this.sfxGain, { vol: 0.18, glide: 580 });
                break;
            case 'land':
                this._playOsc(140, 0.1, 'square', this.sfxGain, { vol: 0.12 });
                break;
            case 'run_step':
                this._playOsc(60 + Math.random() * 30, 0.04, 'square', this.sfxGain, { vol: 0.08 });
                break;
        }
    }
};
