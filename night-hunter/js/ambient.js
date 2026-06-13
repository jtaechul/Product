// ambient.js — 자동차 + 보행자 (시민) 동적 시스템

const AmbientCity = window.AmbientCity = {
    cars: [],
    walkers: [],
    scene: null,
    initialized: false,

    init(scene) {
        this.scene = scene;
        this.spawnInitialCars();
        this.spawnInitialWalkers();
        this.initialized = true;
    },

    // Spawn cars on main roads at random positions, moving along the road
    // 실제 MAIN_ROADS 좌표만 사용 — 자동차가 도로 위만 다님 (task 3)
    spawnInitialCars() {
        const Q = window.GameQuality?.cfg || {};
        const carCount = Q.carCount || 8;
        // 실제 도로 좌표 (world.js MAIN_ROADS 와 일치)
        // H 도로: 차선 폭이 큰 도로만 사용 (perimeter 제외 — 자동차가 너무 가장자리에 몰리지 않게)
        const roads = [
            { type: 'H', z: 55,  xMin: -140, xMax: 140 },   // 경찰서 정면
            { type: 'H', z: 5,   xMin: -140, xMax: 140 },   // R/C divider
            { type: 'H', z: -45, xMin: -140, xMax: 0   },   // 주거 내부 (offsetX=-70, length=146)
            { type: 'H', z: -90, xMin: -140, xMax: 140 },   // 상업/공업 경계
            { type: 'H', z: -115, xMin: -140, xMax: 140 },  // 공업 내부 (신규)
            { type: 'V', x: -50, zMin: -90, zMax: 5    },   // 주거 V 도로
            { type: 'V', x: 100, zMin: 5,   zMax: 85   },   // 경찰지구 V
        ].slice(0, carCount);
        const carColors = [0xcc1a1a, 0x1a44cc, 0xdddddd, 0x111111, 0xffcc00, 0x22aa44, 0x884488, 0xee9933];
        roads.forEach((road, i) => {
            const dir = Math.random() < 0.5 ? -1 : 1;
            const color = carColors[i % carColors.length];
            const car = this.makeCar(color);
            if (road.type === 'H') {
                const startX = road.xMin + Math.random() * (road.xMax - road.xMin);
                car.mesh.position.set(startX, 0, road.z + (dir > 0 ? -1.8 : 1.8));
                car.mesh.rotation.y = dir > 0 ? Math.PI / 2 : -Math.PI / 2;
                car.road = road; car.dir = dir; car.speed = 4 + Math.random() * 3;
            } else {
                const startZ = road.zMin + Math.random() * (road.zMax - road.zMin);
                car.mesh.position.set(road.x + (dir > 0 ? -1.8 : 1.8), 0, startZ);
                car.mesh.rotation.y = dir > 0 ? 0 : Math.PI;
                car.road = road; car.dir = dir; car.speed = 4 + Math.random() * 3;
            }
            this.cars.push(car);
        });
    },

    makeCar(color) {
        const group = new THREE.Group();
        const bodyMat = new THREE.MeshStandardMaterial({ color, roughness: 0.4, metalness: 0.5 });
        const glassMat = new THREE.MeshStandardMaterial({ color: 0x222233, roughness: 0.2, metalness: 0.3, transparent: true, opacity: 0.7 });
        const wheelMat = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.8 });

        // Body
        const body = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.6, 3.6), bodyMat);
        body.position.y = 0.55;
        body.castShadow = true;
        group.add(body);

        // Roof/cabin (smaller box on top)
        const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.55, 2.0), bodyMat);
        cabin.position.set(0, 1.1, -0.1);
        cabin.castShadow = true;
        group.add(cabin);

        // Windshield (front)
        const ws = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.45, 0.08), glassMat);
        ws.position.set(0, 1.05, 0.9);
        ws.rotation.x = -0.3;
        group.add(ws);

        // Rear window
        const rw = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.45, 0.08), glassMat);
        rw.position.set(0, 1.05, -1.1);
        rw.rotation.x = 0.3;
        group.add(rw);

        // Wheels
        const wheelPos = [[-0.75, 0.3, 1.2], [0.75, 0.3, 1.2], [-0.75, 0.3, -1.2], [0.75, 0.3, -1.2]];
        wheelPos.forEach(([wx, wy, wz]) => {
            const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.18, 14), wheelMat);
            wheel.rotation.z = Math.PI / 2;
            wheel.position.set(wx, wy, wz);
            wheel.castShadow = true;
            group.add(wheel);
        });

        // Headlights — emissive material updated dynamically (brighter at night)
        const hlMat = new THREE.MeshStandardMaterial({ color: 0xffffcc, emissive: 0xffffcc, emissiveIntensity: 0.4 });
        const hl1 = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 8), hlMat);
        hl1.position.set(-0.55, 0.55, 1.8);
        group.add(hl1);
        const hl2 = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 8), hlMat);
        hl2.position.set(0.55, 0.55, 1.8);
        group.add(hl2);

        // Taillights — emissive material updated dynamically
        const tlMat = new THREE.MeshStandardMaterial({ color: 0xff2222, emissive: 0xff2222, emissiveIntensity: 0.5 });
        const tl1 = new THREE.Mesh(new THREE.SphereGeometry(0.1, 8, 8), tlMat);
        tl1.position.set(-0.6, 0.55, -1.8);
        group.add(tl1);
        const tl2 = new THREE.Mesh(new THREE.SphereGeometry(0.1, 8, 8), tlMat);
        tl2.position.set(0.6, 0.55, -1.8);
        group.add(tl2);

        this.scene.add(group);
        return { mesh: group, hlMat, tlMat };
    },

    spawnInitialWalkers() {
        // Spawn pedestrians on sidewalks (near roads, walking along)
        const Q = window.GameQuality?.cfg || {};
        const walkerCount = Q.walkerCount || 10;
        const sidewalkSpots = [
            [-90, 56], [-30, 56], [30, 56], [90, 56],
            [-90, 11], [-30, 11], [30, 11], [90, 11],
            [-60, -39], [60, -39],
        ].slice(0, walkerCount);
        sidewalkSpots.forEach(([x, z], i) => {
            const walker = this.makeWalker();
            walker.mesh.position.set(x, 0, z);
            walker.baseX = x; walker.baseZ = z;
            walker.t = Math.random() * 10;
            walker.target = { x: x + (Math.random() - 0.5) * 20, z };
            walker.meshName = (i % 2 === 0) ? 'npc-man' : 'woman';  // 보행자 GLB 모델 (남/녀 교대)
            this.walkers.push(walker);
        });
    },

    // 보행자를 GLB 모델로 교체 (절차적 보행자 방지)
    _upgradeWalker(w) {
        if (!w || w._glb) return;
        if (typeof ChibiCharacter === 'undefined' || !ChibiCharacter.upgradeHost) return;
        const inst = ChibiCharacter.upgradeHost(w.mesh, w.meshName);
        if (inst) { w._glb = inst; w._glbState = null; }
    },

    makeWalker() {
        const group = new THREE.Group();
        const shirtColor = [0x4a5568, 0xb8753a, 0x84a8c4, 0xd4a3a3, 0x9b8b9d, 0x8b9aa8][Math.floor(Math.random()*6)];
        const pantColor = [0x222244, 0x4a3520, 0x333333, 0x556677][Math.floor(Math.random()*4)];
        const skinMat = new THREE.MeshStandardMaterial({ color: 0xffdbac, roughness: 0.6 });
        const shirtMat = new THREE.MeshStandardMaterial({ color: shirtColor, roughness: 0.85 });
        const pantMat = new THREE.MeshStandardMaterial({ color: pantColor, roughness: 0.75 });

        // Articulated legs
        function makeLeg(side) {
            const hip = new THREE.Group();
            hip.position.set(side * 0.1, 0.55, 0);
            const thigh = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.07, 0.28, 10), pantMat);
            thigh.position.y = -0.14; thigh.castShadow = true;
            hip.add(thigh);
            const shin = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.06, 0.28, 10), pantMat);
            shin.position.y = -0.42; shin.castShadow = true;
            hip.add(shin);
            const shoe = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.08, 0.22), new THREE.MeshStandardMaterial({ color: 0x111111 }));
            shoe.position.set(0, -0.6, 0.04); shoe.castShadow = true;
            hip.add(shoe);
            return hip;
        }
        const lh = makeLeg(-1); lh.userData.partName = 'wLeftHip'; group.add(lh);
        const rh = makeLeg(1);  rh.userData.partName = 'wRightHip'; group.add(rh);

        // Torso
        const torso = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.5, 0.22), shirtMat);
        torso.position.y = 0.85; torso.castShadow = true;
        group.add(torso);

        // Arms
        function makeArm(side) {
            const sh = new THREE.Group();
            sh.position.set(side * 0.25, 1.05, 0);
            const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.05, 0.45, 10), shirtMat);
            upper.position.y = -0.22; upper.castShadow = true;
            sh.add(upper);
            const hand = new THREE.Mesh(new THREE.SphereGeometry(0.06, 10, 10), skinMat);
            hand.position.y = -0.48;
            sh.add(hand);
            return sh;
        }
        const ls = makeArm(-1); ls.userData.partName = 'wLeftShoulder'; group.add(ls);
        const rs = makeArm(1);  rs.userData.partName = 'wRightShoulder'; group.add(rs);

        // Head
        const head = new THREE.Mesh(new THREE.SphereGeometry(0.18, 16, 16), skinMat);
        head.position.y = 1.32; head.castShadow = true;
        group.add(head);

        // Hair
        const hair = new THREE.Mesh(
            new THREE.SphereGeometry(0.185, 16, 16, 0, Math.PI*2, 0, Math.PI*0.55),
            new THREE.MeshStandardMaterial({ color: [0x1a0a00, 0x4a2510, 0x664422][Math.floor(Math.random()*3)] })
        );
        hair.position.y = 1.34;
        group.add(hair);

        this.scene.add(group);
        return { mesh: group, leftHip: lh, rightHip: rh, leftShoulder: ls, rightShoulder: rs };
    },

    update(delta, time, playerPos) {
        const isNight = typeof gameState !== 'undefined' && !gameState.isDay;

        // 자동차는 낮/밤 모두 표시 + 주행 (밤엔 헤드라이트가 더 강조됨)
        this.cars.forEach(c => {
            c.mesh.visible = true;
            if (c.hlMat) c.hlMat.emissiveIntensity = isNight ? 2.2 : 0.4;
            if (c.tlMat) c.tlMat.emissiveIntensity = isNight ? 1.6 : 0.5;
        });

        // 보행자는 낮에만 (밤엔 안전상 귀가) + 거리 컬링 (모바일 과부하 방지)
        const CULL = (window.GameQuality && window.GameQuality.cfg && window.GameQuality.cfg.fogFar) ? window.GameQuality.cfg.fogFar * 0.6 : 70;
        const CULL_SQ = CULL * CULL;
        this.walkers.forEach(w => {
            let vis = !isNight;
            if (vis && playerPos) {
                const dx = playerPos.x - w.mesh.position.x, dz = playerPos.z - w.mesh.position.z;
                if (dx * dx + dz * dz > CULL_SQ) vis = false;
            }
            w.mesh.visible = vis;
        });

        // === 자동차 주행 — 각 도로의 실제 좌표 범위 내에서 순환 (task 3) ===
        this.cars.forEach(car => {
            const dist = car.speed * delta;
            const r = car.road;
            if (r.type === 'H') {
                car.mesh.position.x += car.dir * dist;
                const xMin = r.xMin !== undefined ? r.xMin : -140;
                const xMax = r.xMax !== undefined ? r.xMax : 140;
                if (car.mesh.position.x > xMax) car.mesh.position.x = xMin;
                if (car.mesh.position.x < xMin) car.mesh.position.x = xMax;
            } else {
                car.mesh.position.z += car.dir * dist;
                const zMin = r.zMin !== undefined ? r.zMin : -140;
                const zMax = r.zMax !== undefined ? r.zMax : 140;
                if (car.mesh.position.z > zMax) car.mesh.position.z = zMin;
                if (car.mesh.position.z < zMin) car.mesh.position.z = zMax;
            }
        });

        // 밤이면 보행자 업데이트 건너뜀
        if (isNight) return;

        // === 보행자 업데이트 (낮에만) — 도로(asphalt) 회피 ===
        const onRoad = (x, z) => typeof window.isOnRoadAsphalt === 'function'
            && window.isOnRoadAsphalt(x, z, 0.3);
        this.walkers.forEach(w => {
            // GLB는 가까이 올 때만 생성 (생성 스파이크 방지)
            if (!w._glb && playerPos) {
                const gdx = playerPos.x - w.mesh.position.x, gdz = playerPos.z - w.mesh.position.z;
                if (gdx * gdx + gdz * gdz <= CULL_SQ) this._upgradeWalker(w);
            }
            let walkerMoved = false;
            w.t += delta;
            const tdx = w.target.x - w.mesh.position.x;
            const tdz = w.target.z - w.mesh.position.z;
            const td = Math.sqrt(tdx * tdx + tdz * tdz);
            if (td < 0.5 || w.t > 8) {
                // 새 target 선택 — 도로 위 target 은 피해서 재시도 (10회)
                let tx, tz;
                for (let i = 0; i < 10; i++) {
                    tx = w.baseX + (Math.random() - 0.5) * 30;
                    tz = w.baseZ + (Math.random() - 0.5) * 2;
                    if (!onRoad(tx, tz)) break;
                }
                w.target = { x: tx, z: tz };
                w.t = 0;
            } else {
                const speed = 0.6 * delta;
                const nx = w.mesh.position.x + (tdx / td) * speed;
                const nz = w.mesh.position.z + (tdz / td) * speed;
                // 도로 위로 들어가려 하면 target 폐기, 다음 프레임 새 target 선택
                if (onRoad(nx, nz)) {
                    w.t = 8;  // 즉시 target 재선정 트리거
                } else {
                    w.mesh.position.x = nx;
                    w.mesh.position.z = nz;
                    w.mesh.rotation.y = Math.atan2(tdx, tdz);
                    walkerMoved = true;
                    const swing = Math.sin(time * 4.5) * 0.45;
                    if (w.leftHip) w.leftHip.rotation.x = swing;
                    if (w.rightHip) w.rightHip.rotation.x = -swing;
                    if (w.leftShoulder) w.leftShoulder.rotation.x = -swing * 0.6;
                    if (w.rightShoulder) w.rightShoulder.rotation.x = swing * 0.6;
                }
            }
            // GLB 보행자 애니메이션 구동
            if (w._glb) {
                const st = walkerMoved ? 'walk' : 'idle';
                if (st !== w._glbState) { try { w._glb.setState(st); } catch (e) {} w._glbState = st; }
                if (w.mesh.visible) { try { w._glb.update(delta); } catch (e) {} }
            }
        });
    }
};
