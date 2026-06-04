// npc.js — 수배범 NPC (도망가는 정보원, 잡으면 힌트 제공)

const NPCSystem = window.NPCSystem = {
    npcs: [],
    interactDistance: 1.5,  // catch distance (closer for catch mechanic)
    nearbyNpc: null,
    dialogOpen: false,
    detectDistance: 12,
    // Speeds — must be slower than corresponding criminal flee speeds
    // criminal flee speeds: 1호=0.06, 2호=0.09, 3호=0.13
    fleeSpeeds: [0.04, 0.065, 0.09],

    assets: null,         // GLB 자산 ({template, anims:{idle,walk,run}})
    _assetsLoading: false,

    init(scene) {
        this.scene = scene;
        this.createDialogUI();
        this.distributeHints();
        // GLB 자산 비동기 로드 후 NPC 스폰. 로드 실패 시 절차적 모드로 폴백.
        this._loadAssets().then(() => {
            console.log('[NPC] GLB 자산 로드 완료, NPC 생성');
            this.spawnNPCs();
        }).catch(err => {
            console.warn('[NPC] GLB 로드 실패, 절차적 폴백:', err);
            this.spawnNPCs();
        });
    },

    async _loadAssets() {
        if (this.assets) return this.assets;
        const loader = new THREE.GLTFLoader();
        const load = (p) => new Promise((res, rej) => loader.load(p, res, undefined, rej));
        const [npcGltf, idleGltf, walkGltf, runGltf] = await Promise.all([
            load('assets/models/npc-normal.glb'),
            load('assets/models/idle.glb'),
            load('assets/models/walk.glb'),
            load('assets/models/run.glb')
        ]);
        this.assets = {
            template: npcGltf.scene,
            anims: {
                idle: idleGltf.animations[0],
                walk: walkGltf.animations[0],
                run: runGltf.animations[0]
            }
        };
        return this.assets;
    },

    _createGLBNPCMesh(arch, assignment) {
        if (!THREE.SkeletonUtils) {
            console.warn('[NPC] SkeletonUtils 미로드, 절차적 폴백');
            return null;
        }
        const glb = THREE.SkeletonUtils.clone(this.assets.template);
        // 피부색 적용 (arch.skin)
        glb.traverse(o => {
            if (o.isMesh) {
                const m = o.material.clone();
                m.color.setHex(arch.skin || 0xe8c4a0);
                o.material = m;
                o.castShadow = true;
                o.receiveShadow = true;
            }
        });
        glb.scale.setScalar(1.2); // 플레이어와 동일 (1.79m × 1.2 ≈ 2.15유닛)
        glb.position.set(arch.x, 0, arch.z);
        glb.rotation.y = Math.random() * Math.PI * 2;
        // Mixer + 3개 액션
        const mixer = new THREE.AnimationMixer(glb);
        const actions = {
            idle: mixer.clipAction(this.assets.anims.idle),
            walk: mixer.clipAction(this.assets.anims.walk),
            run: mixer.clipAction(this.assets.anims.run)
        };
        actions.idle.play();
        glb.userData.mixer = mixer;
        glb.userData.actions = actions;
        glb.userData.animState = 'idle';
        this.scene.add(glb);
        // 절차적과 동일한 wrapper 구조 반환
        return {
            mesh: glb,
            ...arch,
            assignment,
            visited: false,
            walkTime: Math.random() * 10,
            wanderTarget: { x: arch.x, z: arch.z },
            baseX: arch.x,
            baseZ: arch.z,
            talkIcon: null
        };
    },

    _setAnimState(npcMesh, state) {
        if (!npcMesh.userData.actions) return; // 절차적 NPC면 무시
        if (npcMesh.userData.animState === state) return;
        const oldAction = npcMesh.userData.actions[npcMesh.userData.animState];
        const newAction = npcMesh.userData.actions[state];
        if (oldAction) oldAction.fadeOut(0.2);
        newAction.reset().fadeIn(0.2).play();
        npcMesh.userData.animState = state;
    },

    // STEP 1: citypack 도로 위로 NPC 재배치 (citypack 로드 후 main.js가 호출)
    snapToCitypackRoads() {
        if (!this.npcs || !window.findCitypackSafeSpawn) return;
        const bounds = window._citypackBounds;
        let moved = 0;
        this.npcs.forEach((npc, i) => {
            const cur = npc.mesh.position;
            // 절차적 좌표 그대로면 citypack 안에서는 한 곳에 다 모여있음
            // → bounds 기반으로 spread 후 도로 위로 snap
            let baseX = cur.x, baseZ = cur.z;
            if (bounds) {
                // 12명을 도시 전역에 펼침 (원형 분포, 반경 = 도시 절반의 60%)
                const cityCX = (bounds.minX + bounds.maxX) / 2;
                const cityCZ = (bounds.minZ + bounds.maxZ) / 2;
                const radius = Math.min(bounds.maxX - bounds.minX, bounds.maxZ - bounds.minZ) * 0.3;
                const angle = (i / this.npcs.length) * Math.PI * 2;
                baseX = cityCX + Math.cos(angle) * radius;
                baseZ = cityCZ + Math.sin(angle) * radius;
            }
            // 마진 4로 도로 위 안전 자리 검색 (건물에서 충분히 떨어짐)
            const safe = window.findCitypackSafeSpawn(baseX, baseZ, 4);
            if (safe.x !== cur.x || safe.z !== cur.z) moved++;
            npc.baseX = safe.x;
            npc.baseZ = safe.z;
            npc.mesh.position.x = safe.x;
            npc.mesh.position.z = safe.z;
            if (npc.wanderTarget) npc.wanderTarget = { x: safe.x, z: safe.z };
        });
        console.log(`[NPC] ${moved}/${this.npcs.length} NPC snapped to citypack roads (spread + margin 4)`);
    },

    distributeHints() {
        this.hintAssignments = [];
        const hintTexts = (HintSystem && HintSystem.hintTexts) || { 0: [], 1: [], 2: [] };
        const hintsRequired = (HintSystem && HintSystem.hintsRequired) || [3, 4, 5];
        for (let c = 0; c < 3; c++) {
            const texts = hintTexts[c] || [];
            const required = hintsRequired[c] || 3;
            for (let o = 0; o < required; o++) {
                const t = texts[o] || ('단서 ' + (o + 1));
                this.hintAssignments.push({ criminal: c, order: o, text: t });
            }
        }
    },

    npcArchetypes: [
        // role: 'civilian' (stationary, talkable) | 'suspect' (runs, catch via minigame)
        // Civilians: tell their story + give a hint when talked to
        { x: -25, z: 72, name: '카페 점원 민지', role: 'civilian',
          hair: 0x4a2510, skin: 0xffdbac, clothing: 0xff6b9d, zone: 'POLICE',
          story: '형사님, 도와주세요. 손님이 이상한 사람을 봤다고 해요...' },
        { x: 25, z: 72, name: '편의점 알바 호석', role: 'civilian',
          hair: 0x1a0a00, skin: 0xf5d5b8, clothing: 0x60a5fa, zone: 'POLICE',
          story: '늦은 밤 자주 오는 손님이 있는데, 항상 모자를 깊게 눌러쓰고 와요.' },
        { x: -30, z: 25, name: '주민 김씨', role: 'suspect',
          hair: 0x2a1808, skin: 0xfff2dc, clothing: 0x9b8b9d, zone: 'RESIDENTIAL',
          story: '저는... 그냥 살려고 했을 뿐이에요. 시키는 대로 했을 뿐...' },
        { x: -70, z: -25, name: '학생 이지수', role: 'civilian',
          hair: 0x4a2510, skin: 0xffdbac, clothing: 0xfbbf24, zone: 'RESIDENTIAL',
          story: '학교 가는 길에 이상한 차가 자주 서있었어요. 너무 무서워요.' },
        { x: -110, z: 20, name: '아주머니 박씨', role: 'civilian',
          hair: 0x1a0a00, skin: 0xf5d5b8, clothing: 0xe05080, zone: 'RESIDENTIAL',
          story: '우리 동네에 아이들이 사라졌어요. 형사님, 꼭 찾아주세요.' },
        { x: -25, z: -25, name: '할아버지 최씨', role: 'suspect',
          hair: 0xdddddd, skin: 0xefcfa8, clothing: 0x718096, zone: 'RESIDENTIAL',
          story: '항복합니다... 솔직히 말씀드릴게요...' },
        { x: 30, z: 25, name: '직장인 정현우', role: 'civilian',
          hair: 0x1a0a00, skin: 0xffdbac, clothing: 0x1e3a8a, zone: 'COMMERCIAL',
          story: '퇴근길에 본 게 있어요. 누군가 아이를 끌고 가는 모습을...' },
        { x: 75, z: -10, name: '학생 윤서연', role: 'suspect',
          hair: 0x4a2510, skin: 0xf5d5b8, clothing: 0x06c167, zone: 'COMMERCIAL',
          story: '죄송해요... 돈이 필요해서 그랬어요...' },
        { x: 110, z: 20, name: '바리스타 다은', role: 'civilian',
          hair: 0x2a1808, skin: 0xfff2dc, clothing: 0x8b4513, zone: 'COMMERCIAL',
          story: '카페에 자주 오는 손님이 있어요. 검은 정장에 흉터가 있는...' },
        { x: 30, z: -60, name: '경비원 한대수', role: 'suspect',
          hair: 0x222222, skin: 0xefcfa8, clothing: 0x2d3748, zone: 'COMMERCIAL',
          story: '저도 그자에게 협박당했어요. 모든 걸 말씀드릴게요...' },
        { x: -50, z: -110, name: '근로자 송기철', role: 'civilian',
          hair: 0x1a0a00, skin: 0xddaa88, clothing: 0xff8800, zone: 'FACTORY',
          story: '공장에서 일하다가 본 게 있어요. 밤에 트럭들이 들락날락해요.' },
        { x: 30, z: -110, name: '공장장 조경석', role: 'suspect',
          hair: 0x444444, skin: 0xffdbac, clothing: 0x4a5568, zone: 'FACTORY',
          story: '저 사실은... 그 조직의 일원이었어요. 다 말씀드릴게요...' },
    ],

    spawnNPCs() {
        const assignments = [...this.hintAssignments];
        for (let i = assignments.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [assignments[i], assignments[j]] = [assignments[j], assignments[i]];
        }

        this.npcArchetypes.forEach((arch, i) => {
            // Snap NPC to safe outdoor position before creating mesh
            const safe = this._findSafePosition(arch.x, arch.z);
            const safeArch = { ...arch, x: safe.x, z: safe.z };
            const assignment = assignments[i] || null;
            const npc = this.createNPCMesh(safeArch, assignment);
            // Also update baseX/baseZ to the safe position
            npc.baseX = safe.x;
            npc.baseZ = safe.z;
            npc.wanderTarget = { x: safe.x, z: safe.z };
            this.npcs.push(npc);
        });
    },

    _spawnNightExtras() {
        // Lazily spawn 4 extra night-only wanted suspects (no hint, just bounty)
        if (this._nightExtras) {
            this._nightExtras.forEach(e => { e.mesh.visible = !e.caught; });
            return;
        }
        this._nightExtras = [];
        const positions = [
            [-60, 60], [70, 60], [-80, -20], [80, -20]
        ];
        positions.forEach(([px, pz]) => {
            const safe = this._findSafePosition(px, pz);
            const arch = {
                x: safe.x, z: safe.z, role: 'suspect',
                hair: [0x1a0a00, 0x4a2510, 0x222222][Math.floor(Math.random()*3)],
                skin: 0xddbb99,
                clothing: [0x4a3520, 0x2d3748, 0x553355][Math.floor(Math.random()*3)],
                name: '밤 수배범',
                story: '으윽... 들켰군.'
            };
            const npc = this.createNPCMesh(arch, null);
            npc.baseX = safe.x; npc.baseZ = safe.z;
            npc.wanderTarget = { x: safe.x, z: safe.z };
            this.npcs.push(npc);
            this._nightExtras.push(npc);
        });
    },

    _hideNightExtras() {
        if (!this._nightExtras) return;
        this._nightExtras.forEach(e => { e.mesh.visible = false; });
    },

    _findSafePosition(x, z) {
        // citypack 모드: 전역 헬퍼 사용
        if (window.findCitypackSafeSpawn) {
            return window.findCitypackSafeSpawn(x, z, 1);
        }
        // 절차적 모드: 건물 밀어내기 반복
        if (!window._buildingPositions) return { x, z };
        let cx = x, cz = z;
        for (let pass = 0; pass < 6; pass++) {
            const inside = window._buildingPositions.find(b =>
                Math.abs(cx - b.x) < b.w / 2 + 0.8 && Math.abs(cz - b.z) < b.d / 2 + 0.8
            );
            if (!inside) return { x: cx, z: cz };
            const dx = cx - inside.x;
            const dz = cz - inside.z;
            // Push in dominant axis direction; if dead-centered, pick a side.
            if (Math.abs(dx) >= Math.abs(dz)) {
                cx = inside.x + (dx >= 0 ? 1 : -1) * (inside.w / 2 + 2.5);
            } else {
                cz = inside.z + (dz >= 0 ? 1 : -1) * (inside.d / 2 + 2.5);
            }
        }
        return { x: cx, z: cz };
    },

    createNPCMesh(arch, assignment) {
        // GLB 자산이 로드되어 있으면 GLB로 생성
        if (this.assets) {
            const wrapper = this._createGLBNPCMesh(arch, assignment);
            if (wrapper) return wrapper;
        }
        // 폴백: 기존 절차적 메시
        const group = new THREE.Group();

        const bodyHeight = 0.7;
        const torsoHeight = 0.55;
        const armLen = 0.55;
        const legLen = 0.65;
        const headRadius = 0.18;

        // === LEGS (with knee bend) ===
        const pantsMat = new THREE.MeshStandardMaterial({ color: 0x1f2937, roughness: 0.75 });

        const leftHip = new THREE.Group();
        leftHip.position.set(-0.1, 0.6, 0);
        const lThigh = new THREE.Mesh(
            new THREE.CylinderGeometry(0.08, 0.07, legLen * 0.5, 10),
            pantsMat
        );
        lThigh.position.y = -legLen * 0.25;
        lThigh.castShadow = true;
        leftHip.add(lThigh);
        const lShin = new THREE.Mesh(
            new THREE.CylinderGeometry(0.07, 0.06, legLen * 0.5, 10),
            pantsMat
        );
        lShin.position.y = -legLen * 0.75;
        lShin.castShadow = true;
        leftHip.add(lShin);
        const lShoe = new THREE.Mesh(
            new THREE.BoxGeometry(0.15, 0.1, 0.28),
            new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.4 })
        );
        lShoe.position.set(0, -legLen + 0.05, 0.05);
        lShoe.castShadow = true;
        leftHip.add(lShoe);
        leftHip.userData.partName = 'leftHip';
        group.add(leftHip);

        const rightHip = new THREE.Group();
        rightHip.position.set(0.1, 0.6, 0);
        const rThigh = lThigh.clone();
        rightHip.add(rThigh);
        const rShin = lShin.clone();
        rightHip.add(rShin);
        const rShoe = lShoe.clone();
        rightHip.add(rShoe);
        rightHip.userData.partName = 'rightHip';
        group.add(rightHip);

        // === TORSO ===
        const torsoMat = new THREE.MeshStandardMaterial({ color: arch.clothing, roughness: 0.85 });
        const torso = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, torsoHeight, 0.28),
            torsoMat
        );
        torso.position.y = 0.6 + torsoHeight / 2;
        torso.castShadow = true;
        torso.userData.partName = 'torso';
        group.add(torso);

        // === ARMS (shoulder-elbow-wrist) ===
        const skinMat = new THREE.MeshStandardMaterial({ color: arch.skin, roughness: 0.6 });

        const leftShoulder = new THREE.Group();
        leftShoulder.position.set(-0.3, 0.6 + torsoHeight - 0.05, 0);
        const lUpperArm = new THREE.Mesh(
            new THREE.CylinderGeometry(0.07, 0.06, armLen * 0.5, 10),
            torsoMat
        );
        lUpperArm.position.y = -armLen * 0.25;
        lUpperArm.castShadow = true;
        leftShoulder.add(lUpperArm);
        const lForearm = new THREE.Mesh(
            new THREE.CylinderGeometry(0.06, 0.05, armLen * 0.5, 10),
            skinMat
        );
        lForearm.position.y = -armLen * 0.75;
        lForearm.castShadow = true;
        leftShoulder.add(lForearm);
        const lHand = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 12), skinMat);
        lHand.position.y = -armLen;
        leftShoulder.add(lHand);
        leftShoulder.userData.partName = 'leftShoulder';
        group.add(leftShoulder);

        const rightShoulder = leftShoulder.clone(true);
        rightShoulder.position.set(0.3, 0.6 + torsoHeight - 0.05, 0);
        rightShoulder.userData.partName = 'rightShoulder';
        group.add(rightShoulder);

        // === NECK + HEAD ===
        const neck = new THREE.Mesh(
            new THREE.CylinderGeometry(0.06, 0.07, 0.08, 8),
            skinMat
        );
        neck.position.y = 0.6 + torsoHeight + 0.04;
        group.add(neck);

        const head = new THREE.Mesh(
            new THREE.SphereGeometry(headRadius, 24, 24),
            skinMat
        );
        head.position.y = 0.6 + torsoHeight + 0.08 + headRadius;
        head.castShadow = true;
        head.userData.partName = 'head';
        group.add(head);

        const headY = head.position.y;

        // Hair (cap on top of head)
        const hairMat = new THREE.MeshStandardMaterial({ color: arch.hair, roughness: 0.85 });
        const hair = new THREE.Mesh(
            new THREE.SphereGeometry(headRadius + 0.015, 24, 24, 0, Math.PI * 2, 0, Math.PI * 0.55),
            hairMat
        );
        hair.position.y = headY + 0.02;
        group.add(hair);

        // Eyes
        const eyeWhiteMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
        const eyePupilMat = new THREE.MeshStandardMaterial({ color: 0x1a0a00 });
        const leftEye = new THREE.Mesh(new THREE.SphereGeometry(0.025, 10, 10), eyeWhiteMat);
        leftEye.position.set(-0.06, headY + 0.01, headRadius - 0.02);
        group.add(leftEye);
        const rightEye = new THREE.Mesh(new THREE.SphereGeometry(0.025, 10, 10), eyeWhiteMat);
        rightEye.position.set(0.06, headY + 0.01, headRadius - 0.02);
        group.add(rightEye);
        const lPupil = new THREE.Mesh(new THREE.SphereGeometry(0.012, 8, 8), eyePupilMat);
        lPupil.position.set(-0.06, headY + 0.01, headRadius);
        group.add(lPupil);
        const rPupil = new THREE.Mesh(new THREE.SphereGeometry(0.012, 8, 8), eyePupilMat);
        rPupil.position.set(0.06, headY + 0.01, headRadius);
        group.add(rPupil);

        // Eyebrows
        const browMat = new THREE.MeshStandardMaterial({ color: arch.hair });
        const lBrow = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.012, 0.012), browMat);
        lBrow.position.set(-0.06, headY + 0.05, headRadius - 0.02);
        group.add(lBrow);
        const rBrow = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.012, 0.012), browMat);
        rBrow.position.set(0.06, headY + 0.05, headRadius - 0.02);
        group.add(rBrow);

        // Nose
        const nose = new THREE.Mesh(
            new THREE.ConeGeometry(0.02, 0.04, 6),
            new THREE.MeshStandardMaterial({ color: 0xe8b88a })
        );
        nose.rotation.x = Math.PI / 2;
        nose.position.set(0, headY - 0.01, headRadius - 0.005);
        group.add(nose);

        // Mouth
        const mouth = new THREE.Mesh(
            new THREE.BoxGeometry(0.06, 0.012, 0.005),
            new THREE.MeshStandardMaterial({ color: 0xa0454d })
        );
        mouth.position.set(0, headY - 0.06, headRadius - 0.01);
        group.add(mouth);

        // No head indicator (per design requirement — players must approach to identify)
        const sprite = null;

        group.position.set(arch.x, 0, arch.z);
        group.rotation.y = Math.random() * Math.PI * 2;
        this.scene.add(group);

        return {
            mesh: group,
            ...arch,
            assignment,
            visited: false,
            walkTime: Math.random() * 10,
            wanderTarget: { x: arch.x, z: arch.z },
            baseX: arch.x,
            baseZ: arch.z,
            talkIcon: sprite,
            leftHip, rightHip, leftShoulder, rightShoulder
        };
    },

    createDialogUI() {
        const dialog = document.createElement('div');
        dialog.id = 'npc-dialog';
        dialog.style.cssText = `
            display:none; position:fixed; bottom:140px; left:50%; transform:translateX(-50%);
            width:420px; max-width:92vw;
            background:linear-gradient(135deg, rgba(15,23,42,0.97), rgba(30,41,59,0.97));
            backdrop-filter:blur(16px); border:1px solid rgba(255,255,255,0.15);
            border-radius:18px; padding:20px 24px; z-index:55;
            color:#fff; font-family:'Inter',sans-serif;
            box-shadow:0 12px 50px rgba(0,0,0,0.7);
            animation:msgIn 0.3s ease;
        `;
        dialog.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                <div id="npc-name" style="font-size:14px; font-weight:800; color:#60a5fa; letter-spacing:1px;"></div>
                <button id="npc-close" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;padding:4px;">✕</button>
            </div>
            <div id="npc-text" style="font-size:14px; line-height:1.6; color:#e2e8f0;"></div>
            <div id="npc-hint-box" style="display:none; margin-top:12px; padding:10px 14px; background:rgba(251,191,36,0.1); border:1px solid rgba(251,191,36,0.4); border-radius:10px; font-size:13px; color:#fbbf24; font-weight:600;"></div>
            <div style="margin-top:14px; text-align:right;">
                <button id="npc-ok" style="
                    padding:9px 22px; border:none; border-radius:18px;
                    background:linear-gradient(135deg,#3b82f6,#2563eb);
                    color:#fff; font-size:13px; font-weight:700; cursor:pointer;
                    font-family:'Inter',sans-serif; letter-spacing:1px;
                ">알겠어요</button>
            </div>
        `;
        document.body.appendChild(dialog);
        document.getElementById('npc-close').addEventListener('click', () => this.closeDialog());
        document.getElementById('npc-ok').addEventListener('click', () => this.closeDialog());
    },

    _collidesWithBuilding(x, z) {
        // citypack 모드: GLB 충돌 박스 사용 (마진 0.3)
        if (window._citypackCollision) {
            const r = 0.3;
            for (const b of window._citypackCollision) {
                if (x + r > b.minX && x - r < b.maxX
                 && z + r > b.minZ && z - r < b.maxZ) return true;
            }
            return false;
        }
        if (!window._buildingPositions) return false;
        const r = 0.5;
        for (const b of window._buildingPositions) {
            if (Math.abs(x - b.x) < b.w / 2 + r && Math.abs(z - b.z) < b.d / 2 + r) return true;
        }
        return false;
    },

    _tryMove(npc, dx, dz) {
        const nx = npc.mesh.position.x + dx;
        const nz = npc.mesh.position.z + dz;
        // citypack 모드는 도시 경계, 절차적은 WORLD_SIZE
        let cx, cz;
        if (window._citypackBounds) {
            const b = window._citypackBounds;
            cx = Math.max(b.minX + 2, Math.min(b.maxX - 2, nx));
            cz = Math.max(b.minZ + 2, Math.min(b.maxZ - 2, nz));
        } else {
            const half = WORLD_SIZE / 2 - 2;
            cx = Math.max(-half, Math.min(half, nx));
            cz = Math.max(-half, Math.min(half, nz));
        }
        if (!this._collidesWithBuilding(cx, cz)) {
            npc.mesh.position.x = cx;
            npc.mesh.position.z = cz;
        } else if (!this._collidesWithBuilding(cx, npc.mesh.position.z)) {
            npc.mesh.position.x = cx;
        } else if (!this._collidesWithBuilding(npc.mesh.position.x, cz)) {
            npc.mesh.position.z = cz;
        }
    },

    update(playerPos, delta, time) {
        if (!gameState.isDay) {
            // Night: civilians hide. All suspects visible PLUS extra wanted appear.
            this.npcs.forEach((npc, i) => {
                if (npc.role === 'civilian') {
                    npc.mesh.visible = false;
                } else {
                    npc.mesh.visible = !npc.caught;
                }
            });
            // Extra: spawn additional roving wanted suspects at night
            this._spawnNightExtras();
        } else {
            // Day: suspects 약 33%만 노출, 시민은 항상 보임
            this.npcs.forEach((npc, i) => {
                if (npc.role === 'civilian') {
                    npc.mesh.visible = !npc.caught;
                } else {
                    if (npc._dayVisible === undefined) npc._dayVisible = (i % 3 === 0);
                    npc.mesh.visible = !npc.caught && npc._dayVisible;
                }
            });
            // Hide night extras
            this._hideNightExtras();
        }
        // Common: find nearest visible NPC for interaction

        this.nearbyNpc = null;
        let nearest = null;
        let minDist = this.interactDistance;

        this.npcs.forEach(npc => {
            if (npc.caught || !npc.mesh.visible) return;

            // GLB NPC: 매 프레임 mixer 진행
            if (npc.mesh.userData.mixer) {
                npc.mesh.userData.mixer.update(delta);
            }

            const dx = playerPos.x - npc.mesh.position.x;
            const dz = playerPos.z - npc.mesh.position.z;
            const d = Math.sqrt(dx * dx + dz * dz);

            // Civilians: don't flee, just wander idly. Talk via T button.
            if (npc.role === 'civilian') {
                // Light wander
                npc.walkTime += delta;
                if (npc.walkTime > 5 + Math.random() * 5) {
                    const tx = npc.baseX + (Math.random() - 0.5) * 4;
                    const tz = npc.baseZ + (Math.random() - 0.5) * 4;
                    npc.wanderTarget = this._findSafePosition(tx, tz);
                    npc.walkTime = 0;
                }
                const tdx = npc.wanderTarget.x - npc.mesh.position.x;
                const tdz = npc.wanderTarget.z - npc.mesh.position.z;
                const td = Math.sqrt(tdx * tdx + tdz * tdz);
                if (td > 0.4) {
                    this._tryMove(npc, (tdx / td) * 0.35 * delta, (tdz / td) * 0.35 * delta);
                    npc.mesh.rotation.y = Math.atan2(tdx, tdz);
                    this._setAnimState(npc.mesh, 'walk');
                    // 절차적 폴백 swing
                    const swing = Math.sin(time * 3.5) * 0.3;
                    if (npc.leftHip) npc.leftHip.rotation.x = swing;
                    if (npc.rightHip) npc.rightHip.rotation.x = -swing;
                    if (npc.leftShoulder) npc.leftShoulder.rotation.x = -swing * 0.5;
                    if (npc.rightShoulder) npc.rightShoulder.rotation.x = swing * 0.5;
                } else {
                    this._setAnimState(npc.mesh, 'idle');
                }
                if (d < minDist) { minDist = d; nearest = npc; }
                return;
            }

            // Suspect: detect & flee from player
            if (d < this.detectDistance) {
                // Flee — speed based on assigned criminal difficulty
                const crimId = npc.assignment ? npc.assignment.criminal : 0;
                const speed = this.fleeSpeeds[crimId] || 0.05;
                if (d > 0.01) {
                    let fx = -(dx / d);
                    let fz = -(dz / d);
                    this._tryMove(npc, fx * speed * delta * 60, fz * speed * delta * 60);
                    npc.mesh.rotation.y = Math.atan2(fx, fz);
                }
                this._setAnimState(npc.mesh, 'run');
                // 절차적 폴백 swing + bob
                const swing = Math.sin(time * 10) * 0.6;
                const bob = Math.abs(Math.sin(time * 10)) * 0.04;
                // GLB NPC는 mixer가 Y를 관리하므로 bob 적용 안 함
                if (!npc.mesh.userData.mixer) npc.mesh.position.y = bob;
                if (npc.leftHip) npc.leftHip.rotation.x = swing;
                if (npc.rightHip) npc.rightHip.rotation.x = -swing;
                if (npc.leftShoulder) npc.leftShoulder.rotation.x = -swing * 1.1;
                if (npc.rightShoulder) npc.rightShoulder.rotation.x = swing * 1.1;
            } else {
                // Wander
                npc.walkTime += delta;
                if (npc.walkTime > 4 + Math.random() * 4) {
                    const tx = npc.baseX + (Math.random() - 0.5) * 6;
                    const tz = npc.baseZ + (Math.random() - 0.5) * 6;
                    npc.wanderTarget = this._findSafePosition(tx, tz);
                    npc.walkTime = 0;
                }
                const tdx = npc.wanderTarget.x - npc.mesh.position.x;
                const tdz = npc.wanderTarget.z - npc.mesh.position.z;
                const td = Math.sqrt(tdx * tdx + tdz * tdz);
                if (td > 0.3) {
                    const speed = 0.4;
                    this._tryMove(npc, (tdx / td) * speed * delta, (tdz / td) * speed * delta);
                    npc.mesh.rotation.y = Math.atan2(tdx, tdz);
                    this._setAnimState(npc.mesh, 'walk');
                    const swing = Math.sin(time * 4) * 0.3;
                    if (npc.leftHip) npc.leftHip.rotation.x = swing;
                    if (npc.rightHip) npc.rightHip.rotation.x = -swing;
                    if (npc.leftShoulder) npc.leftShoulder.rotation.x = -swing * 0.5;
                    if (npc.rightShoulder) npc.rightShoulder.rotation.x = swing * 0.5;
                } else {
                    this._setAnimState(npc.mesh, 'idle');
                    if (npc.leftHip) npc.leftHip.rotation.x *= 0.85;
                    if (npc.rightHip) npc.rightHip.rotation.x *= 0.85;
                }
            }

            // Head indicators removed by design

            if (d < minDist) {
                minDist = d;
                nearest = npc;
            }
        });

        this.nearbyNpc = nearest;

        // Civilian: direct talk on proximity. Suspect: trigger minigame.
        if (nearest && !this.dialogOpen) {
            if (nearest.role === 'civilian') {
                this.talkCivilian(nearest);
            } else {
                this.tryCatchSuspect(nearest);
            }
        }
    },

    tryCatchSuspect(npc) {
        if (npc.caught || npc._inMinigame) return;
        // If Minigame is busy or paused, defer
        if (typeof Minigame === 'undefined' || Minigame.active || gameState.isPaused) return;
        npc._inMinigame = true;
        // Use Minigame.startSuspectMinigame (easier mode)
        Minigame.startSuspectMinigame(npc, (success) => {
            npc._inMinigame = false;
            if (success) this.catch(npc);
            else {
                // Escape: relocate
                const ang = Math.random() * Math.PI * 2;
                npc.mesh.position.x = npc.baseX + Math.cos(ang) * 6;
                npc.mesh.position.z = npc.baseZ + Math.sin(ang) * 6;
            }
        });
    },

    talkCivilian(npc) {
        if (npc.visited) return; // only first encounter shows full hint
        npc.visited = true;
        document.getElementById('npc-name').textContent = '👤 ' + npc.name;
        document.getElementById('npc-text').textContent = npc.story || '안녕하세요 형사님.';

        const hintBox = document.getElementById('npc-hint-box');
        if (npc.assignment) {
            const colors = ['#ef4444', '#f97316', '#a855f7'];
            const names = HintSystem.criminalNames;
            hintBox.style.display = 'block';
            hintBox.style.borderColor = colors[npc.assignment.criminal];
            hintBox.style.color = colors[npc.assignment.criminal];
            hintBox.innerHTML = `<div style="font-size:11px; opacity:0.7; margin-bottom:4px;">${names[npc.assignment.criminal]}</div>"${npc.assignment.text}"`;
            HintSystem.collectHintFromNPC(npc.assignment.criminal, npc.assignment.order, npc.assignment.text);
        } else {
            hintBox.style.display = 'none';
        }
        document.getElementById('npc-dialog').style.display = 'block';
        this.dialogOpen = true;
        // Civilians do NOT pay — only suspects (per gameplay design)
        if (typeof SoundManager !== 'undefined') SoundManager.playSFX('collect');
    },

    catch(npc) {
        if (npc.caught) return;
        npc.caught = true;
        document.getElementById('npc-name').textContent = '🚨 수배범 검거: ' + npc.name;

        const hintBox = document.getElementById('npc-hint-box');
        if (npc.assignment) {
            document.getElementById('npc-text').textContent = '항복합니다! 제가 아는 걸 말씀드릴게요...';
            const colors = ['#ef4444', '#f97316', '#a855f7'];
            const names = HintSystem.criminalNames;
            hintBox.style.display = 'block';
            hintBox.style.borderColor = colors[npc.assignment.criminal];
            hintBox.style.color = colors[npc.assignment.criminal];
            hintBox.innerHTML = `<div style="font-size:11px; opacity:0.7; margin-bottom:4px;">${names[npc.assignment.criminal]}</div>"${npc.assignment.text}"`;
            HintSystem.collectHintFromNPC(npc.assignment.criminal, npc.assignment.order, npc.assignment.text);
        } else {
            document.getElementById('npc-text').textContent = '항복합니다... 죄송합니다.';
            hintBox.style.display = 'none';
        }

        document.getElementById('npc-dialog').style.display = 'block';
        this.dialogOpen = true;
        // Suspect bounty: +25 coins on successful catch
        const reward = 25;
        gameState.coins += reward;
        try { showMessage('💰 수배범 검거 보수: +' + reward + ' 코인'); } catch(e) {}
        if (typeof SoundManager !== 'undefined') SoundManager.playSFX('arrest_success');
    },

    talk() {
        if (this.nearbyNpc) this.catch(this.nearbyNpc);
    },

    closeDialog() {
        document.getElementById('npc-dialog').style.display = 'none';
        this.dialogOpen = false;
    }
};
