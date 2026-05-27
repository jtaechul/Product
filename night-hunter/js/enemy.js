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

    init(scene) {
        this.scene = scene;
        this.enemies = [];
        this.enemyMeshes = [];
        this.createAlertUI();

        this.enemyData.forEach(data => {
            const enemy = this.createEnemy(data);
            this.enemies.push(enemy);
        });
    },

    createEnemy(data) {
        const group = new THREE.Group();

        // Body
        const bodyMat = new THREE.MeshLambertMaterial({ color: data.color });
        const body = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.7, 0.35), bodyMat);
        body.position.y = 1.0;
        body.castShadow = true;
        group.add(body);

        // Head
        const head = new THREE.Mesh(
            new THREE.SphereGeometry(0.25, 16, 16),
            new THREE.MeshLambertMaterial({ color: 0xddbb99 })
        );
        head.position.y = 1.6;
        head.castShadow = true;
        group.add(head);

        // Hood/mask
        const hood = new THREE.Mesh(
            new THREE.SphereGeometry(0.27, 16, 16, 0, Math.PI * 2, 0, Math.PI * 0.6),
            new THREE.MeshLambertMaterial({ color: 0x222222 })
        );
        hood.position.y = 1.65;
        group.add(hood);

        // Eyes (menacing)
        const eyeMat = new THREE.MeshBasicMaterial({ color: 0xff0000 });
        const leftEye = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), eyeMat);
        leftEye.position.set(-0.08, 1.6, 0.23);
        group.add(leftEye);
        const rightEye = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), eyeMat);
        rightEye.position.set(0.08, 1.6, 0.23);
        group.add(rightEye);

        // Legs
        const legMat = new THREE.MeshLambertMaterial({ color: 0x222222 });
        const leftLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.6, 8), legMat);
        leftLeg.position.set(-0.15, 0.3, 0);
        leftLeg.castShadow = true;
        leftLeg.userData.partName = 'leftLeg';
        group.add(leftLeg);
        const rightLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.6, 8), legMat);
        rightLeg.position.set(0.15, 0.3, 0);
        rightLeg.castShadow = true;
        rightLeg.userData.partName = 'rightLeg';
        group.add(rightLeg);

        // Arms
        const leftArm = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.5, 8), bodyMat);
        leftArm.position.set(-0.38, 1.0, 0);
        leftArm.rotation.z = 0.15;
        leftArm.userData.partName = 'leftArm';
        group.add(leftArm);
        const rightArm = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.5, 8), bodyMat);
        rightArm.position.set(0.38, 1.0, 0);
        rightArm.rotation.z = -0.15;
        rightArm.userData.partName = 'rightArm';
        group.add(rightArm);

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
        enemy.currentX += (dx / dist) * speed;
        enemy.currentZ += (dz / dist) * speed;

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
            let nx = enemy.currentX + (dx / dist) * speed;
            let nz = enemy.currentZ + (dz / dist) * speed;

            const half = WORLD_SIZE / 2 - 2;
            nx = Math.max(-half, Math.min(half, nx));
            nz = Math.max(-half, Math.min(half, nz));

            enemy.currentX = nx;
            enemy.currentZ = nz;

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
            enemy.currentX += (dx / dist) * speed;
            enemy.currentZ += (dz / dist) * speed;
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
