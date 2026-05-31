// main.js — Game loop, camera, state management, player (Stage 1+2+3)

// ── Game State ──
const gameState = {
    playerName: '소윤',
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
scene.fog = new THREE.Fog(0xcfeaff, 60, 180);

const isMobile = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);

// ── Quality Tier System (상/중/하/최저) ──
// Auto-selected by device, can downgrade on low FPS
const QUALITY = {
    HIGH:   { shadow: 2048, shadowEnabled: true,  bloom: true,  fogFar: 220, far: 500, pixelRatio: 2,   segments: 32, antialias: true,  carCount: 6, walkerCount: 10 },
    MEDIUM: { shadow: 1024, shadowEnabled: true,  bloom: true,  fogFar: 160, far: 300, pixelRatio: 1.3, segments: 24, antialias: true,  carCount: 6, walkerCount: 10 },
    LOW:    { shadow: 0,    shadowEnabled: false, bloom: false, fogFar: 120, far: 200, pixelRatio: 1.0, segments: 16, antialias: false, carCount: 4, walkerCount: 6  },
    POTATO: { shadow: 0,    shadowEnabled: false, bloom: false, fogFar: 80,  far: 150, pixelRatio: 0.75, segments: 10, antialias: false, carCount: 2, walkerCount: 3  }
};
// Detect low-end mobile (older iPhones, low memory, low CPU count)
const lowEnd = (isMobile && navigator.deviceMemory && navigator.deviceMemory <= 4)
    || (isMobile && navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4)
    || (window.innerWidth * window.innerHeight < 700000);
const veryLowEnd = (isMobile && navigator.deviceMemory && navigator.deviceMemory <= 2)
    || (isMobile && navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 2);
let qualityTier = veryLowEnd ? 'POTATO' : (lowEnd ? 'LOW' : (isMobile ? 'MEDIUM' : 'HIGH'));
let Q = QUALITY[qualityTier];
window.GameQuality = { get tier() { return qualityTier; }, get cfg() { return Q; } };

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, Q.far);
scene.fog.far = Q.fogFar;
const renderer = new THREE.WebGLRenderer({
    canvas: document.getElementById('gameCanvas'),
    antialias: Q.antialias !== false,
    powerPreference: Q.pixelRatio <= 1 ? 'low-power' : 'high-performance'
});
renderer.setSize(window.innerWidth, window.innerHeight, true);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, Q.pixelRatio));
renderer.shadowMap.enabled = Q.shadowEnabled;
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

// === 강건한 리사이즈 (좌측 반쪽 노출 버그 수정) ===
// 모바일/iPad에서 layout이 안정화되기 전에 setSize가 호출되어 캔버스 크기가
// viewport보다 작게 잡히는 문제를 다중 trigger로 보정한다.
function resizeRendererToViewport() {
    const w = Math.max(window.innerWidth, document.documentElement.clientWidth);
    const h = Math.max(window.innerHeight, document.documentElement.clientHeight);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, true);  // updateStyle=true → CSS도 정확히 맞춤
    if (composer) composer.setSize(w, h);
    // Canvas CSS를 강제로 컨테이너에 맞춤 (Safari iOS 백업)
    const canvas = renderer.domElement;
    if (canvas) {
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.display = 'block';
    }
}
window.addEventListener('resize', resizeRendererToViewport);
window.addEventListener('orientationchange', () => {
    // Safari iOS는 orientationchange 직후 innerWidth가 즉시 갱신되지 않음 → 두 단계 재호출
    setTimeout(resizeRendererToViewport, 100);
    setTimeout(resizeRendererToViewport, 400);
});
window.addEventListener('load', () => setTimeout(resizeRendererToViewport, 50));
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) setTimeout(resizeRendererToViewport, 100);
});
// 게임 시작 직후 layout 안정화를 위해 RAF 안에서 한 번 더 호출
requestAnimationFrame(() => requestAnimationFrame(resizeRendererToViewport));

// ── Lighting (stylized: warm sun / cool ambient, hemisphere fill) ──
const hemiLight = new THREE.HemisphereLight(0xbcd4ff, 0x6b5a3e, 0.55);
scene.add(hemiLight);

const ambientLight = new THREE.AmbientLight(0xffffff, 0.25);
scene.add(ambientLight);

const sunLight = new THREE.DirectionalLight(0xfff4e0, 1.15);
sunLight.position.set(80, 120, 60);
sunLight.castShadow = Q.shadowEnabled;
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

// === CHARACTER CONFIGS ===
const CHARACTERS = {
    soyun: {
        name: '소윤',
        title: '베테랑 형사',
        desc: '도시의 어둠을 비추는 신예 강력반.\n갈색 눈빛으로 진실을 꿰뚫는다.',
        hairStyle: 'long',           // long flowing
        hairColor: 0x5a3a1f,          // warm brown
        hairHighlight: 0x7a5230,
        eyeColor: 0x7a4d28,           // brown
        pupilColor: 0x2a1408,
        browColor: 0x3a2010,
        lipColor: 0xc97560,           // peach
        accessory: 'redClip'          // red hair clip
    },
    hayun: {
        name: '하윤',
        title: '통신반 형사',
        desc: '날카로운 푸른 눈빛.\n헤드셋으로 본부와 끊임없이 소통한다.',
        hairStyle: 'braids',          // twin braids
        hairColor: 0x4a2a10,          // darker brown
        hairHighlight: 0x6a4020,
        eyeColor: 0x3a82d4,           // blue
        pupilColor: 0x0a1a3a,
        browColor: 0x2a1808,
        lipColor: 0xd07060,           // peach-pink
        accessory: 'headset'          // headset with mic
    }
};

let currentCharacter = 'soyun'; // default; may be changed by selection screen
window.CHARACTERS = CHARACTERS;
window.gameState = gameState; // expose for debugging + downstream UI updates

function createPlayer() {
    buildCharacter(CHARACTERS[currentCharacter]);
}

function swapCharacter(charId) {
    if (!CHARACTERS[charId]) return;
    currentCharacter = charId;
    gameState.playerName = CHARACTERS[charId].name;
    // Clear current player meshes
    while (playerGroup.children.length > 0) {
        const child = playerGroup.children[0];
        playerGroup.remove(child);
        if (child.geometry) child.geometry.dispose();
        if (child.material) child.material.dispose();
    }
    // Rebuild with new config
    buildCharacter(CHARACTERS[charId]);
}
window.swapCharacter = swapCharacter;

function buildCharacter(cfg) {
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
    // 소윤: warm brown brows matching hair
    const browMat = new THREE.MeshStandardMaterial({ color: cfg.browColor, roughness: 0.7 });
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
    // Warm brown eyes (per reference image — 소윤)
    const eyeBlueMat = new THREE.MeshStandardMaterial({ color: cfg.eyeColor, roughness: 0.4 });
    const eyePupilMat = new THREE.MeshStandardMaterial({ color: cfg.pupilColor, roughness: 0.3 });
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
    // 소윤: soft peach lips per reference
    const mouthMat = new THREE.MeshStandardMaterial({ color: cfg.lipColor, roughness: 0.4 });
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

    // === HAIR — 소윤: 따뜻한 갈색 (reference image) ===
    const hairMat = new THREE.MeshStandardMaterial({ color: cfg.hairColor, roughness: 0.55 });
    const hairHighlightMat = new THREE.MeshStandardMaterial({ color: cfg.hairHighlight, roughness: 0.5 });

    // Top cap
    const hairCap = new THREE.Mesh(
        new THREE.SphereGeometry(0.29, 24, 24, 0, Math.PI * 2, 0, Math.PI * 0.55),
        hairMat
    );
    hairCap.position.set(0, 1.82, -0.05);
    hairCap.castShadow = true;
    playerGroup.add(hairCap);

    // Back hair — longer, more volume (per reference, 가슴까지 오는 긴 머리)
    const backHair = new THREE.Mesh(
        new THREE.BoxGeometry(0.5, 0.7, 0.2),
        hairMat
    );
    backHair.position.set(0, 1.35, -0.22);
    backHair.castShadow = true;
    playerGroup.add(backHair);

    // Bangs — soft side-swept (이마 위쪽, 눈썹 가리지 않게)
    const bangsCenter = new THREE.Mesh(
        new THREE.BoxGeometry(0.36, 0.08, 0.08),
        hairMat
    );
    bangsCenter.position.set(0, 1.87, 0.245);
    bangsCenter.rotation.x = -0.22;
    playerGroup.add(bangsCenter);

    // Bangs highlight (lighter strands)
    const bangsHi = new THREE.Mesh(
        new THREE.BoxGeometry(0.15, 0.05, 0.08),
        hairHighlightMat
    );
    bangsHi.position.set(0.08, 1.88, 0.245);
    bangsHi.rotation.x = -0.2;
    playerGroup.add(bangsHi);

    // Side hair — falling down each side past shoulder
    const lSide = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.55, 0.12), hairMat);
    lSide.position.set(-0.25, 1.42, 0.02);
    lSide.castShadow = true;
    playerGroup.add(lSide);
    const rSide = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.55, 0.12), hairMat);
    rSide.position.set(0.25, 1.42, 0.02);
    rSide.castShadow = true;
    playerGroup.add(rSide);

    // Side wisps near face — 얼굴 옆쪽 침범 방지: x를 더 바깥으로, z를 더 뒤로
    const lWisp = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.18, 0.05), hairMat);
    lWisp.position.set(-0.255, 1.74, 0.12);
    lWisp.rotation.z = -0.18;
    playerGroup.add(lWisp);
    const rWisp = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.18, 0.05), hairMat);
    rWisp.position.set(0.255, 1.74, 0.12);
    rWisp.rotation.z = 0.18;
    playerGroup.add(rWisp);

    // === Accessory: red clip (소윤) or headset (하윤) ===
    if (cfg.accessory === 'redClip') {
        const clipMat = new THREE.MeshStandardMaterial({
            color: 0xcc1a1a, roughness: 0.35, metalness: 0.3,
            emissive: 0x440000, emissiveIntensity: 0.1
        });
        const hairClip = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.04, 0.04), clipMat);
        hairClip.position.set(0.22, 1.82, 0.21);
        hairClip.rotation.z = 0.3;
        playerGroup.add(hairClip);
        const clipBead = new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 10), clipMat);
        clipBead.position.set(0.26, 1.83, 0.215);
        playerGroup.add(clipBead);
    } else if (cfg.accessory === 'headset') {
        const headsetMat = new THREE.MeshStandardMaterial({ color: 0x1a1a1a, roughness: 0.5, metalness: 0.4 });
        // Earpiece (right side)
        const earpiece = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 16), headsetMat);
        earpiece.position.set(0.29, 1.66, 0.05);
        playerGroup.add(earpiece);
        // Mic boom arm
        const micArm = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.18, 8), headsetMat);
        micArm.position.set(0.18, 1.58, 0.16);
        micArm.rotation.z = -0.6;
        playerGroup.add(micArm);
        // Mic head
        const micHead = new THREE.Mesh(new THREE.SphereGeometry(0.024, 12, 12), headsetMat);
        micHead.position.set(0.08, 1.52, 0.22);
        playerGroup.add(micHead);
        // Mic ball cover (foam)
        const foam = new THREE.Mesh(
            new THREE.SphereGeometry(0.032, 12, 12),
            new THREE.MeshStandardMaterial({ color: 0x444444, roughness: 0.95 })
        );
        foam.position.set(0.08, 1.52, 0.22);
        playerGroup.add(foam);
    }

    // === HAIR STYLE: 'long' (소윤) or 'braids' (하윤) ===
    if (cfg.hairStyle === 'braids') {
        // 하윤: twin braided pigtails with green ribbon ties
        const ribbonMat = new THREE.MeshStandardMaterial({ color: 0x4a9d4a, roughness: 0.6 });
        function makeBraid(side) {
            const x = side * 0.27;
            // Top junction
            const junction = new THREE.Mesh(new THREE.SphereGeometry(0.085, 14, 14), hairMat);
            junction.position.set(x, 1.55, -0.04);
            playerGroup.add(junction);
            // Upper ribbon tie
            const tie = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.05, 0.08), ribbonMat);
            tie.position.set(x, 1.48, -0.03);
            playerGroup.add(tie);
            // Braid segments (3 cylinders, each tapering for woven look)
            for (let i = 0; i < 4; i++) {
                const seg = new THREE.Mesh(
                    new THREE.CylinderGeometry(0.072 - i * 0.011, 0.066 - i * 0.011, 0.21, 12),
                    hairMat
                );
                seg.position.set(x, 1.36 - i * 0.21, -0.06 - i * 0.01);
                seg.castShadow = true;
                playerGroup.add(seg);
                // Highlight stripe (woven texture)
                if (i % 2 === 0) {
                    const stripe = new THREE.Mesh(
                        new THREE.BoxGeometry(0.04, 0.06, 0.04),
                        hairHighlightMat
                    );
                    stripe.position.set(x, 1.36 - i * 0.21, -0.04);
                    playerGroup.add(stripe);
                }
            }
            // Braid end bulb
            const end = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 10), hairMat);
            end.position.set(x, 0.54, -0.1);
            playerGroup.add(end);
            // Lower ribbon
            const lowerTie = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.04, 0.06), ribbonMat);
            lowerTie.position.set(x, 0.6, -0.09);
            playerGroup.add(lowerTie);
        }
        makeBraid(-1);
        makeBraid(1);
    } else {
        // 소윤: 긴 생머리 (default — long flowing hair down past shoulders)
        function makeLongHair(side) {
            const x = side * 0.22;
            const upper = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.45, 0.1), hairMat);
            upper.position.set(x, 1.2, -0.08); upper.castShadow = true;
            playerGroup.add(upper);
            const lower = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.4, 0.09), hairMat);
            lower.position.set(x, 0.78, -0.12); lower.castShadow = true;
            playerGroup.add(lower);
            const hi = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.55, 0.04), hairHighlightMat);
            hi.position.set(x + side * 0.04, 1.0, -0.06);
            playerGroup.add(hi);
        }
        makeLongHair(-1);
        makeLongHair(1);
    }

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

    if (!playerGroup.parent) {
        playerGroup.position.set(0, 0, 92);
        scene.add(playerGroup);
    }
}

createPlayer();

// ── Day/Night System Init ──
DayNight.init(scene, playerGroup);

// ── Camera ──
let cameraAngleY = 0;
let cameraAngleX = 0.5;          // 기본 각도를 더 아래로 (0.3 → 0.5, 약 28도 ↓)
let cameraDistance = 9;          // 줌 가능하도록 변수화 (range 4~18)
const CAMERA_DISTANCE_MIN = 4;
const CAMERA_DISTANCE_MAX = 18;
let cameraHeight = 4;            // 거리에 비례하여 자동 조정됨
let playerFacingAngle = 0;

function updateCamera() {
    const px = playerGroup.position.x;
    const py = playerGroup.position.y;
    const pz = playerGroup.position.z;

    // 거리에 따라 높이도 자연스럽게 조정 (가까울수록 낮게)
    cameraHeight = 1.5 + cameraDistance * 0.35;
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

// Run button (Jump 버튼 제거됨)
const runBtn = document.createElement('button');
runBtn.id = 'run-btn';
runBtn.textContent = 'RUN';

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
#run-btn {
    position: fixed;
    right: calc(80px + env(safe-area-inset-right, 0px));
    bottom: calc(25px + env(safe-area-inset-bottom, 0px));
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: 2px solid rgba(255,160,0,0.5);
    background: rgba(255,160,0,0.2);
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
#run-btn.active { background: rgba(255,160,0,0.5); transform: scale(0.92); }
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
            cameraAngleX = Math.max(0.05, Math.min(1.4, cameraAngleX + dy * 0.005));
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
    cameraAngleX = Math.max(0.05, Math.min(1.4, cameraAngleX + dy * 0.005));
    lastTouchX = e.clientX;
    lastTouchY = e.clientY;
});
canvas.addEventListener('mouseup', () => { mouseDown = false; });
canvas.addEventListener('contextmenu', e => e.preventDefault());

// === 줌 인/아웃 (휠 + 모바일 핀치) ===
canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const dir = Math.sign(e.deltaY);    // +1 = 줌아웃, -1 = 줌인
    cameraDistance = Math.max(CAMERA_DISTANCE_MIN,
        Math.min(CAMERA_DISTANCE_MAX, cameraDistance + dir * 0.8));
}, { passive: false });

// 모바일 핀치 줌 (두 손가락 거리 변화로 줌)
let pinchStartDist = 0;
let pinchStartCamDist = 0;
canvas.addEventListener('touchstart', e => {
    if (e.touches.length === 2) {
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        pinchStartDist = Math.sqrt(dx * dx + dy * dy);
        pinchStartCamDist = cameraDistance;
    }
}, { passive: true });
canvas.addEventListener('touchmove', e => {
    if (e.touches.length === 2 && pinchStartDist > 0) {
        e.preventDefault();
        const dx = e.touches[0].clientX - e.touches[1].clientX;
        const dy = e.touches[0].clientY - e.touches[1].clientY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const ratio = pinchStartDist / dist;  // 손가락이 벌어지면 ratio < 1 (줌인)
        cameraDistance = Math.max(CAMERA_DISTANCE_MIN,
            Math.min(CAMERA_DISTANCE_MAX, pinchStartCamDist * ratio));
    }
}, { passive: false });
canvas.addEventListener('touchend', e => {
    if (e.touches.length < 2) pinchStartDist = 0;
});

// 앱 전환 / 탭 숨김 시 카메라 드래그 상태 초기화
// (포인터/터치 업 이벤트가 누락되어 카메라가 고정되는 버그 방지)
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) return;
    mouseDown = false;
    cameraDragging = false;
    cameraTouchId = null;
    pinchStartDist = 0;
});
window.addEventListener('blur', () => {
    mouseDown = false;
    cameraDragging = false;
    cameraTouchId = null;
    pinchStartDist = 0;
});

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
    else if (qualityTier === 'LOW') qualityTier = 'POTATO';
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
            try { GameUI.drawFullMap(playerGroup.position, playerFacingAngle); } catch(e) {}
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

    try { SoundManager.init(); } catch (e) { console.warn('SoundManager.init failed:', e); }
    try { SoundManager.playBGM('day'); } catch (e) { console.warn('SoundManager.playBGM failed:', e); }

    // Show character select first, then wanted poster, then animate
    try { showCharacterSelect(); } catch (e) {
        console.warn('Char select failed:', e);
        try { updateCamera(); } catch (e2) {}
        try { showWantedPoster(true); } catch (e3) { animate(); }
    }
}

// === CHARACTER SELECT SCREEN ===
function showCharacterSelect() {
    const modal = document.createElement('div');
    modal.id = 'char-select-modal';
    modal.style.cssText = `
        position:fixed; inset:0; z-index:280;
        background: linear-gradient(135deg, #0a1628 0%, #1a1a3a 100%);
        display:flex; flex-direction:column; align-items:center; justify-content:center;
        font-family:'Inter',sans-serif; color:#fff;
        padding:env(safe-area-inset-top, 16px) env(safe-area-inset-right, 16px) env(safe-area-inset-bottom, 16px) env(safe-area-inset-left, 16px);
        overflow-y:auto;
    `;

    // Portrait SVG factory
    function portrait(charId) {
        if (charId === 'soyun') {
            // 소윤: long brown hair, brown eyes, red hair clip
            return `<svg viewBox="0 0 200 240" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
                <defs>
                    <radialGradient id="bgS" cx="50%" cy="40%"><stop offset="0%" stop-color="#3a2a4a"/><stop offset="100%" stop-color="#1a0e20"/></radialGradient>
                </defs>
                <rect width="200" height="240" fill="url(#bgS)"/>
                <!-- shoulders/uniform -->
                <path d="M 15 240 L 15 195 Q 100 175, 185 195 L 185 240 Z" fill="#1a2a4a"/>
                <!-- collar -->
                <path d="M 75 192 L 100 215 L 125 192 L 125 200 L 75 200 Z" fill="#fff"/>
                <!-- tie -->
                <path d="M 95 200 L 100 240 L 105 240 L 110 200 Z" fill="#0d1b4a"/>
                <!-- badge -->
                <circle cx="100" cy="225" r="8" fill="#d4a800" stroke="#5a3a00" stroke-width="1"/>
                <text x="100" y="228" text-anchor="middle" font-size="6" fill="#5a3a00">★</text>
                <!-- BACK hair (long, behind shoulders) -->
                <path d="M 60 80 Q 50 130, 45 200 L 60 220 L 60 130 Z" fill="#5a3a1f"/>
                <path d="M 140 80 Q 150 130, 155 200 L 140 220 L 140 130 Z" fill="#5a3a1f"/>
                <!-- Face -->
                <ellipse cx="100" cy="115" rx="38" ry="48" fill="#f0d4b0" stroke="#a07a50" stroke-width="0.7"/>
                <!-- Hair top -->
                <path d="M 62 95 Q 100 35, 138 95 L 138 75 Q 100 50, 62 75 Z" fill="#5a3a1f"/>
                <!-- Side hair -->
                <path d="M 62 75 Q 55 110, 65 150 L 78 150 L 75 90 Z" fill="#5a3a1f"/>
                <path d="M 138 75 Q 145 110, 135 150 L 122 150 L 125 90 Z" fill="#5a3a1f"/>
                <!-- Bangs (soft, side swept) -->
                <path d="M 65 78 Q 100 60, 135 78 L 130 95 Q 100 78, 70 95 Z" fill="#5a3a1f"/>
                <!-- Hair highlight -->
                <path d="M 85 80 Q 100 70, 115 80 L 113 95 Q 100 88, 87 95 Z" fill="#7a5230" opacity="0.7"/>
                <!-- Red hair clip (right side) -->
                <rect x="125" y="78" width="14" height="6" fill="#cc1a1a" rx="1"/>
                <circle cx="142" cy="81" r="3" fill="#cc1a1a"/>
                <!-- Eyebrows -->
                <path d="M 78 105 Q 87 102, 95 106" fill="none" stroke="#3a2010" stroke-width="2.5" stroke-linecap="round"/>
                <path d="M 105 106 Q 113 102, 122 105" fill="none" stroke="#3a2010" stroke-width="2.5" stroke-linecap="round"/>
                <!-- Eyes (BROWN) -->
                <ellipse cx="85" cy="118" rx="6" ry="4" fill="#fff"/>
                <ellipse cx="115" cy="118" rx="6" ry="4" fill="#fff"/>
                <circle cx="85" cy="118" r="3.5" fill="#7a4d28"/>
                <circle cx="115" cy="118" r="3.5" fill="#7a4d28"/>
                <circle cx="85" cy="118" r="1.8" fill="#2a1408"/>
                <circle cx="115" cy="118" r="1.8" fill="#2a1408"/>
                <circle cx="83" cy="116" r="0.9" fill="#fff"/>
                <circle cx="113" cy="116" r="0.9" fill="#fff"/>
                <!-- Lashes -->
                <path d="M 79 115 Q 85 112, 91 115" fill="none" stroke="#1a0a00" stroke-width="0.8"/>
                <path d="M 109 115 Q 115 112, 121 115" fill="none" stroke="#1a0a00" stroke-width="0.8"/>
                <!-- Cheek blush -->
                <ellipse cx="75" cy="130" rx="6" ry="3" fill="#ff9090" opacity="0.4"/>
                <ellipse cx="125" cy="130" rx="6" ry="3" fill="#ff9090" opacity="0.4"/>
                <!-- Nose -->
                <path d="M 100 125 L 97 138 Q 100 140, 103 138 Z" fill="#e0b890"/>
                <!-- Mouth (peach) -->
                <path d="M 92 148 Q 100 152, 108 148" fill="none" stroke="#c97560" stroke-width="2.2" stroke-linecap="round"/>
                <!-- Hat -->
                <ellipse cx="100" cy="68" rx="56" ry="11" fill="#0d1b2a"/>
                <rect x="60" y="38" width="80" height="32" fill="#0d1b2a" rx="6"/>
                <rect x="60" y="58" width="80" height="6" fill="#FFD700"/>
                <!-- Hat badge -->
                <circle cx="100" cy="52" r="9" fill="#FFD700"/>
                <text x="100" y="55" text-anchor="middle" font-size="10" fill="#1a1a4a" font-weight="bold">★</text>
            </svg>`;
        } else {
            // 하윤: twin braids, blue eyes, headset
            return `<svg viewBox="0 0 200 240" width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
                <defs>
                    <radialGradient id="bgH" cx="50%" cy="40%"><stop offset="0%" stop-color="#2a3a5a"/><stop offset="100%" stop-color="#0e1828"/></radialGradient>
                </defs>
                <rect width="200" height="240" fill="url(#bgH)"/>
                <!-- shoulders/uniform -->
                <path d="M 15 240 L 15 195 Q 100 175, 185 195 L 185 240 Z" fill="#1a2a4a"/>
                <!-- collar -->
                <path d="M 75 192 L 100 215 L 125 192 L 125 200 L 75 200 Z" fill="#fff"/>
                <path d="M 95 200 L 100 240 L 105 240 L 110 200 Z" fill="#0d1b4a"/>
                <circle cx="100" cy="225" r="8" fill="#d4a800" stroke="#5a3a00" stroke-width="1"/>
                <text x="100" y="228" text-anchor="middle" font-size="6" fill="#5a3a00">★</text>
                <!-- Braided pigtails (LONG, both sides past shoulders) -->
                <!-- Left braid -->
                <g transform="translate(60, 110)">
                    ${[0,1,2,3].map(i => `<ellipse cx="0" cy="${i*22}" rx="11" ry="13" fill="#4a2a10"/>`).join('')}
                    ${[0,2].map(i => `<rect x="-5" y="${i*22}" width="10" height="6" fill="#6a4020" opacity="0.7"/>`).join('')}
                    <ellipse cx="0" cy="100" rx="9" ry="11" fill="#4a2a10"/>
                    <rect x="-6" y="-12" width="12" height="6" fill="#4a9d4a" rx="1"/>
                    <rect x="-5" y="106" width="10" height="5" fill="#4a9d4a" rx="1"/>
                </g>
                <!-- Right braid -->
                <g transform="translate(140, 110)">
                    ${[0,1,2,3].map(i => `<ellipse cx="0" cy="${i*22}" rx="11" ry="13" fill="#4a2a10"/>`).join('')}
                    ${[0,2].map(i => `<rect x="-5" y="${i*22}" width="10" height="6" fill="#6a4020" opacity="0.7"/>`).join('')}
                    <ellipse cx="0" cy="100" rx="9" ry="11" fill="#4a2a10"/>
                    <rect x="-6" y="-12" width="12" height="6" fill="#4a9d4a" rx="1"/>
                    <rect x="-5" y="106" width="10" height="5" fill="#4a9d4a" rx="1"/>
                </g>
                <!-- Face -->
                <ellipse cx="100" cy="115" rx="38" ry="48" fill="#f0d4b0" stroke="#a07a50" stroke-width="0.7"/>
                <!-- Hair top -->
                <path d="M 62 95 Q 100 35, 138 95 L 138 75 Q 100 50, 62 75 Z" fill="#4a2a10"/>
                <!-- Bangs (centered) -->
                <path d="M 70 78 Q 100 62, 130 78 L 128 96 Q 100 80, 72 96 Z" fill="#4a2a10"/>
                <!-- Hair highlight -->
                <path d="M 88 78 Q 100 70, 112 78 L 110 95 Q 100 86, 90 95 Z" fill="#6a4020" opacity="0.7"/>
                <!-- Eyebrows -->
                <path d="M 78 105 Q 87 102, 95 106" fill="none" stroke="#2a1808" stroke-width="2.5" stroke-linecap="round"/>
                <path d="M 105 106 Q 113 102, 122 105" fill="none" stroke="#2a1808" stroke-width="2.5" stroke-linecap="round"/>
                <!-- Eyes (BLUE) -->
                <ellipse cx="85" cy="118" rx="6" ry="4.5" fill="#fff"/>
                <ellipse cx="115" cy="118" rx="6" ry="4.5" fill="#fff"/>
                <circle cx="85" cy="118" r="3.8" fill="#3a82d4"/>
                <circle cx="115" cy="118" r="3.8" fill="#3a82d4"/>
                <circle cx="85" cy="118" r="1.8" fill="#0a1a3a"/>
                <circle cx="115" cy="118" r="1.8" fill="#0a1a3a"/>
                <circle cx="83" cy="116" r="1" fill="#fff"/>
                <circle cx="113" cy="116" r="1" fill="#fff"/>
                <!-- Lashes -->
                <path d="M 78 115 Q 85 111, 92 115" fill="none" stroke="#1a0a00" stroke-width="1"/>
                <path d="M 108 115 Q 115 111, 122 115" fill="none" stroke="#1a0a00" stroke-width="1"/>
                <!-- Cheek blush + freckles -->
                <ellipse cx="75" cy="132" rx="7" ry="3" fill="#ff9090" opacity="0.45"/>
                <ellipse cx="125" cy="132" rx="7" ry="3" fill="#ff9090" opacity="0.45"/>
                <circle cx="78" cy="130" r="0.8" fill="#a06040"/>
                <circle cx="82" cy="134" r="0.8" fill="#a06040"/>
                <circle cx="118" cy="130" r="0.8" fill="#a06040"/>
                <circle cx="122" cy="134" r="0.8" fill="#a06040"/>
                <!-- Nose -->
                <path d="M 100 125 L 97 138 Q 100 140, 103 138 Z" fill="#e0b890"/>
                <!-- Slight smile -->
                <path d="M 92 148 Q 100 153, 108 148" fill="none" stroke="#d07060" stroke-width="2.2" stroke-linecap="round"/>
                <!-- Headset earpiece (right ear) -->
                <ellipse cx="140" cy="120" rx="6" ry="8" fill="#1a1a1a"/>
                <!-- Mic boom -->
                <path d="M 140 124 Q 130 138, 120 148" fill="none" stroke="#1a1a1a" stroke-width="2.5"/>
                <circle cx="118" cy="150" r="4" fill="#444"/>
                <!-- Hat -->
                <ellipse cx="100" cy="68" rx="56" ry="11" fill="#0d1b2a"/>
                <rect x="60" y="38" width="80" height="32" fill="#0d1b2a" rx="6"/>
                <rect x="60" y="58" width="80" height="6" fill="#FFD700"/>
                <!-- Hat badge -->
                <circle cx="100" cy="52" r="9" fill="#FFD700"/>
                <text x="100" y="55" text-anchor="middle" font-size="10" fill="#1a1a4a" font-weight="bold">★</text>
            </svg>`;
        }
    }

    function card(charId) {
        const c = CHARACTERS[charId];
        // 우선순위: PNG → SVG → 인라인 SVG 폴백
        // assets/portrait-<charId>.png 가 있으면 자동 사용, 없으면 SVG로 폴백
        const pngSrc = `assets/portrait-${charId}.png`;
        const svgSrc = `assets/portrait-${charId}.svg`;
        return `
            <div class="char-card" data-char="${charId}" style="
                width:42vw; max-width:280px; min-width:160px;
                background:linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
                border:2px solid rgba(255,255,255,0.15); border-radius:12px;
                padding:12px; margin:0 8px; cursor:pointer;
                display:flex; flex-direction:column; align-items:center;
                transition:all 0.25s;
                touch-action:manipulation;
            ">
                <div style="
                    width:100%; aspect-ratio:400/520; border-radius:10px;
                    overflow:hidden; box-shadow:0 6px 24px rgba(0,0,0,0.5);
                    border:1px solid rgba(255,255,255,0.1); background:#0a0e18;
                ">
                    <img src="${pngSrc}" alt="${c.name}" style="width:100%; height:100%; display:block; object-fit:cover;"
                         onerror="if(this.dataset.fb!=='svg'){this.dataset.fb='svg';this.src='${svgSrc}';}else{this.style.display='none';this.parentNode.insertAdjacentHTML('beforeend', window._portraitFallback ? window._portraitFallback('${charId}') : '');}"/>
                </div>
                <div style="margin-top:10px; font-size:18px; font-weight:900; letter-spacing:1px;">${c.name} <span style="color:#fbbf24;">형사</span></div>
                <div style="font-size:11px; color:#94a3b8; letter-spacing:2px; margin-top:2px;">${c.title}</div>
                <div style="margin-top:8px; font-size:11px; color:#cbd5e1; line-height:1.5; text-align:center; white-space:pre-line; opacity:0.85;">${c.desc}</div>
            </div>
        `;
    }
    // Expose inline-SVG fallback in case the SVG file fails to load
    window._portraitFallback = portrait;

    modal.innerHTML = `
        <div style="font-size:11px; letter-spacing:8px; color:#60a5fa; margin-bottom:6px; font-weight:600;">CHARACTER SELECT</div>
        <h2 style="margin:0 0 16px; font-size:32px; letter-spacing:-1px;
            background:linear-gradient(135deg,#fff,#cbd5e1,#fbbf24);
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            background-clip:text; font-weight:900;
        ">담당 형사를 선택하세요</h2>
        <div style="display:flex; justify-content:center; flex-wrap:wrap; gap:8px; width:100%; max-width:680px;">
            ${card('soyun')}
            ${card('hayun')}
        </div>
        <div style="margin-top:18px; font-size:11px; color:#64748b; letter-spacing:2px;">탭하여 선택</div>
    `;
    document.body.appendChild(modal);

    // Hover/select styling + click handlers
    modal.querySelectorAll('.char-card').forEach(card => {
        const select = () => {
            const charId = card.dataset.char;
            modal.querySelectorAll('.char-card').forEach(c => {
                c.style.borderColor = 'rgba(255,255,255,0.15)';
                c.style.transform = 'scale(1)';
            });
            card.style.borderColor = '#fbbf24';
            card.style.transform = 'scale(1.03)';
            card.style.boxShadow = '0 0 30px rgba(251,191,36,0.4)';
            // CRITICAL: set playerName SYNCHRONOUSLY on click — no race with downstream UI
            currentCharacter = charId;
            if (CHARACTERS[charId]) {
                gameState.playerName = CHARACTERS[charId].name;
            }
            // Robust audio unlock: this click is a guaranteed user gesture
            try {
                if (typeof SoundManager !== 'undefined') {
                    SoundManager.init();
                    if (SoundManager.ctx && SoundManager.ctx.state !== 'running') {
                        SoundManager.ctx.resume().catch(() => {});
                    }
                    SoundManager.playBGM('day');
                }
            } catch (e) { console.warn('BGM kick on charselect failed:', e); }
            // Confirm after brief highlight
            setTimeout(() => {
                modal.style.transition = 'opacity 0.4s';
                modal.style.opacity = '0';
                setTimeout(() => modal.remove(), 400);
                try { swapCharacter(charId); } catch (e) { console.warn('swapCharacter failed:', e); }
                try { updateCamera(); } catch (e) {}
                try { showWantedPoster(true); } catch (e) {
                    console.warn('Wanted poster failed:', e);
                    animate();
                }
            }, 400);
        };
        card.addEventListener('click', select);
        card.addEventListener('touchstart', e => { e.preventDefault(); select(); }, { passive: false });
        card.addEventListener('mouseenter', () => {
            card.style.borderColor = 'rgba(96,165,250,0.5)';
            card.style.transform = 'translateY(-4px)';
        });
        card.addEventListener('mouseleave', () => {
            card.style.borderColor = 'rgba(255,255,255,0.15)';
            card.style.transform = 'translateY(0)';
        });
    });
}
window.showCharacterSelect = showCharacterSelect;

// === WANTED POSTER (수배전단) ===
// Shown at game start as briefing, accessible later from inventory
function showWantedPoster(firstTime) {
    let modal = document.getElementById('wanted-poster-modal');
    if (modal) modal.remove();

    modal = document.createElement('div');
    modal.id = 'wanted-poster-modal';
    modal.style.cssText = `
        position:fixed; inset:0; z-index:250;
        background:rgba(0,0,0,0.85); backdrop-filter:blur(8px);
        display:flex; align-items:center; justify-content:center;
        padding:env(safe-area-inset-top, 10px) env(safe-area-inset-right, 10px) env(safe-area-inset-bottom, 10px) env(safe-area-inset-left, 10px);
        font-family:'Inter',sans-serif; color:#222;
        animation:msgIn 0.4s ease;
    `;

    // Build mugshots as inline SVG (3 suspects)
    function mugshot(criminal, idx, name, traits) {
        // Detailed face per criminal id
        const detail = {
            0: { // 1호 길동 — 전직 학원 강사, 안경, 깔끔
                skinFill: '#d4a884', hoodFill: '#2a2a2a',
                browAngle: -10, scar: false, beard: false, glasses: true, mole: false, faceShape: 'long'
            },
            1: { // 2호 철수 — 카페 사장, 흉터, 짧은 수염
                skinFill: '#c89070', hoodFill: '#1a1a1a',
                browAngle: -15, scar: true, beard: true, glasses: false, mole: false, faceShape: 'square'
            },
            2: { // 3호 영수 — 폐공장 두목, 큰 흉터, 두꺼운 수염
                skinFill: '#b88060', hoodFill: '#0a0a0a',
                browAngle: -20, scar: true, beard: true, glasses: false, mole: true, faceShape: 'wide'
            }
        }[idx] || {};

        const faceWidth = detail.faceShape === 'wide' ? 24 : (detail.faceShape === 'square' ? 22 : 20);
        const faceHeight = detail.faceShape === 'long' ? 28 : (detail.faceShape === 'square' ? 24 : 25);

        return `
            <div style="display:flex; flex-direction:column; align-items:center; margin:0 6px;">
                <div style="
                    width:110px; height:140px; background:#fff;
                    border:3px solid #1a1a1a; border-radius:3px; padding:3px;
                    box-shadow:3px 3px 0 #555;
                ">
                    <svg viewBox="0 0 110 130" width="100%" height="100%">
                        <!-- BG: police mugshot grid -->
                        <defs>
                            <linearGradient id="bg${idx}" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stop-color="#e8d8b8"/>
                                <stop offset="100%" stop-color="#c8b89a"/>
                            </linearGradient>
                        </defs>
                        <rect x="0" y="0" width="110" height="130" fill="url(#bg${idx})"/>
                        <!-- height markers -->
                        ${[20,40,60,80,100].map(y =>
                            `<line x1="0" y1="${y}" x2="110" y2="${y}" stroke="#7a5a3a" stroke-width="0.3" stroke-dasharray="2,2"/>`
                        ).join('')}
                        ${[6,7,8].map(h => `<text x="3" y="${20+(h-6)*30+4}" font-size="5" fill="#7a5a3a" font-family="monospace">${h}'</text>`).join('')}

                        <!-- Neck shadow -->
                        <rect x="40" y="92" width="30" height="20" fill="#${detail.skinFill ? detail.skinFill.substring(1) : 'd4a884'}" opacity="0.7"/>

                        <!-- Shoulders (clothing) -->
                        <path d="M 15 130 L 15 100 Q 55 88, 95 100 L 95 130 Z" fill="${detail.hoodFill || '#1a1a1a'}"/>
                        <!-- Collar -->
                        <path d="M 40 95 L 55 105 L 70 95 L 70 100 L 40 100 Z" fill="${detail.hoodFill || '#1a1a1a'}"/>

                        <!-- Face shape (more realistic) -->
                        <path d="M 55 30
                                 Q ${55 + faceWidth} 33, ${55 + faceWidth} 55
                                 Q ${55 + faceWidth - 2} 75, ${55 + faceWidth - 8} 85
                                 Q 55 95, ${55 - faceWidth + 8} 85
                                 Q ${55 - faceWidth + 2} 75, ${55 - faceWidth} 55
                                 Q ${55 - faceWidth} 33, 55 30 Z"
                              fill="${detail.skinFill}" stroke="#7a5a3a" stroke-width="0.5"/>

                        <!-- Forehead shading -->
                        <path d="M 55 30 Q ${55 + faceWidth - 2} 35, ${55 + faceWidth} 50 L ${55 - faceWidth} 50 Q ${55 - faceWidth + 2} 35, 55 30"
                              fill="#000" opacity="0.08"/>

                        <!-- Hair / hood top -->
                        <path d="M ${55 - faceWidth + 2} 35 Q 55 12, ${55 + faceWidth - 2} 35 L ${55 + faceWidth - 4} 42 L ${55 - faceWidth + 4} 42 Z"
                              fill="${detail.hoodFill}"/>

                        <!-- Ears -->
                        <ellipse cx="${55 - faceWidth + 1}" cy="58" rx="2.5" ry="5" fill="${detail.skinFill}" stroke="#7a5a3a" stroke-width="0.3"/>
                        <ellipse cx="${55 + faceWidth - 1}" cy="58" rx="2.5" ry="5" fill="${detail.skinFill}" stroke="#7a5a3a" stroke-width="0.3"/>

                        <!-- Eye sockets (shadow) -->
                        <ellipse cx="45" cy="55" rx="5" ry="3" fill="#000" opacity="0.15"/>
                        <ellipse cx="65" cy="55" rx="5" ry="3" fill="#000" opacity="0.15"/>

                        <!-- Eye whites -->
                        <ellipse cx="45" cy="55" rx="3.5" ry="2.2" fill="#fff"/>
                        <ellipse cx="65" cy="55" rx="3.5" ry="2.2" fill="#fff"/>
                        <!-- Iris (cold dark) -->
                        <circle cx="45" cy="55" r="2" fill="#3a2a1a"/>
                        <circle cx="65" cy="55" r="2" fill="#3a2a1a"/>
                        <!-- Pupils -->
                        <circle cx="45" cy="55" r="1.1" fill="#000"/>
                        <circle cx="65" cy="55" r="1.1" fill="#000"/>
                        <!-- Eye highlight -->
                        <circle cx="44" cy="54" r="0.5" fill="#fff"/>
                        <circle cx="64" cy="54" r="0.5" fill="#fff"/>

                        <!-- Glasses (1호) -->
                        ${detail.glasses ? `
                            <circle cx="45" cy="55" r="6" fill="none" stroke="#222" stroke-width="1.2"/>
                            <circle cx="65" cy="55" r="6" fill="none" stroke="#222" stroke-width="1.2"/>
                            <line x1="51" y1="55" x2="59" y2="55" stroke="#222" stroke-width="1.2"/>
                        ` : ''}

                        <!-- Eyebrows (angled = angry) -->
                        <path d="M 39 49 Q 45 ${49 + (detail.browAngle || 0) * 0.1}, 51 ${50 + (detail.browAngle || 0) * 0.15}"
                              fill="none" stroke="#1a0e08" stroke-width="2" stroke-linecap="round"/>
                        <path d="M 59 ${50 + (detail.browAngle || 0) * 0.15} Q 65 ${49 + (detail.browAngle || 0) * 0.1}, 71 49"
                              fill="none" stroke="#1a0e08" stroke-width="2" stroke-linecap="round"/>

                        <!-- Nose -->
                        <path d="M 55 56 L 53 68 Q 55 70, 57 68 Z" fill="${detail.skinFill}" stroke="#7a5a3a" stroke-width="0.4"/>
                        <ellipse cx="53.5" cy="69" rx="0.8" ry="0.5" fill="#000" opacity="0.4"/>
                        <ellipse cx="56.5" cy="69" rx="0.8" ry="0.5" fill="#000" opacity="0.4"/>

                        <!-- Mouth (stern frown) -->
                        <path d="M 47 78 Q 55 76, 63 78" fill="none" stroke="#5a2a1a" stroke-width="1.5" stroke-linecap="round"/>

                        <!-- Stubble/beard -->
                        ${detail.beard ? `
                            <ellipse cx="55" cy="82" rx="${faceWidth - 5}" ry="6" fill="#1a0e08" opacity="${idx === 2 ? 0.7 : 0.4}"/>
                            <ellipse cx="55" cy="73" rx="3" ry="1.5" fill="#1a0e08" opacity="0.35"/>
                        ` : ''}

                        <!-- Scar -->
                        ${detail.scar ? `
                            <line x1="${idx === 1 ? 67 : 38}" y1="${idx === 1 ? 60 : 48}"
                                  x2="${idx === 1 ? 72 : 44}" y2="${idx === 1 ? 75 : 56}"
                                  stroke="#8b2020" stroke-width="1.2" stroke-linecap="round"/>
                            <line x1="${idx === 1 ? 68 : 39}" y1="${idx === 1 ? 63 : 51}"
                                  x2="${idx === 1 ? 70 : 41}" y2="${idx === 1 ? 65 : 53}"
                                  stroke="#5a1010" stroke-width="0.4"/>
                        ` : ''}

                        <!-- Mole -->
                        ${detail.mole ? `<circle cx="62" cy="75" r="0.9" fill="#3a1a08"/>` : ''}

                        <!-- ID plate -->
                        <rect x="20" y="113" width="70" height="13" fill="#fff" stroke="#000" stroke-width="0.5"/>
                        <text x="55" y="122" text-anchor="middle" font-size="7" font-family="monospace" font-weight="bold">${criminal}</text>
                    </svg>
                </div>
                <div style="margin-top:6px; font-size:11px; font-weight:800; color:#fff; letter-spacing:1px;">${name}</div>
                <div style="margin-top:2px; font-size:9px; color:#bbb; text-align:center; max-width:110px; line-height:1.3;">${traits}</div>
            </div>
        `;
    }

    modal.innerHTML = `
        <div style="
            background:linear-gradient(180deg, #f4e9d0 0%, #e8d4a8 100%);
            border:6px double #5a3a1a; border-radius:8px;
            padding:18px 22px; max-width:92vw; max-height:90vh; overflow-y:auto;
            box-shadow:0 12px 50px rgba(0,0,0,0.7);
            text-align:center; position:relative;
        ">
            <div style="font-size:11px; letter-spacing:6px; color:#7a4a1a; margin-bottom:4px; font-weight:700;">DETECTIVE BRIEFING</div>
            <h2 style="margin:0 0 4px; font-size:26px; color:#3a1a0a; letter-spacing:2px; font-weight:900;">⚠ 수배 전단 ⚠</h2>
            <div style="font-size:12px; color:#3a1a0a; margin-bottom:4px;">담당 형사: <b>${gameState.playerName || '소윤'}</b></div>
            <div style="font-size:11px; color:#7a4a1a; margin-bottom:14px;">아이들을 납치한 흉악범 3명. 반드시 검거하라.</div>
            <div style="display:flex; justify-content:center; flex-wrap:wrap; background:#1a1a1a; padding:14px 8px; border-radius:6px;">
                ${mugshot('CR-001', 0, '1호 길동', '전직 학원 강사<br/>안경, 깡마름<br/>주택가 잠복')}
                ${mugshot('CR-002', 1, '2호 철수', '가짜 카페 사장<br/>볼 흉터, 짧은 수염<br/>상업지구')}
                ${mugshot('CR-003', 2, '3호 영수', '폐공장 조직 두목<br/>눈썹 흉터, 짙은 수염<br/>공장지대')}
            </div>
            ${firstTime ? `
            <div style="margin-top:14px; padding:12px; background:rgba(122,74,26,0.15); border-radius:6px; font-size:12px; color:#3a1a0a; text-align:left; line-height:1.6;">
                <b>📋 수사 지침</b><br/>
                • 시민들에게 말을 걸어 단서를 수집하세요<br/>
                • 도망치는 수배범을 검거하면 추가 단서 획득<br/>
                • 단서를 모두 모으면 밤에 납치범이 출현합니다<br/>
                • 납치한 아이를 구출해 경찰서로 안전히 데려가세요
            </div>
            ` : ''}
            <button id="wp-close" style="
                margin-top:14px; padding:10px 30px; border:none; border-radius:6px;
                background:linear-gradient(135deg,#3a1a0a, #5a3a1a);
                color:#f4e9d0; font-size:13px; font-weight:800; letter-spacing:2px;
                cursor:pointer; font-family:'Inter',sans-serif;
                touch-action:manipulation;
            ">${firstTime ? '수사 시작' : '닫기'}</button>
        </div>
    `;
    document.body.appendChild(modal);

    const close = () => {
        modal.style.transition = 'opacity 0.3s';
        modal.style.opacity = '0';
        setTimeout(() => modal.remove(), 300);
        if (firstTime) {
            try { showMessage('📻 ' + (gameState.playerName || '소윤') + ' 형사, 시민들에게 말을 걸어 단서를 수집하세요.'); } catch(e) {}
            animate();
        }
    };
    const btn = document.getElementById('wp-close');
    btn.addEventListener('click', close);
    btn.addEventListener('touchstart', e => { e.preventDefault(); close(); }, { passive: false });
}
window.showWantedPoster = showWantedPoster;

createStartScreen();
