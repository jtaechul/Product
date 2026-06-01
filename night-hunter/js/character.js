// character.js — Chibi 3D 여경 캐릭터 (절차적, 비율 1:2.5)
// 전체 높이 ~2.27, 머리 0.7, 몸통 0.65, 다리 0.52, 팔 0.50
// 모든 파츠는 characterGroup(ChibiInstance) 하위로 묶이며,
// 머리/몸통/팔/다리는 개별 그룹/메시 변수로 참조 가능.

(function () {
    'use strict';
    if (typeof THREE === 'undefined') {
        console.error('[ChibiCharacter] THREE required.');
        return;
    }

    // ── 싱글톤 API (main.js 호환) ──
    const ChibiCharacter = {
        loaded: false,
        loading: null,
        preload() {
            this.loaded = true;
            return Promise.resolve(true);
        },
        create(cfg) {
            try { return new ChibiInstance(cfg || {}); }
            catch (err) { console.error('[ChibiCharacter] create failed:', err); return null; }
        }
    };

    function mkMat(color, opts) {
        return new THREE.MeshStandardMaterial(Object.assign({ color, roughness: 0.6 }, opts || {}));
    }

    // ── characterGroup ── (instance)
    class ChibiInstance extends THREE.Group {
        constructor(cfg) {
            super();
            this.cfg = cfg;

            // 캐릭터별 색상 (cfg 오버라이드 가능 — 소윤/하윤 분기 지원)
            const C = this._colors = {
                skin:    cfg.skinColor  || 0xffdbac,
                hair:    cfg.hairColor  || 0x5c3d1e,
                eye:     cfg.eyeColor   || 0x1a0a00,
                lip:     cfg.lipColor   || 0xe05080,
                brow:    cfg.browColor  || 0x3b1f0a,
                uniform: cfg.coatColor  || 0x1a2444,
                hat:     0x0d1b2a,
                gold:    0xFFD700,
                shoe:    0x111111
            };

            this._buildHead();
            this._buildBody();
            this._buildArms();
            this._buildLegs();

            // 모든 파츠 castShadow
            this.traverse(o => {
                if (o.isMesh) { o.castShadow = true; o.receiveShadow = false; }
            });

            // 절차적 애니메이션 상태
            this._state = 'idle';
            this._phase = 0;
            this._amp = 0;
            this._targetAmp = 0;
            this._targetSpeed = 1.5;
        }

        // ──────────────────────────────────────
        //  [머리 그룹 - headGroup]
        // ──────────────────────────────────────
        _buildHead() {
            const headGroup = new THREE.Group();
            this.headGroup = headGroup;
            const C = this._colors;

            // 얼굴
            const face = new THREE.Mesh(
                new THREE.SphereGeometry(0.35, 32, 32),
                mkMat(C.skin)
            );
            face.position.set(0, 1.65, 0);
            headGroup.add(face);
            this.face = face;

            // 볼 홍조 (좌우)
            const cheekMat = new THREE.MeshStandardMaterial({
                color: 0xffb3b3, transparent: true, opacity: 0.6, roughness: 0.55
            });
            [-0.22, 0.22].forEach(x => {
                const cheek = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 16), cheekMat);
                cheek.position.set(x, 1.62, 0.28);
                headGroup.add(cheek);
            });

            // 눈 흰자 (좌우)
            const eyeWMat = mkMat(0xffffff, { roughness: 0.2 });
            [-0.13, 0.13].forEach(x => {
                const w = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 16), eyeWMat);
                w.position.set(x, 1.68, 0.30);
                headGroup.add(w);
            });

            // 눈동자 (좌우)
            const pupilMat = mkMat(C.eye, { roughness: 0.25 });
            [-0.13, 0.13].forEach(x => {
                const p = new THREE.Mesh(new THREE.SphereGeometry(0.06, 16, 16), pupilMat);
                p.position.set(x, 1.68, 0.345);
                headGroup.add(p);
            });

            // 눈 하이라이트 (좌우)
            const hiMat = new THREE.MeshStandardMaterial({
                color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.45
            });
            [-0.14, 0.14].forEach(x => {
                const h = new THREE.Mesh(new THREE.SphereGeometry(0.02, 8, 8), hiMat);
                h.position.set(x, 1.70, 0.36);
                headGroup.add(h);
            });

            // 눈썹 (좌우)
            const browMat = mkMat(C.brow, { roughness: 0.7 });
            [{ x: -0.13, rz:  0.12 },
             { x:  0.13, rz: -0.12 }].forEach(p => {
                const b = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.03, 0.02), browMat);
                b.position.set(p.x, 1.78, 0.32);
                b.rotation.z = p.rz;
                headGroup.add(b);
            });

            // 속눈썹 (좌우 각 3개 — fan 형태)
            const lashMat = mkMat(0x000000, { roughness: 0.6 });
            [-1, 1].forEach(side => {
                for (let i = 0; i < 3; i++) {
                    const lash = new THREE.Mesh(new THREE.BoxGeometry(0.025, 0.05, 0.01), lashMat);
                    // 눈 위쪽 바깥으로 펼침
                    const outOffset = side * (0.10 + 0.022 * i);
                    lash.position.set(outOffset, 1.745, 0.345);
                    lash.rotation.z = side * (0.18 + 0.18 * i);
                    headGroup.add(lash);
                }
            });

            // 코
            const nose = new THREE.Mesh(
                new THREE.SphereGeometry(0.03, 8, 8),
                mkMat(0xe8b88a)
            );
            nose.position.set(0, 1.60, 0.34);
            headGroup.add(nose);

            // 윗입술
            const lipUp = new THREE.Mesh(
                new THREE.BoxGeometry(0.15, 0.03, 0.02),
                mkMat(C.lip, { roughness: 0.45 })
            );
            lipUp.position.set(0, 1.52, 0.33);
            headGroup.add(lipUp);

            // 아랫입술
            const lipDn = new THREE.Mesh(
                new THREE.BoxGeometry(0.12, 0.035, 0.02),
                mkMat(C.lip, { roughness: 0.45 })
            );
            lipDn.position.set(0, 1.49, 0.33);
            headGroup.add(lipDn);

            // 미소 라인
            const smileLine = new THREE.Mesh(
                new THREE.BoxGeometry(0.10, 0.015, 0.01),
                mkMat(0x8b4513, { roughness: 0.6 })
            );
            smileLine.position.set(0, 1.505, 0.34);
            headGroup.add(smileLine);

            // 뒷머리
            const hairBack = new THREE.Mesh(
                new THREE.SphereGeometry(0.36, 32, 32),
                mkMat(C.hair, { roughness: 0.5 })
            );
            hairBack.position.set(0, 1.66, -0.05);
            hairBack.scale.z = 0.85;
            headGroup.add(hairBack);

            // 앞머리
            const bangs = new THREE.Mesh(
                new THREE.BoxGeometry(0.64, 0.14, 0.12),
                mkMat(C.hair, { roughness: 0.5 })
            );
            bangs.position.set(0, 1.90, 0.22);
            headGroup.add(bangs);

            // 옆머리 (좌우)
            [-0.36, 0.36].forEach(x => {
                const sh = new THREE.Mesh(
                    new THREE.BoxGeometry(0.12, 0.55, 0.12),
                    mkMat(C.hair, { roughness: 0.5 })
                );
                sh.position.set(x, 1.60, 0.04);
                headGroup.add(sh);
            });

            // 긴 머리카락 (어깨까지)
            const longHair = new THREE.Mesh(
                new THREE.BoxGeometry(0.58, 0.50, 0.10),
                mkMat(C.hair, { roughness: 0.5 })
            );
            longHair.position.set(0, 1.25, -0.18);
            headGroup.add(longHair);

            // 경찰 모자 챙
            const brim = new THREE.Mesh(
                new THREE.CylinderGeometry(0.44, 0.44, 0.04, 32),
                mkMat(C.hat, { roughness: 0.4, metalness: 0.05 })
            );
            brim.position.set(0, 1.92, 0);
            headGroup.add(brim);

            // 경찰 모자 몸체
            const hatBody = new THREE.Mesh(
                new THREE.CylinderGeometry(0.30, 0.34, 0.25, 32),
                mkMat(C.hat, { roughness: 0.4, metalness: 0.05 })
            );
            hatBody.position.set(0, 2.04, 0);
            headGroup.add(hatBody);

            // 금색 띠 + 배지 공통 머티리얼
            const goldMat = mkMat(C.gold, {
                roughness: 0.25, metalness: 0.9,
                emissive: 0x5a3a00, emissiveIntensity: 0.2
            });

            // 모자 금색 띠
            const goldBand = new THREE.Mesh(
                new THREE.CylinderGeometry(0.335, 0.335, 0.04, 32),
                goldMat
            );
            goldBand.position.set(0, 1.95, 0);
            headGroup.add(goldBand);

            // 모자 배지 (전면)
            const hatBadge = new THREE.Mesh(
                new THREE.CylinderGeometry(0.07, 0.07, 0.02, 16),
                goldMat
            );
            hatBadge.rotation.x = Math.PI / 2;
            hatBadge.position.set(0, 2.12, 0.30);
            headGroup.add(hatBadge);

            this.add(headGroup);
        }

        // ──────────────────────────────────────
        //  [몸통 그룹 - bodyGroup]
        // ──────────────────────────────────────
        _buildBody() {
            const bodyGroup = new THREE.Group();
            this.bodyGroup = bodyGroup;
            const C = this._colors;

            // 몸통
            const torso = new THREE.Mesh(
                new THREE.BoxGeometry(0.70, 0.65, 0.38),
                mkMat(C.uniform, { roughness: 0.55, metalness: 0.05 })
            );
            torso.position.set(0, 1.05, 0);
            bodyGroup.add(torso);
            this.torso = torso;

            // 넥타이
            const tie = new THREE.Mesh(
                new THREE.BoxGeometry(0.11, 0.28, 0.05),
                mkMat(0x0d1b3e, { roughness: 0.4 })
            );
            tie.position.set(0, 1.08, 0.20);
            bodyGroup.add(tie);

            // 가슴 배지
            const chestBadge = new THREE.Mesh(
                new THREE.CylinderGeometry(0.07, 0.07, 0.03, 16),
                mkMat(C.gold, {
                    roughness: 0.25, metalness: 0.9,
                    emissive: 0x5a3a00, emissiveIntensity: 0.2
                })
            );
            chestBadge.rotation.x = Math.PI / 2;
            chestBadge.position.set(-0.18, 1.18, 0.20);
            bodyGroup.add(chestBadge);

            this.add(bodyGroup);
        }

        // ──────────────────────────────────────
        //  [팔 그룹 - leftArm, rightArm]
        //  피벗: 어깨 (위쪽 끝)
        // ──────────────────────────────────────
        _buildArms() {
            const C = this._colors;
            const sleeveMat = mkMat(C.uniform, { roughness: 0.55, metalness: 0.05 });
            const skinMat   = mkMat(C.skin);

            const mkArm = (side) => {
                // 그룹: 어깨 피벗
                const arm = new THREE.Group();
                arm.position.set(side * 0.44, 1.30, 0);
                arm.rotation.z = side * 0.15;  // 자연스럽게 바깥쪽 살짝 벌어짐

                // 팔(소매 — 위에서 아래로 내려가는 원통)
                const sleeve = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.10, 0.10, 0.50, 16),
                    sleeveMat
                );
                sleeve.position.set(0, -0.25, 0);
                arm.add(sleeve);

                // 손 (어깨 그룹 안 — 함께 흔들림)
                const hand = new THREE.Mesh(new THREE.SphereGeometry(0.09, 16, 16), skinMat);
                hand.position.set(0, -0.52, 0);
                arm.add(hand);

                return { arm, hand };
            };

            const L = mkArm(-1);
            const R = mkArm(1);
            this.add(L.arm); this.add(R.arm);
            this.leftArm   = L.arm;   this.leftHand   = L.hand;
            this.rightArm  = R.arm;   this.rightHand  = R.hand;
            this._leftArmRestZ  =  0.15;
            this._rightArmRestZ = -0.15;
        }

        // ──────────────────────────────────────
        //  [다리 그룹 - leftLeg, rightLeg]
        //  피벗: 엉덩이 (위쪽 끝)
        // ──────────────────────────────────────
        _buildLegs() {
            const C = this._colors;
            const pantsMat = mkMat(C.uniform, { roughness: 0.55 });
            const shoeMat  = mkMat(C.shoe, { roughness: 0.35, metalness: 0.2 });

            const mkLeg = (side) => {
                // 다리 원통: 위치 y 0.50, 높이 0.52 → 상단 y=0.76 (엉덩이 피벗)
                const leg = new THREE.Group();
                leg.position.set(side * 0.19, 0.76, 0);

                const cyl = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.13, 0.13, 0.52, 16),
                    pantsMat
                );
                cyl.position.set(0, -0.26, 0);
                leg.add(cyl);

                // 신발: 발 위치 y 0.20 (지면 위 살짝) → 그룹 기준 y=-0.56, z 약간 앞
                const foot = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.10, 0.28), shoeMat);
                foot.position.set(0, -0.56, 0.04);
                leg.add(foot);

                return { leg, foot };
            };

            const L = mkLeg(-1);
            const R = mkLeg(1);
            this.add(L.leg); this.add(R.leg);
            this.leftLeg  = L.leg;  this.leftFoot  = L.foot;
            this.rightLeg = R.leg;  this.rightFoot = R.foot;
        }

        // ──────────────────────────────────────
        //  상태 전환 (부드러운 amp/speed 보간)
        // ──────────────────────────────────────
        setState(name) {
            if (name === this._state) return;
            this._state = name;
            if (name === 'idle')      { this._targetAmp = 0;    this._targetSpeed = 1.6;  }
            else if (name === 'walk') { this._targetAmp = 0.45; this._targetSpeed = 7.0;  }
            else if (name === 'run')  { this._targetAmp = 0.70; this._targetSpeed = 11.0; }
        }

        update(dt) {
            // amp/speed 부드러운 보간 (대략 0.2초 fade)
            this._amp += (this._targetAmp - this._amp) * Math.min(1, 5 * dt);
            this._phase += dt * this._targetSpeed;

            const swing = Math.sin(this._phase) * this._amp;

            // 팔: 좌우 반대로 (어깨 기준 X축 회전)
            this.leftArm.rotation.x  = -swing;
            this.rightArm.rotation.x =  swing;
            // 어깨 자연 벌림 유지
            this.leftArm.rotation.z  = this._leftArmRestZ;
            this.rightArm.rotation.z = this._rightArmRestZ;

            // 다리: 팔과 반대 위상 (엉덩이 기준 X축 회전)
            this.leftLeg.rotation.x  =  swing;
            this.rightLeg.rotation.x = -swing;

            // 상하 바운스 — idle은 호흡, walk/run은 발걸음 박자
            if (this._state === 'idle') {
                const bob = Math.sin(this._phase) * 0.02;
                this.headGroup.position.y = bob;
                this.bodyGroup.position.y = bob * 0.5;
            } else {
                const bob = Math.abs(Math.sin(this._phase)) * (this._state === 'run' ? 0.07 : 0.035);
                this.headGroup.position.y = bob;
                this.bodyGroup.position.y = bob * 0.6;
            }
        }

        setPosition(x, y, z) { this.position.set(x, y, z); }
        setRotation(yRad)    { this.rotation.y = yRad; }

        dispose() {
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
    window.ChibiInstance = ChibiInstance;
})();
