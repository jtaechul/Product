// minigame.js — 추격 & 검거 미니게임 (6단계)

const Minigame = {
    active: false,
    targetEnemy: null,
    gaugeProgress: 0,
    gaugeSpeed: 0,
    gaugeDirection: 1,
    successZoneStart: 0.35,
    successZoneEnd: 0.65,
    result: null,
    resultTimer: 0,
    catchDistance: 1.5,
    rescueChildren: [],

    init() {
        this.createUI();
    },

    createUI() {
        const overlay = document.createElement('div');
        overlay.id = 'minigame-overlay';
        overlay.style.cssText = `
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.6);
            z-index: 80;
            display: none;
            align-items: center;
            justify-content: center;
            flex-direction: column;
        `;
        overlay.innerHTML = `
            <div style="color:#fff; font-size:20px; font-weight:700; margin-bottom:20px;" id="mg-title">검거 시도!</div>
            <div id="mg-gauge-container" style="
                width: 280px; height: 280px;
                position: relative;
                display: flex; align-items: center; justify-content: center;
            ">
                <canvas id="mg-gauge" width="280" height="280" style="position:absolute;"></canvas>
                <div style="color:#fff; font-size:16px; font-weight:700; z-index:1;" id="mg-instruction">SPACE / TAP</div>
            </div>
            <div id="mg-result" style="
                display:none; color:#fff; font-size:28px; font-weight:800;
                margin-top:20px; text-align:center;
            "></div>
        `;
        document.body.appendChild(overlay);

        // Input handlers
        window.addEventListener('keydown', e => {
            if (e.code === 'Space' && this.active) {
                e.preventDefault();
                this.attempt();
            }
        });

        overlay.addEventListener('touchstart', e => {
            if (this.active) {
                e.preventDefault();
                this.attempt();
            }
        }, { passive: false });

        overlay.addEventListener('click', e => {
            if (this.active) {
                this.attempt();
            }
        });
    },

    startMinigame(enemy) {
        this.active = true;
        this.targetEnemy = enemy;
        this.gaugeProgress = 0;
        this.gaugeDirection = 1;
        this.result = null;
        this.resultTimer = 0;

        // Speed based on enemy difficulty
        const speeds = [0.8, 1.3, 2.0];
        this.gaugeSpeed = speeds[enemy.id] || 1.0;

        // Success zone narrows with difficulty
        const zones = [
            { start: 0.3, end: 0.7 },
            { start: 0.35, end: 0.65 },
            { start: 0.4, end: 0.6 }
        ];
        const zone = zones[enemy.id] || zones[0];
        this.successZoneStart = zone.start;
        this.successZoneEnd = zone.end;

        gameState.isPaused = true;
        document.getElementById('minigame-overlay').style.display = 'flex';
        document.getElementById('mg-result').style.display = 'none';
        document.getElementById('mg-instruction').style.display = 'block';
        document.getElementById('mg-title').textContent =
            '⚡ ' + enemy.name + ' 검거 시도!';
    },

    attempt() {
        if (this.result !== null) return;

        const inZone = this.gaugeProgress >= this.successZoneStart &&
                       this.gaugeProgress <= this.successZoneEnd;

        const resultEl = document.getElementById('mg-result');
        resultEl.style.display = 'block';
        document.getElementById('mg-instruction').style.display = 'none';

        if (inZone) {
            this.result = 'success';
            resultEl.textContent = '검거 성공! 🎉';
            resultEl.style.color = '#4ade80';
            if (typeof SoundManager !== 'undefined') SoundManager.playSFX('arrest_success');

            const rescueX = this.targetEnemy.hideoutX;
            const rescueZ = this.targetEnemy.hideoutZ;
            const crimId = this.targetEnemy.id;
            EnemySystem.arrestEnemy(this.targetEnemy);

            // Child rescue animation — child follows player back to police station
            setTimeout(() => {
                this.spawnRescueChild(rescueX, rescueZ, crimId);
                showMessage('👶 아이가 따라옵니다! 경찰서로 데려가세요. (' + gameState.arrests + '/3 체포)');
            }, 800);
        } else {
            this.result = 'fail';
            resultEl.textContent = '도주했습니다 😱';
            resultEl.style.color = '#ef4444';
            if (typeof SoundManager !== 'undefined') SoundManager.playSFX('arrest_fail');

            // Damage player on fail based on resistance
            if (this.targetEnemy.resistance > 0) {
                const dmg = (typeof Shop !== 'undefined' && Shop.hasItem('vest')) ? 0.5 : 1;
                gameState.health = Math.max(0, gameState.health - dmg);
                if (gameState.health <= 0) {
                    setTimeout(() => this.triggerGameOver(), 1000);
                }
            }

            // Relocate enemy
            this.targetEnemy.state = 'patrol';
            this.targetEnemy.patrolTarget = EnemySystem.getPatrolTarget(this.targetEnemy);
            const angle = Math.random() * Math.PI * 2;
            this.targetEnemy.currentX = this.targetEnemy.hideoutX + Math.cos(angle) * 15;
            this.targetEnemy.currentZ = this.targetEnemy.hideoutZ + Math.sin(angle) * 15;
        }

        this.resultTimer = 0;
    },

    update(delta) {
        if (!this.active) return;

        if (this.result === null) {
            // Animate gauge
            this.gaugeProgress += this.gaugeDirection * this.gaugeSpeed * delta;
            if (this.gaugeProgress >= 1) {
                this.gaugeProgress = 1;
                this.gaugeDirection = -1;
            } else if (this.gaugeProgress <= 0) {
                this.gaugeProgress = 0;
                this.gaugeDirection = 1;
            }
        } else {
            this.resultTimer += delta;
            if (this.resultTimer > 1.5) {
                this.close();
            }
        }

        this.drawGauge();
    },

    drawGauge() {
        const canvas = document.getElementById('mg-gauge');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const cx = 140, cy = 140, r = 110;

        ctx.clearRect(0, 0, 280, 280);

        // Background circle
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255,255,255,0.15)';
        ctx.lineWidth = 20;
        ctx.stroke();

        // Success zone (green arc)
        const startAngle = -Math.PI / 2 + this.successZoneStart * Math.PI * 2;
        const endAngle = -Math.PI / 2 + this.successZoneEnd * Math.PI * 2;
        ctx.beginPath();
        ctx.arc(cx, cy, r, startAngle, endAngle);
        ctx.strokeStyle = 'rgba(74, 222, 128, 0.5)';
        ctx.lineWidth = 20;
        ctx.stroke();

        // Moving indicator
        const indicatorAngle = -Math.PI / 2 + this.gaugeProgress * Math.PI * 2;
        const ix = cx + Math.cos(indicatorAngle) * r;
        const iy = cy + Math.sin(indicatorAngle) * r;

        const inZone = this.gaugeProgress >= this.successZoneStart &&
                       this.gaugeProgress <= this.successZoneEnd;

        ctx.beginPath();
        ctx.arc(ix, iy, 14, 0, Math.PI * 2);
        ctx.fillStyle = inZone ? '#4ade80' : '#ffffff';
        ctx.shadowBlur = 15;
        ctx.shadowColor = inZone ? '#4ade80' : '#ffffff';
        ctx.fill();
        ctx.shadowBlur = 0;

        // Center text
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 14px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(this.targetEnemy ? this.targetEnemy.name : '', cx, cy - 8);

        const diffLabels = ['★☆☆', '★★☆', '★★★'];
        ctx.font = '12px Inter, sans-serif';
        ctx.fillStyle = 'rgba(255,255,255,0.6)';
        ctx.fillText(diffLabels[this.targetEnemy ? this.targetEnemy.id : 0], cx, cy + 12);
    },

    close() {
        this.active = false;
        this.targetEnemy = null;
        gameState.isPaused = false;
        document.getElementById('minigame-overlay').style.display = 'none';
    },

    checkCatchable(playerPos) {
        if (this.active || gameState.isDay) return;

        const { enemy, distance } = EnemySystem.getNearestEnemy(playerPos);
        if (enemy && distance < this.catchDistance) {
            this.startMinigame(enemy);
        }
    },

    spawnRescueChild(fromX, fromZ, criminalId) {
        const group = new THREE.Group();
        // Different colors/outfits per criminal (boy/girl variations)
        const outfits = [
            { shirt: 0xfacc15, pants: 0x3b82f6, hair: 0x2a1808, ribbon: null },     // boy yellow
            { shirt: 0xec4899, pants: 0x6b21a8, hair: 0x4a2510, ribbon: 0xff6b9d }, // girl pink
            { shirt: 0x06c167, pants: 0x713f12, hair: 0x1a0a00, ribbon: null }      // boy green
        ];
        const o = outfits[(criminalId !== undefined ? criminalId : 0) % 3];

        // Articulated legs (hip groups)
        const skinMat = new THREE.MeshStandardMaterial({ color: 0xffdbac, roughness: 0.6 });
        const pantsMat = new THREE.MeshStandardMaterial({ color: o.pants, roughness: 0.8 });
        const shirtMat = new THREE.MeshStandardMaterial({ color: o.shirt, roughness: 0.85 });
        const shoeMat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.5 });

        function makeChildLeg(side) {
            const hip = new THREE.Group();
            hip.position.set(side * 0.08, 0.36, 0);
            const thigh = new THREE.Mesh(new THREE.CylinderGeometry(0.065, 0.058, 0.18, 10), pantsMat);
            thigh.position.y = -0.09; thigh.castShadow = true;
            hip.add(thigh);
            const knee = new THREE.Group();
            knee.position.y = -0.18;
            const shin = new THREE.Mesh(new THREE.CylinderGeometry(0.058, 0.05, 0.18, 10), skinMat);
            shin.position.y = -0.09; shin.castShadow = true;
            knee.add(shin);
            const shoe = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.07, 0.16), shoeMat);
            shoe.position.set(0, -0.18, 0.03); shoe.castShadow = true;
            knee.add(shoe);
            hip.add(knee);
            hip.userData.partName = side < 0 ? 'cLeftHip' : 'cRightHip';
            hip.userData.knee = knee;
            return hip;
        }
        group.add(makeChildLeg(-1));
        group.add(makeChildLeg(1));

        // Torso (shirt)
        const torso = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.32, 0.18), shirtMat);
        torso.position.y = 0.54; torso.castShadow = true;
        group.add(torso);

        // Articulated arms
        function makeChildArm(side) {
            const sh = new THREE.Group();
            sh.position.set(side * 0.17, 0.66, 0);
            const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.04, 0.17, 10), shirtMat);
            upper.position.y = -0.085; upper.castShadow = true;
            sh.add(upper);
            const elbow = new THREE.Group();
            elbow.position.y = -0.17;
            const forearm = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.035, 0.16, 10), skinMat);
            forearm.position.y = -0.08; forearm.castShadow = true;
            elbow.add(forearm);
            const hand = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 10), skinMat);
            hand.position.y = -0.16;
            elbow.add(hand);
            sh.add(elbow);
            sh.userData.partName = side < 0 ? 'cLeftShoulder' : 'cRightShoulder';
            sh.userData.elbow = elbow;
            return sh;
        }
        group.add(makeChildArm(-1));
        group.add(makeChildArm(1));

        // Head (slightly bigger proportion = child)
        const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 20, 20), skinMat);
        head.position.y = 0.86; head.castShadow = true;
        group.add(head);

        // Hair
        const hairMat = new THREE.MeshStandardMaterial({ color: o.hair, roughness: 0.7 });
        const hair = new THREE.Mesh(
            new THREE.SphereGeometry(0.165, 20, 20, 0, Math.PI*2, 0, Math.PI*0.55),
            hairMat
        );
        hair.position.y = 0.88;
        group.add(hair);

        // Eyes (big anime-style)
        const eyeWMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
        const eyeBMat = new THREE.MeshStandardMaterial({ color: 0x1a0a00 });
        const lEW = new THREE.Mesh(new THREE.SphereGeometry(0.04, 12, 12), eyeWMat);
        lEW.position.set(-0.055, 0.87, 0.13); lEW.scale.set(1,1.2,0.6);
        group.add(lEW);
        const rEW = lEW.clone(); rEW.position.x = 0.055;
        group.add(rEW);
        const lP = new THREE.Mesh(new THREE.SphereGeometry(0.022, 8, 8), eyeBMat);
        lP.position.set(-0.055, 0.865, 0.16);
        group.add(lP);
        const rP = lP.clone(); rP.position.x = 0.055;
        group.add(rP);

        // Small smile
        const mouth = new THREE.Mesh(
            new THREE.BoxGeometry(0.05, 0.012, 0.008),
            new THREE.MeshStandardMaterial({ color: 0xc04060 })
        );
        mouth.position.set(0, 0.78, 0.155);
        group.add(mouth);

        // Optional ribbon (girl)
        if (o.ribbon) {
            const ribbon = new THREE.Mesh(
                new THREE.BoxGeometry(0.06, 0.04, 0.04),
                new THREE.MeshStandardMaterial({ color: o.ribbon, roughness: 0.5 })
            );
            ribbon.position.set(0, 1.02, 0);
            group.add(ribbon);
        }

        // Cheek blush
        const cheekMat = new THREE.MeshStandardMaterial({ color: 0xff9999, transparent: true, opacity: 0.5 });
        const lC = new THREE.Mesh(new THREE.SphereGeometry(0.03, 8, 8), cheekMat);
        lC.position.set(-0.09, 0.82, 0.13); lC.scale.set(1,0.6,0.3);
        group.add(lC);
        const rC = lC.clone(); rC.position.x = 0.09;
        group.add(rC);

        group.position.set(fromX, 0, fromZ);
        scene.add(group);
        this.rescueChildren.push({
            mesh: group,
            time: 0,
            following: true,  // following player
            criminalId,
            arrivedAtPolice: false
        });
    },

    updateRescueChildren(delta) {
        const policeX = 0, policeZ = 92;
        for (let i = this.rescueChildren.length - 1; i >= 0; i--) {
            const child = this.rescueChildren[i];
            child.time += delta;

            if (child.arrivedAtPolice) continue;

            // Check arrival at police
            const pdx = policeX - child.mesh.position.x;
            const pdz = policeZ - child.mesh.position.z;
            const pdist = Math.sqrt(pdx*pdx + pdz*pdz);

            // Player position to follow (slightly behind)
            const followOffset = 1.6 + (i * 0.3);
            const tx = playerGroup.position.x - Math.sin(playerGroup.rotation.y) * followOffset;
            const tz = playerGroup.position.z - Math.cos(playerGroup.rotation.y) * followOffset;
            const dx = tx - child.mesh.position.x;
            const dz = tz - child.mesh.position.z;
            const dist = Math.sqrt(dx * dx + dz * dz);

            // If player at police station, count this child as rescued
            const playerAtPolice = Math.sqrt(playerGroup.position.x ** 2 + (playerGroup.position.z - policeZ) ** 2) < 14;
            if (playerAtPolice && pdist < 16) {
                child.arrivedAtPolice = true;
                gameState.rescued = (gameState.rescued || 0) + 1;
                showMessage('👧 아이가 안전하게 도착했습니다! (' + gameState.rescued + '/3)');
                // Fade out child
                setTimeout(() => {
                    scene.remove(child.mesh);
                    this.rescueChildren.splice(this.rescueChildren.indexOf(child), 1);
                    if (gameState.rescued >= 3) {
                        setTimeout(() => this.triggerVictory(), 1500);
                    }
                }, 1200);
                continue;
            }

            // Follow player
            if (dist > 0.5) {
                const speed = Math.min(0.16, dist * 0.12) * delta * 60;
                child.mesh.position.x += (dx / dist) * speed;
                child.mesh.position.z += (dz / dist) * speed;
                child.mesh.rotation.y = Math.atan2(dx, dz);

                // Walk animation
                const swing = Math.sin(child.time * 10) * 0.5;
                const kbend = Math.max(0, Math.sin(child.time * 10)) * 0.55;
                child.mesh.children.forEach(c => {
                    if (c.userData.partName === 'cLeftHip') {
                        c.rotation.x = swing;
                        if (c.userData.knee) c.userData.knee.rotation.x = -kbend;
                    }
                    if (c.userData.partName === 'cRightHip') {
                        c.rotation.x = -swing;
                        if (c.userData.knee) c.userData.knee.rotation.x = -Math.max(0, Math.sin(child.time * 10 + Math.PI)) * 0.55;
                    }
                    if (c.userData.partName === 'cLeftShoulder') c.rotation.x = -swing * 0.8;
                    if (c.userData.partName === 'cRightShoulder') c.rotation.x = swing * 0.8;
                });
            }
        }
    },

    triggerVictory() {
        gameState.gameOver = true;
        gameState.isPaused = true;
        if (typeof SoundManager !== 'undefined') { SoundManager.stopBGM(); SoundManager.playSFX('victory'); }
        this.close();

        const overlay = document.createElement('div');
        overlay.id = 'ending-screen';
        overlay.style.cssText = `
            position: fixed; top:0; left:0; right:0; bottom:0;
            background: rgba(0,0,0,0.85);
            z-index: 200;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            animation: fadeIn 1.5s ease;
        `;

        const totalTime = (gameState.day - 1) * 12 +
            (gameState.isDay ? gameState.dayDuration - gameState.timeRemaining : gameState.dayDuration + gameState.nightDuration - gameState.timeRemaining);
        const mins = Math.floor(totalTime / 60);
        let grade = 'C';
        if (mins <= 15) grade = 'S';
        else if (mins <= 20) grade = 'A';
        else if (mins <= 25) grade = 'B';

        overlay.innerHTML = `
            <h1 style="font-size:48px; color:#FFD700; text-shadow:0 0 30px rgba(255,215,0,0.5); margin-bottom:10px;">임무 성공! 🎉</h1>
            <p style="font-size:20px; color:#eee; margin-bottom:30px;">아이들을 모두 구출했습니다!</p>
            <div style="background:rgba(0,0,0,0.65); padding:20px 30px; border-radius:16px; text-align:center; margin-bottom:30px;">
                <p style="margin:8px 0; color:#aaa;">플레이 일수: <span style="color:#fff;">${gameState.day}일</span></p>
                <p style="margin:8px 0; color:#aaa;">소요 시간: <span style="color:#fff;">${mins}분</span></p>
                <p style="margin:8px 0; color:#aaa;">수집 힌트: <span style="color:#fff;">${gameState.hintsCollected}/9</span></p>
                <p style="margin:8px 0; color:#aaa;">등급: <span style="color:#FFD700; font-size:28px; font-weight:800;">${grade}</span></p>
            </div>
            <div style="display:flex; gap:16px;">
                <button onclick="location.reload()" style="padding:14px 32px; border:none; border-radius:30px; background:#fff; color:#000; font-size:16px; font-weight:700; cursor:pointer;">🔄 다시 시작</button>
            </div>
        `;
        document.body.appendChild(overlay);
    },

    triggerGameOver() {
        gameState.gameOver = true;
        gameState.isPaused = true;
        if (typeof SoundManager !== 'undefined') { SoundManager.stopBGM(); SoundManager.playSFX('gameover'); }
        this.close();

        const overlay = document.createElement('div');
        overlay.id = 'ending-screen';
        overlay.style.cssText = `
            position: fixed; top:0; left:0; right:0; bottom:0;
            background: rgba(0,0,0,0.9);
            z-index: 200;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            animation: fadeIn 0.5s ease;
        `;
        overlay.innerHTML = `
            <h1 style="font-size:48px; color:#CC0000; margin-bottom:10px;">임무 실패…</h1>
            <p style="font-size:20px; color:#999; margin-bottom:30px;">아이들을 구하지 못했습니다…</p>
            <div style="background:rgba(0,0,0,0.65); padding:20px 30px; border-radius:16px; text-align:center; margin-bottom:30px;">
                <p style="margin:8px 0; color:#aaa;">검거: <span style="color:#fff;">${gameState.arrests}/3</span></p>
                <p style="margin:8px 0; color:#aaa;">힌트: <span style="color:#fff;">${gameState.hintsCollected}/9</span></p>
                <p style="margin:12px 0; color:#999; font-style:italic; font-size:14px;">포기하지 마세요. 아이들이 기다리고 있어요.</p>
            </div>
            <div style="display:flex; gap:16px;">
                <button onclick="location.reload()" style="padding:14px 32px; border:none; border-radius:30px; background:#fff; color:#000; font-size:16px; font-weight:700; cursor:pointer;">🔄 다시 도전</button>
            </div>
        `;
        document.body.appendChild(overlay);
    }
};
