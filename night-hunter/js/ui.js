// ui.js — 미니맵 + 전체 UI (8단계)

const GameUI = {
    minimapCanvas: null,
    minimapCtx: null,
    minimapSize: 120,

    init() {
        this.createMinimap();
        this.createActionButtons();
        this.createLandscapeOverlay();
    },

    createMinimap() {
        const container = document.createElement('div');
        container.id = 'minimap-container';
        container.style.cssText = `
            position:fixed; right:12px; top:60px;
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
        const memoBtn = document.getElementById('btn-memo');
        if (!memoBtn) {
            const mb = document.createElement('button');
            mb.className = 'action-btn';
            mb.id = 'btn-memo-ui';
            mb.textContent = '📋';
            mb.style.background = 'rgba(59,130,246,0.25)';
            mb.style.borderColor = 'rgba(59,130,246,0.5)';
            mb.style.pointerEvents = 'auto';
            mb.addEventListener('click', () => HintSystem.toggleMemo());
            mb.addEventListener('touchstart', e => { e.preventDefault(); HintSystem.toggleMemo(); }, { passive: false });
            document.getElementById('action-buttons').appendChild(mb);
        }
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
        const scale = size / 80;

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

        // Hints removed from minimap (player must explore)

        // Enemies
        if (!gameState.isDay&&typeof EnemySystem!=='undefined') {
            EnemySystem.enemies.forEach(e => {
                if (e.arrested||e.state==='hidden') return;
                const ex=mx(e.currentX), ez=mz(e.currentZ);
                if (ex<-10||ex>size+10||ez<-10||ez>size+10) return;
                ctx.fillStyle='#ff3333'; ctx.beginPath(); ctx.arc(ex,ez,3,0,Math.PI*2); ctx.fill();
            });
        }

        // Shop
        if (typeof Shop!=='undefined') {
            const sx=mx(Shop.shopX), sz=mz(Shop.shopZ);
            if (sx>-10&&sx<size+10&&sz>-10&&sz<size+10) { ctx.fillStyle='#3b82f6'; ctx.beginPath(); ctx.arc(sx,sz,3,0,Math.PI*2); ctx.fill(); }
        }

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
                position:fixed; right:12px; top:190px;
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
