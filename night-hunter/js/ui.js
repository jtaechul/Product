// ui.js — 미니맵 + 전체 UI (8단계)

const GameUI = window.GameUI = {
    minimapCanvas: null,
    minimapCtx: null,
    minimapSize: 120,

    init() {
        this.createMinimap();
        this.createActionButtons();
        this.createBGMIndicator();
        this.createLandscapeOverlay();
    },

    createBGMIndicator() {
        const btn = document.createElement('button');
        btn.id = 'btn-bgm-toggle';
        btn.title = 'BGM 토글';
        btn.style.cssText = `
            position:fixed;
            right:calc(14px + env(safe-area-inset-right, 0px));
            bottom:calc(145px + env(safe-area-inset-bottom, 0px));
            width:44px; height:44px; border-radius:50%;
            border:2px solid rgba(96,165,250,0.6);
            background:rgba(15,23,42,0.7);
            backdrop-filter:blur(8px); color:#fff; font-size:18px;
            cursor:pointer; touch-action:none; z-index:30;
            pointer-events:auto;
            display:flex; align-items:center; justify-content:center;
        `;
        btn.textContent = '🔇';
        const toggle = () => {
            if (typeof SoundManager === 'undefined') return;
            try { SoundManager.init(); } catch(e) {}
            if (SoundManager.ctx && SoundManager.ctx.state !== 'running') {
                SoundManager.ctx.resume().catch(() => {});
            }
            if (SoundManager.bgmActive) {
                SoundManager.stopBGM();
                SoundManager._pendingBGMType = null;
            } else {
                SoundManager.playBGM(gameState.isDay ? 'day' : 'night');
            }
        };
        btn.addEventListener('click', toggle);
        btn.addEventListener('touchstart', e => { e.preventDefault(); toggle(); }, { passive: false });
        document.body.appendChild(btn);
        // Live status updater
        setInterval(() => {
            if (typeof SoundManager === 'undefined') return;
            const playing = SoundManager.bgmActive && SoundManager.ctx && SoundManager.ctx.state === 'running';
            btn.textContent = playing ? '🔊' : '🔇';
            btn.style.borderColor = playing ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.7)';
        }, 500);
    },

    createMinimap() {
        const container = document.createElement('div');
        container.id = 'minimap-container';
        container.style.cssText = `
            position:fixed;
            right:calc(12px + env(safe-area-inset-right, 0px));
            top:calc(60px + env(safe-area-inset-top, 0px));
            width:${this.minimapSize}px; height:${this.minimapSize}px;
            border-radius:50%; overflow:hidden;
            border:2px solid rgba(255,255,255,0.3);
            background:rgba(0,0,0,0.5);
            z-index:25; pointer-events:none;
        `;
        const canvas = document.createElement('canvas');
        canvas.id = 'minimap';
        canvas.width = this.minimapSize;
        canvas.height = this.minimapSize;
        canvas.style.cssText = 'width:100%;height:100%;';
        container.appendChild(canvas);
        document.body.appendChild(container);

        this.minimapCanvas = canvas;
        this.minimapCtx = canvas.getContext('2d');
    },

    createActionButtons() {
        // Memo (수사 노트)
        const mb = document.createElement('button');
        mb.id = 'btn-memo-ui';
        mb.textContent = '📋';
        mb.style.cssText = `
            position:fixed;
            right:calc(150px + env(safe-area-inset-right, 0px));
            bottom:calc(85px + env(safe-area-inset-bottom, 0px));
            width:48px; height:48px; border-radius:50%;
            border:2px solid rgba(59,130,246,0.55);
            background:rgba(59,130,246,0.28);
            backdrop-filter:blur(8px); color:#fff; font-size:20px;
            cursor:pointer; touch-action:none; z-index:30;
            pointer-events:auto;
            display:flex; align-items:center; justify-content:center;
        `;
        mb.addEventListener('click', () => HintSystem.toggleMemo());
        mb.addEventListener('touchstart', e => { e.preventDefault(); HintSystem.toggleMemo(); }, { passive: false });
        document.body.appendChild(mb);

        // Wanted poster (수배 전단) — re-openable from inventory
        const wp = document.createElement('button');
        wp.id = 'btn-wanted-poster';
        wp.textContent = '📜';
        wp.style.cssText = `
            position:fixed;
            right:calc(202px + env(safe-area-inset-right, 0px));
            bottom:calc(85px + env(safe-area-inset-bottom, 0px));
            width:48px; height:48px; border-radius:50%;
            border:2px solid rgba(180,120,40,0.6);
            background:rgba(180,120,40,0.3);
            backdrop-filter:blur(8px); color:#fff; font-size:20px;
            cursor:pointer; touch-action:none; z-index:30;
            pointer-events:auto;
            display:flex; align-items:center; justify-content:center;
        `;
        wp.addEventListener('click', () => { if (window.showWantedPoster) window.showWantedPoster(false); });
        wp.addEventListener('touchstart', e => { e.preventDefault(); if (window.showWantedPoster) window.showWantedPoster(false); }, { passive: false });
        document.body.appendChild(wp);
    },

    createLandscapeOverlay() {
        const overlay = document.createElement('div');
        overlay.id = 'landscape-overlay';
        overlay.style.cssText = `
            display:none; position:fixed; top:0; left:0; right:0; bottom:0;
            background:#000; z-index:9999;
            flex-direction:column; align-items:center; justify-content:center;
            color:#fff; font-family:'Inter',sans-serif; text-align:center;
        `;
        overlay.innerHTML = `
            <div style="font-size:48px; margin-bottom:16px;">📱🔄</div>
            <div style="font-size:18px; font-weight:700;">화면을 가로로 돌려주세요</div>
            <div style="font-size:13px; color:#888; margin-top:8px;">이 게임은 가로 모드에서만 플레이할 수 있습니다.</div>
        `;
        document.body.appendChild(overlay);

        const check = () => {
            const isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
            const isPortrait = window.innerHeight > window.innerWidth;
            overlay.style.display = (isMobile && isPortrait) ? 'flex' : 'none';
        };
        window.addEventListener('resize', check);
        window.addEventListener('orientationchange', () => setTimeout(check, 200));
        check();
    },

    updateMinimap(playerPos, playerAngle, cameraAngle) {
        const ctx = this.minimapCtx;
        const size = this.minimapSize;
        const half = size / 2;
        // 무전기 보유 시 더 넓은 범위 (200 → 거의 월드 전체)
        const hasRadio = typeof Shop !== 'undefined' && Shop.hasItem('radio');
        const viewRange = hasRadio ? 200 : 80;
        const scale = size / viewRange;

        ctx.clearRect(0, 0, size, size);

        // Clip circle
        ctx.save();
        ctx.beginPath();
        ctx.arc(half, half, half, 0, Math.PI * 2);
        ctx.clip();
        ctx.fillStyle = '#1a2e1a';
        ctx.fillRect(0, 0, size, size);

        // Rotate world with camera (camera forward = up)
        ctx.save();
        ctx.translate(half, half);
        ctx.rotate(cameraAngle);
        ctx.translate(-half, -half);

        // Helper: world→minimap coords (before camera rotation)
        const mx = (wx) => half + (wx - playerPos.x) * scale;
        const mz = (wz) => half + (wz - playerPos.z) * scale;

        // Roads
        ctx.strokeStyle = 'rgba(80,80,80,0.6)';
        ctx.lineWidth = 2;
        [[- 150, 50, 150, 50], [0, -150, 0, 150], [-100, -40, 100, -40]].forEach(([x1,z1,x2,z2]) => {
            ctx.beginPath(); ctx.moveTo(mx(x1), mz(z1)); ctx.lineTo(mx(x2), mz(z2)); ctx.stroke();
        });

        // Buildings
        buildingData.forEach(b => {
            const bx = mx(b.x||0), bz = mz(b.z||0);
            const bw = (b.w||6)*scale, bd = (b.d||6)*scale;
            if (bx<-30||bx>size+30||bz<-30||bz>size+30) return;
            if (b.type==='police') ctx.fillStyle='rgba(30,100,200,0.7)';
            else if (b.zone==='RESIDENTIAL') ctx.fillStyle='rgba(180,140,80,0.5)';
            else if (b.zone==='COMMERCIAL') ctx.fillStyle='rgba(100,140,180,0.5)';
            else if (b.zone==='FACTORY') ctx.fillStyle='rgba(120,120,120,0.5)';
            else ctx.fillStyle='rgba(150,150,150,0.4)';
            ctx.fillRect(bx-bw/2, bz-bd/2, bw, bd);
        });

        // === 무전기(radio) 힌트 마커 ===
        // 무전기 = 추적 장치 — 보이지 않는(은신 중인) 대상도 위치를 송신해 미니맵에 표시.
        // 미니맵 범위를 벗어난 대상은 가장자리에 클램프된 작은 점으로 방향만 표시.
        const drawHintMarker = (worldX, worldZ, color) => {
            let nx = mx(worldX), nz = mz(worldZ);
            const margin = 4;
            const outOfRange = (nx < margin || nx > size - margin ||
                                nz < margin || nz > size - margin);
            if (outOfRange) {
                // 미니맵 가장자리로 클램프 (방향 화살표 대용)
                const dx = nx - half, dz = nz - half;
                const dist = Math.sqrt(dx * dx + dz * dz);
                if (dist < 1e-3) return;
                const r = half - margin - 2;
                nx = half + (dx / dist) * r;
                nz = half + (dz / dist) * r;
                ctx.fillStyle = color;
                ctx.globalAlpha = 0.7;
                ctx.beginPath(); ctx.arc(nx, nz, 2.5, 0, Math.PI * 2); ctx.fill();
                ctx.globalAlpha = 1;
            } else {
                // 범위 내 — 큰 마커 + 펄스 링
                ctx.fillStyle = color;
                ctx.beginPath(); ctx.arc(nx, nz, 3.5, 0, Math.PI * 2); ctx.fill();
                ctx.strokeStyle = '#fff'; ctx.lineWidth = 1; ctx.stroke();
                // 펄스 외곽 (애니메이션)
                const pulse = (Date.now() % 1000) / 1000;
                ctx.strokeStyle = color;
                ctx.globalAlpha = 1 - pulse;
                ctx.lineWidth = 1.5;
                ctx.beginPath(); ctx.arc(nx, nz, 3.5 + pulse * 5, 0, Math.PI * 2); ctx.stroke();
                ctx.globalAlpha = 1;
            }
        };

        // [낮] 수배범(suspect) 위치 — radio 보유 시 모두 표시 (visible 무관)
        if (hasRadio && gameState.isDay && typeof NPCSystem !== 'undefined') {
            NPCSystem.npcs.forEach(n => {
                if (n.caught) return;
                if (n.role !== 'suspect') return;
                drawHintMarker(n.mesh.position.x, n.mesh.position.z, '#fbbf24');
            });
        }

        // [밤] 납치범(enemy) 위치 — radio 보유 시 모두 표시 (arrested만 제외)
        // hidden 상태여도 위치는 송신됨 — 단서 미수집이라도 추적 가능
        if (hasRadio && !gameState.isDay && typeof EnemySystem !== 'undefined') {
            EnemySystem.enemies.forEach(e => {
                if (e.arrested) return;
                drawHintMarker(e.currentX, e.currentZ, '#ff3333');
            });
        }

        // Shop NPC removed — police station shown via building color

        ctx.restore(); // end camera rotation

        // Player arrow — rotates with character direction relative to camera
        // charAngleOnMap = character world angle - camera angle, then flip for canvas
        const charRelAngle = Math.PI - playerAngle + cameraAngle;
        ctx.save();
        ctx.translate(half, half);
        ctx.rotate(charRelAngle);
        ctx.fillStyle = '#60a5fa';
        ctx.beginPath();
        ctx.moveTo(0, -7); ctx.lineTo(-5, 5); ctx.lineTo(5, 5);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 1; ctx.stroke();
        ctx.restore();

        // Border
        ctx.strokeStyle='rgba(255,255,255,0.25)'; ctx.lineWidth=1;
        ctx.beginPath(); ctx.arc(half,half,half-1,0,Math.PI*2); ctx.stroke();
        ctx.restore();

        // North indicator (rotates with camera)
        ctx.save();
        ctx.translate(half, half);
        ctx.rotate(cameraAngle);
        ctx.fillStyle='#ef4444'; ctx.font='bold 9px sans-serif'; ctx.textAlign='center';
        ctx.fillText('N', 0, -half+12);
        ctx.restore();
    },

    updateHintCounter() {
        const collected = typeof HintSystem !== 'undefined' ? HintSystem.collectedHints.length : 0;
        let el = document.getElementById('hint-counter');
        if (!el) {
            el = document.createElement('div');
            el.id = 'hint-counter';
            el.style.cssText = `
                position:fixed;
                right:calc(12px + env(safe-area-inset-right, 0px));
                top:calc(190px + env(safe-area-inset-top, 0px));
                background:rgba(0,0,0,0.5); backdrop-filter:blur(4px);
                padding:4px 10px; border-radius:12px;
                font-size:11px; color:#fbbf24; font-weight:700;
                z-index:25; pointer-events:none;
            `;
            document.body.appendChild(el);
        }
        el.textContent = '🔍 ' + collected + '/12';
    }
};
