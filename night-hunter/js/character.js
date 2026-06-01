// character.js — Chibi 3D 여경 캐릭터 v4 (픽셀 아트 레퍼런스 기반)
// 큰 머리(r=0.5), 큰 애니 눈, 둥근 chibi 경찰 모자, 벨트 파우치, 견장

(function () {
    'use strict';
    if (typeof THREE === 'undefined') {
        console.error('[ChibiCharacter] THREE required.');
        return;
    }

    const ChibiCharacter = {
        loaded: false,
        preload() { this.loaded = true; return Promise.resolve(true); },
        create(cfg) {
            try { return new ChibiInstance(cfg || {}); }
            catch (err) { console.error('[ChibiCharacter] create failed:', err); return null; }
        }
    };

    function mat(color, opts) {
        return new THREE.MeshStandardMaterial(Object.assign({ color, roughness: 0.6 }, opts || {}));
    }

    class ChibiInstance extends THREE.Group {
        constructor(cfg) {
            super();
            this.cfg = cfg;
            const C = this._C = {
                skin:    cfg.skinColor || 0xffe0c8,
                hair:    cfg.hairColor || 0x5a3a1a,
                eye:     cfg.eyeColor  || 0x2a1408,
                lip:     cfg.lipColor  || 0xe8a090,
                brow:    cfg.browColor || 0x3b1f0a,
                uni:     cfg.coatColor || 0x1e3060,
                hat:     0x1a2a50,
                gold:    0xd4a820,
                black:   0x111111,
            };
            this._buildHead();
            this._buildBody();
            this._buildArms();
            this._buildLegs();
            this.traverse(o => { if (o.isMesh) { o.castShadow = true; } });
            this._state = 'idle';
            this._phase = 0;
            this._amp = 0;
            this._targetAmp = 0;
            this._targetSpeed = 1.5;
        }

        _buildHead() {
            const g = new THREE.Group();
            this.headGroup = g;
            const C = this._C;
            const HY = 1.90; // 머리 중심 Y

            // 뒷머리
            g.add(mesh(new THREE.SphereGeometry(0.52, 32, 32),
                mat(C.hair, { roughness: 0.6 }),
                [0, HY, -0.03]));

            // 옆머리 (귀 옆으로)
            [-1, 1].forEach(s => {
                const sh = mesh(new THREE.CylinderGeometry(0.13, 0.11, 0.48, 12),
                    mat(C.hair, { roughness: 0.6 }), [s * 0.47, HY - 0.18, 0.02]);
                g.add(sh);
            });

            // 얼굴 구
            const face = mesh(new THREE.SphereGeometry(0.50, 32, 32),
                mat(C.skin, { roughness: 0.5 }), [0, HY, 0]);
            g.add(face);
            this.face = face;

            // 앞머리 bangs
            g.add(mesh(new THREE.BoxGeometry(0.82, 0.20, 0.18),
                mat(C.hair, { roughness: 0.6 }), [0, HY + 0.38, 0.34]));

            // 볼 홍조
            const blushM = new THREE.MeshStandardMaterial({
                color: 0xff9999, transparent: true, opacity: 0.50, roughness: 0.5
            });
            [-0.32, 0.32].forEach(x => {
                const b = new THREE.Mesh(new THREE.SphereGeometry(0.13, 16, 16), blushM);
                b.scale.y = 0.45;
                b.position.set(x, HY - 0.11, 0.42);
                g.add(b);
            });

            // === 눈 (큰 애니 스타일) ===
            const eyeWM = mat(0xffffff, { roughness: 0.05 });
            const irisM = mat(C.eye,    { roughness: 0.15 });
            const pupM  = mat(0x060606, { roughness: 0.1 });
            const hlM   = new THREE.MeshStandardMaterial({
                color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 1.0
            });

            [-0.19, 0.19].forEach(x => {
                // 흰자 — 넓은 타원
                const w = new THREE.Mesh(new THREE.SphereGeometry(0.13, 20, 20), eyeWM);
                w.scale.set(1.0, 1.35, 0.65);
                w.position.set(x, HY + 0.04, 0.45);
                g.add(w);

                // 홍채 — 어두운 큰 원
                const ir = new THREE.Mesh(new THREE.SphereGeometry(0.105, 20, 20), irisM);
                ir.scale.set(0.95, 1.20, 0.55);
                ir.position.set(x, HY + 0.02, 0.48);
                g.add(ir);

                // 동공
                const pu = new THREE.Mesh(new THREE.SphereGeometry(0.052, 14, 14), pupM);
                pu.position.set(x, HY + 0.01, 0.505);
                g.add(pu);

                // 하이라이트 (큰 흰 점)
                const hl = new THREE.Mesh(new THREE.SphereGeometry(0.032, 10, 10), hlM);
                hl.position.set(x - 0.045, HY + 0.07, 0.515);
                g.add(hl);

                // 하이라이트 (작은 흰 점)
                const hl2 = new THREE.Mesh(new THREE.SphereGeometry(0.018, 8, 8), hlM);
                hl2.position.set(x + 0.04, HY - 0.03, 0.515);
                g.add(hl2);
            });

            // 눈썹
            [-0.19, 0.19].forEach((x, i) => {
                const brow = mesh(new THREE.BoxGeometry(0.14, 0.035, 0.02),
                    mat(C.brow, { roughness: 0.7 }),
                    [x, HY + 0.24, 0.43]);
                brow.rotation.z = (i === 0 ? 0.08 : -0.08);
                g.add(brow);
            });

            // 코 (작은 점)
            g.add(mesh(new THREE.SphereGeometry(0.025, 8, 8),
                mat(0xd4a070), [0, HY - 0.10, 0.50]));

            // 입 (미소 호)
            const smileM = mat(C.lip, { roughness: 0.5 });
            const smile = new THREE.Mesh(new THREE.TorusGeometry(0.065, 0.016, 8, 16, Math.PI), smileM);
            smile.rotation.x = Math.PI;
            smile.position.set(0, HY - 0.21, 0.49);
            g.add(smile);

            // === 경찰 모자 (둥근 chibi 돔) ===
            // 돔 본체
            const dome = new THREE.Mesh(
                new THREE.SphereGeometry(0.55, 32, 32, 0, Math.PI * 2, 0, Math.PI * 0.52),
                mat(C.hat, { roughness: 0.5 })
            );
            dome.position.set(0, HY + 0.22, 0);
            g.add(dome);

            // 챙 (전체 원판)
            g.add(mesh(new THREE.CylinderGeometry(0.60, 0.60, 0.045, 32),
                mat(C.black, { roughness: 0.35 }), [0, HY + 0.20, 0]));

            // 앞챙 (앞쪽으로 돌출)
            g.add(mesh(new THREE.BoxGeometry(0.82, 0.04, 0.32),
                mat(C.black, { roughness: 0.35 }), [0, HY + 0.21, 0.42]));

            // 금색 띠
            g.add(mesh(new THREE.CylinderGeometry(0.54, 0.54, 0.065, 32),
                mat(C.gold, { roughness: 0.25, metalness: 0.75 }), [0, HY + 0.22, 0]));

            // 배지
            const hatBadge = mesh(new THREE.CylinderGeometry(0.085, 0.085, 0.045, 16),
                mat(C.gold, { roughness: 0.15, metalness: 0.9, emissive: 0x5a3a00, emissiveIntensity: 0.35 }),
                [0, HY + 0.42, 0.44]);
            hatBadge.rotation.x = Math.PI / 2;
            g.add(hatBadge);

            this.add(g);
        }

        _buildBody() {
            const g = new THREE.Group();
            this.bodyGroup = g;
            const C = this._C;
            const goldM = mat(C.gold, { roughness: 0.2, metalness: 0.85 });

            // 몸통
            g.add(mesh(new THREE.BoxGeometry(0.78, 0.68, 0.44),
                mat(C.uni, { roughness: 0.6 }), [0, 1.05, 0]));

            // 칼라 (흰 셔츠)
            g.add(mesh(new THREE.BoxGeometry(0.24, 0.20, 0.09),
                mat(0xeeeeee, { roughness: 0.5 }), [0, 1.34, 0.23]));

            // 넥타이
            g.add(mesh(new THREE.BoxGeometry(0.09, 0.26, 0.045),
                mat(0x101030, { roughness: 0.4 }), [0, 1.18, 0.235]));

            // 버튼
            [1.28, 1.12, 0.96, 0.82].forEach(y =>
                g.add(mesh(new THREE.SphereGeometry(0.028, 8, 8), goldM, [0, y, 0.234])));

            // 가슴 배지
            const badge = mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.045, 16), goldM, [-0.22, 1.22, 0.23]);
            badge.rotation.x = Math.PI / 2;
            g.add(badge);

            // 어깨 견장 (좌우)
            [-0.40, 0.40].forEach(x => {
                g.add(mesh(new THREE.BoxGeometry(0.22, 0.07, 0.24), mat(C.uni, { roughness: 0.5 }), [x, 1.38, 0]));
                g.add(mesh(new THREE.BoxGeometry(0.22, 0.025, 0.24), goldM, [x, 1.40, 0]));
            });

            // 벨트
            g.add(mesh(new THREE.BoxGeometry(0.80, 0.11, 0.46),
                mat(C.black, { roughness: 0.4 }), [0, 0.77, 0]));

            // 버클
            g.add(mesh(new THREE.BoxGeometry(0.13, 0.11, 0.055), goldM, [0, 0.77, 0.245]));

            // 파우치 (좌우)
            [-0.24, 0.24].forEach(x =>
                g.add(mesh(new THREE.BoxGeometry(0.13, 0.14, 0.09),
                    mat(C.black, { roughness: 0.45 }), [x, 0.75, 0.24])));

            // 무전기 (오른쪽)
            g.add(mesh(new THREE.BoxGeometry(0.07, 0.18, 0.06),
                mat(0x222222, { roughness: 0.5 }), [0.38, 0.85, 0.19]));

            this.add(g);
        }

        _buildArms() {
            const C = this._C;
            const sleeveM = mat(C.uni, { roughness: 0.6 });
            const skinM   = mat(C.skin, { roughness: 0.5 });

            const mkArm = (side) => {
                const arm = new THREE.Group();
                arm.position.set(side * 0.47, 1.30, 0);
                arm.rotation.z = side * 0.16;

                arm.add(assign(mesh(new THREE.CylinderGeometry(0.112, 0.10, 0.46, 16), sleeveM, [0, -0.23, 0])));
                arm.add(assign(mesh(new THREE.CylinderGeometry(0.095, 0.09, 0.20, 16), sleeveM, [0, -0.56, 0])));

                const hand = mesh(new THREE.SphereGeometry(0.092, 16, 16), skinM, [0, -0.70, 0]);
                arm.add(hand);
                return { arm, hand };
            };

            const L = mkArm(-1), R = mkArm(1);
            this.add(L.arm); this.add(R.arm);
            this.leftArm = L.arm; this.rightArm = R.arm;
            this._lArmZ =  0.16;
            this._rArmZ = -0.16;
        }

        _buildLegs() {
            const C = this._C;
            const pantsM = mat(C.uni,   { roughness: 0.6 });
            const bootM  = mat(C.black, { roughness: 0.30, metalness: 0.15 });

            const mkLeg = (side) => {
                const leg = new THREE.Group();
                leg.position.set(side * 0.19, 0.74, 0);

                leg.add(mesh(new THREE.CylinderGeometry(0.145, 0.125, 0.42, 16), pantsM, [0, -0.21, 0]));
                leg.add(mesh(new THREE.CylinderGeometry(0.122, 0.112, 0.33, 16), pantsM, [0, -0.575, 0]));

                // 부츠
                const boot = mesh(new THREE.BoxGeometry(0.21, 0.155, 0.34), bootM, [0, -0.77, 0.04]);
                leg.add(boot);
                // 부츠 광택
                const sh = mesh(new THREE.SphereGeometry(0.04, 8, 8),
                    new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.08, metalness: 0.3 }),
                    [0, -0.75, 0.19]);
                leg.add(sh);
                return { leg };
            };

            const L = mkLeg(-1), R = mkLeg(1);
            this.add(L.leg); this.add(R.leg);
            this.leftLeg = L.leg; this.rightLeg = R.leg;
        }

        setState(name) {
            if (name === this._state) return;
            this._state = name;
            if      (name === 'idle') { this._targetAmp = 0;    this._targetSpeed = 1.6;  }
            else if (name === 'walk') { this._targetAmp = 0.40; this._targetSpeed = 7.0;  }
            else if (name === 'run')  { this._targetAmp = 0.65; this._targetSpeed = 11.0; }
        }

        update(dt) {
            this._amp += (this._targetAmp - this._amp) * Math.min(1, 5 * dt);
            this._phase += dt * this._targetSpeed;
            const sw = Math.sin(this._phase) * this._amp;

            this.leftArm.rotation.x  = -sw;
            this.rightArm.rotation.x =  sw;
            this.leftArm.rotation.z  = this._lArmZ;
            this.rightArm.rotation.z = this._rArmZ;
            this.leftLeg.rotation.x  =  sw;
            this.rightLeg.rotation.x = -sw;

            const bob = this._state === 'idle'
                ? Math.sin(this._phase) * 0.015
                : Math.abs(Math.sin(this._phase)) * (this._state === 'run' ? 0.06 : 0.03);
            this.headGroup.position.y = bob;
            this.bodyGroup.position.y = bob * 0.5;
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

    // 헬퍼
    function mesh(geo, mat, pos) {
        const m = new THREE.Mesh(geo, mat);
        if (pos) m.position.set(...pos);
        return m;
    }
    function assign(m) { return m; }

    window.ChibiCharacter = ChibiCharacter;
    window.ChibiInstance  = ChibiInstance;
})();
