// character.js — FBX 애니메이션 기반 chibi 캐릭터 시스템 (소윤/하윤)
// Mixamo 스타일 FBX(스켈레톤 + 애니메이션) + 절차적 chibi 메시 부착
// 모델 로드 실패 시 main.js의 기존 절차적 캐릭터(fallback)로 동작.

(function () {
    'use strict';
    if (typeof THREE === 'undefined') {
        console.error('[ChibiCharacter] THREE required.');
        return;
    }

    const MODEL_PATHS = {
        idle: 'assets/models/idle.fbx',
        walk: 'assets/models/walk.fbx',
        run:  'assets/models/run.fbx'
    };

    // mixamorig: prefix 정규화
    function cleanBoneName(name) {
        return (name || '').replace(/^mixamorig[:\d]*/i, '').replace(/^_+/, '');
    }

    function findBone(root, candidates) {
        let found = null;
        root.traverse(obj => {
            if (found) return;
            if (!obj.isBone && obj.type !== 'Bone') return;
            const clean = cleanBoneName(obj.name);
            if (candidates.includes(clean)) found = obj;
        });
        return found;
    }

    // ── 모듈 상태 (싱글톤) ─────────────────────────────────
    const ChibiCharacter = {
        cache: { idle: null, walk: null, run: null },
        loaded: false,
        loading: null,

        // 페이지 로드 시 1회 호출. 성공 여부 boolean 반환.
        preload() {
            if (this.loaded) return Promise.resolve(true);
            if (this.loading) return this.loading;
            if (typeof THREE.FBXLoader === 'undefined') {
                console.warn('[ChibiCharacter] FBXLoader 미포함 — fallback 사용');
                return Promise.resolve(false);
            }
            const loader = new THREE.FBXLoader();
            const loadOne = (key, path) => new Promise(res => {
                loader.load(path,
                    obj => { this.cache[key] = obj; res(true); },
                    undefined,
                    err => {
                        console.warn('[ChibiCharacter] ' + path + ' 로드 실패:', err && err.message || err);
                        res(false);
                    }
                );
            });
            this.loading = Promise.all([
                loadOne('idle', MODEL_PATHS.idle),
                loadOne('walk', MODEL_PATHS.walk),
                loadOne('run',  MODEL_PATHS.run)
            ]).then(results => {
                this.loaded = results.every(Boolean);
                if (this.loaded) {
                    console.log('[ChibiCharacter] FBX 3개 로드 완료 (idle/walk/run)');
                } else {
                    console.warn('[ChibiCharacter] 일부 FBX 로드 실패 — fallback 사용');
                }
                return this.loaded;
            });
            return this.loading;
        },

        // 새 인스턴스 생성. 로드 안된 경우 null 반환 (호출측 fallback).
        create(cfg) {
            if (!this.loaded) return null;
            try {
                return new ChibiInstance(cfg || {}, this.cache);
            } catch (err) {
                console.error('[ChibiCharacter] 인스턴스 생성 실패:', err);
                return null;
            }
        }
    };

    // ── 인스턴스 ─────────────────────────────────────────
    class ChibiInstance extends THREE.Group {
        constructor(cfg, animCache) {
            super();
            this.cfg = Object.assign({
                name: 'soyun',
                skinColor:  0xfde0c8,
                hairColor:  0x5d3a1c,
                eyeColor:   0x7a4d28,
                pupilColor: 0x1a0a04,
                lipColor:   0xc97560,
                browColor:  0x3a2010,
                hairStyle:  'long',     // 'long' | 'braids'
                accessory:  'redClip',  // 'redClip' | 'headset' | null
                shirtColor: 0xf5f3ec,
                coatColor:  0x1a1f2e,
                pantsColor: 0x222a3a,
                shoeColor:  0x0a0a0a,
                scale: 1.0
            }, cfg);

            // 1) 베이스 스켈레톤: idle FBX 클론
            const base = THREE.SkeletonUtils
                ? THREE.SkeletonUtils.clone(animCache.idle)
                : animCache.idle.clone(true);
            base.traverse(obj => {
                if (obj.isMesh) {
                    // Mixamo가 placeholder 메시를 갖고 있을 수 있음 — 숨김
                    obj.visible = false;
                }
            });
            this.skeletonRoot = base;
            this.add(base);

            // 모델 크기 정규화 — Mixamo는 보통 100단위, 우리 월드는 m 단위
            // 캐릭터의 발-머리 높이가 약 1.8m가 되도록 자동 스케일
            const box = new THREE.Box3().setFromObject(base);
            const sz = new THREE.Vector3(); box.getSize(sz);
            const targetH = 1.8;
            if (sz.y > 0.01) {
                const s = targetH / sz.y;
                base.scale.setScalar(s);
            }
            // 발이 y=0 (지면)에 닿도록 보정
            const box2 = new THREE.Box3().setFromObject(base);
            if (box2.min.y < 0 || box2.min.y > 0.01) {
                base.position.y -= box2.min.y;
            }

            // 2) 본 찾기 (mixamorig: prefix 정규화)
            this.bones = {
                hips:     findBone(base, ['Hips', 'hips']),
                spine:    findBone(base, ['Spine', 'Spine1', 'Spine2']),
                chest:    findBone(base, ['Spine2', 'Spine1', 'Chest']),
                neck:     findBone(base, ['Neck']),
                head:     findBone(base, ['Head']),
                leftArm:  findBone(base, ['LeftArm', 'LeftUpperArm']),
                rightArm: findBone(base, ['RightArm', 'RightUpperArm']),
                leftForeArm:  findBone(base, ['LeftForeArm', 'LeftLowerArm']),
                rightForeArm: findBone(base, ['RightForeArm', 'RightLowerArm']),
                leftHand:  findBone(base, ['LeftHand']),
                rightHand: findBone(base, ['RightHand']),
                leftUpLeg:  findBone(base, ['LeftUpLeg', 'LeftHip']),
                rightUpLeg: findBone(base, ['RightUpLeg', 'RightHip']),
                leftLeg:    findBone(base, ['LeftLeg', 'LeftKnee']),
                rightLeg:   findBone(base, ['RightLeg', 'RightKnee']),
                leftFoot:   findBone(base, ['LeftFoot']),
                rightFoot:  findBone(base, ['RightFoot'])
            };

            // 3) 절차적 chibi 메시 빌드 (본에 부착)
            this._buildMaterials();
            this._buildChibiMesh();

            // 4) AnimationMixer + 클립 등록
            this.mixer = new THREE.AnimationMixer(base);
            this.actions = {};
            ['idle', 'walk', 'run'].forEach(k => {
                const src = animCache[k];
                if (src && src.animations && src.animations[0]) {
                    const clip = src.animations[0];
                    const act = this.mixer.clipAction(clip);
                    act.play();
                    act.setEffectiveWeight(k === 'idle' ? 1 : 0);
                    this.actions[k] = act;
                }
            });
            this.currentState = 'idle';

            if (this.cfg.scale !== 1.0) this.scale.setScalar(this.cfg.scale);
        }

        _buildMaterials() {
            const c = this.cfg;
            this.mats = {
                skin:  new THREE.MeshStandardMaterial({ color: c.skinColor, roughness: 0.55 }),
                hair:  new THREE.MeshStandardMaterial({ color: c.hairColor, roughness: 0.45 }),
                shirt: new THREE.MeshStandardMaterial({ color: c.shirtColor, roughness: 0.50 }),
                coat:  new THREE.MeshStandardMaterial({ color: c.coatColor, roughness: 0.55, metalness: 0.10 }),
                pants: new THREE.MeshStandardMaterial({ color: c.pantsColor, roughness: 0.60 }),
                shoe:  new THREE.MeshStandardMaterial({ color: c.shoeColor, roughness: 0.35, metalness: 0.25 }),
                eyeW:  new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.20 }),
                eyeI:  new THREE.MeshStandardMaterial({ color: c.eyeColor, roughness: 0.22 }),
                eyeP:  new THREE.MeshStandardMaterial({ color: c.pupilColor, roughness: 0.18 }),
                hi:    new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.4 }),
                brow:  new THREE.MeshStandardMaterial({ color: c.browColor, roughness: 0.60 }),
                lip:   new THREE.MeshStandardMaterial({ color: c.lipColor, roughness: 0.40 }),
                cheek: new THREE.MeshStandardMaterial({ color: 0xffaaaa, transparent: true, opacity: 0.45 }),
                badge: new THREE.MeshStandardMaterial({ color: 0xdaa520, roughness: 0.20, metalness: 0.90, emissive: 0x5a3a00, emissiveIntensity: 0.25 }),
                red:   new THREE.MeshStandardMaterial({ color: 0xc01818, roughness: 0.40 }),
                green: new THREE.MeshStandardMaterial({ color: 0x4a8a3e, roughness: 0.50 })
            };
        }

        _buildChibiMesh() {
            const m = this.mats;
            const cfg = this.cfg;

            // FBX 스켈레톤이 실제 m 단위로 정규화되었으므로 비율 그대로 사용
            // 단, 본의 local 좌표계는 FBX 원본 스케일 기준이므로
            // skeletonRoot.scale로 글로벌 보정됨. 본 자식으로 부착하는 메시는
            // 원본 단위 기준(약 100x)으로 그릴 필요가 있음.
            // → 본 자식에 sub-group을 만들어 (1/100) 스케일로 보정
            const fbxUnitScale = 1 / (this.skeletonRoot.scale.x || 1);
            const Smk = (parentBone) => {
                if (!parentBone) return null;
                const holder = new THREE.Group();
                holder.scale.setScalar(fbxUnitScale);
                parentBone.add(holder);
                return holder;
            };

            // ─ 머리 (chibi 비율 — 크게) ─
            const headHolder = Smk(this.bones.head);
            if (headHolder) {
                const HEAD_R = 0.30;
                // 두개골
                const skull = new THREE.Mesh(new THREE.SphereGeometry(HEAD_R, 24, 20), m.skin);
                skull.castShadow = true;
                skull.scale.set(1.0, 1.05, 1.0);
                headHolder.add(skull);

                // 볼터치
                const cheekL = new THREE.Mesh(new THREE.SphereGeometry(0.06, 10, 10), m.cheek);
                cheekL.position.set(-0.17, -0.05, 0.22); cheekL.scale.set(1, 0.7, 0.3);
                headHolder.add(cheekL);
                const cheekR = cheekL.clone(); cheekR.position.x = 0.17;
                headHolder.add(cheekR);

                // 큰 눈 (흰자 + 홍채 + 동공 + 하이라이트)
                const mkEye = (sx) => {
                    const g = new THREE.Group();
                    const w = new THREE.Mesh(new THREE.SphereGeometry(0.085, 16, 16), m.eyeW);
                    w.scale.set(1, 1.15, 0.55); g.add(w);
                    const i = new THREE.Mesh(new THREE.SphereGeometry(0.055, 14, 14), m.eyeI);
                    i.position.set(0, 0, 0.04); i.scale.set(1, 1, 0.4); g.add(i);
                    const p = new THREE.Mesh(new THREE.SphereGeometry(0.028, 12, 12), m.eyeP);
                    p.position.set(0, 0, 0.07); p.scale.set(1, 1, 0.4); g.add(p);
                    const h1 = new THREE.Mesh(new THREE.SphereGeometry(0.014, 10, 10), m.hi);
                    h1.position.set(-0.012, 0.018, 0.085); g.add(h1);
                    const h2 = new THREE.Mesh(new THREE.SphereGeometry(0.008, 10, 10), m.hi);
                    h2.position.set(0.018, -0.015, 0.085); g.add(h2);
                    g.position.set(sx, 0.005, 0.24);
                    return g;
                };
                headHolder.add(mkEye(-0.11));
                headHolder.add(mkEye(0.11));

                // 눈썹
                const browL = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.022, 0.015), m.brow);
                browL.position.set(-0.11, 0.085, 0.275); browL.rotation.z = 0.12;
                headHolder.add(browL);
                const browR = browL.clone(); browR.position.x = 0.11; browR.rotation.z = -0.12;
                headHolder.add(browR);

                // 코 (살짝)
                const nose = new THREE.Mesh(new THREE.SphereGeometry(0.014, 8, 8), m.skin);
                nose.position.set(0, -0.025, 0.295);
                headHolder.add(nose);

                // 입
                const mouth = new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 10), m.lip);
                mouth.position.set(0, -0.105, 0.285);
                mouth.scale.set(1.4, 0.5, 0.3);
                headHolder.add(mouth);

                // 헤어 — 캡(두피 덮개)
                const hairCap = new THREE.Mesh(
                    new THREE.SphereGeometry(HEAD_R + 0.015, 24, 18, 0, Math.PI*2, 0, Math.PI*0.55),
                    m.hair
                );
                hairCap.position.y = 0.0;
                headHolder.add(hairCap);

                // 앞머리 (뱅)
                const bangs = new THREE.Mesh(
                    new THREE.SphereGeometry(0.21, 18, 14, 0, Math.PI*2, 0, Math.PI*0.45),
                    m.hair
                );
                bangs.position.set(0, 0.13, 0.16);
                bangs.scale.set(1.4, 0.65, 0.55);
                headHolder.add(bangs);

                // 헤어스타일
                if (cfg.hairStyle === 'braids') {
                    // 양갈래
                    [-1, 1].forEach(side => {
                        const br = new THREE.Mesh(
                            new THREE.CylinderGeometry(0.045, 0.06, 0.42, 10),
                            m.hair
                        );
                        br.position.set(side * 0.27, -0.18, -0.05);
                        br.rotation.z = side * 0.20;
                        br.castShadow = true;
                        headHolder.add(br);
                        // 끝 매듭
                        const tip = new THREE.Mesh(new THREE.SphereGeometry(0.055, 10, 10), m.hair);
                        tip.position.set(side * 0.32, -0.39, -0.05);
                        headHolder.add(tip);
                        // 헤어밴드 (녹색)
                        const band = new THREE.Mesh(
                            new THREE.TorusGeometry(0.055, 0.012, 6, 14),
                            m.green
                        );
                        band.position.set(side * 0.28, -0.07, -0.05);
                        band.rotation.x = Math.PI / 2;
                        headHolder.add(band);
                    });
                } else {
                    // 긴 생머리 — 뒤로 흐름
                    const back = new THREE.Mesh(
                        new THREE.SphereGeometry(0.32, 18, 16, 0, Math.PI*2, 0, Math.PI*0.55),
                        m.hair
                    );
                    back.position.set(0, -0.04, -0.06);
                    back.scale.set(1.0, 1.4, 0.85);
                    headHolder.add(back);
                    // 사이드
                    [-1, 1].forEach(side => {
                        const s = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.32, 0.12), m.hair);
                        s.position.set(side * 0.22, -0.10, 0.06);
                        s.rotation.z = side * 0.20;
                        headHolder.add(s);
                    });
                }

                // 액세서리
                if (cfg.accessory === 'redClip') {
                    const clip = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.025, 0.05), m.red);
                    clip.position.set(-0.16, 0.20, 0.22);
                    clip.rotation.z = 0.4;
                    headHolder.add(clip);
                } else if (cfg.accessory === 'headset') {
                    const band = new THREE.Mesh(
                        new THREE.TorusGeometry(0.30, 0.018, 6, 18, Math.PI),
                        new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.4, metalness: 0.4 })
                    );
                    band.rotation.x = Math.PI / 2;
                    band.position.y = 0.21;
                    headHolder.add(band);
                    [-1, 1].forEach(side => {
                        const cup = new THREE.Mesh(
                            new THREE.SphereGeometry(0.055, 12, 12),
                            new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.45 })
                        );
                        cup.position.set(side * 0.30, 0.05, 0);
                        cup.scale.set(0.7, 1, 0.7);
                        headHolder.add(cup);
                    });
                    // 마이크
                    const mic = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.015, 0.18), m.shoe);
                    mic.position.set(0.21, -0.06, 0.10); mic.rotation.y = -0.4;
                    headHolder.add(mic);
                }
            }

            // ─ 상체 (코트 + 셔츠) ─
            const spineHolder = Smk(this.bones.spine || this.bones.chest);
            if (spineHolder) {
                const torso = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.20, 0.22, 0.55, 14),
                    m.coat
                );
                torso.position.y = 0.18;
                torso.castShadow = true;
                spineHolder.add(torso);
                // 셔츠 V
                const shirt = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.19, 0.21, 0.30, 14, 1, false, -Math.PI/6, Math.PI/3),
                    m.shirt
                );
                shirt.position.set(0, 0.30, 0.005);
                spineHolder.add(shirt);
                // 형사 배지
                const badge = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.045, 0.045, 0.012, 12),
                    m.badge
                );
                badge.rotation.x = Math.PI / 2;
                badge.position.set(-0.13, 0.32, 0.18);
                spineHolder.add(badge);
            }

            // ─ 골반/하체 ─
            const hipHolder = Smk(this.bones.hips);
            if (hipHolder) {
                const pelvis = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.20, 0.18, 14), m.pants);
                pelvis.position.y = -0.05;
                hipHolder.add(pelvis);
            }

            // ─ 팔 (어깨 → 팔뚝 → 손) ─
            const armR = 0.07;
            [
                { bone: this.bones.leftArm,  fore: this.bones.leftForeArm,  hand: this.bones.leftHand,  side: -1 },
                { bone: this.bones.rightArm, fore: this.bones.rightForeArm, hand: this.bones.rightHand, side: 1 }
            ].forEach(({ bone, fore, hand, side }) => {
                const up = Smk(bone);
                if (up) {
                    // 어깨 본 → 팔뚝 본 사이를 채우는 원통
                    const upMesh = new THREE.Mesh(new THREE.CylinderGeometry(armR, armR*0.9, 0.30, 12), m.coat);
                    upMesh.position.y = -0.15;
                    upMesh.castShadow = true;
                    up.add(upMesh);
                }
                const fo = Smk(fore);
                if (fo) {
                    const fmesh = new THREE.Mesh(new THREE.CylinderGeometry(armR*0.9, armR*0.8, 0.28, 12), m.coat);
                    fmesh.position.y = -0.14;
                    fmesh.castShadow = true;
                    fo.add(fmesh);
                }
                const ha = Smk(hand);
                if (ha) {
                    const h = new THREE.Mesh(new THREE.SphereGeometry(0.075, 12, 12), m.skin);
                    h.scale.set(0.9, 1.0, 0.7);
                    ha.add(h);
                }
            });

            // ─ 다리 (허벅지 → 종아리 → 발) ─
            const legR = 0.085;
            [
                { up: this.bones.leftUpLeg,  lo: this.bones.leftLeg,  ft: this.bones.leftFoot },
                { up: this.bones.rightUpLeg, lo: this.bones.rightLeg, ft: this.bones.rightFoot }
            ].forEach(({ up, lo, ft }) => {
                const u = Smk(up);
                if (u) {
                    const t = new THREE.Mesh(new THREE.CylinderGeometry(legR, legR*0.92, 0.36, 12), m.pants);
                    t.position.y = -0.18;
                    t.castShadow = true;
                    u.add(t);
                }
                const l = Smk(lo);
                if (l) {
                    const s = new THREE.Mesh(new THREE.CylinderGeometry(legR*0.92, legR*0.78, 0.34, 12), m.pants);
                    s.position.y = -0.17;
                    s.castShadow = true;
                    l.add(s);
                }
                const f = Smk(ft);
                if (f) {
                    const boot = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.10, 0.26), m.shoe);
                    boot.position.set(0, -0.05, 0.04);
                    boot.castShadow = true;
                    f.add(boot);
                }
            });
        }

        setState(name) {
            if (!this.actions[name] || name === this.currentState) return;
            const from = this.actions[this.currentState];
            const to   = this.actions[name];
            const FADE = 0.20;
            if (from) from.fadeOut(FADE);
            to.reset().fadeIn(FADE);
            this.currentState = name;
        }

        update(dt) {
            if (this.mixer) this.mixer.update(dt);
        }

        setPosition(x, y, z) { this.position.set(x, y, z); }
        setRotation(yRad)    { this.rotation.y = yRad; }

        dispose() {
            this.traverse(obj => {
                if (obj.geometry) obj.geometry.dispose();
                if (obj.material) {
                    if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
                    else obj.material.dispose();
                }
            });
            if (this.parent) this.parent.remove(this);
            this.mixer = null;
        }
    }

    window.ChibiCharacter = ChibiCharacter;
    window.ChibiInstance = ChibiInstance;
})();
