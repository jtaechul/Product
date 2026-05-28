// hint.js — NPC 기반 힌트 수집 시스템 (구체 제거)

const HintSystem = {
    hints: [],          // legacy compatibility (empty)
    collectedHints: [], // {criminal, order, text}
    hintMeshes: [],     // empty
    interactDistance: 2.5,
    nearbyHint: null,   // legacy, always null
    memoOpen: false,

    // Hints generated dynamically per game — NPCs distribute them
    hintTexts: {
        0: [
            '주택가 어딘가에 있는 집이에요...',
            '파란색 외벽이 인상적이었어요.',
            '3층짜리 단독주택이에요.',
            '집 앞에 빨간 우체통이 있어요.',
        ],
        1: [
            '상업지구 빌딩 중 하나예요.',
            '외벽이 흰색인 건물이에요.',
            '5층 정도 되는 건물이었어요.',
            'CAFE 간판이 크게 걸려있어요.',
            '큰 도로 옆에 있는 건물이에요.',
        ],
        2: [
            '공장지대 쪽에 있는 건물이에요...',
            '회색 콘크리트 외벽이에요.',
            '7층 정도로 꽤 높아요.',
            '옥상에 빨간 물탱크가 있어요.',
            '주변에 굴뚝이 있는 공장이에요.',
            '철조망이 둘러진 곳 안쪽이에요.',
        ]
    },

    criminalNames: ['1호 납치범 (길동)', '2호 납치범 (철수)', '3호 납치범 (영수)'],

    hintsRequired: [3, 4, 5], // total hints needed per criminal

    init(scene) {
        this.scene = scene;
        this.collectedHints = [];
        this.nearbyHint = null;
        this.createMemoUI();
        this.createPopupUI();
    },

    createMemoUI() {
        const memoPanel = document.createElement('div');
        memoPanel.id = 'memo-panel';
        memoPanel.style.cssText = `
            display: none;
            position: fixed;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            width: 360px; max-width: 92vw;
            max-height: 80vh;
            background: linear-gradient(135deg, rgba(15,23,42,0.97), rgba(30,41,59,0.97));
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 16px;
            padding: 22px;
            z-index: 50;
            overflow-y: auto;
            color: #fff;
            font-family: 'Inter', sans-serif;
            box-shadow: 0 12px 40px rgba(0,0,0,0.6);
        `;
        memoPanel.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                <h3 style="margin:0; font-size:18px; font-weight:800;">📋 수사 노트</h3>
                <button id="memo-close" style="background:none; border:none; color:#94a3b8; font-size:22px; cursor:pointer; padding:4px;">✕</button>
            </div>
            <div id="memo-content"></div>
            <div style="margin-top:16px; text-align:center; opacity:0.6; font-size:12px; letter-spacing:1px;">
                수집한 단서: <span id="memo-count">0</span>/12
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
            background: linear-gradient(135deg, rgba(15,23,42,0.97), rgba(30,41,59,0.97));
            backdrop-filter: blur(12px);
            border: 2px solid #fbbf24;
            border-radius: 16px;
            padding: 26px 36px;
            z-index: 60;
            text-align: center;
            color: #fff;
            font-family: 'Inter', sans-serif;
            animation: msgIn 0.3s ease;
            max-width: 85vw;
            box-shadow: 0 12px 40px rgba(0,0,0,0.6);
        `;
        popup.innerHTML = `
            <div style="font-size:13px; color:#fbbf24; margin-bottom:8px; letter-spacing:2px;" id="hint-popup-criminal"></div>
            <div style="font-size:17px; font-weight:700; line-height:1.5;" id="hint-popup-text"></div>
            <div style="margin-top:10px; font-size:11px; opacity:0.6; letter-spacing:1px;">+10 코인</div>
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
        const colors = ['#ef4444', '#f97316', '#a855f7'];

        for (let c = 0; c < 3; c++) {
            const criminalHints = this.collectedHints.filter(h => h.criminal === c);
            const total = this.hintsRequired[c];

            html += `<div style="margin-bottom:14px; padding:14px; background:rgba(255,255,255,0.04); border-radius:12px; border-left:3px solid ${colors[c]};">`;
            html += `<div style="font-size:13px; font-weight:800; color:${colors[c]}; margin-bottom:10px; letter-spacing:1px;">${this.criminalNames[c]} (${criminalHints.length}/${total})</div>`;

            for (let o = 0; o < total; o++) {
                const found = criminalHints.find(h => h.order === o);
                if (found) {
                    html += `<div style="font-size:13px; padding:5px 0; color:#e2e8f0;">✓ ${found.text}</div>`;
                } else {
                    html += `<div style="font-size:13px; padding:5px 0; color:#475569;">— ???</div>`;
                }
            }

            if (criminalHints.length >= total) {
                html += `<div style="margin-top:8px; padding:6px 10px; background:${colors[c]}33; border-radius:6px; font-size:11px; color:${colors[c]}; font-weight:700;">▶ 은거지 위치 파악 완료! 밤이 되면 출현합니다.</div>`;
            }
            html += '</div>';
        }
        content.innerHTML = html;
        document.getElementById('memo-count').textContent = this.collectedHints.length;
    },

    // No floating hint orbs anymore — kept for compatibility
    update(playerPos, delta, time) {
        // nothing — hints come from NPCs now
    },

    hideInteractPrompt() {
        this.hidePrompt();
    },

    showPrompt(text) {
        let el = document.getElementById('interact-prompt');
        if (!el) {
            el = document.createElement('div');
            el.id = 'interact-prompt';
            el.style.cssText = `
                position:fixed; top:38%; left:50%; transform:translate(-50%,-50%);
                background:rgba(0,0,0,0.82); backdrop-filter:blur(4px);
                padding:6px 14px; border-radius:14px; border:1px solid rgba(255,220,0,0.4);
                font-size:12px; color:#fbbf24; font-weight:700; z-index:35;
                pointer-events:none; white-space:nowrap;
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

    // Called by NPC system when player receives a hint
    collectHintFromNPC(criminal, order, text) {
        // Avoid duplicates
        if (this.collectedHints.some(h => h.criminal === criminal && h.order === order)) {
            return false;
        }
        this.collectedHints.push({ criminal, order, text });
        gameState.hintsCollected = this.collectedHints.length;
        gameState.coins += 10;
        if (typeof SoundManager !== 'undefined') SoundManager.playSFX('collect');

        const popup = document.getElementById('hint-popup');
        document.getElementById('hint-popup-criminal').textContent =
            this.criminalNames[criminal] + ' — 단서 ' + (order + 1) + '/' + this.hintsRequired[criminal];
        document.getElementById('hint-popup-text').textContent = '"' + text + '"';
        popup.style.display = 'block';
        setTimeout(() => { popup.style.display = 'none'; }, 2500);

        // Check if all hints for this criminal collected
        const crimHints = this.collectedHints.filter(h => h.criminal === criminal);
        if (crimHints.length === this.hintsRequired[criminal]) {
            setTimeout(() => {
                showMessage('📻 ' + this.criminalNames[criminal] + ' 은거지 파악 완료!\n밤이 되면 출현합니다.');
            }, 2600);
            if (typeof EnemySystem !== 'undefined') EnemySystem.markRevealed(criminal);
        }

        return true;
    },

    hasAllHintsFor(criminal) {
        return this.collectedHints.filter(h => h.criminal === criminal).length >= this.hintsRequired[criminal];
    },

    reset() {
        this.collectedHints = [];
        this.memoOpen = false;
        const panel = document.getElementById('memo-panel');
        if (panel) panel.style.display = 'none';
    }
};
