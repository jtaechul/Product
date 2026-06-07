// shop.js — 상점 & 인벤토리 (7단계)

const Shop = window.Shop = {
    isOpen: false,
    shopNpcMesh: null,
    shopDistance: 3,
    shopX: 20,
    shopZ: 90,

    items: [
        { id: 'flashlight', name: '🔦 고성능 손전등', desc: '탐색 범위 2배', price: 30, type: 'passive', owned: false },
        { id: 'drink', name: '💊 에너지 드링크', desc: '스태미나 완전 회복, 체력 +2', price: 20, type: 'consumable', count: 0 },
        { id: 'vest', name: '🧥 방탄 조끼', desc: '검거 실패 피해 50% 감소', price: 50, type: 'passive', owned: false },
        { id: 'radio', name: '📡 무전기', desc: '미니맵에 힌트 위치 표시', price: 40, type: 'passive', owned: false },
        { id: 'shoes', name: '👟 러닝화', desc: '이동속도 +20% 영구', price: 35, type: 'passive', owned: false }
    ],

    inventory: [],

    init(scene) {
        this.scene = scene;
        // No more standalone shop NPC — police station handles shopping
        this.createShopUI();
        this.createInventoryUI();
    },

    createShopNpc() {
        const group = new THREE.Group();

        // Body (blue capsule-like)
        const body = new THREE.Mesh(
            new THREE.CylinderGeometry(0.4, 0.35, 1.2, 12),
            new THREE.MeshStandardMaterial({ color: 0x2563eb })
        );
        body.position.y = 1.0;
        body.castShadow = true;
        group.add(body);

        // Head
        const head = new THREE.Mesh(
            new THREE.SphereGeometry(0.3, 16, 16),
            new THREE.MeshStandardMaterial({ color: 0xffdbac })
        );
        head.position.y = 1.85;
        head.castShadow = true;
        group.add(head);

        // Hat
        const hat = new THREE.Mesh(
            new THREE.CylinderGeometry(0.15, 0.35, 0.25, 12),
            new THREE.MeshStandardMaterial({ color: 0x2563eb })
        );
        hat.position.y = 2.1;
        group.add(hat);

        // Sign sprite
        const canvas = document.createElement('canvas');
        canvas.width = 128;
        canvas.height = 64;
        const ctx = canvas.getContext('2d');
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, 128, 64);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 28px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('🛒 SHOP', 64, 42);
        const texture = new THREE.CanvasTexture(canvas);
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture }));
        sprite.scale.set(2.5, 1.25, 1);
        sprite.position.y = 3;
        group.add(sprite);

        group.position.set(this.shopX, 0, this.shopZ);
        this.scene.add(group);
        this.shopNpcMesh = group;
    },

    createShopUI() {
        const panel = document.createElement('div');
        panel.id = 'shop-panel';
        panel.style.cssText = `
            display:none; position:fixed; top:50%; left:50%;
            transform:translate(-50%,-50%);
            width:360px; max-width:92vw; max-height:80vh;
            background:rgba(0,0,0,0.9); backdrop-filter:blur(12px);
            border:1px solid rgba(255,255,255,0.2); border-radius:16px;
            padding:20px; z-index:55; overflow-y:auto;
            color:#fff; font-family:'Inter',sans-serif;
        `;
        panel.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h3 style="margin:0;font-size:18px;">🛒 상점</h3>
                <span id="shop-coins" style="font-size:15px;color:#fbbf24;">💰 0</span>
                <button id="shop-close" style="background:none;border:none;color:#fff;font-size:24px;cursor:pointer;">✕</button>
            </div>
            <div id="shop-items"></div>
        `;
        document.body.appendChild(panel);
        document.getElementById('shop-close').addEventListener('click', () => this.closeShop());
    },

    createInventoryUI() {
        const invBtn = document.createElement('button');
        invBtn.id = 'btn-inventory';
        invBtn.textContent = '🎒';
        invBtn.style.cssText = `
            position:fixed;
            right:calc(150px + env(safe-area-inset-right, 0px));
            bottom:calc(25px + env(safe-area-inset-bottom, 0px));
            width:48px; height:48px; border-radius:50%;
            border:2px solid rgba(34,197,94,0.55);
            background:rgba(34,197,94,0.28);
            backdrop-filter:blur(8px); color:#fff; font-size:20px;
            cursor:pointer; touch-action:none; z-index:30;
            pointer-events:auto;
            display:flex; align-items:center; justify-content:center;
        `;
        invBtn.addEventListener('click', () => this.toggleInventory());
        invBtn.addEventListener('touchstart', e => { e.preventDefault(); this.toggleInventory(); }, { passive: false });
        document.body.appendChild(invBtn);

        const panel = document.createElement('div');
        panel.id = 'inventory-panel';
        panel.style.cssText = `
            display:none; position:fixed; top:50%; left:50%;
            transform:translate(-50%,-50%);
            width:320px; max-width:90vw; max-height:70vh;
            background:rgba(0,0,0,0.9); backdrop-filter:blur(12px);
            border:1px solid rgba(255,255,255,0.2); border-radius:16px;
            padding:20px; z-index:55; overflow-y:auto;
            color:#fff; font-family:'Inter',sans-serif;
        `;
        panel.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h3 style="margin:0;font-size:18px;">🎒 인벤토리</h3>
                <button id="inv-close" style="background:none;border:none;color:#fff;font-size:24px;cursor:pointer;">✕</button>
            </div>
            <div id="inv-items"></div>
        `;
        document.body.appendChild(panel);
        document.getElementById('inv-close').addEventListener('click', () => this.toggleInventory());
    },

    // Police station also acts as shop (보급실)
    // PRINCIPLES.md #9 — window._policeStation 단일 출처 참조
    policeShopDist: 15,

    update(playerPos) {
        if (!gameState.isDay || DayNight.isTransitioning) {
            this.hideShopPrompt();
            return;
        }

        // _policeStation 에서 좌표 동적 읽음 (경찰서 위치 변경 시 자동 추종)
        const ps = window._policeStation || { x: 0, z: 60 };
        const dx = playerPos.x - ps.x;
        const dz = playerPos.z - ps.z;
        const dist = Math.sqrt(dx * dx + dz * dz);
        const nearPolice = dist < this.policeShopDist;

        if (nearPolice && !this.isOpen) {
            this.showShopButton(true, true);
        } else if (!this.isOpen) {
            this.showShopButton(false);
        }
    },

    showShopButton(show, isPolice) {
        let btn = document.getElementById('btn-shop-open');
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'btn-shop-open';
            btn.style.cssText = `
                position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
                width:56px; height:56px; border-radius:50%;
                border:2px solid rgba(59,130,246,0.7); background:rgba(59,130,246,0.35);
                backdrop-filter:blur(8px); color:#fff; font-size:18px; font-weight:800;
                font-family:'Inter',sans-serif; cursor:pointer; touch-action:none;
                z-index:40; pointer-events:auto; display:none;
                box-shadow:0 4px 16px rgba(59,130,246,0.4);
                align-items:center; justify-content:center;
            `;
            btn.textContent = 'P';
            btn.addEventListener('click', () => this.openShop());
            btn.addEventListener('touchstart', e => { e.preventDefault(); this.openShop(); }, { passive: false });
            document.body.appendChild(btn);
        }
        btn.style.display = show ? 'flex' : 'none';
        if (show) {
            this._isPolice = isPolice;
            HintSystem.showPrompt(isPolice ? 'P 키 → 경찰서 보급실' : 'P 키 → 상점');
        } else {
            HintSystem.hidePrompt();
        }
    },

    hideShopPrompt() {
        this.showShopButton(false);
    },

    openShop() {
        this.isOpen = true;
        gameState.isPaused = true;
        // Update title based on context
        const panel = document.getElementById('shop-panel');
        const titleEl = panel.querySelector('h3');
        if (titleEl) titleEl.textContent = this._isPolice ? '🚔 경찰서 보급실' : '🛒 상점';
        panel.style.display = 'block';
        const btnI = document.getElementById('btn-interact');
        if (btnI) btnI.style.display = 'none';
        this.renderShopItems();
    },

    closeShop() {
        this.isOpen = false;
        gameState.isPaused = false;
        document.getElementById('shop-panel').style.display = 'none';
    },

    renderShopItems() {
        document.getElementById('shop-coins').textContent = '💰 ' + gameState.coins;
        const container = document.getElementById('shop-items');
        container.innerHTML = '';

        this.items.forEach(item => {
            const soldOut = item.type === 'passive' && item.owned;
            const canAfford = gameState.coins >= item.price;

            const div = document.createElement('div');
            div.style.cssText = `
                padding:14px; margin-bottom:10px;
                background:rgba(255,255,255,0.05);
                border:1px solid rgba(255,255,255,0.1);
                border-radius:12px;
                display:flex; justify-content:space-between; align-items:center;
                opacity:${soldOut ? '0.4' : '1'};
            `;
            div.innerHTML = `
                <div>
                    <div style="font-size:15px;font-weight:700;">${item.name}</div>
                    <div style="font-size:12px;color:#aaa;margin-top:4px;">${item.desc}</div>
                </div>
                <button class="shop-buy-btn" data-id="${item.id}" style="
                    padding:8px 16px; border:none; border-radius:20px;
                    font-size:13px; font-weight:700; cursor:pointer;
                    font-family:'Inter',sans-serif;
                    background:${soldOut ? '#555' : (canAfford ? '#fbbf24' : '#444')};
                    color:${soldOut ? '#999' : (canAfford ? '#000' : '#888')};
                    pointer-events:${soldOut ? 'none' : 'auto'};
                ">${soldOut ? '보유' : ('💰' + item.price)}</button>
            `;
            container.appendChild(div);
        });

        container.querySelectorAll('.shop-buy-btn').forEach(btn => {
            btn.addEventListener('click', () => this.buyItem(btn.dataset.id));
        });
    },

    buyItem(itemId) {
        const item = this.items.find(i => i.id === itemId);
        if (!item || gameState.coins < item.price) return;
        if (item.type === 'passive' && item.owned) return;

        gameState.coins -= item.price;
        if (typeof SoundManager !== 'undefined') SoundManager.playSFX('buy');

        if (item.type === 'passive') {
            item.owned = true;
            this.applyPassiveEffect(item.id);
        } else {
            item.count++;
            this.inventory.push({ ...item });
        }

        this.renderShopItems();
    },

    applyPassiveEffect(id) {
        switch (id) {
            case 'flashlight':
                if (DayNight.flashlight) {
                    DayNight.flashlight.angle = Math.PI / 4;
                    DayNight.flashlight.distance = 25;
                }
                showMessage('🔦 손전등 업그레이드!');
                break;
            case 'vest':
                showMessage('🧥 방탄 조끼 착용!');
                break;
            case 'radio':
                showMessage('📡 무전기 획득! 힌트 위치가 표시됩니다.');
                break;
            case 'shoes':
                gameState.moveSpeed *= 1.2;
                gameState.runSpeed *= 1.2;
                showMessage('👟 러닝화 착용! 이동속도 UP!');
                break;
        }
    },

    hasItem(id) {
        const item = this.items.find(i => i.id === id);
        if (!item) return false;
        if (item.type === 'passive') return item.owned;
        return item.count > 0;
    },

    toggleInventory() {
        const panel = document.getElementById('inventory-panel');
        const isOpen = panel.style.display === 'block';
        panel.style.display = isOpen ? 'none' : 'block';
        gameState.isPaused = !isOpen;

        if (!isOpen) this.renderInventory();
    },

    renderInventory() {
        const container = document.getElementById('inv-items');
        container.innerHTML = '';

        const passives = this.items.filter(i => i.type === 'passive' && i.owned);
        const consumables = this.items.filter(i => i.type === 'consumable' && i.count > 0);

        if (passives.length === 0 && consumables.length === 0) {
            container.innerHTML = '<p style="text-align:center;color:#666;font-size:14px;">아이템이 없습니다</p>';
            return;
        }

        passives.forEach(item => {
            const div = document.createElement('div');
            div.style.cssText = 'padding:10px;margin-bottom:8px;background:rgba(255,255,255,0.05);border-radius:10px;';
            div.innerHTML = `<span style="font-size:14px;">${item.name}</span> <span style="color:#4ade80;font-size:12px;">장착중</span>`;
            container.appendChild(div);
        });

        consumables.forEach(item => {
            const div = document.createElement('div');
            div.style.cssText = 'padding:10px;margin-bottom:8px;background:rgba(255,255,255,0.05);border-radius:10px;display:flex;justify-content:space-between;align-items:center;';
            div.innerHTML = `
                <span style="font-size:14px;">${item.name} ×${item.count}</span>
                <button class="inv-use-btn" data-id="${item.id}" style="
                    padding:6px 14px;border:none;border-radius:16px;
                    background:#4ade80;color:#000;font-size:12px;font-weight:700;cursor:pointer;
                ">사용</button>
            `;
            container.appendChild(div);
        });

        container.querySelectorAll('.inv-use-btn').forEach(btn => {
            btn.addEventListener('click', () => this.useItem(btn.dataset.id));
        });
    },

    useItem(id) {
        const item = this.items.find(i => i.id === id);
        if (!item || item.count <= 0) return;

        switch (id) {
            case 'drink':
                gameState.stamina = gameState.maxStamina;
                gameState.health = Math.min(gameState.maxHealth, gameState.health + 2);
                showMessage('💊 에너지 드링크 사용! 체력 +2');
                break;
        }

        item.count--;
        this.renderInventory();
    },

    reset() {
        this.isOpen = false;
        this.inventory = [];
        this.items.forEach(i => { i.owned = false; i.count = 0; });
        if (this.shopNpcMesh && this.shopNpcMesh.parent) {
            this.scene.remove(this.shopNpcMesh);
        }
    }
};
