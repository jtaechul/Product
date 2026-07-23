import * as THREE from 'three';

// ─── 건물 데이터 ────────────────────────────────────────────────
// 도로: N-S x=-14(폭8), x=14(폭8) / E-W z=-20(폭8), z=20(폭8)
// 건물 x: 주택가 < -20, 상업 -8~8, 공장 > 20
// 건물 z: 중앙 -14~14, 남 < -25, 북 > 25

const BUILDINGS = [
    // 주택가 (residential) — 낮고 따뜻한 색
    { x: -38, z: -35, w: 8,  h: 5,  d: 8,  color: 0xE8C090 },
    { x: -32, z:  -3, w: 7,  h: 4,  d: 9,  color: 0xD4A574 },
    { x: -24, z:   9, w: 9,  h: 6,  d: 8,  color: 0xC8B89A },
    { x: -40, z:  32, w: 7,  h: 5,  d: 7,  color: 0xB8A080 },
    { x: -28, z: -30, w: 8,  h: 4,  d: 7,  color: 0xE0C070 },

    // 상업지구 (commercial) — 높고 유리 느낌
    { x:  -6, z: -33, w: 10, h: 16, d: 10, color: 0x4A90D9 },
    { x:   6, z:  -4, w:  8, h: 22, d:  8, color: 0x2C7BC7 },
    { x:  -4, z:   7, w: 12, h: 12, d: 10, color: 0x85C1E9 },
    { x:   5, z:  33, w:  8, h: 18, d:  8, color: 0x1A5276 },
    { x:  -2, z: -43, w:  6, h: 28, d:  6, color: 0x5DADE2 },

    // 공장지대 (industrial) — 넓고 어두운 색
    { x:  32, z: -30, w: 16, h:  7, d: 12, color: 0x7F8C8D },
    { x:  38, z:   5, w: 12, h:  5, d: 15, color: 0x626567 },
    { x:  28, z:  32, w: 18, h:  6, d: 10, color: 0x808B96 },
    { x:  42, z: -43, w: 10, h: 10, d: 10, color: 0x5D6D7E },
    { x:  26, z:  -4, w:  8, h:  9, d:  8, color: 0x717D7E },
];

// ─── 가로등 위치 ────────────────────────────────────────────────
const LAMP_POSITIONS = [
    // N-S 도로 왼쪽(주택가 경계) x=-18
    { x: -18, z: -36 },
    { x: -18, z:   0 },
    { x: -18, z:  36 },
    // N-S 도로 오른쪽(공장 경계) x=18
    { x:  18, z: -36 },
    { x:  18, z:   0 },
    { x:  18, z:  36 },
    // E-W 도로 z=-20 주변
    { x: -38, z: -25 },
    { x:   0, z: -25 },
    { x:  35, z: -25 },
    // E-W 도로 z=20 주변
    { x:   0, z:  25 },
];

// ─── 공장 굴뚝 (선택 장식) ─────────────────────────────────────
const CHIMNEYS = [
    { x: 35, z: -26, r: 0.8, h: 14 },
    { x: 42, z: -46, r: 0.7, h: 12 },
    { x: 30, z:  29, r: 0.9, h: 10 },
];

export function buildCity(scene) {
    addSceneLighting(scene);
    addGround(scene);
    addRoads(scene);
    addBuildings(scene);
    addStreetLamps(scene);
    addChimneys(scene);
}

// ─── 조명 ──────────────────────────────────────────────────────
function addSceneLighting(scene) {
    // 부드러운 전체 조명
    scene.add(new THREE.AmbientLight(0xd0e8ff, 0.55));

    // 태양광
    const sun = new THREE.DirectionalLight(0xfff4e0, 1.0);
    sun.position.set(60, 100, 40);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 300;
    sun.shadow.camera.left   = -85;
    sun.shadow.camera.right  =  85;
    sun.shadow.camera.top    =  85;
    sun.shadow.camera.bottom = -85;
    scene.add(sun);

    // 반사광 (북쪽 하늘)
    const fill = new THREE.DirectionalLight(0x88aaff, 0.25);
    fill.position.set(-40, 60, -60);
    scene.add(fill);
}

// ─── 지면 ──────────────────────────────────────────────────────
function addGround(scene) {
    const geo = new THREE.PlaneGeometry(140, 140);
    const mat = new THREE.MeshLambertMaterial({ color: 0x6B7B5A });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.rotation.x = -Math.PI / 2;
    mesh.receiveShadow = true;
    scene.add(mesh);
}

// ─── 도로 + 인도 ───────────────────────────────────────────────
function addRoads(scene) {
    const roadMat = new THREE.MeshLambertMaterial({ color: 0x454545 });
    const walkMat = new THREE.MeshLambertMaterial({ color: 0xAAAAAA });

    function plane(mat, x, z, w, d, y = 0.01) {
        const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), mat);
        m.rotation.x = -Math.PI / 2;
        m.position.set(x, y, z);
        m.receiveShadow = true;
        scene.add(m);
    }

    // 인도 (더 밝음, y 약간 낮게 먼저 깔기)
    plane(walkMat, -14,  0, 11, 140, 0.008);
    plane(walkMat,  14,  0, 11, 140, 0.008);
    plane(walkMat,   0, -20, 140, 10, 0.008);
    plane(walkMat,   0,  20, 140, 10, 0.008);

    // 차도 (어두움, y 살짝 위)
    plane(roadMat, -14,  0,  7, 140, 0.015);
    plane(roadMat,  14,  0,  7, 140, 0.015);
    plane(roadMat,   0, -20, 140,  6, 0.015);
    plane(roadMat,   0,  20, 140,  6, 0.015);

    // 교차로 센터 (인도 색)
    plane(walkMat, -14, -20, 11, 10, 0.02);
    plane(walkMat, -14,  20, 11, 10, 0.02);
    plane(walkMat,  14, -20, 11, 10, 0.02);
    plane(walkMat,  14,  20, 11, 10, 0.02);

    // 중앙선 (흰 점선 느낌 — 얇은 박스들)
    const lineMat = new THREE.MeshBasicMaterial({ color: 0xFFFFCC });
    for (let z = -65; z < 70; z += 8) {
        const line = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.02, 4), lineMat);
        line.position.set(-14, 0.02, z);
        scene.add(line);
        const line2 = line.clone();
        line2.position.set(14, 0.02, z);
        scene.add(line2);
    }
    for (let x = -65; x < 70; x += 8) {
        const line = new THREE.Mesh(new THREE.BoxGeometry(4, 0.02, 0.25), lineMat);
        line.position.set(x, 0.02, -20);
        scene.add(line);
        const line2 = line.clone();
        line2.position.set(x, 0.02, 20);
        scene.add(line2);
    }
}

// ─── 건물 ──────────────────────────────────────────────────────
function addBuildings(scene) {
    BUILDINGS.forEach(b => {
        // 본체
        const body = new THREE.Mesh(
            new THREE.BoxGeometry(b.w, b.h, b.d),
            new THREE.MeshLambertMaterial({ color: b.color })
        );
        body.position.set(b.x, b.h / 2, b.z);
        body.castShadow = true;
        body.receiveShadow = true;
        scene.add(body);

        // 옥상 테두리 (어두운 띠)
        const rim = new THREE.Mesh(
            new THREE.BoxGeometry(b.w + 0.3, 0.35, b.d + 0.3),
            new THREE.MeshLambertMaterial({ color: 0x2A2A2A })
        );
        rim.position.set(b.x, b.h + 0.175, b.z);
        rim.castShadow = true;
        scene.add(rim);

        // 창문 — 건물 앞면에 얇은 노란 박스 격자
        addWindows(scene, b);
    });
}

function addWindows(scene, b) {
    if (b.h < 4) return;
    const winMat = new THREE.MeshBasicMaterial({ color: 0xFFEE99 });
    const rows = Math.floor(b.h / 2.5);
    const cols = Math.max(1, Math.floor(b.w / 3));

    for (let row = 1; row <= rows; row++) {
        for (let col = 0; col < cols; col++) {
            const wx = b.x - b.w / 2 + (col + 0.5) * (b.w / cols);
            const wy = row * (b.h / (rows + 1));
            // 앞면
            const win = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.7, 0.05), winMat);
            win.position.set(wx, wy, b.z + b.d / 2 + 0.01);
            scene.add(win);
            // 뒷면
            const win2 = win.clone();
            win2.position.set(wx, wy, b.z - b.d / 2 - 0.01);
            scene.add(win2);
        }
    }
}

// ─── 가로등 ────────────────────────────────────────────────────
function addStreetLamps(scene) {
    const poleMat = new THREE.MeshLambertMaterial({ color: 0x888888 });
    const glowMat = new THREE.MeshBasicMaterial({ color: 0xFFFF99 });

    LAMP_POSITIONS.forEach(pos => {
        // 기둥
        const pole = new THREE.Mesh(
            new THREE.CylinderGeometry(0.12, 0.16, 8, 8),
            poleMat
        );
        pole.position.set(pos.x, 4, pos.z);
        pole.castShadow = true;
        scene.add(pole);

        // 가로 팔
        const arm = new THREE.Mesh(
            new THREE.CylinderGeometry(0.06, 0.06, 2.5, 6),
            poleMat
        );
        arm.rotation.z = Math.PI / 2;
        arm.position.set(pos.x + 1.25, 8.1, pos.z);
        scene.add(arm);

        // 등갓 (구)
        const bulb = new THREE.Mesh(
            new THREE.SphereGeometry(0.38, 10, 10),
            glowMat
        );
        bulb.position.set(pos.x + 2.5, 8.0, pos.z);
        scene.add(bulb);

        // 노란 점광원
        const light = new THREE.PointLight(0xFFEE66, 1.8, 30);
        light.position.set(pos.x + 2.5, 7.8, pos.z);
        scene.add(light);
    });
}

// ─── 굴뚝 (공장지대 장식) ─────────────────────────────────────
function addChimneys(scene) {
    const mat = new THREE.MeshLambertMaterial({ color: 0x555555 });
    const topMat = new THREE.MeshLambertMaterial({ color: 0x333333 });

    CHIMNEYS.forEach(c => {
        const body = new THREE.Mesh(
            new THREE.CylinderGeometry(c.r * 0.8, c.r, c.h, 12),
            mat
        );
        body.position.set(c.x, c.h / 2, c.z);
        body.castShadow = true;
        scene.add(body);

        const top = new THREE.Mesh(
            new THREE.CylinderGeometry(c.r, c.r * 0.8, 1, 12),
            topMat
        );
        top.position.set(c.x, c.h + 0.5, c.z);
        scene.add(top);
    });
}
