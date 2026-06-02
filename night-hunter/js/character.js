// character.js v6 — Feminine GLB 기반 (베이스 메시 + 분리 애니메이션)
// 베이스: assets/models/soyun.glb (Feminine_TPose)
// 애니: assets/models/idle.glb / walk.glb / run.glb
// API: ChibiCharacter.preload(), .create(cfg), instance.setState('idle'|'walk'|'run')

(function () {
    'use strict';
    if (typeof THREE === 'undefined') {
        console.error('[ChibiCharacter] THREE 미정의'); return;
    }
    if (typeof THREE.GLTFLoader === 'undefined') {
        console.error('[ChibiCharacter] GLTFLoader 미정의'); return;
    }

    // ── 캐시 ──
    const meshCache  = {};   // { 'soyun': gltf, 'hayun': gltf }
    const animCache  = {};   // { 'idle': clip, 'walk': clip, 'run': clip }

    function loadGLB(path) {
        return new Promise((resolve, reject) => {
            new THREE.GLTFLoader().load(
                path,
                resolve,
                undefined,
                (err) => { console.warn('[ChibiCharacter] 로드 실패', path, err); reject(err); }
            );
        });
    }

    const ChibiCharacter = {
        loaded: false,
        preload() {
            if (this._promise) return this._promise;
            this._promise = Promise.all([
                // 메시 (T-Pose 베이스)
                loadGLB('assets/models/soyun.glb').then(g => { meshCache['soyun'] = g; }),
                loadGLB('assets/models/hayun.glb').then(g => { meshCache['hayun'] = g; }),
                // 공통 애니메이션
                loadGLB('assets/models/idle.glb').then(g => {
                    if (g.animations.length) animCache['idle'] = g.animations[0];
                }),
                loadGLB('assets/models/walk.glb').then(g => {
                    if (g.animations.length) animCache['walk'] = g.animations[0];
                }),
                loadGLB('assets/models/run.glb').then(g => {
                    if (g.animations.length) animCache['run'] = g.animations[0];
                }),
            ]).then(() => {
                this.loaded = true;
                console.log('[ChibiCharacter] 로드 완료 — 메시:', Object.keys(meshCache),
                            '애니:', Object.keys(animCache));
                return true;
            }).catch(err => {
                console.error('[ChibiCharacter] preload 실패', err);
                return false;
            });
            return this._promise;
        },
        create(cfg) {
            try { return new ChibiInstance(cfg || {}); }
            catch (err) { console.error('[ChibiCharacter] create 실패', err); return null; }
        }
    };

    // ── 인스턴스 ──
    class ChibiInstance extends THREE.Group {
        constructor(cfg) {
            super();
            this.cfg = cfg;
            const name = cfg.name || 'soyun';
            const gltf = meshCache[name] || meshCache['soyun'];
            if (!gltf) { console.error('[ChibiCharacter] 캐시 미스', name); return; }

            // 모델 복제 (각 인스턴스 독립)
            this._model = THREE.SkeletonUtils
                ? THREE.SkeletonUtils.clone(gltf.scene)
                : gltf.scene.clone(true);

            // 여성 캐릭터 스케일 조정 (약 1.7m 키 기준)
            this._model.scale.set(1.0, 1.0, 1.0);
            this._model.position.y = 0;
            this.add(this._model);

            // 그림자
            this._model.traverse(o => {
                if (o.isMesh) { o.castShadow = true; o.receiveShadow = false; }
            });

            // ── AnimationMixer ──
            this._mixer = new THREE.AnimationMixer(this._model);
            this._actions = {};

            // 분리 애니메이션 클립을 믹서에 등록
            ['idle', 'walk', 'run'].forEach(key => {
                const clip = animCache[key];
                if (clip) {
                    this._actions[key] = this._mixer.clipAction(clip);
                } else {
                    console.warn('[ChibiCharacter] 애니 없음:', key);
                }
            });

            this._state = null;
            this.setState('idle');
        }

        setState(name) {
            if (name === this._state) return;
            const next = this._actions[name] || this._actions['idle'];
            if (!next) return;
            const prev = this._currentAction;
            if (prev && prev !== next) prev.fadeOut(0.2);
            next.reset().fadeIn(0.2).play();
            this._currentAction = next;
            this._state = name;
        }

        update(dt) {
            if (this._mixer) this._mixer.update(dt);
        }

        setPosition(x, y, z) { this.position.set(x, y, z); }
        setRotation(yRad)    { this.rotation.y = yRad; }

        dispose() {
            if (this._mixer) this._mixer.stopAllAction();
            this.traverse(o => {
                if (o.geometry) o.geometry.dispose();
                if (o.material) {
                    if (Array.isArray(o.material)) o.material.forEach(m => m.dispose());
                    else o.material.dispose();
                }
            });
            if (this.parent) this.parent.remove(this);
        }
    }

    window.ChibiCharacter = ChibiCharacter;
    window.ChibiInstance  = ChibiInstance;
})();
