// hint.js — NPC 기반 힌트 수집 시스템 (구체 제거)

const HintSystem = window.HintSystem = {
    hints: [],          // legacy compatibility (empty)
    collectedHints: [], // {criminal, order, text}
    hintMeshes: [],     // empty
    interactDistance: 2.5,
    nearbyHint: null,   // legacy, always null
    memoOpen: false,

    // Story-driven hints — generated per game from hideout features
    // Each criminal has a backstory + clues that reference the random features
    criminalStories: {
        0: { // 1호 길동 — 전직 학원 강사
            name: '1호 납치범 (길동)',
            backstory: '전직 학원 강사. 학교에서 해고된 후 분노를 아이들에게 풀고 있어요.',
            chunks: [
                '제가 그날 봤어요. 한 남자가 아이를 끌고 주택가로 가더라구요.',
                '40대 남자였어요. 안경 쓰고, 회색 코트를 입었어요. 학원에서 잘렸다는 소문이...',
                '주택가 안쪽 골목에 자주 나타나요. {color} 외벽 집이에요.',
                '그 집 앞에는 {marker_desc}가 있어요. 분명히 그 집이에요!',
            ]
        },
        1: { // 2호 철수 — 가짜 카페 사장
            name: '2호 납치범 (철수)',
            backstory: '겉으로는 카페 사장. 실제로는 미성년자 거래상.',
            chunks: [
                '상업지구에서 본 적 있어요. 검은 정장에 흉터가 있는 남자...',
                '낮에는 멀쩡한 가게를 운영하는 척하지만, 밤에는 이상한 사람들이 드나들어요.',
                '큰 도로 옆 빌딩이에요. {color} 외벽이고 키가 좀 큰 편이에요.',
                '간판이 {marker_desc}이에요. 그게 그 자의 위장 사업이에요.',
                '제가 한번 그 안을 봤는데 지하에서 비명 소리가...',
            ]
        },
        2: { // 3호 영수 — 폐공장의 비밀
            name: '3호 납치범 (영수)',
            backstory: '폐공장을 점거한 인신매매 조직 두목. 가장 위험한 범인.',
            chunks: [
                '공장지대... 거기에 그 자가 있어요. 험상궂은 60대 남자예요.',
                '폐공장 단지에 자기 조직이 있어요. 부하들이 많아서 조심하세요.',
                '{color} 외벽의 큰 건물이에요. 일반 공장보다 키가 커요.',
                '옥상에 특이한 게 있어요... {marker_desc}이 있어서 멀리서도 보여요.',
                '주변에는 굴뚝에서 매캐한 연기가 나는데, 그건 위장이에요.',
                '아이들을 거기서 트럭으로 옮긴다는 소문을 들었어요...',
            ]
        }
    },

    // Color name lookup (hex → Korean)
    colorNames: {
        0x4488cc: '파란색', 0x88cc44: '연두색', 0xcc6644: '주황색',
        0xaa44cc: '보라색', 0x44ccaa: '청록색', 0xcccc44: '노란색',
        0xf0f0e8: '흰색', 0xddccaa: '베이지색', 0xccaadd: '연보라색',
        0xaaccdd: '하늘색', 0xeecccc: '연분홍색',
        0x888888: '회색', 0x777733: '카키색', 0x664433: '갈색',
        0x553355: '진보라색', 0x336666: '청록회색'
    },
    markerDescs: {
        mailbox: '빨간 우체통', gnome: '난쟁이 정원 인형',
        birdhouse: '새집(birdhouse)', flowerpot: '큰 화분의 꽃들',
        cafe: 'CAFE 간판', neon: 'BAR 네온 간판',
        shop: 'SHOP 간판', clinic: 'CLINIC 간판',
        tank: '옥상의 빨간 물탱크', antenna: '높은 통신 안테나',
        silo: '거대한 곡물 사일로', crane: '노란색 타워 크레인'
    },

    // Generated per-game from world's _hideoutFeatures
    hintTexts: { 0: [], 1: [], 2: [] },

    criminalNames: ['1호 납치범 (길동)', '2호 납치범 (철수)', '3호 납치범 (영수)'],

    hintsRequired: [3, 4, 5],

    init(scene) {
        this.scene = scene;
        this.collectedHints = [];
        this.nearbyHint = null;
        this.generateHintTexts();
        this.createMemoUI();
        this.createPopupUI();
    },

    generateHintTexts() {
        // Build hints from criminal stories + hideout features
        const features = window._hideoutFeatures || {};
        const zoneMap = { 0: 'RESIDENTIAL', 1: 'COMMERCIAL', 2: 'FACTORY' };
        for (let c = 0; c < 3; c++) {
            const story = this.criminalStories[c];
            if (!story) continue;
            const f = features[zoneMap[c]] || {};
            const colorName = this.colorNames[f.color] || '회색';
            const markerDesc = this.markerDescs[f.marker] || '특이한 표식';
            this.hintTexts[c] = story.chunks.map(chunk =>
                chunk.replace('{color}', colorName).replace('{marker_desc}', markerDesc)
            );
            // Take only as many as hintsRequired allows
            this.hintTexts[c] = this.hintTexts[c].slice(0, this.hintsRequired[c]);
        }
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

        // hint-popup disabled — NPC dialog already shows the hint to prevent overlap

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
