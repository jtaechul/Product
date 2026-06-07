// world.js — 남양주시 평내동 풍 도로 우선 도시 설계
// 격자형 도시 모델: 메인 간선도로 + 보조도로, 도로에 면하는 건물 배치 + 로데오거리

// 월드 비대칭 — 북쪽은 단축 (빨간 영역 삭제로 경찰서 + 도로 시프트 후 짧아짐)
const WORLD_X_HALF = 150;
const WORLD_Z_NORTH = 90;   // 북쪽 끝 — 경찰서 위쪽
const WORLD_Z_SOUTH = -150; // 남쪽 끝
const WORLD_SIZE = 300;     // 기존 호환용 (X 방향 풀 폭)
const WORLD_Z_LEN = WORLD_Z_NORTH - WORLD_Z_SOUTH;  // 240
window.WORLD_SIZE = WORLD_SIZE;
window.WORLD_Z_NORTH = WORLD_Z_NORTH;
window.WORLD_Z_SOUTH = WORLD_Z_SOUTH;

// 주거지구 아파트 단지 (남양주시 평내동 실제 단지 참고)
// 10개 단지 (실제 평내동 아파트단지 이름 사용)
const APARTMENT_COMPLEXES = [
    { kr: '평내금호어울림', en: 'KUMHO EOULLIM',       dong: [101, 102, 103, 104] },
    { kr: '평내중흥아파트', en: 'JUNGHEUNG APT',       dong: [201, 202, 203, 204] },
    { kr: '평내우림아파트', en: 'WOORIM APT',          dong: [301, 302, 303] },
    { kr: '평내일성트루엘', en: 'ILSEONG TRUELL',      dong: [401, 402, 403] },
    { kr: '대주평내파크빌', en: 'DAEJOO PARKVILLE',    dong: [501, 502, 503, 504] },
    { kr: '신명스카이뷰', en: 'SHINMYUNG SKYVIEW',     dong: [601, 602, 603] },
    { kr: '상록데시앙', en: 'SANGNOK DECIAN',          dong: [701, 702, 703, 704] },
    { kr: 'e편한세상', en: 'E-PYEONHAN WORLD',        dong: [801, 802, 803] },
    { kr: '어울림공동주택', en: 'EOULLIM RESIDENCE',   dong: [901, 902, 903, 904] },
    { kr: '평내한신타운', en: 'HANSHIN TOWN',          dong: [1001, 1002, 1003] },
    { kr: '평내쌍용아파트', en: 'SSANGYONG APT',       dong: [1101, 1102, 1103, 1104] },
    { kr: '평내현대아파트', en: 'HYUNDAI APT',         dong: [1201, 1202, 1203] }
];

// 공업지구 기업명 풀 (양각 글자로 공장 외벽에 부착)
const FACTORY_COMPANIES = [
    { kr: '삼송전자',       en: 'SAMSONG ELEC' },
    { kr: '해피닉스반도체', en: 'HAPPYNIX SEMI' },
    { kr: '한대제철',       en: 'HANDAE STEEL' },
    { kr: 'LJ화학',         en: 'LJ CHEMICAL' },
    { kr: '대우중공업',     en: 'DAEWOO HEAVY' },
    { kr: '포송기계',       en: 'POSONG MACHINE' },
    { kr: '송원유화',       en: 'SONGWON OIL' },
    { kr: '동광알루미늄',   en: 'DONGKWANG ALU' },
    { kr: '신영금속',       en: 'SHINYEONG METAL' },
    { kr: 'KP에너지',       en: 'KP ENERGY' },
    { kr: '두민조선',       en: 'DOOMIN SHIPYARD' },
    { kr: '효승케미컬',     en: 'HYOSEUNG CHEM' },
    { kr: '광명특수강',     en: 'KWANGMYUNG STL' },
    { kr: 'DM자동차부품',   en: 'DM AUTO PARTS' },
    { kr: '풍원섬유',       en: 'PUNGWON TEXTILE' },
    { kr: '신백시멘트',     en: 'SHINBAEK CEMENT' },
    { kr: '진성공업',       en: 'JINSEONG IND' },
    { kr: '한국태광',       en: 'KOREA TAEKWANG' }
];

// Zone definitions (경찰서 시프트 후)
const ZONES = {
    POLICE:      { name: '경찰서 구역', cx: 0, cz: 67 },
    RESIDENTIAL: { name: '주택가',     cx: -80, cz: -25 },
    COMMERCIAL:  { name: '상업지구',   cx: 80, cz: -25 },
    FACTORY:     { name: '공장지대',   cx: 0, cz: -100 }
};

// Korean city road network - inspired by Bundang/Ilsan grid
// Main arterial roads — 사각형 perimeter + 내부 격자
// CORE RULE: 상업지구 내부(z=-90~5, x=5~135) 에는 차량 도로 없음 — 전체가 로데오
// Z 범위: -140 ~ 85, X 범위: -140 ~ 140
const MAIN_ROADS = [
    // ── Perimeter (sealed rectangle) ──
    { type: 'H', z: 85,  w: 8,  length: 290 },   // 북측 perimeter
    { type: 'H', z: -140, w: 8, length: 290 },   // 남측 perimeter
    { type: 'V', x: -140, w: 8, length: 240 },   // 서측 perimeter
    { type: 'V', x: 140,  w: 8, length: 240 },   // 동측 perimeter

    // ── East-West arterials (상업지구 경계 + 위/아래 zone) ──
    { type: 'H', z: 55,  w: 8, length: 290 },    // 경찰서 정면 도로
    { type: 'H', z: 5,   w: 8, length: 290 },    // R/C divider — 상업지구 북측 경계
    { type: 'H', z: -90, w: 10, length: 290 },   // 상업/공업 경계 — 상업지구 남측 경계

    // ── V 도로 — 경찰지구 섹션 (z=5~85) ──
    // 모든 V 도로는 H z=5 (상업 북측 경계) 위쪽만 존재
    { type: 'V', x: 0,    w: 10, length: 50, offsetZ: 30  }, // 경찰 중앙 (z=5~55, 경찰서 회피)
    { type: 'V', x: -50,  w: 8,  length: 80, offsetZ: 45  }, // 경찰 좌측
    { type: 'V', x: 50,   w: 8,  length: 80, offsetZ: 45  }, // 경찰 우측
    { type: 'V', x: -100, w: 6,  length: 80, offsetZ: 45  },
    { type: 'V', x: 100,  w: 6,  length: 80, offsetZ: 45  },

    // ── V 도로 — 공업지구 섹션 (z=-140~-90) ──
    // 모든 V 도로는 H z=-90 (상업 남측 경계) 아래쪽만 존재
    { type: 'V', x: 0,    w: 8, length: 50, offsetZ: -115 },
    { type: 'V', x: -50,  w: 8, length: 50, offsetZ: -115 },
    { type: 'V', x: 50,   w: 8, length: 50, offsetZ: -115 },
    { type: 'V', x: -100, w: 6, length: 50, offsetZ: -115 },
    { type: 'V', x: 100,  w: 6, length: 50, offsetZ: -115 },

    // ── V 도로 — 주거/상업 내부 격자 (z=-90~5, H z=-90 ↔ H z=5 연결) ──
    // x=-100/-50/0 — 아파트 단지 사이 간격(블록 경계에서 ±1m 이상 여유)에 배치,
    // 상업지구(x=5~135) 진입 전 x=0 에서 끝나 CORE/#11 위반 없음
    { type: 'V', x: -100, w: 6, length: 95, offsetZ: -42.5 },
    { type: 'V', x: -50,  w: 8, length: 95, offsetZ: -42.5 },
    { type: 'V', x: 0,    w: 8, length: 95, offsetZ: -42.5 },

    // ── H 연결도로 — 주거지구 내부 횡단 (서측 perimeter ↔ V x=0, z=-45) ──
    // offsetX 로 서쪽 절반만 깔아 상업지구(로데오) 내부를 가로지르지 않음 (PRINCIPLES.md #11)
    { type: 'H', z: -45,  w: 8, length: 146, offsetX: -70 }
];
window.MAIN_ROADS = MAIN_ROADS;

// Building blocks defined by road grid intersections
// Each block has 4 sides; buildings face outward (toward roads)
const BUILDING_BLOCKS = [];

function defineBlocks() {
    BUILDING_BLOCKS.length = 0;

    // 경찰서 앞 구역(z=15~50) — 아파트 단지로 전환 (V 도로 ±100/±50/0 와 겹치지 않게 6개 분할 유지)
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -135, maxX: -104, minZ: 15, maxZ: 50, density: 'apt', complexIdx: 6 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX:  -96, maxX:  -54, minZ: 15, maxZ: 50, density: 'apt', complexIdx: 7 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX:  -46, maxX:   -6, minZ: 15, maxZ: 50, density: 'apt', complexIdx: 8 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX:    6, maxX:   46, minZ: 15, maxZ: 50, density: 'apt', complexIdx: 9 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX:   54, maxX:   96, minZ: 15, maxZ: 50, density: 'apt', complexIdx: 10 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX:  104, maxX:  135, minZ: 15, maxZ: 50, density: 'apt', complexIdx: 11 });

    // 아파트 단지 — 6 블록 (V 도로 간 안전 구간만 사용)
    // 상단행 (z=-40~0, H z=-45 도로 위쪽)
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -135, maxX: -105, minZ: -40, maxZ: 0,  density: 'apt', complexIdx: 0 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -90, maxX: -55,  minZ: -40, maxZ: 0,  density: 'apt', complexIdx: 1 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -45, maxX: -5,   minZ: -40, maxZ: 0,  density: 'apt', complexIdx: 2 });

    // 하단행 (z=-85~-50, H z=-45 도로 아래쪽) — 3개 블록
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -135, maxX: -105, minZ: -85, maxZ: -50, density: 'apt', complexIdx: 3 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -90, maxX: -55,   minZ: -85, maxZ: -50, density: 'apt', complexIdx: 4 });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -45, maxX: -5,    minZ: -85, maxZ: -50, density: 'apt', complexIdx: 5 });

    // === 상업지구 전체 = 로데오 거리 (분당/평촌 번화 풍) ===
    // 4개 긴 가로 행: 2개 로데오(z=-15~-22, z=-55~-62) 좌우 양옆에 상가 행
    // 차량 도로 없음 — perimeter 와 H z=5 / z=-90 외부에서만 진입
    BUILDING_BLOCKS.push({
        zone: 'COMMERCIAL', minX: 5, maxX: 135, minZ: -14, maxZ: -1,
        density: 'rodeo', facing: '-Z', rodeo: true  // 북측 행, 간판 남쪽 N로데오 향함
    });
    BUILDING_BLOCKS.push({
        zone: 'COMMERCIAL', minX: 5, maxX: 135, minZ: -36, maxZ: -23,
        density: 'rodeo', facing: '+Z', rodeo: true  // N로데오 남측 행, 간판 북쪽 향함
    });
    BUILDING_BLOCKS.push({
        zone: 'COMMERCIAL', minX: 5, maxX: 135, minZ: -54, maxZ: -41,
        density: 'rodeo', facing: '-Z', rodeo: true  // S로데오 북측 행
    });
    BUILDING_BLOCKS.push({
        zone: 'COMMERCIAL', minX: 5, maxX: 135, minZ: -76, maxZ: -63,
        density: 'rodeo', facing: '+Z', rodeo: true  // S로데오 남측 행
    });

    // 공업 블록 — V 도로 (factory section) 와 겹치지 않게 6개 분할
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX: -135, maxX: -104, minZ: -135, maxZ: -95, density: 'sparse' });
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX:  -96, maxX:  -54, minZ: -135, maxZ: -95, density: 'sparse' });
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX:  -46, maxX:   -6, minZ: -135, maxZ: -95, density: 'sparse' });
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX:    6, maxX:   46, minZ: -135, maxZ: -95, density: 'sparse' });
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX:   54, maxX:   96, minZ: -135, maxZ: -95, density: 'sparse' });
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX:  104, maxX:  135, minZ: -135, maxZ: -95, density: 'sparse' });

    // === PRINCIPLES.md #4 검증: 블록 vs 도로 asphalt 교차 검사 ===
    validateBlocksVsRoads();
}

// 도로 asphalt vs 빌딩 블록 AABB 검증 — 경고 출력 + 자동 보정
function validateBlocksVsRoads() {
    const issues = [];
    BUILDING_BLOCKS.forEach((b, i) => {
        MAIN_ROADS.forEach(r => {
            let roadMinX, roadMaxX, roadMinZ, roadMaxZ;
            if (r.type === 'H') {
                const ox = r.offsetX || 0;
                const half = r.length / 2;
                roadMinX = ox - half; roadMaxX = ox + half;
                roadMinZ = r.z - r.w / 2; roadMaxZ = r.z + r.w / 2;
            } else {
                const oz = r.offsetZ || 0;
                const half = r.length / 2;
                roadMinX = r.x - r.w / 2; roadMaxX = r.x + r.w / 2;
                roadMinZ = oz - half; roadMaxZ = oz + half;
            }
            // AABB intersection
            if (b.maxX > roadMinX && b.minX < roadMaxX &&
                b.maxZ > roadMinZ && b.minZ < roadMaxZ) {
                issues.push({ block: i, zone: b.zone, road: r });
            }
        });
    });
    if (issues.length > 0) {
        console.error('[PRINCIPLES.md #1] 도로-블록 교차 검출:', issues);
    }
}

function createWorld(scene) {
    const worldGroup = new THREE.Group();
    const buildingData = [];

    defineBlocks();
    createGround(worldGroup);
    createRoadNetwork(worldGroup);
    createRodeoStreet(worldGroup);
    const policeStation = createPoliceStation(worldGroup);
    buildingData.push(policeStation);

    const zoneBuildings = createGridBuildings(worldGroup);
    buildingData.push(...zoneBuildings);
    // 경찰서는 더 이상 단일 충돌 박스로 처리하지 않음 — createPoliceInterior 에서 벽 segment 로 등록 (통과 가능 입구 포함)

    createStreetProps(worldGroup);
    createCityParks(worldGroup);

    // 경찰서 내부 충돌 등록 — 벽/구치소/책상 (입구 갭은 충돌 박스에 미포함 → 통과 가능)
    if (typeof window._policeColliders !== 'undefined' && window._buildingPositions) {
        window._policeColliders.forEach(c => window._buildingPositions.push(c));
        // buildingData 에도 추가 (main.js checkBuildingCollision 이 buildingData 순회)
        window._policeColliders.forEach(c => {
            buildingData.push({ x: c.x, z: c.z, w: c.w, d: c.d, h: c.h || 3, type: 'policeWall', hideoutIndex: -1 });
        });
    }

    scene.add(worldGroup);
    return { worldGroup, buildingData };
}

function makeProceduralTexture(baseColor, noiseAmount, size) {
    const c = document.createElement('canvas');
    c.width = c.height = size || 256;
    const ctx = c.getContext('2d');
    ctx.fillStyle = baseColor;
    ctx.fillRect(0, 0, c.width, c.height);
    const img = ctx.getImageData(0, 0, c.width, c.height);
    for (let i = 0; i < img.data.length; i += 4) {
        const n = (Math.random() - 0.5) * noiseAmount;
        img.data[i] = Math.max(0, Math.min(255, img.data[i] + n));
        img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n));
        img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n));
    }
    ctx.putImageData(img, 0, 0);
    const tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    return tex;
}

function createGround(group) {
    // Grass — 월드 비대칭 (북측 단축)
    const grassTex = makeProceduralTexture('#3a6b2a', 60, 512);
    grassTex.repeat.set(20, 18);
    const groundCx = 0;
    const groundCz = (WORLD_Z_NORTH + WORLD_Z_SOUTH) / 2; // -30
    const geo = new THREE.PlaneGeometry(WORLD_SIZE, WORLD_Z_LEN);
    const mat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        map: grassTex,
        roughness: 0.95,
        metalness: 0
    });
    const ground = new THREE.Mesh(geo, mat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(groundCx, 0, groundCz);
    ground.receiveShadow = true;
    group.add(ground);

    // 경계벽 (비대칭) — 북측 z=WORLD_Z_NORTH, 남측 z=WORLD_Z_SOUTH
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.9 });
    const wallH = 3;
    // 북측 벽 (z=WORLD_Z_NORTH)
    const wallN = new THREE.Mesh(new THREE.BoxGeometry(WORLD_SIZE, wallH, 1), wallMat);
    wallN.position.set(0, wallH / 2, WORLD_Z_NORTH);
    wallN.castShadow = true;
    group.add(wallN);
    // 남측 벽
    const wallS = new THREE.Mesh(new THREE.BoxGeometry(WORLD_SIZE, wallH, 1), wallMat);
    wallS.position.set(0, wallH / 2, WORLD_Z_SOUTH);
    wallS.castShadow = true;
    group.add(wallS);
    // 동/서측 벽 (월드 Z 범위 따라 길이 조정)
    const wallE = new THREE.Mesh(new THREE.BoxGeometry(1, wallH, WORLD_Z_LEN), wallMat);
    wallE.position.set(WORLD_SIZE / 2, wallH / 2, groundCz);
    wallE.castShadow = true;
    group.add(wallE);
    const wallW = new THREE.Mesh(new THREE.BoxGeometry(1, wallH, WORLD_Z_LEN), wallMat);
    wallW.position.set(-WORLD_SIZE / 2, wallH / 2, groundCz);
    wallW.castShadow = true;
    group.add(wallW);
}

function createRoadNetwork(group) {
    const asphaltTex = makeProceduralTexture('#2a2a2a', 30, 256);
    asphaltTex.repeat.set(8, 8);
    const sidewalkTex = makeProceduralTexture('#a8a8a8', 25, 256);
    sidewalkTex.repeat.set(8, 8);

    const roadMat = new THREE.MeshStandardMaterial({ color: 0xffffff, map: asphaltTex, roughness: 0.85 });
    const sidewalkMat = new THREE.MeshStandardMaterial({ color: 0xffffff, map: sidewalkTex, roughness: 0.9 });
    const stripeMat = new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.5, emissive: 0x553300, emissiveIntensity: 0.1 });

    // 세그먼트 도로 그리기 — 시작/끝 z 로 구간 도로 한 조각
    function drawVRoadSegment(x, w, zStart, zEnd) {
        const len = zEnd - zStart;
        if (len < 1) return;
        const cz = (zStart + zEnd) / 2;
        const sw = w + 6;
        const sidewalk = new THREE.Mesh(
            new THREE.BoxGeometry(sw, 0.06, len), sidewalkMat
        );
        sidewalk.position.set(x, 0.05, cz);
        sidewalk.receiveShadow = true;
        group.add(sidewalk);
        const road = new THREE.Mesh(
            new THREE.BoxGeometry(w, 0.06, len), roadMat
        );
        road.position.set(x, 0.08, cz);
        road.receiveShadow = true;
        group.add(road);
        for (let z = zStart + 4; z < zEnd; z += 8) {
            const stripe = new THREE.Mesh(
                new THREE.BoxGeometry(0.3, 0.05, 3), stripeMat
            );
            stripe.position.set(x, 0.12, z);
            group.add(stripe);
        }
    }

    // Y positions: grass 0, sidewalk 0.05, road 0.08, stripe 0.12 — clear z-order
    MAIN_ROADS.forEach(r => {
        const w = r.w;
        const sw = w + 6; // sidewalk wider than road
        if (r.type === 'H') {
            // Horizontal road — offsetX 로 부분 구간 도로 지원 (전체폭 290 이 아닌 경우)
            const ox = r.offsetX || 0;
            const sidewalk = new THREE.Mesh(
                new THREE.BoxGeometry(r.length, 0.06, sw),
                sidewalkMat
            );
            sidewalk.position.set(ox, 0.05, r.z);
            sidewalk.receiveShadow = true;
            group.add(sidewalk);

            const road = new THREE.Mesh(
                new THREE.BoxGeometry(r.length, 0.06, w),
                roadMat
            );
            road.position.set(ox, 0.08, r.z);
            road.receiveShadow = true;
            group.add(road);

            // Center line (dashed yellow)
            for (let x = ox - r.length/2 + 4; x < ox + r.length/2; x += 8) {
                const stripe = new THREE.Mesh(
                    new THREE.BoxGeometry(3, 0.05, 0.3),
                    stripeMat
                );
                stripe.position.set(x, 0.12, r.z);
                group.add(stripe);
            }
        } else {
            // Vertical road — 단일 세그먼트 (로데오 제거됨)
            const oz = r.offsetZ || 0;
            const zStart = oz - r.length / 2;
            const zEnd   = oz + r.length / 2;
            drawVRoadSegment(r.x, w, zStart, zEnd);
        }
    });

    // === 한국 표준 zebra 횡단보도 — 교차로 4면에만, 가운데 비움 ===
    // 줄 폭 l1=0.5m, 간격 l2=0.7m (1.5*l1), 6줄, D1≈4m, 진행방향에 수직
    const cwMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4 });
    const hRoads = MAIN_ROADS.filter(r => r.type === 'H');
    const vRoads = MAIN_ROADS.filter(r => r.type === 'V');

    const STRIPE_W   = 0.50;   // l1 (각 줄 폭)
    const STRIPE_GAP = 0.70;   // l2 (간격)
    const N_STRIPES  = 6;      // 줄 개수
    const CW_OFFSET  = 1.0;    // 교차로 가장자리에서 횡단보도 시작 거리

    hRoads.forEach(h => {
        const ohx = h.offsetX || 0;
        const hXmin = ohx - h.length / 2;
        const hXmax = ohx + h.length / 2;
        vRoads.forEach(v => {
            const oz = v.offsetZ || 0;
            const vZmin = oz - v.length / 2;
            const vZmax = oz + v.length / 2;
            const inH = v.x > hXmin && v.x < hXmax;
            const inV = h.z >= vZmin && h.z <= vZmax;
            if (!(inH && inV)) return;

            const cx = v.x, cz = h.z;

            // V 도로를 가로지르는 횡단보도(보행자 E-W 횡단) — 줄은 도로와 평행(Z축)으로 길게,
            // 줄들은 보행 방향(X축)으로 나열 — 진행방향에 수직인 l1 폭 줄무늬 (한국 표준)
            // 밴드 풋프린트: X = 줄 폭+간격 합, Z = 도로 폭(v.w) — 도로 실 구간 밖이면 그리지 않음
            const drawZebraAcrossV = (centerZ) => {
                const halfDepth = (v.w * 0.92) / 2;
                if (centerZ - halfDepth < vZmin || centerZ + halfDepth > vZmax) return;
                for (let k = 0; k < N_STRIPES; k++) {
                    const xPos = cx + (k - (N_STRIPES - 1) / 2) * (STRIPE_W + STRIPE_GAP);
                    const stripe = new THREE.Mesh(
                        new THREE.BoxGeometry(STRIPE_W, 0.05, v.w * 0.92), cwMat
                    );
                    stripe.position.set(xPos, 0.13, centerZ);
                    group.add(stripe);
                }
            };
            // H 도로를 가로지르는 횡단보도(보행자 N-S 횡단) — 줄은 도로와 평행(X축)으로 길게,
            // 줄들은 보행 방향(Z축)으로 나열 — 도로 실 구간(hXmin~hXmax) 밖이면 그리지 않음
            const drawZebraAcrossH = (centerX) => {
                const halfDepth = (h.w * 0.92) / 2;
                if (centerX - halfDepth < hXmin || centerX + halfDepth > hXmax) return;
                for (let k = 0; k < N_STRIPES; k++) {
                    const zPos = cz + (k - (N_STRIPES - 1) / 2) * (STRIPE_W + STRIPE_GAP);
                    const stripe = new THREE.Mesh(
                        new THREE.BoxGeometry(h.w * 0.92, 0.05, STRIPE_W), cwMat
                    );
                    stripe.position.set(centerX, 0.13, zPos);
                    group.add(stripe);
                }
            };

            // 4면 횡단보도 — 교차로 가장자리에서 CW_OFFSET 만큼 띄운 위치에 밴드 배치
            // (밴드 깊이 = 횡단 대상 도로의 폭)
            drawZebraAcrossV(cz + h.w / 2 + CW_OFFSET + (v.w * 0.92) / 2);
            drawZebraAcrossV(cz - h.w / 2 - CW_OFFSET - (v.w * 0.92) / 2);
            drawZebraAcrossH(cx + v.w / 2 + CW_OFFSET + (h.w * 0.92) / 2);
            drawZebraAcrossH(cx - v.w / 2 - CW_OFFSET - (h.w * 0.92) / 2);
        });
    });
}

// 상업지구 전체 = 로데오 거리 — 가로 2줄 로데오 + 양옆 상가
// 차량 도로 없음 (CORE RULE 준수)
function createRodeoStreet(group) {
    // 2개 로데오 생성 (N: z=-22~-15, S: z=-62~-55)
    const RODEOS = [
        { rzMin: -22, rzMax: -15, name: 'N' },
        { rzMin: -62, rzMax: -55, name: 'S' }
    ];
    RODEOS.forEach((rodeo, idx) => buildRodeoStrip(group, rodeo.rzMin, rodeo.rzMax, idx));
}

// 단일 로데오 스트립 생성
function buildRodeoStrip(group, RZ_MIN, RZ_MAX, idx) {
    const RX_MIN = 5, RX_MAX = 135;
    const RW = RX_MAX - RX_MIN;
    const RD = RZ_MAX - RZ_MIN;
    const RCX = (RX_MIN + RX_MAX) / 2;
    const RCZ = (RZ_MIN + RZ_MAX) / 2;

    // 메인 타일 보도 — 베이지 톤 + 가로 줄무늬 패턴
    const tileTex = makeProceduralTexture('#d4c8a8', 28, 256);
    tileTex.repeat.set(20, 6);
    const tileMat = new THREE.MeshStandardMaterial({
        color: 0xffffff, map: tileTex, roughness: 0.88
    });
    const plaza = new THREE.Mesh(
        new THREE.BoxGeometry(RW, 0.08, RD), tileMat
    );
    plaza.position.set(RCX, 0.10, RCZ);
    plaza.receiveShadow = true;
    group.add(plaza);

    // 중앙 라인 (장식 띠)
    const stripeMat = new THREE.MeshStandardMaterial({
        color: 0xc8a878, roughness: 0.75
    });
    const stripe = new THREE.Mesh(
        new THREE.BoxGeometry(RW - 4, 0.05, 0.8), stripeMat
    );
    stripe.position.set(RCX, 0.16, RCZ);
    group.add(stripe);

    // 벤치는 제거 (사용자 요청)

    // 중앙 가로수 + 화분 + 가로등
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5c3a1e, roughness: 0.9 });
    const folMat = new THREE.MeshStandardMaterial({ color: 0x3a7a2e, roughness: 0.85 });
    const lampPoleMat = new THREE.MeshStandardMaterial({ color: 0x333333, metalness: 0.6, roughness: 0.35 });
    const lampGlobeMat = new THREE.MeshStandardMaterial({
        color: 0xffeeaa, emissive: 0x553300, emissiveIntensity: 0, roughness: 0.4
    });
    const planterMat = new THREE.MeshStandardMaterial({ color: 0x9a8770, roughness: 0.9 });
    const treeSpacing = 9;
    for (let tx = RX_MIN + 6; tx <= RX_MAX - 4; tx += treeSpacing) {
        // 사각 화분
        const planter = new THREE.Mesh(
            new THREE.BoxGeometry(1.4, 0.4, 1.4), planterMat
        );
        planter.position.set(tx, 0.32, RCZ);
        planter.castShadow = true;
        group.add(planter);
        // 가로수
        const trunkH = 2.6;
        const trunk = new THREE.Mesh(
            new THREE.CylinderGeometry(0.15, 0.25, trunkH, 8), trunkMat
        );
        trunk.position.set(tx, 0.52 + trunkH / 2, RCZ);
        trunk.castShadow = true;
        group.add(trunk);
        const foliage = new THREE.Mesh(
            new THREE.SphereGeometry(1.2, 12, 12), folMat
        );
        foliage.position.set(tx, 0.52 + trunkH + 0.7, RCZ);
        foliage.castShadow = true;
        group.add(foliage);

        // 가로등 (가로수 옆마다)
        const poleH = 4.0;
        const pole = new THREE.Mesh(
            new THREE.CylinderGeometry(0.07, 0.10, poleH, 10), lampPoleMat
        );
        pole.position.set(tx + 3.5, poleH / 2 + 0.05, RCZ);
        pole.castShadow = true;
        group.add(pole);
        const globe = new THREE.Mesh(
            new THREE.SphereGeometry(0.22, 12, 12), lampGlobeMat
        );
        globe.position.set(tx + 3.5, poleH + 0.05, RCZ);
        globe.userData.isStreetLight = true;
        group.add(globe);
    }

    // 입구 표지 — 양끝에 작은 아치형 게이트 느낌의 기둥 2쌍
    const pillarMat = new THREE.MeshStandardMaterial({ color: 0xa89878, roughness: 0.75 });
    [RX_MIN + 1, RX_MAX - 1].forEach(px => {
        [RCZ - 5.5, RCZ + 5.5].forEach(pz => {
            const pillar = new THREE.Mesh(
                new THREE.BoxGeometry(0.6, 4.5, 0.6), pillarMat
            );
            pillar.position.set(px, 2.3, pz);
            pillar.castShadow = true;
            group.add(pillar);
            const top = new THREE.Mesh(
                new THREE.BoxGeometry(0.9, 0.25, 0.9), pillarMat
            );
            top.position.set(px, 4.6, pz);
            group.add(top);
        });
    });

    // "RODEO" 입구 사인 (양끝 상단)
    [RX_MIN + 1, RX_MAX - 1].forEach((px, idx) => {
        const cv = document.createElement('canvas');
        cv.width = 512; cv.height = 128;
        const ctx = cv.getContext('2d');
        ctx.fillStyle = '#1a1a2a';
        ctx.fillRect(0, 0, 512, 128);
        ctx.fillStyle = '#ffd700';
        ctx.font = 'bold 56px "Inter","Noto Sans KR",sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText('RODEO', 256, 50);
        ctx.font = 'bold 28px "Noto Sans KR",sans-serif';
        ctx.fillStyle = '#fff';
        ctx.fillText('평내 로데오 거리', 256, 95);
        const tex = new THREE.CanvasTexture(cv);
        const sign = new THREE.Mesh(
            new THREE.PlaneGeometry(8, 2),
            new THREE.MeshStandardMaterial({
                map: tex, emissive: 0x222244, emissiveIntensity: 0.5
            })
        );
        sign.position.set(px, 5.5, RCZ);
        sign.rotation.y = idx === 0 ? Math.PI / 2 : -Math.PI / 2;
        group.add(sign);
    });
}

function createPoliceStation(group) {
    // z=67: H z=55 도로(asphalt 51~59) 와 H z=85 도로(asphalt 81~89) 사이 공터.
    // 경찰서 풋프린트(±d/2=±7) 가 두 도로 asphalt 와 전혀 겹치지 않는 유일한 안전 구간(z 66~74).
    // 도로(남쪽 z=55) 방향 -Z 에 입구 — 통과 가능 + 내부 진입
    const x = 0, z = 67;
    const w = 18, d = 14, h = 14;
    const building = createPoliceStationShell(group, x, z, w, d, h);
    // 내부 가구·구치소·취조실 + 충돌 박스 등록
    createPoliceInterior(group, x, z, w, d, h);

    // Police signage (KOREAN POLICE) — 도로(남쪽) 방향 외벽 상단
    const cv = document.createElement('canvas');
    cv.width = 512; cv.height = 96;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = '#003399';
    ctx.fillRect(0, 0, 512, 96);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 56px Inter, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('경찰서 POLICE', 256, 48);
    const tex = new THREE.CanvasTexture(cv);
    const signMesh = new THREE.Mesh(
        new THREE.PlaneGeometry(10, 1.8),
        new THREE.MeshStandardMaterial({ map: tex, emissive: 0x001144, emissiveIntensity: 0.3, side: THREE.DoubleSide })
    );
    signMesh.position.set(x, h - 1.5, z - d / 2 - 0.30);  // 외벽 표면(z=60-0.2) 보다 살짝 앞
    signMesh.rotation.y = Math.PI; // -Z (남쪽 도로) 방향
    group.add(signMesh);

    // Police lights (blue+red flashing on roof)
    const blueLight = new THREE.Mesh(
        new THREE.SphereGeometry(0.5, 16, 16),
        new THREE.MeshStandardMaterial({ color: 0x0066ff, emissive: 0x0066ff, emissiveIntensity: 1.0 })
    );
    blueLight.position.set(x - 2, h + 0.7, z);
    blueLight.userData.policeLight = 'blue';
    group.add(blueLight);

    const redLight = new THREE.Mesh(
        new THREE.SphereGeometry(0.5, 16, 16),
        new THREE.MeshStandardMaterial({ color: 0xff0000, emissive: 0xff0000, emissiveIntensity: 1.0 })
    );
    redLight.position.set(x + 2, h + 0.7, z);
    redLight.userData.policeLight = 'red';
    group.add(redLight);

    // Flagpole + Korean flag area
    const pole = new THREE.Mesh(
        new THREE.CylinderGeometry(0.1, 0.1, 10, 8),
        new THREE.MeshStandardMaterial({ color: 0xcccccc, roughness: 0.4, metalness: 0.6 })
    );
    pole.position.set(x + 10, 5, z + 7);
    group.add(pole);

    // Standalone POLICE signpost — 도로(남쪽) 쪽 인도에 배치
    const spMat = new THREE.MeshStandardMaterial({ color: 0x222244, roughness: 0.6, metalness: 0.5 });
    const signPost = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 4.5, 8), spMat);
    const SP_Z = z - d / 2 - 3; // 경찰서 남쪽 3m (도로 z=95 와 경찰서 z=103 사이의 인도)
    signPost.position.set(x, 2.25, SP_Z);
    group.add(signPost);

    const spCV = document.createElement('canvas');
    spCV.width = 320; spCV.height = 160;
    const spCtx = spCV.getContext('2d');
    // Background gradient (dark blue → navy)
    const grad = spCtx.createLinearGradient(0, 0, 0, 160);
    grad.addColorStop(0, '#0033aa'); grad.addColorStop(1, '#001166');
    spCtx.fillStyle = grad; spCtx.fillRect(0, 0, 320, 160);
    // White border
    spCtx.strokeStyle = '#ffffff'; spCtx.lineWidth = 5;
    spCtx.strokeRect(5, 5, 310, 150);
    // Star badge (simple circle emblem)
    spCtx.fillStyle = '#ffdd00';
    spCtx.beginPath(); spCtx.arc(36, 80, 22, 0, Math.PI * 2); spCtx.fill();
    spCtx.fillStyle = '#003399';
    spCtx.beginPath(); spCtx.arc(36, 80, 16, 0, Math.PI * 2); spCtx.fill();
    spCtx.fillStyle = '#ffdd00';
    spCtx.beginPath(); spCtx.arc(36, 80, 9, 0, Math.PI * 2); spCtx.fill();
    // POLICE text
    spCtx.fillStyle = '#ffffff';
    spCtx.font = 'bold 62px Inter, sans-serif';
    spCtx.textAlign = 'left'; spCtx.textBaseline = 'middle';
    spCtx.fillText('POLICE', 68, 68);
    spCtx.font = 'bold 30px Inter, sans-serif';
    spCtx.fillStyle = '#99ccff';
    spCtx.fillText('경    찰    서', 68, 118);
    const spTex = new THREE.CanvasTexture(spCV);
    // DoubleSide 로 한 장만 — 도로(남쪽 -Z) 향함, 양면에서 보임
    const spBoard = new THREE.Mesh(
        new THREE.PlaneGeometry(5, 2.5),
        new THREE.MeshStandardMaterial({ map: spTex, emissive: 0x001133, emissiveIntensity: 0.5, side: THREE.DoubleSide })
    );
    spBoard.position.set(x, 5.5, SP_Z);
    spBoard.rotation.y = Math.PI; // 도로(남쪽) 방향 향함
    group.add(spBoard);
    // Sign cap (top of board)
    const spCap = new THREE.Mesh(
        new THREE.BoxGeometry(5.3, 0.25, 0.35),
        new THREE.MeshStandardMaterial({ color: 0x001166, roughness: 0.5 })
    );
    spCap.position.set(x, 6.75, SP_Z);
    group.add(spCap);

    // 단일 출처 — PRINCIPLES.md #9 (다른 모듈은 window._policeStation 참조)
    window._policeStation = { x, z, w, d, h, frontZ: z - d / 2, backZ: z + d / 2 };
    return { mesh: building, x, z, w, d, h, type: 'police', zone: 'POLICE' };
}

// 경찰서 외피 — 4벽(남측 입구 갭) + 옥상 + 콘크리트 베이스. 단일 박스 아닌 분할 벽으로 내부 가시화.
function createPoliceStationShell(group, x, z, w, d, h) {
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x1a3a5c, roughness: 0.78, metalness: 0.08 });
    const baseMat = new THREE.MeshStandardMaterial({ color: 0x999999, roughness: 0.95 });
    const winMat = new THREE.MeshStandardMaterial({
        color: 0x88ccff, emissive: 0x334455, emissiveIntensity: 0.3,
        roughness: 0.3, metalness: 0.5
    });
    const ledgeMat = new THREE.MeshStandardMaterial({ color: 0x555555, roughness: 0.8 });
    const floorMat = new THREE.MeshStandardMaterial({ color: 0x6e6a64, roughness: 0.85 });

    const wt = 0.4;  // 벽 두께
    const halfW = w / 2, halfD = d / 2;
    const ENTRANCE_W = 4.5;  // 입구 갭 (도로 -Z 방향)
    const halfE = ENTRANCE_W / 2;

    // 콘크리트 베이스
    const base = new THREE.Mesh(new THREE.BoxGeometry(w + 0.4, 0.5, d + 0.4), baseMat);
    base.position.set(x, 0.25, z);
    base.receiveShadow = true;
    group.add(base);

    // 실내 바닥 (타일/콘크리트)
    const floor = new THREE.Mesh(new THREE.BoxGeometry(w - 0.6, 0.04, d - 0.6), floorMat);
    floor.position.set(x, 0.52, z);
    floor.receiveShadow = true;
    group.add(floor);

    // 남측 벽 (z = z - halfD) — 입구 갭 좌우 2조각
    const southZ = z - halfD;
    const southSegW = (w - ENTRANCE_W) / 2;
    const southSegHalfW = southSegW / 2;
    const sLeft = new THREE.Mesh(new THREE.BoxGeometry(southSegW, h, wt), wallMat);
    sLeft.position.set(x - halfE - southSegHalfW, h / 2, southZ);
    sLeft.castShadow = true; sLeft.receiveShadow = true;
    group.add(sLeft);
    const sRight = sLeft.clone();
    sRight.position.set(x + halfE + southSegHalfW, h / 2, southZ);
    group.add(sRight);

    // 남측 입구 상단 — 입구 위 가로 도리 (h>3 부분)
    const sTop = new THREE.Mesh(new THREE.BoxGeometry(ENTRANCE_W, h - 3, wt), wallMat);
    sTop.position.set(x, 3 + (h - 3) / 2, southZ);
    sTop.castShadow = true;
    group.add(sTop);

    // 북측 벽 (z = z + halfD) — solid
    const northZ = z + halfD;
    const north = new THREE.Mesh(new THREE.BoxGeometry(w, h, wt), wallMat);
    north.position.set(x, h / 2, northZ);
    north.castShadow = true; north.receiveShadow = true;
    group.add(north);

    // 동측 벽
    const east = new THREE.Mesh(new THREE.BoxGeometry(wt, h, d), wallMat);
    east.position.set(x + halfW, h / 2, z);
    east.castShadow = true; east.receiveShadow = true;
    group.add(east);

    // 서측 벽
    const west = east.clone();
    west.position.set(x - halfW, h / 2, z);
    group.add(west);

    // 옥상 슬래브
    const roof = new THREE.Mesh(new THREE.BoxGeometry(w + 0.6, 0.3, d + 0.6), ledgeMat);
    roof.position.set(x, h + 0.15, z);
    roof.castShadow = true; roof.receiveShadow = true;
    group.add(roof);

    // 외벽 창문 (남측 입구 좌우, 동/서 측면, 북측 — 각 층)
    const floors = Math.max(1, Math.floor(h / 3));
    for (let f = 0; f < floors; f++) {
        const wy = 1.5 + f * 3;
        // 남측 좌측 벽에 창문 2개
        for (let i = 0; i < 2; i++) {
            const winS = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.3, 0.08), winMat);
            winS.position.set(x - halfE - southSegHalfW + (i - 0.5) * 2.0, wy, southZ - 0.05);
            group.add(winS);
        }
        for (let i = 0; i < 2; i++) {
            const winS = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.3, 0.08), winMat);
            winS.position.set(x + halfE + southSegHalfW + (i - 0.5) * 2.0, wy, southZ - 0.05);
            group.add(winS);
        }
        // 북측 창문 3개
        for (let i = 0; i < 3; i++) {
            const winN = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.3, 0.08), winMat);
            winN.position.set(x + (i - 1) * 5.0, wy, northZ + 0.05);
            group.add(winN);
        }
        // 동/서 창문 각 2개
        for (let i = 0; i < 2; i++) {
            const winE = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.3, 0.9), winMat);
            winE.position.set(x + halfW + 0.05, wy, z + (i - 0.5) * 4.5);
            group.add(winE);
            const winW = winE.clone();
            winW.position.set(x - halfW - 0.05, wy, z + (i - 0.5) * 4.5);
            group.add(winW);
        }
    }

    // 남측 입구 유리 자동문 (도로 방향 -Z, rotY=Math.PI)
    createGlassScreenDoor(group, x, 0, southZ - 0.02, ENTRANCE_W - 0.3, 2.9, Math.PI);

    return roof; // 옥상 메쉬 반환 (mesh 참조용)
}

// 경찰서 내부 — 3 구치소, 취조실, 형사 책상/의자 + 충돌 박스 등록
function createPoliceInterior(group, x, z, w, d, h) {
    window._policeColliders = window._policeColliders || [];
    const colliders = window._policeColliders;
    colliders.length = 0;

    // 외피 4벽 충돌 등록 (남측은 입구 좌우 2조각만 — 입구 갭은 통과 가능)
    const halfW = w / 2, halfD = d / 2;
    const ENTRANCE_W = 4.5;
    const halfE = ENTRANCE_W / 2;
    const southZ = z - halfD;
    const northZ = z + halfD;
    const southSegW = (w - ENTRANCE_W) / 2;

    // 남측 좌·우 외벽
    colliders.push({ x: x - halfE - southSegW / 2, z: southZ, w: southSegW, d: 0.4, hideoutIndex: -1 });
    colliders.push({ x: x + halfE + southSegW / 2, z: southZ, w: southSegW, d: 0.4, hideoutIndex: -1 });
    // 북측 외벽
    colliders.push({ x: x, z: northZ, w: w, d: 0.4, hideoutIndex: -1 });
    // 동측 외벽
    colliders.push({ x: x + halfW, z: z, w: 0.4, d: d, hideoutIndex: -1 });
    // 서측 외벽
    colliders.push({ x: x - halfW, z: z, w: 0.4, d: d, hideoutIndex: -1 });

    // === 내부 자재 / 가구 ===
    const wallMat = new THREE.MeshStandardMaterial({ color: 0xd6d2c8, roughness: 0.85 });
    const cellWallMat = new THREE.MeshStandardMaterial({ color: 0xa8a8a8, roughness: 0.88 });
    const barMat = new THREE.MeshStandardMaterial({ color: 0x3a3a3a, roughness: 0.4, metalness: 0.85 });
    const deskMat = new THREE.MeshStandardMaterial({ color: 0x6b3f2a, roughness: 0.72 });
    const deskTopMat = new THREE.MeshStandardMaterial({ color: 0x4a2a1a, roughness: 0.6 });
    const chairMat = new THREE.MeshStandardMaterial({ color: 0x222232, roughness: 0.7, metalness: 0.2 });
    const cellBedMat = new THREE.MeshStandardMaterial({ color: 0x6a6a78, roughness: 0.85 });
    const cellMattressMat = new THREE.MeshStandardMaterial({ color: 0x88c0d0, roughness: 0.7 });
    const interrogTableMat = new THREE.MeshStandardMaterial({ color: 0x4a4a52, roughness: 0.55, metalness: 0.4 });
    const interrogLightMat = new THREE.MeshStandardMaterial({
        color: 0xfff1c4, emissive: 0xfff1a0, emissiveIntensity: 1.2, roughness: 0.3
    });

    // 1) 구치소 행 (북측 z = z+halfD-4 ~ z+halfD) — 3 칸
    // 셀 구역: z ∈ [northZ - 4, northZ - 0.2], x 전체 [x-halfW+0.2, x+halfW-0.2]
    const cellRowZ = northZ - 2;           // 셀 중앙 z
    const cellRowDepth = 3.6;              // 셀 깊이
    const cellRowMinX = x - halfW + 0.4;
    const cellRowMaxX = x + halfW - 0.4;
    const cellRowW = cellRowMaxX - cellRowMinX;
    const cellW = cellRowW / 3;            // 각 셀 폭 ≈ 5.7m

    // 셀 전면 (남측) 벽 — 셀 코리도 분리, 각 셀마다 1m 짜리 출입구 갭
    const cellFrontZ = cellRowZ - cellRowDepth / 2 + 0.1;  // 셀 전면 z
    const cellWallH = h - 0.6;
    // 셀 전면 벽: 각 셀당 5.7m, 가운데 1.2m 출입구 갭 (양옆 2.25m씩 벽)
    for (let i = 0; i < 3; i++) {
        const cx = cellRowMinX + cellW * (i + 0.5);
        const segHalf = (cellW - 1.2) / 2 / 2;   // 양옆 짧은 벽 폭의 절반
        const segW = (cellW - 1.2) / 2;
        // 좌측 짧은 벽 (출입구 좌측)
        const segL = new THREE.Mesh(new THREE.BoxGeometry(segW, cellWallH, 0.2), cellWallMat);
        segL.position.set(cx - 0.6 - segHalf, cellWallH / 2 + 0.54, cellFrontZ);
        group.add(segL);
        colliders.push({ x: cx - 0.6 - segHalf, z: cellFrontZ, w: segW, d: 0.2, hideoutIndex: -1 });
        const segR = segL.clone();
        segR.position.set(cx + 0.6 + segHalf, cellWallH / 2 + 0.54, cellFrontZ);
        group.add(segR);
        colliders.push({ x: cx + 0.6 + segHalf, z: cellFrontZ, w: segW, d: 0.2, hideoutIndex: -1 });

        // 셀 출입구 위 도리 (상단 가로 바)
        const lintel = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.4, 0.2), cellWallMat);
        lintel.position.set(cx, 2.7 + 0.2, cellFrontZ);
        group.add(lintel);

        // 셀 출입구 — 검은 철창 (BARS) 5줄 세로
        for (let b = 0; b < 5; b++) {
            const bar = new THREE.Mesh(
                new THREE.BoxGeometry(0.08, 2.6, 0.08), barMat
            );
            bar.position.set(cx - 0.5 + (b * 1.0 / 4), 1.84, cellFrontZ);
            group.add(bar);
        }
        // 가로 바 2줄
        for (let h2 = 0; h2 < 2; h2++) {
            const hbar = new THREE.Mesh(
                new THREE.BoxGeometry(1.2, 0.06, 0.06), barMat
            );
            hbar.position.set(cx, 0.6 + h2 * 2.0, cellFrontZ);
            group.add(hbar);
        }

        // 셀 내부 침상 (각 셀 안 침대)
        const bedFrame = new THREE.Mesh(
            new THREE.BoxGeometry(cellW * 0.6, 0.4, 1.8), cellBedMat
        );
        bedFrame.position.set(cx, 0.74, cellRowZ + 0.6);
        group.add(bedFrame);
        const mattress = new THREE.Mesh(
            new THREE.BoxGeometry(cellW * 0.55, 0.15, 1.6), cellMattressMat
        );
        mattress.position.set(cx, 1.01, cellRowZ + 0.6);
        group.add(mattress);
        colliders.push({ x: cx, z: cellRowZ + 0.6, w: cellW * 0.6, d: 1.8, hideoutIndex: -1 });

        // 셀 번호 표지 (간단한 사각 사인)
        const cellSignCV = document.createElement('canvas');
        cellSignCV.width = 128; cellSignCV.height = 64;
        const csCtx = cellSignCV.getContext('2d');
        csCtx.fillStyle = '#0a1a2a';
        csCtx.fillRect(0, 0, 128, 64);
        csCtx.fillStyle = '#ffdd66';
        csCtx.font = 'bold 36px Inter, sans-serif';
        csCtx.textAlign = 'center'; csCtx.textBaseline = 'middle';
        csCtx.fillText('구치소 ' + (i + 1), 64, 32);
        const csTex = new THREE.CanvasTexture(cellSignCV);
        const cellSign = new THREE.Mesh(
            new THREE.PlaneGeometry(1.4, 0.7),
            new THREE.MeshStandardMaterial({ map: csTex, emissive: 0x222244, emissiveIntensity: 0.4, side: THREE.DoubleSide })
        );
        cellSign.position.set(cx, 3.3, cellFrontZ - 0.12);
        cellSign.rotation.y = Math.PI;
        group.add(cellSign);
    }
    // 셀 간 칸막이 벽 (x = cellRowMinX + cellW, cellRowMinX + 2*cellW)
    for (let i = 1; i < 3; i++) {
        const divX = cellRowMinX + cellW * i;
        const div = new THREE.Mesh(
            new THREE.BoxGeometry(0.2, cellWallH, cellRowDepth), cellWallMat
        );
        div.position.set(divX, cellWallH / 2 + 0.54, cellRowZ);
        group.add(div);
        colliders.push({ x: divX, z: cellRowZ, w: 0.2, d: cellRowDepth, hideoutIndex: -1 });
    }

    // 2) 취조실 — 서남쪽 코너 (x ∈ [x-halfW+0.2, x-halfW+0.2+5.5], z ∈ [southZ+0.2, cellFrontZ-0.4])
    const irMinX = x - halfW + 0.4;
    const irMaxX = x - halfW + 5.8;
    const irMinZ = southZ + 0.4;
    const irMaxZ = cellFrontZ - 0.5;
    const irCx = (irMinX + irMaxX) / 2;
    const irCz = (irMinZ + irMaxZ) / 2;
    const irW = irMaxX - irMinX;
    const irD = irMaxZ - irMinZ;

    // 취조실 동측 벽 (x = irMaxX) — 도어 갭 z ∈ [irCz-0.7, irCz+0.7]
    const irDoorGapHalf = 0.7;
    const irEastWallSegD = (irD - irDoorGapHalf * 2) / 2;
    const irEastUp = new THREE.Mesh(
        new THREE.BoxGeometry(0.2, cellWallH, irEastWallSegD), wallMat
    );
    irEastUp.position.set(irMaxX, cellWallH / 2 + 0.54, irMinZ + irEastWallSegD / 2);
    group.add(irEastUp);
    colliders.push({ x: irMaxX, z: irMinZ + irEastWallSegD / 2, w: 0.2, d: irEastWallSegD, hideoutIndex: -1 });
    const irEastDown = irEastUp.clone();
    irEastDown.position.set(irMaxX, cellWallH / 2 + 0.54, irMaxZ - irEastWallSegD / 2);
    group.add(irEastDown);
    colliders.push({ x: irMaxX, z: irMaxZ - irEastWallSegD / 2, w: 0.2, d: irEastWallSegD, hideoutIndex: -1 });

    // 취조실 북측 벽 (z = irMaxZ) — solid (셀 전면 벽과 분리)
    const irNorth = new THREE.Mesh(
        new THREE.BoxGeometry(irW, cellWallH, 0.2), wallMat
    );
    irNorth.position.set(irCx, cellWallH / 2 + 0.54, irMaxZ);
    group.add(irNorth);
    colliders.push({ x: irCx, z: irMaxZ, w: irW, d: 0.2, hideoutIndex: -1 });

    // 취조실 책상 (메탈 톤, 강제 조명 아래)
    const irTable = new THREE.Mesh(
        new THREE.BoxGeometry(1.8, 0.06, 0.9), interrogTableMat
    );
    irTable.position.set(irCx, 0.92, irCz);
    irTable.castShadow = true;
    group.add(irTable);
    // 책상 다리 4개
    for (let lx = -1; lx <= 1; lx += 2) {
        for (let lz = -1; lz <= 1; lz += 2) {
            const leg = new THREE.Mesh(
                new THREE.BoxGeometry(0.08, 0.9, 0.08), interrogTableMat
            );
            leg.position.set(irCx + lx * 0.78, 0.45, irCz + lz * 0.35);
            group.add(leg);
        }
    }
    colliders.push({ x: irCx, z: irCz, w: 1.8, d: 0.9, hideoutIndex: -1 });

    // 취조실 의자 2개 (책상 양옆)
    [-1, 1].forEach(dir => {
        const seat = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, 0.08, 0.5), chairMat
        );
        seat.position.set(irCx, 0.6, irCz + dir * 0.95);
        group.add(seat);
        const back = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, 0.7, 0.06), chairMat
        );
        back.position.set(irCx, 0.95, irCz + dir * (0.95 + (dir > 0 ? 0.22 : -0.22)));
        group.add(back);
        colliders.push({ x: irCx, z: irCz + dir * 0.95, w: 0.5, d: 0.5, hideoutIndex: -1 });
    });

    // 취조실 천장 스포트라이트 (강제 조명 — emissive 큰 구체)
    const irLight = new THREE.Mesh(
        new THREE.SphereGeometry(0.22, 12, 12), interrogLightMat
    );
    irLight.position.set(irCx, 2.6, irCz);
    group.add(irLight);
    const irLightCord = new THREE.Mesh(
        new THREE.CylinderGeometry(0.02, 0.02, 0.8, 6),
        new THREE.MeshStandardMaterial({ color: 0x222222 })
    );
    irLightCord.position.set(irCx, 3.0, irCz);
    group.add(irLightCord);

    // 취조실 표지판 ("취조실")
    const irSignCV = document.createElement('canvas');
    irSignCV.width = 256; irSignCV.height = 80;
    const irCtx = irSignCV.getContext('2d');
    irCtx.fillStyle = '#1a1a2a';
    irCtx.fillRect(0, 0, 256, 80);
    irCtx.fillStyle = '#ffaa44';
    irCtx.font = 'bold 42px "Noto Sans KR", Inter, sans-serif';
    irCtx.textAlign = 'center'; irCtx.textBaseline = 'middle';
    irCtx.fillText('취조실', 128, 40);
    const irSignTex = new THREE.CanvasTexture(irSignCV);
    const irSign = new THREE.Mesh(
        new THREE.PlaneGeometry(2.4, 0.75),
        new THREE.MeshStandardMaterial({ map: irSignTex, emissive: 0x442200, emissiveIntensity: 0.5, side: THREE.DoubleSide })
    );
    irSign.position.set(irMaxX + 0.12, 3.0, irCz);
    irSign.rotation.y = -Math.PI / 2;  // +X 방향 (코리도 쪽)
    group.add(irSign);

    // 3) 형사 업무 공간 — 동쪽 절반 (취조실 옆) 책상 3개 + 의자
    // 책상 영역: x ∈ [irMaxX + 0.8, x + halfW - 0.6], z ∈ [southZ + 0.8, cellFrontZ - 0.6]
    const deskAreaMinX = irMaxX + 1.2;
    const deskAreaMaxX = x + halfW - 0.6;
    const deskAreaMinZ = southZ + 1.0;
    const deskAreaMaxZ = cellFrontZ - 0.8;
    const deskCount = 3;
    const deskSpacing = (deskAreaMaxX - deskAreaMinX) / deskCount;
    for (let dk = 0; dk < deskCount; dk++) {
        const dcx = deskAreaMinX + deskSpacing * (dk + 0.5);
        const dcz = deskAreaMinZ + 1.0;
        // 책상 상판
        const top = new THREE.Mesh(
            new THREE.BoxGeometry(1.6, 0.08, 0.85), deskTopMat
        );
        top.position.set(dcx, 0.95, dcz);
        top.castShadow = true;
        group.add(top);
        // 다리 4개
        for (let lx = -1; lx <= 1; lx += 2) {
            for (let lz = -1; lz <= 1; lz += 2) {
                const leg = new THREE.Mesh(
                    new THREE.BoxGeometry(0.08, 0.92, 0.08), deskMat
                );
                leg.position.set(dcx + lx * 0.7, 0.46, dcz + lz * 0.34);
                group.add(leg);
            }
        }
        colliders.push({ x: dcx, z: dcz, w: 1.6, d: 0.85, hideoutIndex: -1 });

        // 책상 위 모니터 (어두운 박스 + 글로우)
        const monitor = new THREE.Mesh(
            new THREE.BoxGeometry(0.9, 0.6, 0.08),
            new THREE.MeshStandardMaterial({
                color: 0x111122, emissive: 0x2244aa, emissiveIntensity: 0.4, roughness: 0.3, metalness: 0.4
            })
        );
        monitor.position.set(dcx, 1.35, dcz - 0.25);
        group.add(monitor);
        const monStand = new THREE.Mesh(
            new THREE.BoxGeometry(0.08, 0.18, 0.08),
            new THREE.MeshStandardMaterial({ color: 0x222222 })
        );
        monStand.position.set(dcx, 1.08, dcz - 0.25);
        group.add(monStand);
        // 키보드
        const kbd = new THREE.Mesh(
            new THREE.BoxGeometry(0.7, 0.04, 0.25),
            new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.4 })
        );
        kbd.position.set(dcx, 1.01, dcz + 0.05);
        group.add(kbd);
        // 종이 파일 더미
        const paper = new THREE.Mesh(
            new THREE.BoxGeometry(0.4, 0.06, 0.3),
            new THREE.MeshStandardMaterial({ color: 0xddccaa, roughness: 0.85 })
        );
        paper.position.set(dcx + 0.5, 1.02, dcz + 0.15);
        group.add(paper);
        // 머그컵
        const mug = new THREE.Mesh(
            new THREE.CylinderGeometry(0.07, 0.07, 0.13, 12),
            new THREE.MeshStandardMaterial({ color: 0xeedd88, roughness: 0.5 })
        );
        mug.position.set(dcx - 0.6, 1.05, dcz - 0.2);
        group.add(mug);

        // 의자 (책상 남쪽 - 형사 앉는 자리)
        const seat = new THREE.Mesh(
            new THREE.BoxGeometry(0.55, 0.08, 0.55), chairMat
        );
        seat.position.set(dcx, 0.55, dcz + 0.95);
        group.add(seat);
        const back = new THREE.Mesh(
            new THREE.BoxGeometry(0.55, 0.7, 0.06), chairMat
        );
        back.position.set(dcx, 0.92, dcz + 1.17);
        group.add(back);
        const chairPole = new THREE.Mesh(
            new THREE.CylinderGeometry(0.04, 0.04, 0.5, 8),
            new THREE.MeshStandardMaterial({ color: 0x444444, metalness: 0.7 })
        );
        chairPole.position.set(dcx, 0.3, dcz + 0.95);
        group.add(chairPole);
        colliders.push({ x: dcx, z: dcz + 0.95, w: 0.55, d: 0.55, hideoutIndex: -1 });
    }

    // 안내 표지 — 입구 안쪽 (도로 방향에서 들어올 때 보이도록)
    const infoCV = document.createElement('canvas');
    infoCV.width = 256; infoCV.height = 96;
    const iCtx = infoCV.getContext('2d');
    iCtx.fillStyle = '#001a4a';
    iCtx.fillRect(0, 0, 256, 96);
    iCtx.fillStyle = '#ffdd66';
    iCtx.font = 'bold 32px "Noto Sans KR", Inter, sans-serif';
    iCtx.textAlign = 'center'; iCtx.textBaseline = 'middle';
    iCtx.fillText('남양주경찰서', 128, 28);
    iCtx.font = 'bold 20px Inter, sans-serif';
    iCtx.fillStyle = '#aaccff';
    iCtx.fillText('NAMYANGJU POLICE', 128, 60);
    const infoTex = new THREE.CanvasTexture(infoCV);
    const infoSign = new THREE.Mesh(
        new THREE.PlaneGeometry(3.0, 1.1),
        new THREE.MeshStandardMaterial({ map: infoTex, emissive: 0x001144, emissiveIntensity: 0.4, side: THREE.DoubleSide })
    );
    infoSign.position.set(x, 3.5, southZ + 0.12);  // 입구 도리(y=3~) 위쪽 안쪽 표지
    group.add(infoSign);
}

// 주거지구 아파트 단지명 + 동번호 양각 라벨
// 좌우 측면 (창문 없는 외벽)에 단지명 + 거대 동번호 통합 배치
function createApartmentLabel(group, b) {
    const cplx = b.complex;
    if (!cplx) return;

    // 단지명을 2줄로 분리 — "평내" + 브랜드명 (글자 잘림 방지)
    const dongStr = String(b.dong);
    let krL1, krL2;
    if (cplx.kr.startsWith('평내')) {
        krL1 = '평내';
        krL2 = cplx.kr.substring(2);
    } else {
        const half = Math.ceil(cplx.kr.length / 2);
        krL1 = cplx.kr.substring(0, half);
        krL2 = cplx.kr.substring(half);
    }

    const sideW = Math.min(b.bd * 0.95, 7.6);
    const sideH = Math.min(b.bh * 0.55, 18.0);

    const cv1 = document.createElement('canvas');
    cv1.width = 512; cv1.height = 1280;
    const ctx1 = cv1.getContext('2d');
    ctx1.clearRect(0, 0, 512, 1280);
    function bevelText(ctx, text, font, x, y) {
        ctx.font = font;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        // 그림자 (양각 효과)
        ctx.fillStyle = 'rgba(0,0,0,0.55)';
        ctx.fillText(text, x + 5, y + 5);
        // 하이라이트
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.fillText(text, x - 2, y - 2);
        // 메인 (메탈 그레이→다크블루)
        const grad = ctx.createLinearGradient(x, y - 100, x, y + 100);
        grad.addColorStop(0, '#3a3a4a');
        grad.addColorStop(0.5, '#1a1a2a');
        grad.addColorStop(1, '#0a0a14');
        ctx.fillStyle = grad;
        ctx.fillText(text, x, y);
    }
    // 단지명 2줄로 표시 — 잘리지 않게 폰트 축소
    // L2 가 5글자 이상이면 더 줄여서 좌우 안 잘림
    const l2Font = krL2.length >= 5
        ? 'bold 100px "Noto Sans KR", "Inter", sans-serif'
        : 'bold 130px "Noto Sans KR", "Inter", sans-serif';
    bevelText(ctx1, krL1, 'bold 140px "Noto Sans KR", "Inter", sans-serif', 256, 180);
    bevelText(ctx1, krL2, l2Font, 256, 340);
    bevelText(ctx1, cplx.en, 'bold 50px "Inter", "Noto Sans KR", sans-serif', 256, 430);
    // 동번호 — 단지명보다 살짝 크지만 옆면 폭에 꽉 차지 않게 적당히
    bevelText(ctx1, dongStr + '동', 'bold 150px "Inter", "Noto Sans KR", sans-serif', 256, 880);

    const tex1 = new THREE.CanvasTexture(cv1);
    tex1.anisotropy = 8;
    const sideLabel = new THREE.Mesh(
        new THREE.PlaneGeometry(sideW, sideH),
        new THREE.MeshStandardMaterial({
            map: tex1, transparent: true, alphaTest: 0.05,
            roughness: 0.5, metalness: 0.4, side: THREE.DoubleSide
        })
    );
    // 좌측 옆면 (-X 방향) 외벽 — 창문 없는 면
    // PlaneGeometry 기본 normal=+Z. rotation y=-π/2 시 normal=-X (외부 바라봄) → 정상 글씨
    sideLabel.position.set(b.bx - b.bw / 2 - 0.10, b.bh * 0.50, b.bz);
    sideLabel.rotation.y = -Math.PI / 2;
    group.add(sideLabel);

    // 우측 옆면(+X) — rotation y=+π/2 시 normal=+X (외부 바라봄) → 정상 글씨
    const sideLabel2 = sideLabel.clone();
    sideLabel2.position.set(b.bx + b.bw / 2 + 0.10, b.bh * 0.50, b.bz);
    sideLabel2.rotation.y = Math.PI / 2;
    group.add(sideLabel2);
    // 정면 라벨은 제거 — 통창 샷시와 겹치지 않도록
}

// 공업지구 양각 기업명 글자 생성 (건물 정면 +Z 외벽)
function createEmbossedCompanyName(group, b) {
    const company = b.company;
    if (!company) return;

    // 글자 크기 — 폭은 건물 폭의 ~80%, 높이는 창문 사이 빈 띠(1.4m)에 들어가게
    const textW = Math.min(b.bw * 0.82, 9.5);
    const textH = 1.35; // 창문(높이 1.3m) 사이 빈 띠 약 1.5m 안에 안전하게 들어감

    // Canvas 텍스처 — 한글+영문 양각 느낌 (베벨 셰이딩)
    const cv = document.createElement('canvas');
    cv.width = 1024; cv.height = 256;
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, 1024, 256);

    // 한글 글자 — 메탈릭 회색, 위쪽 하이라이트 + 아래쪽 그림자로 양각감
    const krFont = 'bold 130px "Noto Sans KR", "Inter", sans-serif';
    const enFont = 'bold 48px "Inter", "Noto Sans KR", sans-serif';

    function drawEmbossed(text, font, x, y, scale) {
        ctx.font = font;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        // 1) 아래쪽 그림자 (양각 효과)
        ctx.fillStyle = 'rgba(0,0,0,0.55)';
        ctx.fillText(text, x + 3 * scale, y + 3 * scale);
        // 2) 위쪽 하이라이트
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.fillText(text, x - 1 * scale, y - 1 * scale);
        // 3) 메인 글자 — 메탈 그레이
        const grad = ctx.createLinearGradient(0, y - 50, 0, y + 50);
        grad.addColorStop(0, '#e8e8e8');
        grad.addColorStop(0.5, '#a8a8a8');
        grad.addColorStop(1, '#606060');
        ctx.fillStyle = grad;
        ctx.fillText(text, x, y);
        // 4) 미세한 흰색 윗 라인 (반사광)
        ctx.fillStyle = 'rgba(255,255,255,0.25)';
        ctx.fillText(text, x, y - 1.5 * scale);
    }

    drawEmbossed(company.kr, krFont, 512, 105, 1);
    drawEmbossed(company.en, enFont, 512, 200, 0.7);

    const tex = new THREE.CanvasTexture(cv);
    tex.anisotropy = 8;

    // 글자 평면 — 벽에서 살짝 떨어뜨려 그림자 받게 (양각 효과 강화)
    const plane = new THREE.Mesh(
        new THREE.PlaneGeometry(textW, textH),
        new THREE.MeshStandardMaterial({
            map: tex,
            transparent: true,
            alphaTest: 0.08,
            roughness: 0.45,
            metalness: 0.55,
            side: THREE.DoubleSide
        })
    );
    // y 위치 — 창문 사이 빈 띠 (3, 6, 9, 12…) 중 가능한 가장 높은 위치
    // 창문 중심: y=1.5, 4.5, 7.5… 창문 사이 = y=3, 6, 9…
    const stripStep = 3.0;
    const maxStripY = b.bh - 0.4 - textH / 2; // 옥상 아래로 여유
    let stripY = Math.floor((maxStripY) / stripStep) * stripStep;
    if (stripY < 3.0) stripY = 3.0;
    plane.position.set(b.bx, stripY, b.bz + b.bd / 2 + 0.18);
    plane.castShadow = true;
    group.add(plane);

    // 양각감 보강 — 같은 텍스처 더 어둡게 한 겹 뒤쪽에 배치 (그림자 레이어)
    const shadowPlane = new THREE.Mesh(
        new THREE.PlaneGeometry(textW, textH),
        new THREE.MeshBasicMaterial({
            map: tex,
            transparent: true,
            alphaTest: 0.08,
            color: 0x222222,
            opacity: 0.55
        })
    );
    shadowPlane.position.set(b.bx + 0.05, stripY - 0.05, b.bz + b.bd / 2 + 0.12);
    group.add(shadowPlane);
}

// 유리 스크린 도어 (자동문 스타일) — 모든 건물 입구 공용
// rotY: 0=+Z 정면, Math.PI=-Z 정면, Math.PI/2=-X 정면, -Math.PI/2=+X 정면
function createGlassScreenDoor(group, cx, cy, cz, doorW, doorH, rotY) {
    const glassMat = new THREE.MeshStandardMaterial({
        color: 0xaad4ee, transparent: true, opacity: 0.55,
        roughness: 0.12, metalness: 0.55,
        emissive: 0x224466, emissiveIntensity: 0.28,
        side: THREE.DoubleSide
    });
    const frameMat = new THREE.MeshStandardMaterial({
        color: 0x333333, roughness: 0.35, metalness: 0.75
    });
    const handleMat = new THREE.MeshStandardMaterial({
        color: 0xcccccc, roughness: 0.25, metalness: 0.85
    });

    const halfW = doorW / 2;
    const sin = Math.sin(rotY || 0);
    const cos = Math.cos(rotY || 0);
    // 패널은 두 짝 (양 옆으로 슬라이딩 갭 살짝) — 5cm 갭
    const panelW = halfW - 0.05;
    const panelCx = halfW / 2 + 0.025;

    // 우측 패널
    const panelR = new THREE.Mesh(
        new THREE.BoxGeometry(panelW, doorH * 0.92, 0.06), glassMat
    );
    panelR.position.set(cx + cos * panelCx, doorH * 0.46 + (cy || 0), cz - sin * panelCx);
    panelR.rotation.y = rotY || 0;
    group.add(panelR);

    // 좌측 패널
    const panelL = panelR.clone();
    panelL.position.set(cx - cos * panelCx, doorH * 0.46 + (cy || 0), cz + sin * panelCx);
    group.add(panelL);

    // 프레임 (상단 가로 바)
    const frameTop = new THREE.Mesh(
        new THREE.BoxGeometry(doorW + 0.15, 0.12, 0.10), frameMat
    );
    frameTop.position.set(cx, doorH * 0.92 + 0.06 + (cy || 0), cz);
    frameTop.rotation.y = rotY || 0;
    group.add(frameTop);

    // 프레임 (좌측 세로 바)
    const frameLeft = new THREE.Mesh(
        new THREE.BoxGeometry(0.10, doorH + 0.15, 0.10), frameMat
    );
    frameLeft.position.set(cx - cos * (halfW + 0.05), doorH * 0.5 + (cy || 0), cz + sin * (halfW + 0.05));
    frameLeft.rotation.y = rotY || 0;
    group.add(frameLeft);

    // 프레임 (우측 세로 바)
    const frameRight = frameLeft.clone();
    frameRight.position.set(cx + cos * (halfW + 0.05), doorH * 0.5 + (cy || 0), cz - sin * (halfW + 0.05));
    group.add(frameRight);

    // 손잡이 (양 패널 가운데, 세로 슬림 바)
    const handle = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, doorH * 0.45, 0.04), handleMat
    );
    handle.position.set(cx + cos * 0.06, doorH * 0.46 + (cy || 0), cz - sin * 0.06);
    handle.rotation.y = rotY || 0;
    group.add(handle);
}

function createBuilding(group, x, z, w, d, h, color, label, glass, windowStyle, skipDoor) {
    // Glass towers (tall commercial) get reflective material; others matte stucco
    const mat = glass
        ? new THREE.MeshStandardMaterial({ color, roughness: 0.18, metalness: 0.45 })
        : new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0.05 });
    const geo = new THREE.BoxGeometry(w, h, d);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, h / 2, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);

    // Concrete base
    const base = new THREE.Mesh(
        new THREE.BoxGeometry(w + 0.4, 0.5, d + 0.4),
        new THREE.MeshStandardMaterial({ color: 0x999999, roughness: 0.95 })
    );
    base.position.set(x, 0.25, z);
    base.receiveShadow = true;
    group.add(base);

    // Windows on all 4 sides
    const winMat = new THREE.MeshStandardMaterial({
        color: 0x88ccff,
        emissive: 0x334455,
        emissiveIntensity: 0.3,
        roughness: 0.3,
        metalness: 0.5
    });
    const floors = Math.max(1, Math.floor(h / 3));
    const winRowsW = Math.max(1, Math.floor(w / 2.5));
    const winRowsD = Math.max(1, Math.floor(d / 2.5));

    if (windowStyle === 'apartment') {
        // 평내동 아파트 스타일 — 앞/뒤만 큰 샷시(통창) 형태, 좌우는 무창 외벽
        const sashMat = new THREE.MeshStandardMaterial({
            color: 0xbcd6ee, emissive: 0x344c66, emissiveIntensity: 0.22,
            roughness: 0.18, metalness: 0.55
        });
        const mullionMat = new THREE.MeshStandardMaterial({
            color: 0xf0f0f0, roughness: 0.55, metalness: 0.35
        });
        const balconyMat = new THREE.MeshStandardMaterial({
            color: 0xd4c8b4, roughness: 0.78, metalness: 0.06
        });
        const sashH = 1.95;
        const sashW = w * 0.92;
        // 모바일 부담 줄이기: 멀리언 칸 수 축소 (각 칸 4m 폭)
        const unitCount = Math.max(2, Math.round(w / 4.0));
        for (let f = 0; f < floors; f++) {
            const sashY = 1.6 + f * 3;
            // 발코니 하단 (콘크리트 띠) — 층간 구분
            const balcony = new THREE.Mesh(
                new THREE.BoxGeometry(sashW + 0.4, 0.45, 0.18),
                balconyMat
            );
            balcony.position.set(x, sashY - sashH/2 - 0.15, z + d/2 + 0.10);
            group.add(balcony);
            const balconyB = balcony.clone();
            balconyB.position.set(x, sashY - sashH/2 - 0.15, z - d/2 - 0.10);
            group.add(balconyB);

            // 앞면 통창 (가로로 길게)
            const sashF = new THREE.Mesh(
                new THREE.BoxGeometry(sashW, sashH, 0.08),
                sashMat
            );
            sashF.position.set(x, sashY, z + d/2 + 0.05);
            group.add(sashF);
            // 뒷면 통창
            const sashB = new THREE.Mesh(
                new THREE.BoxGeometry(sashW, sashH, 0.08),
                sashMat
            );
            sashB.position.set(x, sashY, z - d/2 - 0.05);
            group.add(sashB);
            // 세로 멀리언 (집 사이 구분, 통창 위에 부착)
            for (let u = 0; u <= unitCount; u++) {
                const mx = x - sashW/2 + (sashW / unitCount) * u;
                const muF = new THREE.Mesh(
                    new THREE.BoxGeometry(0.12, sashH + 0.1, 0.10),
                    mullionMat
                );
                muF.position.set(mx, sashY, z + d/2 + 0.10);
                group.add(muF);
                const muB = muF.clone();
                muB.position.set(mx, sashY, z - d/2 - 0.10);
                group.add(muB);
            }
            // 가로 멀리언 (샷시 상/하단)
            const horBarTop = new THREE.Mesh(
                new THREE.BoxGeometry(sashW + 0.15, 0.10, 0.10),
                mullionMat
            );
            horBarTop.position.set(x, sashY + sashH/2, z + d/2 + 0.10);
            group.add(horBarTop);
            const horBarTopB = horBarTop.clone();
            horBarTopB.position.set(x, sashY + sashH/2, z - d/2 - 0.10);
            group.add(horBarTopB);
        }
        // 좌우 외벽 — 무창. 페인트 그라데이션 띠만 살짝 (포인트)
        const stripeMat = new THREE.MeshStandardMaterial({
            color: 0xc8b89a, roughness: 0.85
        });
        for (let s = 0; s < 2; s++) {
            const stripe = new THREE.Mesh(
                new THREE.BoxGeometry(0.05, h * 0.7, d * 0.4),
                stripeMat
            );
            stripe.position.set(x + (s === 0 ? -1 : 1) * (w/2 + 0.025), h * 0.5, z);
            group.add(stripe);
        }
    } else if (windowStyle === 'commercial') {
        // 분당/평촌 번화 스타일 — 앞뒤좌우 4면 모두 통창 샷시 연결
        const sashMat = new THREE.MeshStandardMaterial({
            color: 0xa8d0ee, emissive: 0x2c4860, emissiveIntensity: 0.32,
            roughness: 0.16, metalness: 0.6
        });
        const mullionMat = new THREE.MeshStandardMaterial({
            color: 0x2a2a2a, roughness: 0.5, metalness: 0.4
        });
        const sashH = 1.85;
        // 1F 는 유리문 (입구) — 2F+ 는 통창
        // 유리 1F
        const door1FMat = new THREE.MeshStandardMaterial({
            color: 0x84b5d8, emissive: 0x2c4860, emissiveIntensity: 0.45,
            roughness: 0.18, metalness: 0.55, transparent: true, opacity: 0.85
        });
        const doorFrameMat = new THREE.MeshStandardMaterial({
            color: 0x1a1a1a, roughness: 0.4, metalness: 0.6
        });
        const doorCount = Math.max(3, Math.round(w / 1.8));
        const doorW = w / doorCount;
        for (let dx = 0; dx < doorCount; dx++) {
            const dCenterX = x - w / 2 + doorW * (dx + 0.5);
            // 앞면 유리문
            const glassF = new THREE.Mesh(
                new THREE.BoxGeometry(doorW * 0.88, 2.4, 0.08), door1FMat
            );
            glassF.position.set(dCenterX, 1.35, z + d / 2 + 0.05);
            group.add(glassF);
            // 문 프레임 (양옆 세로)
            const frameLF = new THREE.Mesh(
                new THREE.BoxGeometry(0.08, 2.5, 0.10), doorFrameMat
            );
            frameLF.position.set(dCenterX - doorW * 0.44, 1.4, z + d / 2 + 0.07);
            group.add(frameLF);
            // 뒷면 유리문 (서비스 입구)
            const glassB = glassF.clone();
            glassB.position.set(dCenterX, 1.35, z - d / 2 - 0.05);
            group.add(glassB);
        }
        // 1F 좌우는 통창
        const sashWX = d * 0.9;  // 측면 통창 길이 (depth 방향)
        const sash1L = new THREE.Mesh(
            new THREE.BoxGeometry(0.08, sashH, sashWX), sashMat
        );
        sash1L.position.set(x - w / 2 - 0.05, 1.5, z);
        group.add(sash1L);
        const sash1R = sash1L.clone();
        sash1R.position.set(x + w / 2 + 0.05, 1.5, z);
        group.add(sash1R);

        // 2F+ — 앞뒤좌우 4면 통창
        for (let f = 1; f < floors; f++) {
            const sashY = 1.5 + f * 3;
            // 앞면
            const sashF = new THREE.Mesh(
                new THREE.BoxGeometry(w * 0.93, sashH, 0.08), sashMat
            );
            sashF.position.set(x, sashY, z + d / 2 + 0.05);
            group.add(sashF);
            // 뒷면
            const sashB = sashF.clone();
            sashB.position.set(x, sashY, z - d / 2 - 0.05);
            group.add(sashB);
            // 좌측 통창
            const sashL = new THREE.Mesh(
                new THREE.BoxGeometry(0.08, sashH, d * 0.93), sashMat
            );
            sashL.position.set(x - w / 2 - 0.05, sashY, z);
            group.add(sashL);
            // 우측 통창
            const sashR = sashL.clone();
            sashR.position.set(x + w / 2 + 0.05, sashY, z);
            group.add(sashR);

            // 세로 멀리언 (앞뒤)
            const unitX = Math.max(2, Math.round(w / 3.5));
            for (let u = 1; u < unitX; u++) {
                const mx = x - w / 2 + (w / unitX) * u;
                const muF = new THREE.Mesh(
                    new THREE.BoxGeometry(0.10, sashH + 0.1, 0.10), mullionMat
                );
                muF.position.set(mx, sashY, z + d / 2 + 0.10);
                group.add(muF);
                const muB = muF.clone();
                muB.position.set(mx, sashY, z - d / 2 - 0.10);
                group.add(muB);
            }
            // 좌우 멀리언
            const unitZ = Math.max(2, Math.round(d / 3.5));
            for (let u = 1; u < unitZ; u++) {
                const mz = z - d / 2 + (d / unitZ) * u;
                const muL = new THREE.Mesh(
                    new THREE.BoxGeometry(0.10, sashH + 0.1, 0.10), mullionMat
                );
                muL.position.set(x - w / 2 - 0.10, sashY, mz);
                group.add(muL);
                const muR = muL.clone();
                muR.position.set(x + w / 2 + 0.10, sashY, mz);
                group.add(muR);
            }
            // 가로 멀리언 (각 층 상단)
            const horBar = new THREE.Mesh(
                new THREE.BoxGeometry(w + 0.2, 0.10, 0.10), mullionMat
            );
            horBar.position.set(x, sashY + sashH / 2, z + d / 2 + 0.10);
            group.add(horBar);
            const horBarB = horBar.clone();
            horBarB.position.set(x, sashY + sashH / 2, z - d / 2 - 0.10);
            group.add(horBarB);
        }
    } else {
        // 일반 빌딩 (공업/경찰서) — 4면 균등한 사각 창문
        for (let f = 0; f < floors; f++) {
            for (let wi = 0; wi < winRowsW; wi++) {
                const winF = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.3, 0.08), winMat);
                winF.position.set(x - w / 2 + (w / winRowsW) * (wi + 0.5), 1.5 + f * 3, z + d / 2 + 0.05);
                group.add(winF);
                const winB = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.3, 0.08), winMat);
                winB.position.set(x - w / 2 + (w / winRowsW) * (wi + 0.5), 1.5 + f * 3, z - d / 2 - 0.05);
                group.add(winB);
            }
            for (let di = 0; di < winRowsD; di++) {
                const winR = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.3, 0.9), winMat);
                winR.position.set(x + w / 2 + 0.05, 1.5 + f * 3, z - d / 2 + (d / winRowsD) * (di + 0.5));
                group.add(winR);
                const winL = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.3, 0.9), winMat);
                winL.position.set(x - w / 2 - 0.05, 1.5 + f * 3, z - d / 2 + (d / winRowsD) * (di + 0.5));
                group.add(winL);
            }
        }
    }

    // 유리 스크린 도어 (자동문 슬라이딩 글래스 패널 — 모든 일반 건물 공용)
    if (!skipDoor) {
        createGlassScreenDoor(group, x, 0, z + d / 2 + 0.05, 2.0, 2.6, 0);
    }

    // Roof ledge
    const ledge = new THREE.Mesh(
        new THREE.BoxGeometry(w + 0.6, 0.25, d + 0.6),
        new THREE.MeshStandardMaterial({ color: 0x555555, roughness: 0.8 })
    );
    ledge.position.set(x, h + 0.12, z);
    group.add(ledge);

    mesh.userData = { label, x, z, w, d, h };
    return mesh;
}

// Place buildings within blocks, facing nearest road
function createGridBuildings(group) {
    const buildings = [];
    // Randomized hideout features each game session
    // Pick random color + marker for each criminal
    function pickRandom(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
    const resColorPool = [0x4488cc, 0x88cc44, 0xcc6644, 0xaa44cc, 0x44ccaa, 0xcccc44];
    const resMarkerPool = ['mailbox', 'gnome', 'birdhouse', 'flowerpot'];
    const resHeightPool = [6, 9, 12];

    const comColorPool = [0xf0f0e8, 0xddccaa, 0xccaadd, 0xaaccdd, 0xeecccc];
    const comMarkerPool = ['cafe', 'neon', 'shop', 'clinic'];
    const comHeightPool = [12, 15, 18, 21];

    const facColorPool = [0x888888, 0x777733, 0x664433, 0x553355, 0x336666];
    const facMarkerPool = ['tank', 'antenna', 'silo', 'crane'];
    const facHeightPool = [12, 18, 24];

    const hideoutTargets = {
        RESIDENTIAL: { color: pickRandom(resColorPool), h: pickRandom(resHeightPool), marker: pickRandom(resMarkerPool), criminal: 0 },
        COMMERCIAL:  { color: pickRandom(comColorPool), h: pickRandom(comHeightPool), marker: pickRandom(comMarkerPool), criminal: 1 },
        FACTORY:     { color: pickRandom(facColorPool), h: pickRandom(facHeightPool), marker: pickRandom(facMarkerPool), criminal: 2 }
    };
    window._hideoutFeatures = hideoutTargets;  // share with hint system
    const hideoutPlaced = { RESIDENTIAL: false, COMMERCIAL: false, FACTORY: false };

    // Color palettes per zone — 평내동 아파트 외벽: 베이지/크림/연한 다홍
    const palette = {
        POLICE: [0x889977, 0xa8a896, 0x8b9aa8, 0x99a8b8],
        RESIDENTIAL: [0xe8dcc4, 0xddc9a8, 0xe0d2b8, 0xd4bf9d, 0xeed8b8, 0xd8c4a0, 0xe6d4bc],
        COMMERCIAL: [0x6680a0, 0x5a7090, 0x708090, 0x90a0b0, 0x556677, 0x8090a0, 0x9eb4cc],
        FACTORY: [0x6a6a6a, 0x5a5a5a, 0x7a7a7a, 0x4a4a4a, 0x808080]
    };

    // Track all block hideout candidates first, then randomly choose
    const candidateBuildings = [];

    BUILDING_BLOCKS.forEach((block, blockIdx) => {
        const { zone, minX, maxX, minZ, maxZ, density } = block;
        const blockW = maxX - minX;
        const blockD = maxZ - minZ;
        if (blockW <= 0 || blockD <= 0) return;

        // Determine building size by zone
        let bw, bd, bhMin, bhMax, spacing;
        if (zone === 'POLICE') {
            bw = 7; bd = 7; bhMin = 6; bhMax = 12; spacing = 10;
        } else if (zone === 'RESIDENTIAL') {
            // 고층 아파트 슬랩형 (평내동 스타일)
            bw = 11; bd = 8; bhMin = 32; bhMax = 42; spacing = 17;
        } else if (zone === 'COMMERCIAL') {
            if (block.rodeo) {
                // 로데오 거리 양쪽 — 조금 더 큰 상가건물
                bw = 14; bd = 10; bhMin = 14; bhMax = 22; spacing = 16;
            } else {
                bw = 8; bd = 7; bhMin = 12; bhMax = 24; spacing = 11;
            }
        } else if (zone === 'FACTORY') {
            bw = 12; bd = 11; bhMin = 8; bhMax = 14; spacing = 15;
        }

        const cols = Math.max(1, Math.floor(blockW / spacing));
        const rows = Math.max(1, Math.floor(blockD / spacing));
        const stepX = blockW / cols;
        const stepZ = blockD / rows;

        // 아파트 동번호 순환 (블록당)
        let dongCursor = 0;

        for (let row = 0; row < rows; row++) {
            for (let col = 0; col < cols; col++) {
                const bx = minX + stepX * (col + 0.5);
                const bz = minZ + stepZ * (row + 0.5);
                const bh = bhMin + Math.random() * (bhMax - bhMin);

                // Sparse density: skip some
                if (density === 'sparse' && Math.random() < 0.3) continue;
                if (density === 'medium' && Math.random() < 0.15) continue;

                const bcolor = palette[zone][Math.floor(Math.random() * palette[zone].length)];
                const candidate = {
                    bx, bz,
                    bw: (zone === 'RESIDENTIAL' || block.rodeo) ? bw : bw + (Math.random() - 0.5) * 1.5,
                    bd: (zone === 'RESIDENTIAL' || block.rodeo) ? bd : bd + (Math.random() - 0.5) * 1.5,
                    bh, bcolor, zone, blockIdx
                };
                if (zone === 'RESIDENTIAL' && typeof block.complexIdx === 'number') {
                    const cplx = APARTMENT_COMPLEXES[block.complexIdx];
                    if (cplx) {
                        candidate.complex = cplx;
                        candidate.dong = cplx.dong[dongCursor % cplx.dong.length];
                        dongCursor++;
                    }
                }
                // 간판 부착 면 — 블록의 facing 속성을 그대로 상속 (signs.js 가 읽음)
                if (zone === 'COMMERCIAL') {
                    candidate.signFacing = block.facing || '+Z';
                    candidate.rodeo = !!block.rodeo;
                }
                candidateBuildings.push(candidate);
            }
        }
    });

    // Randomly pick 1 hideout per zone
    ['RESIDENTIAL', 'COMMERCIAL', 'FACTORY'].forEach(zone => {
        const cands = candidateBuildings.filter(c => c.zone === zone);
        if (cands.length === 0) return;
        const chosen = cands[Math.floor(Math.random() * cands.length)];
        chosen.isHideout = true;
        const ht = hideoutTargets[zone];
        if (zone !== 'RESIDENTIAL') {
            // 주거지 외에는 기존 hideout 외관(색/높이) 유지
            chosen.bcolor = ht.color;
            chosen.bh = ht.h;
            chosen.bw = Math.max(chosen.bw, 8);
            chosen.bd = Math.max(chosen.bd, 7);
        }
        chosen.criminal = ht.criminal;
        chosen.marker = ht.marker;
        // 주거 hideout: 단지명+동번호를 hideoutFeatures 에 노출
        if (zone === 'RESIDENTIAL' && chosen.complex && chosen.dong) {
            hideoutTargets.RESIDENTIAL.complexKr = chosen.complex.kr;
            hideoutTargets.RESIDENTIAL.complexEn = chosen.complex.en;
            hideoutTargets.RESIDENTIAL.dong = chosen.dong;
        }
    });

    // 공업지구 건물마다 기업명 할당 — 셔플 후 순환 (중복 최소화)
    const factoryShuffled = FACTORY_COMPANIES.slice().sort(() => Math.random() - 0.5);
    let facCursor = 0;
    candidateBuildings.forEach(b => {
        if (b.zone !== 'FACTORY') return;
        b.company = factoryShuffled[facCursor % factoryShuffled.length];
        facCursor++;
        // 공업지구 은거지의 기업명을 hideoutFeatures 에 노출 (힌트 시스템용)
        if (b.isHideout && b.criminal === 2) {
            hideoutTargets.FACTORY.company = b.company;
        }
    });

    // Create the buildings
    candidateBuildings.forEach(b => {
        const label = b.isHideout ? `${b.zone} 은거지` : `${b.zone}`;
        const isGlass = (b.zone === 'COMMERCIAL' && b.bh >= 15);
        const winStyle = (b.zone === 'RESIDENTIAL') ? 'apartment' : 'normal';
        // 상가는 통창 + 1F 유리문 스타일 적용
        const finalStyle = (b.zone === 'COMMERCIAL') ? 'commercial' : winStyle;
        const mesh = createBuilding(group, b.bx, b.bz, b.bw, b.bd, b.bh, b.bcolor, label, isGlass, finalStyle);
        buildings.push({
            mesh, x: b.bx, z: b.bz, w: b.bw, d: b.bd, h: b.bh,
            type: b.isHideout ? 'hideout' : 'normal',
            zone: b.zone,
            hideoutIndex: b.isHideout ? b.criminal : -1,
            signFacing: b.signFacing || '+Z',
            rodeo: !!b.rodeo
        });

        // Add zone-specific decorations
        if (b.zone === 'RESIDENTIAL') {
            // 옥상 물탱크 + 안테나 (평내동 아파트 옥상 디테일)
            const tank = new THREE.Mesh(
                new THREE.CylinderGeometry(1.2, 1.2, 1.4, 16),
                new THREE.MeshStandardMaterial({ color: 0xaaaaaa, roughness: 0.6, metalness: 0.4 })
            );
            tank.position.set(b.bx - b.bw / 4, b.bh + 0.7, b.bz);
            tank.castShadow = true;
            group.add(tank);

            // 옥상 난간 (회색 띠)
            const railing = new THREE.Mesh(
                new THREE.BoxGeometry(b.bw + 0.4, 0.4, b.bd + 0.4),
                new THREE.MeshStandardMaterial({ color: 0xbbbbbb, roughness: 0.7 })
            );
            railing.position.set(b.bx, b.bh + 0.2, b.bz);
            group.add(railing);

            // 옥상 안테나
            const ant = new THREE.Mesh(
                new THREE.CylinderGeometry(0.05, 0.05, 3, 6),
                new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.6 })
            );
            ant.position.set(b.bx + b.bw / 4, b.bh + 1.5, b.bz);
            group.add(ant);

            // 아파트 단지명 + 동번호 양각 라벨 (좌우 측면)
            if (b.complex && b.dong) {
                try { createApartmentLabel(group, b); }
                catch (e) { console.warn('apartment label failed', e); }
            }
        }
        if (b.zone === 'COMMERCIAL') {
            // AC unit
            if (Math.random() > 0.4) {
                const ac = new THREE.Mesh(
                    new THREE.BoxGeometry(1.2, 0.6, 0.8),
                    new THREE.MeshStandardMaterial({ color: 0xcccccc, roughness: 0.5 })
                );
                ac.position.set(b.bx + (Math.random() - 0.5) * (b.bw - 2), b.bh + 0.6, b.bz + (Math.random() - 0.5) * (b.bd - 2));
                ac.castShadow = true;
                group.add(ac);
            }
            // 옛 절차적 간판(핑크 BAR/CAFE/SHOP/CLINIC + 랜덤 박스)은 제거.
            // 상업지구 간판은 js/signs.js (loadSigns) 에서 일괄 부착.
        }
        if (b.zone === 'FACTORY') {
            // 양각 기업명 글자 — 건물 정면(+Z) 외벽에 부착
            if (b.company) {
                try { createEmbossedCompanyName(group, b); }
                catch (e) { console.warn('embossed company failed', e); }
            }
            // Chimney
            if (Math.random() > 0.3) {
                const chimney = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.5, 0.7, 4, 12),
                    new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.95 })
                );
                chimney.position.set(b.bx - b.bw / 4, b.bh + 2, b.bz);
                chimney.castShadow = true;
                group.add(chimney);
                const smoke = new THREE.Mesh(
                    new THREE.SphereGeometry(1, 12, 12),
                    new THREE.MeshStandardMaterial({ color: 0xaaaaaa, transparent: true, opacity: 0.35 })
                );
                smoke.position.set(b.bx - b.bw / 4, b.bh + 5, b.bz);
                group.add(smoke);
            }
            if (b.marker === 'tank') {
                const tank = new THREE.Mesh(
                    new THREE.CylinderGeometry(1.7, 1.7, 3.5, 20),
                    new THREE.MeshStandardMaterial({ color: 0xcc1a1a, roughness: 0.6, metalness: 0.2 })
                );
                tank.position.set(b.bx + 2, b.bh + 1.75, b.bz - 1);
                tank.castShadow = true;
                group.add(tank);
            } else if (b.marker === 'antenna') {
                const antPole = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.08, 0.08, 5, 8),
                    new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.7, roughness: 0.3 })
                );
                antPole.position.set(b.bx + 1.5, b.bh + 2.5, b.bz - 1);
                antPole.castShadow = true;
                group.add(antPole);
                // Cross bars
                for (let i = 0; i < 3; i++) {
                    const bar = new THREE.Mesh(
                        new THREE.BoxGeometry(0.8 - i * 0.2, 0.05, 0.05),
                        new THREE.MeshStandardMaterial({ color: 0xcccccc })
                    );
                    bar.position.set(b.bx + 1.5, b.bh + 3 + i * 0.7, b.bz - 1);
                    group.add(bar);
                }
                // Red blinking light
                const aLight = new THREE.Mesh(
                    new THREE.SphereGeometry(0.15, 12, 12),
                    new THREE.MeshStandardMaterial({ color: 0xff0000, emissive: 0xff0000, emissiveIntensity: 0.9 })
                );
                aLight.position.set(b.bx + 1.5, b.bh + 5.2, b.bz - 1);
                group.add(aLight);
            } else if (b.marker === 'silo') {
                const silo = new THREE.Mesh(
                    new THREE.CylinderGeometry(1.4, 1.4, 5, 20),
                    new THREE.MeshStandardMaterial({ color: 0xaaaaaa, roughness: 0.7, metalness: 0.3 })
                );
                silo.position.set(b.bx + 2, b.bh + 2.5, b.bz - 1);
                silo.castShadow = true;
                group.add(silo);
                const dome = new THREE.Mesh(
                    new THREE.SphereGeometry(1.4, 16, 12, 0, Math.PI * 2, 0, Math.PI / 2),
                    new THREE.MeshStandardMaterial({ color: 0x999999, metalness: 0.5 })
                );
                dome.position.set(b.bx + 2, b.bh + 5, b.bz - 1);
                group.add(dome);
            } else if (b.marker === 'crane') {
                const cBase = new THREE.Mesh(
                    new THREE.BoxGeometry(0.3, 4, 0.3),
                    new THREE.MeshStandardMaterial({ color: 0xffaa00, roughness: 0.5 })
                );
                cBase.position.set(b.bx + 2, b.bh + 2, b.bz - 1);
                cBase.castShadow = true;
                group.add(cBase);
                const arm = new THREE.Mesh(
                    new THREE.BoxGeometry(6, 0.3, 0.3),
                    new THREE.MeshStandardMaterial({ color: 0xffaa00, roughness: 0.5 })
                );
                arm.position.set(b.bx + 4, b.bh + 4, b.bz - 1);
                arm.castShadow = true;
                group.add(arm);
                const hook = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.02, 0.02, 1.5, 6),
                    new THREE.MeshStandardMaterial({ color: 0x222222 })
                );
                hook.position.set(b.bx + 6, b.bh + 3.25, b.bz - 1);
                group.add(hook);
            }
        }
    });

    window._buildingPositions = buildings.map(b => ({
        x: b.x, z: b.z, w: b.w, d: b.d,
        hideoutIndex: typeof b.hideoutIndex === 'number' ? b.hideoutIndex : -1
    }));
    return buildings;
}

function createStreetLight(group, x, z) {
    const poleMat = new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.7, metalness: 0.5 });
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.12, 5, 8), poleMat);
    pole.position.set(x, 2.5, z);
    pole.castShadow = true;
    group.add(pole);

    // Lamp directly on top of pole — no overhang arm (avoids extending over road)
    const lampMat = new THREE.MeshStandardMaterial({ color: 0xffdd88, emissive: 0x332200, emissiveIntensity: 0, roughness: 0.5 });
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.28, 12, 12), lampMat);
    lamp.position.set(x, 5.15, z);
    lamp.userData.isStreetLight = true;
    group.add(lamp);

    // Small cap on top of lamp
    const cap = new THREE.Mesh(new THREE.ConeGeometry(0.3, 0.18, 8), poleMat);
    cap.position.set(x, 5.4, z);
    group.add(cap);

    return lamp;
}

function createStreetProps(group) {
    const streetLights = [];

    function lightOnRoad(x, z) {
        for (const rr of MAIN_ROADS) {
            if (rr.type === 'H') {
                const ox = rr.offsetX || 0;
                if (Math.abs(z - rr.z) < rr.w / 2 + 1 && x >= ox - rr.length/2 - 1 && x <= ox + rr.length/2 + 1) return true;
            }
            if (rr.type === 'V') {
                const oz = rr.offsetZ || 0;
                if (Math.abs(x - rr.x) < rr.w / 2 + 1 && z >= oz - rr.length/2 - 1 && z <= oz + rr.length/2 + 1) return true;
            }
        }
        return false;
    }

    // Place streetlights along main roads — skip if on another road
    MAIN_ROADS.forEach(r => {
        if (r.type === 'H') {
            const ox = r.offsetX || 0;
            for (let x = ox - r.length/2 + 10; x < ox + r.length/2; x += 18) {
                const z1 = r.z + r.w/2 + 2.5, z2 = r.z - r.w/2 - 2.5;
                if (!lightOnRoad(x, z1)) streetLights.push(createStreetLight(group, x, z1));
                if (!lightOnRoad(x, z2)) streetLights.push(createStreetLight(group, x, z2));
            }
        } else {
            for (let z = -r.length/2 + 10; z < r.length/2; z += 18) {
                const x1 = r.x + r.w/2 + 2.5;
                if (!lightOnRoad(x1, z)) streetLights.push(createStreetLight(group, x1, z));
            }
        }
    });

    window._streetLights = streetLights;

    // Benches removed from road areas — placed only in central plaza (createParks)

    // Trees on sidewalk strips (parallel to roads, just outside road edge)
    const treeMat = new THREE.MeshStandardMaterial({ color: 0x2d6a1e, roughness: 0.85 });
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5c3a1e, roughness: 0.9 });
    const treesPlaced = [];

    function nearBuilding(x, z) {
        if (typeof window !== 'undefined' && window._buildingPositions) {
            for (const b of window._buildingPositions) {
                if (Math.abs(x - b.x) < b.w / 2 + 1.5 && Math.abs(z - b.z) < b.d / 2 + 1.5) return true;
            }
        }
        return false;
    }
    function tooClose(x, z) {
        for (const t of treesPlaced) {
            if (Math.abs(x - t.x) < 4 && Math.abs(z - t.z) < 4) return true;
        }
        return false;
    }

    // Check if position overlaps any road (including the road's full width + buffer)
    function onAnyRoad(x, z) {
        for (const rr of MAIN_ROADS) {
            if (rr.type === 'H') {
                const ox = rr.offsetX || 0;
                if (Math.abs(z - rr.z) < rr.w / 2 + 2.5 && x >= ox - rr.length/2 - 2 && x <= ox + rr.length/2 + 2) return true;
            }
            if (rr.type === 'V') {
                const oz = rr.offsetZ || 0;
                if (Math.abs(x - rr.x) < rr.w / 2 + 2.5 && z >= oz - rr.length/2 - 2 && z <= oz + rr.length/2 + 2) return true;
            }
        }
        return false;
    }

    // Place trees along horizontal road edges only (off any road, off buildings)
    MAIN_ROADS.forEach(r => {
        if (r.type !== 'H') return;
        const ox = r.offsetX || 0;
        for (let x = ox - r.length / 2 + 14; x < ox + r.length / 2 - 6; x += 14) {
            [r.z + r.w / 2 + 4.5, r.z - r.w / 2 - 4.5].forEach(z => {
                if (onAnyRoad(x, z)) return;
                if (nearBuilding(x, z)) return;
                if (tooClose(x, z)) return;
                // Tapered trunk
                const tH = 2.2 + Math.random() * 0.6;
                const trunk = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.12, 0.22, tH, 8),
                    trunkMat
                );
                trunk.position.set(x, tH / 2, z);
                trunk.castShadow = true;
                group.add(trunk);
                // Multi-layered foliage (3 spheres of different sizes/colors)
                const greens = [0x2d6a1e, 0x3a7a2e, 0x4a8a3e, 0x356622];
                const baseColor = greens[Math.floor(Math.random() * greens.length)];
                const baseMat = new THREE.MeshStandardMaterial({ color: baseColor, roughness: 0.9 });

                // Bottom (widest)
                const c1 = new THREE.Mesh(new THREE.SphereGeometry(1.4 + Math.random() * 0.2, 12, 12), baseMat);
                c1.position.set(x, tH + 0.5, z);
                c1.castShadow = true;
                group.add(c1);
                // Middle
                const c2 = new THREE.Mesh(new THREE.SphereGeometry(1.1 + Math.random() * 0.15, 12, 12), baseMat);
                c2.position.set(x + (Math.random()-0.5) * 0.3, tH + 1.4, z + (Math.random()-0.5) * 0.3);
                c2.castShadow = true;
                group.add(c2);
                // Top (smallest, lighter green)
                const lighterMat = new THREE.MeshStandardMaterial({
                    color: new THREE.Color(baseColor).offsetHSL(0, 0, 0.1).getHex(),
                    roughness: 0.85
                });
                const c3 = new THREE.Mesh(new THREE.SphereGeometry(0.7 + Math.random() * 0.15, 12, 12), lighterMat);
                c3.position.set(x + (Math.random()-0.5) * 0.4, tH + 2.1, z + (Math.random()-0.5) * 0.4);
                c3.castShadow = true;
                group.add(c3);
                treesPlaced.push({ x, z });
            });
        }
    });
}

function createParks(group) {
    // legacy: noop. createCityParks 가 분당신도시 스타일 공원을 배치.
}

// 분당신도시 / 일산 호수공원 스타일 — 도시 빈 공터에 공원 조성
function createCityParks(group) {
    const grassTex = makeProceduralTexture('#4a8c3a', 50, 256);
    grassTex.repeat.set(6, 6);
    const parkMat = new THREE.MeshStandardMaterial({
        color: 0xffffff, map: grassTex, roughness: 0.95
    });
    const pathTex = makeProceduralTexture('#d2c0a8', 25, 128);
    pathTex.repeat.set(4, 4);
    const pathMat = new THREE.MeshStandardMaterial({
        color: 0xffffff, map: pathTex, roughness: 0.85
    });
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5c3a1e, roughness: 0.9 });

    // 공원 후보 — 도로/건물 안 겹치게 안전 위치 (PRINCIPLES.md #1 준수)
    // 1) 경찰서 동측 광장 (V x=0 ↔ V x=50 사이, H z=55 ↔ z=85 사이)
    // 2) 경찰서 서측 광장 (V x=-50 ↔ V x=0 사이)
    // 3) 주거 ↔ 상업 사이 좁은 녹지 (x=-5 ↔ x=5)
    const parks = [
        { cx:  27, cz: 70, w: 35, d: 14, hasFountain: true,  treeCount: 12 },
        { cx: -27, cz: 70, w: 35, d: 14, hasFountain: false, treeCount: 10 }
    ];

    parks.forEach(p => {
        // 잔디 베이스
        const grass = new THREE.Mesh(
            new THREE.BoxGeometry(p.w, 0.06, p.d), parkMat
        );
        grass.position.set(p.cx, 0.045, p.cz);
        grass.receiveShadow = true;
        group.add(grass);

        // 산책로 (X 자형)
        const path1 = new THREE.Mesh(
            new THREE.BoxGeometry(p.w * 0.85, 0.05, 1.5), pathMat
        );
        path1.position.set(p.cx, 0.10, p.cz);
        path1.receiveShadow = true;
        group.add(path1);
        const path2 = new THREE.Mesh(
            new THREE.BoxGeometry(1.5, 0.05, p.d * 0.85), pathMat
        );
        path2.position.set(p.cx, 0.10, p.cz);
        path2.receiveShadow = true;
        group.add(path2);

        // 중앙 분수 / 화단
        if (p.hasFountain) {
            const basin = new THREE.Mesh(
                new THREE.CylinderGeometry(2.0, 2.2, 0.5, 24),
                new THREE.MeshStandardMaterial({ color: 0xc8b89a, roughness: 0.65 })
            );
            basin.position.set(p.cx, 0.30, p.cz);
            basin.castShadow = true;
            group.add(basin);
            const water = new THREE.Mesh(
                new THREE.CylinderGeometry(1.7, 1.7, 0.06, 24),
                new THREE.MeshStandardMaterial({
                    color: 0x4a8cdc, roughness: 0.2, metalness: 0.55,
                    emissive: 0x1a3a64, emissiveIntensity: 0.2
                })
            );
            water.position.set(p.cx, 0.55, p.cz);
            group.add(water);
            const spout = new THREE.Mesh(
                new THREE.CylinderGeometry(0.10, 0.15, 1.4, 12),
                new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.6, roughness: 0.4 })
            );
            spout.position.set(p.cx, 1.0, p.cz);
            group.add(spout);
        } else {
            // 화단
            const flowerbed = new THREE.Mesh(
                new THREE.CylinderGeometry(2.2, 2.4, 0.35, 16),
                new THREE.MeshStandardMaterial({ color: 0x6c543a, roughness: 0.85 })
            );
            flowerbed.position.set(p.cx, 0.22, p.cz);
            flowerbed.receiveShadow = true;
            group.add(flowerbed);
            const flowers = new THREE.Mesh(
                new THREE.CylinderGeometry(2.05, 2.05, 0.05, 16),
                new THREE.MeshStandardMaterial({ color: 0xee7080, roughness: 0.7 })
            );
            flowers.position.set(p.cx, 0.42, p.cz);
            group.add(flowers);
        }

        // 가로수 (공원 둘레)
        const greens = [0x2d6a1e, 0x3a7a2e, 0x4a8a3e, 0x356622];
        for (let t = 0; t < p.treeCount; t++) {
            const angle = (t / p.treeCount) * Math.PI * 2;
            const rx = (p.w / 2 - 1.5) * Math.cos(angle);
            const rz = (p.d / 2 - 1.5) * Math.sin(angle);
            const tx = p.cx + rx, tz = p.cz + rz;
            // 십자 산책로 영역 회피
            if (Math.abs(rx) < 1.2 && Math.abs(rz) < 1.2) continue;

            const tH = 2.0 + Math.random() * 0.8;
            const trunk = new THREE.Mesh(
                new THREE.CylinderGeometry(0.12, 0.20, tH, 8), trunkMat
            );
            trunk.position.set(tx, tH / 2 + 0.06, tz);
            trunk.castShadow = true;
            group.add(trunk);
            const folColor = greens[Math.floor(Math.random() * greens.length)];
            const fol = new THREE.Mesh(
                new THREE.SphereGeometry(1.0 + Math.random() * 0.3, 10, 8),
                new THREE.MeshStandardMaterial({ color: folColor, roughness: 0.85 })
            );
            fol.position.set(tx, tH + 0.5, tz);
            fol.castShadow = true;
            group.add(fol);
        }

        // 벤치 4개 (산책로 십자 끝)
        const benchMat = new THREE.MeshStandardMaterial({ color: 0x6b3f2a, roughness: 0.7 });
        const benchPos = [
            { x: p.cx, z: p.cz + p.d * 0.35, rot: 0 },
            { x: p.cx, z: p.cz - p.d * 0.35, rot: 0 },
            { x: p.cx + p.w * 0.35, z: p.cz, rot: Math.PI / 2 },
            { x: p.cx - p.w * 0.35, z: p.cz, rot: Math.PI / 2 }
        ];
        benchPos.forEach(bp => {
            const seat = new THREE.Mesh(
                new THREE.BoxGeometry(1.6, 0.10, 0.45), benchMat
            );
            seat.position.set(bp.x, 0.45, bp.z);
            seat.rotation.y = bp.rot;
            seat.castShadow = true;
            group.add(seat);
            const back = new THREE.Mesh(
                new THREE.BoxGeometry(1.6, 0.5, 0.08), benchMat
            );
            back.position.set(bp.x, 0.75, bp.z);
            back.rotation.y = bp.rot;
            group.add(back);
        });

        // 공원 collision 영역 — 공원 자체는 통과 가능, 분수/화단만 차단
        if (window._buildingPositions) {
            // 분수/화단 차단
            window._buildingPositions.push({
                x: p.cx, z: p.cz, w: 4.5, d: 4.5, hideoutIndex: -1
            });
        }
    });
}
