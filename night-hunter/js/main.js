// main.js — Game loop, camera, state management, player (Stage 1+2+3)

// ── Game State ──
const gameState = {
    health: 5,
    maxHealth: 5,
    coins: 30,
    day: 1,
    isDay: true,
    timeRemaining: 7 * 60,
    dayDuration: 7 * 60,
    nightDuration: 5 * 60,
    arrests: 0,
    totalArrests: 3,
    hintsCollected: 0,
    gameOver: false,
    isPaused: false,
    moveSpeed: 0.12,
    runSpeed: 0.24,
    isRunning: false,
    stamina: 100,
    maxStamina: 100
};

// ── Three.js Setup ──
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x87CEEB);
scene.fog = new THREE.Fog(0x87CEEB, 80, 200);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 500);
const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('gameCanvas'), antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

// ── Lighting (Daytime) ──
const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
scene.add(ambientLight);

const sunLight = new THREE.DirectionalLight(0xffffff, 1.0);
sunLight.position.set(50, 80, 50);
sunLight.castShadow = true;
sunLight.shadow.mapSize.width = 2048;
sunLight.shadow.mapSize.height = 2048;
sunLight.shadow.camera.near = 0.5;
sunLight.shadow.camera.far = 300;
sunLight.shadow.camera.left = -100;
sunLight.shadow.camera.right = 100;
sunLight.shadow.camera.top = 100;
sunLight.shadow.camera.bottom = -100;
scene.add(sunLight);

// ── Create World ──
const { worldGroup, buildingData } = createWorld(scene);

// ── Player Character ──
const playerGroup = new THREE.Group();

function createPlayer() {
    // Legs
    const legMat = new THREE.MeshLambertMaterial({ color: 0x1a2a4a });
    const leftLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.7, 8), legMat);
    leftLeg.position.set(-0.2, 0.35, 0);
    leftLeg.castShadow = true;
    leftLeg.userData.partName = 'leftLeg';
    playerGroup.add(leftLeg);

    const rightLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.7, 8), legMat);
    rightLeg.position.set(0.2, 0.35, 0);
    rightLeg.castShadow = true;
    rightLeg.userData.partName = 'rightLeg';
    playerGroup.add(rightLeg);

    // Shoes
    const shoeMat = new THREE.MeshLambertMaterial({ color: 0x111111 });
    const leftShoe = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.12, 0.3), shoeMat);
    leftShoe.position.set(-0.2, 0.0, 0.05);
    leftShoe.castShadow = true;
    playerGroup.add(leftShoe);

    const rightShoe = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.12, 0.3), shoeMat);
    rightShoe.position.set(0.2, 0.0, 0.05);
    rightShoe.castShadow = true;
    playerGroup.add(rightShoe);

    // Body
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.75, 0.35), legMat);
    body.position.set(0, 1.1, 0);
    body.castShadow = true;
    body.userData.partName = 'body';
    playerGroup.add(body);

    // Necktie
    const tie = new THREE.Mesh(
        new THREE.BoxGeometry(0.1, 0.3, 0.05),
        new THREE.MeshLambertMaterial({ color: 0x003399 })
    );
    tie.position.set(0, 1.15, 0.18);
    playerGroup.add(tie);

    // Badge
    const badge = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.08, 0.03, 16),
        new THREE.MeshPhongMaterial({ color: 0xFFD700, emissive: 0x332200 })
    );
    badge.rotation.x = Math.PI / 2;
    badge.position.set(-0.18, 1.25, 0.18);
    playerGroup.add(badge);

    // Arms
    const leftArm = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.6, 8), legMat);
    leftArm.position.set(-0.42, 1.1, 0);
    leftArm.rotation.z = 0.15;
    leftArm.castShadow = true;
    leftArm.userData.partName = 'leftArm';
    playerGroup.add(leftArm);

    const rightArm = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.6, 8), legMat);
    rightArm.position.set(0.42, 1.1, 0);
    rightArm.rotation.z = -0.15;
    rightArm.castShadow = true;
    rightArm.userData.partName = 'rightArm';
    playerGroup.add(rightArm);

    // Hands
    const skinMat = new THREE.MeshLambertMaterial({ color: 0xffdbac });
    const leftHand = new THREE.Mesh(new THREE.SphereGeometry(0.1, 8, 8), skinMat);
    leftHand.position.set(-0.44, 0.78, 0);
    playerGroup.add(leftHand);

    const rightHand = new THREE.Mesh(new THREE.SphereGeometry(0.1, 8, 8), skinMat);
    rightHand.position.set(0.44, 0.78, 0);
    playerGroup.add(rightHand);

    // Head
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.28, 32, 32), skinMat);
    head.position.set(0, 1.68, 0);
    head.castShadow = true;
    playerGroup.add(head);

    // Cheeks
    const cheekMat = new THREE.MeshLambertMaterial({ color: 0xffb3b3, transparent: true, opacity: 0.6 });
    const leftCheek = new THREE.Mesh(new THREE.SphereGeometry(0.07, 8, 8), cheekMat);
    leftCheek.position.set(-0.16, 1.65, 0.22);
    playerGroup.add(leftCheek);
    const rightCheek = new THREE.Mesh(new THREE.SphereGeometry(0.07, 8, 8), cheekMat);
    rightCheek.position.set(0.16, 1.65, 0.22);
    playerGroup.add(rightCheek);

    // Eyebrows
    const browMat = new THREE.MeshLambertMaterial({ color: 0x3b1f0a });
    const leftBrow = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.025, 0.02), browMat);
    leftBrow.position.set(-0.1, 1.75, 0.27);
    leftBrow.rotation.z = 0.15;
    playerGroup.add(leftBrow);
    const rightBrow = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.025, 0.02), browMat);
    rightBrow.position.set(0.1, 1.75, 0.27);
    rightBrow.rotation.z = -0.15;
    playerGroup.add(rightBrow);

    // Eyes
    const eyeWhiteMat = new THREE.MeshLambertMaterial({ color: 0xffffff });
    const eyeBlackMat = new THREE.MeshLambertMaterial({ color: 0x1a0a00 });
    const highlightMat = new THREE.MeshLambertMaterial({ color: 0xffffff });

    const leftEyeWhite = new THREE.Mesh(new THREE.SphereGeometry(0.065, 12, 12), eyeWhiteMat);
    leftEyeWhite.position.set(-0.1, 1.68, 0.25);
    playerGroup.add(leftEyeWhite);
    const rightEyeWhite = new THREE.Mesh(new THREE.SphereGeometry(0.065, 12, 12), eyeWhiteMat);
    rightEyeWhite.position.set(0.1, 1.68, 0.25);
    playerGroup.add(rightEyeWhite);

    const leftPupil = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), eyeBlackMat);
    leftPupil.position.set(-0.1, 1.68, 0.285);
    playerGroup.add(leftPupil);
    const rightPupil = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), eyeBlackMat);
    rightPupil.position.set(0.1, 1.68, 0.285);
    playerGroup.add(rightPupil);

    const leftHighlight = new THREE.Mesh(new THREE.SphereGeometry(0.015, 6, 6), highlightMat);
    leftHighlight.position.set(-0.09, 1.695, 0.3);
    playerGroup.add(leftHighlight);
    const rightHighlight = new THREE.Mesh(new THREE.SphereGeometry(0.015, 6, 6), highlightMat);
    rightHighlight.position.set(0.11, 1.695, 0.3);
    playerGroup.add(rightHighlight);

    // Eyelashes
    const lashMat = new THREE.MeshLambertMaterial({ color: 0x000000 });
    [-0.13, -0.10, -0.07].forEach(lx => {
        const lash = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.04, 0.01), lashMat);
        lash.position.set(lx, 1.735, 0.27);
        playerGroup.add(lash);
    });
    [0.07, 0.10, 0.13].forEach(lx => {
        const lash = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.04, 0.01), lashMat);
        lash.position.set(lx, 1.735, 0.27);
        playerGroup.add(lash);
    });

    // Nose
    const nose = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 8), new THREE.MeshLambertMaterial({ color: 0xe8b88a }));
    nose.position.set(0, 1.63, 0.285);
    playerGroup.add(nose);

    // Lips
    const lipMat = new THREE.MeshLambertMaterial({ color: 0xe05080 });
    const upperLip = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.025, 0.02), lipMat);
    upperLip.position.set(0, 1.56, 0.275);
    playerGroup.add(upperLip);
    const lowerLip = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.03, 0.02), lipMat);
    lowerLip.position.set(0, 1.535, 0.275);
    playerGroup.add(lowerLip);
    const smileLine = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.012, 0.01), new THREE.MeshLambertMaterial({ color: 0x8b4513 }));
    smileLine.position.set(0, 1.548, 0.285);
    playerGroup.add(smileLine);

    // Hair
    const hairMat = new THREE.MeshLambertMaterial({ color: 0x1a0a00 });
    const backHair = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.55, 0.15), hairMat);
    backHair.position.set(0, 1.65, -0.18);
    playerGroup.add(backHair);
    const frontHair = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.12, 0.1), hairMat);
    frontHair.position.set(0, 1.88, 0.18);
    playerGroup.add(frontHair);
    const leftHair = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.45, 0.1), hairMat);
    leftHair.position.set(-0.28, 1.65, 0.05);
    playerGroup.add(leftHair);
    const rightHair = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.45, 0.1), hairMat);
    rightHair.position.set(0.28, 1.65, 0.05);
    playerGroup.add(rightHair);

    // Ponytail
    const ponytail = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.04, 0.5, 8), hairMat);
    ponytail.position.set(0, 1.3, -0.25);
    ponytail.rotation.x = 0.3;
    playerGroup.add(ponytail);

    // Hat
    const hatMat = new THREE.MeshLambertMaterial({ color: 0x0d1b2a });
    const hatBrim = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.04, 32), hatMat);
    hatBrim.position.set(0, 1.9, 0);
    playerGroup.add(hatBrim);
    const hatBody = new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.3, 0.22, 32), hatMat);
    hatBody.position.set(0, 2.02, 0);
    playerGroup.add(hatBody);
    const hatBand = new THREE.Mesh(
        new THREE.CylinderGeometry(0.295, 0.295, 0.04, 32),
        new THREE.MeshPhongMaterial({ color: 0xFFD700, emissive: 0x332200 })
    );
    hatBand.position.set(0, 1.93, 0);
    playerGroup.add(hatBand);
    const hatBadge = new THREE.Mesh(
        new THREE.CylinderGeometry(0.06, 0.06, 0.02, 16),
        new THREE.MeshPhongMaterial({ color: 0xFFD700, emissive: 0x332200 })
    );
    hatBadge.rotation.x = Math.PI / 2;
    hatBadge.position.set(0, 2.08, 0.26);
    playerGroup.add(hatBadge);

    playerGroup.position.set(0, 0, 92);
    scene.add(playerGroup);
}

createPlayer();

// ── Day/Night System Init ──
DayNight.init(scene, playerGroup);

// ── Camera ──
let cameraAngleY = 0;
let cameraAngleX = 0.3;
const cameraDistance = 10;
const cameraHeight = 5;

function updateCamera() {
    const px = playerGroup.position.x;
    const py = playerGroup.position.y;
    const pz = playerGroup.position.z;

    const camX = px + Math.sin(cameraAngleY) * cameraDistance * Math.cos(cameraAngleX);
    const camY = py + cameraHeight + Math.sin(cameraAngleX) * cameraDistance;
    const camZ = pz + Math.cos(cameraAngleY) * cameraDistance * Math.cos(cameraAngleX);

    camera.position.set(camX, camY, camZ);
    camera.lookAt(px, py + 1.5, pz);
}

// ── Input ──
const keys = {};
let moveDir = { x: 0, z: 0 };
let isTouchMoving = false;
let cameraDragging = false;
let lastTouchX = 0, lastTouchY = 0;

window.addEventListener('keydown', e => {
    keys[e.code] = true;
    if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') gameState.isRunning = true;
    if (e.code === 'KeyE') HintSystem.collectNearbyHint();
    if (e.code === 'KeyI') HintSystem.toggleMemo();
});
window.addEventListener('keyup', e => {
    keys[e.code] = false;
    if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') gameState.isRunning = false;
});

// ── Virtual Joystick (원형) ──
const joystickOuter = document.createElement('div');
joystickOuter.id = 'joystick-outer';
const joystickInner = document.createElement('div');
joystickInner.id = 'joystick-inner';
joystickOuter.appendChild(joystickInner);

// Run button
const runBtn = document.createElement('button');
runBtn.id = 'run-btn';
runBtn.textContent = 'RUN';

const joystickStyle = document.createElement('style');
joystickStyle.textContent = `
#joystick-outer {
    position: fixed;
    left: 24px;
    bottom: 90px;
    width: 130px;
    height: 130px;
    border-radius: 50%;
    background: rgba(255,255,255,0.08);
    border: 2px solid rgba(255,255,255,0.25);
    z-index: 30;
    pointer-events: auto;
    touch-action: none;
    display: flex;
    align-items: center;
    justify-content: center;
}
#joystick-inner {
    width: 50px;
    height: 50px;
    border-radius: 50%;
    background: rgba(255,255,255,0.35);
    border: 2px solid rgba(255,255,255,0.5);
    pointer-events: none;
    transition: none;
}
#run-btn {
    position: fixed;
    left: 170px;
    bottom: 100px;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: 2px solid rgba(255,160,0,0.5);
    background: rgba(255,160,0,0.2);
    backdrop-filter: blur(4px);
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    touch-action: none;
    z-index: 30;
    pointer-events: auto;
}
#run-btn.active {
    background: rgba(255,160,0,0.5);
    transform: scale(0.92);
}
#action-buttons {
    position: fixed;
    right: 20px;
    bottom: 120px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    z-index: 30;
}
.action-btn {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.3);
    background: rgba(255,255,255,0.15);
    backdrop-filter: blur(4px);
    color: #fff;
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    touch-action: none;
    transition: transform 0.1s;
    pointer-events: auto;
}
.action-btn:active { transform: scale(0.9); }
.action-btn-interact { background: rgba(255,220,0,0.25); border-color: rgba(255,220,0,0.5); }
#stamina-bar {
    position: fixed;
    bottom: 70px;
    left: 50%;
    transform: translateX(-50%);
    width: 180px;
    height: 8px;
    background: rgba(0,0,0,0.4);
    border-radius: 4px;
    overflow: hidden;
    z-index: 30;
}
#stamina-fill {
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, #22c55e, #4ade80);
    transition: width 0.2s;
    border-radius: 4px;
}
`;
document.head.appendChild(joystickStyle);
document.getElementById('hud').appendChild(joystickOuter);
document.getElementById('hud').appendChild(runBtn);

// Action buttons
const actionBtnContainer = document.createElement('div');
actionBtnContainer.id = 'action-buttons';
actionBtnContainer.innerHTML = `
    <button class="action-btn action-btn-interact" id="btn-interact" style="display:none;" onclick="HintSystem.collectNearbyHint()">E</button>
`;
document.getElementById('hud').appendChild(actionBtnContainer);

// Stamina bar
const staminaBarDiv = document.createElement('div');
staminaBarDiv.id = 'stamina-bar';
staminaBarDiv.innerHTML = '<div id="stamina-fill"></div>';
document.getElementById('hud').appendChild(staminaBarDiv);

// ── System Init (DOM 요소 생성 이후) ──
HintSystem.init(scene);
EnemySystem.init(scene);

// ── Joystick Logic ──
let joystickActive = false;
let joystickTouchId = null;
const joystickMaxDist = 40;

function getJoystickCenter() {
    const rect = joystickOuter.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

function handleJoystickMove(cx, cy) {
    const center = getJoystickCenter();
    let dx = cx - center.x;
    let dy = cy - center.y;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist > joystickMaxDist) {
        dx = (dx / dist) * joystickMaxDist;
        dy = (dy / dist) * joystickMaxDist;
    }

    joystickInner.style.transform = `translate(${dx}px, ${dy}px)`;

    const deadzone = 8;
    if (dist > deadzone) {
        moveDir.x = dx / joystickMaxDist;
        moveDir.z = dy / joystickMaxDist;
        isTouchMoving = true;
    } else {
        moveDir.x = 0;
        moveDir.z = 0;
        isTouchMoving = false;
    }
}

function resetJoystick() {
    joystickInner.style.transform = 'translate(0px, 0px)';
    joystickActive = false;
    joystickTouchId = null;
    moveDir.x = 0;
    moveDir.z = 0;
    isTouchMoving = false;
}

joystickOuter.addEventListener('touchstart', e => {
    e.preventDefault();
    const t = e.changedTouches[0];
    joystickActive = true;
    joystickTouchId = t.identifier;
    handleJoystickMove(t.clientX, t.clientY);
}, { passive: false });

window.addEventListener('touchmove', e => {
    if (!joystickActive) return;
    for (let i = 0; i < e.changedTouches.length; i++) {
        if (e.changedTouches[i].identifier === joystickTouchId) {
            e.preventDefault();
            handleJoystickMove(e.changedTouches[i].clientX, e.changedTouches[i].clientY);
            return;
        }
    }
}, { passive: false });

window.addEventListener('touchend', e => {
    for (let i = 0; i < e.changedTouches.length; i++) {
        if (e.changedTouches[i].identifier === joystickTouchId) {
            resetJoystick();
            return;
        }
    }
});
window.addEventListener('touchcancel', () => resetJoystick());

// Mouse joystick (PC)
joystickOuter.addEventListener('mousedown', e => {
    e.preventDefault();
    joystickActive = true;
    handleJoystickMove(e.clientX, e.clientY);
});
window.addEventListener('mousemove', e => {
    if (!joystickActive) return;
    handleJoystickMove(e.clientX, e.clientY);
});
window.addEventListener('mouseup', () => { if (joystickActive) resetJoystick(); });

// Run button
runBtn.addEventListener('touchstart', e => { e.preventDefault(); gameState.isRunning = true; runBtn.classList.add('active'); }, { passive: false });
runBtn.addEventListener('touchend', e => { e.preventDefault(); gameState.isRunning = false; runBtn.classList.remove('active'); }, { passive: false });
runBtn.addEventListener('mousedown', e => { e.preventDefault(); gameState.isRunning = true; runBtn.classList.add('active'); });
runBtn.addEventListener('mouseup', () => { gameState.isRunning = false; runBtn.classList.remove('active'); });
runBtn.addEventListener('mouseleave', () => { gameState.isRunning = false; runBtn.classList.remove('active'); });

// Camera drag (right side of screen / touch)
const canvas = document.getElementById('gameCanvas');
let cameraTouchId = null;

canvas.addEventListener('touchstart', e => {
    for (let i = 0; i < e.changedTouches.length; i++) {
        const touch = e.changedTouches[i];
        if (touch.clientX > window.innerWidth * 0.35 && cameraTouchId === null) {
            cameraDragging = true;
            cameraTouchId = touch.identifier;
            lastTouchX = touch.clientX;
            lastTouchY = touch.clientY;
        }
    }
}, { passive: true });

canvas.addEventListener('touchmove', e => {
    if (!cameraDragging) return;
    for (let i = 0; i < e.changedTouches.length; i++) {
        const touch = e.changedTouches[i];
        if (touch.identifier === cameraTouchId) {
            e.preventDefault();
            const dx = touch.clientX - lastTouchX;
            const dy = touch.clientY - lastTouchY;
            cameraAngleY -= dx * 0.005;
            cameraAngleX = Math.max(0.05, Math.min(1.2, cameraAngleX + dy * 0.005));
            lastTouchX = touch.clientX;
            lastTouchY = touch.clientY;
            return;
        }
    }
}, { passive: false });

canvas.addEventListener('touchend', e => {
    for (let i = 0; i < e.changedTouches.length; i++) {
        if (e.changedTouches[i].identifier === cameraTouchId) {
            cameraDragging = false;
            cameraTouchId = null;
        }
    }
});

// Mouse camera drag
let mouseDown = false;
canvas.addEventListener('mousedown', e => {
    if (e.button === 0 || e.button === 2) {
        mouseDown = true;
        lastTouchX = e.clientX;
        lastTouchY = e.clientY;
    }
});
canvas.addEventListener('mousemove', e => {
    if (!mouseDown) return;
    const dx = e.clientX - lastTouchX;
    const dy = e.clientY - lastTouchY;
    cameraAngleY -= dx * 0.005;
    cameraAngleX = Math.max(0.05, Math.min(1.2, cameraAngleX + dy * 0.005));
    lastTouchX = e.clientX;
    lastTouchY = e.clientY;
});
canvas.addEventListener('mouseup', () => { mouseDown = false; });
canvas.addEventListener('contextmenu', e => e.preventDefault());

// ── Collision Detection ──
function checkBuildingCollision(nx, nz) {
    const playerRadius = 0.5;
    for (const b of buildingData) {
        const bx = b.x || b.mesh.position.x;
        const bz = b.z || b.mesh.position.z;
        const bw = (b.w || 6) / 2 + playerRadius;
        const bd = (b.d || 6) / 2 + playerRadius;
        if (Math.abs(nx - bx) < bw && Math.abs(nz - bz) < bd) {
            return true;
        }
    }
    return false;
}

// ── Player Movement ──
const clock = new THREE.Clock();
let walkTime = 0;

function updatePlayer(delta) {
    let dx = 0, dz = 0;

    // Keyboard
    if (keys['KeyW'] || keys['ArrowUp']) dz -= 1;
    if (keys['KeyS'] || keys['ArrowDown']) dz += 1;
    if (keys['KeyA'] || keys['ArrowLeft']) dx -= 1;
    if (keys['KeyD'] || keys['ArrowRight']) dx += 1;

    // Touch d-pad
    if (isTouchMoving) {
        dx = moveDir.x;
        dz = moveDir.z;
    }

    // Camera-relative movement
    if (dx !== 0 || dz !== 0) {
        const len = Math.sqrt(dx * dx + dz * dz);
        dx /= len;
        dz /= len;

        const sinA = Math.sin(cameraAngleY);
        const cosA = Math.cos(cameraAngleY);
        const worldDx = dx * cosA - dz * sinA;
        const worldDz = dx * sinA + dz * cosA;

        // Speed & stamina
        let speed = gameState.moveSpeed;
        if (gameState.isRunning && gameState.stamina > 0) {
            speed = gameState.runSpeed;
            gameState.stamina = Math.max(0, gameState.stamina - 30 * delta);
        } else if (gameState.stamina <= 0) {
            speed = 0.08;
        }

        if (!gameState.isRunning) {
            gameState.stamina = Math.min(gameState.maxStamina, gameState.stamina + 15 * delta);
        }

        const nx = playerGroup.position.x + worldDx * speed * delta * 60;
        const nz = playerGroup.position.z + worldDz * speed * delta * 60;

        // Boundary & collision
        const half = WORLD_SIZE / 2 - 1;
        const clampedX = Math.max(-half, Math.min(half, nx));
        const clampedZ = Math.max(-half, Math.min(half, nz));

        if (!checkBuildingCollision(clampedX, clampedZ)) {
            playerGroup.position.x = clampedX;
            playerGroup.position.z = clampedZ;
        } else if (!checkBuildingCollision(clampedX, playerGroup.position.z)) {
            playerGroup.position.x = clampedX;
        } else if (!checkBuildingCollision(playerGroup.position.x, clampedZ)) {
            playerGroup.position.z = clampedZ;
        }

        // Face movement direction
        const angle = Math.atan2(worldDx, worldDz);
        playerGroup.rotation.y = angle;

        // Walk animation
        walkTime += delta * (gameState.isRunning ? 12 : 8);
        animateWalk(walkTime);
    } else {
        // Idle animation
        gameState.stamina = Math.min(gameState.maxStamina, gameState.stamina + 15 * delta);
        animateIdle(clock.elapsedTime);
    }

    // Update stamina bar
    document.getElementById('stamina-fill').style.width = (gameState.stamina / gameState.maxStamina * 100) + '%';
    const staminaPct = gameState.stamina / gameState.maxStamina;
    const staminaFill = document.getElementById('stamina-fill');
    if (staminaPct > 0.5) staminaFill.style.background = 'linear-gradient(90deg, #22c55e, #4ade80)';
    else if (staminaPct > 0.2) staminaFill.style.background = 'linear-gradient(90deg, #eab308, #facc15)';
    else staminaFill.style.background = 'linear-gradient(90deg, #ef4444, #f87171)';
}

function animateWalk(time) {
    const swing = Math.sin(time) * 0.3;
    playerGroup.children.forEach(child => {
        const name = child.userData.partName;
        if (name === 'leftLeg') child.rotation.x = swing;
        if (name === 'rightLeg') child.rotation.x = -swing;
        if (name === 'leftArm') child.rotation.x = -swing;
        if (name === 'rightArm') child.rotation.x = swing;
    });
}

function animateIdle(time) {
    playerGroup.children.forEach(child => {
        const name = child.userData.partName;
        if (name === 'body') {
            child.position.y = 1.1 + Math.sin(time * 1.5) * 0.01;
        }
        if (name === 'leftLeg' || name === 'rightLeg' || name === 'leftArm' || name === 'rightArm') {
            child.rotation.x *= 0.9;
        }
    });
}

// ── Timer & HUD ──
let lastTime = performance.now();

function updateTimer(delta) {
    if (gameState.gameOver || gameState.isPaused) return;

    // Handle active transition
    if (DayNight.isTransitioning) {
        const finished = DayNight.updateTransition(delta);
        if (finished) {
            DayNight.updateWindowGlow(!gameState.isDay);
        }
        updateTimerDisplay();
        return;
    }

    gameState.timeRemaining -= delta;

    if (gameState.timeRemaining <= 0) {
        if (gameState.isDay) {
            DayNight.startTransition('toNight');
        } else {
            DayNight.startTransition('toDay');
        }
        gameState.timeRemaining = 0;
    }

    DayNight.checkLastMinuteWarning();
    DayNight.updateFlashlight();
    updateTimerDisplay();
}

function updateTimerDisplay() {
    const mins = Math.floor(Math.abs(gameState.timeRemaining) / 60);
    const secs = Math.floor(Math.abs(gameState.timeRemaining) % 60);
    document.getElementById('timer').textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
}

function showMessage(text) {
    const box = document.getElementById('message-box');
    box.textContent = text;
    box.style.display = 'block';
    setTimeout(() => { box.style.display = 'none'; }, 3000);
}

function updateHUD() {
    const hearts = document.querySelectorAll('#health-bar .heart');
    hearts.forEach((h, i) => {
        h.style.opacity = i < gameState.health ? '1' : '0.2';
    });
    document.getElementById('coin-amount').textContent = gameState.coins;
    document.getElementById('arrest-count').textContent = `👮 검거 ${gameState.arrests}/${gameState.totalArrests}`;
}

// ── Game Loop ──
function animate() {
    if (gameState.gameOver) return;
    requestAnimationFrame(animate);

    const now = performance.now();
    const delta = Math.min((now - lastTime) / 1000, 0.1);
    lastTime = now;

    if (!gameState.isPaused) {
        updatePlayer(delta);
        updateTimer(delta);
        updateCamera();
        updateHUD();
        HintSystem.update(playerGroup.position, delta, clock.elapsedTime);
        EnemySystem.update(playerGroup.position, delta, clock.elapsedTime);
    }

    renderer.render(scene, camera);
}

// ── Start ──
showMessage('🚔 도시 어딘가에 아이들이 납치되어 있습니다.\n힌트를 찾아 수사를 시작하세요.');
updateCamera();
animate();
