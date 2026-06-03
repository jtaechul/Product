// hint.js — NPC 기반 힌트 수집 시스템 (구체 제거)

const HintSystem = window.HintSystem = {
    hints: [],          // legacy compatibility (empty)
    collectedHints: [], // {criminal, order, text}
    hintMeshes: [],     // empty
    interactDistance: 2.5,
    nearbyHint: null,   // legacy, always null
    memoOpen: false,

    // Story-driven hints — downtown citypack context (STEP 4)
    // Zone/marker 의존성 제거, 도심 분위기 텍스트로 작성
    criminalStories: {
        0: { // 1호 길동 — 학원 강사 출신
            name: '1호 납치범 (길동)',
            backstory: '도심 학원가에서 일하다 강제추행 의혹으로 해고된 학원 강사. 학원생들을 노리는 변태성 납치범.',
            chunks: [
                '그날 밤 도심 골목에서 한 남자가 어린 학생을 끌고 가는 걸 봤어요. 사람들이 잘 다니지 않는 좁은 골목이었어요.',
                '40대, 안경 쓴 마른 남자. 회색 코트 입고 있었어요. 이 근처에서 학원 강사로 일했다고 들었는데, 강제추행 의혹으로 잘렸다고 해요.',
                '도심 북쪽 좁은 골목 끝에 오래된 빌딩 옥탑방에서 자주 보인대요. 동네 사람들이 그러는데, 거기서 절대 마주치지 말라고 했어요.',
            ]
        },
        1: { // 2호 철수 — 위장 사업가
            name: '2호 납치범 (철수)',
            backstory: '도심 사무용 빌딩에서 무역회사 위장. 실제로는 미성년자 인신매매 중간상으로, 지하실에 아이들을 감금.',
            chunks: [
                '검은 정장에 볼 흉터 있는 남자. 도심 큰 사거리 빌딩에서 자주 봤어요. 항상 부하 두세 명이랑 같이 다녀요.',
                '낮에는 무역회사 사장 행세를 해요. 회사는 정상 영업하는 척하지만, 밤에는 이상한 사람들이 비상계단으로 드나든대요.',
                '그 빌딩 지하 주차장에서 의심스러운 일이 자주 일어나요. 새벽에 큰 화물차들이 짐을 옮긴다는 명목으로 드나들어요.',
                '지하실에서 비명 소리가 들린다고... 누가 신고하려 했지만 다음 날 회사 명의로 합의금 받고 입 다물렸다고 해요.',
            ]
        },
        2: { // 3호 영수 — 조직 두목
            name: '3호 납치범 (영수)',
            backstory: '도심 최대 빌딩 옥상에 본거지를 둔 인신매매 조직 두목. 헬기로 아이들을 다른 도시로 빼돌리는 가장 위험한 범인.',
            chunks: [
                '60대 험상궂은 남자. 도심 한복판 가장 높은 빌딩 근처에서 부하들이랑만 다녀요. 절대 혼자 다니지 않아요.',
                '본거지는 도심에서 가장 큰 빌딩 옥상이에요. 일반 출입은 막혀있고, 전용 엘리베이터로만 올라갈 수 있대요.',
                '눈썹에 큰 흉터, 짙은 수염. 그 자의 인상이에요. 못 본 사람이 행운이라고 할 만큼 무서운 표정이래요.',
                '옥상에서 헬기 소리가 자주 들려요. 새벽에 납치한 아이들을 인천이나 부산으로 빼돌릴 때 쓴다고 해요.',
                '다가가지 마세요. 그 자 부하들은 무장하고 있고, 한 번 마주친 사람은 살아 돌아오지 못한대요.',
            ]
        }
    },

    // Color/marker 룩업은 절차적 모드 폴백용으로 유지
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
        // citypack 모드는 placeholder 없는 도심 텍스트 그대로 사용
        // 절차적 모드는 zone feature로 치환 (폴백)
        const isCitypack = !window.location.search.includes('procedural=1');
        const features = window._hideoutFeatures || {};
        const zoneMap = { 0: 'RESIDENTIAL', 1: 'COMMERCIAL', 2: 'FACTORY' };
        for (let c = 0; c < 3; c++) {
            const story = this.criminalStories[c];
            if (!story) continue;
            if (isCitypack) {
                this.hintTexts[c] = story.chunks.slice(0, this.hintsRequired[c]);
            } else {
                const f = features[zoneMap[c]] || {};
                const colorName = this.colorNames[f.color] || '회색';
                const markerDesc = this.markerDescs[f.marker] || '특이한 표식';
                this.hintTexts[c] = story.chunks.map(chunk =>
                    chunk.replace('{color}', colorName).replace('{marker_desc}', markerDesc)
                ).slice(0, this.hintsRequired[c]);
            }
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
