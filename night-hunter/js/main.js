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
    maxStamina: 100,
    isJumping: false,
    jumpVelocity: 0,
    jumpHeight: 0
};

// ── Three.js Setup ──
const scene = new THREE.Scene();

// Gradient sky background (procedural)
function makeSkyTexture(topColor, bottomColor) {
    const canvas = document.createElement('canvas');
    canvas.width = 2; canvas.height = 256;
    const ctx = canvas.getContext('2d');
    const grd = ctx.createLinearGradient(0, 0, 0, 256);
    grd.addColorStop(0, topColor);
    grd.addColorStop(0.5, bottomColor);
    grd.addColorStop(1, bottomColor);
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, 2, 256);
    const tex = new THREE.CanvasTexture(canvas);
    tex.minFilter = THREE.LinearFilter;
    return tex;
}
scene.background = makeSkyTexture('#7ec0ee', '#cfeaff');
scene.fog = new THREE.Fog(0xcfeaff, 70, 220);

const isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 500);
const renderer = new THREE.WebGLRenderer({
    canvas: document.getElementById('gameCanvas'),
    antialias: !isMobile,
    powerPreference: 'high-performance'
});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, isMobile ? 1.2 : 2));
renderer.shadowMap.enabled = !isMobile;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputEncoding = THREE.sRGBEncoding;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;
renderer.physicallyCorrectLights = false;

// Post-processing — disable on mobile for battery/performance
let composer = null;
let bloomPass = null;
let fxaaPass = null;
if (!isMobile) {
    try {
        composer = new THREE.EffectComposer(renderer);
        composer.addPass(new THREE.RenderPass(scene, camera));
        bloomPass = new THREE.UnrealBloomPass(
            new THREE.Vector2(window.innerWidth, window.innerHeight),
            0.3, 0.7, 0.85
        );
        composer.addPass(bloomPass);
        fxaaPass = new THREE.ShaderPass(THREE.FXAAShader);
        fxaaPass.material.uniforms['resolution'].value.set(
            1 / (window.innerWidth * renderer.getPixelRatio()),
            1 / (window.innerHeight * renderer.getPixelRatio())
        );
        composer.addPass(fxaaPass);
    } catch (e) {
        console.warn('Postprocessing not available');
    }
}

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    if (composer) composer.setSize(window.innerWidth, window.innerHeight);
    if (fxaaPass) {
        fxaaPass.material.uniforms['resolution'].value.set(
            1 / (window.innerWidth * renderer.getPixelRatio()),
            1 / (window.innerHeight * renderer.getPixelRatio())
        );
    }
});

// ── Lighting (Daytime) ──
const ambientLight = new THREE.AmbientLight(0xc8d8f0, 0.7);
scene.add(ambientLight);

const hemiLight = new THREE.HemisphereLight(0x87CEEB, 0x3a6b2a, 0.4);
scene.add(hemiLight);

const sunLight = new THREE.DirectionalLight(0xfff5e0, 1.0);
sunLight.position.set(60, 100, 40);
sunLight.castShadow = !isMobile;
const shadowSize = isMobile ? 512 : 1024;
sunLight.shadow.mapSize.width = shadowSize;
sunLight.shadow.mapSize.height = shadowSize;
sunLight.shadow.camera.near = 0.5;
sunLight.shadow.camera.far = 200;
sunLight.shadow.camera.left = -60;
sunLight.shadow.camera.right = 60;
sunLight.shadow.camera.top = 60;
sunLight.shadow.camera.bottom = -60;
sunLight.shadow.bias = -0.001;
scene.add(sunLight);

// ── Create World ──
const { worldGroup, buildingData } = createWorld(scene);

// ── Player Character ──
const playerGroup = new THREE.Group();

function createPlayer() {
    // Legs
    const legMat = new THREE.MeshStandardMaterial({ color: 0x1a2a4a, roughness: 0.7, metalness: 0.1 });
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
    const shoeMat = new THREE.MeshStandardMaterial({ color: 0x111111 });
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
        new THREE.MeshStandardMaterial({ color: 0x003399 })
    );
    tie.position.set(0, 1.15, 0.18);
    playerGroup.add(tie);

    // Badge
    const badge = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.08, 0.03, 16),
        new THREE.MeshStandardMaterial({ color: 0xFFD700, emissive: 0x332200 })
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
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xffdbac });
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
    const cheekMat = new THREE.MeshStandardMaterial({ color: 0xffb3b3, transparent: true, opacity: 0.6 });
    const leftCheek = new THREE.Mesh(new THREE.SphereGeometry(0.07, 8, 8), cheekMat);
    leftCheek.position.set(-0.16, 1.65, 0.22);
    playerGroup.add(leftCheek);
    const rightCheek = new THREE.Mesh(new THREE.SphereGeometry(0.07, 8, 8), cheekMat);
    rightCheek.position.set(0.16, 1.65, 0.22);
    playerGroup.add(rightCheek);

    // Eyebrows
    const browMat = new THREE.MeshStandardMaterial({ color: 0x3b1f0a });
    const leftBrow = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.025, 0.02), browMat);
    leftBrow.position.set(-0.1, 1.75, 0.27);
    leftBrow.rotation.z = 0.15;
    playerGroup.add(leftBrow);
    const rightBrow = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.025, 0.02), browMat);
    rightBrow.position.set(0.1, 1.75, 0.27);
    rightBrow.rotation.z = -0.15;
    playerGroup.add(rightBrow);

    // Eyes
    const eyeWhiteMat = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const eyeBlackMat = new THREE.MeshStandardMaterial({ color: 0x1a0a00 });
    const highlightMat = new THREE.MeshStandardMaterial({ color: 0xffffff });

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
    const lashMat = new THREE.MeshStandardMaterial({ color: 0x000000 });
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
    const nose = new THREE.Mesh(new THREE.SphereGeometry(0.025, 8, 8), new THREE.MeshStandardMaterial({ color: 0xe8b88a }));
    nose.position.set(0, 1.63, 0.285);
    playerGroup.add(nose);

    // Lips
    const lipMat = new THREE.MeshStandardMaterial({ color: 0xe05080 });
    const upperLip = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.025, 0.02), lipMat);
    upperLip.position.set(0, 1.56, 0.275);
    playerGroup.add(upperLip);
    const lowerLip = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.03, 0.02), lipMat);
    lowerLip.position.set(0, 1.535, 0.275);
    playerGroup.add(lowerLip);
    const smileLine = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.012, 0.01), new THREE.MeshStandardMaterial({ color: 0x8b4513 }));
    smileLine.position.set(0, 1.548, 0.285);
    playerGroup.add(smileLine);

    // Hair — full coverage with sphere base + back volume
    const hairMat = new THREE.MeshStandardMaterial({ color: 0x2a1208, roughness: 0.85 });

    // Hair sphere base (covers top + back of head)
    const hairBase = new THREE.Mesh(
        new THREE.SphereGeometry(0.31, 24, 24, 0, Math.PI * 2, 0, Math.PI * 0.65),
        hairMat
    );
    hairBase.position.set(0, 1.68, 0);
    hairBase.castShadow = true;
    playerGroup.add(hairBase);

    // Back hair volume (longer, behind head)
    const backHairVol = new THREE.Mesh(
        new THREE.SphereGeometry(0.25, 20, 20, 0, Math.PI * 2, 0, Math.PI * 0.7),
        hairMat
    );
    backHairVol.position.set(0, 1.52, -0.15);
    backHairVol.scale.set(1.0, 1.4, 0.7);
    backHairVol.castShadow = true;
    playerGroup.add(backHairVol);

    // Side hair (shoulder-length)
    const leftSideHair = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.55, 0.18),
        hairMat
    );
    leftSideHair.position.set(-0.27, 1.5, -0.05);
    leftSideHair.castShadow = true;
    playerGroup.add(leftSideHair);

    const rightSideHair = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.55, 0.18),
        hairMat
    );
    rightSideHair.position.set(0.27, 1.5, -0.05);
    rightSideHair.castShadow = true;
    playerGroup.add(rightSideHair);

    // Front bangs
    const frontBangs = new THREE.Mesh(
        new THREE.BoxGeometry(0.5, 0.14, 0.12),
        hairMat
    );
    frontBangs.position.set(0, 1.88, 0.2);
    frontBangs.rotation.x = -0.2;
    playerGroup.add(frontBangs);

    // Ponytail (longer & thicker)
    const ponytail = new THREE.Mesh(
        new THREE.CylinderGeometry(0.09, 0.05, 0.7, 12),
        hairMat
    );
    ponytail.position.set(0, 1.25, -0.28);
    ponytail.rotation.x = 0.35;
    ponytail.castShadow = true;
    playerGroup.add(ponytail);

    // Hair tie
    const hairTie = new THREE.Mesh(
        new THREE.CylinderGeometry(0.06, 0.06, 0.04, 8),
        new THREE.MeshStandardMaterial({ color: 0xcc1a1a, roughness: 0.5 })
    );
    hairTie.position.set(0, 1.5, -0.25);
    playerGroup.add(hairTie);

    // Hat
    const hatMat = new THREE.MeshStandardMaterial({ color: 0x0d1b2a });
    const hatBrim = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.04, 32), hatMat);
    hatBrim.position.set(0, 1.9, 0);
    playerGroup.add(hatBrim);
    const hatBody = new THREE.Mesh(new THREE.CylinderGeometry(0.26, 0.3, 0.22, 32), hatMat);
    hatBody.position.set(0, 2.02, 0);
    playerGroup.add(hatBody);
    const hatBand = new THREE.Mesh(
        new THREE.CylinderGeometry(0.295, 0.295, 0.04, 32),
        new THREE.MeshStandardMaterial({ color: 0xFFD700, emissive: 0x332200 })
    );
    hatBand.position.set(0, 1.93, 0);
    playerGroup.add(hatBand);
    const hatBadge = new THREE.Mesh(
        new THREE.CylinderGeometry(0.06, 0.06, 0.02, 16),
        new THREE.MeshStandardMaterial({ color: 0xFFD700, emissive: 0x332200 })
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
let playerFacingAngle = 0;

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
    if (e.code === 'KeyH') HintSystem.collectNearbyHint();
    if (e.code === 'KeyP') { if (!Shop.isOpen) Shop.openShop(); else Shop.closeShop(); }
    if (e.code === 'KeyI') Shop.toggleInventory();
    if (e.code === 'KeyM') HintSystem.toggleMemo();
    if (e.code === 'Space') { e.preventDefault(); triggerJump(); }
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

// Run + Jump buttons
const runBtn = document.createElement('button');
runBtn.id = 'run-btn';
runBtn.textContent = 'RUN';

const jumpBtn = document.createElement('button');
jumpBtn.id = 'jump-btn';
jumpBtn.textContent = 'JUMP';

const joystickStyle = document.createElement('style');
joystickStyle.textContent = `
#joystick-outer {
    position: fixed;
    left: calc(20px + env(safe-area-inset-left, 0px));
    bottom: calc(30px + env(safe-area-inset-bottom, 0px));
    width: 120px;
    height: 120px;
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
    width: 46px;
    height: 46px;
    border-radius: 50%;
    background: rgba(255,255,255,0.35);
    border: 2px solid rgba(255,255,255,0.5);
    pointer-events: none;
    transition: none;
}
#run-btn, #jump-btn {
    position: fixed;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    backdrop-filter: blur(4px);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    font-family: 'Inter', sans-serif;
    cursor: pointer;
    touch-action: none;
    z-index: 30;
    pointer-events: auto;
}
#run-btn {
    right: calc(80px + env(safe-area-inset-right, 0px));
    bottom: calc(25px + env(safe-area-inset-bottom, 0px));
    border: 2px solid rgba(255,160,0,0.5);
    background: rgba(255,160,0,0.2);
}
#jump-btn {
    right: calc(80px + env(safe-area-inset-right, 0px));
    bottom: calc(90px + env(safe-area-inset-bottom, 0px));
    border: 2px solid rgba(100,200,255,0.5);
    background: rgba(100,200,255,0.2);
}
#run-btn.active { background: rgba(255,160,0,0.5); transform: scale(0.92); }
#jump-btn.active { background: rgba(100,200,255,0.5); transform: scale(0.92); }
#action-buttons {
    position: fixed;
    right: calc(14px + env(safe-area-inset-right, 0px));
    bottom: calc(25px + env(safe-area-inset-bottom, 0px));
    display: flex;
    flex-direction: column;
    gap: 8px;
    z-index: 30;
}
.action-btn {
    width: 52px;
    height: 52px;
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.3);
    background: rgba(255,255,255,0.15);
    backdrop-filter: blur(4px);
    color: #fff;
    font-size: 18px;
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
    bottom: 10px;
    left: 160px;
    width: 140px;
    height: 6px;
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
document.getElementById('hud').appendChild(jumpBtn);

// Action buttons
const actionBtnContainer = document.createElement('div');
actionBtnContainer.id = 'action-buttons';
actionBtnContainer.innerHTML = `
    <button class="action-btn action-btn-interact" id="btn-interact" style="display:none !important;">E</button>
`;
document.getElementById('hud').appendChild(actionBtnContainer);

// Stamina bar
const staminaBarDiv = document.createElement('div');
staminaBarDiv.id = 'stamina-bar';
staminaBarDiv.innerHTML = '<div id="stamina-fill"></div>';
document.getElementById('hud').appendChild(staminaBarDiv);

// ── System Init (DOM 요소 생성 이후) ──
HintSystem.init(scene);
EnemySystem.init(scene, buildingData);
Minigame.init();
Shop.init(scene);
NPCSystem.init(scene);
GameUI.init();

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

// Jump button
jumpBtn.addEventListener('touchstart', e => { e.preventDefault(); triggerJump(); jumpBtn.classList.add('active'); }, { passive: false });
jumpBtn.addEventListener('touchend', e => { e.preventDefault(); jumpBtn.classList.remove('active'); }, { passive: false });
jumpBtn.addEventListener('mousedown', e => { e.preventDefault(); triggerJump(); jumpBtn.classList.add('active'); });
jumpBtn.addEventListener('mouseup', () => { jumpBtn.classList.remove('active'); });

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

function triggerJump() {
    if (!gameState.isJumping && !gameState.isPaused) {
        gameState.isJumping = true;
        gameState.jumpVelocity = 5;
        if (typeof SoundManager !== 'undefined') SoundManager.playSFX('jump');
    }
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

    // Camera-relative movement (Roblox-style)
    if (dx !== 0 || dz !== 0) {
        const len = Math.sqrt(dx * dx + dz * dz);
        dx /= len;
        dz /= len;

        // Transform input to world space based on camera orientation
        // Camera is at angle cameraAngleY from player
        // Forward (camera→player) = (-sinA, -cosA), Right = (cosA, -sinA)
        const sinA = Math.sin(cameraAngleY);
        const cosA = Math.cos(cameraAngleY);
        const worldDx = dx * cosA + dz * sinA;
        const worldDz = -dx * sinA + dz * cosA;

        // Target angle = direction of movement
        const targetAngle = Math.atan2(worldDx, worldDz);

        // Smooth rotation toward movement direction
        let angleDiff = targetAngle - playerFacingAngle;
        while (angleDiff > Math.PI) angleDiff -= Math.PI * 2;
        while (angleDiff < -Math.PI) angleDiff += Math.PI * 2;
        playerFacingAngle += angleDiff * Math.min(1, 12 * delta);
        playerGroup.rotation.y = playerFacingAngle;

        // Move in camera-relative world direction
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

        // Walk animation
        const prevStep = Math.floor(walkTime / Math.PI);
        walkTime += delta * (gameState.isRunning ? 12 : 8);
        const newStep = Math.floor(walkTime / Math.PI);
        if (newStep !== prevStep && gameState.isRunning && !gameState.isJumping && typeof SoundManager !== 'undefined') {
            SoundManager.playSFX('run_step');
        }
        animateWalk(walkTime);
    } else {
        // Idle animation
        gameState.stamina = Math.min(gameState.maxStamina, gameState.stamina + 15 * delta);
        animateIdle(clock.elapsedTime);
    }

    // Jump physics
    if (gameState.isJumping) {
        gameState.jumpVelocity -= 15 * delta;
        gameState.jumpHeight += gameState.jumpVelocity * delta;
        if (gameState.jumpHeight <= 0) {
            gameState.jumpHeight = 0;
            gameState.isJumping = false;
            if (typeof SoundManager !== 'undefined') SoundManager.playSFX('land');
            gameState.jumpVelocity = 0;
        }
        playerGroup.position.y = gameState.jumpHeight;
    }

    // Police station heal (within 15 units)
    const psDist = Math.sqrt(playerGroup.position.x * playerGroup.position.x + (playerGroup.position.z - 80) * (playerGroup.position.z - 80));
    if (psDist < 15 && gameState.health < gameState.maxHealth) {
        gameState.healTimer = (gameState.healTimer || 0) + delta;
        if (gameState.healTimer > 3) {
            gameState.health = Math.min(gameState.maxHealth, gameState.health + 1);
            gameState.healTimer = 0;
            showMessage('🏥 경찰서에서 체력이 회복됩니다 (+1)');
        }
    } else {
        gameState.healTimer = 0;
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
let minimapTimer = 0;
function animate() {
    if (gameState.gameOver) return;
    requestAnimationFrame(animate);

    const now = performance.now();
    const delta = Math.min((now - lastTime) / 1000, 0.1);
    lastTime = now;

    if (gameState.health <= 0 && !Minigame.active) {
        Minigame.triggerGameOver();
        return;
    }

    minimapTimer += delta;

    if (!gameState.isPaused) {
        updatePlayer(delta);
        updateTimer(delta);
        updateCamera();
        updateHUD();
        HintSystem.update(playerGroup.position, delta, clock.elapsedTime);
        EnemySystem.update(playerGroup.position, delta, clock.elapsedTime);
        Shop.update(playerGroup.position);
        NPCSystem.update(playerGroup.position, delta, clock.elapsedTime);
        Minigame.checkCatchable(playerGroup.position);
        // Throttle minimap to ~6 FPS (mobile battery saver)
        if (minimapTimer > 0.16) {
            GameUI.updateMinimap(playerGroup.position, playerFacingAngle, cameraAngleY);
            GameUI.updateHintCounter();
            minimapTimer = 0;
        }
    }
    Minigame.update(delta);
    Minigame.updateRescueChildren(delta);
    DayNight.updateStarTwinkle(clock.elapsedTime);

    if (composer) composer.render();
    else renderer.render(scene, camera);
}

// ── Start Screen ──
function createStartScreen() {
    const screen = document.createElement('div');
    screen.id = 'start-screen';
    // Use overflow:auto + flex-start + safe area top padding so content never gets clipped
    screen.style.cssText = `
        position:fixed; inset:0; z-index:300;
        background:
            radial-gradient(ellipse at top, rgba(96,165,250,0.15), transparent 60%),
            radial-gradient(ellipse at bottom, rgba(251,191,36,0.08), transparent 60%),
            linear-gradient(180deg, #020617 0%, #0f172a 50%, #1e293b 100%);
        font-family:'Inter',sans-serif; color:#fff;
        overflow-y:auto;
        -webkit-overflow-scrolling:touch;
    `;

    // Inner flex container with safe-area padding
    const inner = document.createElement('div');
    inner.style.cssText = `
        min-height:100%;
        width:100%;
        box-sizing:border-box;
        padding: max(20px, env(safe-area-inset-top, 0px)) max(20px, env(safe-area-inset-right, 0px)) max(20px, env(safe-area-inset-bottom, 0px)) max(20px, env(safe-area-inset-left, 0px));
        display:flex; flex-direction:column;
        align-items:center; justify-content:center;
        position:relative;
    `;
    screen.appendChild(inner);

    // Rain canvas (background layer, doesn't affect layout)
    const rainCanvas = document.createElement('canvas');
    rainCanvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;opacity:0.25;z-index:1;';
    rainCanvas.width = window.innerWidth;
    rainCanvas.height = window.innerHeight;
    inner.appendChild(rainCanvas);
    const rctx = rainCanvas.getContext('2d');
    const drops = Array.from({length: 50}, () => ({
        x: Math.random() * rainCanvas.width,
        y: Math.random() * rainCanvas.height,
        speed: 4 + Math.random() * 6,
        len: 8 + Math.random() * 12
    }));
    let rainAnim;
    const drawRain = () => {
        rctx.clearRect(0, 0, rainCanvas.width, rainCanvas.height);
        rctx.strokeStyle = 'rgba(150,200,255,0.4)';
        rctx.lineWidth = 1;
        drops.forEach(d => {
            rctx.beginPath();
            rctx.moveTo(d.x, d.y);
            rctx.lineTo(d.x, d.y + d.len);
            rctx.stroke();
            d.y += d.speed;
            if (d.y > rainCanvas.height) { d.y = -d.len; d.x = Math.random() * rainCanvas.width; }
        });
        rainAnim = requestAnimationFrame(drawRain);
    };
    drawRain();
    screen._rainCleanup = () => cancelAnimationFrame(rainAnim);

    // Detect compact landscape (mobile-style narrow height)
    const compact = window.innerHeight < 500;

    const content = document.createElement('div');
    content.style.cssText = 'position:relative; z-index:2; display:flex; flex-direction:column; align-items:center;';
    content.innerHTML = `
        <div style="
            width:${compact ? 56 : 80}px; height:${compact ? 56 : 80}px; border-radius:50%;
            background:linear-gradient(135deg,#1e3a8a,#0f172a);
            border:2px solid rgba(96,165,250,0.5);
            box-shadow:0 0 30px rgba(96,165,250,0.4), inset 0 0 15px rgba(96,165,250,0.2);
            display:flex; align-items:center; justify-content:center;
            margin-bottom:${compact ? 8 : 14}px;
            flex-shrink:0;
        ">
            <svg width="${compact ? 28 : 40}" height="${compact ? 28 : 40}" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 2L4 7v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V7l-8-5z"/>
                <path d="M9 12l2 2 4-4"/>
            </svg>
        </div>
        <div style="font-size:${compact ? 9 : 11}px; letter-spacing:${compact ? 5 : 7}px; color:#60a5fa; margin-bottom:${compact ? 4 : 8}px; font-weight:600;">DETECTIVE CHRONICLES</div>
        <h1 style="
            font-size:${compact ? 36 : 52}px; font-weight:900; letter-spacing:-2px; margin:0;
            background:linear-gradient(135deg,#ffffff 0%,#cbd5e1 50%,#fbbf24 100%);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            background-clip:text; text-shadow:0 4px 30px rgba(96,165,250,0.3);
            line-height:1;
        ">NIGHT HUNTER</h1>
        <div style="width:50%; height:1px; margin:${compact ? 10 : 16}px 0;
            background:linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);"></div>
        <p style="font-size:${compact ? 11 : 13}px; color:#94a3b8; margin:0 0 ${compact ? 14 : 22}px; letter-spacing:0.5px; text-align:center; max-width:400px; line-height:1.5;">
            도시의 어둠 속에서 사라진 아이들.<br/>당신만이 그들을 구할 수 있습니다.
        </p>
        <button id="start-btn" style="
            padding:${compact ? '10px 36px' : '13px 44px'}; border:none; border-radius:8px;
            background:linear-gradient(135deg,#1e40af,#2563eb,#3b82f6);
            color:#fff; font-size:${compact ? 13 : 14}px; font-weight:700; letter-spacing:2px;
            cursor:pointer; font-family:'Inter',sans-serif;
            box-shadow:0 6px 24px rgba(59,130,246,0.5);
            touch-action:manipulation;
            transition:transform 0.2s;
        ">START MISSION</button>
        <div style="margin-top:${compact ? 14 : 22}px; display:flex; gap:${compact ? 14 : 20}px; font-size:${compact ? 9 : 10}px; color:#64748b; letter-spacing:1.5px;">
            <span>WASD MOVE</span><span>·</span><span>SHIFT RUN</span><span>·</span><span>SPACE JUMP</span>
        </div>
    `;
    inner.appendChild(content);
    document.body.appendChild(screen);

    const btn = document.getElementById('start-btn');
    btn.addEventListener('mouseenter', () => { btn.style.transform = 'scale(1.04)'; });
    btn.addEventListener('mouseleave', () => { btn.style.transform = 'scale(1)'; });
    btn.addEventListener('click', startGame);
    btn.addEventListener('touchstart', e => { e.preventDefault(); startGame(); }, { passive: false });
}

function startGame() {
    const screen = document.getElementById('start-screen');
    if (screen) {
        screen.style.transition = 'opacity 0.5s';
        screen.style.opacity = '0';
        setTimeout(() => screen.remove(), 500);
    }

    SoundManager.init();
    SoundManager.playBGM('day');

    showMessage('📻 도시 어딘가에 아이들이 납치되어 있습니다.\n힌트를 찾아 수사를 시작하세요.');
    updateCamera();
    animate();
}

createStartScreen();
