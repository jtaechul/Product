// character.js v5 — GLB 기반 캐릭터 (RobotExpressive 모델 사용)
// 14개 애니메이션 포함: Idle, Walking, Running, Jump, Wave, Dance, ThumbsUp, ...
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
    const cache = {};      // { 'soyun': gltf, 'hayun': gltf }
    let loaded = false;
    let loadingPromise = null;

    function loadOne(name, path) {
        return new Promise((resolve, reject) => {
            new THREE.GLTFLoader().load(path,
                (gltf) => { cache[name] = gltf; resolve(gltf); },
                undefined,
                (err) => { console.warn('[ChibiCharacter] 로드 실패', path, err); reject(err); }
            );
        });
    }

    const ChibiCharacter = {
        loaded: false,
        preload() {
            if (loadingPromise) return loadingPromise;
            loadingPromise = Promise.all([
                loadOne('soyun', 'assets/models/soyun.glb'),
                loadOne('hayun', 'assets/models/hayun.glb'),
            ]).then(() => {
                this.loaded = true;
                console.log('[ChibiCharacter] GLB 로드 완료', Object.keys(cache));
                return true;
            }).catch(err => {
                console.error('[ChibiCharacter] preload 실패', err);
                return false;
            });
            return loadingPromise;
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
            const gltf = cache[name] || cache['soyun'];
            if (!gltf) { console.error('[ChibiCharacter] 캐시 미스', name); return; }

            // 모델 복제 (각 인스턴스 독립)
            this._model = THREE.SkeletonUtils
                ? THREE.SkeletonUtils.clone(gltf.scene)
                : gltf.scene.clone(true);

            // RobotExpressive는 약 2m 키 → 캐릭터 크기 2.2 비율에 맞춰 스케일
            this._model.scale.set(0.5, 0.5, 0.5);
            this._model.position.y = 0;
            this.add(this._model);

            // 그림자
            this._model.traverse(o => {
                if (o.isMesh) { o.castShadow = true; o.receiveShadow = false; }
            });

            // ── AnimationMixer ──
            this._mixer = new THREE.AnimationMixer(this._model);
            this._actions = {};
            gltf.animations.forEach(clip => {
                this._actions[clip.name] = this._mixer.clipAction(clip);
            });

            // 상태 → 액션 매핑 (RobotExpressive 명칭)
            this._stateMap = {
                idle: 'Idle',
                walk: 'Walking',
                run:  'Running'
            };

            this._state = null;
            this.setState('idle');
        }

        setState(name) {
            if (name === this._state) return;
            const targetName = this._stateMap[name] || 'Idle';
            const next = this._actions[targetName];
            if (!next) return;
            const prev = this._currentAction;
            if (prev) prev.fadeOut(0.2);
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
