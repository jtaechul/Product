// character.js v18 — soyun/hayun GLB 기반 (베이스 메시 + 분리 애니메이션)
// 베이스: assets/models/soyun.glb / hayun.glb (스킨드 메시, Mixamo 스켈레톤)
// 애니: assets/models/idle.glb / walk.glb / run.glb (동일 스켈레톤 retarget)
// v18: hairstyles.glb 제거 — 새 캐릭터 모델에 머리가 포함되어 헤어 부착/머리 크롭 불필요
// v20: iPad OOM 대응(애니 GLB 텍스처 즉시 해제) + 검정 캐릭터 보정(metalness=0/emissive 제거)
//      + 바운딩박스로 발바닥 지면 정렬
// API: ChibiCharacter.preload(), .create(cfg), instance.setState('idle'|'walk'|'run')
//      instance.setHairstyle(index), instance.getHairstyleCount()
//      instance.setHairTransform({x,y,z,rx,ry,rz,s})
//      instance.applyHeadCrop({yMin,yMax,zMin,zMax}) — 박스 안 정점 면 제거
// v13: 헤어 기본값 사용자 확정 / 회전 순서 YXZ / 머리 크롭 Y·Z 박스
// v14: 머리 크롭에 X축 추가 (6면 박스) + 헤어 메시는 크롭 대상에서 제외
// v15: 헤어 기본값 재확정 (y=0.2, z=-0.08, rz=21°, s=0.0128)
//      크롭 박스에 Y/Z 회전 지원 — 박스를 기울여서 자를 수 있음
// v16: 박스 회전을 명시적 Euler('YXZ') 로 통일 (헤어 짐벌과 일치)
//      (preview 에 박스 와이어프레임 시각화 추가)
// v17: 사용자 확정값으로 헤어/헤드크롭 고정 + 인스턴스 생성 시 자동 크롭 적용
//      캐릭터별 hairstyleIndex 지원 (cfg.hairstyleIndex)

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
    const DEG = Math.PI / 180;
    // 사용자가 미리보기로 직접 조정해 확정한 값 (2025-06-03)
    const HAIR_DEFAULT = {
        x:    0,
        y:    0.2,
        z:   -0.08,
        rx:   0,
        ry:  270 * DEG,             // Sketchfab → Mixamo 좌표계 보정
        rz:   21 * DEG,
        s:    0.01302
    };
    // soyun 본체 머리뭉치 자르기 박스 (사용자 확정값) — 모든 인스턴스 생성 시 자동 적용
    const HEAD_CROP_DEFAULT = {
        xMin: -Infinity, xMax: Infinity,    // X 무제한
        yMin:  1.64,      yMax: 1.80,
        zMin: -0.20,      zMax: 0.015,
        ryDeg: 10,        rzDeg: 0
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

    // 애니메이션만 필요한 GLB(idle/walk/run)는 클립 추출 후 메시·텍스처를 즉시 해제해
    // 모바일(iPad) WebGL 메모리 폭주(2048² 텍스처 다수 → OOM 크래시)를 방지한다.
    function disposeGLTFScene(gltf) {
        if (!gltf || !gltf.scene) return;
        gltf.scene.traverse(o => {
            if (o.geometry) o.geometry.dispose();
            const mats = Array.isArray(o.material) ? o.material : (o.material ? [o.material] : []);
            mats.forEach(m => {
                if (!m) return;
                for (const k in m) { const v = m[k]; if (v && v.isTexture) v.dispose(); }
                if (m.dispose) m.dispose();
            });
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
                // 메시 (T-Pose 베이스) — soyun/hayun GLB는 동일 모델이므로 1개만 로드해
                // iPad 메모리(2048² 텍스처)를 절약한다. 모든 캐릭터가 이 메시로 폴백된다.
                loadGLB('assets/models/soyun.glb').then(g => { meshCache['soyun'] = g; }),
                // 공통 애니메이션 (root motion 제거 → 제자리 재생)
                loadGLB('assets/models/idle.glb').then(g => {
                    if (g.animations.length) animCache['idle'] = stripHorizontalRootMotion(g.animations[0]);
                    disposeGLTFScene(g);   // 메시·텍스처 해제 (애니 클립만 사용)
                }),
                loadGLB('assets/models/walk.glb').then(g => {
                    if (g.animations.length) animCache['walk'] = stripHorizontalRootMotion(g.animations[0]);
                    disposeGLTFScene(g);
                }),
                loadGLB('assets/models/run.glb').then(g => {
                    if (g.animations.length) animCache['run'] = stripHorizontalRootMotion(g.animations[0]);
                    disposeGLTFScene(g);
                }),
                // (hairstyles.glb 제거됨 — 새 캐릭터 모델에 머리가 포함됨)
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

            // 재질 보정 + 그림자
            // 새 GLB는 metalness=1(완전 금속)이라 환경맵이 없으면 검게 렌더된다.
            // metalness를 낮추고 emissive 아티팩트를 제거해 텍스처가 정상적으로 보이게 한다.
            this._model.traverse(o => {
                if (!o.isMesh) return;
                o.castShadow = true; o.receiveShadow = false;
                const mats = Array.isArray(o.material) ? o.material : (o.material ? [o.material] : []);
                mats.forEach(m => {
                    if (!m) return;
                    if ('metalness' in m) m.metalness = 0.0;
                    if ('roughness' in m) m.roughness = 0.85;
                    if (m.emissive) m.emissive.setRGB(0, 0, 0);   // export 아티팩트(emissive=1,1,1) 제거
                    m.needsUpdate = true;
                });
            });

            // 발바닥을 정확히 지면(인스턴스 y=0 = playerGroup 원점)에 정렬 — 발 파묻힘/뜸 방지
            this._model.position.y = 0;
            this._model.updateMatrixWorld(true);
            const _box = new THREE.Box3().setFromObject(this._model);
            if (isFinite(_box.min.y)) this._model.position.y = -_box.min.y;

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
            // (hairstyles.glb 제거 — 머리 크롭/헤어 부착 없음. 새 모델에 머리 포함)
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
            // 마커: applyHeadCrop 이 본체만 자르고 헤어는 건너뛰도록
            hair.userData.isHair = true;
            hair.traverse(o => { o.userData.isHair = true; });

            // 현재 transform 값(없으면 기본값) 적용
            const t = this._hairXf || Object.assign({}, HAIR_DEFAULT);
            this._hairXf = t;
            hair.scale.setScalar(t.s);
            hair.position.set(t.x, t.y, t.z);
            // YXZ 순서: Y(좌우 돌리기)를 먼저 → X(앞뒤 기울임) → Z(좌우 기울임)
            // 기본 XYZ 로 두면 270° Y 회전이 X/Z 축을 회전시켜 직관 무너짐
            hair.rotation.set(t.rx, t.ry, t.rz, 'YXZ');

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
            this._hair.rotation.set(t.rx, t.ry, t.rz, 'YXZ');
            this._hair.scale.setScalar(t.s);
        }

        getHairTransform() {
            return Object.assign({}, this._hairXf || HAIR_DEFAULT);
        }

        // soyun 본체 영역 면 제거 — 새 헤어로 덮을 때 기존 머리카락 숨김
        // 인자: { xMin, xMax, yMin, yMax, zMin, zMax, ryDeg, rzDeg }
        //   xMin ≤ x ≤ xMax AND ... 박스 안 정점이 하나라도 포함된 face 를
        //   인덱스 버퍼에서 제거. 값을 생략하면 그 축은 무제한(±무한대).
        //   모든 값이 무한대면 원상복구.
        //   ryDeg/rzDeg: 박스 자체를 박스 중심 기준으로 Y/Z 축으로 회전.
        //     (Y 먼저, Z 다음 적용 — 정점은 역순으로 역회전 후 axis-aligned 검사)
        //   userData.isHair === true 마커 메시는 건너뜀 (헤어는 보호).
        // 비파괴: 원본 인덱스를 보관하므로 매번 재계산해도 안전.
        applyHeadCrop(opts = {}) {
            if (!this._model) return;
            const xMin = (opts.xMin !== undefined) ? opts.xMin : -Infinity;
            const xMax = (opts.xMax !== undefined) ? opts.xMax :  Infinity;
            const yMin = (opts.yMin !== undefined) ? opts.yMin : -Infinity;
            const yMax = (opts.yMax !== undefined) ? opts.yMax :  Infinity;
            const zMin = (opts.zMin !== undefined) ? opts.zMin : -Infinity;
            const zMax = (opts.zMax !== undefined) ? opts.zMax :  Infinity;
            const noBox = !isFinite(xMin) && !isFinite(xMax) &&
                          !isFinite(yMin) && !isFinite(yMax) &&
                          !isFinite(zMin) && !isFinite(zMax);

            // 박스 회전 → 정점을 박스 좌표계로 역변환할 행렬 계산
            // 박스는 Euler('YXZ', X=0) 으로 회전 — 헤어와 동일한 짐벌
            // (Y 가 가장 바깥쪽: ry 는 항상 절대 Y축 기준)
            const ryRad = (opts.ryDeg || 0) * DEG;
            const rzRad = (opts.rzDeg || 0) * DEG;
            const hasRot = ryRad !== 0 || rzRad !== 0;
            let mInv = null;
            if (hasRot) {
                const e = new THREE.Euler(0, ryRad, rzRad, 'YXZ');
                mInv = new THREE.Matrix4().makeRotationFromEuler(e).invert();
            }
            // 박스 중심 (무제한 축은 0)
            const cx = (isFinite(xMin) && isFinite(xMax)) ? (xMin + xMax) / 2 : 0;
            const cy = (isFinite(yMin) && isFinite(yMax)) ? (yMin + yMax) / 2 : 0;
            const cz = (isFinite(zMin) && isFinite(zMax)) ? (zMin + zMax) / 2 : 0;
            const tmpV = hasRot ? new THREE.Vector3() : null;

            this._model.traverse(o => {
                if (!o.isSkinnedMesh && !o.isMesh) return;
                // 헤어는 본에 부착되어 traverse 에 잡히므로 명시적으로 제외
                if (o.userData && o.userData.isHair) return;
                const geo = o.geometry;
                if (!geo || !geo.attributes || !geo.attributes.position) return;

                // 원본 인덱스 보관 (최초 1회)
                if (!geo.userData._origIndex) {
                    geo.userData._origIndex = geo.index ? geo.index.array.slice() : null;
                }
                const orig = geo.userData._origIndex;
                if (!orig) return;

                if (noBox) {
                    geo.setIndex(Array.from(orig));
                    return;
                }

                const positions = geo.attributes.position.array;
                const removeVert = new Uint8Array(positions.length / 3);
                for (let i = 0; i < removeVert.length; i++) {
                    let x = positions[i * 3 + 0];
                    let y = positions[i * 3 + 1];
                    let z = positions[i * 3 + 2];
                    if (hasRot) {
                        // 박스 중심 기준으로 평행이동 → 역회전 → 다시 평행이동
                        tmpV.set(x - cx, y - cy, z - cz).applyMatrix4(mInv);
                        x = tmpV.x + cx;
                        y = tmpV.y + cy;
                        z = tmpV.z + cz;
                    }
                    if (x >= xMin && x <= xMax &&
                        y >= yMin && y <= yMax &&
                        z >= zMin && z <= zMax) {
                        removeVert[i] = 1;
                    }
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
