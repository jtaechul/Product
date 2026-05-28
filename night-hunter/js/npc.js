// npc.js — 시민 NPC 시스템

const NPCSystem = {
    npcs: [],
    interactDistance: 2.5,
    nearbyNpc: null,
    dialogOpen: false,

    npcData: [
        { x: -20, z: 70, color: 0xff6b9d, name: '카페 점원',
          tip: '주택가에 빨간 우체통이 있는 파란 집을 본 적이 있어요...', criminal: 0 },
        { x: 30, z: 88, color: 0x8b9dc3, name: '학생',
          tip: 'CAFE 간판이 있는 흰색 건물에서 이상한 사람을 봤어요!', criminal: 1 },
        { x: -60, z: 35, color: 0x9b8b9d, name: '주민',
          tip: '주택가 어딘가에서 비명소리가 들렸어요...', criminal: 0 },
        { x: 90, z: 20, color: 0xa0aec0, name: '직장인',
          tip: '상업지구 5층짜리 건물에 수상한 사람들이 드나들어요.', criminal: 1 },
        { x: -30, z: -80, color: 0x718096, name: '공장 근로자',
          tip: '공장지대 회색 건물 옥상에 빨간 물탱크가 있어요. 거기 조심해요.', criminal: 2 },
        { x: 25, z: -110, color: 0x4a5568, name: '경비원',
          tip: '7층짜리 공장에서 밤마다 이상한 불빛이 보여요.', criminal: 2 },
    ],

    init(scene) {
        this.scene = scene;
        this.createDialogUI();

        this.npcData.forEach((data, i) => {
            const group = new THREE.Group();

            // Body — varied silhouettes
            const bodyHeight = 1.0 + Math.random() * 0.2;
            const body = new THREE.Mesh(
                new THREE.CylinderGeometry(0.32, 0.28, bodyHeight, 12),
                new THREE.MeshStandardMaterial({ color: data.color, roughness: 0.85 })
            );
            body.position.y = bodyHeight / 2 + 0.3;
            body.castShadow = true;
            group.add(body);

            // Legs
            const legColor = 0x2d3748;
            const lLeg = new THREE.Mesh(
                new THREE.CylinderGeometry(0.1, 0.1, 0.5, 8),
                new THREE.MeshStandardMaterial({ color: legColor, roughness: 0.7 })
            );
            lLeg.position.set(-0.13, 0.25, 0);
            lLeg.castShadow = true;
            group.add(lLeg);
            const rLeg = lLeg.clone();
            rLeg.position.set(0.13, 0.25, 0);
            group.add(rLeg);

            // Head
            const head = new THREE.Mesh(
                new THREE.SphereGeometry(0.22, 24, 24),
                new THREE.MeshStandardMaterial({ color: 0xffdbac, roughness: 0.6 })
            );
            head.position.y = bodyHeight + 0.55;
            head.castShadow = true;
            group.add(head);

            // Hair
            const hairColor = [0x1a0a00, 0x4a2510, 0x8b4513][i % 3];
            const hair = new THREE.Mesh(
                new THREE.SphereGeometry(0.24, 16, 16, 0, Math.PI * 2, 0, Math.PI * 0.55),
                new THREE.MeshStandardMaterial({ color: hairColor, roughness: 0.8 })
            );
            hair.position.y = bodyHeight + 0.65;
            group.add(hair);

            // Eyes
            const eyeMat = new THREE.MeshStandardMaterial({ color: 0x1a0a00 });
            const lEye = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 8), eyeMat);
            lEye.position.set(-0.07, bodyHeight + 0.57, 0.21);
            group.add(lEye);
            const rEye = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 8), eyeMat);
            rEye.position.set(0.07, bodyHeight + 0.57, 0.21);
            group.add(rEye);

            // Talk indicator (floating dialog bubble)
            const canvas = document.createElement('canvas');
            canvas.width = 64; canvas.height = 64;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = 'rgba(96,165,250,0.95)';
            ctx.beginPath();
            ctx.arc(32, 28, 22, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 24px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('💬', 32, 30);
            const tex = new THREE.CanvasTexture(canvas);
            const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
            sprite.scale.set(0.5, 0.5, 1);
            sprite.position.y = bodyHeight + 1.0;
            group.add(sprite);

            group.position.set(data.x, 0, data.z);
            group.rotation.y = Math.random() * Math.PI * 2;
            scene.add(group);

            this.npcs.push({
                mesh: group,
                ...data,
                visited: false,
                walkTime: Math.random() * 10,
                wanderTarget: { x: data.x, z: data.z },
                baseX: data.x,
                baseZ: data.z
            });
        });
    },

    createDialogUI() {
        const dialog = document.createElement('div');
        dialog.id = 'npc-dialog';
        dialog.style.cssText = `
            display:none; position:fixed; bottom:130px; left:50%; transform:translateX(-50%);
            width:380px; max-width:90vw;
            background:linear-gradient(135deg, rgba(15,23,42,0.97), rgba(30,41,59,0.97));
            backdrop-filter:blur(16px); border:1px solid rgba(255,255,255,0.15);
            border-radius:18px; padding:18px 22px; z-index:55;
            color:#fff; font-family:'Inter',sans-serif;
            box-shadow:0 10px 40px rgba(0,0,0,0.6);
            animation:msgIn 0.3s ease;
        `;
        dialog.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div id="npc-name" style="font-size:13px; font-weight:700; color:#60a5fa;"></div>
                <button id="npc-close" style="background:none;border:none;color:#94a3b8;font-size:18px;cursor:pointer;padding:4px;">✕</button>
            </div>
            <div id="npc-text" style="font-size:14px; line-height:1.5; color:#e2e8f0;"></div>
            <div style="margin-top:14px; text-align:right;">
                <button id="npc-ok" style="
                    padding:8px 20px; border:none; border-radius:18px;
                    background:linear-gradient(135deg,#3b82f6,#2563eb);
                    color:#fff; font-size:13px; font-weight:700; cursor:pointer;
                    font-family:'Inter',sans-serif;
                ">알겠어요</button>
            </div>
        `;
        document.body.appendChild(dialog);
        document.getElementById('npc-close').addEventListener('click', () => this.closeDialog());
        document.getElementById('npc-ok').addEventListener('click', () => this.closeDialog());
    },

    update(playerPos, delta, time) {
        this.nearbyNpc = null;
        let nearest = null;
        let minDist = this.interactDistance;

        this.npcs.forEach(npc => {
            // Wander animation
            npc.walkTime += delta;
            if (npc.walkTime > 5 + Math.random() * 5) {
                npc.wanderTarget = {
                    x: npc.baseX + (Math.random() - 0.5) * 8,
                    z: npc.baseZ + (Math.random() - 0.5) * 8
                };
                npc.walkTime = 0;
            }
            const tdx = npc.wanderTarget.x - npc.mesh.position.x;
            const tdz = npc.wanderTarget.z - npc.mesh.position.z;
            const td = Math.sqrt(tdx * tdx + tdz * tdz);
            if (td > 0.2) {
                npc.mesh.position.x += (tdx / td) * 0.4 * delta;
                npc.mesh.position.z += (tdz / td) * 0.4 * delta;
                npc.mesh.rotation.y = Math.atan2(tdx, tdz);
            }

            // Check player distance
            const dx = playerPos.x - npc.mesh.position.x;
            const dz = playerPos.z - npc.mesh.position.z;
            const d = Math.sqrt(dx * dx + dz * dz);
            if (d < minDist) {
                minDist = d;
                nearest = npc;
            }
        });

        this.nearbyNpc = nearest;

        // Show talk button
        let talkBtn = document.getElementById('btn-npc-talk');
        if (!talkBtn) {
            talkBtn = document.createElement('button');
            talkBtn.id = 'btn-npc-talk';
            talkBtn.style.cssText = `
                position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
                width:64px; height:64px; border-radius:50%;
                border:2px solid rgba(96,165,250,0.6); background:rgba(96,165,250,0.25);
                backdrop-filter:blur(8px); color:#fff; font-size:24px;
                font-family:'Inter',sans-serif; cursor:pointer; touch-action:none;
                z-index:40; pointer-events:auto; display:none;
                align-items:center; justify-content:center;
                box-shadow:0 4px 20px rgba(96,165,250,0.4);
            `;
            talkBtn.innerHTML = '💬';
            talkBtn.addEventListener('click', () => this.talk());
            talkBtn.addEventListener('touchstart', e => { e.preventDefault(); this.talk(); }, { passive: false });
            document.body.appendChild(talkBtn);
        }
        if (nearest && gameState.isDay && !this.dialogOpen) {
            talkBtn.style.display = 'flex';
        } else {
            talkBtn.style.display = 'none';
        }
    },

    talk() {
        if (!this.nearbyNpc) return;
        const npc = this.nearbyNpc;
        document.getElementById('npc-name').textContent = '👤 ' + npc.name;
        document.getElementById('npc-text').textContent = npc.tip;
        document.getElementById('npc-dialog').style.display = 'block';
        this.dialogOpen = true;

        // First time talking — give coin bonus
        if (!npc.visited) {
            npc.visited = true;
            gameState.coins += 5;
        }

        if (typeof SoundManager !== 'undefined') SoundManager.playSFX('collect');
    },

    closeDialog() {
        document.getElementById('npc-dialog').style.display = 'none';
        this.dialogOpen = false;
    }
};
