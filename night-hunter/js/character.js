// character.js v12 — soyun GLB 기반 (베이스 메시 + 분리 애니메이션 + 머리스타일)
// 베이스: assets/models/soyun.glb (스킨드 메시, Mixamo 스켈레톤)
// 애니: assets/models/idle.glb / walk.glb / run.glb (동일 스켈레톤 retarget)
// 머리: assets/models/hairstyles.glb (Sketchfab 모음, 9종)
// API: ChibiCharacter.preload(), .create(cfg), instance.setState('idle'|'walk'|'run')
//      instance.setHairstyle(index), instance.getHairstyleCount()
//      instance.setHairTransform({x,y,z,rx,ry,rz,s}) — 미리보기 튜닝용
//      instance.applyHeadCrop({yMin, zFront}) — 머리 정점 면 제거 (헤어 셸 숨김)
// v12: 6축 transform API + 머리 크롭 (Y>yMin AND Z>zFront 면 제거)

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
    const hairCache  = [];   // [mesh0, mesh1, ...] 머리스타일 메시 원본

    // 머리 부착 변환 — Sketchfab cm 단위 모델 → soyun 미터 단위 스켈레톤 부착
    // 지오메트리는 공통 정수리(Y=HAIR_REF_Y cm) 기준으로 재정렬되어
    // 스케일 피벗이 정수리에 고정되고 모든 헤어가 동일 기준으로 정렬된다.
    const HAIR_REF_Y     = 160;                 // 헤어팩 공통 정수리 높이(cm) — 스케일 피벗 기준
    const HAIR_DEFAULT = {
        x:   0,
        y:   0.26,                  // Head 본 로컬 기준 정수리 위치(m, 사용자 확정값)
        z:   0,
        rx:  0,
        ry:  3 * Math.PI / 2,       // 270° (Sketchfab→Mixamo 좌표계 보정)
        rz:  0,
        s:   0.011                  // cm → m (얼굴 대비 살짝 키움)
    };

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

    // hairstyles.glb 에서 머리 메시 9종 추출 (스킨 없음 → 일반 Mesh)
    function extractHairMeshes(gltf) {
        gltf.scene.traverse(o => {
            if (o.isMesh && !o.isSkinnedMesh) {
                hairCache.push(o);
            }
        });
        console.log('[ChibiCharacter] hairstyles 추출:', hairCache.length, '종');
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
                // 머리스타일 (선택사항 — 실패해도 계속)
                loadGLB('assets/models/hairstyles.glb').then(g => extractHairMeshes(g))
                    .catch(() => console.warn('[ChibiCharacter] hairstyles.glb 로드 실패 (계속 진행)')),
            ]).then(() => {
                this.loaded = true;
                console.log('[ChibiCharacter] 로드 완료 — 메시:', Object.keys(meshCache),
                            '애니:', Object.keys(animCache),
                            '머리:', hairCache.length);
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
        },
        getHairstyleCount() { return hairCache.length; }
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

            // Head 본 찾기 (머리스타일 부착 지점)
            this._headBone = null;
            this._model.traverse(o => {
                if (o.isBone && o.name === 'Head') this._headBone = o;
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
            this._hair = null;
            this._hairIndex = -1;
            this.setState('idle');

            // 머리스타일 기본값 (cfg.hairstyleIndex 또는 0)
            if (hairCache.length > 0) {
                const defaultIdx = (cfg.hairstyleIndex !== undefined) ? cfg.hairstyleIndex : 0;
                this.setHairstyle(defaultIdx);
            }
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

        // 머리스타일 교체 — index: 0..N-1, -1 이면 제거
        setHairstyle(index) {
            if (this._hair) {
                if (this._hair.parent) this._hair.parent.remove(this._hair);
                if (this._hair.geometry) this._hair.geometry.dispose();
                this._hair = null;
            }
            this._hairIndex = index;
            if (index < 0 || index >= hairCache.length) return;

            const src = hairCache[index];
            if (!src) return;

            // 원본 메시는 공유 자원이라 clone (텍스처는 공유, geometry는 독립 복제 후 가공)
            const hair = src.clone(true);
            // 지오메트리를 공통 정수리 기준점(cm)으로 이동 → 스케일이 Y를 끌고가지 않음 +
            // 모든 헤어스타일이 동일 기준으로 정렬됨
            hair.geometry = hair.geometry.clone();
            hair.geometry.translate(0, -HAIR_REF_Y, 0);
            hair.castShadow = true;

            // 현재 transform 값(없으면 기본값) 적용
            const t = this._hairXf || Object.assign({}, HAIR_DEFAULT);
            this._hairXf = t;
            hair.scale.setScalar(t.s);
            hair.position.set(t.x, t.y, t.z);
            hair.rotation.set(t.rx, t.ry, t.rz);

            // Head 본의 자식으로 부착 → 머리와 함께 회전/이동
            if (this._headBone) {
                this._headBone.add(hair);
            } else {
                this.add(hair);  // 폴백: 그룹 루트
            }
            this._hair = hair;
        }

        getHairstyleIndex() { return this._hairIndex; }

        // 헤어 6축 transform 미세조정 (미리보기 튜닝용)
        // 인자: { x, y, z, rx, ry, rz, s } — 일부만 지정해도 됨
        setHairTransform(xf) {
            this._hairXf = Object.assign(this._hairXf || Object.assign({}, HAIR_DEFAULT), xf);
            if (!this._hair) return;
            const t = this._hairXf;
            this._hair.position.set(t.x, t.y, t.z);
            this._hair.rotation.set(t.rx, t.ry, t.rz);
            this._hair.scale.setScalar(t.s);
        }

        getHairTransform() {
            return Object.assign({}, this._hairXf || HAIR_DEFAULT);
        }

        // soyun 머리(헤어 셸) 영역 면 제거 — 새 헤어로 덮을 때 기존 머리카락 숨김
        // 인자: { yMin, zFront }
        //   - yMin: 이 Y 이상의 정점이 포함된 면을 제거 후보로 표시 (m, soyun 메시 자체 좌표)
        //   - zFront: 이보다 Z가 작은(앞쪽=얼굴) 정점은 보호 → 뒤통수만 제거
        // 두 조건 모두 만족하는 정점이 하나라도 포함된 face는 indices에서 제거.
        // 결과는 메시 인덱스 버퍼에 비파괴적으로 적용 (원본 보관 → 슬라이더로 재적용 가능)
        applyHeadCrop({ yMin = 1.55, zFront = -0.02 } = {}) {
            if (!this._model) return;
            this._model.traverse(o => {
                if (!o.isSkinnedMesh && !o.isMesh) return;
                const geo = o.geometry;
                if (!geo || !geo.attributes || !geo.attributes.position) return;

                // 원본 인덱스 보관 (최초 1회)
                if (!geo.userData._origIndex) {
                    geo.userData._origIndex = geo.index ? geo.index.array.slice() : null;
                }
                const orig = geo.userData._origIndex;
                if (!orig) return;  // 비인덱스 메시 (드물지만 안전 가드)

                const positions = geo.attributes.position.array;
                const removeVert = new Uint8Array(positions.length / 3);
                for (let i = 0; i < removeVert.length; i++) {
                    const y = positions[i * 3 + 1];
                    const z = positions[i * 3 + 2];
                    if (y >= yMin && z >= zFront) removeVert[i] = 1;
                }

                const newIdx = [];
                for (let i = 0; i < orig.length; i += 3) {
                    const a = orig[i], b = orig[i + 1], c = orig[i + 2];
                    if (!removeVert[a] && !removeVert[b] && !removeVert[c]) {
                        newIdx.push(a, b, c);
                    }
                }
                geo.setIndex(newIdx);
            });
        }

        // 머리 크롭 원상복구
        clearHeadCrop() {
            if (!this._model) return;
            this._model.traverse(o => {
                if (!o.geometry) return;
                const orig = o.geometry.userData._origIndex;
                if (orig) o.geometry.setIndex(Array.from(orig));
            });
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
