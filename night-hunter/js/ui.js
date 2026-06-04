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
            z-index:25; pointer-events:auto;
            cursor:pointer;
        `;
        container.title = '클릭하여 전체 지도 보기';
        const canvas = document.createElement('canvas');
        canvas.id = 'minimap';
        canvas.width = this.minimapSize;
        canvas.height = this.minimapSize;
        canvas.style.cssText = 'width:100%;height:100%; pointer-events:none;';
        container.appendChild(canvas);
        document.body.appendChild(container);

        this.minimapCanvas = canvas;
        this.minimapCtx = canvas.getContext('2d');

        // 클릭으로 전체 지도 모달 열기
        const openFull = (e) => { e?.preventDefault?.(); this.openFullMap(); };
        container.addEventListener('click', openFull);
        container.addEventListener('touchend', openFull);

        // 전체 지도 모달 생성 (초기 hidden)
        this._createFullMapModal();
    },

    _createFullMapModal() {
        const modal = document.createElement('div');
        modal.id = 'fullmap-modal';
        modal.style.cssText = `
            display:none; position:fixed; inset:0; z-index:240;
            background:rgba(0,0,0,0.85); backdrop-filter:blur(8px);
            padding:env(safe-area-inset-top,16px) env(safe-area-inset-right,16px)
                    env(safe-area-inset-bottom,16px) env(safe-area-inset-left,16px);
            justify-content:center; align-items:center;
            font-family:'Inter',sans-serif;
        `;
        modal.innerHTML = `
            <div style="display:flex; flex-direction:column; align-items:center; gap:8px;
                width:min(92vw, 92vh); max-height:96vh;">
                <div style="position:relative; width:100%; aspect-ratio:1/1;
                    max-height:calc(96vh - 110px);">
                    <canvas id="fullmap-canvas" style="width:100%; height:100%; display:block;
                        background:rgba(15,23,42,0.95); border:2px solid rgba(255,255,255,0.25);
                        border-radius:14px; box-shadow:0 20px 60px rgba(0,0,0,0.7);"></canvas>
                    <button id="fullmap-close" style="
                        position:absolute; top:8px; right:8px;
                        width:40px; height:40px; border-radius:50%;
                        background:rgba(15,23,42,0.85); color:#fff; border:1px solid rgba(255,255,255,0.2);
                        cursor:pointer; font-size:18px; font-weight:700;
                        display:flex; align-items:center; justify-content:center;
                    ">✕</button>
                    <div style="position:absolute; top:14px; left:18px;
                        font-size:11px; letter-spacing:3px; color:#60a5fa; font-weight:700;">
                        FULL MAP
                    </div>
                </div>
                <div style="width:100%;
                    display:flex; flex-direction:column; gap:6px;
                    background:rgba(15,23,42,0.85); backdrop-filter:blur(6px);
                    border:1px solid rgba(255,255,255,0.15); border-radius:10px;
                    padding:8px 10px; font-family:'Inter',sans-serif;">
                    <div style="display:flex; gap:6px 14px; flex-wrap:wrap; justify-content:center;">
                        <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#fff;font-weight:600;white-space:nowrap;">
                            <span style="display:inline-block;width:11px;height:11px;background:rgba(200,200,200,0.85);border-radius:2px;border:1px solid rgba(255,255,255,0.3);"></span>건물
                        </span>
                        <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#fff;font-weight:600;white-space:nowrap;">
                            <span style="display:inline-block;width:11px;height:11px;background:rgba(60,60,60,0.9);border-radius:2px;border:1px solid rgba(255,255,255,0.3);"></span>도로/골목
                        </span>
                        <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#fff;font-weight:600;white-space:nowrap;">
                            <span style="display:inline-block;width:11px;height:11px;background:rgba(30,100,220,0.95);border-radius:50%;border:1.5px solid #fff;"></span>🚔 경찰서
                        </span>
                    </div>
                    <div style="display:flex; gap:6px 14px; flex-wrap:wrap; justify-content:center;">
                        <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#e2e8f0;font-weight:600;white-space:nowrap;">
                            <span style="display:inline-block;width:11px;height:11px;background:#fbbf24;border-radius:50%;border:1px solid #fff;"></span>수배범
                        </span>
                        <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#e2e8f0;font-weight:600;white-space:nowrap;">
                            <span style="display:inline-block;width:11px;height:11px;background:#86efac;border-radius:50%;border:1px solid #fff;"></span>목격자
                        </span>
                        <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#e2e8f0;font-weight:600;white-space:nowrap;">
                            <span style="display:inline-block;width:11px;height:11px;background:#ff3333;border-radius:50%;border:1px solid #fff;"></span>납치범
                        </span>
                        <span style="display:flex;align-items:center;gap:5px;font-size:11px;color:#60a5fa;font-weight:600;white-space:nowrap;">
                            <span style="display:inline-block;width:0;height:0;border-left:6px solid transparent;border-right:6px solid transparent;border-bottom:10px solid #3a82d4;"></span>나
                        </span>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        const close = () => { modal.style.display = 'none'; this._fullMapOpen = false; };
        document.getElementById('fullmap-close').addEventListener('click', close);
        modal.addEventListener('click', e => { if (e.target === modal) close(); });

        this.fullMapCanvas = document.getElementById('fullmap-canvas');
        this.fullMapCtx = this.fullMapCanvas.getContext('2d');
        this._fullMapOpen = false;
    },

    openFullMap() {
        const modal = document.getElementById('fullmap-modal');
        if (!modal) return;
        modal.style.display = 'flex';
        this._fullMapOpen = true;
        // 캔버스 해상도를 화면 크기에 맞춤 (transform 리셋 — 반복 호출 시 scale 누적 방지)
        const rect = this.fullMapCanvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        this.fullMapCanvas.width = rect.width * dpr;
        this.fullMapCanvas.height = rect.height * dpr;
        this.fullMapCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    },

    drawFullMap(playerPos, playerAngle) {
        if (!this._fullMapOpen || !this.fullMapCtx) return;
        const ctx = this.fullMapCtx;
        const c = this.fullMapCanvas;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        // 캔버스가 정사각형이 아닐 수 있음 → 가로/세로 모두 사용해 fit
        const sizeW = c.width / dpr;
        const sizeH = c.height / dpr;
        const W = (typeof WORLD_SIZE !== 'undefined') ? WORLD_SIZE : 300;
        const scale = Math.min(sizeW, sizeH) / W;  // 작은 쪽에 맞춰 전체 월드 표시
        const cx = sizeW / 2;
        const cy = sizeH / 2;
        const wx = (x) => cx + x * scale;
        const wz = (z) => cy + z * scale;

        ctx.clearRect(0, 0, sizeW, sizeH);

        // citypack 전체지도: 도시 전체를 한 화면에 fit
        if (window._citypackCollision) {
            const boxes = window._citypackCollision;
            const cb = window._citypackBounds || { minX: -300, maxX: 300, minZ: -300, maxZ: 300 };
            const cityW = cb.maxX - cb.minX;
            const cityD = cb.maxZ - cb.minZ;
            const cityScale = Math.min(sizeW / cityW, sizeH / cityD) * 0.92;
            const cityCX = (cb.minX + cb.maxX) / 2;
            const cityCZ = (cb.minZ + cb.maxZ) / 2;
            const cwx = (x) => sizeW / 2 + (x - cityCX) * cityScale;
            const cwz = (z) => sizeH / 2 + (z - cityCZ) * cityScale;

            // 도로 톤 배경
            ctx.fillStyle = '#3a3a3a';
            ctx.fillRect(0, 0, sizeW, sizeH);
            // 건물 — fill만 (외곽선 없이 인접 건물 자연스럽게 합쳐 보임)
            ctx.fillStyle = 'rgba(225,215,195,0.95)';
            boxes.forEach(b => {
                const x = cwx(b.minX), z = cwz(b.minZ);
                const w = (b.maxX - b.minX) * cityScale;
                const h = (b.maxZ - b.minZ) * cityScale;
                ctx.fillRect(x - 0.5, z - 0.5, w + 1, h + 1);
            });
            // 경찰서 (가장 눈에 띄게)
            if (window._policeStation) {
                const px = cwx(window._policeStation.x);
                const pz = cwz(window._policeStation.z);
                ctx.fillStyle = 'rgba(30,100,220,0.3)';
                ctx.beginPath();
                ctx.arc(px, pz, 18, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = 'rgba(30,120,240,1)';
                ctx.beginPath();
                ctx.arc(px, pz, 9, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2.5;
                ctx.stroke();
                ctx.font = 'bold 14px Inter';
                ctx.textAlign = 'center';
                ctx.fillStyle = '#fff';
                ctx.strokeStyle = 'rgba(0,0,0,0.8)';
                ctx.lineWidth = 3;
                ctx.strokeText('🚔 경찰서', px, pz - 18);
                ctx.fillText('🚔 경찰서', px, pz - 18);
            }
            // NPC/적 (무전기 보유 시)
            const hasRadio = typeof Shop !== 'undefined' && Shop.hasItem('radio');
            if (hasRadio && typeof NPCSystem !== 'undefined') {
                NPCSystem.npcs.forEach(n => {
                    if (!n.mesh || !n.mesh.visible || n.caught) return;
                    const nx = cwx(n.mesh.position.x), nz = cwz(n.mesh.position.z);
                    if (n.role === 'suspect') {
                        ctx.fillStyle = '#fbbf24';
                    } else if (n.assignment) {
                        ctx.fillStyle = '#86efac';
                    } else return;
                    ctx.beginPath();
                    ctx.arc(nx, nz, 4, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.strokeStyle = '#fff';
                    ctx.lineWidth = 1;
                    ctx.stroke();
                });
                if (typeof EnemySystem !== 'undefined') {
                    EnemySystem.enemies.forEach(e => {
                        if (!e.mesh || !e.mesh.visible || e.arrested) return;
                        const ex = cwx(e.mesh.position.x), ez = cwz(e.mesh.position.z);
                        ctx.fillStyle = '#ff3333';
                        ctx.beginPath();
                        ctx.arc(ex, ez, 5, 0, Math.PI * 2);
                        ctx.fill();
                        ctx.strokeStyle = '#fff';
                        ctx.lineWidth = 1.5;
                        ctx.stroke();
                    });
                }
            }
            // 플레이어 화살표
            ctx.save();
            ctx.translate(cwx(playerPos.x), cwz(playerPos.z));
            ctx.rotate(Math.PI - playerAngle);
            ctx.fillStyle = '#3a82d4';
            ctx.beginPath();
            ctx.moveTo(0, -12);
            ctx.lineTo(8, 8);
            ctx.lineTo(-8, 8);
            ctx.closePath();
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.restore();
            return;
        }

        // 절차적 모드: 기존 표시
        ctx.fillStyle = '#1a2e1a';
        ctx.fillRect(0, 0, sizeW, sizeH);
        ctx.strokeStyle = 'rgba(120,120,120,0.5)';
        ctx.lineWidth = 3;
        const mainRoads = [
            [-150, 95, 150, 95], [-150, 50, 150, 50], [-150, 5, 150, 5],
            [-150, -45, 150, -45], [-150, -85, 150, -85], [-150, -135, 150, -135],
            [0, -140, 0, 90], [-50, -100, -50, 100], [50, -100, 50, 100],
            [-100, -90, -100, 90], [100, -90, 100, 90]
        ];
        mainRoads.forEach(([x1,z1,x2,z2]) => {
            ctx.beginPath(); ctx.moveTo(wx(x1), wz(z1)); ctx.lineTo(wx(x2), wz(z2)); ctx.stroke();
        });
        if (typeof buildingData !== 'undefined') {
            buildingData.forEach(b => {
                const bx = b.x || 0, bz = b.z || 0;
                const bw = (b.w || 6) * scale, bd = (b.d || 6) * scale;
                if (b.type === 'police') ctx.fillStyle = 'rgba(30,100,200,0.95)';
                else if (b.zone === 'POLICE') ctx.fillStyle = 'rgba(180,140,80,0.75)';
                else if (b.zone === 'RESIDENTIAL') ctx.fillStyle = 'rgba(180,140,80,0.75)';
                else if (b.zone === 'COMMERCIAL') ctx.fillStyle = 'rgba(80,200,180,0.75)';
                else if (b.zone === 'FACTORY') ctx.fillStyle = 'rgba(120,120,120,0.75)';
                else ctx.fillStyle = 'rgba(150,150,150,0.55)';
                ctx.fillRect(wx(bx) - bw / 2, wz(bz) - bd / 2, bw, bd);
            });
        }
        // 무전기 보유 시 힌트 NPC / 납치범 표시
        const hasRadio = typeof Shop !== 'undefined' && Shop.hasItem('radio');
        if (hasRadio && gameState.isDay && typeof NPCSystem !== 'undefined') {
            NPCSystem.npcs.forEach(n => {
                if (n.role === 'suspect') {
                    if (n.caught) return;
                    ctx.fillStyle = '#fbbf24';
                } else if (n.role === 'civilian') {
                    if (n.visited || !n.assignment) return;
                    ctx.fillStyle = '#86efac';
                } else return;
                ctx.beginPath(); ctx.arc(wx(n.mesh.position.x), wz(n.mesh.position.z), 6, 0, Math.PI*2); ctx.fill();
                ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke();
            });
        }
        if (hasRadio && !gameState.isDay && typeof EnemySystem !== 'undefined') {
            EnemySystem.enemies.forEach(e => {
                if (e.arrested) return;
                if (typeof HintSystem !== 'undefined' && !HintSystem.hasAllHintsFor(e.id)) return;
                ctx.fillStyle = '#ff3333';
                ctx.beginPath(); ctx.arc(wx(e.currentX), wz(e.currentZ), 6, 0, Math.PI*2); ctx.fill();
                ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke();
            });
        }
        // 플레이어 (큰 화살표)
        ctx.save();
        ctx.translate(wx(playerPos.x), wz(playerPos.z));
        ctx.rotate(Math.PI - playerAngle);
        ctx.fillStyle = '#60a5fa';
        ctx.beginPath();
        ctx.moveTo(0, -12); ctx.lineTo(-9, 9); ctx.lineTo(9, 9);
        ctx.closePath(); ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
        ctx.restore();
        // 북쪽 표시
        ctx.fillStyle = '#ef4444'; ctx.font = 'bold 16px sans-serif'; ctx.textAlign = 'center';
        ctx.fillText('N', size / 2, 22);
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

        // STEP 5: 수배 전단(📜) 버튼 제거됨
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

        // citypack 미니맵: 도로 어두운 배경 + 건물 단일 fill (외곽선 없음 → 인접 건물 자연스럽게 합쳐 보임)
        if (window._citypackCollision) {
            // 1) 도로 배경
            ctx.fillStyle = '#3a3a3a';
            ctx.fillRect(0, 0, size, size);
            // 2) 건물 — fill만 (외곽선 X → 붙은 건물 합쳐서 보임)
            ctx.fillStyle = 'rgba(225,215,195,0.95)';
            window._citypackCollision.forEach(b => {
                const x1 = mx(b.minX), x2 = mx(b.maxX);
                const z1 = mz(b.minZ), z2 = mz(b.maxZ);
                const w = x2 - x1, h = z2 - z1;
                if (x2 < -5 || x1 > size + 5 || z2 < -5 || z1 > size + 5) return;
                ctx.fillRect(x1 - 0.5, z1 - 0.5, w + 1, h + 1); // 0.5 overlap → 인접 박스 사이 틈 없앰
            });
            // 3) 경찰서: 파란 펄스 (가까울수록 큼, 멀어도 보이게 살짝 크게)
            if (window._policeStation) {
                const psx = mx(window._policeStation.x);
                const psz = mz(window._policeStation.z);
                // glow ring
                ctx.fillStyle = 'rgba(30,100,220,0.25)';
                ctx.beginPath();
                ctx.arc(psx, psz, 11, 0, Math.PI * 2);
                ctx.fill();
                // main dot
                ctx.fillStyle = 'rgba(30,120,240,1)';
                ctx.beginPath();
                ctx.arc(psx, psz, 6, 0, Math.PI * 2);
                ctx.fill();
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2;
                ctx.stroke();
            }
        } else {
            // 절차적 모드: 기존 도로/건물 표시
            ctx.strokeStyle = 'rgba(80,80,80,0.6)';
            ctx.lineWidth = 2;
            [[- 150, 50, 150, 50], [0, -150, 0, 150], [-100, -40, 100, -40]].forEach(([x1,z1,x2,z2]) => {
                ctx.beginPath(); ctx.moveTo(mx(x1), mz(z1)); ctx.lineTo(mx(x2), mz(z2)); ctx.stroke();
            });
            buildingData.forEach(b => {
                const bx = mx(b.x||0), bz = mz(b.z||0);
                const bw = (b.w||6)*scale, bd = (b.d||6)*scale;
                if (bx<-30||bx>size+30||bz<-30||bz>size+30) return;
                if (b.type==='police') ctx.fillStyle='rgba(30,100,200,0.85)';
                else if (b.zone==='POLICE') ctx.fillStyle='rgba(180,140,80,0.6)';
                else if (b.zone==='RESIDENTIAL') ctx.fillStyle='rgba(180,140,80,0.6)';
                else if (b.zone==='COMMERCIAL') ctx.fillStyle='rgba(80,200,180,0.6)';
                else if (b.zone==='FACTORY') ctx.fillStyle='rgba(120,120,120,0.6)';
                else ctx.fillStyle='rgba(150,150,150,0.4)';
                ctx.fillRect(bx-bw/2, bz-bd/2, bw, bd);
            });
        }

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

        // [낮] 힌트 제공 NPC 위치 — 수배범(suspect): 미검거 / 목격자(civilian): 미대화+힌트보유
        if (hasRadio && gameState.isDay && typeof NPCSystem !== 'undefined') {
            NPCSystem.npcs.forEach(n => {
                if (n.role === 'suspect') {
                    if (n.caught) return;
                    drawHintMarker(n.mesh.position.x, n.mesh.position.z, '#fbbf24');
                } else if (n.role === 'civilian') {
                    if (n.visited) return;      // 이미 대화함 — 힌트 획득 완료
                    if (!n.assignment) return;  // 힌트 없는 시민 제외
                    drawHintMarker(n.mesh.position.x, n.mesh.position.z, '#86efac');
                }
            });
        }

        // [밤] 납치범(enemy) — 단서 수집 완료(revealed) + 미검거인 경우만 표시
        if (hasRadio && !gameState.isDay && typeof EnemySystem !== 'undefined') {
            EnemySystem.enemies.forEach(e => {
                if (e.arrested) return;
                if (typeof HintSystem !== 'undefined' && !HintSystem.hasAllHintsFor(e.id)) return;
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
