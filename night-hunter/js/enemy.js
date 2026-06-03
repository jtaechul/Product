// enemy.js — 납치범 AI (5단계)
// 3명의 납치범: 밤에만 출현, 순찰/도망/숨기 패턴

const EnemySystem = window.EnemySystem = {
    enemies: [],
    enemyMeshes: [],
    detectDistance: 8,
    loseDistance: 15,
    alertTimer: 0,

    enemyData: [
        {
            id: 0, name: '길동', color: 0xff3333,
            hideoutX: -70, hideoutZ: 15,
            patrolSpeed: 0.03, fleeSpeed: 0.06,
            hideSpots: [{ x: -75, z: 20 }],
            resistance: 0,
            patrolRadius: 15
        },
        {
            id: 1, name: '철수', color: 0xff8800,
            hideoutX: 70, hideoutZ: 10,
            patrolSpeed: 0.05, fleeSpeed: 0.09,
            hideSpots: [{ x: 65, z: 15 }, { x: 78, z: 5 }, { x: 68, z: 20 }],
            resistance: 1,
            patrolRadius: 20
        },
        {
            id: 2, name: '영수', color: 0x9933ff,
            hideoutX: 10, hideoutZ: -100,
            patrolSpeed: 0.07, fleeSpeed: 0.13,
            hideSpots: [
                { x: 5, z: -95 }, { x: 18, z: -105 }, { x: 0, z: -110 },
                { x: 25, z: -90 }, { x: -10, z: -100 }
            ],
            resistance: 2,
            patrolRadius: 25
        }
    ],

    assets: null,

    init(scene, buildingData) {
        this.scene = scene;
        this.enemies = [];
        this.enemyMeshes = [];
        this.createAlertUI();

        // Randomize hideout positions based on actual hideout buildings
        if (buildingData) {
            const hideouts = buildingData.filter(b => b.type === 'hideout');
            hideouts.forEach(h => {
                const idx = h.hideoutIndex;
                if (idx >= 0 && idx < this.enemyData.length) {
                    this.enemyData[idx].hideoutX = h.x;
                    this.enemyData[idx].hideoutZ = h.z + h.d / 2 + 5; // in front of building
                }
            });
        }

        // Snap all enemy hideouts + hide spots outside any buildings
        this.enemyData.forEach(data => {
            const safe = this._findSafePosition(data.hideoutX, data.hideoutZ);
            data.hideoutX = safe.x;
            data.hideoutZ = safe.z;
            if (Array.isArray(data.hideSpots)) {
                data.hideSpots = data.hideSpots.map(s => this._findSafePosition(s.x, s.z));
            }
        });

        // GLB 자산 로드 후 적 생성 (NPCSystem과 공유). 실패 시 절차적 폴백.
        this._loadAssets().then(() => {
            console.log('[Enemy] GLB 자산 로드 완료');
            this._spawnAll();
        }).catch(err => {
            console.warn('[Enemy] GLB 로드 실패, 절차적 폴백:', err);
            this._spawnAll();
        });
    },

    _spawnAll() {
        this.enemyData.forEach(data => {
            const enemy = this.createEnemy(data);
            this.enemies.push(enemy);
        });
    },

    async _loadAssets() {
        if (this.assets) return this.assets;
        // NPCSystem 자산 재사용 가능하면 그대로
        if (typeof NPCSystem !== 'undefined' && NPCSystem.assets) {
            this.assets = NPCSystem.assets;
            return this.assets;
        }
        const loader = new THREE.GLTFLoader();
        const load = (p) => new Promise((res, rej) => loader.load(p, res, undefined, rej));
        const [npcGltf, idleGltf, walkGltf, runGltf] = await Promise.all([
            load('assets/models/npc-normal.glb'),
            load('assets/models/idle.glb'),
            load('assets/models/walk.glb'),
            load('assets/models/run.glb')
        ]);
        this.assets = {
            template: npcGltf.scene,
            anims: {
                idle: idleGltf.animations[0],
                walk: walkGltf.animations[0],
                run: runGltf.animations[0]
            }
        };
        return this.assets;
    },

    _createGLBEnemyMesh(data) {
        if (!THREE.SkeletonUtils) return null;
        const mesh = THREE.SkeletonUtils.clone(this.assets.template);
        // 범인 색상으로 머티리얼 틴팅 (옷처럼 보이도록)
        mesh.traverse(o => {
            if (o.isMesh) {
                const m = o.material.clone();
                m.color.setHex(data.color);
                o.material = m;
                o.castShadow = true;
                o.receiveShadow = true;
            }
        });
        mesh.scale.setScalar(3.0); // NPC(2.8)보다 약간 크게 — 위협감
        // Mixer
        const mixer = new THREE.AnimationMixer(mesh);
        const actions = {
            idle: mixer.clipAction(this.assets.anims.idle),
            walk: mixer.clipAction(this.assets.anims.walk),
            run: mixer.clipAction(this.assets.anims.run)
        };
        actions.idle.play();
        mesh.userData.mixer = mixer;
        mesh.userData.actions = actions;
        mesh.userData.animState = 'idle';
        return mesh;
    },

    _setAnimState(mesh, state) {
        if (!mesh.userData.actions) return;
        if (mesh.userData.animState === state) return;
        const oldAction = mesh.userData.actions[mesh.userData.animState];
        const newAction = mesh.userData.actions[state];
        if (oldAction) oldAction.fadeOut(0.2);
        newAction.reset().fadeIn(0.2).play();
        mesh.userData.animState = state;
    },

    _createAlertSprite() {
        const c = document.createElement('canvas');
        c.width = c.height = 64;
        const ctx = c.getContext('2d');
        ctx.fillStyle = 'rgba(255,68,68,0.95)';
        ctx.beginPath();
        ctx.arc(32, 32, 28, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 56px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('!', 32, 32);
        const tex = new THREE.CanvasTexture(c);
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
        sprite.scale.set(1.0, 1.0, 1);
        return sprite;
    },

    _findSafePosition(x, z) {
        if (!window._buildingPositions) return { x, z };
        let cx = x, cz = z;
        for (let pass = 0; pass < 6; pass++) {
            const inside = window._buildingPositions.find(b =>
                Math.abs(cx - b.x) < b.w / 2 + 0.8 && Math.abs(cz - b.z) < b.d / 2 + 0.8
            );
            if (!inside) return { x: cx, z: cz };
            const dx = cx - inside.x;
            const dz = cz - inside.z;
            if (Math.abs(dx) >= Math.abs(dz)) {
                cx = inside.x + (dx >= 0 ? 1 : -1) * (inside.w / 2 + 2.5);
            } else {
                cz = inside.z + (dz >= 0 ? 1 : -1) * (inside.d / 2 + 2.5);
            }
        }
        return { x: cx, z: cz };
    },

    createEnemy(data) {
        // GLB 우선
        if (this.assets) {
            const glbMesh = this._createGLBEnemyMesh(data);
            if (glbMesh) {
                glbMesh.position.set(data.hideoutX, 0, data.hideoutZ);
                this.scene.add(glbMesh);
                // 경보 스프라이트 추가
                const alertSprite = this._createAlertSprite();
                alertSprite.position.set(0, 4, 0);
                alertSprite.visible = false;
                glbMesh.add(alertSprite);
                return {
                    mesh: glbMesh, data,
                    state: 'hidden', stateTimer: 0,
                    currentX: data.hideoutX, currentZ: data.hideoutZ,
                    patrolTarget: { x: data.hideoutX, z: data.hideoutZ },
                    hideTarget: null, hideSpots: data.hideSpots || [],
                    walkTime: 0, contactTimer: 0,
                    alertSprite, _isGLB: true
                };
            }
        }
        const group = new THREE.Group();
        const bodyMat = new THREE.MeshStandardMaterial({ color: data.color, roughness: 0.85 });
        const blackMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.9 });

        // Articulated legs (hip groups for animation)
        const leftHip = new THREE.Group();
        leftHip.position.set(-0.1, 0.6, 0);
        const lThigh = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.08, 0.32, 10), blackMat);
        lThigh.position.y = -0.16; lThigh.castShadow = true;
        leftHip.add(lThigh);
        const lShin = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.07, 0.32, 10), blackMat);
        lShin.position.y = -0.48; lShin.castShadow = true;
        leftHip.add(lShin);
        const lShoe = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.1, 0.3), blackMat);
        lShoe.position.set(0, -0.66, 0.05); lShoe.castShadow = true;
        leftHip.add(lShoe);
        leftHip.userData.partName = 'leftLeg';
        group.add(leftHip);

        const rightHip = leftHip.clone(true);
        rightHip.position.set(0.1, 0.6, 0);
        rightHip.userData.partName = 'rightLeg';
        group.add(rightHip);

        // Torso (hoodie)
        const torso = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.7, 0.32), bodyMat);
        torso.position.y = 0.95;
        torso.castShadow = true;
        group.add(torso);

        // Articulated arms
        const leftShoulder = new THREE.Group();
        leftShoulder.position.set(-0.32, 1.2, 0);
        const lUpperArm = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.06, 0.3, 10), bodyMat);
        lUpperArm.position.y = -0.15; lUpperArm.castShadow = true;
        leftShoulder.add(lUpperArm);
        const lForearm = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.05, 0.3, 10), bodyMat);
        lForearm.position.y = -0.45; lForearm.castShadow = true;
        leftShoulder.add(lForearm);
        const lHand = new THREE.Mesh(new THREE.SphereGeometry(0.07, 12, 12), new THREE.MeshStandardMaterial({ color: 0xddbb99 }));
        lHand.position.y = -0.6;
        leftShoulder.add(lHand);
        leftShoulder.userData.partName = 'leftArm';
        group.add(leftShoulder);

        const rightShoulder = leftShoulder.clone(true);
        rightShoulder.position.set(0.32, 1.2, 0);
        rightShoulder.userData.partName = 'rightArm';
        group.add(rightShoulder);

        // Head with hood
        const head = new THREE.Mesh(
            new THREE.SphereGeometry(0.2, 20, 20),
            new THREE.MeshStandardMaterial({ color: 0xddbb99, roughness: 0.6 })
        );
        head.position.y = 1.5;
        head.castShadow = true;
        group.add(head);

        // Hood (hooded sweatshirt)
        const hood = new THREE.Mesh(
            new THREE.SphereGeometry(0.24, 20, 20, 0, Math.PI * 2, 0, Math.PI * 0.65),
            blackMat
        );
        hood.position.y = 1.55;
        group.add(hood);

        // Detailed face — eye sockets, brows, nose, scar (per criminal)
        const skinDark = new THREE.MeshStandardMaterial({ color: 0xc09875, roughness: 0.7 });
        const browMat = new THREE.MeshStandardMaterial({ color: 0x1a0e08, roughness: 0.6 });

        // Eye sockets (deeper, shadowed)
        const lSocket = new THREE.Mesh(new THREE.SphereGeometry(0.045, 12, 12), skinDark);
        lSocket.position.set(-0.07, 1.51, 0.16); lSocket.scale.set(1, 0.7, 0.4);
        group.add(lSocket);
        const rSocket = lSocket.clone();
        rSocket.position.set(0.07, 1.51, 0.16);
        group.add(rSocket);

        // Glowing red eyes (smaller, more menacing)
        const eyeMat = new THREE.MeshStandardMaterial({ color: 0xff2222, emissive: 0xff0000, emissiveIntensity: 1.0 });
        const leftEye = new THREE.Mesh(new THREE.SphereGeometry(0.022, 12, 12), eyeMat);
        leftEye.position.set(-0.07, 1.5, 0.185);
        group.add(leftEye);
        const rightEye = new THREE.Mesh(new THREE.SphereGeometry(0.022, 12, 12), eyeMat);
        rightEye.position.set(0.07, 1.5, 0.185);
        group.add(rightEye);

        // Angled eyebrows (angry)
        const lBrow = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.018, 0.015), browMat);
        lBrow.position.set(-0.07, 1.555, 0.18);
        lBrow.rotation.z = -0.25;
        group.add(lBrow);
        const rBrow = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.018, 0.015), browMat);
        rBrow.position.set(0.07, 1.555, 0.18);
        rBrow.rotation.z = 0.25;
        group.add(rBrow);

        // Nose (small triangular)
        const nose = new THREE.Mesh(
            new THREE.ConeGeometry(0.022, 0.06, 6),
            new THREE.MeshStandardMaterial({ color: 0xc09875, roughness: 0.7 })
        );
        nose.rotation.x = Math.PI / 2;
        nose.position.set(0, 1.46, 0.205);
        group.add(nose);

        // Scar on cheek (criminal-specific marker)
        if (data.id === 1) {
            // 2호 철수: 얼굴 흉터
            const scar = new THREE.Mesh(
                new THREE.BoxGeometry(0.008, 0.06, 0.005),
                new THREE.MeshStandardMaterial({ color: 0x8b2020, roughness: 0.5 })
            );
            scar.position.set(0.1, 1.45, 0.18);
            scar.rotation.z = -0.5;
            group.add(scar);
        }
        if (data.id === 2) {
            // 3호 영수: 눈 위 흉터
            const scar = new THREE.Mesh(
                new THREE.BoxGeometry(0.012, 0.05, 0.005),
                new THREE.MeshStandardMaterial({ color: 0x8b2020, roughness: 0.5 })
            );
            scar.position.set(-0.08, 1.58, 0.18);
            scar.rotation.z = 0.3;
            group.add(scar);
        }

        // Stubble/beard (1호: clean, 2호: slight, 3호: heavy)
        if (data.id >= 1) {
            const stubble = new THREE.Mesh(
                new THREE.SphereGeometry(0.16, 16, 16, 0, Math.PI * 2, Math.PI * 0.55, Math.PI * 0.4),
                new THREE.MeshStandardMaterial({ color: 0x2a1d10, roughness: 0.9, transparent: true, opacity: data.id === 2 ? 0.8 : 0.5 })
            );
            stubble.position.y = 1.5;
            group.add(stubble);
        }

        // Cheekbones (subtle shadow)
        const lCheek = new THREE.Mesh(new THREE.SphereGeometry(0.04, 10, 10), skinDark);
        lCheek.position.set(-0.13, 1.46, 0.13); lCheek.scale.set(1, 0.7, 0.3);
        group.add(lCheek);
        const rCheek = lCheek.clone();
        rCheek.position.set(0.13, 1.46, 0.13);
        group.add(rCheek);

        // Mask (black bandana over mouth)
        const mask = new THREE.Mesh(
            new THREE.BoxGeometry(0.22, 0.1, 0.05),
            blackMat
        );
        mask.position.set(0, 1.4, 0.16);
        group.add(mask);

        // "!" alert sprite (hidden by default)
        const alertCanvas = document.createElement('canvas');
        alertCanvas.width = 64;
        alertCanvas.height = 64;
        const actx = alertCanvas.getContext('2d');
        actx.fillStyle = '#ff0000';
        actx.font = 'bold 56px Inter, sans-serif';
        actx.textAlign = 'center';
        actx.textBaseline = 'middle';
        actx.fillText('!', 32, 32);
        const alertTexture = new THREE.CanvasTexture(alertCanvas);
        const alertSprite = new THREE.Sprite(
            new THREE.SpriteMaterial({ map: alertTexture, transparent: true })
        );
        alertSprite.scale.set(0.8, 0.8, 1);
        alertSprite.position.y = 2.3;
        alertSprite.visible = false;
        group.add(alertSprite);

        group.position.set(data.hideoutX, 0, data.hideoutZ);
        group.visible = false;
        this.scene.add(group);
        this.enemyMeshes.push(group);

        return {
            ...data,
            mesh: group,
            alertSprite,
            state: 'hidden',    // hidden, patrol, flee, hiding
            arrested: false,
            walkTime: 0,
            patrolTarget: null,
            hideTarget: null,
            stateTimer: 0,
            currentX: data.hideoutX,
            currentZ: data.hideoutZ
        };
    },

    createAlertUI() {
        const alertBar = document.createElement('div');
        alertBar.id = 'enemy-alert';
        alertBar.style.cssText = `
            display: none;
            position: fixed;
            top: 60px; left: 50%;
            transform: translateX(-50%);
            background: rgba(200,0,0,0.7);
            backdrop-filter: blur(4px);
            padding: 6px 18px;
            border-radius: 20px;
            border: 1px solid rgba(255,0,0,0.5);
            font-size: 14px;
            font-weight: 700;
            color: #fff;
            z-index: 25;
            animation: fadeIn 0.3s ease;
        `;
        document.body.appendChild(alertBar);
    },

    update(playerPos, delta, time) {
        if (gameState.isDay && !DayNight.isTransitioning) {
            this.enemies.forEach(e => {
                if (!e.arrested) {
                    e.mesh.visible = false;
                    e.state = 'hidden';
                    e.mesh.position.set(e.hideoutX, 0, e.hideoutZ);
                    e.currentX = e.hideoutX;
                    e.currentZ = e.hideoutZ;
                }
            });
            document.getElementById('enemy-alert').style.display = 'none';
            return;
        }

        let anyVisible = false;

        this.enemies.forEach(enemy => {
            if (enemy.arrested) {
                enemy.mesh.visible = false;
                return;
            }

            // Only appear at night IF all hints for this criminal are collected
            const revealed = HintSystem.hasAllHintsFor(enemy.id);
            if (!revealed) {
                enemy.mesh.visible = false;
                enemy.state = 'hidden';
                return;
            }

            if (!gameState.isDay) {
                if (enemy.state === 'hidden') {
                    enemy.state = 'patrol';
                    enemy.mesh.visible = true;
                    enemy.patrolTarget = this.getPatrolTarget(enemy);
                }
            }

            if (enemy.state === 'hidden') return;

            enemy.mesh.visible = true;
            const dx = playerPos.x - enemy.currentX;
            const dz = playerPos.z - enemy.currentZ;
            const dist = Math.sqrt(dx * dx + dz * dz);

            // Check if on screen
            const screenPos = enemy.mesh.position.clone().project(camera);
            const onScreen = Math.abs(screenPos.x) < 1.2 && Math.abs(screenPos.y) < 1.2 && screenPos.z < 1;

            if (onScreen && dist < 40) {
                anyVisible = true;
            }

            switch (enemy.state) {
                case 'patrol':
                    this.updatePatrol(enemy, delta, time);
                    if (dist < this.detectDistance) {
                        enemy.state = 'flee';
                        enemy.alertSprite.visible = true;
                        enemy.stateTimer = 0;
                    }
                    break;

                case 'flee':
                    this.updateFlee(enemy, playerPos, delta, time);
                    enemy.stateTimer += delta;
                    if (dist > this.loseDistance) {
                        if (enemy.hideSpots.length > 0 && Math.random() < 0.5) {
                            enemy.state = 'hiding';
                            enemy.hideTarget = enemy.hideSpots[
                                Math.floor(Math.random() * enemy.hideSpots.length)
                            ];
                            enemy.stateTimer = 0;
                        } else {
                            enemy.state = 'patrol';
                            enemy.patrolTarget = this.getPatrolTarget(enemy);
                            enemy.alertSprite.visible = false;
                        }
                    }
                    break;

                case 'hiding':
                    this.updateHiding(enemy, playerPos, delta, time);
                    enemy.stateTimer += delta;
                    if (enemy.stateTimer > 8) {
                        enemy.state = 'patrol';
                        enemy.patrolTarget = this.getPatrolTarget(enemy);
                        enemy.alertSprite.visible = false;
                    }
                    if (dist < this.detectDistance) {
                        enemy.state = 'flee';
                        enemy.alertSprite.visible = true;
                        enemy.stateTimer = 0;
                    }
                    break;
            }

            // GLB 애니메이션 상태 + mixer 진행
            if (enemy.mesh.userData.mixer) {
                enemy.mesh.userData.mixer.update(delta);
                const animState =
                    enemy.state === 'flee'   ? 'run' :
                    enemy.state === 'patrol' ? 'walk' :
                                               'idle';
                this._setAnimState(enemy.mesh, animState);
            }

            // 절차적 폴백 swing
            if (enemy.state === 'patrol' || enemy.state === 'flee') {
                enemy.walkTime += delta * (enemy.state === 'flee' ? 12 : 6);
                const swing = Math.sin(enemy.walkTime) * 0.3;
                enemy.mesh.children.forEach(child => {
                    if (child.userData.partName === 'leftLeg') child.rotation.x = swing;
                    if (child.userData.partName === 'rightLeg') child.rotation.x = -swing;
                    if (child.userData.partName === 'leftArm') child.rotation.x = -swing;
                    if (child.userData.partName === 'rightArm') child.rotation.x = swing;
                });
            }

            enemy.mesh.position.set(enemy.currentX, 0, enemy.currentZ);

            // Contact damage
            if (dist < 1.2 && !Minigame.active) {
                enemy.contactTimer = (enemy.contactTimer || 0) + delta;
                if (enemy.contactTimer > 0.5) {
                    const dmg = (typeof Shop !== 'undefined' && Shop.hasItem('vest')) ? 0.25 : 0.5;
                    gameState.health = Math.max(0, gameState.health - dmg);
                    enemy.contactTimer = 0;
                }
            } else {
                enemy.contactTimer = 0;
            }
        });

        // Alert bar
        const alertEl = document.getElementById('enemy-alert');
        if (anyVisible) {
            alertEl.style.display = 'block';
            alertEl.textContent = '⚠️ 납치범 발견!';
        } else {
            alertEl.style.display = 'none';
        }
    },

    _collidesWithBuilding(x, z, enemyHideoutIdx) {
        if (!window._buildingPositions) return false;
        const r = 0.4;
        for (const b of window._buildingPositions) {
            if (b.hideoutIndex === enemyHideoutIdx) continue; // pass through own hideout
            if (Math.abs(x - b.x) < b.w / 2 + r && Math.abs(z - b.z) < b.d / 2 + r) return true;
        }
        return false;
    },

    _tryMoveEnemy(enemy, dx, dz) {
        const nx = enemy.currentX + dx;
        const nz = enemy.currentZ + dz;
        const half = WORLD_SIZE / 2 - 2;
        const cx = Math.max(-half, Math.min(half, nx));
        const cz = Math.max(-half, Math.min(half, nz));
        const idx = enemy.id;
        if (!this._collidesWithBuilding(cx, cz, idx)) {
            enemy.currentX = cx; enemy.currentZ = cz;
        } else if (!this._collidesWithBuilding(cx, enemy.currentZ, idx)) {
            enemy.currentX = cx;
        } else if (!this._collidesWithBuilding(enemy.currentX, cz, idx)) {
            enemy.currentZ = cz;
        }
    },

    updatePatrol(enemy, delta, time) {
        if (!enemy.patrolTarget) {
            enemy.patrolTarget = this.getPatrolTarget(enemy);
        }

        const tx = enemy.patrolTarget.x;
        const tz = enemy.patrolTarget.z;
        const dx = tx - enemy.currentX;
        const dz = tz - enemy.currentZ;
        const dist = Math.sqrt(dx * dx + dz * dz);

        if (dist < 1) {
            enemy.patrolTarget = this.getPatrolTarget(enemy);
            return;
        }

        const speed = enemy.patrolSpeed * delta * 60;
        this._tryMoveEnemy(enemy, (dx / dist) * speed, (dz / dist) * speed);

        const angle = Math.atan2(dx, dz);
        enemy.mesh.rotation.y = angle;
        enemy.alertSprite.visible = false;
    },

    updateFlee(enemy, playerPos, delta, time) {
        const dx = enemy.currentX - playerPos.x;
        const dz = enemy.currentZ - playerPos.z;
        const dist = Math.sqrt(dx * dx + dz * dz);

        if (dist > 0) {
            const speed = enemy.fleeSpeed * delta * 60;
            this._tryMoveEnemy(enemy, (dx / dist) * speed, (dz / dist) * speed);

            const angle = Math.atan2(dx, dz);
            enemy.mesh.rotation.y = angle;
        }

        // Blinking alert
        enemy.alertSprite.visible = Math.sin(time * 10) > 0;
    },

    updateHiding(enemy, playerPos, delta, time) {
        if (!enemy.hideTarget) return;

        const tx = enemy.hideTarget.x;
        const tz = enemy.hideTarget.z;
        const dx = tx - enemy.currentX;
        const dz = tz - enemy.currentZ;
        const dist = Math.sqrt(dx * dx + dz * dz);

        if (dist > 1) {
            const speed = enemy.fleeSpeed * 0.7 * delta * 60;
            this._tryMoveEnemy(enemy, (dx / dist) * speed, (dz / dist) * speed);
            const angle = Math.atan2(dx, dz);
            enemy.mesh.rotation.y = angle;
        }

        // Pulsing opacity when hiding
        enemy.mesh.children.forEach(child => {
            if (child.material && !child.isSprite) {
                child.material.transparent = true;
                child.material.opacity = 0.5 + Math.sin(time * 4) * 0.2;
            }
        });
        enemy.alertSprite.visible = false;
    },

    getPatrolTarget(enemy) {
        // Try up to 8 random points; pick first that is not inside any building.
        for (let i = 0; i < 8; i++) {
            const angle = Math.random() * Math.PI * 2;
            const r = Math.random() * enemy.patrolRadius;
            const tx = enemy.hideoutX + Math.cos(angle) * r;
            const tz = enemy.hideoutZ + Math.sin(angle) * r;
            if (!this._collidesWithBuilding(tx, tz, enemy.id)) {
                return { x: tx, z: tz };
            }
        }
        // Fallback: snap any random point to safe position
        const angle = Math.random() * Math.PI * 2;
        const r = Math.random() * enemy.patrolRadius;
        return this._findSafePosition(
            enemy.hideoutX + Math.cos(angle) * r,
            enemy.hideoutZ + Math.sin(angle) * r
        );
    },

    getDistanceToPlayer(enemyIndex, playerPos) {
        const e = this.enemies[enemyIndex];
        if (!e || e.arrested) return Infinity;
        const dx = playerPos.x - e.currentX;
        const dz = playerPos.z - e.currentZ;
        return Math.sqrt(dx * dx + dz * dz);
    },

    getNearestEnemy(playerPos) {
        let nearest = null;
        let minDist = Infinity;
        this.enemies.forEach(e => {
            if (e.arrested || e.state === 'hidden') return;
            const dx = playerPos.x - e.currentX;
            const dz = playerPos.z - e.currentZ;
            const dist = Math.sqrt(dx * dx + dz * dz);
            if (dist < minDist) {
                minDist = dist;
                nearest = e;
            }
        });
        return { enemy: nearest, distance: minDist };
    },

    markRevealed(criminalId) {
        // No-op marker — visibility now driven by HintSystem.hasAllHintsFor()
        // Could be used for additional effects in future
    },

    arrestEnemy(enemy) {
        enemy.arrested = true;
        enemy.mesh.visible = false;
        enemy.state = 'hidden';
        this.scene.remove(enemy.mesh);
        gameState.arrests++;
        gameState.coins += 50;
    },

    reset() {
        this.enemies.forEach(e => {
            if (e.mesh.parent) this.scene.remove(e.mesh);
        });
        this.enemies = [];
        this.enemyMeshes = [];
    }
};
