// robloxCharacter.js
// Roblox R15-style 캐릭터 시스템 (Three.js r128+)
// - 15개 R15 관절 (Bone) + SkinnedMesh 리깅
// - Rounded Box 메쉬 분할 (머리/상체/하체/팔(상하)/다리(상하)/손/발)
// - 입체 별/배지 액세서리 + 양갈래 땋은머리 메쉬
// - 플라스틱 피규어 재질 + 림 라이트 헬퍼
//
// 사용 예:
//   const char = new RobloxCharacters.Hayun();
//   scene.add(char);
//   RobloxCharacters.setupLighting(scene);
//   RobloxCharacters.configureRenderer(renderer);
//   // 매 프레임:
//   char.updateIdle(clock.elapsedTime);
//   // 또는: char.updateWalk(clock.elapsedTime, 1);

(function () {
    'use strict';

    if (typeof THREE === 'undefined') {
        console.error('robloxCharacter.js: THREE must be loaded first.');
        return;
    }

    // ─────────────────────────────────────────────────────────────────────
    // RoundedBoxGeometry — Roblox 특유의 둥근 모서리를 가진 박스
    // BoxGeometry를 세분화한 뒤 각 정점을 "내부 박스 + 반지름 구"로 변형
    // ─────────────────────────────────────────────────────────────────────
    class RoundedBoxGeometry extends THREE.BufferGeometry {
        constructor(width = 1, height = 1, depth = 1, segments = 4, radius = 0.05) {
            super();
            segments = Math.max(1, segments | 0);
            radius = Math.min(radius, Math.min(width, Math.min(height, depth)) / 2 - 1e-4);

            const box = new THREE.BoxGeometry(
                width, height, depth, segments, segments, segments
            );

            const innerHalf = new THREE.Vector3(
                Math.max(0, width / 2 - radius),
                Math.max(0, height / 2 - radius),
                Math.max(0, depth / 2 - radius)
            );

            const pos = box.attributes.position;
            const v = new THREE.Vector3();
            const inner = new THREE.Vector3();
            const dir = new THREE.Vector3();

            for (let i = 0; i < pos.count; i++) {
                v.fromBufferAttribute(pos, i);
                inner.set(
                    Math.max(-innerHalf.x, Math.min(innerHalf.x, v.x)),
                    Math.max(-innerHalf.y, Math.min(innerHalf.y, v.y)),
                    Math.max(-innerHalf.z, Math.min(innerHalf.z, v.z))
                );
                dir.subVectors(v, inner);
                if (dir.lengthSq() > 1e-8) {
                    dir.normalize().multiplyScalar(radius);
                    v.copy(inner).add(dir);
                    pos.setXYZ(i, v.x, v.y, v.z);
                }
            }
            pos.needsUpdate = true;
            box.computeVertexNormals();

            // BoxGeometry의 attribute를 그대로 인계
            this.setAttribute('position', box.attributes.position);
            this.setAttribute('normal', box.attributes.normal);
            this.setAttribute('uv', box.attributes.uv);
            this.setIndex(box.index);
            box.dispose();
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // R15 관절 이름 (16개 본 = Root + 15개 R15 조인트)
    // ─────────────────────────────────────────────────────────────────────
    const R15_BONES = [
        'Root',          //  0 - 골반 중심 (RootBone)
        'LowerTorso',    //  1 - 골반→허리
        'UpperTorso',    //  2 - 허리→목 (Waist 조인트의 자식)
        'Neck',          //  3 - 목/머리
        'LeftShoulder',  //  4 - 좌측 어깨
        'LeftElbow',     //  5 - 좌측 팔꿈치
        'LeftWrist',     //  6 - 좌측 손목
        'RightShoulder', //  7
        'RightElbow',    //  8
        'RightWrist',    //  9
        'LeftHip',       // 10 - 좌측 고관절
        'LeftKnee',      // 11
        'LeftAnkle',     // 12
        'RightHip',      // 13
        'RightKnee',     // 14
        'RightAnkle'     // 15
    ];

    // ─────────────────────────────────────────────────────────────────────
    // RobloxR15Character (Base) — 모든 캐릭터의 공통 베이스 클래스
    // ─────────────────────────────────────────────────────────────────────
    class RobloxR15Character extends THREE.Group {
        constructor(config = {}) {
            super();
            this.config = Object.assign({
                // 신체/제복 컬러
                skinColor:    0xfae4c8,
                uniformColor: 0x1a2a4a,
                pantsColor:   0x0a1730,
                shoeColor:    0x111111,
                // 머리카락
                hairColor:    0x5a3a1c,
                hairStyle:    'long',     // 'long' | 'braids'
                // 얼굴
                eyeColor:     0x7a4d28,
                pupilColor:   0x0a0500,
                browColor:    0x3a2010,
                lipColor:     0xc97560,
                // 개인 액세서리
                accessory:    'redClip',  // 'redClip' | 'headset' | 'none'
                // 스케일 (1.0 = 약 1.78m)
                scale: 1.0
            }, config);

            this.bones = {};        // name → Bone
            this.boneArray = [];    // skeleton.bones 순서
            this.parts = {};        // 본체 SkinnedMesh 들
            this.accessories = [];  // 별/배지/땋은머리 등
            this.skinnedMeshes = [];
            this.skeleton = null;

            this._buildMaterials();
            this._buildSkeleton();
            this._buildBodyParts();
            this._buildHead();
            this._buildAccessories();
            this._setDefaultPose();

            if (this.config.scale !== 1.0) this.scale.setScalar(this.config.scale);
        }

        // === Materials ===
        // Roblox 플라스틱 피규어 느낌: roughness 0.2~0.3, 금속 배지는 metalness 0.9
        _buildMaterials() {
            const c = this.config;
            this.mats = {
                skin:    new THREE.MeshStandardMaterial({ color: c.skinColor,    roughness: 0.42, metalness: 0.00 }),
                uniform: new THREE.MeshStandardMaterial({ color: c.uniformColor, roughness: 0.28, metalness: 0.05 }),
                pants:   new THREE.MeshStandardMaterial({ color: c.pantsColor,   roughness: 0.30, metalness: 0.05 }),
                shoe:    new THREE.MeshStandardMaterial({ color: c.shoeColor,    roughness: 0.30, metalness: 0.10 }),
                hair:    new THREE.MeshStandardMaterial({ color: c.hairColor,    roughness: 0.25, metalness: 0.00 }),
                // 금속 배지 (별/오벌)
                gold: new THREE.MeshStandardMaterial({
                    color: 0xdaa520, roughness: 0.18, metalness: 0.90,
                    emissive: 0x5a3a00, emissiveIntensity: 0.12
                }),
                redClip: new THREE.MeshStandardMaterial({ color: 0xcc1818, roughness: 0.22, metalness: 0.00 }),
                tie:     new THREE.MeshStandardMaterial({ color: 0x0d1830, roughness: 0.28, metalness: 0.05 }),
                white:   new THREE.MeshStandardMaterial({ color: 0xf2f2f0, roughness: 0.40, metalness: 0.00 }),
                capDark: new THREE.MeshStandardMaterial({ color: 0x0a1530, roughness: 0.22, metalness: 0.05 }),
                capVisor:new THREE.MeshStandardMaterial({ color: 0x000510, roughness: 0.18, metalness: 0.20 }),
                // 얼굴 디테일
                eyeWhite:new THREE.MeshStandardMaterial({ color: 0xfffaf2, roughness: 0.20, metalness: 0.00 }),
                eyeIris: new THREE.MeshStandardMaterial({ color: c.eyeColor, roughness: 0.20, metalness: 0.00 }),
                eyePupil:new THREE.MeshStandardMaterial({ color: c.pupilColor, roughness: 0.20, metalness: 0.00 }),
                brow:    new THREE.MeshStandardMaterial({ color: c.browColor, roughness: 0.55, metalness: 0.00 }),
                lip:     new THREE.MeshStandardMaterial({ color: c.lipColor, roughness: 0.35, metalness: 0.00 }),
                // 헤드셋
                headsetBlack: new THREE.MeshStandardMaterial({ color: 0x101010, roughness: 0.35, metalness: 0.30 }),
                ledGreen:     new THREE.MeshStandardMaterial({ color: 0x4af04a, emissive: 0x4af04a, emissiveIntensity: 1.2 }),
                ribbon:       new THREE.MeshStandardMaterial({ color: 0x4a9d4a, roughness: 0.35, metalness: 0.10 })
            };
        }

        // === Skeleton (Root + 15 R15 joints) ===
        _buildSkeleton() {
            // 신체 비율 (m 단위 기준)
            const P = this.proportions = {
                footH: 0.06, lowerLegH: 0.42, upperLegH: 0.42,
                lowerTorsoH: 0.12, upperTorsoH: 0.50, upperTorsoW: 0.42,
                neckH: 0.05, headH: 0.24, headW: 0.21,
                shoulderOffsetX: 0.26, upperArmH: 0.36, lowerArmH: 0.32, handH: 0.10,
                hipOffsetX: 0.10, torsoDepth: 0.22, legDepth: 0.18
            };
            const yHip = P.footH + P.lowerLegH + P.upperLegH; // Root 본의 Y (월드 절대값)

            const mk = (name) => {
                const b = new THREE.Bone();
                b.name = name;
                this.bones[name] = b;
                return b;
            };
            // 본 생성
            const root = mk('Root');
            const lowerTorso = mk('LowerTorso');
            const upperTorso = mk('UpperTorso');
            const neck = mk('Neck');
            const lShoulder = mk('LeftShoulder');
            const lElbow = mk('LeftElbow');
            const lWrist = mk('LeftWrist');
            const rShoulder = mk('RightShoulder');
            const rElbow = mk('RightElbow');
            const rWrist = mk('RightWrist');
            const lHip = mk('LeftHip');
            const lKnee = mk('LeftKnee');
            const lAnkle = mk('LeftAnkle');
            const rHip = mk('RightHip');
            const rKnee = mk('RightKnee');
            const rAnkle = mk('RightAnkle');

            // R15 계층 구조
            root.add(lowerTorso);
            lowerTorso.add(upperTorso);
            upperTorso.add(neck);
            upperTorso.add(lShoulder); lShoulder.add(lElbow); lElbow.add(lWrist);
            upperTorso.add(rShoulder); rShoulder.add(rElbow); rElbow.add(rWrist);
            root.add(lHip); lHip.add(lKnee); lKnee.add(lAnkle);
            root.add(rHip); rHip.add(rKnee); rKnee.add(rAnkle);

            // 본의 LOCAL position = 그 본의 회전축(피벗)이 위치하는 곳
            root.position.set(0, yHip, 0); // 월드 절대 위치
            lowerTorso.position.set(0, 0, 0);                  // pelvis (root에 일치)
            upperTorso.position.set(0, P.lowerTorsoH, 0);      // waist
            neck.position.set(0, P.upperTorsoH, 0);            // neck base
            lShoulder.position.set(-P.shoulderOffsetX, P.upperTorsoH - 0.04, 0);
            rShoulder.position.set( P.shoulderOffsetX, P.upperTorsoH - 0.04, 0);
            lElbow.position.set(0, -P.upperArmH, 0);
            rElbow.position.set(0, -P.upperArmH, 0);
            lWrist.position.set(0, -P.lowerArmH, 0);
            rWrist.position.set(0, -P.lowerArmH, 0);
            lHip.position.set(-P.hipOffsetX, 0, 0);
            rHip.position.set( P.hipOffsetX, 0, 0);
            lKnee.position.set(0, -P.upperLegH, 0);
            rKnee.position.set(0, -P.upperLegH, 0);
            lAnkle.position.set(0, -P.lowerLegH, 0);
            rAnkle.position.set(0, -P.lowerLegH, 0);

            // 본을 캐릭터 그룹에 부착 + Skeleton 생성
            this.add(root);
            this.boneArray = R15_BONES.map(n => this.bones[n]);
            this.skeleton = new THREE.Skeleton(this.boneArray);
        }

        // 단일 본에 100% 가중된 강체(SkinnedMesh) 생성 헬퍼
        _makeRigidSkinnedMesh(geom, material, boneName) {
            const boneIdx = R15_BONES.indexOf(boneName);
            if (boneIdx < 0) throw new Error('Unknown bone: ' + boneName);
            const vc = geom.attributes.position.count;
            const skinIdx = new Uint16Array(vc * 4);
            const skinWt = new Float32Array(vc * 4);
            for (let i = 0; i < vc; i++) {
                skinIdx[i * 4 + 0] = boneIdx;
                skinWt[i * 4 + 0] = 1.0; // 나머지 3개는 0
            }
            geom.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(skinIdx, 4));
            geom.setAttribute('skinWeight', new THREE.Float32BufferAttribute(skinWt, 4));
            const mesh = new THREE.SkinnedMesh(geom, material);
            mesh.castShadow = true;
            mesh.receiveShadow = true;
            mesh.frustumCulled = false; // 본이 움직여도 컬링되지 않게
            mesh.bind(this.skeleton);
            this.add(mesh);
            this.skinnedMeshes.push(mesh);
            return mesh;
        }

        // 본의 자식으로 강체 메쉬 부착 (액세서리/얼굴 디테일용)
        _attachToBone(mesh, boneName) {
            this.bones[boneName].add(mesh);
            mesh.castShadow = true;
        }

        // === 본체 15개 R15 Body Part ===
        // 각 메쉬는 자신의 본 origin(=조인트 위치)에서 적절한 방향으로 translate
        _buildBodyParts() {
            const P = this.proportions;
            const M = this.mats;

            // UpperTorso: 본은 허리에 있고 메쉬는 위로 뻗음
            const upperTorsoGeom = new RoundedBoxGeometry(
                P.upperTorsoW, P.upperTorsoH, P.torsoDepth, 4, 0.045
            );
            upperTorsoGeom.translate(0, P.upperTorsoH * 0.5, 0);
            this.parts.upperTorso = this._makeRigidSkinnedMesh(upperTorsoGeom, M.uniform, 'UpperTorso');

            // LowerTorso: 본은 골반에 있고 메쉬는 위로
            const lowerTorsoGeom = new RoundedBoxGeometry(
                P.upperTorsoW * 0.88, P.lowerTorsoH, P.torsoDepth * 0.95, 3, 0.035
            );
            lowerTorsoGeom.translate(0, P.lowerTorsoH * 0.5, 0);
            this.parts.lowerTorso = this._makeRigidSkinnedMesh(lowerTorsoGeom, M.pants, 'LowerTorso');

            // Upper Arms (제복 색)
            const makeUpperArm = (boneName) => {
                const g = new RoundedBoxGeometry(0.155, P.upperArmH, 0.155, 3, 0.04);
                g.translate(0, -P.upperArmH * 0.5, 0);
                return this._makeRigidSkinnedMesh(g, M.uniform, boneName);
            };
            this.parts.leftUpperArm  = makeUpperArm('LeftShoulder');
            this.parts.rightUpperArm = makeUpperArm('RightShoulder');

            // Lower Arms (피부색)
            const makeLowerArm = (boneName) => {
                const g = new RoundedBoxGeometry(0.13, P.lowerArmH, 0.13, 3, 0.035);
                g.translate(0, -P.lowerArmH * 0.5, 0);
                return this._makeRigidSkinnedMesh(g, M.skin, boneName);
            };
            this.parts.leftLowerArm  = makeLowerArm('LeftElbow');
            this.parts.rightLowerArm = makeLowerArm('RightElbow');

            // Hands
            const makeHand = (boneName) => {
                const g = new RoundedBoxGeometry(0.12, P.handH, 0.135, 2, 0.04);
                g.translate(0, -P.handH * 0.5, 0);
                return this._makeRigidSkinnedMesh(g, M.skin, boneName);
            };
            this.parts.leftHand  = makeHand('LeftWrist');
            this.parts.rightHand = makeHand('RightWrist');

            // Upper Legs (바지)
            const makeUpperLeg = (boneName) => {
                const g = new RoundedBoxGeometry(0.18, P.upperLegH, P.legDepth, 3, 0.04);
                g.translate(0, -P.upperLegH * 0.5, 0);
                return this._makeRigidSkinnedMesh(g, M.pants, boneName);
            };
            this.parts.leftUpperLeg  = makeUpperLeg('LeftHip');
            this.parts.rightUpperLeg = makeUpperLeg('RightHip');

            // Lower Legs (바지)
            const makeLowerLeg = (boneName) => {
                const g = new RoundedBoxGeometry(0.16, P.lowerLegH, P.legDepth * 0.9, 3, 0.035);
                g.translate(0, -P.lowerLegH * 0.5, 0);
                return this._makeRigidSkinnedMesh(g, M.pants, boneName);
            };
            this.parts.leftLowerLeg  = makeLowerLeg('LeftKnee');
            this.parts.rightLowerLeg = makeLowerLeg('RightKnee');

            // Feet (구두)
            const makeFoot = (boneName) => {
                const g = new RoundedBoxGeometry(0.16, P.footH, 0.28, 2, 0.025);
                g.translate(0, -P.footH * 0.5, 0.05); // 앞쪽으로 살짝 길게
                return this._makeRigidSkinnedMesh(g, M.shoe, boneName);
            };
            this.parts.leftFoot  = makeFoot('LeftAnkle');
            this.parts.rightFoot = makeFoot('RightAnkle');
        }

        // === Head + face features ===
        _buildHead() {
            const P = this.proportions;
            const M = this.mats;

            // Head 박스: Neck 본 위로 headCenterOffset 만큼 위에 중심을 둠
            const headCenterY = P.neckH + P.headH * 0.5;
            const headGeom = new RoundedBoxGeometry(P.headW, P.headH, P.headW, 5, 0.065);
            headGeom.translate(0, headCenterY, 0);
            this.parts.head = this._makeRigidSkinnedMesh(headGeom, M.skin, 'Neck');

            // 목 원기둥
            const neckGeom = new RoundedBoxGeometry(0.09, P.neckH, 0.09, 2, 0.018);
            neckGeom.translate(0, P.neckH * 0.5, 0);
            this.parts.neckMesh = this._makeRigidSkinnedMesh(neckGeom, M.skin, 'Neck');

            // === 얼굴 디테일 (모두 Neck 본의 자식으로 부착) ===
            const faceZ = P.headW * 0.5;
            const eyeY = headCenterY + 0.005;
            const eyeX = 0.042;

            // 눈 흰자
            const eyeGeom = new THREE.SphereGeometry(0.025, 14, 14);
            for (const x of [-eyeX, eyeX]) {
                const eye = new THREE.Mesh(eyeGeom, M.eyeWhite);
                eye.position.set(x, eyeY, faceZ + 0.002);
                eye.scale.set(1.0, 0.85, 0.55);
                this._attachToBone(eye, 'Neck');
            }
            // 홍채
            const irisGeom = new THREE.SphereGeometry(0.015, 12, 12);
            for (const x of [-eyeX, eyeX]) {
                const iris = new THREE.Mesh(irisGeom, M.eyeIris);
                iris.position.set(x, eyeY, faceZ + 0.013);
                this._attachToBone(iris, 'Neck');
            }
            // 동공 + 하이라이트
            for (const x of [-eyeX, eyeX]) {
                const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.007, 8, 8), M.eyePupil);
                pupil.position.set(x, eyeY, faceZ + 0.018);
                this._attachToBone(pupil, 'Neck');
                const hi = new THREE.Mesh(new THREE.SphereGeometry(0.004, 6, 6),
                    new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.6 }));
                hi.position.set(x - 0.004, eyeY + 0.005, faceZ + 0.020);
                this._attachToBone(hi, 'Neck');
            }
            // 눈썹 (각도 부여)
            const browGeom = new RoundedBoxGeometry(0.045, 0.012, 0.013, 2, 0.005);
            const lBrow = new THREE.Mesh(browGeom, M.brow);
            lBrow.position.set(-eyeX, eyeY + 0.032, faceZ - 0.002);
            lBrow.rotation.z = -0.10;
            this._attachToBone(lBrow, 'Neck');
            const rBrow = new THREE.Mesh(browGeom, M.brow);
            rBrow.position.set(eyeX, eyeY + 0.032, faceZ - 0.002);
            rBrow.rotation.z = 0.10;
            this._attachToBone(rBrow, 'Neck');
            // 코 (작은 원뿔)
            const nose = new THREE.Mesh(
                new THREE.ConeGeometry(0.012, 0.025, 8),
                new THREE.MeshStandardMaterial({ color: 0xe8b88a, roughness: 0.5 })
            );
            nose.rotation.x = Math.PI / 2;
            nose.position.set(0, eyeY - 0.025, faceZ + 0.008);
            this._attachToBone(nose, 'Neck');
            // 입술
            const lipGeom = new RoundedBoxGeometry(0.05, 0.012, 0.008, 2, 0.005);
            const lip = new THREE.Mesh(lipGeom, M.lip);
            lip.position.set(0, eyeY - 0.055, faceZ + 0.004);
            this._attachToBone(lip, 'Neck');
            // 머리카락 (스타일별)
            this._buildHair(headCenterY);
        }

        // === Hair ===
        _buildHair(headY) {
            const P = this.proportions;
            const M = this.mats;

            // 모든 스타일 공통: 정수리 캡
            const topGeom = new RoundedBoxGeometry(P.headW + 0.015, P.headH * 0.6, P.headW + 0.015, 4, 0.07);
            topGeom.translate(0, headY + P.headH * 0.22, 0);
            const top = new THREE.Mesh(topGeom, M.hair);
            this._attachToBone(top, 'Neck');
            this.accessories.push(top);

            // 앞머리 (얇은 박스)
            const bangGeom = new RoundedBoxGeometry(P.headW - 0.01, 0.05, 0.025, 2, 0.012);
            const bang = new THREE.Mesh(bangGeom, M.hair);
            bang.position.set(0, headY + P.headH * 0.25, P.headW * 0.5 - 0.003);
            bang.rotation.x = -0.18;
            this._attachToBone(bang, 'Neck');
            this.accessories.push(bang);

            if (this.config.hairStyle === 'braids') {
                this._buildTwinBraids(headY);
            } else {
                this._buildLongHair(headY);
            }
        }

        _buildLongHair(headY) {
            const P = this.proportions;
            const M = this.mats;
            // 옆머리 (어깨까지 내려옴)
            const sideGeom = new RoundedBoxGeometry(0.045, P.headH * 1.5, P.headW * 0.75, 2, 0.022);
            const lSide = new THREE.Mesh(sideGeom, M.hair);
            lSide.position.set(-P.headW * 0.5 - 0.01, headY - P.headH * 0.25, -0.005);
            this._attachToBone(lSide, 'Neck');
            const rSide = new THREE.Mesh(sideGeom, M.hair);
            rSide.position.set(P.headW * 0.5 + 0.01, headY - P.headH * 0.25, -0.005);
            this._attachToBone(rSide, 'Neck');
            // 뒤로 흐르는 뒷머리
            const backGeom = new RoundedBoxGeometry(P.headW * 0.85, P.headH * 1.2, 0.04, 3, 0.02);
            const back = new THREE.Mesh(backGeom, M.hair);
            back.position.set(0, headY - P.headH * 0.2, -P.headW * 0.5 - 0.01);
            this._attachToBone(back, 'Neck');
            this.accessories.push(lSide, rSide, back);
        }

        _buildTwinBraids(headY) {
            const P = this.proportions;
            const M = this.mats;

            const makeBraid = (side) => {
                const grp = new THREE.Group();
                // 7세그먼트 땋은 패턴 (가운데가 가장 두꺼움)
                const segCount = 7;
                const segH = 0.052;
                for (let i = 0; i < segCount; i++) {
                    const w = 0.06 - i * 0.005;
                    const seg = new THREE.Mesh(
                        new RoundedBoxGeometry(w, segH, w * 0.9, 3, 0.022),
                        M.hair
                    );
                    seg.position.set(
                        Math.sin(i * 0.6) * 0.004, // 미세한 지그재그
                        -segH * 0.5 - i * segH * 0.95,
                        0
                    );
                    grp.add(seg);
                }
                // 위 초록 리본
                const tieTop = new THREE.Mesh(
                    new RoundedBoxGeometry(0.08, 0.02, 0.08, 2, 0.01),
                    M.ribbon
                );
                tieTop.position.set(0, 0.012, 0);
                grp.add(tieTop);
                // 아래 초록 리본
                const tieBtm = new THREE.Mesh(
                    new RoundedBoxGeometry(0.045, 0.018, 0.045, 2, 0.008),
                    M.ribbon
                );
                tieBtm.position.set(0, -segH * segCount * 0.95 - 0.008, 0);
                grp.add(tieBtm);

                grp.position.set(
                    side * (P.headW * 0.5 + 0.025),
                    headY - 0.03,
                    -0.015
                );
                return grp;
            };

            const lBraid = makeBraid(-1);
            const rBraid = makeBraid(1);
            this._attachToBone(lBraid, 'Neck');
            this._attachToBone(rBraid, 'Neck');
            this.accessories.push(lBraid, rBraid);
        }

        // === Accessories (입체 별 배지/모자/제복 디테일/개인 액세서리) ===
        _buildAccessories() {
            const P = this.proportions;
            const M = this.mats;
            const torsoTop = P.upperTorsoH;
            const torsoFront = P.torsoDepth * 0.5;

            // === 흰 셔츠 칼라 + 넥타이 ===
            const collar = new THREE.Mesh(
                new RoundedBoxGeometry(0.18, 0.09, 0.04, 2, 0.012),
                M.white
            );
            collar.position.set(0, torsoTop * 0.78, torsoFront + 0.005);
            this._attachToBone(collar, 'UpperTorso');

            const tie = new THREE.Mesh(
                new RoundedBoxGeometry(0.055, 0.30, 0.018, 2, 0.008),
                M.tie
            );
            tie.position.set(0, torsoTop * 0.45, torsoFront + 0.014);
            this._attachToBone(tie, 'UpperTorso');

            // === 금속 단추 4개 (세로) ===
            for (let i = 0; i < 4; i++) {
                const btn = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.013, 0.013, 0.006, 14),
                    M.gold
                );
                btn.rotation.x = Math.PI / 2;
                btn.position.set(0.045, torsoTop * 0.6 - i * 0.075, torsoFront + 0.015);
                this._attachToBone(btn, 'UpperTorso');
            }

            // === 가슴 POLICE 배지 (오벌 + 입체 별) ===
            const badgeOval = new THREE.Mesh(
                new THREE.CylinderGeometry(0.05, 0.05, 0.014, 18),
                M.gold
            );
            badgeOval.rotation.x = Math.PI / 2;
            badgeOval.scale.set(1.0, 1.0, 1.25);
            badgeOval.position.set(0.115, torsoTop * 0.3, torsoFront + 0.012);
            this._attachToBone(badgeOval, 'UpperTorso');
            const badgeStar = new THREE.Mesh(
                new THREE.ExtrudeGeometry(this._makeStarShape(0.026, 0.013, 5), {
                    depth: 0.01, bevelEnabled: true,
                    bevelSize: 0.003, bevelThickness: 0.003, bevelSegments: 2
                }),
                M.gold
            );
            badgeStar.position.set(0.115, torsoTop * 0.3, torsoFront + 0.022);
            this._attachToBone(badgeStar, 'UpperTorso');
            this.accessories.push(badgeOval, badgeStar);

            // === 어깨 견장 (★★ 두개) ===
            const epaGeom = new RoundedBoxGeometry(0.09, 0.014, 0.055, 2, 0.005);
            for (const side of [-1, 1]) {
                const epau = new THREE.Mesh(epaGeom, M.tie);
                epau.position.set(side * 0.12, torsoTop - 0.018, 0);
                this._attachToBone(epau, 'UpperTorso');
                // 작은 별 2개
                for (let i = 0; i < 2; i++) {
                    const s = new THREE.Mesh(
                        new THREE.ExtrudeGeometry(this._makeStarShape(0.008, 0.004, 5), {
                            depth: 0.004, bevelEnabled: false
                        }),
                        M.gold
                    );
                    s.position.set(side * 0.12 + (i - 0.5) * 0.015, torsoTop - 0.008, 0.022);
                    this._attachToBone(s, 'UpperTorso');
                }
            }

            // === 어깨 POLICE 패치 (상박 안쪽) ===
            const patchMat = new THREE.MeshStandardMaterial({ color: 0x0a1730, roughness: 0.5, metalness: 0.0 });
            const patchGeom = new RoundedBoxGeometry(0.13, 0.15, 0.005, 2, 0.01);
            for (const [side, boneName] of [[-1, 'LeftShoulder'], [1, 'RightShoulder']]) {
                const patch = new THREE.Mesh(patchGeom, patchMat);
                patch.position.set(side * 0.077, -P.upperArmH * 0.4, 0);
                patch.rotation.y = side * Math.PI * 0.5;
                this._attachToBone(patch, boneName);
            }

            // === 경찰 모자 (Cap) ===
            this._buildCap();

            // === 개인 액세서리 ===
            if (this.config.accessory === 'redClip') {
                this._buildRedClip();
            } else if (this.config.accessory === 'headset') {
                this._buildHeadset();
            }
        }

        _makeStarShape(outerR, innerR, points) {
            const shape = new THREE.Shape();
            for (let i = 0; i < points * 2; i++) {
                const r = (i % 2 === 0) ? outerR : innerR;
                const a = (i / (points * 2)) * Math.PI * 2 - Math.PI / 2;
                const x = Math.cos(a) * r;
                const y = Math.sin(a) * r;
                if (i === 0) shape.moveTo(x, y);
                else shape.lineTo(x, y);
            }
            shape.closePath();
            return shape;
        }

        _buildCap() {
            const P = this.proportions;
            const M = this.mats;
            const headY = P.neckH + P.headH * 0.5;
            const capY = headY + P.headH * 0.5 + 0.04;

            // Crown
            const crown = new THREE.Mesh(
                new RoundedBoxGeometry(P.headW + 0.06, 0.09, P.headW + 0.06, 4, 0.045),
                M.capDark
            );
            crown.position.set(0, capY, 0);
            this._attachToBone(crown, 'Neck');

            // Gold band
            const band = new THREE.Mesh(
                new THREE.BoxGeometry(P.headW + 0.064, 0.012, P.headW + 0.064),
                M.gold
            );
            band.position.set(0, capY - 0.045, 0);
            this._attachToBone(band, 'Neck');

            // Visor (앞)
            const visor = new THREE.Mesh(
                new RoundedBoxGeometry(P.headW + 0.08, 0.012, 0.08, 2, 0.008),
                M.capVisor
            );
            visor.position.set(0, capY - 0.055, P.headW * 0.5 + 0.025);
            visor.rotation.x = 0.08;
            this._attachToBone(visor, 'Neck');

            // === 모자 별 (오벌 + 입체 별) — 로블록스 액세서리 스타일 ===
            const capBadgeOval = new THREE.Mesh(
                new THREE.CylinderGeometry(0.045, 0.045, 0.013, 16),
                M.gold
            );
            capBadgeOval.rotation.x = Math.PI / 2;
            capBadgeOval.scale.set(1.0, 1.0, 1.2);
            capBadgeOval.position.set(0, capY, P.headW * 0.5 + 0.012);
            this._attachToBone(capBadgeOval, 'Neck');
            const capStar = new THREE.Mesh(
                new THREE.ExtrudeGeometry(this._makeStarShape(0.024, 0.012, 5), {
                    depth: 0.012, bevelEnabled: true,
                    bevelSize: 0.003, bevelThickness: 0.003, bevelSegments: 2
                }),
                M.gold
            );
            capStar.position.set(0, capY, P.headW * 0.5 + 0.022);
            this._attachToBone(capStar, 'Neck');
            this.accessories.push(crown, band, visor, capBadgeOval, capStar);
        }

        _buildRedClip() {
            const P = this.proportions;
            const headY = P.neckH + P.headH * 0.5;
            const clip = new THREE.Mesh(
                new RoundedBoxGeometry(0.05, 0.015, 0.014, 2, 0.005),
                this.mats.redClip
            );
            clip.position.set(P.headW * 0.42, headY + P.headH * 0.22, P.headW * 0.4);
            clip.rotation.y = 0.3;
            this._attachToBone(clip, 'Neck');
            this.accessories.push(clip);
        }

        _buildHeadset() {
            const P = this.proportions;
            const M = this.mats;
            const headY = P.neckH + P.headH * 0.5;

            // 헤드밴드 (Torus 반원)
            const band = new THREE.Mesh(
                new THREE.TorusGeometry(P.headW * 0.6, 0.012, 8, 26, Math.PI),
                M.headsetBlack
            );
            band.position.set(0, headY + P.headH * 0.4, 0);
            band.rotation.y = Math.PI / 2;
            this._attachToBone(band, 'Neck');

            // 오른쪽 이어피스
            const ear = new THREE.Mesh(
                new RoundedBoxGeometry(0.035, 0.075, 0.05, 3, 0.018),
                M.headsetBlack
            );
            ear.position.set(P.headW * 0.5 + 0.018, headY + 0.005, 0);
            this._attachToBone(ear, 'Neck');

            // 마이크 붐 (곡선 — 짧은 원기둥 2개 + 마이크 헤드)
            const boom1 = new THREE.Mesh(
                new THREE.CylinderGeometry(0.006, 0.006, 0.12, 8), M.headsetBlack
            );
            boom1.position.set(P.headW * 0.45, headY - 0.05, 0.025);
            boom1.rotation.z = -0.5;
            boom1.rotation.y = -0.4;
            this._attachToBone(boom1, 'Neck');

            const boom2 = new THREE.Mesh(
                new THREE.CylinderGeometry(0.005, 0.005, 0.08, 8), M.headsetBlack
            );
            boom2.position.set(P.headW * 0.28, headY - 0.085, P.headW * 0.32);
            boom2.rotation.z = -0.4;
            boom2.rotation.y = -0.8;
            this._attachToBone(boom2, 'Neck');

            // 마이크 헤드
            const micHead = new THREE.Mesh(
                new THREE.SphereGeometry(0.018, 12, 12), M.headsetBlack
            );
            micHead.position.set(P.headW * 0.15, headY - 0.105, P.headW * 0.52);
            this._attachToBone(micHead, 'Neck');

            // 녹색 LED
            const led = new THREE.Mesh(
                new THREE.SphereGeometry(0.008, 8, 8), M.ledGreen
            );
            led.position.set(P.headW * 0.5 + 0.045, headY + 0.04, 0);
            this._attachToBone(led, 'Neck');

            this.accessories.push(band, ear, boom1, boom2, micHead, led);
        }

        // === Default pose: 양팔 내림, 정면 직립 ===
        _setDefaultPose() {
            // 모든 본 회전 0 → 메쉬 geometry가 본 origin 아래로 translate 되어 있으므로
            // 자연스럽게 양팔이 내려진 차렷 자세
            for (const name of R15_BONES) {
                this.bones[name].rotation.set(0, 0, 0);
            }
        }

        // ============ Public API ============

        /** 본 회전 설정 (Euler XYZ 라디안) */
        setJointRotation(name, x = 0, y = 0, z = 0) {
            const b = this.bones[name];
            if (b) b.rotation.set(x, y, z);
        }

        /** 걷기 사이클 (Game loop 매 프레임 호출) */
        updateWalk(time, intensity = 1) {
            const s = Math.sin(time * 6) * 0.4 * intensity;
            const c = Math.cos(time * 6);
            this.setJointRotation('LeftHip',   s, 0, 0);
            this.setJointRotation('RightHip', -s, 0, 0);
            this.setJointRotation('LeftKnee',  Math.max(0, -s * 0.7), 0, 0);
            this.setJointRotation('RightKnee', Math.max(0,  s * 0.7), 0, 0);
            this.setJointRotation('LeftShoulder',  -s * 0.7, 0, 0);
            this.setJointRotation('RightShoulder', s * 0.7, 0, 0);
            this.setJointRotation('LeftElbow',  Math.max(0, -s * 0.4), 0, 0);
            this.setJointRotation('RightElbow', Math.max(0,  s * 0.4), 0, 0);
            // 미세한 상체 흔들림
            this.setJointRotation('UpperTorso', 0, c * 0.05 * intensity, 0);
        }

        /** 정적 호흡 (Idle) */
        updateIdle(time) {
            const br = Math.sin(time * 1.6) * 0.015;
            this.setJointRotation('UpperTorso', br, 0, 0);
            this.setJointRotation('Neck', -br * 0.4, 0, 0);
        }

        /** 경례 자세 (오른손 기본) */
        poseSalute(rightHand = true) {
            const sh = rightHand ? 'RightShoulder' : 'LeftShoulder';
            const el = rightHand ? 'RightElbow' : 'LeftElbow';
            const dir = rightHand ? -1 : 1;
            this.setJointRotation(sh, 0, 0, dir * 2.0);
            this.setJointRotation(el, 0, 0, dir * 1.6);
            this.setJointRotation('Neck', -0.05, 0, 0);
        }

        /** dispose: 모든 geometry/material 메모리 해제 */
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

    // ─────────────────────────────────────────────────────────────────────
    // SoyunCharacter — 따뜻한 갈색 머리/갈색 눈/빨간 클립
    // ─────────────────────────────────────────────────────────────────────
    class SoyunCharacter extends RobloxR15Character {
        constructor(config = {}) {
            super(Object.assign({
                skinColor:    0xfae4c8,
                uniformColor: 0x1a2a4a,
                pantsColor:   0x0a1730,
                hairColor:    0x5a3a1c,
                hairStyle:    'long',
                eyeColor:     0x7a4d28,    // 따뜻한 갈색
                pupilColor:   0x1a0a00,
                browColor:    0x3a2010,
                lipColor:     0xc97560,    // 피치 코랄
                accessory:    'redClip'
            }, config));
            this.name = 'Soyun';
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // HayunCharacter — 양갈래 땋은머리/푸른 눈/헤드셋
    // ─────────────────────────────────────────────────────────────────────
    class HayunCharacter extends RobloxR15Character {
        constructor(config = {}) {
            super(Object.assign({
                skinColor:    0xfae4c8,
                uniformColor: 0x1a2a4a,
                pantsColor:   0x0a1730,
                hairColor:    0x4a2a18,
                hairStyle:    'braids',
                eyeColor:     0x3a82d4,    // 푸른 눈
                pupilColor:   0x0a1a3a,
                browColor:    0x2a1808,
                lipColor:     0xd07060,
                accessory:    'headset'
            }, config));
            this.name = 'Hayun';
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Scene 조명 헬퍼 — 화사한 림 라이트 + 부드러운 키 라이트 + 풍부한 대기광
    // ─────────────────────────────────────────────────────────────────────
    function setupRobloxLighting(scene) {
        // 풍부한 대기광 (따뜻한 창가 분위기)
        const ambient = new THREE.AmbientLight(0xfff5e6, 0.80);
        scene.add(ambient);
        // 하늘/땅 반사광
        const hemi = new THREE.HemisphereLight(0xcfe9ff, 0xc8b09a, 0.65);
        hemi.position.set(0, 5, 0);
        scene.add(hemi);
        // 정면-위 키 라이트 (메인)
        const key = new THREE.DirectionalLight(0xffe8c0, 1.0);
        key.position.set(2.2, 3.0, 2.5);
        key.castShadow = true;
        key.shadow.mapSize.width = 2048;
        key.shadow.mapSize.height = 2048;
        key.shadow.camera.left = -2.5;
        key.shadow.camera.right = 2.5;
        key.shadow.camera.top = 3.0;
        key.shadow.camera.bottom = -1.0;
        key.shadow.camera.near = 0.1;
        key.shadow.camera.far = 12;
        key.shadow.bias = -0.0003;
        scene.add(key);
        // === RIM LIGHT (등 뒤에서 강한 직사광 — 블록 테두리 빛남) ===
        const rim = new THREE.DirectionalLight(0xffffff, 1.8);
        rim.position.set(-0.8, 3.5, -3.5);
        scene.add(rim);
        // 보조 사이드 림 (푸른빛)
        const sideRim = new THREE.DirectionalLight(0xa8d8ff, 0.7);
        sideRim.position.set(-3.0, 2.0, -1.5);
        scene.add(sideRim);
        return { ambient, hemi, key, rim, sideRim };
    }

    // 렌더러 설정 (플라스틱 피규어 느낌의 톤매핑)
    function configureRobloxRenderer(renderer) {
        renderer.outputEncoding = THREE.sRGBEncoding;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.18;
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        renderer.physicallyCorrectLights = true;
    }

    // === Export ===
    window.RobloxCharacters = {
        Base: RobloxR15Character,
        Soyun: SoyunCharacter,
        Hayun: HayunCharacter,
        RoundedBoxGeometry,
        setupLighting: setupRobloxLighting,
        configureRenderer: configureRobloxRenderer,
        R15_BONES
    };
})();
