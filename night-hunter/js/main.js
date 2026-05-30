// main.js — Game loop, camera, state management, player (Stage 1+2+3)

// ── Game State ──
const gameState = {
    health: 3,
    maxHealth: 3,
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

// ── Quality Tier System (상/중/하) ──
// Auto-selected by device, can downgrade on low FPS
const QUALITY = {
    HIGH:   { shadow: 2048, bloom: true, vignette: true, smaa: true,  pixelRatio: 2,   segments: 32 },
    MEDIUM: { shadow: 1024, bloom: true, vignette: false, smaa: false, pixelRatio: 1.5, segments: 24 },
    LOW:    { shadow: 512,  bloom: false, vignette: false, smaa: false, pixelRatio: 1.0, segments: 16 }
};
let qualityTier = isMobile ? 'MEDIUM' : 'HIGH';
let Q = QUALITY[qualityTier];
window.GameQuality = { get tier() { return qualityTier; }, get cfg() { return Q; } };

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 500);
const renderer = new THREE.WebGLRenderer({
    canvas: document.getElementById('gameCanvas'),
    antialias: true,
    powerPreference: 'high-performance'
});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, Q.pixelRatio));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
// r128 uses outputEncoding (newer r150+ uses outputColorSpace)
renderer.outputEncoding = THREE.sRGBEncoding;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.physicallyCorrectLights = false;

// ── Post-processing (EffectComposer) ──
let composer = null;
let bloomPass = null;
let smaaPass = null;
let vignettePass = null;

// Vignette shader (subtle darkened edges)
const VignetteShader = {
    uniforms: {
        tDiffuse: { value: null },
        offset: { value: 1.0 },
        darkness: { value: 1.1 }
    },
    vertexShader: `varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader: `
        uniform sampler2D tDiffuse; uniform float offset; uniform float darkness;
        varying vec2 vUv;
        void main(){
            vec4 tex = texture2D(tDiffuse, vUv);
            vec2 uv = (vUv - 0.5) * vec2(offset);
            float vig = smoothstep(0.8, 0.2, dot(uv, uv) * darkness);
            tex.rgb = mix(tex.rgb, tex.rgb * vig, 0.6);
            gl_FragColor = tex;
        }`
};

function buildComposer() {
    if (!THREE.EffectComposer || !THREE.RenderPass) return;
    try {
        composer = new THREE.EffectComposer(renderer);
        composer.addPass(new THREE.RenderPass(scene, camera));

        if (Q.bloom && THREE.UnrealBloomPass) {
            bloomPass = new THREE.UnrealBloomPass(
                new THREE.Vector2(window.innerWidth, window.innerHeight),
                0.25, 0.6, 0.85
            );
            composer.addPass(bloomPass);
        }
        // SMAA/Vignette removed for stability — Bloom is enough for atmosphere
    } catch (e) {
        console.warn('Postprocessing build failed, falling back to basic render:', e);
        composer = null;
    }
}
buildComposer();

window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    if (composer) composer.setSize(window.innerWidth, window.innerHeight);
});

// ── Lighting (stylized: warm sun / cool ambient, hemisphere fill) ──
const hemiLight = new THREE.HemisphereLight(0xbcd4ff, 0x6b5a3e, 0.55);
scene.add(hemiLight);

const ambientLight = new THREE.AmbientLight(0xffffff, 0.25);
scene.add(ambientLight);

const sunLight = new THREE.DirectionalLight(0xfff4e0, 1.15);
sunLight.position.set(80, 120, 60);
sunLight.castShadow = true;
sunLight.shadow.mapSize.width = Q.shadow;
sunLight.shadow.mapSize.height = Q.shadow;
sunLight.shadow.camera.near = 0.5;
sunLight.shadow.camera.far = 350;
sunLight.shadow.camera.left = -160;
sunLight.shadow.camera.right = 160;
sunLight.shadow.camera.top = 160;
sunLight.shadow.camera.bottom = -160;
sunLight.shadow.bias = -0.0005;
sunLight.shadow.normalBias = 0.02;
scene.add(sunLight);

// Rim/fill light for character separation (subtle cool backlight)
const rimLight = new THREE.DirectionalLight(0xaac4ff, 0.25);
rimLight.position.set(-60, 40, -80);
scene.add(rimLight);

// ── Create World ──
const { worldGroup, buildingData } = createWorld(scene);

// ── Player Character ──
const playerGroup = new THREE.Group();

function createPlayer() {
    // Articulated legs — hip group with thigh, knee group with shin + shoe
    const legMat = new THREE.MeshStandardMaterial({ color: 0x1a2a4a, roughness: 0.7, metalness: 0.1 });
    const shoeMat = new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.5 });

    function makeLeg(side) {
        const hip = new THREE.Group();
        hip.position.set(side * 0.16, 0.7, 0);

        const thigh = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.1, 0.36, 12), legMat);
        thigh.position.y = -0.18;
        thigh.castShadow = true;
        hip.add(thigh);

        const knee = new THREE.Group();
        knee.position.y = -0.36;
        const shin = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.09, 0.34, 12), legMat);
        shin.position.y = -0.17;
        shin.castShadow = true;
        knee.add(shin);
        const shoe = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.1, 0.3), shoeMat);
        shoe.position.set(0, -0.36, 0.05);
        shoe.castShadow = true;
        knee.add(shoe);
        hip.add(knee);

        hip.userData.partName = side < 0 ? 'leftLeg' : 'rightLeg';
        hip.userData.knee = knee;
        return hip;
    }
    playerGroup.add(makeLeg(-1));
    playerGroup.add(makeLeg(1));

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
    // Articulated arms — shoulder group with upper arm, elbow group with forearm + hand
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xffdbac, roughness: 0.6 });

    function makeArm(side) {
        const shoulder = new THREE.Group();
        shoulder.position.set(side * 0.34, 1.42, 0);
        shoulder.rotation.z = side * -0.08;

        const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.07, 0.32, 12), legMat);
        upper.position.y = -0.16;
        upper.castShadow = true;
        shoulder.add(upper);

        const elbow = new THREE.Group();
        elbow.position.y = -0.32;
        const forearm = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.06, 0.3, 12), legMat);
        forearm.position.y = -0.15;
        forearm.castShadow = true;
        elbow.add(forearm);
        const hand = new THREE.Mesh(new THREE.SphereGeometry(0.08, 12, 12), skinMat);
        hand.position.y = -0.3;
        elbow.add(hand);
        shoulder.add(elbow);

        shoulder.userData.partName = side < 0 ? 'leftArm' : 'rightArm';
        shoulder.userData.elbow = elbow;
        return shoulder;
    }
    playerGroup.add(makeArm(-1));
    playerGroup.add(makeArm(1));

    // Head
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.28, 32, 32), skinMat);
    head.position.set(0, 1.68, 0);
    head.castShadow = true;
    playerGroup.add(head);

    // Subtle cheek blush (smaller, softer)
    const cheekMat = new THREE.MeshStandardMaterial({ color: 0xffa8a8, transparent: true, opacity: 0.4 });
    const leftCheek = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 10), cheekMat);
    leftCheek.position.set(-0.17, 1.62, 0.235);
    leftCheek.scale.set(1, 0.7, 0.3);
    playerGroup.add(leftCheek);
    const rightCheek = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 10), cheekMat);
    rightCheek.position.set(0.17, 1.62, 0.235);
    rightCheek.scale.set(1, 0.7, 0.3);
    playerGroup.add(rightCheek);

    // === REFINED FACE (referenced pixel art) ===
    // Clean anime-style female face with big blue eyes, twin braided pigtails

    // Eyebrows — thin slightly arched
    const browMat = new THREE.MeshStandardMaterial({ color: 0x1a0a00, roughness: 0.7 });
    const leftBrow = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.022, 0.015), browMat);
    leftBrow.position.set(-0.1, 1.76, 0.275);
    leftBrow.rotation.z = 0.12;
    playerGroup.add(leftBrow);
    const rightBrow = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.022, 0.015), browMat);
    rightBrow.position.set(0.1, 1.76, 0.275);
    rightBrow.rotation.z = -0.12;
    playerGroup.add(rightBrow);

    // BIG BLUE eyes (anime style — larger ratio)
    const eyeWhiteMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });
    const eyeBlueMat = new THREE.MeshStandardMaterial({ color: 0x3a82d4, roughness: 0.4 });
    const eyePupilMat = new THREE.MeshStandardMaterial({ color: 0x0a1a3a, roughness: 0.3 });
    const highlightMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.3 });

    // Eye whites (bigger)
    const lEyeW = new THREE.Mesh(new THREE.SphereGeometry(0.078, 16, 16), eyeWhiteMat);
    lEyeW.position.set(-0.105, 1.69, 0.245);
    lEyeW.scale.set(1, 1.1, 0.6);
    playerGroup.add(lEyeW);
    const rEyeW = new THREE.Mesh(new THREE.SphereGeometry(0.078, 16, 16), eyeWhiteMat);
    rEyeW.position.set(0.105, 1.69, 0.245);
    rEyeW.scale.set(1, 1.1, 0.6);
    playerGroup.add(rEyeW);

    // Blue iris (large)
    const lIris = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 12), eyeBlueMat);
    lIris.position.set(-0.105, 1.685, 0.295);
    lIris.scale.set(1, 1, 0.4);
    playerGroup.add(lIris);
    const rIris = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 12), eyeBlueMat);
    rIris.position.set(0.105, 1.685, 0.295);
    rIris.scale.set(1, 1, 0.4);
    playerGroup.add(rIris);

    // Pupils (small dark center)
    const lPupil = new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 10), eyePupilMat);
    lPupil.position.set(-0.105, 1.685, 0.31);
    playerGroup.add(lPupil);
    const rPupil = new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 10), eyePupilMat);
    rPupil.position.set(0.105, 1.685, 0.31);
    playerGroup.add(rPupil);

    // Sparkle highlights (top-left of each eye)
    const lHi = new THREE.Mesh(new THREE.SphereGeometry(0.018, 8, 8), highlightMat);
    lHi.position.set(-0.12, 1.705, 0.318);
    playerGroup.add(lHi);
    const rHi = new THREE.Mesh(new THREE.SphereGeometry(0.018, 8, 8), highlightMat);
    rHi.position.set(0.09, 1.705, 0.318);
    playerGroup.add(rHi);

    // Small lower highlights
    const lHi2 = new THREE.Mesh(new THREE.SphereGeometry(0.008, 6, 6), highlightMat);
    lHi2.position.set(-0.09, 1.67, 0.315);
    playerGroup.add(lHi2);
    const rHi2 = new THREE.Mesh(new THREE.SphereGeometry(0.008, 6, 6), highlightMat);
    rHi2.position.set(0.12, 1.67, 0.315);
    playerGroup.add(rHi2);

    // Nose — minimal (small subtle bump)
    const nose = new THREE.Mesh(
        new THREE.SphereGeometry(0.018, 8, 8),
        new THREE.MeshStandardMaterial({ color: 0xe8a888, roughness: 0.6 })
    );
    nose.position.set(0, 1.625, 0.295);
    nose.scale.set(1, 0.8, 0.7);
    playerGroup.add(nose);

    // Mouth — small smile (curved line via box rotated)
    const mouthMat = new THREE.MeshStandardMaterial({ color: 0xc04060, roughness: 0.5 });
    const mouth = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.018, 0.012), mouthMat);
    mouth.position.set(0, 1.55, 0.295);
    playerGroup.add(mouth);
    // Tiny upturned corners (smile)
    const lCorner = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.018, 0.012), mouthMat);
    lCorner.position.set(-0.045, 1.555, 0.293);
    lCorner.rotation.z = 0.35;
    playerGroup.add(lCorner);
    const rCorner = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.018, 0.012), mouthMat);
    rCorner.position.set(0.045, 1.555, 0.293);
    rCorner.rotation.z = -0.35;
    playerGroup.add(rCorner);

    // === HAIR — positioned high + back so face stays exposed ===
    const hairMat = new THREE.MeshStandardMaterial({ color: 0x1a0e08, roughness: 0.65 });

    // Top cap — small, high, slightly back so doesn't reach face front
    const hairCap = new THREE.Mesh(
        new THREE.SphereGeometry(0.29, 24, 24, 0, Math.PI * 2, 0, Math.PI * 0.55),
        hairMat
    );
    hairCap.position.set(0, 1.82, -0.05);
    hairCap.castShadow = true;
    playerGroup.add(hairCap);

    // Back hair (hangs behind head, doesn't touch face)
    const backHair = new THREE.Mesh(
        new THREE.BoxGeometry(0.42, 0.4, 0.18),
        hairMat
    );
    backHair.position.set(0, 1.6, -0.2);
    backHair.castShadow = true;
    playerGroup.add(backHair);

    // Bangs — only over forehead (above brows, not reaching eyes)
    const bangsCenter = new THREE.Mesh(
        new THREE.BoxGeometry(0.4, 0.09, 0.1),
        hairMat
    );
    bangsCenter.position.set(0, 1.86, 0.24);
    bangsCenter.rotation.x = -0.18;
    playerGroup.add(bangsCenter);
    // Side wisps
    const lWisp = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.18, 0.06), hairMat);
    lWisp.position.set(-0.21, 1.77, 0.18);
    lWisp.rotation.z = -0.2;
    playerGroup.add(lWisp);
    const rWisp = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.18, 0.06), hairMat);
    rWisp.position.set(0.21, 1.77, 0.18);
    rWisp.rotation.z = 0.2;
    playerGroup.add(rWisp);

    // === TWIN BRAIDED PIGTAILS ===
    // Each braid = 3 segments stacked (slightly varied) to suggest texture
    function makeBraid(side) {
        const x = side * 0.32;
        const braidGroup = new THREE.Group();
        // Top junction (where pigtail attaches)
        const junction = new THREE.Mesh(
            new THREE.SphereGeometry(0.09, 12, 12),
            hairMat
        );
        junction.position.set(x, 1.55, -0.03);
        playerGroup.add(junction);

        // Hair tie (green ribbon as in pixel art)
        const tie = new THREE.Mesh(
            new THREE.BoxGeometry(0.13, 0.05, 0.08),
            new THREE.MeshStandardMaterial({ color: 0x4a9d4a, roughness: 0.6 })
        );
        tie.position.set(x, 1.5, -0.02);
        playerGroup.add(tie);

        // Braid segments (3 cylinders, each tapering)
        for (let i = 0; i < 3; i++) {
            const seg = new THREE.Mesh(
                new THREE.CylinderGeometry(0.075 - i * 0.012, 0.07 - i * 0.012, 0.22, 12),
                hairMat
            );
            seg.position.set(x, 1.4 - i * 0.22, -0.05 - i * 0.02);
            seg.castShadow = true;
            playerGroup.add(seg);
        }

        // Braid end (small bulb)
        const end = new THREE.Mesh(
            new THREE.SphereGeometry(0.055, 10, 10),
            hairMat
        );
        end.position.set(x, 0.74, -0.1);
        playerGroup.add(end);

        // Lower tie (green)
        const lowerTie = new THREE.Mesh(
            new THREE.BoxGeometry(0.1, 0.04, 0.06),
            new THREE.MeshStandardMaterial({ color: 0x4a9d4a })
        );
        lowerTie.position.set(x, 0.8, -0.09);
        playerGroup.add(lowerTie);
    }
    makeBraid(-1);
    makeBraid(1);

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
try { HintSystem.init(scene); } catch (e) { console.error('HintSystem.init failed:', e); }
try { EnemySystem.init(scene, buildingData); } catch (e) { console.error('EnemySystem.init failed:', e); }
try { Minigame.init(); } catch (e) { console.error('Minigame.init failed:', e); }
try { Shop.init(scene); } catch (e) { console.error('Shop.init failed:', e); }
try { NPCSystem.init(scene); } catch (e) { console.error('NPCSystem.init failed:', e); }
try { AmbientCity.init(scene); } catch (e) { console.error('AmbientCity.init failed:', e); }
try { GameUI.init(); } catch (e) { console.error('GameUI.init failed:', e); }

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

    // Police station auto-healing removed — must rely on energy drink item
    // Update stamina bar
    document.getElementById('stamina-fill').style.width = (gameState.stamina / gameState.maxStamina * 100) + '%';
    const staminaPct = gameState.stamina / gameState.maxStamina;
    const staminaFill = document.getElementById('stamina-fill');
    if (staminaPct > 0.5) staminaFill.style.background = 'linear-gradient(90deg, #22c55e, #4ade80)';
    else if (staminaPct > 0.2) staminaFill.style.background = 'linear-gradient(90deg, #eab308, #facc15)';
    else staminaFill.style.background = 'linear-gradient(90deg, #ef4444, #f87171)';
}

function animateWalk(time) {
    // Hip swing + knee bend (knee bends when leg is going forward)
    const hipSwing = Math.sin(time) * 0.5;
    // Knee bend: bend most when leg is at apex of forward swing
    const leftKneeBend = Math.max(0, Math.sin(time)) * 0.6;
    const rightKneeBend = Math.max(0, Math.sin(time + Math.PI)) * 0.6;
    // Arm swing (opposite to legs)
    const armSwing = -Math.sin(time) * 0.45;
    const leftElbowBend = Math.max(0, -Math.sin(time)) * 0.35 + 0.2;
    const rightElbowBend = Math.max(0, Math.sin(time)) * 0.35 + 0.2;

    playerGroup.children.forEach(child => {
        const name = child.userData.partName;
        if (name === 'leftLeg') {
            child.rotation.x = hipSwing;
            if (child.userData.knee) child.userData.knee.rotation.x = -leftKneeBend;
        }
        if (name === 'rightLeg') {
            child.rotation.x = -hipSwing;
            if (child.userData.knee) child.userData.knee.rotation.x = -rightKneeBend;
        }
        if (name === 'leftArm') {
            child.rotation.x = armSwing;
            if (child.userData.elbow) child.userData.elbow.rotation.x = -leftElbowBend;
        }
        if (name === 'rightArm') {
            child.rotation.x = -armSwing;
            if (child.userData.elbow) child.userData.elbow.rotation.x = -rightElbowBend;
        }
    });
}

function animateIdle(time) {
    playerGroup.children.forEach(child => {
        const name = child.userData.partName;
        if (name === 'body') {
            child.position.y = 1.1 + Math.sin(time * 1.5) * 0.01;
        }
        if (name === 'leftLeg' || name === 'rightLeg' || name === 'leftArm' || name === 'rightArm') {
            child.rotation.x *= 0.85;
            if (child.userData.knee) child.userData.knee.rotation.x *= 0.85;
            if (child.userData.elbow) {
                // Slight resting elbow bend
                child.userData.elbow.rotation.x += (-0.15 - child.userData.elbow.rotation.x) * 0.1;
            }
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

// ── FPS auto-quality downgrade ──
let fpsAccum = 0, fpsFrames = 0, fpsCheckTimer = 0, lowFpsStreak = 0;
function monitorFPS(delta) {
    fpsAccum += delta;
    fpsFrames++;
    fpsCheckTimer += delta;
    if (fpsCheckTimer >= 2) {
        const fps = fpsFrames / fpsAccum;
        fpsAccum = 0; fpsFrames = 0; fpsCheckTimer = 0;
        if (fps < 30) {
            lowFpsStreak++;
            if (lowFpsStreak >= 2) { downgradeQuality(); lowFpsStreak = 0; }
        } else {
            lowFpsStreak = 0;
        }
    }
}

function downgradeQuality() {
    if (qualityTier === 'HIGH') qualityTier = 'MEDIUM';
    else if (qualityTier === 'MEDIUM') qualityTier = 'LOW';
    else return; // already lowest
    Q = QUALITY[qualityTier];

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, Q.pixelRatio));
    sunLight.shadow.mapSize.width = Q.shadow;
    sunLight.shadow.mapSize.height = Q.shadow;
    if (sunLight.shadow.map) { sunLight.shadow.map.dispose(); sunLight.shadow.map = null; }
    if (!Q.bloom && bloomPass && composer) {
        const i = composer.passes.indexOf(bloomPass);
        if (i >= 0) composer.passes.splice(i, 1);
        bloomPass = null;
    }
    console.log('Quality downgraded to', qualityTier);
}

// ── Game Loop ──
let minimapTimer = 0;
function animate() {
    if (gameState.gameOver) return;
    requestAnimationFrame(animate);

    const now = performance.now();
    const delta = Math.min((now - lastTime) / 1000, 0.1);
    lastTime = now;
    monitorFPS(delta);

    if (gameState.health <= 0 && !Minigame.active) {
        Minigame.triggerGameOver();
        return;
    }

    minimapTimer += delta;

    if (!gameState.isPaused) {
        try { updatePlayer(delta); } catch(e) { console.warn('updatePlayer', e); }
        try { updateTimer(delta); } catch(e) { console.warn('updateTimer', e); }
        try { updateCamera(); } catch(e) { console.warn('updateCamera', e); }
        try { updateHUD(); } catch(e) { console.warn('updateHUD', e); }
        try { HintSystem.update(playerGroup.position, delta, clock.elapsedTime); } catch(e) { console.warn('HintSystem', e); }
        try { EnemySystem.update(playerGroup.position, delta, clock.elapsedTime); } catch(e) { console.warn('EnemySystem', e); }
        try { Shop.update(playerGroup.position); } catch(e) { console.warn('Shop', e); }
        try { NPCSystem.update(playerGroup.position, delta, clock.elapsedTime); } catch(e) { console.warn('NPCSystem', e); }
        try { if (typeof AmbientCity !== 'undefined') AmbientCity.update(delta, clock.elapsedTime); } catch(e) { console.warn('AmbientCity', e); }
        try { Minigame.checkCatchable(playerGroup.position); } catch(e) { console.warn('Minigame.check', e); }
        if (minimapTimer > 0.16) {
            try { GameUI.updateMinimap(playerGroup.position, playerFacingAngle, cameraAngleY); } catch(e) { console.warn('minimap', e); }
            try { GameUI.updateHintCounter(); } catch(e) {}
            minimapTimer = 0;
        }
    }
    try { Minigame.update(delta); } catch(e) { console.warn('Minigame.update', e); }
    try { Minigame.updateRescueChildren(delta); } catch(e) { console.warn('Minigame.rescue', e); }
    try { DayNight.updateStarTwinkle(clock.elapsedTime); } catch(e) {}

    // Render with composer fallback
    try {
        if (composer) composer.render();
        else renderer.render(scene, camera);
    } catch (e) {
        console.warn('Render failed, falling back:', e);
        composer = null;
        try { renderer.render(scene, camera); } catch (e2) { console.error('Renderer fatal:', e2); }
    }
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

    // Defensive: each step independently — failures in audio MUST NOT block render loop
    try { SoundManager.init(); } catch (e) { console.warn('SoundManager.init failed:', e); }
    try { SoundManager.playBGM('day'); } catch (e) { console.warn('SoundManager.playBGM failed:', e); }
    try { showMessage('📻 도시 어딘가에 아이들이 납치되어 있습니다.\n힌트를 찾아 수사를 시작하세요.'); } catch (e) {}
    try { updateCamera(); } catch (e) { console.warn('updateCamera failed:', e); }
    animate();
}

createStartScreen();
