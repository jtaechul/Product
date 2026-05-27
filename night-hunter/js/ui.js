// ui.js — 미니맵 + 전체 UI (8단계)

const GameUI = {
    minimapCanvas: null,
    minimapCtx: null,
    minimapSize: 120,

    init() {
        this.createMinimap();
        this.createActionButtons();
    },

    createMinimap() {
        const container = document.createElement('div');
        container.id = 'minimap-container';
        container.style.cssText = `
            position:fixed; right:16px; bottom:90px;
            width:${this.minimapSize}px; height:${this.minimapSize}px;
            border-radius:50%; overflow:hidden;
            border:2px solid rgba(255,255,255,0.3);
            background:rgba(0,0,0,0.5);
            z-index:30; pointer-events:none;
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

    updateMinimap(playerPos, playerAngle) {
        const ctx = this.minimapCtx;
        const size = this.minimapSize;
        const half = size / 2;
        const scale = size / 80;

        ctx.clearRect(0, 0, size, size);

        // Background circle
        ctx.save();
        ctx.beginPath();
        ctx.arc(half, half, half, 0, Math.PI * 2);
        ctx.clip();

        ctx.fillStyle = '#1a2e1a';
        ctx.fillRect(0, 0, size, size);

        // Roads
        ctx.strokeStyle = 'rgba(80,80,80,0.6)';
        ctx.lineWidth = 2;
        const roads = [
            { x1: -150, z1: 50, x2: 150, z2: 50, w: 8 },
            { x1: 0, z1: -150, x2: 0, z2: 150, w: 8 },
            { x1: -100, z1: -40, x2: 100, z2: -40, w: 6 },
        ];
        roads.forEach(r => {
            const sx = half + (r.x1 - playerPos.x) * scale;
            const sy = half + (r.z1 - playerPos.z) * scale;
            const ex = half + (r.x2 - playerPos.x) * scale;
            const ey = half + (r.z2 - playerPos.z) * scale;
            ctx.beginPath();
            ctx.moveTo(sx, sy);
            ctx.lineTo(ex, ey);
            ctx.stroke();
        });

        // Buildings
        buildingData.forEach(b => {
            const bx = half + ((b.x || 0) - playerPos.x) * scale;
            const bz = half + ((b.z || 0) - playerPos.z) * scale;
            const bw = (b.w || 6) * scale;
            const bd = (b.d || 6) * scale;

            if (bx < -20 || bx > size + 20 || bz < -20 || bz > size + 20) return;

            if (b.type === 'hideout') {
                ctx.fillStyle = 'rgba(255,60,60,0.6)';
            } else if (b.type === 'police') {
                ctx.fillStyle = 'rgba(30,100,200,0.7)';
            } else {
                ctx.fillStyle = 'rgba(150,150,150,0.4)';
            }
            ctx.fillRect(bx - bw / 2, bz - bd / 2, bw, bd);
        });

        // Hints (star markers)
        if (typeof HintSystem !== 'undefined') {
            HintSystem.hints.forEach(h => {
                if (h.collected) return;
                const hx = half + (h.x - playerPos.x) * scale;
                const hz = half + (h.z - playerPos.z) * scale;
                if (hx < -10 || hx > size + 10 || hz < -10 || hz > size + 10) return;

                const showOnMap = (typeof Shop !== 'undefined' && Shop.hasItem('radio')) || gameState.isDay;
                if (showOnMap && gameState.isDay) {
                    ctx.fillStyle = '#fbbf24';
                    ctx.font = 'bold 10px sans-serif';
                    ctx.textAlign = 'center';
                    ctx.fillText('★', hx, hz + 4);
                }
            });
        }

        // Enemies (at night)
        if (!gameState.isDay && typeof EnemySystem !== 'undefined') {
            EnemySystem.enemies.forEach(e => {
                if (e.arrested || e.state === 'hidden') return;
                const ex = half + (e.currentX - playerPos.x) * scale;
                const ez = half + (e.currentZ - playerPos.z) * scale;
                if (ex < -10 || ex > size + 10 || ez < -10 || ez > size + 10) return;

                ctx.fillStyle = '#ff3333';
                ctx.beginPath();
                ctx.arc(ex, ez, 3, 0, Math.PI * 2);
                ctx.fill();
            });
        }

        // Shop NPC
        if (typeof Shop !== 'undefined') {
            const sx = half + (Shop.shopX - playerPos.x) * scale;
            const sz = half + (Shop.shopZ - playerPos.z) * scale;
            if (sx > -10 && sx < size + 10 && sz > -10 && sz < size + 10) {
                ctx.fillStyle = '#3b82f6';
                ctx.beginPath();
                ctx.arc(sx, sz, 3, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        // Player (blue triangle pointing forward)
        ctx.save();
        ctx.translate(half, half);
        ctx.rotate(playerAngle);
        ctx.fillStyle = '#60a5fa';
        ctx.beginPath();
        ctx.moveTo(0, -6);
        ctx.lineTo(-4, 4);
        ctx.lineTo(4, 4);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.restore();

        // Border circle
        ctx.strokeStyle = 'rgba(255,255,255,0.2)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(half, half, half - 1, 0, Math.PI * 2);
        ctx.stroke();

        ctx.restore();
    },

    updateHintCounter() {
        const collected = typeof HintSystem !== 'undefined' ? HintSystem.collectedHints.length : 0;
        let el = document.getElementById('hint-counter');
        if (!el) {
            el = document.createElement('div');
            el.id = 'hint-counter';
            el.style.cssText = `
                position:fixed; right:16px; bottom:220px;
                background:rgba(0,0,0,0.5); backdrop-filter:blur(4px);
                padding:4px 12px; border-radius:12px;
                font-size:12px; color:#fbbf24; font-weight:700;
                z-index:30; pointer-events:none;
            `;
            document.body.appendChild(el);
        }
        el.textContent = '🔍 ' + collected + '/9';
    }
};
