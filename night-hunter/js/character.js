// character.js v8 — soyun GLB 기반 (베이스 메시 + 분리 애니메이션)
// 베이스: assets/models/soyun.glb (스킨드 메시, Mixamo 스켈레톤)
// 애니: assets/models/idle.glb / walk.glb / run.glb (동일 스켈레톤 retarget)
// API: ChibiCharacter.preload(), .create(cfg), instance.setState('idle'|'walk'|'run')
// 주의: 스킨드 메시 복제에 THREE.SkeletonUtils 필수 (index.html 에서 로드)
// v8: Hips 수평 root motion 제거 → 제자리 재생 (게임이 위치를 직접 제어)

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

    // ── Root Motion 제거 ──
    // Mixamo/FBX 걷기·달리기 클립은 Hips(루트) 본에 전진 이동(translation)이 들어있다.
    // 게임이 playerGroup.position 으로 이동을 직접 제어하므로, 클립의 수평 이동(X,Z)을
    // 첫 프레임 값으로 고정해 "제자리(in-place)" 애니메이션으로 만든다.
    // Y(상하 바운스)는 유지해 자연스러움을 살린다.
    function stripHorizontalRootMotion(clip) {
        if (!clip || !clip.tracks) return clip;
        clip.tracks.forEach(t => {
            if (/\.position$/.test(t.name) && t.values && t.values.length >= 3) {
                const v = t.values;          // [x,y,z, x,y,z, ...]
                const x0 = v[0], z0 = v[2];
                for (let i = 0; i < v.length; i += 3) {
                    v[i]     = x0;           // X 고정 (수평 전진 제거)
                    v[i + 2] = z0;           // Z 고정
                    // v[i + 1] (Y) 는 그대로 두어 상하 바운스 유지
                }
            }
        });
        return clip;
    }

    const ChibiCharacter = {
        loaded: false,
        preload() {
            if (this._promise) return this._promise;
            this._promise = Promise.all([
                // 메시 (T-Pose 베이스)
                loadGLB('assets/models/soyun.glb').then(g => { meshCache['soyun'] = g; }),
                loadGLB('assets/models/hayun.glb').then(g => { meshCache['hayun'] = g; }),
                // 공통 애니메이션 (root motion 제거 → 제자리 재생)
                loadGLB('assets/models/idle.glb').then(g => {
                    if (g.animations.length) animCache['idle'] = stripHorizontalRootMotion(g.animations[0]);
                }),
                loadGLB('assets/models/walk.glb').then(g => {
                    if (g.animations.length) animCache['walk'] = stripHorizontalRootMotion(g.animations[0]);
                }),
                loadGLB('assets/models/run.glb').then(g => {
                    if (g.animations.length) animCache['run'] = stripHorizontalRootMotion(g.animations[0]);
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

            // 모델 복제 (각 인스턴스 독립) — 스킨드 메시는 SkeletonUtils 필수
            if (THREE.SkeletonUtils) {
                this._model = THREE.SkeletonUtils.clone(gltf.scene);
            } else {
                console.warn('[ChibiCharacter] SkeletonUtils 미로드 — 스킨 바인딩이 깨질 수 있음');
                this._model = gltf.scene.clone(true);
            }

            // 캐릭터 스케일 (약 1.7m 키 기준, 게임 월드 스케일에 맞춤)
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
