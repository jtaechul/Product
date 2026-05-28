// npc.js — 수배범 NPC (도망가는 정보원, 잡으면 힌트 제공)

const NPCSystem = {
    npcs: [],
    interactDistance: 1.5,  // catch distance (closer for catch mechanic)
    nearbyNpc: null,
    dialogOpen: false,
    detectDistance: 12,
    // Speeds — must be slower than corresponding criminal flee speeds
    // criminal flee speeds: 1호=0.06, 2호=0.09, 3호=0.13
    fleeSpeeds: [0.04, 0.065, 0.09],

    init(scene) {
        this.scene = scene;
        this.createDialogUI();
        this.distributeHints();
        this.spawnNPCs();
    },

    distributeHints() {
        // Build list of (criminal, order, text) tuples
        this.hintAssignments = [];
        const hintTexts = HintSystem.hintTexts;
        for (let c = 0; c < 3; c++) {
            const texts = hintTexts[c];
            const required = HintSystem.hintsRequired[c];
            for (let o = 0; o < required; o++) {
                this.hintAssignments.push({ criminal: c, order: o, text: texts[o] });
            }
        }
    },

    npcArchetypes: [
        // Spread across zones
        { x: -25, z: 72, name: '카페 점원',     hair: 0x4a2510, skin: 0xffdbac, clothing: 0xff6b9d, zone: 'POLICE' },
        { x: 25, z: 72, name: '편의점 알바',    hair: 0x1a0a00, skin: 0xf5d5b8, clothing: 0x60a5fa, zone: 'POLICE' },
        { x: -30, z: 25, name: '주민 김씨',     hair: 0x2a1808, skin: 0xfff2dc, clothing: 0x9b8b9d, zone: 'RESIDENTIAL' },
        { x: -70, z: -25, name: '학생 이씨',    hair: 0x4a2510, skin: 0xffdbac, clothing: 0xfbbf24, zone: 'RESIDENTIAL' },
        { x: -110, z: 20, name: '아주머니 박씨', hair: 0x1a0a00, skin: 0xf5d5b8, clothing: 0xe05080, zone: 'RESIDENTIAL' },
        { x: -25, z: -25, name: '할아버지 최씨', hair: 0xdddddd, skin: 0xefcfa8, clothing: 0x718096, zone: 'RESIDENTIAL' },
        { x: 30, z: 25, name: '직장인 정씨',    hair: 0x1a0a00, skin: 0xffdbac, clothing: 0x1e3a8a, zone: 'COMMERCIAL' },
        { x: 75, z: -10, name: '학생 윤씨',     hair: 0x4a2510, skin: 0xf5d5b8, clothing: 0x06c167, zone: 'COMMERCIAL' },
        { x: 110, z: 20, name: '바리스타',      hair: 0x2a1808, skin: 0xfff2dc, clothing: 0x8b4513, zone: 'COMMERCIAL' },
        { x: 30, z: -60, name: '경비원 한씨',   hair: 0x222222, skin: 0xefcfa8, clothing: 0x2d3748, zone: 'COMMERCIAL' },
        { x: -50, z: -110, name: '근로자 송씨', hair: 0x1a0a00, skin: 0xddaa88, clothing: 0xff8800, zone: 'FACTORY' },
        { x: 30, z: -110, name: '공장장 조씨',  hair: 0x444444, skin: 0xffdbac, clothing: 0x4a5568, zone: 'FACTORY' },
    ],

    spawnNPCs() {
        // Shuffle hint assignments for randomness
        const assignments = [...this.hintAssignments];
        for (let i = assignments.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [assignments[i], assignments[j]] = [assignments[j], assignments[i]];
        }

        this.npcArchetypes.forEach((arch, i) => {
            const assignment = assignments[i] || null;
            const npc = this.createNPCMesh(arch, assignment);
            this.npcs.push(npc);
        });
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

        // === Wanted indicator (red circle with !) ===
        const cv = document.createElement('canvas');
        cv.width = 64; cv.height = 64;
        const ctx = cv.getContext('2d');
        ctx.fillStyle = 'rgba(239,68,68,0.95)';
        ctx.beginPath();
        ctx.arc(32, 30, 22, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 36px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('!', 32, 30);
        const tex = new THREE.CanvasTexture(cv);
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
        sprite.scale.set(0.4, 0.4, 1);
        sprite.position.y = headY + 0.5;
        sprite.userData.talkIcon = true;
        group.add(sprite);

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

    update(playerPos, delta, time) {
        if (!gameState.isDay) {
            // Hide all suspects at night
            this.npcs.forEach(npc => { npc.mesh.visible = false; });
            return;
        }

        this.nearbyNpc = null;
        let nearest = null;
        let minDist = this.interactDistance;

        this.npcs.forEach(npc => {
            if (npc.caught) {
                npc.mesh.visible = false;
                return;
            }
            npc.mesh.visible = true;

            const dx = playerPos.x - npc.mesh.position.x;
            const dz = playerPos.z - npc.mesh.position.z;
            const d = Math.sqrt(dx * dx + dz * dz);

            // Behavior: detect & flee from player
            if (d < this.detectDistance) {
                // Flee — speed based on assigned criminal difficulty
                const crimId = npc.assignment ? npc.assignment.criminal : 0;
                const speed = this.fleeSpeeds[crimId] || 0.05;
                if (d > 0.01) {
                    let fx = -(dx / d);
                    let fz = -(dz / d);
                    // Clamp to world bounds
                    const nx = npc.mesh.position.x + fx * speed * delta * 60;
                    const nz = npc.mesh.position.z + fz * speed * delta * 60;
                    const half = WORLD_SIZE / 2 - 2;
                    npc.mesh.position.x = Math.max(-half, Math.min(half, nx));
                    npc.mesh.position.z = Math.max(-half, Math.min(half, nz));
                    npc.mesh.rotation.y = Math.atan2(fx, fz);
                }
                // Run animation
                const swing = Math.sin(time * 10) * 0.55;
                if (npc.leftHip) npc.leftHip.rotation.x = swing;
                if (npc.rightHip) npc.rightHip.rotation.x = -swing;
                if (npc.leftShoulder) npc.leftShoulder.rotation.x = -swing;
                if (npc.rightShoulder) npc.rightShoulder.rotation.x = swing;
            } else {
                // Wander
                npc.walkTime += delta;
                if (npc.walkTime > 4 + Math.random() * 4) {
                    npc.wanderTarget = {
                        x: npc.baseX + (Math.random() - 0.5) * 6,
                        z: npc.baseZ + (Math.random() - 0.5) * 6
                    };
                    npc.walkTime = 0;
                }
                const tdx = npc.wanderTarget.x - npc.mesh.position.x;
                const tdz = npc.wanderTarget.z - npc.mesh.position.z;
                const td = Math.sqrt(tdx * tdx + tdz * tdz);
                if (td > 0.3) {
                    const speed = 0.4;
                    npc.mesh.position.x += (tdx / td) * speed * delta;
                    npc.mesh.position.z += (tdz / td) * speed * delta;
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

            // Talk icon visibility
            if (npc.talkIcon) {
                npc.talkIcon.visible = true;
                npc.talkIcon.scale.setScalar(0.4 + Math.sin(time * 3) * 0.05);
            }

            if (d < minDist) {
                minDist = d;
                nearest = npc;
            }
        });

        this.nearbyNpc = nearest;

        // Auto-catch when very close — no button needed
        if (nearest && !this.dialogOpen) {
            this.catch(nearest);
        }
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
        gameState.coins += 5;
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
