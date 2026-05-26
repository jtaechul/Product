import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { buildCity } from './world.js';

function init() {
    const canvas = document.getElementById('game-canvas');

    // ─── 씬 ───────────────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x87CEEB);       // 낮 하늘색
    scene.fog = new THREE.FogExp2(0x87CEEB, 0.007);     // 원거리 안개

    // ─── 카메라 (3인칭 위에서 내려보는 시점) ─────────────────
    const camera = new THREE.PerspectiveCamera(
        55,
        window.innerWidth / window.innerHeight,
        0.1,
        500
    );
    camera.position.set(0, 80, 100);
    camera.lookAt(0, 0, 0);

    // ─── 렌더러 ───────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    // ─── 카메라 컨트롤 ────────────────────────────────────────
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.minDistance = 20;
    controls.maxDistance = 180;
    controls.maxPolarAngle = Math.PI / 2.15;   // 지면 아래로 내려가지 않게
    controls.target.set(0, 0, 0);

    // ─── 도시 생성 ────────────────────────────────────────────
    buildCity(scene);

    // ─── 리사이즈 대응 ────────────────────────────────────────
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // ─── 게임 루프 ────────────────────────────────────────────
    function animate() {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
    }
    animate();
}

init();
