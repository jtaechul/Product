import * as THREE from 'three';
import { buildCity } from './world.js';
import { Player } from './player.js';

function init() {
    const canvas = document.getElementById('game-canvas');

    // ─── 씬 ───────────────────────────────────────────────────
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x87CEEB);
    scene.fog = new THREE.FogExp2(0x87CEEB, 0.007);

    // ─── 카메라 (플레이어가 제어) ─────────────────────────────
    const camera = new THREE.PerspectiveCamera(
        60,
        window.innerWidth / window.innerHeight,
        0.1,
        400
    );

    // ─── 렌더러 ───────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    // ─── 도시 + 플레이어 생성 ────────────────────────────────
    buildCity(scene);
    const player = new Player(scene, camera);

    // ─── 리사이즈 대응 ────────────────────────────────────────
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });

    // ─── 게임 루프 ────────────────────────────────────────────
    function animate() {
        requestAnimationFrame(animate);
        player.update();
        renderer.render(scene, camera);
    }
    animate();
}

init();
