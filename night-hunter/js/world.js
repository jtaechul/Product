// world.js — 한국 신도시 풍 도로 우선 도시 설계
// 분당/일산 격자형 도시 모델: 메인 간선도로 + 보조도로 + 골목, 도로에 면하는 건물 배치

const WORLD_SIZE = 300;

// Zone definitions
const ZONES = {
    POLICE:      { name: '경찰서 구역', cx: 0, cz: 100 },
    RESIDENTIAL: { name: '주택가',     cx: -80, cz: 0 },
    COMMERCIAL:  { name: '상업지구',   cx: 80, cz: 0 },
    FACTORY:     { name: '공장지대',   cx: 0, cz: -100 }
};

// Korean city road network - inspired by Bundang/Ilsan grid
// Main arterial roads (큰 도로, 8 wide)
const MAIN_ROADS = [
    // East-West arterials
    { type: 'H', z: 95, w: 8, length: 280 },   // Police district main
    { type: 'H', z: 50, w: 10, length: 280 },  // Central arterial (main)
    { type: 'H', z: 5, w: 8, length: 280 },    // Residential/Commercial divider
    { type: 'H', z: -45, w: 8, length: 280 },  // Lower arterial
    { type: 'H', z: -85, w: 10, length: 280 }, // Factory border main
    { type: 'H', z: -135, w: 6, length: 240 }, // Factory back

    // North-South arterials (x=0 stops short to leave police plaza clean)
    { type: 'V', x: 0, w: 10, length: 230, offsetZ: -25 },   // Central — z range -140 to 90 (stops before police)
    { type: 'V', x: -50, w: 8, length: 200 },  // West main
    { type: 'V', x: 50, w: 8, length: 200 },   // East main
    { type: 'V', x: -100, w: 6, length: 180 }, // Far west
    { type: 'V', x: 100, w: 6, length: 180 },  // Far east
    { type: 'V', x: -130, w: 5, length: 150 },
    { type: 'V', x: 130, w: 5, length: 150 },
];

// Building blocks defined by road grid intersections
// Each block has 4 sides; buildings face outward (toward roads)
const BUILDING_BLOCKS = [];

function defineBlocks() {
    BUILDING_BLOCKS.length = 0;

    // Police zone blocks (between z=70 and z=120)
    BUILDING_BLOCKS.push({ zone: 'POLICE', minX: -45, maxX: -10, minZ: 55, maxZ: 90, density: 'low' });
    BUILDING_BLOCKS.push({ zone: 'POLICE', minX: 10, maxX: 45, minZ: 55, maxZ: 90, density: 'low' });
    BUILDING_BLOCKS.push({ zone: 'POLICE', minX: -95, maxX: -55, minZ: 55, maxZ: 90, density: 'low' });
    BUILDING_BLOCKS.push({ zone: 'POLICE', minX: 55, maxX: 95, minZ: 55, maxZ: 90, density: 'low' });

    // Residential blocks (-95 < x < -5, -40 < z < 45)
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -95, maxX: -55, minZ: 10, maxZ: 45, density: 'high' });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -45, maxX: -5, minZ: 10, maxZ: 45, density: 'high' });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -95, maxX: -55, minZ: -40, maxZ: 0, density: 'high' });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -45, maxX: -5, minZ: -40, maxZ: 0, density: 'high' });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -125, maxX: -105, minZ: 10, maxZ: 45, density: 'medium' });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -125, maxX: -105, minZ: -40, maxZ: 0, density: 'medium' });
    BUILDING_BLOCKS.push({ zone: 'RESIDENTIAL', minX: -95, maxX: -55, minZ: -80, maxZ: -50, density: 'medium' });

    // Commercial blocks (5 < x < 95, -40 < z < 45)
    BUILDING_BLOCKS.push({ zone: 'COMMERCIAL', minX: 5, maxX: 45, minZ: 10, maxZ: 45, density: 'high' });
    BUILDING_BLOCKS.push({ zone: 'COMMERCIAL', minX: 55, maxX: 95, minZ: 10, maxZ: 45, density: 'high' });
    BUILDING_BLOCKS.push({ zone: 'COMMERCIAL', minX: 5, maxX: 45, minZ: -40, maxZ: 0, density: 'high' });
    BUILDING_BLOCKS.push({ zone: 'COMMERCIAL', minX: 55, maxX: 95, minZ: -40, maxZ: 0, density: 'high' });
    BUILDING_BLOCKS.push({ zone: 'COMMERCIAL', minX: 105, maxX: 125, minZ: 10, maxZ: 45, density: 'medium' });
    BUILDING_BLOCKS.push({ zone: 'COMMERCIAL', minX: 105, maxX: 125, minZ: -40, maxZ: 0, density: 'medium' });
    BUILDING_BLOCKS.push({ zone: 'COMMERCIAL', minX: 55, maxX: 95, minZ: -80, maxZ: -50, density: 'medium' });

    // Factory blocks (z < -90)
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX: -100, maxX: -55, minZ: -125, maxZ: -95, density: 'sparse' });
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX: -45, maxX: -5, minZ: -125, maxZ: -95, density: 'sparse' });
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX: 5, maxX: 45, minZ: -125, maxZ: -95, density: 'sparse' });
    BUILDING_BLOCKS.push({ zone: 'FACTORY', minX: 55, maxX: 100, minZ: -125, maxZ: -95, density: 'sparse' });
}

function createWorld(scene) {
    const worldGroup = new THREE.Group();
    const buildingData = [];

    defineBlocks();
    createGround(worldGroup);
    createRoadNetwork(worldGroup);
    const policeStation = createPoliceStation(worldGroup);
    buildingData.push(policeStation);

    const zoneBuildings = createGridBuildings(worldGroup);
    buildingData.push(...zoneBuildings);
    // Add police station to global building positions list
    if (window._buildingPositions) {
        window._buildingPositions.push({ x: 0, z: 110, w: 18, d: 14, hideoutIndex: -1 });
    }

    createStreetProps(worldGroup);
    createParks(worldGroup);

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
    // Grass at y=0 (low)
    const grassTex = makeProceduralTexture('#3a6b2a', 60, 512);
    grassTex.repeat.set(20, 20);
    const geo = new THREE.PlaneGeometry(WORLD_SIZE, WORLD_SIZE);
    const mat = new THREE.MeshStandardMaterial({
        color: 0xffffff,
        map: grassTex,
        roughness: 0.95,
        metalness: 0
    });
    const ground = new THREE.Mesh(geo, mat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, 0, 0);
    ground.receiveShadow = true;
    group.add(ground);

    // City boundary wall
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.9 });
    const wallH = 3;
    [[-1,0,1,WORLD_SIZE],[1,0,1,WORLD_SIZE],[0,-1,WORLD_SIZE,1],[0,1,WORLD_SIZE,1]].forEach(([dx,dz,w,d]) => {
        const wall = new THREE.Mesh(new THREE.BoxGeometry(w === 1 ? 1 : WORLD_SIZE, wallH, d === 1 ? 1 : WORLD_SIZE), wallMat);
        wall.position.set(dx * WORLD_SIZE / 2, wallH / 2, dz * WORLD_SIZE / 2);
        wall.castShadow = true;
        group.add(wall);
    });
}

function createRoadNetwork(group) {
    const asphaltTex = makeProceduralTexture('#2a2a2a', 30, 256);
    asphaltTex.repeat.set(8, 8);
    const sidewalkTex = makeProceduralTexture('#a8a8a8', 25, 256);
    sidewalkTex.repeat.set(8, 8);

    const roadMat = new THREE.MeshStandardMaterial({ color: 0xffffff, map: asphaltTex, roughness: 0.85 });
    const sidewalkMat = new THREE.MeshStandardMaterial({ color: 0xffffff, map: sidewalkTex, roughness: 0.9 });
    const stripeMat = new THREE.MeshStandardMaterial({ color: 0xfacc15, roughness: 0.5, emissive: 0x553300, emissiveIntensity: 0.1 });

    // Y positions: grass 0, sidewalk 0.05, road 0.08, stripe 0.12 — clear z-order
    MAIN_ROADS.forEach(r => {
        const w = r.w;
        const sw = w + 6; // sidewalk wider than road
        if (r.type === 'H') {
            // Horizontal road
            const sidewalk = new THREE.Mesh(
                new THREE.BoxGeometry(r.length, 0.06, sw),
                sidewalkMat
            );
            sidewalk.position.set(0, 0.05, r.z);
            sidewalk.receiveShadow = true;
            group.add(sidewalk);

            const road = new THREE.Mesh(
                new THREE.BoxGeometry(r.length, 0.06, w),
                roadMat
            );
            road.position.set(0, 0.08, r.z);
            road.receiveShadow = true;
            group.add(road);

            // Center line (dashed yellow)
            for (let x = -r.length/2 + 4; x < r.length/2; x += 8) {
                const stripe = new THREE.Mesh(
                    new THREE.BoxGeometry(3, 0.05, 0.3),
                    stripeMat
                );
                stripe.position.set(x, 0.12, r.z);
                group.add(stripe);
            }
        } else {
            // Vertical road (optional offsetZ to shift center)
            const oz = r.offsetZ || 0;
            const sidewalk = new THREE.Mesh(
                new THREE.BoxGeometry(sw, 0.06, r.length),
                sidewalkMat
            );
            sidewalk.position.set(r.x, 0.05, oz);
            sidewalk.receiveShadow = true;
            group.add(sidewalk);

            const road = new THREE.Mesh(
                new THREE.BoxGeometry(w, 0.06, r.length),
                roadMat
            );
            road.position.set(r.x, 0.08, oz);
            road.receiveShadow = true;
            group.add(road);

            for (let z = -r.length/2 + 4; z < r.length/2; z += 8) {
                const stripe = new THREE.Mesh(
                    new THREE.BoxGeometry(0.3, 0.05, 3),
                    stripeMat
                );
                stripe.position.set(r.x, 0.12, oz + z);
                group.add(stripe);
            }
        }
    });

    // Crosswalks at major intersections
    const cwMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4 });
    const intersections = [
        [0, 50], [-50, 50], [50, 50], [0, 5], [-50, 5], [50, 5],
        [0, -45], [-50, -45], [50, -45], [0, -85]
    ];
    intersections.forEach(([cx, cz]) => {
        for (let i = -3; i <= 3; i += 1.2) {
            const cw1 = new THREE.Mesh(new THREE.BoxGeometry(5, 0.05, 0.4), cwMat);
            cw1.position.set(cx + i, 0.13, cz - 6);
            group.add(cw1);
            const cw2 = new THREE.Mesh(new THREE.BoxGeometry(5, 0.05, 0.4), cwMat);
            cw2.position.set(cx + i, 0.13, cz + 6);
            group.add(cw2);
        }
    });
}

function createPoliceStation(group) {
    const x = 0, z = 110;
    const w = 18, d = 14, h = 14;
    const building = createBuilding(group, x, z, w, d, h, 0x1a3a5c, '경찰서');

    // Police signage (KOREAN POLICE)
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
        new THREE.MeshStandardMaterial({ map: tex, emissive: 0x001144, emissiveIntensity: 0.3 })
    );
    signMesh.position.set(x, h - 1.5, z + d / 2 + 0.15);
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

    // Standalone POLICE signpost in front of entrance
    const spMat = new THREE.MeshStandardMaterial({ color: 0x222244, roughness: 0.6, metalness: 0.5 });
    const signPost = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 4.5, 8), spMat);
    signPost.position.set(x, 2.25, z + d / 2 + 3);
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
    // Front face
    const spBoard = new THREE.Mesh(
        new THREE.PlaneGeometry(5, 2.5),
        new THREE.MeshStandardMaterial({ map: spTex, emissive: 0x001133, emissiveIntensity: 0.5 })
    );
    spBoard.position.set(x, 5.5, z + d / 2 + 3.07);
    group.add(spBoard);
    // Back face (mirrored)
    const spBoardBack = new THREE.Mesh(
        new THREE.PlaneGeometry(5, 2.5),
        new THREE.MeshStandardMaterial({ map: spTex, emissive: 0x001133, emissiveIntensity: 0.5, side: THREE.BackSide })
    );
    spBoardBack.position.set(x, 5.5, z + d / 2 + 2.93);
    group.add(spBoardBack);
    // Sign cap (top of board)
    const spCap = new THREE.Mesh(
        new THREE.BoxGeometry(5.3, 0.25, 0.35),
        new THREE.MeshStandardMaterial({ color: 0x001166, roughness: 0.5 })
    );
    spCap.position.set(x, 6.75, z + d / 2 + 3);
    group.add(spCap);

    return { mesh: building, x, z, w, d, h, type: 'police', zone: 'POLICE' };
}

function createBuilding(group, x, z, w, d, h, color, label, glass) {
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

    for (let f = 0; f < floors; f++) {
        for (let wi = 0; wi < winRowsW; wi++) {
            // Front
            const winF = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.3, 0.08), winMat);
            winF.position.set(x - w / 2 + (w / winRowsW) * (wi + 0.5), 1.5 + f * 3, z + d / 2 + 0.05);
            group.add(winF);
            // Back
            const winB = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.3, 0.08), winMat);
            winB.position.set(x - w / 2 + (w / winRowsW) * (wi + 0.5), 1.5 + f * 3, z - d / 2 - 0.05);
            group.add(winB);
        }
        for (let di = 0; di < winRowsD; di++) {
            // Right
            const winR = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.3, 0.9), winMat);
            winR.position.set(x + w / 2 + 0.05, 1.5 + f * 3, z - d / 2 + (d / winRowsD) * (di + 0.5));
            group.add(winR);
            // Left
            const winL = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.3, 0.9), winMat);
            winL.position.set(x - w / 2 - 0.05, 1.5 + f * 3, z - d / 2 + (d / winRowsD) * (di + 0.5));
            group.add(winL);
        }
    }

    // Door (always faces nearest road)
    const doorMat = new THREE.MeshStandardMaterial({ color: 0x3a2510, roughness: 0.7 });
    const door = new THREE.Mesh(new THREE.BoxGeometry(1.6, 2.6, 0.15), doorMat);
    door.position.set(x, 1.3, z + d / 2 + 0.08);
    group.add(door);
    // Doorknob
    const knob = new THREE.Mesh(
        new THREE.SphereGeometry(0.06, 8, 8),
        new THREE.MeshStandardMaterial({ color: 0xffcc33, roughness: 0.3, metalness: 0.8 })
    );
    knob.position.set(x + 0.5, 1.3, z + d / 2 + 0.18);
    group.add(knob);

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

    // Color palettes per zone
    const palette = {
        POLICE: [0x889977, 0xa8a896, 0x8b9aa8, 0x99a8b8],
        RESIDENTIAL: [0xc8a888, 0xb8a890, 0xa89878, 0xd0c0a8, 0xc8b8a0, 0xb09880, 0xddc4a0],
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
            bw = 6; bd = 6; bhMin = 6; bhMax = 9; spacing = 9;
        } else if (zone === 'COMMERCIAL') {
            bw = 8; bd = 7; bhMin = 12; bhMax = 24; spacing = 11;
        } else if (zone === 'FACTORY') {
            bw = 12; bd = 11; bhMin = 8; bhMax = 14; spacing = 15;
        }

        const cols = Math.max(1, Math.floor(blockW / spacing));
        const rows = Math.max(1, Math.floor(blockD / spacing));
        const stepX = blockW / cols;
        const stepZ = blockD / rows;

        for (let row = 0; row < rows; row++) {
            for (let col = 0; col < cols; col++) {
                const bx = minX + stepX * (col + 0.5);
                const bz = minZ + stepZ * (row + 0.5);
                const bh = bhMin + Math.random() * (bhMax - bhMin);

                // Sparse density: skip some
                if (density === 'sparse' && Math.random() < 0.3) continue;
                if (density === 'medium' && Math.random() < 0.15) continue;

                const bcolor = palette[zone][Math.floor(Math.random() * palette[zone].length)];
                candidateBuildings.push({
                    bx, bz, bw: bw + (Math.random() - 0.5) * 1.5,
                    bd: bd + (Math.random() - 0.5) * 1.5,
                    bh, bcolor, zone, blockIdx
                });
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
        chosen.bcolor = ht.color;
        chosen.bh = ht.h;
        chosen.bw = Math.max(chosen.bw, 8);
        chosen.bd = Math.max(chosen.bd, 7);
        chosen.criminal = ht.criminal;
        chosen.marker = ht.marker;
    });

    // Create the buildings
    candidateBuildings.forEach(b => {
        const label = b.isHideout ? `${b.zone} 은거지` : `${b.zone}`;
        const isGlass = (b.zone === 'COMMERCIAL' && b.bh >= 15);
        const mesh = createBuilding(group, b.bx, b.bz, b.bw, b.bd, b.bh, b.bcolor, label, isGlass);
        buildings.push({
            mesh, x: b.bx, z: b.bz, w: b.bw, d: b.bd, h: b.bh,
            type: b.isHideout ? 'hideout' : 'normal',
            zone: b.zone,
            hideoutIndex: b.isHideout ? b.criminal : -1
        });

        // Add zone-specific decorations
        if (b.zone === 'RESIDENTIAL') {
            // Pitched roof
            const roofColor = b.isHideout ? 0x4488cc : [0x8b3a1f, 0x6b2810, 0xa84922][Math.floor(Math.random() * 3)];
            const roof = new THREE.Mesh(
                new THREE.ConeGeometry(Math.max(b.bw, b.bd) * 0.78, 1.8, 4),
                new THREE.MeshStandardMaterial({ color: roofColor, roughness: 0.85 })
            );
            roof.position.set(b.bx, b.bh + 0.9, b.bz);
            roof.rotation.y = Math.PI / 4;
            roof.castShadow = true;
            group.add(roof);

            // Front fence removed (was rendering as tall white panels)

            const fmx = b.bx + b.bw / 2 + 0.7, fmz = b.bz + b.bd / 2 + 1.0;
            if (b.marker === 'mailbox') {
                const mb = new THREE.Mesh(
                    new THREE.BoxGeometry(0.5, 1.0, 0.4),
                    new THREE.MeshStandardMaterial({ color: 0xcc0000, roughness: 0.5, metalness: 0.3 })
                );
                mb.position.set(fmx, 0.6, fmz); mb.castShadow = true;
                group.add(mb);
            } else if (b.marker === 'gnome') {
                const g = new THREE.Mesh(
                    new THREE.ConeGeometry(0.25, 0.5, 8),
                    new THREE.MeshStandardMaterial({ color: 0xff3344, roughness: 0.6 })
                );
                g.position.set(fmx, 0.45, fmz); g.castShadow = true;
                group.add(g);
                const body = new THREE.Mesh(
                    new THREE.SphereGeometry(0.18, 12, 12),
                    new THREE.MeshStandardMaterial({ color: 0x4488dd })
                );
                body.position.set(fmx, 0.18, fmz);
                group.add(body);
            } else if (b.marker === 'birdhouse') {
                const pole = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.05, 0.05, 1.8, 8),
                    new THREE.MeshStandardMaterial({ color: 0x4a2510 })
                );
                pole.position.set(fmx, 0.9, fmz);
                group.add(pole);
                const house = new THREE.Mesh(
                    new THREE.BoxGeometry(0.4, 0.4, 0.4),
                    new THREE.MeshStandardMaterial({ color: 0x8b4513, roughness: 0.85 })
                );
                house.position.set(fmx, 2.0, fmz); house.castShadow = true;
                group.add(house);
                const roof = new THREE.Mesh(
                    new THREE.ConeGeometry(0.3, 0.25, 4),
                    new THREE.MeshStandardMaterial({ color: 0xcc6644 })
                );
                roof.position.set(fmx, 2.3, fmz); roof.rotation.y = Math.PI/4;
                group.add(roof);
            } else if (b.marker === 'flowerpot') {
                const pot = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.25, 0.18, 0.35, 12),
                    new THREE.MeshStandardMaterial({ color: 0xb8753a, roughness: 0.9 })
                );
                pot.position.set(fmx, 0.18, fmz); pot.castShadow = true;
                group.add(pot);
                // Flowers
                for (let fi = 0; fi < 5; fi++) {
                    const flower = new THREE.Mesh(
                        new THREE.SphereGeometry(0.06, 8, 8),
                        new THREE.MeshStandardMaterial({ color: [0xff4488, 0xffcc44, 0x88ff44, 0xffffff][fi % 4], emissive: 0x111111 })
                    );
                    flower.position.set(fmx + (Math.random()-0.5)*0.3, 0.45 + Math.random()*0.15, fmz + (Math.random()-0.5)*0.3);
                    group.add(flower);
                }
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
            if (rr.type === 'H' && Math.abs(z - rr.z) < rr.w / 2 + 1) return true;
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
            for (let x = -r.length/2 + 10; x < r.length/2; x += 18) {
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
            if (rr.type === 'H' && Math.abs(z - rr.z) < rr.w / 2 + 2.5) return true;
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
        for (let x = -r.length / 2 + 14; x < r.length / 2 - 6; x += 14) {
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
    // Plaza / fountain removed per design — open ground only
}
