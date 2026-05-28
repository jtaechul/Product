// hint.js — 힌트 시스템 (4단계)
// 도시 곳곳에 노란 빛나는 구체 9개 (납치범 3명 × 힌트 3개), 낮에만 수집 가능

const HintSystem = {
    hints: [],
    collectedHints: [],
    hintMeshes: [],
    interactDistance: 2,
    nearbyHint: null,
    memoOpen: false,

    hintData: [
        // 납치범 1호 (3개) — 쉬움
        { criminal: 0, order: 0, text: '주택가에 있는 건물이야', x: -5, z: 75 },
        { criminal: 0, order: 1, text: '파란색 3층짜리야', x: -40, z: 30 },
        { criminal: 0, order: 2, text: '앞에 빨간 우체통이 있어', x: -80, z: -10 },
        // 납치범 2호 (4개) — 보통
        { criminal: 1, order: 0, text: '상업지구 어딘가에 있어', x: 30, z: 60 },
        { criminal: 1, order: 1, text: '흰색 건물이고 5층이야', x: 60, z: -15 },
        { criminal: 1, order: 2, text: "간판에 'CAFE'라고 써있어", x: 100, z: 30 },
        { criminal: 1, order: 3, text: '큰 도로 옆에 위치해 있어', x: 95, z: -45 },
        // 납치범 3호 (5개) — 어려움
        { criminal: 2, order: 0, text: '공장지대에 숨어있어', x: -20, z: 55 },
        { criminal: 2, order: 1, text: '회색 건물이고 키가 큰 편', x: 40, z: -60 },
        { criminal: 2, order: 2, text: '7층짜리 공장이야', x: -60, z: -90 },
        { criminal: 2, order: 3, text: '옥상에 빨간 물탱크가 있어', x: 60, z: -100 },
        { criminal: 2, order: 4, text: '주변에 굴뚝과 철조망이 있어', x: -100, z: -120 },
    ],

    hintsRequired: [3, 4, 5],

    criminalNames: ['1호 납치범', '2호 납치범', '3호 납치범'],

    init(scene) {
        this.scene = scene;
        this.hints = [];
        this.collectedHints = [];
        this.hintMeshes = [];
        this.nearbyHint = null;

        this.hintData.forEach((data, i) => {
            const group = new THREE.Group();

            // Glowing yellow sphere
            const sphere = new THREE.Mesh(
                new THREE.SphereGeometry(0.5, 16, 16),
                new THREE.MeshStandardMaterial({
                    color: 0xffdd00,
                    emissive: 0xffaa00,
                    emissiveIntensity: 0.8,
                    transparent: true,
                    opacity: 0.9
                })
            );
            sphere.castShadow = true;
            group.add(sphere);

            // Outer glow ring
            const glow = new THREE.Mesh(
                new THREE.SphereGeometry(0.8, 16, 16),
                new THREE.MeshBasicMaterial({
                    color: 0xffee66,
                    transparent: true,
                    opacity: 0.2
                })
            );
            group.add(glow);

            // Exclamation mark sprite
            const canvas = document.createElement('canvas');
            canvas.width = 128; canvas.height = 128;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#fbbf24';
            ctx.font = 'bold 96px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.shadowColor = '#ff8800';
            ctx.shadowBlur = 12;
            ctx.fillText('!', 64, 64);
            const texture = new THREE.CanvasTexture(canvas);
            const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true });
            const sprite = new THREE.Sprite(spriteMat);
            sprite.scale.set(0.9, 0.9, 1);
            sprite.position.y = 1.5;
            group.add(sprite);

            group.position.set(data.x, 1.2, data.z);
            scene.add(group);

            const hint = {
                ...data,
                index: i,
                mesh: group,
                collected: false,
                glowMesh: glow,
                sphereMesh: sphere
            };
            this.hints.push(hint);
            this.hintMeshes.push(group);
        });

        this.createMemoUI();
        this.createPopupUI();
    },

    createMemoUI() {
        const memoBtn = document.createElement('button');
        memoBtn.className = 'action-btn';
        memoBtn.id = 'btn-memo';
        memoBtn.textContent = '📋';
        memoBtn.style.background = 'rgba(59,130,246,0.25)';
        memoBtn.style.borderColor = 'rgba(59,130,246,0.5)';
        memoBtn.style.pointerEvents = 'auto';
        memoBtn.addEventListener('click', () => this.toggleMemo());
        memoBtn.addEventListener('touchstart', (e) => { e.preventDefault(); this.toggleMemo(); });
        document.getElementById('action-buttons').appendChild(memoBtn);

        const memoPanel = document.createElement('div');
        memoPanel.id = 'memo-panel';
        memoPanel.style.cssText = `
            display: none;
            position: fixed;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: 340px; max-width: 90vw;
            max-height: 70vh;
            background: rgba(0,0,0,0.85);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 16px;
            padding: 24px;
            z-index: 50;
            overflow-y: auto;
            color: #fff;
            font-family: 'Inter', sans-serif;
        `;
        memoPanel.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                <h3 style="margin:0; font-size:18px;">📋 수사 메모장</h3>
                <button id="memo-close" style="background:none; border:none; color:#fff; font-size:24px; cursor:pointer; padding:4px;">✕</button>
            </div>
            <div id="memo-content"></div>
            <div style="margin-top:16px; text-align:center; opacity:0.5; font-size:13px;">
                수집한 힌트: <span id="memo-count">0</span>/12
            </div>
        `;
        document.body.appendChild(memoPanel);

        document.getElementById('memo-close').addEventListener('click', () => this.toggleMemo());
    },

    createPopupUI() {
        const popup = document.createElement('div');
        popup.id = 'hint-popup';
        popup.style.cssText = `
            display: none;
            position: fixed;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0,0,0,0.9);
            backdrop-filter: blur(12px);
            border: 2px solid #ffdd00;
            border-radius: 16px;
            padding: 28px 36px;
            z-index: 60;
            text-align: center;
            color: #fff;
            font-family: 'Inter', sans-serif;
            animation: fadeIn 0.3s ease;
            max-width: 85vw;
        `;
        popup.innerHTML = `
            <div style="font-size:28px; margin-bottom:8px;">🔍</div>
            <div style="font-size:13px; color:#ffdd00; margin-bottom:8px;" id="hint-popup-criminal"></div>
            <div style="font-size:18px; font-weight:700; line-height:1.5;" id="hint-popup-text"></div>
            <div style="margin-top:12px; font-size:12px; opacity:0.5;">+10 코인</div>
        `;
        document.body.appendChild(popup);
    },

    toggleMemo() {
        this.memoOpen = !this.memoOpen;
        const panel = document.getElementById('memo-panel');
        panel.style.display = this.memoOpen ? 'block' : 'none';
        gameState.isPaused = this.memoOpen;

        if (this.memoOpen) this.updateMemoContent();
    },

    updateMemoContent() {
        const content = document.getElementById('memo-content');
        let html = '';

        for (let c = 0; c < 3; c++) {
            const criminalHints = this.collectedHints.filter(h => h.criminal === c);
            const colors = ['#ef4444', '#f97316', '#a855f7'];
            const names = this.criminalNames;

            html += `<div style="margin-bottom:14px; padding:12px; background:rgba(255,255,255,0.05); border-radius:10px; border-left:3px solid ${colors[c]};">`;
            html += `<div style="font-size:14px; font-weight:700; color:${colors[c]}; margin-bottom:8px;">${names[c]}</div>`;

            for (let o = 0; o < this.hintsRequired[c]; o++) {
                const found = criminalHints.find(h => h.order === o);
                if (found) {
                    html += `<div style="font-size:13px; padding:4px 0; color:#eee;">✅ "${found.text}"</div>`;
                } else {
                    html += `<div style="font-size:13px; padding:4px 0; color:#555;">❓ ???</div>`;
                }
            }
            html += '</div>';
        }

        content.innerHTML = html;
        document.getElementById('memo-count').textContent = this.collectedHints.length;
    },

    update(playerPos, delta, time) {
        if (!gameState.isDay || DayNight.isTransitioning) {
            this.hideInteractPrompt();
            this.hintMeshes.forEach(m => { m.visible = false; });
            return;
        }

        this.nearbyHint = null;
        const interactBtn = document.getElementById('btn-interact');

        this.hints.forEach(hint => {
            if (hint.collected) {
                hint.mesh.visible = false;
                return;
            }

            hint.mesh.visible = true;

            // Floating animation
            hint.mesh.position.y = 1.2 + Math.sin(time * 2 + hint.index) * 0.3;
            hint.sphereMesh.rotation.y += delta * 1.5;
            hint.glowMesh.material.opacity = 0.15 + Math.sin(time * 3 + hint.index) * 0.1;

            // Distance check
            const dx = playerPos.x - hint.mesh.position.x;
            const dz = playerPos.z - hint.mesh.position.z;
            const dist = Math.sqrt(dx * dx + dz * dz);

            if (dist < this.interactDistance) {
                this.nearbyHint = hint;
            }
        });

        if (this.nearbyHint) {
            this.showHintButton(true);
        } else {
            this.showHintButton(false);
        }
    },

    showHintButton(show) {
        let btn = document.getElementById('btn-hint-collect');
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'btn-hint-collect';
            btn.style.cssText = `
                position:fixed; top:50%; left:55%; transform:translate(-50%,-50%);
                width:60px; height:60px; border-radius:50%;
                border:2px solid rgba(255,220,0,0.6); background:rgba(255,220,0,0.2);
                backdrop-filter:blur(4px); color:#fbbf24; font-size:18px; font-weight:800;
                font-family:'Inter',sans-serif; cursor:pointer; touch-action:none;
                z-index:40; pointer-events:auto; display:none;
            `;
            btn.textContent = 'H';
            btn.addEventListener('click', () => this.collectNearbyHint());
            btn.addEventListener('touchstart', e => { e.preventDefault(); this.collectNearbyHint(); }, { passive: false });
            document.body.appendChild(btn);
        }
        btn.style.display = show ? 'flex' : 'none';
        btn.style.alignItems = 'center';
        btn.style.justifyContent = 'center';
        if (show) this.showPrompt('H키로 수집');
        else this.hidePrompt();
    },

    hideInteractPrompt() {
        const btn = document.getElementById('btn-interact');
        if (btn) btn.style.display = 'none';
        this.hidePrompt();
    },

    showPrompt(text) {
        let el = document.getElementById('interact-prompt');
        if (!el) {
            el = document.createElement('div');
            el.id = 'interact-prompt';
            el.style.cssText = `
                position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
                background:rgba(0,0,0,0.75); backdrop-filter:blur(4px);
                padding:10px 24px; border-radius:20px; border:1px solid rgba(255,220,0,0.4);
                font-size:15px; color:#fbbf24; font-weight:700; z-index:35;
                pointer-events:none;
            `;
            document.body.appendChild(el);
        }
        el.textContent = text;
        el.style.display = 'block';
    },

    hidePrompt() {
        const el = document.getElementById('interact-prompt');
        if (el) el.style.display = 'none';
    },

    collectNearbyHint() {
        if (!this.nearbyHint || !gameState.isDay) return false;

        const hint = this.nearbyHint;
        hint.collected = true;
        hint.mesh.visible = false;
        this.scene.remove(hint.mesh);

        this.collectedHints.push({
            criminal: hint.criminal,
            order: hint.order,
            text: hint.text
        });

        gameState.hintsCollected = this.collectedHints.length;
        gameState.coins += 10;
        if (typeof SoundManager !== 'undefined') SoundManager.playSFX('collect');

        // Show popup
        const popup = document.getElementById('hint-popup');
        document.getElementById('hint-popup-criminal').textContent =
            this.criminalNames[hint.criminal] + ' 단서 ' + (hint.order + 1) + '/3';
        document.getElementById('hint-popup-text').textContent = '"' + hint.text + '"';
        popup.style.display = 'block';

        setTimeout(() => { popup.style.display = 'none'; }, 2500);

        this.nearbyHint = null;
        document.getElementById('btn-interact').style.display = 'none';

        return true;
    },

    reset() {
        this.hints.forEach(h => {
            if (h.mesh.parent) this.scene.remove(h.mesh);
        });
        this.hints = [];
        this.collectedHints = [];
        this.hintMeshes = [];
        this.nearbyHint = null;
        this.memoOpen = false;
        document.getElementById('memo-panel').style.display = 'none';
    }
};
