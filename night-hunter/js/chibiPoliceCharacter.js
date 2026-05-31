// chibiPoliceCharacter.js
// 첨부 이미지 참고 — 치비/anime 피규어 스타일 여자 경찰
// 큰 머리 + 큰 눈 + 슬림한 몸 + 미니스커트 + 부츠 + 경찰 캡

(function () {
    'use strict';
    if (typeof THREE === 'undefined') {
        console.error('chibiPoliceCharacter.js: THREE required.');
        return;
    }

    class ChibiPoliceCharacter extends THREE.Group {
        constructor(config = {}) {
            super();
            this.config = Object.assign({
                skinColor:    0xfae0c2,
                shirtColor:   0x7a90b0,
                skirtColor:   0x2a3a58,
                bootColor:    0x1a1a1a,
                beltColor:    0x0a0a0a,
                hairColor:    0x2a1808,
                eyeColor:     0x3a2410,
                capColor:     0x1a2a4a,
                pupilColor:   0x0a0500,
                lipColor:     0xd97560,
                hairStyle:    'ponytail',
                scale: 1.0
            }, config);

            this.parts = {};
            this.bones = {};
            this.accessories = [];

            this._buildMaterials();
            this._buildSkeleton();
            this._buildBody();
            this._buildHead();
            this._buildHair();
            this._buildCap();
            this._buildBelt();
            this._setDefaultPose();

            if (this.config.scale !== 1.0) this.scale.setScalar(this.config.scale);
        }

        _buildMaterials() {
            const c = this.config;
            this.mats = {
                skin:     new THREE.MeshStandardMaterial({ color: c.skinColor, roughness: 0.50, metalness: 0.0 }),
                skinDark: new THREE.MeshStandardMaterial({ color: 0xe8b890, roughness: 0.55, metalness: 0.0 }),
                shirt:    new THREE.MeshStandardMaterial({ color: c.shirtColor, roughness: 0.45, metalness: 0.05 }),
                skirt:    new THREE.MeshStandardMaterial({ color: c.skirtColor, roughness: 0.50, metalness: 0.05 }),
                boot:     new THREE.MeshStandardMaterial({ color: c.bootColor, roughness: 0.40, metalness: 0.25 }),
                belt:     new THREE.MeshStandardMaterial({ color: c.beltColor, roughness: 0.50, metalness: 0.30 }),
                hair:     new THREE.MeshStandardMaterial({ color: c.hairColor, roughness: 0.42, metalness: 0.05 }),
                tie:      new THREE.MeshStandardMaterial({ color: 0x0a1530, roughness: 0.35, metalness: 0.10 }),
                cap:      new THREE.MeshStandardMaterial({ color: c.capColor, roughness: 0.38, metalness: 0.10 }),
                capVisor: new THREE.MeshStandardMaterial({ color: 0x000510, roughness: 0.28, metalness: 0.25 }),
                gold: new THREE.MeshStandardMaterial({
                    color: 0xdaa520, roughness: 0.20, metalness: 0.90,
                    emissive: 0x5a3a00, emissiveIntensity: 0.18
                }),
                silver:  new THREE.MeshStandardMaterial({ color: 0xb8c0c8, roughness: 0.25, metalness: 0.85 }),
                eyeWhite:new THREE.MeshStandardMaterial({ color: 0xfffaf2, roughness: 0.18 }),
                eyeIris: new THREE.MeshStandardMaterial({ color: c.eyeColor, roughness: 0.15 }),
                eyePupil:new THREE.MeshStandardMaterial({ color: c.pupilColor, roughness: 0.15 }),
                brow:    new THREE.MeshStandardMaterial({ color: 0x1a0e05, roughness: 0.55 }),
                lip:     new THREE.MeshStandardMaterial({ color: c.lipColor, roughness: 0.40 }),
                white:   new THREE.MeshStandardMaterial({ color: 0xf5f5f0, roughness: 0.45 })
            };
        }

        _buildSkeleton() {
            // 치비 비율 — 약 5.5~6 헤드 키, 머리 크게
            const P = this.proportions = {
                headW:  0.34,           // 머리 너비 (크게)
                headH:  0.36,           // 머리 높이 (살짝 세로)
                neckH:  0.04,
                neckW:  0.09,
                torsoH: 0.36,           // 짧은 상체
                torsoW: 0.30,
                waistW: 0.26,
                hipW:   0.30,
                skirtH: 0.18,           // 미니스커트
                upperLegH: 0.26,        // 짧게
                lowerLegH: 0.24,
                bootH:  0.14,
                legR:   0.058,
                upperArmH: 0.20,        // 매우 짧게 (소매)
                lowerArmH: 0.20,
                armR:   0.05,
                shoulderOffsetX: 0.15
            };

            // 본
            this.bones.root = new THREE.Group();
            this.bones.hip = new THREE.Group();
            this.bones.torso = new THREE.Group();
            this.bones.neck = new THREE.Group();
            this.bones.leftShoulder = new THREE.Group();
            this.bones.leftElbow = new THREE.Group();
            this.bones.rightShoulder = new THREE.Group();
            this.bones.rightElbow = new THREE.Group();
            this.bones.leftHip = new THREE.Group();
            this.bones.leftKnee = new THREE.Group();
            this.bones.rightHip = new THREE.Group();
            this.bones.rightKnee = new THREE.Group();

            this.bones.root.add(this.bones.hip);
            this.bones.hip.add(this.bones.torso);
            this.bones.torso.add(this.bones.neck);
            this.bones.torso.add(this.bones.leftShoulder);
            this.bones.leftShoulder.add(this.bones.leftElbow);
            this.bones.torso.add(this.bones.rightShoulder);
            this.bones.rightShoulder.add(this.bones.rightElbow);
            this.bones.hip.add(this.bones.leftHip);
            this.bones.leftHip.add(this.bones.leftKnee);
            this.bones.hip.add(this.bones.rightHip);
            this.bones.rightHip.add(this.bones.rightKnee);

            const yHip = P.bootH + P.lowerLegH + P.upperLegH; // 0.14+0.24+0.26 = 0.64
            this.bones.root.position.set(0, 0, 0);
            this.bones.hip.position.set(0, yHip, 0);
            this.bones.torso.position.set(0, 0.04, 0);
            this.bones.neck.position.set(0, P.torsoH, 0);

            this.bones.leftShoulder.position.set(-P.shoulderOffsetX, P.torsoH - 0.03, 0);
            this.bones.rightShoulder.position.set( P.shoulderOffsetX, P.torsoH - 0.03, 0);
            this.bones.leftElbow.position.set(0, -P.upperArmH, 0);
            this.bones.rightElbow.position.set(0, -P.upperArmH, 0);

            this.bones.leftHip.position.set(-0.07, -0.02, 0);
            this.bones.rightHip.position.set( 0.07, -0.02, 0);
            this.bones.leftKnee.position.set(0, -P.upperLegH, 0);
            this.bones.rightKnee.position.set(0, -P.upperLegH, 0);

            this.add(this.bones.root);
        }

        _addPart(boneName, mesh) {
            this.bones[boneName].add(mesh);
            mesh.castShadow = true;
            mesh.receiveShadow = true;
            return mesh;
        }

        _buildBody() {
            const P = this.proportions;
            const M = this.mats;

            // === 상체 (셔츠) — 어깨가 넓고 허리가 잘록한 LatheGeometry ===
            const torsoPts = [
                new THREE.Vector2(P.waistW * 0.5, 0.0),
                new THREE.Vector2(P.waistW * 0.5, P.torsoH * 0.1),
                new THREE.Vector2(P.waistW * 0.5 - 0.005, P.torsoH * 0.35),  // 잘록한 허리
                new THREE.Vector2(P.torsoW * 0.5 - 0.005, P.torsoH * 0.55),  // 가슴/흉부
                new THREE.Vector2(P.torsoW * 0.5, P.torsoH * 0.78),
                new THREE.Vector2(P.torsoW * 0.5 - 0.02, P.torsoH * 0.95),   // 어깨로 좁아짐
                new THREE.Vector2(P.neckW * 0.5 + 0.02, P.torsoH)
            ];
            const torsoGeom = new THREE.LatheGeometry(torsoPts, 24);
            const torso = new THREE.Mesh(torsoGeom, M.shirt);
            this._addPart('torso', torso);

            // 어깨 캡 (짧은 소매)
            for (const side of [-1, 1]) {
                const cap = new THREE.Mesh(
                    new THREE.SphereGeometry(P.armR + 0.022, 16, 14, 0, Math.PI * 2, 0, Math.PI * 0.5),
                    M.shirt
                );
                cap.rotation.x = Math.PI;
                this.bones[side === -1 ? 'leftShoulder' : 'rightShoulder'].add(cap);
                cap.castShadow = true;
            }

            // === 셔츠 칼라 (앞쪽 V형) ===
            const collarShape = new THREE.Shape();
            collarShape.moveTo(-0.07, 0.04);
            collarShape.lineTo(0.07, 0.04);
            collarShape.lineTo(0.04, -0.025);
            collarShape.lineTo(0.0, 0.0);
            collarShape.lineTo(-0.04, -0.025);
            collarShape.closePath();
            const collarGeom = new THREE.ExtrudeGeometry(collarShape, { depth: 0.01, bevelEnabled: false });
            const collar = new THREE.Mesh(collarGeom, M.white);
            collar.position.set(0, P.torsoH - 0.02, P.torsoW * 0.42);
            this._addPart('torso', collar);

            // === 넥타이 ===
            const tieKnot = new THREE.Mesh(
                new THREE.BoxGeometry(0.035, 0.03, 0.025),
                M.tie
            );
            tieKnot.position.set(0, P.torsoH - 0.04, P.torsoW * 0.46);
            this._addPart('torso', tieKnot);
            // 본체 (사다리꼴)
            const tieShape = new THREE.Shape();
            tieShape.moveTo(-0.020, 0);
            tieShape.lineTo(0.020, 0);
            tieShape.lineTo(0.030, -0.16);
            tieShape.lineTo(0.0, -0.18);
            tieShape.lineTo(-0.030, -0.16);
            tieShape.closePath();
            const tieGeom = new THREE.ExtrudeGeometry(tieShape, { depth: 0.012, bevelEnabled: false });
            const tieBody = new THREE.Mesh(tieGeom, M.tie);
            tieBody.position.set(0, P.torsoH - 0.06, P.torsoW * 0.45);
            this._addPart('torso', tieBody);

            // === 가슴 배지 (좌측) — 오벌 + 별 ===
            const badge = new THREE.Mesh(
                new THREE.CylinderGeometry(0.04, 0.04, 0.012, 16),
                M.gold
            );
            badge.rotation.x = Math.PI / 2;
            badge.scale.set(1.0, 1.0, 1.2);
            badge.position.set(-P.torsoW * 0.32, P.torsoH * 0.62, P.torsoW * 0.46);
            this._addPart('torso', badge);
            const starShape = this._makeStar(0.022, 0.011, 5);
            const star = new THREE.Mesh(
                new THREE.ExtrudeGeometry(starShape, {
                    depth: 0.008, bevelEnabled: true, bevelSize: 0.002, bevelThickness: 0.002, bevelSegments: 2
                }), M.gold
            );
            star.position.set(-P.torsoW * 0.32, P.torsoH * 0.62, P.torsoW * 0.46 + 0.012);
            this._addPart('torso', star);
            this.accessories.push(badge, star);

            // === 미니 스커트 (A-라인) ===
            const skirtTopR = P.waistW * 0.5 + 0.005;
            const skirtBotR = P.hipW * 0.65;
            const skirtPts = [
                new THREE.Vector2(skirtTopR, 0),
                new THREE.Vector2(skirtTopR + 0.005, -0.03),
                new THREE.Vector2(skirtBotR * 0.7, -P.skirtH * 0.7),
                new THREE.Vector2(skirtBotR, -P.skirtH)
            ];
            const skirt = new THREE.Mesh(new THREE.LatheGeometry(skirtPts, 22), M.skirt);
            skirt.position.set(0, 0.03, 0);
            this._addPart('hip', skirt);

            // === 팔 (짧은 소매 끝 → 맨팔) ===
            const buildArm = (side) => {
                const mid = side === -1 ? 'leftShoulder' : 'rightShoulder';
                const low = side === -1 ? 'leftElbow' : 'rightElbow';
                // 상박 (피부, 짧음)
                const upper = new THREE.Mesh(
                    new THREE.CylinderGeometry(P.armR, P.armR * 0.92, P.upperArmH, 14),
                    M.skin
                );
                upper.position.set(0, -P.upperArmH * 0.5, 0);
                this._addPart(mid, upper);
                // 하박 (피부)
                const lower = new THREE.Mesh(
                    new THREE.CylinderGeometry(P.armR * 0.88, P.armR * 0.80, P.lowerArmH, 14),
                    M.skin
                );
                lower.position.set(0, -P.lowerArmH * 0.5, 0);
                this._addPart(low, lower);
                // 손 (작은 둥근 박스)
                const hand = new THREE.Mesh(
                    new THREE.SphereGeometry(P.armR * 1.05, 12, 10),
                    M.skin
                );
                hand.position.set(0, -P.lowerArmH - 0.015, 0);
                hand.scale.set(1.0, 0.85, 0.7);
                this._addPart(low, hand);
            };
            buildArm(-1); buildArm(1);

            // === 다리 (맨다리) + 부츠 ===
            const buildLeg = (side) => {
                const mid = side === -1 ? 'leftHip' : 'rightHip';
                const low = side === -1 ? 'leftKnee' : 'rightKnee';
                // 상다리
                const upper = new THREE.Mesh(
                    new THREE.CylinderGeometry(P.legR + 0.005, P.legR, P.upperLegH, 14),
                    M.skin
                );
                upper.position.set(0, -P.upperLegH * 0.5, 0);
                this._addPart(mid, upper);
                // 하다리 (살짝 가늘어짐)
                const lower = new THREE.Mesh(
                    new THREE.CylinderGeometry(P.legR * 0.85, P.legR * 0.70, P.lowerLegH, 14),
                    M.skin
                );
                lower.position.set(0, -P.lowerLegH * 0.5, 0);
                this._addPart(low, lower);
                // === 부츠 (calf-high 컴뱃 부츠) ===
                const bootShaft = new THREE.Mesh(
                    new THREE.CylinderGeometry(P.legR * 0.90, P.legR * 0.95, P.bootH * 0.8, 14),
                    M.boot
                );
                bootShaft.position.set(0, -P.lowerLegH - P.bootH * 0.4, 0);
                this._addPart(low, bootShaft);
                // 부츠 발 부분
                const bootFoot = new THREE.Mesh(
                    new THREE.BoxGeometry(P.legR * 2.0, P.bootH * 0.55, P.legR * 3.4),
                    M.boot
                );
                bootFoot.position.set(0, -P.lowerLegH - P.bootH * 0.85, P.legR * 0.7);
                this._addPart(low, bootFoot);
                // 부츠 앞코 (둥글게)
                const bootToe = new THREE.Mesh(
                    new THREE.SphereGeometry(P.legR * 0.95, 10, 8),
                    M.boot
                );
                bootToe.scale.set(1.0, 0.4, 1.1);
                bootToe.position.set(0, -P.lowerLegH - P.bootH * 0.95, P.legR * 2.2);
                this._addPart(low, bootToe);
            };
            buildLeg(-1); buildLeg(1);
        }

        _buildHead() {
            const P = this.proportions;
            const M = this.mats;

            // 목
            const neck = new THREE.Mesh(
                new THREE.CylinderGeometry(P.neckW * 0.5, P.neckW * 0.42, P.neckH, 12),
                M.skin
            );
            neck.position.set(0, P.neckH * 0.5, 0);
            this._addPart('neck', neck);

            // 머리 (살짝 세로로 긴 타원, 더 둥근 anime 두상)
            const head = new THREE.Mesh(
                new THREE.SphereGeometry(P.headW * 0.5, 24, 20),
                M.skin
            );
            head.scale.set(1.0, (P.headH / P.headW) * 1.0, 0.95);
            head.position.set(0, P.neckH + P.headH * 0.5, 0);
            this._addPart('neck', head);

            // === 큰 anime 눈 (위치는 머리 중심 살짝 아래) ===
            const faceCY = P.neckH + P.headH * 0.45;     // 얼굴 중심 (살짝 아래)
            const faceZ = P.headW * 0.475;                // 얼굴 표면 (정면)
            const eyeX = 0.062;
            const eyeY = faceCY;

            // 눈 흰자 — 큰 가로로 긴 타원
            for (const x of [-eyeX, eyeX]) {
                const w = new THREE.Mesh(new THREE.SphereGeometry(0.045, 18, 14), M.eyeWhite);
                w.position.set(x, eyeY, faceZ + 0.001);
                w.scale.set(1.0, 0.95, 0.45);
                this._addPart('neck', w);
            }
            // 홍채 (큰 갈색/푸른색)
            for (const x of [-eyeX, eyeX]) {
                const ir = new THREE.Mesh(new THREE.SphereGeometry(0.028, 16, 12), M.eyeIris);
                ir.position.set(x, eyeY - 0.005, faceZ + 0.013);
                ir.scale.set(1.0, 1.0, 0.55);
                this._addPart('neck', ir);
            }
            // 동공
            for (const x of [-eyeX, eyeX]) {
                const p = new THREE.Mesh(new THREE.SphereGeometry(0.013, 12, 10), M.eyePupil);
                p.position.set(x, eyeY - 0.005, faceZ + 0.021);
                this._addPart('neck', p);
            }
            // 큰 하이라이트
            const hiMat = new THREE.MeshStandardMaterial({
                color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.6
            });
            for (const x of [-eyeX, eyeX]) {
                const h = new THREE.Mesh(new THREE.SphereGeometry(0.008, 8, 8), hiMat);
                h.position.set(x - 0.008, eyeY + 0.012, faceZ + 0.025);
                this._addPart('neck', h);
            }
            // 윗눈썹 라인 (눈 위쪽 어두운 라인) — anime의 두꺼운 눈매
            const lashMat = new THREE.MeshStandardMaterial({ color: 0x0a0500, roughness: 0.5 });
            for (const x of [-eyeX, eyeX]) {
                const lash = new THREE.Mesh(new THREE.TorusGeometry(0.038, 0.005, 6, 14, Math.PI), lashMat);
                lash.position.set(x, eyeY + 0.018, faceZ + 0.003);
                lash.rotation.z = Math.PI;
                lash.scale.set(1.0, 0.7, 1.0);
                this._addPart('neck', lash);
            }

            // 눈썹 (anime — 작은 호)
            const browGeom = new THREE.BoxGeometry(0.04, 0.008, 0.012);
            for (const [x, rot] of [[-eyeX, -0.15], [eyeX, 0.15]]) {
                const b = new THREE.Mesh(browGeom, M.brow);
                b.position.set(x, eyeY + 0.052, faceZ - 0.002);
                b.rotation.z = rot;
                this._addPart('neck', b);
            }

            // 작은 코 (anime는 거의 안 보임 — 작은 점)
            const nose = new THREE.Mesh(
                new THREE.SphereGeometry(0.006, 8, 6), M.skinDark
            );
            nose.position.set(0, eyeY - 0.04, faceZ + 0.011);
            this._addPart('neck', nose);

            // 작은 입 (살짝 미소)
            const mouth = new THREE.Mesh(
                new THREE.TorusGeometry(0.014, 0.0035, 6, 10, Math.PI),
                M.lip
            );
            mouth.position.set(0, eyeY - 0.075, faceZ + 0.005);
            mouth.rotation.z = Math.PI;
            mouth.rotation.x = -Math.PI * 0.1;
            this._addPart('neck', mouth);

            // 볼터치
            const blushMat = new THREE.MeshStandardMaterial({
                color: 0xff9090, roughness: 0.6, transparent: true, opacity: 0.5
            });
            for (const x of [-0.085, 0.085]) {
                const bl = new THREE.Mesh(new THREE.SphereGeometry(0.025, 10, 8), blushMat);
                bl.position.set(x, eyeY - 0.035, faceZ - 0.002);
                bl.scale.set(1.0, 0.5, 0.18);
                this._addPart('neck', bl);
            }
        }

        _makeStar(outerR, innerR, points) {
            const shape = new THREE.Shape();
            for (let i = 0; i < points * 2; i++) {
                const r = (i % 2 === 0) ? outerR : innerR;
                const a = (i / (points * 2)) * Math.PI * 2 - Math.PI / 2;
                if (i === 0) shape.moveTo(Math.cos(a) * r, Math.sin(a) * r);
                else shape.lineTo(Math.cos(a) * r, Math.sin(a) * r);
            }
            shape.closePath();
            return shape;
        }

        // === 핵심 — 머리카락은 얼굴을 가리지 않게 ===
        _buildHair() {
            const P = this.proportions;
            const M = this.mats;
            const headY = P.neckH + P.headH * 0.5;

            // 1) 정수리 캡 (위쪽만 덮는 반구) — 얼굴 가리지 않음
            const topGeom = new THREE.SphereGeometry(
                P.headW * 0.52, 24, 16,
                0, Math.PI * 2,
                0, Math.PI * 0.50          // 위쪽 절반만
            );
            const top = new THREE.Mesh(topGeom, M.hair);
            top.scale.set(1.05, (P.headH / P.headW) * 1.0, 1.05);
            top.position.set(0, headY + P.headH * 0.02, 0);
            this._addPart('neck', top);

            // 2) 뒤통수 (뒷부분 절반 — 정면은 비움)
            const backGeom = new THREE.SphereGeometry(
                P.headW * 0.52, 24, 16,
                Math.PI * 0.30, Math.PI * 1.40,  // 뒤쪽 240도만 (정면 120도 비움)
                0, Math.PI * 0.80
            );
            const back = new THREE.Mesh(backGeom, M.hair);
            back.scale.set(1.04, (P.headH / P.headW) * 1.0, 1.05);
            back.position.set(0, headY + P.headH * 0.02, 0);
            this._addPart('neck', back);

            // 3) 앞머리 (이마 가리는 짧은 컬) — 얼굴 위에서 시작
            const bangGeom = new THREE.SphereGeometry(
                P.headW * 0.42, 16, 8,
                0, Math.PI,
                0, Math.PI * 0.30
            );
            const bang = new THREE.Mesh(bangGeom, M.hair);
            bang.position.set(0, headY + P.headH * 0.30, P.headW * 0.20);
            bang.scale.set(1.0, 0.7, 0.55);
            this._addPart('neck', bang);

            // 4) 옆머리 짧게 — 귀 옆
            for (const side of [-1, 1]) {
                const sideHair = new THREE.Mesh(
                    new THREE.BoxGeometry(0.035, P.headH * 0.4, 0.05),
                    M.hair
                );
                sideHair.position.set(side * (P.headW * 0.48), headY - P.headH * 0.05, -0.01);
                this._addPart('neck', sideHair);
            }

            if (this.config.hairStyle === 'ponytail') {
                this._buildPonytail(headY);
            } else if (this.config.hairStyle === 'braids') {
                this._buildBraids(headY);
            }
        }

        _buildPonytail(headY) {
            const P = this.proportions;
            const M = this.mats;
            // 묶음 위치 (뒤통수 위)
            const baseY = headY + P.headH * 0.18;
            const baseZ = -P.headW * 0.48;

            // 검은 머리끈
            const tie = new THREE.Mesh(
                new THREE.TorusGeometry(0.028, 0.008, 8, 14),
                new THREE.MeshStandardMaterial({ color: 0x0a0500, roughness: 0.55 })
            );
            tie.position.set(0, baseY, baseZ + 0.005);
            tie.rotation.y = Math.PI / 2;
            this._addPart('neck', tie);

            // 포니테일 그룹 (뒤로 흘러 살짝 옆으로)
            const tailGrp = new THREE.Group();
            // 굵은 윗부분
            const tail1 = new THREE.Mesh(
                new THREE.CylinderGeometry(0.05, 0.04, 0.18, 14),
                M.hair
            );
            tail1.position.set(0, -0.09, 0);
            tailGrp.add(tail1);
            // 가운데
            const tail2 = new THREE.Mesh(
                new THREE.CylinderGeometry(0.04, 0.03, 0.16, 14),
                M.hair
            );
            tail2.position.set(0.01, -0.25, 0);
            tail2.rotation.z = 0.06;
            tailGrp.add(tail2);
            // 끝부분 (가늘게)
            const tail3 = new THREE.Mesh(
                new THREE.CylinderGeometry(0.030, 0.012, 0.12, 12),
                M.hair
            );
            tail3.position.set(0.025, -0.39, 0);
            tail3.rotation.z = 0.12;
            tailGrp.add(tail3);
            // 끝 둥근 마무리
            const tailEnd = new THREE.Mesh(
                new THREE.SphereGeometry(0.018, 10, 8), M.hair
            );
            tailEnd.position.set(0.040, -0.45, 0);
            tailGrp.add(tailEnd);

            tailGrp.position.set(0, baseY - 0.01, baseZ);
            tailGrp.rotation.x = -0.55;  // 뒤로 쳐짐
            this._addPart('neck', tailGrp);
            this.accessories.push(tailGrp);
        }

        _buildBraids(headY) {
            const P = this.proportions;
            const M = this.mats;
            for (const side of [-1, 1]) {
                const grp = new THREE.Group();
                for (let i = 0; i < 6; i++) {
                    const seg = new THREE.Mesh(
                        new THREE.SphereGeometry(0.045 - i * 0.005, 12, 10), M.hair
                    );
                    seg.position.set(0, -i * 0.07, 0);
                    grp.add(seg);
                }
                grp.position.set(side * (P.headW * 0.5 + 0.015), headY - 0.02, -0.015);
                this._addPart('neck', grp);
                this.accessories.push(grp);
            }
        }

        _buildCap() {
            const P = this.proportions;
            const M = this.mats;
            const headTopY = P.neckH + P.headH * 0.92;

            // === Cap 크라운 (둥근 모자 형태) — LatheGeometry로 옆 보면 부풀어 오른 형태 ===
            const crownPts = [
                new THREE.Vector2(0.0, 0.0),
                new THREE.Vector2(P.headW * 0.53, 0.0),
                new THREE.Vector2(P.headW * 0.54, 0.025),
                new THREE.Vector2(P.headW * 0.50, 0.07),
                new THREE.Vector2(P.headW * 0.38, 0.10),
                new THREE.Vector2(P.headW * 0.18, 0.115),
                new THREE.Vector2(0.0, 0.117)
            ];
            const crown = new THREE.Mesh(new THREE.LatheGeometry(crownPts, 24), M.cap);
            crown.position.set(0, headTopY, 0);
            this._addPart('neck', crown);

            // 모자 가운데 밴드 (얇은 검은 줄)
            const band = new THREE.Mesh(
                new THREE.TorusGeometry(P.headW * 0.53, 0.006, 8, 24),
                new THREE.MeshStandardMaterial({ color: 0x000510, roughness: 0.4 })
            );
            band.position.set(0, headTopY + 0.008, 0);
            band.rotation.x = Math.PI / 2;
            this._addPart('neck', band);

            // 비저 (앞으로 짧게 뻗는 챙)
            const visor = new THREE.Mesh(
                new THREE.CylinderGeometry(
                    P.headW * 0.62, P.headW * 0.66, 0.010, 24, 1, false,
                    -Math.PI * 0.30, Math.PI * 0.60
                ),
                M.capVisor
            );
            visor.position.set(0, headTopY + 0.003, 0.01);
            this._addPart('neck', visor);

            // 정면 금색 배지 (오벌 + 별)
            const ovalBadge = new THREE.Mesh(
                new THREE.CylinderGeometry(0.028, 0.028, 0.010, 16), M.gold
            );
            ovalBadge.rotation.x = Math.PI / 2;
            ovalBadge.scale.set(1.0, 1.0, 1.4);
            ovalBadge.position.set(0, headTopY + 0.05, P.headW * 0.50);
            this._addPart('neck', ovalBadge);
            const star = new THREE.Mesh(
                new THREE.ExtrudeGeometry(this._makeStar(0.020, 0.010, 5), {
                    depth: 0.008, bevelEnabled: true, bevelSize: 0.002,
                    bevelThickness: 0.002, bevelSegments: 2
                }), M.gold
            );
            star.position.set(0, headTopY + 0.05, P.headW * 0.50 + 0.008);
            this._addPart('neck', star);
            this.accessories.push(crown, band, visor, ovalBadge, star);
        }

        _buildBelt() {
            const P = this.proportions;
            const M = this.mats;
            // 벨트 — 골반에 두꺼운 검은 띠
            const belt = new THREE.Mesh(
                new THREE.CylinderGeometry(P.waistW * 0.5 + 0.005, P.waistW * 0.5 + 0.005, 0.04, 18),
                M.belt
            );
            belt.position.set(0, 0.025, 0);
            this._addPart('hip', belt);

            // 좌측 권총집
            const holster = new THREE.Mesh(
                new THREE.BoxGeometry(0.045, 0.08, 0.025), M.belt
            );
            holster.position.set(-P.waistW * 0.5 - 0.015, -0.025, 0.015);
            this._addPart('hip', holster);
            const grip = new THREE.Mesh(
                new THREE.BoxGeometry(0.022, 0.028, 0.012),
                new THREE.MeshStandardMaterial({ color: 0x2a2a2a, roughness: 0.45 })
            );
            grip.position.set(-P.waistW * 0.5 - 0.015, 0.022, 0.015);
            this._addPart('hip', grip);

            // 우측 파우치 2개
            for (let i = 0; i < 2; i++) {
                const pouch = new THREE.Mesh(
                    new THREE.BoxGeometry(0.032, 0.04, 0.022), M.belt
                );
                pouch.position.set(P.waistW * 0.32 + i * 0.04, 0.005, 0.025);
                this._addPart('hip', pouch);
            }

            // 벨트 버클 (앞 가운데)
            const buckle = new THREE.Mesh(
                new THREE.BoxGeometry(0.038, 0.022, 0.012), M.silver
            );
            buckle.position.set(0, 0.025, P.waistW * 0.5 - 0.001);
            this._addPart('hip', buckle);
        }

        _setDefaultPose() {
            for (const n of Object.keys(this.bones)) {
                this.bones[n].rotation.set(0, 0, 0);
            }
        }

        setJointRotation(name, x = 0, y = 0, z = 0) {
            const b = this.bones[name];
            if (b) b.rotation.set(x, y, z);
        }

        updateWalk(time, intensity = 1) {
            const s = Math.sin(time * 6) * 0.35 * intensity;
            this.setJointRotation('leftHip', s, 0, 0);
            this.setJointRotation('rightHip', -s, 0, 0);
            this.setJointRotation('leftKnee', Math.max(0, -s * 0.7), 0, 0);
            this.setJointRotation('rightKnee', Math.max(0, s * 0.7), 0, 0);
            this.setJointRotation('leftShoulder', -s * 0.5, 0, 0);
            this.setJointRotation('rightShoulder', s * 0.5, 0, 0);
            this.setJointRotation('leftElbow', Math.max(0, -s * 0.3) + 0.1, 0, 0);
            this.setJointRotation('rightElbow', Math.max(0, s * 0.3) + 0.1, 0, 0);
        }

        updateIdle(time) {
            const br = Math.sin(time * 1.6) * 0.015;
            this.setJointRotation('torso', br, 0, 0);
            this.setJointRotation('neck', -br * 0.4, 0, 0);
        }

        poseHandsOnHip() {
            this.setJointRotation('leftShoulder', 0, 0, 0.5);
            this.setJointRotation('leftElbow', 0.1, 0, 1.3);
            this.setJointRotation('rightShoulder', 0, 0, -0.5);
            this.setJointRotation('rightElbow', 0.1, 0, -1.3);
        }

        poseSalute(rightHand = true) {
            const sh = rightHand ? 'rightShoulder' : 'leftShoulder';
            const el = rightHand ? 'rightElbow' : 'leftElbow';
            const dir = rightHand ? -1 : 1;
            this.setJointRotation(sh, 0, 0, dir * 2.0);
            this.setJointRotation(el, 0, 0, dir * 1.6);
        }

        dispose() {
            this.traverse(obj => {
                if (obj.geometry) obj.geometry.dispose();
                if (obj.material) {
                    if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
                    else obj.material.dispose();
                }
            });
        }
    }

    class SoyunChibi extends ChibiPoliceCharacter {
        constructor(cfg = {}) {
            super(Object.assign({
                hairColor: 0x2a1808, eyeColor: 0x7a4d28, hairStyle: 'ponytail'
            }, cfg));
            this.name = 'Soyun';
        }
    }
    class HayunChibi extends ChibiPoliceCharacter {
        constructor(cfg = {}) {
            super(Object.assign({
                hairColor: 0x3a1f10, eyeColor: 0x3a82d4, hairStyle: 'ponytail'
            }, cfg));
            this.name = 'Hayun';
        }
    }

    function setupChibiLighting(scene) {
        scene.add(new THREE.AmbientLight(0xffffff, 0.95));
        scene.add(new THREE.HemisphereLight(0xfff5e8, 0xe0d0b0, 0.5));
        const key = new THREE.DirectionalLight(0xfff0e0, 1.0);
        key.position.set(2, 3, 2);
        key.castShadow = true;
        key.shadow.mapSize.width = 2048; key.shadow.mapSize.height = 2048;
        key.shadow.camera.left = -2; key.shadow.camera.right = 2;
        key.shadow.camera.top = 3; key.shadow.camera.bottom = -1;
        key.shadow.bias = -0.0003;
        scene.add(key);
        const rim = new THREE.DirectionalLight(0xffffff, 0.8);
        rim.position.set(-1.5, 2.5, -3);
        scene.add(rim);
    }

    function configureChibiRenderer(renderer) {
        renderer.outputEncoding = THREE.sRGBEncoding;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.15;
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.physicallyCorrectLights = true;
    }

    window.ChibiCharacters = {
        Base: ChibiPoliceCharacter,
        Soyun: SoyunChibi,
        Hayun: HayunChibi,
        setupLighting: setupChibiLighting,
        configureRenderer: configureChibiRenderer
    };
})();
