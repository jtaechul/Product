// signs.js — 분당 상권 가로 간판 52개
// 1) assets/models/signs/{id}.glb 로딩 시도 (사용자 SketchUp 작업물)
// 2) GLB 없으면 절차적 Box + CanvasTexture로 폴백 (즉시 동작)

(function () {

// 사이즈 (게임 단위 ≈ 1m)
const SIZES = {
    L: { w: 4.5, h: 1.10, d: 0.28, bw: 0.06, ew: 0.85 },
    M: { w: 3.5, h: 0.95, d: 0.22, bw: 0.05, ew: 0.72 },
    S: { w: 2.5, h: 0.80, d: 0.18, bw: 0.05, ew: 0.58 }
};

// 52개 간판 데이터
const SIGNS = [
    // 카페/커피 8
    { id:'starlucks',   en:'STARLUCKS',      kr:'스타락스',     sz:'L', bg:'#007048', fg:'#ffffff', bd:'#00462d', bx:'#ffd700' },
    { id:'edia',        en:'EDIA COFFEE',    kr:'이지아커피',   sz:'M', bg:'#1b2a6b', fg:'#ffffff', bd:'#0f1950', bx:'#ffc800' },
    { id:'megalatte',   en:'MEGALATTE',      kr:'메가라떼',     sz:'M', bg:'#ffd700', fg:'#000000', bd:'#c8a000', bx:'#000000' },
    { id:'kompose',     en:'KOMPOSE',        kr:'콤포즈커피',   sz:'M', bg:'#00a99d', fg:'#ffffff', bd:'#006e64', bx:'#ffffff' },
    { id:'twosome',     en:'TWOSOME HOUSE',  kr:'투썸하우스',   sz:'L', bg:'#c8102e', fg:'#ffffff', bd:'#8c0a1e', bx:'#ffd700' },
    { id:'paulbass',    en:'PAUL BASS',      kr:'폴배쓰카페',   sz:'M', bg:'#6b3f2a', fg:'#f0dcbe', bd:'#462814', bx:'#c8b48c' },
    { id:'hallis',      en:'HALLIS COFFEE',  kr:'할리즈커피',   sz:'M', bg:'#f47920', fg:'#ffffff', bd:'#be500a', bx:'#ffffff' },
    { id:'paikda',      en:'PAIKDA COFFEE',  kr:'빽다커피',     sz:'M', bg:'#ffffff', fg:'#1e1e1e', bd:'#d21e1e', bx:'#d21e1e' },

    // 음식점 14
    { id:'maeburger',   en:'MAE BURGER',     kr:'맥버거',       sz:'L', bg:'#da291c', fg:'#ffd300', bd:'#aa140a', bx:'#ffd300' },
    { id:'burgerqueen', en:'BURGER QUEEN',   kr:'버거퀸',       sz:'L', bg:'#ff6600', fg:'#ffffff', bd:'#b43c00', bx:'#ffd700' },
    { id:'lotteria',    en:'LOTTERIA',       kr:'롯테리아',     sz:'M', bg:'#c41e3a', fg:'#ffffff', bd:'#8c0a23', bx:'#ffd700' },
    { id:'bbpchicken',  en:'BBP CHICKEN',    kr:'BBP치킨',      sz:'L', bg:'#ffc107', fg:'#000000', bd:'#c89100', bx:'#dc0000' },
    { id:'gyowon',      en:'GYOWON',         kr:'교원치킨',     sz:'L', bg:'#8b0000', fg:'#ffd700', bd:'#5a0000', bx:'#ffd700' },
    { id:'bhpchicken',  en:'BHP CHICKEN',    kr:'BHP치킨',      sz:'M', bg:'#c81e1e', fg:'#ffffff', bd:'#8c0a0a', bx:'#ffff00' },
    { id:'dominopizza', en:'DOMINO PIZZA',   kr:'도미노파자',   sz:'L', bg:'#0064b4', fg:'#ffffff', bd:'#003c82', bx:'#dc1e1e' },
    { id:'bonbab',      en:'BONBAB',         kr:'본밥',         sz:'S', bg:'#1565c0', fg:'#ffffff', bd:'#0a3c96', bx:'#ffd700' },
    { id:'hansot',      en:'HANSOT BAPSANG', kr:'한솥밥상',     sz:'S', bg:'#2e7d32', fg:'#ffffff', bd:'#145019', bx:'#ffeb3b' },
    { id:'subwaysand',  en:'SUBWAY SAND',    kr:'써브웨이샌드', sz:'M', bg:'#00833e', fg:'#ffc400', bd:'#005a28', bx:'#ffc400' },
    { id:'kimbabchon',  en:'KIMBAB CHON',    kr:'김밥천우',     sz:'M', bg:'#c62828', fg:'#ffffff', bd:'#8c0a0a', bx:'#ffd700' },
    { id:'papabird',    en:'PAPA BIRD',      kr:'파파버드',     sz:'M', bg:'#e65100', fg:'#ffffff', bd:'#aa3200', bx:'#ffd700' },
    { id:'ramennoodle', en:'DONGNE RAMEN',   kr:'동네라멘',     sz:'S', bg:'#b71c1c', fg:'#ffeb3b', bd:'#820000', bx:'#ffeb3b' },
    { id:'sundae',      en:'BUNDANG SUNDAE', kr:'분당순대국',   sz:'S', bg:'#643214', fg:'#ffebc8', bd:'#461e0a', bx:'#c89632' },

    // 병원/의원 8
    { id:'yensae',      en:'YENSAE ENT',     kr:'연새이비인후과', sz:'S', bg:'#0d47a1', fg:'#ffffff', bd:'#c8cdd7', bx:'#ffffff' },
    { id:'chastar',     en:'CHA STAR SKIN',  kr:'차앤별피부과', sz:'S', bg:'#ffffff', fg:'#ec407a', bd:'#ec407a', bx:'#ec407a' },
    { id:'brighteye',   en:'BRIGHT EYE',     kr:'밝은눈안과',   sz:'S', bg:'#01579b', fg:'#ffffff', bd:'#c8d2dc', bx:'#64c8ff' },
    { id:'gooddental',  en:'GOOD DENTAL',    kr:'선한치과의원', sz:'S', bg:'#009688', fg:'#ffffff', bd:'#c8d7d2', bx:'#ffffff' },
    { id:'hamsoa',      en:'HAMSOA CLINIC',  kr:'함소아한의원', sz:'S', bg:'#1b5e20', fg:'#ffffff', bd:'#c8dcc8', bx:'#ffeb3b' },
    { id:'sungshim',    en:'SUNGSHIM ORTH',  kr:'성심정형외과', sz:'S', bg:'#1565c0', fg:'#ffffff', bd:'#c8d2dc', bx:'#ffffff' },
    { id:'misobeauty',  en:'MISO BEAUTY',    kr:'미소성형외과', sz:'S', bg:'#ffffff', fg:'#ad1457', bd:'#ad1457', bx:'#ad1457' },
    { id:'sjclinic',    en:'SJ PEDIATRIC',   kr:'SJ소아과',     sz:'S', bg:'#64b5f6', fg:'#ffffff', bd:'#1e64c8', bx:'#ffffff' },

    // 학원/교육 6
    { id:'nunbit',      en:'NUNBIT EDU',     kr:'눈빛이학원',   sz:'M', bg:'#ff9800', fg:'#ffffff', bd:'#c86400', bx:'#ffffff' },
    { id:'daekyo',      en:'DAEKYO YEOLGI',  kr:'대교열기',     sz:'M', bg:'#1565c0', fg:'#ffffff', bd:'#0a4196', bx:'#ffd700' },
    { id:'sidaeprep',   en:'SIDAE PREP',     kr:'시대준비학원', sz:'M', bg:'#1a237e', fg:'#ffd700', bd:'#0f145a', bx:'#ffd700' },
    { id:'engkingdom',  en:'ENG KINGDOM',    kr:'영어왕국',     sz:'M', bg:'#ffeb3b', fg:'#000000', bd:'#c8af00', bx:'#ff5000' },
    { id:'mathgenius',  en:'MATH GENIUS',    kr:'수학천재',     sz:'M', bg:'#1565c0', fg:'#ffffff', bd:'#0a3c96', bx:'#ffeb3b' },
    { id:'cheongdam',   en:'CHEONGDAM LANG', kr:'청담어학당',   sz:'M', bg:'#121450', fg:'#d4af37', bd:'#d4af37', bx:'#d4af37' },

    // 의류/뷰티/쇼핑 6
    { id:'olivebom',    en:'OLIVE BOM',      kr:'올리브봄',     sz:'L', bg:'#6c7537', fg:'#ffffff', bd:'#414b14', bx:'#ffeb3b' },
    { id:'daigashop',   en:'DAIGA SHOP',     kr:'다이가샵',     sz:'L', bg:'#1e88e5', fg:'#ffffff', bd:'#f0f0f0', bx:'#ffffff' },
    { id:'unikro',      en:'UNIKRO',         kr:'유니크로',     sz:'L', bg:'#d32f2f', fg:'#ffffff', bd:'#f0f0f0', bx:'#ffffff' },
    { id:'abcshoes',    en:'ABC SHOES',      kr:'ABC슈즈마트',  sz:'M', bg:'#0d47a1', fg:'#ffffff', bd:'#ffd700', bx:'#ffd700' },
    { id:'naturechip',  en:'NATURE CHIP',    kr:'네이처채집',   sz:'M', bg:'#388e3c', fg:'#ffffff', bd:'#c8dcc8', bx:'#ffffff' },
    { id:'innibar',     en:'INNIBAR',        kr:'이니발르',     sz:'M', bg:'#1b5e20', fg:'#ffffff', bd:'#b4cdb4', bx:'#c8e6c8' },

    // 금융/은행 4
    { id:'kukminbank',  en:'KUKMIN BANK',    kr:'국민우리은행', sz:'M', bg:'#ffc107', fg:'#000000', bd:'#c89100', bx:'#000000' },
    { id:'sinhanbank',  en:'SINHAN SMART',   kr:'신한스마트은행', sz:'M', bg:'#0c3f96', fg:'#ffffff', bd:'#c8d2dc', bx:'#ffffff' },
    { id:'kakaomoney',  en:'KAKAO MONEY',    kr:'카카오머니',   sz:'M', bg:'#ffeb00', fg:'#3c1e00', bd:'#c8af00', bx:'#3c1e00' },
    { id:'tossmoney',   en:'TOSS MONEY',     kr:'토스머니',     sz:'M', bg:'#0277bd', fg:'#ffffff', bd:'#c8d2e1', bx:'#ffffff' },

    // 편의점/생활/기타 6
    { id:'gu25',        en:'GU MARKET',      kr:'GU마켓',       sz:'L', bg:'#1565c0', fg:'#ffa500', bd:'#ffa500', bx:'#ffa500' },
    { id:'sebong',      en:'SEBONG STORE',   kr:'세봉스토어',   sz:'L', bg:'#ff8f00', fg:'#006400', bd:'#006400', bx:'#ffffff' },
    { id:'cg24',        en:'CG 24',          kr:'CG24편의점',   sz:'L', bg:'#6a1b9a', fg:'#ffffff', bd:'#c896ff', bx:'#ffffff' },
    { id:'bundangpharm',en:'BUNDANG PHARM',  kr:'분당약국',     sz:'S', bg:'#ffffff', fg:'#d32f2f', bd:'#d32f2f', bx:'#d32f2f' },
    { id:'pctime',      en:'PC TIME',        kr:'피씨타임',     sz:'M', bg:'#0d0d1e', fg:'#00c8ff', bd:'#00c8ff', bx:'#00ff96' },
    { id:'noraebang',   en:'STAR SINGING',   kr:'스타노래방',   sz:'M', bg:'#1e0a32', fg:'#c800ff', bd:'#c800ff', bx:'#ffd700' }
];

// 색상 문자열 → THREE.Color
function hexToColor(h) {
    return new THREE.Color(h);
}

// 약간 밝게 (LED 발광)
function lighten(hex, amount) {
    const c = new THREE.Color(hex);
    c.r = Math.min(1, c.r + amount);
    c.g = Math.min(1, c.g + amount);
    c.b = Math.min(1, c.b + amount);
    return c;
}

// Canvas 텍스처 — 간판 앞면 (배경 + 엠블럼 + 영문 + 한글)
function makeBoardTexture(sign) {
    const cv = document.createElement('canvas');
    cv.width = 512; cv.height = 128;
    const ctx = cv.getContext('2d');

    // 배경
    ctx.fillStyle = sign.bg;
    ctx.fillRect(0, 0, 512, 128);

    // 엠블럼 박스 (좌측)
    ctx.fillStyle = sign.bx;
    ctx.fillRect(10, 10, 108, 108);
    // 엠블럼 안쪽 테두리
    ctx.strokeStyle = sign.bd;
    ctx.lineWidth = 4;
    ctx.strokeRect(12, 12, 104, 104);

    // 영문 상호명
    ctx.fillStyle = sign.fg;
    ctx.font = 'bold 34px "Inter", "Noto Sans KR", sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(sign.en, 132, 55);

    // 한글 상호명
    ctx.font = 'bold 28px "Noto Sans KR", sans-serif';
    ctx.fillText(sign.kr, 132, 100);

    const tex = new THREE.CanvasTexture(cv);
    tex.anisotropy = 4;
    return tex;
}

// 절차적 간판 메시 (Group)
function buildProceduralSign(sign) {
    const sz = SIZES[sign.sz];
    const W = sz.w, H = sz.h, D = sz.d, BW = sz.bw;
    const group = new THREE.Group();
    group.name = `Sign_${sign.id}`;

    // 메인 보드 — 앞면에 텍스트 텍스처
    const boardTex = makeBoardTexture(sign);
    const matFront = new THREE.MeshStandardMaterial({
        map: boardTex,
        emissive: hexToColor(sign.bg),
        emissiveMap: boardTex,
        emissiveIntensity: 0.35,
        roughness: 0.45,
        metalness: 0.25
    });
    const matSide = new THREE.MeshStandardMaterial({
        color: hexToColor(sign.bg),
        emissive: hexToColor(sign.bg),
        emissiveIntensity: 0.15,
        roughness: 0.55,
        metalness: 0.2
    });
    // 6면 material: +x, -x, +y, -y, +z(front), -z
    const board = new THREE.Mesh(
        new THREE.BoxGeometry(W - BW * 2, H - BW * 2, D),
        [matSide, matSide, matSide, matSide, matFront, matSide]
    );
    board.position.set(0, 0, 0);
    board.castShadow = true;
    group.add(board);

    // 테두리 4면 (포인트 컬러)
    const borderMat = new THREE.MeshStandardMaterial({
        color: hexToColor(sign.bd),
        emissive: hexToColor(sign.bd),
        emissiveIntensity: 0.2,
        roughness: 0.5,
        metalness: 0.3
    });
    const bTop = new THREE.Mesh(new THREE.BoxGeometry(W, BW, D + 0.02), borderMat);
    bTop.position.set(0, H / 2 - BW / 2, 0);
    group.add(bTop);
    const bBot = new THREE.Mesh(new THREE.BoxGeometry(W, BW, D + 0.02), borderMat);
    bBot.position.set(0, -H / 2 + BW / 2, 0);
    group.add(bBot);
    const bL = new THREE.Mesh(new THREE.BoxGeometry(BW, H, D + 0.02), borderMat);
    bL.position.set(-W / 2 + BW / 2, 0, 0);
    group.add(bL);
    const bR = new THREE.Mesh(new THREE.BoxGeometry(BW, H, D + 0.02), borderMat);
    bR.position.set(W / 2 - BW / 2, 0, 0);
    group.add(bR);

    // LED 하단 조명띠 (앞으로 살짝 돌출, 밝은 색)
    const ledColor = lighten(sign.bg, 0.25);
    const ledMat = new THREE.MeshStandardMaterial({
        color: ledColor,
        emissive: ledColor,
        emissiveIntensity: 0.85,
        roughness: 0.3,
        metalness: 0.1
    });
    const led = new THREE.Mesh(
        new THREE.BoxGeometry(W, 0.08, D + 0.05),
        ledMat
    );
    led.position.set(0, -H / 2 - 0.07, 0.03);
    group.add(led);

    return group;
}

// GLB 로드 → 텍스트 텍스처 적용 → 메인 보드 메시에 매핑
function applyTextureToGLB(root, sign) {
    const tex = makeBoardTexture(sign);
    root.traverse(child => {
        if (!child.isMesh) return;
        const name = (child.name || '').toLowerCase();
        if (name.includes('main_board') || name.includes('mainboard')) {
            child.material = new THREE.MeshStandardMaterial({
                map: tex,
                emissive: hexToColor(sign.bg),
                emissiveMap: tex,
                emissiveIntensity: 0.35,
                roughness: 0.45,
                metalness: 0.25
            });
        }
        child.castShadow = true;
    });
}

// GLB 로딩 (실패 시 절차적 폴백)
function loadSignMesh(sign, onReady) {
    const url = `assets/models/signs/${sign.id}.glb`;
    const loader = new THREE.GLTFLoader();
    loader.load(
        url,
        (gltf) => {
            const root = gltf.scene;
            applyTextureToGLB(root, sign);
            root.name = `Sign_${sign.id}_GLB`;
            onReady(root);
        },
        undefined,
        (_err) => {
            // 404 또는 로드 실패 → 절차적 폴백
            onReady(buildProceduralSign(sign));
        }
    );
}

// 빌딩 1개에 간판 부착 (앞면 = +Z 면)
function attachSignsToBuilding(scene, building, signList) {
    const { x, z, w, d, h } = building;
    const frontZ = z + d / 2 + 0.18;

    // 빌딩 높이에 맞춰 슬롯 개수 결정
    let slots;
    if (h >= 18) slots = 4;
    else if (h >= 12) slots = 3;
    else if (h >= 8) slots = 2;
    else slots = 1;

    const count = Math.min(slots, signList.length);
    if (count === 0) return;

    // 최상단 슬롯 z 위치 — 옥상 아래 1.2m
    const topY = h - 1.4;
    const slotGap = 1.5;

    for (let i = 0; i < count; i++) {
        const sign = signList[i];
        const sz = SIZES[sign.sz];
        // 간판이 빌딩 폭보다 크면 스케일 다운
        const maxW = w - 0.6;
        const scale = sz.w > maxW ? maxW / sz.w : 1.0;
        const yPos = topY - i * slotGap;

        loadSignMesh(sign, (mesh) => {
            mesh.scale.setScalar(scale);
            mesh.position.set(x, yPos, frontZ);
            scene.add(mesh);
        });
    }
}

// 메인 진입점 — createWorld 직후 호출
window.loadSigns = function (scene, buildingData) {
    if (!buildingData || !Array.isArray(buildingData)) return;
    const commercial = buildingData.filter(b => b.zone === 'COMMERCIAL');
    if (commercial.length === 0) return;

    // 빌딩 큰 순으로 정렬 (간판 많이 다는 빌딩 = 큰 빌딩)
    commercial.sort((a, b) => (b.w * b.h) - (a.w * a.h));

    // 52개 간판을 빌딩에 라운드로빈 분배
    const signQueue = SIGNS.slice();
    let idx = 0;
    for (const b of commercial) {
        if (idx >= signQueue.length) break;
        // 빌딩 높이별 슬롯 개수와 동일하게 잘라서 전달
        let slots;
        if (b.h >= 18) slots = 4;
        else if (b.h >= 12) slots = 3;
        else if (b.h >= 8) slots = 2;
        else slots = 1;
        const portion = signQueue.slice(idx, idx + slots);
        attachSignsToBuilding(scene, b, portion);
        idx += portion.length;
    }
};

window.SIGN_DATA = SIGNS;
window.SIGN_SIZES = SIZES;

})();
