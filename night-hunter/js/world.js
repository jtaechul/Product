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

    createStreetProps(worldGroup);
    createParks(worldGroup);

    scene.add(worldGroup);
    return { worldGroup, buildingData };
}

function createGround(group) {
    const geo = new THREE.PlaneGeometry(WORLD_SIZE, WORLD_SIZE);
    const mat = new THREE.MeshLambertMaterial({ color: 0x2d5a1e });
    const ground = new THREE.Mesh(geo, mat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(0, 0, 0);
    ground.receiveShadow = true;
    group.add(ground);

    const boundary = new THREE.LineSegments(
        new THREE.EdgesGeometry(new THREE.BoxGeometry(WORLD_SIZE, 0.5, WORLD_SIZE)),
        new THREE.LineBasicMaterial({ color: 0x444444 })
    );
    boundary.position.y = 0.25;
    group.add(boundary);
}

function createRoads(group) {
    const roadMat = new THREE.MeshLambertMaterial({ color: 0x333333 });
    const sidewalkMat = new THREE.MeshLambertMaterial({ color: 0xaaaaaa });

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
                new THREE.MeshLambertMaterial({ color: 0xffffff })
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
    const cwMat = new THREE.MeshLambertMaterial({ color: 0xffffff });
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
    const signMat = new THREE.MeshLambertMaterial({ color: 0x003399 });
    const sign = new THREE.Mesh(signGeo, signMat);
    sign.position.set(x, h - 1, z + d / 2 + 0.15);
    group.add(sign);

    // Police light on top
    const lightGeo = new THREE.SphereGeometry(0.5, 16, 16);
    const lightMat = new THREE.MeshPhongMaterial({ color: 0x0066ff, emissive: 0x0033aa });
    const policeLight = new THREE.Mesh(lightGeo, lightMat);
    policeLight.position.set(x - 1, h + 0.5, z);
    group.add(policeLight);

    const lightRed = new THREE.Mesh(
        new THREE.SphereGeometry(0.5, 16, 16),
        new THREE.MeshPhongMaterial({ color: 0xff0000, emissive: 0xaa0000 })
    );
    lightRed.position.set(x + 1, h + 0.5, z);
    group.add(lightRed);

    // Flagpole
    const pole = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.08, 8),
        new THREE.MeshLambertMaterial({ color: 0xcccccc })
    );
    pole.position.set(x + 8, 4, z + 6);
    group.add(pole);

    return { mesh: building, x, z, w, d, h, type: 'police', zone: 'POLICE' };
}

function createBuilding(group, x, z, w, d, h, color, label) {
    const geo = new THREE.BoxGeometry(w, h, d);
    const mat = new THREE.MeshLambertMaterial({ color });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, h / 2, z);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);

    // Windows
    const winMat = new THREE.MeshPhongMaterial({ color: 0x88ccff, emissive: 0x112233 });
    const floors = Math.floor(h / 3);
    for (let f = 0; f < floors; f++) {
        for (let wi = 0; wi < Math.floor(w / 2.5); wi++) {
            const win = new THREE.Mesh(new THREE.BoxGeometry(0.8, 1.2, 0.1), winMat);
            win.position.set(
                x - w / 2 + 1.5 + wi * 2.5,
                1.5 + f * 3,
                z + d / 2 + 0.06
            );
            group.add(win);
        }
    }

    // Door
    const doorMat = new THREE.MeshLambertMaterial({ color: 0x4a3520 });
    const door = new THREE.Mesh(new THREE.BoxGeometry(1.5, 2.5, 0.15), doorMat);
    door.position.set(x, 1.25, z + d / 2 + 0.08);
    group.add(door);

    // Front road/sidewalk
    const frontRoad = new THREE.Mesh(
        new THREE.BoxGeometry(w + 2, 0.06, 3),
        new THREE.MeshLambertMaterial({ color: 0x555555 })
    );
    frontRoad.position.set(x, 0.03, z + d / 2 + 2.5);
    frontRoad.receiveShadow = true;
    group.add(frontRoad);
    const sidewalk = new THREE.Mesh(
        new THREE.BoxGeometry(w + 3, 0.05, 1.5),
        new THREE.MeshLambertMaterial({ color: 0xaaaaaa })
    );
    sidewalk.position.set(x, 0.025, z + d / 2 + 0.75);
    sidewalk.receiveShadow = true;
    group.add(sidewalk);

    mesh.userData = { label, x, z, w, d, h };
    return mesh;
}

function createZoneBuildings(group) {
    const buildings = [];
    const placed = [];

    function canPlace(px, pz, pw, pd) {
        const margin = 3;
        for (const p of placed) {
            if (Math.abs(px - p.x) < (pw + p.w) / 2 + margin &&
                Math.abs(pz - p.z) < (pd + p.d) / 2 + margin) {
                return false;
            }
        }
        if (Math.abs(px) < 6 && Math.abs(pz - 50) < 6) return false;
        if (Math.abs(px) < 6 && Math.abs(pz) < 6) return false;
        return true;
    }

    // Police zone buildings (6 more, total 7 with station)
    const policeBuildings = [
        { x: -20, z: 90, w: 6, d: 5, h: 6, color: 0x889977, label: '편의점' },
        { x: 20, z: 90, w: 7, d: 5, h: 6, color: 0x997766, label: '카페' },
        { x: -25, z: 70, w: 5, d: 5, h: 9, color: 0x667788, label: '아파트' },
        { x: 25, z: 70, w: 6, d: 6, h: 9, color: 0x776655, label: '사무실' },
        { x: -15, z: 65, w: 5, d: 5, h: 6, color: 0x998877, label: '약국' },
        { x: 15, z: 65, w: 7, d: 5, h: 6, color: 0x778899, label: '식당' }
    ];
    policeBuildings.forEach(b => {
        const mesh = createBuilding(group, b.x, b.z, b.w, b.d, b.h, b.color, b.label);
        buildings.push({ mesh, ...b, type: 'normal', zone: 'POLICE' });
        placed.push(b);
    });

    // Residential zone A (15 buildings, including hideout 1)
    const resColors = [0x8B4513, 0xCD853F, 0xA0522D, 0xD2691E, 0xBC8F8F, 0xF5DEB3, 0xDEB887, 0xC4A882];
    for (let i = 0; i < 15; i++) {
        let bx, bz, bw, bd, bh, bcolor, blabel, isHideout = false;

        if (i === 0) {
            // Hideout 1: blue 3-floor in residential
            bx = -70; bz = 15; bw = 8; bd = 7;
            bh = 9; bcolor = 0x4488cc; blabel = '파란 3층집';
            isHideout = true;
        } else {
            const attempts = 50;
            let found = false;
            for (let a = 0; a < attempts; a++) {
                bx = -130 + Math.random() * 110;
                bz = -60 + Math.random() * 120;
                bw = 5 + Math.random() * 4;
                bd = 5 + Math.random() * 3;
                if (canPlace(bx, bz, bw, bd)) { found = true; break; }
            }
            if (!found) continue;
            const floors = 2 + Math.floor(Math.random() * 3);
            bh = floors * 3;
            bcolor = resColors[Math.floor(Math.random() * resColors.length)];
            blabel = '주택 ' + (i + 1);
        }

        const mesh = createBuilding(group, bx, bz, bw, bd, bh, bcolor, blabel);
        buildings.push({ mesh, x: bx, z: bz, w: bw, d: bd, h: bh, type: isHideout ? 'hideout' : 'normal', zone: 'RESIDENTIAL', hideoutIndex: isHideout ? 0 : -1 });
        placed.push({ x: bx, z: bz, w: bw, d: bd });

        if (isHideout) {
            // Red mailbox
            const mailbox = new THREE.Mesh(
                new THREE.BoxGeometry(0.6, 1.2, 0.5),
                new THREE.MeshLambertMaterial({ color: 0xcc0000 })
            );
            mailbox.position.set(bx + bw / 2 + 1, 0.6, bz + bd / 2);
            mailbox.castShadow = true;
            group.add(mailbox);
        }

        // Triangular roofs for residential
        if (!isHideout || i === 0) {
            const roofGeo = new THREE.ConeGeometry(Math.max(bw, bd) * 0.7, 2, 4);
            const roofMat = new THREE.MeshLambertMaterial({ color: 0x8B0000 });
            const roof = new THREE.Mesh(roofGeo, roofMat);
            roof.position.set(bx, bh + 1, bz);
            roof.rotation.y = Math.PI / 4;
            roof.castShadow = true;
            group.add(roof);
        }
    }

    // Commercial zone B (18 buildings, including hideout 2)
    const comColors = [0x6688aa, 0x556677, 0x778899, 0x8899aa, 0x445566, 0x99aabb, 0x667788, 0x889999];
    for (let i = 0; i < 18; i++) {
        let bx, bz, bw, bd, bh, bcolor, blabel, isHideout = false;

        if (i === 0) {
            // Hideout 2: white 5-floor in commercial, CAFE sign
            bx = 70; bz = 10; bw = 7; bd = 7;
            bh = 15; bcolor = 0xeeeeee; blabel = 'CAFE 건물';
            isHideout = true;
        } else {
            const attempts = 50;
            let found = false;
            for (let a = 0; a < attempts; a++) {
                bx = 25 + Math.random() * 110;
                bz = -60 + Math.random() * 120;
                bw = 5 + Math.random() * 5;
                bd = 5 + Math.random() * 4;
                if (canPlace(bx, bz, bw, bd)) { found = true; break; }
            }
            if (!found) continue;
            const floors = 4 + Math.floor(Math.random() * 5);
            bh = floors * 3;
            bcolor = comColors[Math.floor(Math.random() * comColors.length)];
            blabel = '빌딩 ' + (i + 1);
        }

        const mesh = createBuilding(group, bx, bz, bw, bd, bh, bcolor, blabel);
        buildings.push({ mesh, x: bx, z: bz, w: bw, d: bd, h: bh, type: isHideout ? 'hideout' : 'normal', zone: 'COMMERCIAL', hideoutIndex: isHideout ? 1 : -1 });
        placed.push({ x: bx, z: bz, w: bw, d: bd });

        if (isHideout) {
            // CAFE sign
            const cafeGeo = new THREE.BoxGeometry(4, 1.2, 0.3);
            const cafeMat = new THREE.MeshPhongMaterial({ color: 0xff6600, emissive: 0x331100 });
            const cafeSign = new THREE.Mesh(cafeGeo, cafeMat);
            cafeSign.position.set(bx, bh * 0.6, bz + bd / 2 + 0.2);
            group.add(cafeSign);
        }
    }

    // Factory zone C (10 buildings, including hideout 3)
    const facColors = [0x555555, 0x666666, 0x777777, 0x4a4a4a, 0x5a5a5a];
    for (let i = 0; i < 10; i++) {
        let bx, bz, bw, bd, bh, bcolor, blabel, isHideout = false;

        if (i === 0) {
            // Hideout 3: gray 7-floor in factory, red water tank on roof
            bx = 10; bz = -100; bw = 10; bd = 9;
            bh = 21; bcolor = 0x888888; blabel = '회색 공장';
            isHideout = true;
        } else {
            const attempts = 50;
            let found = false;
            for (let a = 0; a < attempts; a++) {
                bx = -110 + Math.random() * 220;
                bz = -140 + Math.random() * 80;
                bw = 8 + Math.random() * 8;
                bd = 6 + Math.random() * 6;
                if (canPlace(bx, bz, bw, bd)) { found = true; break; }
            }
            if (!found) continue;
            const floors = 2 + Math.floor(Math.random() * 3);
            bh = floors * 3;
            bcolor = facColors[Math.floor(Math.random() * facColors.length)];
            blabel = '창고 ' + (i + 1);
        }

        const mesh = createBuilding(group, bx, bz, bw, bd, bh, bcolor, blabel);
        buildings.push({ mesh, x: bx, z: bz, w: bw, d: bd, h: bh, type: isHideout ? 'hideout' : 'normal', zone: 'FACTORY', hideoutIndex: isHideout ? 2 : -1 });
        placed.push({ x: bx, z: bz, w: bw, d: bd });

        if (isHideout) {
            // Red water tank on roof
            const tank = new THREE.Mesh(
                new THREE.CylinderGeometry(1.5, 1.5, 3, 16),
                new THREE.MeshLambertMaterial({ color: 0xcc0000 })
            );
            tank.position.set(bx + 2, bh + 1.5, bz - 1);
            tank.castShadow = true;
            group.add(tank);
        }

        // Chimneys for factory buildings
        if (Math.random() > 0.3) {
            const chimney = new THREE.Mesh(
                new THREE.CylinderGeometry(0.5, 0.7, 4, 8),
                new THREE.MeshLambertMaterial({ color: 0x444444 })
            );
            chimney.position.set(bx - bw / 4, bh + 2, bz);
            chimney.castShadow = true;
            group.add(chimney);
        }

        // Fences for factory zone
        if (!isHideout && Math.random() > 0.5) {
            const fenceGeo = new THREE.BoxGeometry(bw + 4, 1.5, 0.1);
            const fenceMat = new THREE.MeshLambertMaterial({ color: 0x666666, wireframe: true });
            const fence = new THREE.Mesh(fenceGeo, fenceMat);
            fence.position.set(bx, 0.75, bz + bd / 2 + 2);
            group.add(fence);
        }
    }

    return buildings;
}

function createStreetLight(group, x, z) {
    const poleMat = new THREE.MeshLambertMaterial({ color: 0x555555 });
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.12, 5, 8), poleMat);
    pole.position.set(x, 2.5, z);
    pole.castShadow = true;
    group.add(pole);

    const arm = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.08, 0.08), poleMat);
    arm.position.set(x + 0.75, 5, z);
    group.add(arm);

    const lampGeo = new THREE.SphereGeometry(0.3, 8, 8);
    const lampMat = new THREE.MeshPhongMaterial({ color: 0xffdd88, emissive: 0x332200 });
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
    const benchMat = new THREE.MeshLambertMaterial({ color: 0x8B4513 });
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
        const leg1 = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.5, 0.6), new THREE.MeshLambertMaterial({ color: 0x333333 }));
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
            new THREE.MeshLambertMaterial({ color: 0x336633 })
        );
        can.position.set(tx, 0.5, tz);
        can.castShadow = true;
        group.add(can);
        const lid = new THREE.Mesh(
            new THREE.CylinderGeometry(0.35, 0.35, 0.08, 8),
            new THREE.MeshLambertMaterial({ color: 0x444444 })
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
            new THREE.MeshLambertMaterial({ color: 0x333333 })
        );
        tlPole.position.set(tlx, 2, tlz);
        group.add(tlPole);

        const tlBox = new THREE.Mesh(
            new THREE.BoxGeometry(0.5, 1.2, 0.4),
            new THREE.MeshLambertMaterial({ color: 0x222222 })
        );
        tlBox.position.set(tlx, 4.2, tlz);
        group.add(tlBox);

        [0xff0000, 0xffaa00, 0x00ff00].forEach((c, ci) => {
            const light = new THREE.Mesh(
                new THREE.SphereGeometry(0.12, 8, 8),
                new THREE.MeshPhongMaterial({ color: c, emissive: ci === 2 ? 0x003300 : 0x000000 })
            );
            light.position.set(tlx, 4.6 - ci * 0.35, tlz + 0.22);
            group.add(light);
        });
    });

    // Trees (30)
    const treeMat = new THREE.MeshLambertMaterial({ color: 0x2d5a1e });
    const trunkMat = new THREE.MeshLambertMaterial({ color: 0x5c3a1e });
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
    const plazaMat = new THREE.MeshLambertMaterial({ color: 0x999988 });
    const plaza = new THREE.Mesh(plazaGeo, plazaMat);
    plaza.rotation.x = -Math.PI / 2;
    plaza.position.set(0, 0.05, 50);
    group.add(plaza);

    // Fountain base
    const fountainBase = new THREE.Mesh(
        new THREE.CylinderGeometry(3, 3.5, 0.8, 24),
        new THREE.MeshLambertMaterial({ color: 0x888888 })
    );
    fountainBase.position.set(0, 0.4, 50);
    group.add(fountainBase);

    // Fountain water
    const water = new THREE.Mesh(
        new THREE.CylinderGeometry(2.5, 2.5, 0.3, 24),
        new THREE.MeshPhongMaterial({ color: 0x4488cc, transparent: true, opacity: 0.7 })
    );
    water.position.set(0, 0.65, 50);
    group.add(water);

    // Fountain center pillar
    const pillar = new THREE.Mesh(
        new THREE.CylinderGeometry(0.3, 0.4, 2.5, 12),
        new THREE.MeshLambertMaterial({ color: 0x777777 })
    );
    pillar.position.set(0, 1.8, 50);
    group.add(pillar);

    // Small parks (2)
    const parkPositions = [[-60, 40], [60, -30]];
    parkPositions.forEach(([px, pz]) => {
        const parkGround = new THREE.Mesh(
            new THREE.PlaneGeometry(15, 15),
            new THREE.MeshLambertMaterial({ color: 0x3a7a2e })
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
                new THREE.MeshLambertMaterial({ color: 0x5c3a1e })
            );
            trunk.position.set(px + ox, 0.9, pz + oz);
            trunk.castShadow = true;
            group.add(trunk);

            const canopy = new THREE.Mesh(
                new THREE.SphereGeometry(1.2, 8, 8),
                new THREE.MeshLambertMaterial({ color: 0x2d6a1e })
            );
            canopy.position.set(px + ox, 2.5, pz + oz);
            canopy.castShadow = true;
            group.add(canopy);
        }

        // Park bench
        const seat = new THREE.Mesh(
            new THREE.BoxGeometry(2, 0.12, 0.5),
            new THREE.MeshLambertMaterial({ color: 0x8B4513 })
        );
        seat.position.set(px, 0.45, pz + 5);
        group.add(seat);
    });
}
