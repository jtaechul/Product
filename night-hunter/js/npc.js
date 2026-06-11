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

    // 여자로 판별할 NPC 이름 (그 외는 남자 → npc-man.glb 적용).
    // 잘못 분류된 게 있으면 이 목록만 고치면 된다.
    _femaleNPCNames: new Set([
        '카페 점원 민지', '학생 이지수', '아주머니 박씨', '주민회 회장 정혜영',
        '동네 슈퍼 이모', '학생 윤서연', '바리스타 다은', '꽃집 사장 미영', '경리 이수민'
    ]),
    _isMaleNPC(arch) { return !this._femaleNPCNames.has(arch.name); },

    init(scene) {
        this.scene = scene;
        this.createDialogUI();
        this.distributeHints();
        this.spawnNPCs();
        this._applyManModels();
    },

    // NPC를 GLB 모델로 업그레이드 (ChibiCharacter 로드 완료 후)
    _applyManModels() {
        if (typeof ChibiCharacter === 'undefined' || !ChibiCharacter.preload) return;
        ChibiCharacter.preload().then(() => {
            this.npcs.forEach(npc => this._upgradeNpcToMan(npc));
        }).catch(() => {});
    },

    // NPC 역할/성별에 따른 GLB 메시 선택: 수배범(suspect)→suspect, 남자 시민→npc-man, 여자 시민→woman
    // (진짜 납치범 3명은 enemy.js에서 kidnapper 적용)
    _npcMeshName(npc) {
        if (npc.role === 'suspect') return 'suspect';
        if (this._isMaleNPC(npc)) return 'npc-man';
        return 'woman';
    },

    // GLB NPC 애니메이션 구동 (이동→walk/run, 정지→idle)
    // dist: 플레이어와의 거리 — 멀면 본 계산(mixer) 스킵해 모바일 CPU 절약
    _driveGlbAnim(npc, delta, state, dist) {
        const glb = npc._glb;
        if (!glb) return;
        if (state !== npc._glbState) { try { glb.setState(state); } catch (e) {} npc._glbState = state; }
        if (!npc.mesh.visible) return;
        if (dist !== undefined && dist > 45) return;   // 원거리: 포즈 갱신 생략 (시각 차이 없음)
        try { glb.update(delta); } catch (e) {}
    },

    _upgradeNpcToMan(npc) {
        if (!npc || npc._glb) return;
        if (typeof ChibiCharacter === 'undefined' || !ChibiCharacter.upgradeHost) return;
        const inst = ChibiCharacter.upgradeHost(npc.mesh, this._npcMeshName(npc));
        if (inst) { npc._glb = inst; npc._glbState = null; }
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
        // 스토리: 평내동 인신매매 조직 + 3명의 납치범 (길동/철수/영수) 추적
        // ── 경찰서 주변 (POLICE zone) ──
        { x: -25, z: 72, name: '카페 점원 민지', role: 'civilian',
          hair: 0x4a2510, skin: 0xffdbac, clothing: 0xff6b9d, zone: 'POLICE',
          story: '형사님 오셨군요. 오늘 아침에 가게에 무서운 손님이 왔어요. 안경 쓴 40대 남자가 아이 사진을 들고 와서 본 적 있냐고 물어보더라구요. 분명히 그 사람이 길동이에요.' },
        { x: 25, z: 72, name: '편의점 알바 호석', role: 'civilian',
          hair: 0x1a0a00, skin: 0xf5d5b8, clothing: 0x60a5fa, zone: 'POLICE',
          story: '늦은 밤 자주 오는 손님이 있어요. 항상 모자를 깊게 눌러쓰고, 검은 정장에 흉터가 있어요. 카드를 안 쓰고 늘 현금만 내고 가요. 뭔가 수상해요.' },
        { x: -70, z: 70, name: '공원 산책 어르신 정씨', role: 'civilian',
          hair: 0xcccccc, skin: 0xefcfa8, clothing: 0x556677, zone: 'POLICE',
          story: '평내동에 30년 살았는데, 요즘처럼 무서운 적이 없어요. 어제 새벽에 검은색 트럭이 우리 단지 앞을 지나갔어요. 공장 쪽으로 가더라구요.' },
        { x: 70, z: 70, name: '신문 배달원 영찬', role: 'civilian',
          hair: 0x222222, skin: 0xffdbac, clothing: 0xee9933, zone: 'POLICE',
          story: '새벽에 신문 돌리다 보면 별의별 걸 다 봐요. 로데오 거리 어떤 상가 지하에서 비명 소리가 들린 적이 있어요. 무서워서 그냥 도망쳤어요.' },
        // ── 주거지구 (RESIDENTIAL) ──
        { x: -30, z: 25, name: '주민 김씨', role: 'suspect',
          hair: 0x2a1808, skin: 0xfff2dc, clothing: 0x9b8b9d, zone: 'RESIDENTIAL',
          story: '저는... 그냥 살려고 했을 뿐이에요. 시키는 대로 했을 뿐...' },
        { x: -70, z: -25, name: '학생 이지수', role: 'civilian',
          hair: 0x4a2510, skin: 0xffdbac, clothing: 0xfbbf24, zone: 'RESIDENTIAL',
          story: '학교 가는 길에 이상한 차가 자주 서있었어요. 운전석에 안경 쓴 아저씨가 있었는데, 학교 앞에서 우리를 빤히 쳐다봤어요. 너무 무서워요.' },
        { x: -110, z: 20, name: '아주머니 박씨', role: 'civilian',
          hair: 0x1a0a00, skin: 0xf5d5b8, clothing: 0xe05080, zone: 'RESIDENTIAL',
          story: '우리 동네에서 아이들이 두 명이나 사라졌어요. 형사님, 꼭 찾아주세요. 저쪽 큰 아파트 단지에서 밤마다 이상한 소리가 들린다는 얘기가 돌아요.' },
        { x: -25, z: -25, name: '할아버지 최씨', role: 'suspect',
          hair: 0xdddddd, skin: 0xefcfa8, clothing: 0x718096, zone: 'RESIDENTIAL',
          story: '항복합니다... 솔직히 말씀드릴게요...' },
        { x: -110, z: -25, name: '주민회 회장 정혜영', role: 'civilian',
          hair: 0x2a1808, skin: 0xffdbac, clothing: 0xcc4488, zone: 'RESIDENTIAL',
          story: '아파트 CCTV 영상을 확인해 봤어요. 회색 코트의 남자가 새벽 3시쯤 우리 단지 안으로 들어갔어요. 동 입구에서 사라졌는데, 어느 동인지 정확히 기억해요.' },
        { x: -90, z: -60, name: '택배 기사 김태수', role: 'civilian',
          hair: 0x1a0a00, skin: 0xddaa88, clothing: 0xff5522, zone: 'RESIDENTIAL',
          story: '저 단지 사람들이요, 한 호수만 이상하게 택배를 받아도 답이 없어요. 벨 누르면 잠깐 후에 문 사이로 손만 쑥 나와요. 얼굴을 절대 안 보여줘요.' },
        { x: -30, z: -65, name: '경비실 이씨 아저씨', role: 'civilian',
          hair: 0x555555, skin: 0xefcfa8, clothing: 0x2d3748, zone: 'RESIDENTIAL',
          story: '경비실에서 야간 근무하면서 의심스러운 출입자 다 기록해놨어요. 안경 쓴 40대 남자가 자주 들락날락하는데, 가끔 큰 가방을 들고 와요. 한밤중에도요.' },
        { x: -70, z: -65, name: '동네 슈퍼 이모', role: 'civilian',
          hair: 0x4a2510, skin: 0xfff2dc, clothing: 0x4080cc, zone: 'RESIDENTIAL',
          story: '아침마다 그 안경잡이가 와서 라면이랑 빵을 한 가득 사가요. 혼자 사는 사람이 그렇게 많이 사? 집에 누구를 가둬놨나 의심스러워요.' },
        // ── 상업지구 (COMMERCIAL) ──
        { x: 30, z: 25, name: '직장인 정현우', role: 'civilian',
          hair: 0x1a0a00, skin: 0xffdbac, clothing: 0x1e3a8a, zone: 'COMMERCIAL',
          story: '퇴근길에 본 게 있어요. 검은 정장의 남자가 아이를 끌고 가는 모습을... 로데오 거리 한 가게로 들어갔어요. 간판이 분명히 기억나요.' },
        { x: 75, z: -10, name: '학생 윤서연', role: 'suspect',
          hair: 0x4a2510, skin: 0xf5d5b8, clothing: 0x06c167, zone: 'COMMERCIAL',
          story: '죄송해요... 돈이 필요해서 그랬어요...' },
        { x: 110, z: 20, name: '바리스타 다은', role: 'civilian',
          hair: 0x2a1808, skin: 0xfff2dc, clothing: 0x8b4513, zone: 'COMMERCIAL',
          story: '카페에 자주 오는 손님이 있어요. 검은 정장에 흉터가 있는 남자. 매일 같은 자리에 앉아서 누군가와 통화하는데, "물건 옮겨", "처리해" 같은 말을 해요.' },
        { x: 30, z: -60, name: '경비원 한대수', role: 'suspect',
          hair: 0x222222, skin: 0xefcfa8, clothing: 0x2d3748, zone: 'COMMERCIAL',
          story: '저도 그자에게 협박당했어요. 모든 걸 말씀드릴게요...' },
        { x: 110, z: -30, name: '가게 사장 강민호', role: 'civilian',
          hair: 0x222222, skin: 0xddaa88, clothing: 0x884444, zone: 'COMMERCIAL',
          story: '제 옆 가게요, 낮에는 정상 영업하는 척하는데 밤만 되면 다른 가게가 돼요. 손님이 들어갔다 나오는데 다 표정이 이상해요. 술집 같지도 않은데 새벽 4시까지 불이 켜져 있어요.' },
        { x: 30, z: -10, name: '청소부 황씨', role: 'civilian',
          hair: 0x555555, skin: 0xefcfa8, clothing: 0x44aa44, zone: 'COMMERCIAL',
          story: '새벽에 로데오 거리를 청소하다 보면 가끔 검은 봉투에 담긴 물건들이 가게 뒷문으로 옮겨져요. 흉터 있는 남자가 직접 옮기더라구요. 무서워서 못 본 척했어요.' },
        { x: 75, z: -70, name: '꽃집 사장 미영', role: 'civilian',
          hair: 0x4a2510, skin: 0xffdbac, clothing: 0xff88aa, zone: 'COMMERCIAL',
          story: '그 흉터남이 우리 가게에 와서 꽃 시켰는데, 카드 안 받고 무조건 현금만 내요. 영수증도 거부하더라구요. 모든 게 너무 비밀스러워요.' },
        // ── 공업지구 (FACTORY) ──
        { x: -65, z: -110, name: '근로자 송기철', role: 'civilian',
          hair: 0x1a0a00, skin: 0xddaa88, clothing: 0xff8800, zone: 'FACTORY',
          story: '공장에서 일하다가 본 게 있어요. 밤마다 같은 트럭들이 들락날락해요. 짐칸이 무거워 보이는데 정작 화물 서류는 비어있어요. 그 회사 사장이 60대 험상궂은 남자예요.' },
        { x: 30, z: -110, name: '공장장 조경석', role: 'suspect',
          hair: 0x444444, skin: 0xffdbac, clothing: 0x4a5568, zone: 'FACTORY',
          story: '저 사실은... 그 조직의 일원이었어요. 다 말씀드릴게요...' },
        { x: -115, z: -125, name: '용접공 박철민', role: 'civilian',
          hair: 0x222222, skin: 0xc8a878, clothing: 0xaa7733, zone: 'FACTORY',
          story: '제가 일하는 공장 옆에 이상한 공장이 있어요. 양각으로 회사 이름이 큼지막하게 박혀있는데, 거기 직원은 거의 안 보여요. 굴뚝에선 연기만 펑펑 나는데 정작 생산하는 건 없어요.' },
        { x: 80, z: -125, name: '트럭 운전기사 윤형식', role: 'civilian',
          hair: 0x666666, skin: 0xddaa88, clothing: 0x55aaee, zone: 'FACTORY',
          story: '여기서 트럭 몰면서 봤어요. 그 공장 뒷문에서 가끔 작은 화물칸에서 사람 소리 같은 게 들렸어요. 한밤중에요. 신고하려다 협박당해서 입을 닫고 있었어요.' },
        { x: -30, z: -125, name: '경리 이수민', role: 'civilian',
          hair: 0x2a1808, skin: 0xffdbac, clothing: 0xaa66cc, zone: 'FACTORY',
          story: '회계 장부를 보면 그 공장 매출이 너무 비정상이에요. 생산 기록은 거의 없는데 매달 거액이 들어와요. 입금 출처는 다 다른 명의의 차명 계좌예요.' },
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
                x: safe.x, z: safe.z, role: 'suspect', isGeneralSuspect: true,
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
            this._upgradeNpcToMan(npc);   // 밤 수배범도 남자면 npc-man 적용
        });
    },

    _hideNightExtras() {
        if (!this._nightExtras) return;
        this._nightExtras.forEach(e => { e.mesh.visible = false; });
    },

    _findSafePosition(x, z) {
        // 1) 도로 위에 spawn 되면 가까운 인도 방향으로 push (최대 8회, 매번 7m)
        if (typeof window.isOnRoadAsphalt === 'function') {
            let cx = x, cz = z;
            for (let pass = 0; pass < 8; pass++) {
                if (!window.isOnRoadAsphalt(cx, cz, 0.3)) break;
                // z 우선 push (H 도로는 ±z 로 빠져나감), 안 되면 x push 도 시도
                cz += (cz >= 0 ? 7 : -7);
                if (window.isOnRoadAsphalt(cx, cz, 0.3)) {
                    cx += (cx >= 0 ? 7 : -7);
                }
            }
            x = cx; z = cz;
        }
        // 2) 빌딩 안에 있으면 외부로 push
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
        if (!window._buildingPositions) return false;
        const r = 0.5;
        for (const b of window._buildingPositions) {
            if (Math.abs(x - b.x) < b.w / 2 + r && Math.abs(z - b.z) < b.d / 2 + r) return true;
        }
        return false;
    },

    // 도로 회피 — NPC 는 인도/공원에서만 다닌다 (task 2)
    _isBlockedForNpc(x, z) {
        if (this._collidesWithBuilding(x, z)) return true;
        if (typeof window.isOnRoadAsphalt === 'function' && window.isOnRoadAsphalt(x, z, 0.3)) return true;
        return false;
    },

    _tryMove(npc, dx, dz) {
        const nx = npc.mesh.position.x + dx;
        const nz = npc.mesh.position.z + dz;
        const half = WORLD_SIZE / 2 - 2;
        const cx = Math.max(-half, Math.min(half, nx));
        const cz = Math.max(-half, Math.min(half, nz));
        if (!this._isBlockedForNpc(cx, cz)) {
            npc.mesh.position.x = cx;
            npc.mesh.position.z = cz;
        } else if (!this._isBlockedForNpc(cx, npc.mesh.position.z)) {
            npc.mesh.position.x = cx;
        } else if (!this._isBlockedForNpc(npc.mesh.position.x, cz)) {
            npc.mesh.position.z = cz;
        }
    },

    update(playerPos, delta, time) {
        // 매 프레임 GLB 미적용 NPC 보정 — 로딩 타이밍/누락으로 절차적 NPC가 남지 않게 함
        for (let i = 0; i < this.npcs.length; i++) if (!this.npcs[i]._glb) this._upgradeNpcToMan(this.npcs[i]);

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
                    const swing = Math.sin(time * 3.5) * 0.3;
                    if (npc.leftHip) npc.leftHip.rotation.x = swing;
                    if (npc.rightHip) npc.rightHip.rotation.x = -swing;
                    if (npc.leftShoulder) npc.leftShoulder.rotation.x = -swing * 0.5;
                    if (npc.rightShoulder) npc.rightShoulder.rotation.x = swing * 0.5;
                }
                if (npc._glb) this._driveGlbAnim(npc, delta, td > 0.4 ? 'walk' : 'idle', d);
                if (d < minDist) { minDist = d; nearest = npc; }
                return;
            }

            // Suspect: detect & flee from player
            let glbState = 'idle';
            if (d < this.detectDistance) {
                glbState = 'run';
                // Flee — speed based on assigned criminal difficulty
                const crimId = npc.assignment ? npc.assignment.criminal : 0;
                const speed = this.fleeSpeeds[crimId] || 0.05;
                if (d > 0.01) {
                    let fx = -(dx / d);
                    let fz = -(dz / d);
                    this._tryMove(npc, fx * speed * delta * 60, fz * speed * delta * 60);
                    npc.mesh.rotation.y = Math.atan2(fx, fz);
                }
                // Run animation with subtle bob
                const swing = Math.sin(time * 10) * 0.6;
                const bob = Math.abs(Math.sin(time * 10)) * 0.04;
                npc.mesh.position.y = bob;
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
                glbState = td > 0.3 ? 'walk' : 'idle';
                if (td > 0.3) {
                    const speed = 0.4;
                    this._tryMove(npc, (tdx / td) * speed * delta, (tdz / td) * speed * delta);
                    npc.mesh.rotation.y = Math.atan2(tdx, tdz);
                    const swing = Math.sin(time * 4) * 0.3;
                    if (npc.leftHip) npc.leftHip.rotation.x = swing;
                    if (npc.rightHip) npc.rightHip.rotation.x = -swing;
                    if (npc.leftShoulder) npc.leftShoulder.rotation.x = -swing * 0.5;
                    if (npc.rightShoulder) npc.rightShoulder.rotation.x = swing * 0.5;
                } else {
                    if (npc.leftHip) npc.leftHip.rotation.x *= 0.85;
                    if (npc.rightHip) npc.rightHip.rotation.x *= 0.85;
                }
            }

            if (npc._glb) this._driveGlbAnim(npc, delta, glbState, d);

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
