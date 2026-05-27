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

            EnemySystem.arrestEnemy(this.targetEnemy);

            // Child rescue message
            setTimeout(() => {
                showMessage('👶 아이를 구출했습니다! (' + gameState.arrests + '/3)');
                if (gameState.arrests >= gameState.totalArrests) {
                    setTimeout(() => this.triggerVictory(), 1500);
                }
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
