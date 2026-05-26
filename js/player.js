import * as THREE from 'three';

const MOVE_SPEED = 0.18;
const TURN_SPEED = 0.028;
const CAM_DIST   = 16;
const CAM_HEIGHT = 8;
const CAM_LERP   = 0.12;

export class Player {
    constructor(scene, camera) {
        this.camera = camera;
        this.angle  = Math.PI; // 시작 시 -Z 방향(도시 안쪽)을 바라봄
        this.input  = { up: false, down: false, left: false, right: false };

        this._buildMesh(scene);
        this.mesh.position.set(0, 0, 42); // 도시 남쪽 입구에서 시작
        this._snapCamera();               // 즉시 카메라 위치 설정 (lerp 없이)
        this._bindDpad();
    }

    _buildMesh(scene) {
        const group = new THREE.Group();

        // 몸통 (경찰 파란색)
        const body = new THREE.Mesh(
            new THREE.BoxGeometry(1.0, 1.8, 0.6),
            new THREE.MeshLambertMaterial({ color: 0x1D4ED8 })
        );
        body.position.y = 1.0;
        body.castShadow = true;
        group.add(body);

        // 머리
        const head = new THREE.Mesh(
            new THREE.BoxGeometry(0.7, 0.7, 0.7),
            new THREE.MeshLambertMaterial({ color: 0xFBCFE8 })
        );
        head.position.y = 2.25;
        head.castShadow = true;
        group.add(head);

        // 모자
        const hat = new THREE.Mesh(
            new THREE.BoxGeometry(0.85, 0.22, 0.85),
            new THREE.MeshLambertMaterial({ color: 0x1E3A5F })
        );
        hat.position.y = 2.7;
        group.add(hat);

        // 진행 방향 표시점 (앞면 노란 점)
        const dot = new THREE.Mesh(
            new THREE.SphereGeometry(0.13, 6, 6),
            new THREE.MeshBasicMaterial({ color: 0xFDE047 })
        );
        dot.position.set(0, 1.0, -0.38);
        group.add(dot);

        this.mesh = group;
        scene.add(group);
    }

    _snapCamera() {
        const fwdX = Math.sin(this.angle);
        const fwdZ = Math.cos(this.angle);
        const p    = this.mesh.position;
        this.camera.position.set(
            p.x - fwdX * CAM_DIST,
            CAM_HEIGHT,
            p.z - fwdZ * CAM_DIST
        );
        this.camera.lookAt(p.x, 1.5, p.z);
    }

    _bindDpad() {
        const bind = (id, dir) => {
            const el = document.getElementById(id);
            if (!el) return;

            const press   = e => { e.preventDefault(); this.input[dir] = true;  el.classList.add('pressed'); };
            const release = e => { e.preventDefault(); this.input[dir] = false; el.classList.remove('pressed'); };

            el.addEventListener('touchstart',  press,   { passive: false });
            el.addEventListener('touchend',    release, { passive: false });
            el.addEventListener('touchcancel', release, { passive: false });
            // 데스크톱 마우스로도 테스트 가능
            el.addEventListener('mousedown',  press);
            el.addEventListener('mouseup',    release);
            el.addEventListener('mouseleave', release);
        };

        bind('dpad-up',    'up');
        bind('dpad-down',  'down');
        bind('dpad-left',  'left');
        bind('dpad-right', 'right');
    }

    update() {
        // 회전
        if (this.input.left)  this.angle += TURN_SPEED;
        if (this.input.right) this.angle -= TURN_SPEED;

        const fwdX = Math.sin(this.angle);
        const fwdZ = Math.cos(this.angle);

        // 이동
        if (this.input.up) {
            this.mesh.position.x += fwdX * MOVE_SPEED;
            this.mesh.position.z += fwdZ * MOVE_SPEED;
        }
        if (this.input.down) {
            this.mesh.position.x -= fwdX * MOVE_SPEED;
            this.mesh.position.z -= fwdZ * MOVE_SPEED;
        }

        // 월드 경계 클램프
        this.mesh.position.x = Math.max(-62, Math.min(62, this.mesh.position.x));
        this.mesh.position.z = Math.max(-62, Math.min(62, this.mesh.position.z));

        this.mesh.rotation.y = this.angle;

        // 카메라 부드럽게 추적 (lerp)
        const p = this.mesh.position;
        const target = new THREE.Vector3(
            p.x - fwdX * CAM_DIST,
            CAM_HEIGHT,
            p.z - fwdZ * CAM_DIST
        );
        this.camera.position.lerp(target, CAM_LERP);
        this.camera.lookAt(p.x, 1.5, p.z);
    }
}
