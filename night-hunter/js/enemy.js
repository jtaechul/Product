// enemy.js — 납치범 AI (5단계)
// 3명의 납치범: 밤에만 출현, 순찰/도망/숨기 패턴

const EnemySystem = {
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

        this.enemyData.forEach(data => {
            const enemy = this.createEnemy(data);
            this.enemies.push(enemy);
        });
    },

    createEnemy(data) {
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

        // Menacing red eyes
        const eyeMat = new THREE.MeshStandardMaterial({ color: 0xff2222, emissive: 0xff0000, emissiveIntensity: 0.8 });
        const leftEye = new THREE.Mesh(new THREE.SphereGeometry(0.025, 10, 10), eyeMat);
        leftEye.position.set(-0.06, 1.5, 0.18);
        group.add(leftEye);
        const rightEye = new THREE.Mesh(new THREE.SphereGeometry(0.025, 10, 10), eyeMat);
        rightEye.position.set(0.06, 1.5, 0.18);
        group.add(rightEye);

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

            // Walk animation
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
        const angle = Math.random() * Math.PI * 2;
        const r = Math.random() * enemy.patrolRadius;
        return {
            x: enemy.hideoutX + Math.cos(angle) * r,
            z: enemy.hideoutZ + Math.sin(angle) * r
        };
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
