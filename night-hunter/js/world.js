// world.js — 300×300 도시 맵, 건물 50개, 3구역, 도로, 거리 소품

const WORLD_SIZE = 300;

const ZONES = {
    POLICE: { name: '경찰서 구역', cx: 0, cz: 100, w: 120, h: 80 },
    RESIDENTIAL: { name: '주택가 A', cx: -80, cz: 0, w: 120, h: 140 },
    COMMERCIAL: { name: '상업지구 B', cx: 80, cz: 0, w: 120, h: 140 },
    FACTORY: { name: '공장지대 C', cx: 0, cz: -90, w: 250, h: 100 }
};

const HIDEOUT_BUILDINGS = [
    { zone: 'RESIDENTIAL', color: 0x4488cc, floors: 3, width: 8, depth: 7, label: '1호 은거지', mailbox: true },
    { zone: 'COMMERCIAL', color: 0xeeeeee, floors: 5, width: 7, depth: 7, label: '2호 은거지', sign: 'CAFE' },
    { zone: 'FACTORY', color: 0x888888, floors: 7, width: 10, depth: 9, label: '3호 은거지', waterTank: true }
];

function createWorld(scene) {
    const worldGroup = new THREE.Group();
    const buildingData = [];

    createGround(worldGroup);
    createRoads(worldGroup);
    const policeStation = createPoliceStation(worldGroup);
    buildingData.push(policeStation);

    const zoneBuildings = createZoneBuildings(worldGroup);
    buildingData.push(...zoneBuildings);

    connectBuildingsToRoads(worldGroup, buildingData);
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
    // Main ground — PBR with procedural grass texture
    const grassTex = makeProceduralTexture('#3a6b2a', 60, 512);
    grassTex.repeat.set(20, 20);
    const geo = new THREE.PlaneGeometry(WORLD_SIZE, WORLD_SIZE, 60, 60);
    // Add slight bumpiness to vertices
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
        pos.setZ(i, Math.random() * 0.15);
    }
    geo.computeVertexNormals();
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

    // Grass patches for visual variety
    const patchColors = [0x2d5a1e, 0x3a7a2e, 0x4a8a3e, 0x2e6622];
    for (let i = 0; i < 40; i++) {
        const px = (Math.random() - 0.5) * WORLD_SIZE * 0.9;
        const pz = (Math.random() - 0.5) * WORLD_SIZE * 0.9;
        const ps = 8 + Math.random() * 20;
        const patch = new THREE.Mesh(
            new THREE.CircleGeometry(ps, 12),
            new THREE.MeshStandardMaterial({ color: patchColors[i % patchColors.length], roughness: 0.9 })
        );
        patch.rotation.x = -Math.PI / 2;
        patch.position.set(px, 0.01, pz);
        group.add(patch);
    }

    // City boundary wall
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x555555 });
    const wallH = 3;
    [[-1,0,1,WORLD_SIZE],[1,0,1,WORLD_SIZE],[0,-1,WORLD_SIZE,1],[0,1,WORLD_SIZE,1]].forEach(([dx,dz,w,d]) => {
        const wall = new THREE.Mesh(new THREE.BoxGeometry(w === 1 ? 1 : WORLD_SIZE, wallH, d === 1 ? 1 : WORLD_SIZE), wallMat);
        wall.position.set(dx * WORLD_SIZE / 2, wallH / 2, dz * WORLD_SIZE / 2);
        wall.castShadow = true;
        group.add(wall);
    });
}

function createRoads(group) {
    const roadMat = new THREE.MeshStandardMaterial({ color: 0x333333 });
    const sidewalkMat = new THREE.MeshStandardMaterial({ color: 0xaaaaaa });

    function makeRoad(x, z, w, d) {
        const sw = new THREE.Mesh(new THREE.BoxGeometry(w + 2, 0.06, d + 2), sidewalkMat);
        sw.position.set(x, 0.03, z);
        sw.receiveShadow = true;
        group.add(sw);

        const road = new THREE.Mesh(new THREE.BoxGeometry(w, 0.08, d), roadMat);
        road.position.set(x, 0.04, z);
        road.receiveShadow = true;
        group.add(road);

        for (let i = -d / 2 + 3; i < d / 2; i += 6) {
            const stripe = new THREE.Mesh(
                new THREE.BoxGeometry(0.3, 0.09, 2),
                new THREE.MeshStandardMaterial({ color: 0xffffff })
            );
            stripe.position.set(x, 0.045, z + i);
            group.add(stripe);
        }
    }

    // Main horizontal road
    makeRoad(0, 50, 8, WORLD_SIZE);
    // Main vertical road
    makeRoad(0, 0, WORLD_SIZE, 8);
    // Secondary horizontal
    makeRoad(0, -40, 8, 200);
    // Zone connectors
    makeRoad(-50, 25, 6, 100);
    makeRoad(50, 25, 6, 100);

    // Crosswalks at intersections
    const cwMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const crosswalkPositions = [
        [0, 50], [-50, 50], [50, 50], [0, -40], [-50, 0], [50, 0]
    ];
    crosswalkPositions.forEach(([cx, cz]) => {
        for (let i = -3; i <= 3; i += 1.2) {
            const cw = new THREE.Mesh(new THREE.BoxGeometry(4, 0.09, 0.5), cwMat);
            cw.position.set(cx + i, 0.045, cz);
            group.add(cw);
        }
    });
}

function createPoliceStation(group) {
    const x = 0, z = 80;
    const w = 14, d = 10, h = 12;
    const building = createBuilding(group, x, z, w, d, h, 0x1a3a5c, '경찰서');

    // Police sign
    const signGeo = new THREE.BoxGeometry(6, 1.5, 0.2);
    const signMat = new THREE.MeshStandardMaterial({ color: 0x003399 });
    const sign = new THREE.Mesh(signGeo, signMat);
    sign.position.set(x, h - 1, z + d / 2 + 0.15);
    group.add(sign);

    // Police light on top
    const lightGeo = new THREE.SphereGeometry(0.5, 16, 16);
    const lightMat = new THREE.MeshStandardMaterial({ color: 0x0066ff, emissive: 0x0033aa });
    const policeLight = new THREE.Mesh(lightGeo, lightMat);
    policeLight.position.set(x - 1, h + 0.5, z);
    group.add(policeLight);

    const lightRed = new THREE.Mesh(
        new THREE.SphereGeometry(0.5, 16, 16),
        new THREE.MeshStandardMaterial({ color: 0xff0000, emissive: 0xaa0000 })
    );
    lightRed.position.set(x + 1, h + 0.5, z);
    group.add(lightRed);

    // Flagpole
    const pole = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.08, 8),
        new THREE.MeshStandardMaterial({ color: 0xcccccc })
    );
    pole.position.set(x + 8, 4, z + 6);
    group.add(pole);

    return { mesh: building, x, z, w, d, h, type: 'police', zone: 'POLICE' };
}

function createBuilding(group, x, z, w, d, h, color, label) {
    // PBR material with stucco-like roughness
    const mat = new THREE.MeshStandardMaterial({
        color,
        roughness: 0.85,
        metalness: 0.05
    });
    const geo = new THREE.BoxGeometry(w, h, d);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, h / 2, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);

    // Base/foundation
    const base = new THREE.Mesh(
        new THREE.BoxGeometry(w + 0.3, 0.4, d + 0.3),
        new THREE.MeshStandardMaterial({ color: 0x666666 })
    );
    base.position.set(x, 0.2, z);
    base.receiveShadow = true;
    group.add(base);

    // Windows on front and back
    const winMat = new THREE.MeshStandardMaterial({ color: 0x88ccff, emissive: 0x223344 });
    const floors = Math.floor(h / 3);
    for (let f = 0; f < floors; f++) {
        for (let wi = 0; wi < Math.floor(w / 2.5); wi++) {
            // Front windows
            const win = new THREE.Mesh(new THREE.BoxGeometry(0.8, 1.2, 0.1), winMat);
            win.position.set(x - w / 2 + 1.5 + wi * 2.5, 1.5 + f * 3, z + d / 2 + 0.06);
            group.add(win);
            // Back windows
            const win2 = new THREE.Mesh(new THREE.BoxGeometry(0.8, 1.2, 0.1), winMat);
            win2.position.set(x - w / 2 + 1.5 + wi * 2.5, 1.5 + f * 3, z - d / 2 - 0.06);
            group.add(win2);
        }
    }

    // Roof ledge
    const ledge = new THREE.Mesh(
        new THREE.BoxGeometry(w + 0.5, 0.2, d + 0.5),
        new THREE.MeshStandardMaterial({ color: 0x555555 })
    );
    ledge.position.set(x, h + 0.1, z);
    group.add(ledge);

    // Door
    const doorMat = new THREE.MeshStandardMaterial({ color: 0x4a3520 });
    const door = new THREE.Mesh(new THREE.BoxGeometry(1.5, 2.5, 0.15), doorMat);
    door.position.set(x, 1.25, z + d / 2 + 0.08);
    group.add(door);

    // Front road/sidewalk
    const frontRoad = new THREE.Mesh(
        new THREE.BoxGeometry(w + 2, 0.06, 3),
        new THREE.MeshStandardMaterial({ color: 0x555555 })
    );
    frontRoad.position.set(x, 0.03, z + d / 2 + 2.5);
    frontRoad.receiveShadow = true;
    group.add(frontRoad);
    const sidewalk = new THREE.Mesh(
        new THREE.BoxGeometry(w + 3, 0.05, 1.5),
        new THREE.MeshStandardMaterial({ color: 0xaaaaaa })
    );
    sidewalk.position.set(x, 0.025, z + d / 2 + 0.75);
    sidewalk.receiveShadow = true;
    group.add(sidewalk);

    mesh.userData = { label, x, z, w, d, h };
    return mesh;
}

function createZoneBuildings(group) {
    const buildings = [];

    // Grid-based realistic city layout
    // Each zone has rows of buildings facing roads, with narrow gaps between them

    // ── Police Zone (around police station) ──
    // Small commercial: cafe, convenience, pharmacy on either side
    const policeBuildings = [
        { x: -28, z: 92, w: 9, d: 6, h: 6, color: 0xa8b59a, label: '편의점' },
        { x: -16, z: 92, w: 7, d: 6, h: 5, color: 0xc4a882, label: '꽃집' },
        { x: 16, z: 92, w: 8, d: 6, h: 6, color: 0xb5a085, label: '카페' },
        { x: 28, z: 92, w: 9, d: 6, h: 5, color: 0x9eb7a8, label: '약국' },
        { x: -28, z: 68, w: 8, d: 7, h: 12, color: 0x8b9aa8, label: '오피스텔' },
        { x: 28, z: 68, w: 8, d: 7, h: 12, color: 0x99a8b8, label: '오피스' },
    ];
    policeBuildings.forEach(b => {
        const mesh = createBuilding(group, b.x, b.z, b.w, b.d, b.h, b.color, b.label);
        buildings.push({ mesh, ...b, type: 'normal', zone: 'POLICE' });
    });

    // ── Residential Zone A (-140 to -20 x, -100 to 50 z) ──
    // Suburban houses in grid: 5 rows × 4 cols = 20 houses
    const resColors = [0xc8a888, 0xb8a890, 0xa89878, 0xd0c0a8, 0xc8b8a0, 0xb09880];
    const resRows = [-90, -60, -30, 0, 30];
    const resCols = [-130, -110, -90, -70, -45];

    // Hideout 1 placeholder
    let h1Placed = false;

    resRows.forEach((rz, ri) => {
        resCols.forEach((rx, ci) => {
            // Skip cells that would conflict with main road
            if (Math.abs(rz - 50) < 8 || Math.abs(rz + 40) < 8) return;

            const isH1Spot = !h1Placed && ri === 3 && ci === 2;
            const isHideout = isH1Spot;

            const bw = isHideout ? 8 : (5.5 + Math.random() * 1.5);
            const bd = isHideout ? 7 : (5 + Math.random() * 1.5);
            const bh = isHideout ? 9 : (3 + Math.floor(Math.random() * 2) * 3);
            const bcolor = isHideout ? 0x4488cc : resColors[Math.floor(Math.random() * resColors.length)];
            const blabel = isHideout ? '파란 3층집' : `주택 ${ri}-${ci}`;

            const mesh = createBuilding(group, rx, rz, bw, bd, bh, bcolor, blabel);
            buildings.push({ mesh, x: rx, z: rz, w: bw, d: bd, h: bh,
                type: isHideout ? 'hideout' : 'normal', zone: 'RESIDENTIAL',
                hideoutIndex: isHideout ? 0 : -1 });

            // Pitched roof
            const roofGeo = new THREE.ConeGeometry(Math.max(bw, bd) * 0.75, 1.8, 4);
            const roofMat = new THREE.MeshStandardMaterial({
                color: isHideout ? 0x4488cc : [0x8b4513, 0x6b3410, 0xa0522d][Math.floor(Math.random() * 3)],
                roughness: 0.8
            });
            const roof = new THREE.Mesh(roofGeo, roofMat);
            roof.position.set(rx, bh + 0.9, rz);
            roof.rotation.y = Math.PI / 4;
            roof.castShadow = true;
            group.add(roof);

            // Front yard fence
            const fence = new THREE.Mesh(
                new THREE.BoxGeometry(bw + 1.5, 0.6, 0.08),
                new THREE.MeshStandardMaterial({ color: 0xeeeeee, roughness: 0.7 })
            );
            fence.position.set(rx, 0.3, rz + bd / 2 + 1.5);
            group.add(fence);

            if (isHideout) {
                // Red mailbox in front
                const mailbox = new THREE.Mesh(
                    new THREE.BoxGeometry(0.5, 1.0, 0.4),
                    new THREE.MeshStandardMaterial({ color: 0xcc0000, roughness: 0.5, metalness: 0.3 })
                );
                mailbox.position.set(rx + bw / 2 + 0.5, 0.5, rz + bd / 2 + 1);
                mailbox.castShadow = true;
                group.add(mailbox);
                const mboxPole = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.05, 0.05, 1, 8),
                    new THREE.MeshStandardMaterial({ color: 0x666666 })
                );
                mboxPole.position.set(rx + bw / 2 + 0.5, 0.0, rz + bd / 2 + 1);
                group.add(mboxPole);
                h1Placed = true;
            }
        });
    });

    // ── Commercial Zone B (25 to 140 x, -100 to 50 z) ──
    // Taller mixed buildings in tighter grid
    const comColors = [0x6680a0, 0x5a7090, 0x708090, 0x90a0b0, 0x556677, 0x8090a0, 0x607080];
    const comRows = [-90, -60, -25, 5, 35];
    const comCols = [40, 65, 90, 120];

    let h2Placed = false;

    comRows.forEach((rz, ri) => {
        comCols.forEach((rx, ci) => {
            if (Math.abs(rz - 50) < 8) return;

            const isH2Spot = !h2Placed && ri === 2 && ci === 1;
            const isHideout = isH2Spot;

            const bw = isHideout ? 8 : (6 + Math.random() * 3);
            const bd = isHideout ? 7 : (6 + Math.random() * 2);
            const bh = isHideout ? 15 : (9 + Math.floor(Math.random() * 4) * 3);
            const bcolor = isHideout ? 0xf0f0e8 : comColors[Math.floor(Math.random() * comColors.length)];
            const blabel = isHideout ? 'CAFE 건물' : `빌딩 ${ri}-${ci}`;

            const mesh = createBuilding(group, rx, rz, bw, bd, bh, bcolor, blabel);
            buildings.push({ mesh, x: rx, z: rz, w: bw, d: bd, h: bh,
                type: isHideout ? 'hideout' : 'normal', zone: 'COMMERCIAL',
                hideoutIndex: isHideout ? 1 : -1 });

            // AC unit on roof (commercial feature)
            if (Math.random() > 0.5) {
                const ac = new THREE.Mesh(
                    new THREE.BoxGeometry(1.2, 0.6, 0.8),
                    new THREE.MeshStandardMaterial({ color: 0xcccccc, roughness: 0.5 })
                );
                ac.position.set(rx + (Math.random() - 0.5) * (bw - 2), bh + 0.5, rz + (Math.random() - 0.5) * (bd - 2));
                ac.castShadow = true;
                group.add(ac);
            }

            if (isHideout) {
                // Glowing CAFE sign
                const cafeSign = new THREE.Mesh(
                    new THREE.BoxGeometry(4.5, 1.4, 0.35),
                    new THREE.MeshStandardMaterial({ color: 0xff6600, emissive: 0xff6600, emissiveIntensity: 0.4, roughness: 0.4 })
                );
                cafeSign.position.set(rx, bh * 0.5, rz + bd / 2 + 0.25);
                group.add(cafeSign);

                // Sign text via canvas
                const cv = document.createElement('canvas');
                cv.width = 256; cv.height = 80;
                const ct = cv.getContext('2d');
                ct.fillStyle = '#ff6600'; ct.fillRect(0, 0, 256, 80);
                ct.fillStyle = '#fff';
                ct.font = 'bold 56px Inter, sans-serif';
                ct.textAlign = 'center'; ct.textBaseline = 'middle';
                ct.fillText('CAFE', 128, 42);
                const tex = new THREE.CanvasTexture(cv);
                const signMesh = new THREE.Mesh(
                    new THREE.PlaneGeometry(4.5, 1.4),
                    new THREE.MeshBasicMaterial({ map: tex })
                );
                signMesh.position.set(rx, bh * 0.5, rz + bd / 2 + 0.43);
                group.add(signMesh);
                h2Placed = true;
            }
        });
    });

    // ── Factory Zone C (-130 to 130 x, -150 to -100 z) ──
    // Wide industrial warehouses
    const facColors = [0x6a6a6a, 0x5a5a5a, 0x7a7a7a, 0x4a4a4a, 0x808080];
    const facRows = [-145, -118];
    const facCols = [-100, -65, -30, 5, 40, 75, 110];

    let h3Placed = false;

    facRows.forEach((rz, ri) => {
        facCols.forEach((rx, ci) => {
            const isH3Spot = !h3Placed && ri === 1 && ci === 4;
            const isHideout = isH3Spot;

            const bw = isHideout ? 12 : (8 + Math.random() * 4);
            const bd = isHideout ? 10 : (8 + Math.random() * 3);
            const bh = isHideout ? 21 : (6 + Math.floor(Math.random() * 3) * 3);
            const bcolor = isHideout ? 0x888888 : facColors[Math.floor(Math.random() * facColors.length)];
            const blabel = isHideout ? '회색 공장' : `창고 ${ri}-${ci}`;

            const mesh = createBuilding(group, rx, rz, bw, bd, bh, bcolor, blabel);
            buildings.push({ mesh, x: rx, z: rz, w: bw, d: bd, h: bh,
                type: isHideout ? 'hideout' : 'normal', zone: 'FACTORY',
                hideoutIndex: isHideout ? 2 : -1 });

            // Chimney
            if (Math.random() > 0.4) {
                const chimney = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.5, 0.7, 4, 12),
                    new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.9 })
                );
                chimney.position.set(rx - bw / 4, bh + 2, rz);
                chimney.castShadow = true;
                group.add(chimney);
                // Smoke (visible in day too)
                const smoke = new THREE.Mesh(
                    new THREE.SphereGeometry(1.0, 12, 12),
                    new THREE.MeshStandardMaterial({ color: 0xaaaaaa, transparent: true, opacity: 0.4 })
                );
                smoke.position.set(rx - bw / 4, bh + 5, rz);
                group.add(smoke);
            }

            if (isHideout) {
                // Red water tank
                const tank = new THREE.Mesh(
                    new THREE.CylinderGeometry(1.6, 1.6, 3.2, 20),
                    new THREE.MeshStandardMaterial({ color: 0xcc1a1a, roughness: 0.6, metalness: 0.2 })
                );
                tank.position.set(rx + 2, bh + 1.6, rz - 1);
                tank.castShadow = true;
                group.add(tank);
                // Tank legs
                for (let lx = -1; lx <= 1; lx += 2) {
                    for (let lz = -1; lz <= 1; lz += 2) {
                        const leg = new THREE.Mesh(
                            new THREE.CylinderGeometry(0.1, 0.1, 1, 8),
                            new THREE.MeshStandardMaterial({ color: 0x444444 })
                        );
                        leg.position.set(rx + 2 + lx * 0.8, bh + 0.5, rz - 1 + lz * 0.8);
                        group.add(leg);
                    }
                }
                h3Placed = true;
            }
        });
    });

    return buildings;
}

function connectBuildingsToRoads(group, buildings) {
    const roadMat = new THREE.MeshStandardMaterial({ color: 0x444444 });
    const sidewalkMat = new THREE.MeshStandardMaterial({ color: 0x999999 });

    // Main road lines (axis-aligned)
    const mainRoads = [
        { axis: 'z', pos: 0, min: -150, max: 150 },   // vertical center
        { axis: 'x', pos: 50, min: -150, max: 150 },   // horizontal upper
        { axis: 'x', pos: -40, min: -100, max: 100 },  // horizontal lower
        { axis: 'z', pos: -50, min: -25, max: 75 },    // left connector
        { axis: 'z', pos: 50, min: -25, max: 75 },     // right connector
    ];

    buildings.forEach(b => {
        const bx = b.x || 0;
        const bz = b.z || 0;
        const bw = b.w || 6;
        const bd = b.d || 6;
        const frontZ = bz + bd / 2 + 4;

        // Find nearest main road
        let bestDist = Infinity;
        let bestTarget = null;

        mainRoads.forEach(r => {
            if (r.axis === 'x') {
                // Horizontal road at z=r.pos
                const dist = Math.abs(frontZ - r.pos);
                if (dist < bestDist && bx >= r.min && bx <= r.max) {
                    bestDist = dist;
                    bestTarget = { x: bx, z: r.pos };
                }
            } else {
                // Vertical road at x=r.pos
                const dist = Math.abs(bx - r.pos);
                if (dist < bestDist && bz >= r.min && bz <= r.max) {
                    bestDist = dist;
                    bestTarget = { x: r.pos, z: bz };
                }
            }
        });

        if (!bestTarget || bestDist < 3) return;

        // Draw connecting road from building front to nearest main road
        const dx = bestTarget.x - bx;
        const dz = bestTarget.z - frontZ;
        const len = Math.sqrt(dx * dx + dz * dz);
        if (len < 2) return;

        const cx = (bx + bestTarget.x) / 2;
        const cz = (frontZ + bestTarget.z) / 2;
        const angle = Math.atan2(dx, dz);

        // Sidewalk (wider)
        const sw = new THREE.Mesh(new THREE.BoxGeometry(4, 0.04, len + 1), sidewalkMat);
        sw.position.set(cx, 0.02, cz);
        sw.rotation.y = angle;
        sw.receiveShadow = true;
        group.add(sw);

        // Road surface
        const road = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.06, len), roadMat);
        road.position.set(cx, 0.03, cz);
        road.rotation.y = angle;
        road.receiveShadow = true;
        group.add(road);
    });
}

function createStreetLight(group, x, z) {
    const poleMat = new THREE.MeshStandardMaterial({ color: 0x555555 });
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.12, 5, 8), poleMat);
    pole.position.set(x, 2.5, z);
    pole.castShadow = true;
    group.add(pole);

    const arm = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.08, 0.08), poleMat);
    arm.position.set(x + 0.75, 5, z);
    group.add(arm);

    const lampGeo = new THREE.SphereGeometry(0.3, 8, 8);
    const lampMat = new THREE.MeshStandardMaterial({ color: 0xffdd88, emissive: 0x332200 });
    const lamp = new THREE.Mesh(lampGeo, lampMat);
    lamp.position.set(x + 1.5, 4.8, z);
    lamp.userData.isStreetLight = true;
    group.add(lamp);

    return lamp;
}

function createStreetProps(group) {
    const streetLights = [];

    // Streetlights along roads (40 total)
    for (let i = -140; i <= 140; i += 15) {
        streetLights.push(createStreetLight(group, 6, i));
        streetLights.push(createStreetLight(group, -6, i));
    }
    for (let i = -60; i <= 60; i += 20) {
        streetLights.push(createStreetLight(group, i, 56));
    }

    window._streetLights = streetLights;

    // Benches (15)
    const benchMat = new THREE.MeshStandardMaterial({ color: 0x8B4513 });
    const benchPositions = [
        [10, 85], [-10, 85], [30, 55], [-30, 55], [10, 55],
        [-10, 30], [10, 30], [-40, 10], [40, 10], [0, 10],
        [-60, -20], [60, -20], [0, -50], [-30, -80], [30, -80]
    ];
    benchPositions.forEach(([bx, bz]) => {
        const seat = new THREE.Mesh(new THREE.BoxGeometry(2, 0.15, 0.6), benchMat);
        seat.position.set(bx, 0.5, bz);
        seat.castShadow = true;
        group.add(seat);
        const back = new THREE.Mesh(new THREE.BoxGeometry(2, 0.6, 0.1), benchMat);
        back.position.set(bx, 0.8, bz - 0.25);
        group.add(back);
        const leg1 = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.5, 0.6), new THREE.MeshStandardMaterial({ color: 0x333333 }));
        leg1.position.set(bx - 0.8, 0.25, bz);
        group.add(leg1);
        const leg2 = leg1.clone();
        leg2.position.set(bx + 0.8, 0.25, bz);
        group.add(leg2);
    });

    // Trash cans (10)
    const trashPositions = [
        [12, 82], [-12, 82], [5, 55], [-5, 55], [25, 40],
        [-25, 0], [25, 0], [0, -30], [-50, -60], [50, -60]
    ];
    trashPositions.forEach(([tx, tz]) => {
        const can = new THREE.Mesh(
            new THREE.CylinderGeometry(0.3, 0.35, 1, 8),
            new THREE.MeshStandardMaterial({ color: 0x336633 })
        );
        can.position.set(tx, 0.5, tz);
        can.castShadow = true;
        group.add(can);
        const lid = new THREE.Mesh(
            new THREE.CylinderGeometry(0.35, 0.35, 0.08, 8),
            new THREE.MeshStandardMaterial({ color: 0x444444 })
        );
        lid.position.set(tx, 1.04, tz);
        group.add(lid);
    });

    // Traffic lights (8)
    const tlPositions = [
        [5, 55], [-5, 55], [5, 45], [-5, 45],
        [55, 5], [-55, 5], [55, -5], [-55, -5]
    ];
    tlPositions.forEach(([tlx, tlz]) => {
        const tlPole = new THREE.Mesh(
            new THREE.CylinderGeometry(0.08, 0.08, 4, 6),
            new THREE.MeshStandardMaterial({ color: 0x333333 })
        );
        tlPole.position.set(tlx, 2, tlz);
        group.add(tlPole);

        const tlBox = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, 1.2, 0.4),
            new THREE.MeshStandardMaterial({ color: 0x222222 })
        );
        tlBox.position.set(tlx, 4.2, tlz);
        group.add(tlBox);

        [0xff0000, 0xffaa00, 0x00ff00].forEach((c, ci) => {
            const light = new THREE.Mesh(
                new THREE.SphereGeometry(0.12, 8, 8),
                new THREE.MeshStandardMaterial({ color: c, emissive: ci === 2 ? 0x003300 : 0x000000 })
            );
            light.position.set(tlx, 4.6 - ci * 0.35, tlz + 0.22);
            group.add(light);
        });
    });

    // Trees (30)
    const treeMat = new THREE.MeshStandardMaterial({ color: 0x2d5a1e });
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5c3a1e });
    for (let i = 0; i < 30; i++) {
        let tx, tz;
        let attempts = 0;
        do {
            tx = -140 + Math.random() * 280;
            tz = -140 + Math.random() * 280;
            attempts++;
        } while (attempts < 30 && (
            (Math.abs(tx) < 8) || (Math.abs(tz - 50) < 8) ||
            (Math.abs(tx) < 8 && Math.abs(tz) < 8)
        ));

        const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.2, 2, 6), trunkMat);
        trunk.position.set(tx, 1, tz);
        trunk.castShadow = true;
        group.add(trunk);

        const canopy = new THREE.Mesh(new THREE.SphereGeometry(1.5 + Math.random(), 8, 8), treeMat);
        canopy.position.set(tx, 3 + Math.random(), tz);
        canopy.castShadow = true;
        group.add(canopy);
    }
}

function createParks(group) {
    // Central plaza with fountain
    const plazaGeo = new THREE.CircleGeometry(12, 32);
    const plazaMat = new THREE.MeshStandardMaterial({ color: 0x999988 });
    const plaza = new THREE.Mesh(plazaGeo, plazaMat);
    plaza.rotation.x = -Math.PI / 2;
    plaza.position.set(0, 0.05, 50);
    group.add(plaza);

    // Fountain base
    const fountainBase = new THREE.Mesh(
        new THREE.CylinderGeometry(3, 3.5, 0.8, 24),
        new THREE.MeshStandardMaterial({ color: 0x888888 })
    );
    fountainBase.position.set(0, 0.4, 50);
    group.add(fountainBase);

    // Fountain water
    const water = new THREE.Mesh(
        new THREE.CylinderGeometry(2.5, 2.5, 0.3, 24),
        new THREE.MeshStandardMaterial({ color: 0x4488cc, transparent: true, opacity: 0.7 })
    );
    water.position.set(0, 0.65, 50);
    group.add(water);

    // Fountain center pillar
    const pillar = new THREE.Mesh(
        new THREE.CylinderGeometry(0.3, 0.4, 2.5, 12),
        new THREE.MeshStandardMaterial({ color: 0x777777 })
    );
    pillar.position.set(0, 1.8, 50);
    group.add(pillar);

    // Small parks (2)
    const parkPositions = [[-60, 40], [60, -30]];
    parkPositions.forEach(([px, pz]) => {
        const parkGround = new THREE.Mesh(
            new THREE.PlaneGeometry(15, 15),
            new THREE.MeshStandardMaterial({ color: 0x3a7a2e })
        );
        parkGround.rotation.x = -Math.PI / 2;
        parkGround.position.set(px, 0.02, pz);
        group.add(parkGround);

        // Park trees
        for (let t = 0; t < 4; t++) {
            const ox = (Math.random() - 0.5) * 10;
            const oz = (Math.random() - 0.5) * 10;
            const trunk = new THREE.Mesh(
                new THREE.CylinderGeometry(0.12, 0.18, 1.8, 6),
                new THREE.MeshStandardMaterial({ color: 0x5c3a1e })
            );
            trunk.position.set(px + ox, 0.9, pz + oz);
            trunk.castShadow = true;
            group.add(trunk);

            const canopy = new THREE.Mesh(
                new THREE.SphereGeometry(1.2, 8, 8),
                new THREE.MeshStandardMaterial({ color: 0x2d6a1e })
            );
            canopy.position.set(px + ox, 2.5, pz + oz);
            canopy.castShadow = true;
            group.add(canopy);
        }

        // Park bench
        const seat = new THREE.Mesh(
            new THREE.BoxGeometry(2, 0.12, 0.5),
            new THREE.MeshStandardMaterial({ color: 0x8B4513 })
        );
        seat.position.set(px, 0.45, pz + 5);
        group.add(seat);
    });
}
