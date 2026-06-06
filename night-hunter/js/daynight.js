// daynight.js — 낮/밤 전환 시스템 (3단계)

const DayNight = {
    transitionDuration: 30,
    isTransitioning: false,
    transitionProgress: 0,
    transitionType: null, // 'toNight' or 'toDay'

    // Sky objects
    moon: null,
    stars: [],
    flashlight: null,
    streetLightObjects: [],

    // Colors
    daySkyColor: new THREE.Color(0x87CEEB),
    nightSkyColor: new THREE.Color(0x050510),
    dayFogColor: new THREE.Color(0x87CEEB),
    nightFogColor: new THREE.Color(0x050510),
    currentSkyColor: new THREE.Color(0x87CEEB),
    currentFogColor: new THREE.Color(0x87CEEB),

    // Radio messages
    radioMessages: {
        day1: '📻 도시 어딘가에 아이들이 납치되어 있습니다.\n힌트를 찾아 수사를 시작하세요.',
        night: '📻 밤입니다. 납치범들이 활동을 시작했습니다.\n조심하세요.',
        afterArrest: '📻 수고했어요. 아직 {n}명의 납치범이 남아있습니다.',
        lastMinute: '📻 시간이 없어요! 서두르세요!',
        newDay: '📻 ☀️ 새벽이 밝았습니다.\n{day}일차 수사를 시작하세요.'
    },

    init(scene, playerGroup) {
        this.scene = scene;
        this.playerGroup = playerGroup;
        this.createMoon();
        this.createStars();
        this.createFlashlight();
        this.hideMoon();
        this.initStreetLightPool();
    },

    createMoon() {
        const moonGeo = new THREE.SphereGeometry(8, 32, 32);
        const moonMat = new THREE.MeshStandardMaterial({
            color: 0xffffee,
            emissive: 0xaaaaaa,
            emissiveIntensity: 0.5
        });
        this.moon = new THREE.Mesh(moonGeo, moonMat);
        this.moon.position.set(80, 120, -80);
        this.moon.visible = false;
        this.scene.add(this.moon);

        // Moon glow
        const glowGeo = new THREE.SphereGeometry(12, 32, 32);
        const glowMat = new THREE.MeshBasicMaterial({
            color: 0x4466aa,
            transparent: true,
            opacity: 0.15
        });
        this.moonGlow = new THREE.Mesh(glowGeo, glowMat);
        this.moonGlow.position.copy(this.moon.position);
        this.moonGlow.visible = false;
        this.scene.add(this.moonGlow);
    },

    createStars() {
        const starGeo = new THREE.BufferGeometry();
        const positions = [];
        for (let i = 0; i < 50; i++) {
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.random() * Math.PI * 0.4 + 0.1;
            const r = 180;
            positions.push(
                r * Math.sin(phi) * Math.cos(theta),
                r * Math.cos(phi),
                r * Math.sin(phi) * Math.sin(theta)
            );
        }
        starGeo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        const starMat = new THREE.PointsMaterial({
            color: 0xffffff,
            size: 1.5,
            transparent: true,
            opacity: 0
        });
        this.starField = new THREE.Points(starGeo, starMat);
        this.starField.visible = false;
        this.scene.add(this.starField);
    },

    createFlashlight() {
        this.flashlight = new THREE.SpotLight(0xffeedd, 0, 15, Math.PI / 6, 0.5, 1);
        this.flashlight.castShadow = false;
        this.scene.add(this.flashlight);
        this.scene.add(this.flashlight.target);
    },

    showMoon() {
        this.moon.visible = true;
        this.moonGlow.visible = true;
        this.starField.visible = true;
    },

    hideMoon() {
        this.moon.visible = false;
        this.moonGlow.visible = false;
        this.starField.visible = false;
    },

    startTransition(type) {
        this.isTransitioning = true;
        this.transitionProgress = 0;
        this.transitionType = type;

        if (typeof SoundManager !== 'undefined') SoundManager.playSFX('transition');

        if (type === 'toNight') {
            showMessage('🌙 밤이 되었습니다…');
        } else {
            showMessage('☀️ 새벽이 밝아옵니다…');
        }
    },

    updateTransition(delta) {
        if (!this.isTransitioning) return false;

        this.transitionProgress += delta / this.transitionDuration;
        const t = Math.min(this.transitionProgress, 1);
        const smooth = t * t * (3 - 2 * t); // smoothstep

        if (this.transitionType === 'toNight') {
            this.currentSkyColor.lerpColors(this.daySkyColor, this.nightSkyColor, smooth);
            this.currentFogColor.lerpColors(this.dayFogColor, this.nightFogColor, smooth);
            this.scene.background = this.currentSkyColor;
            this.scene.fog.color = this.currentFogColor;
            this.scene.fog.near = 80 - 50 * smooth;
            this.scene.fog.far = 200 - 80 * smooth;

            // Lighting: warm day → cool night
            ambientLight.intensity = 0.25 - 0.12 * smooth;
            sunLight.intensity = 1.15 - 1.0 * smooth;
            if (typeof hemiLight !== 'undefined') hemiLight.intensity = 0.55 - 0.4 * smooth;
            // Sun color shifts warm→cool (moon)
            sunLight.color.lerpColors(new THREE.Color(0xfff4e0), new THREE.Color(0x3a4a8a), smooth);
            // Bloom intensifies at night
            if (typeof bloomPass !== 'undefined' && bloomPass) bloomPass.strength = 0.2 + 0.3 * smooth;

            // Stars fade in
            this.starField.visible = true;
            this.starField.material.opacity = smooth;

            // Moon
            if (smooth > 0.5) {
                this.moon.visible = true;
                this.moonGlow.visible = true;
            }

            // Streetlights turn on one by one
            this.updateStreetLights(smooth, true);

            // Flashlight
            if (smooth > 0.7) {
                this.flashlight.intensity = (smooth - 0.7) / 0.3 * 2;
            }
        } else {
            // toDay
            this.currentSkyColor.lerpColors(this.nightSkyColor, this.daySkyColor, smooth);
            this.currentFogColor.lerpColors(this.nightFogColor, this.dayFogColor, smooth);
            this.scene.background = this.currentSkyColor;
            this.scene.fog.color = this.currentFogColor;
            this.scene.fog.near = 30 + 50 * smooth;
            this.scene.fog.far = 120 + 80 * smooth;

            ambientLight.intensity = 0.13 + 0.12 * smooth;
            sunLight.intensity = 0.15 + 1.0 * smooth;
            if (typeof hemiLight !== 'undefined') hemiLight.intensity = 0.15 + 0.4 * smooth;
            sunLight.color.lerpColors(new THREE.Color(0x3a4a8a), new THREE.Color(0xfff4e0), smooth);
            if (typeof bloomPass !== 'undefined' && bloomPass) bloomPass.strength = 0.5 - 0.3 * smooth;

            // Stars fade out
            this.starField.material.opacity = 1 - smooth;
            if (smooth > 0.8) {
                this.moon.visible = false;
                this.moonGlow.visible = false;
                this.starField.visible = false;
            }

            // Streetlights off
            this.updateStreetLights(smooth, false);

            // Flashlight off
            this.flashlight.intensity = 2 * (1 - smooth);
        }

        if (t >= 1) {
            this.isTransitioning = false;
            this.finishTransition();
            return true;
        }
        return false;
    },

    initStreetLightPool() {
        const lights = window._streetLights || [];
        // Pre-create PointLights for every 4th lamp (max ~10 lights)
        lights.forEach((lamp, i) => {
            if (i % 4 === 0) {
                const pl = new THREE.PointLight(0xffdd88, 0, 18);
                pl.position.copy(lamp.position);
                this.scene.add(pl);
                lamp.userData.pointLight = pl;
            }
        });
    },

    updateStreetLights(progress, turningOn) {
        const lights = window._streetLights || [];
        const total = lights.length;
        if (total === 0) return;

        lights.forEach((lamp, i) => {
            const threshold = (i / total) * 0.8;
            if (turningOn && progress > threshold) {
                lamp.material.emissive.setHex(0xffaa44);
                lamp.material.emissiveIntensity = 1.0;
                if (lamp.userData.pointLight) lamp.userData.pointLight.intensity = 0.8;
            } else if (!turningOn && progress > threshold) {
                lamp.material.emissive.setHex(0x332200);
                lamp.material.emissiveIntensity = 0;
                if (lamp.userData.pointLight) lamp.userData.pointLight.intensity = 0;
            }
        });
    },

    finishTransition() {
        if (this.transitionType === 'toNight') {
            if (typeof SoundManager !== 'undefined') SoundManager.playBGM('night');
            gameState.isDay = false;
            gameState.timeRemaining = gameState.nightDuration;
            document.getElementById('time-icon').textContent = '🌙';
            showMessage(this.radioMessages.night);
        } else {
            if (typeof SoundManager !== 'undefined') SoundManager.playBGM('day');
            gameState.day++;
            gameState.isDay = true;
            gameState.timeRemaining = gameState.dayDuration;
            document.getElementById('time-icon').textContent = '☀️';
            document.getElementById('day-text').textContent = gameState.day + '일차';

            const remaining = gameState.totalArrests - gameState.arrests;
            if (remaining > 0 && gameState.arrests > 0) {
                showMessage(this.radioMessages.afterArrest.replace('{n}', remaining));
            } else {
                showMessage(this.radioMessages.newDay.replace('{day}', gameState.day));
            }
        }
    },

    updateFlashlight() {
        if (!gameState.isDay || this.isTransitioning) {
            const px = this.playerGroup.position.x;
            const pz = this.playerGroup.position.z;
            // Forward direction matches playerGroup.rotation.y (0=+Z)
            const fx = Math.sin(this.playerGroup.rotation.y);
            const fz = Math.cos(this.playerGroup.rotation.y);
            this.flashlight.position.set(px, 1.8, pz);
            this.flashlight.target.position.set(
                px + fx * 10,
                0,
                pz + fz * 10
            );
        }
    },

    updateWindowGlow(isNight) {
        // Make windows glow at night
        this.scene.traverse(obj => {
            if (obj.isMesh && obj.material && obj.material.color) {
                const c = obj.material.color.getHex();
                if (c === 0x88ccff) {
                    if (isNight) {
                        // Lit warm-yellow windows for bloom
                        obj.material.emissive.setHex(0xffdd88);
                        obj.material.emissiveIntensity = 1.5;
                    } else {
                        obj.material.emissive.setHex(0x223344);
                        obj.material.emissiveIntensity = 0.2;
                    }
                }
            }
        });
    },

    checkLastMinuteWarning() {
        if (!gameState.isDay && gameState.timeRemaining <= 60 && gameState.timeRemaining > 59) {
            showMessage(this.radioMessages.lastMinute);
        }
    },

    updateStarTwinkle(time) {
        if (!this.starField || !this.starField.visible) return;
        const sizes = this.starField.geometry.attributes.position;
        if (!this._starBaseSize) {
            this._starBaseSize = [];
            for (let i = 0; i < sizes.count; i++) {
                this._starBaseSize.push(0.8 + Math.random() * 1.2);
            }
        }
        this.starField.material.size = 1.5 + Math.sin(time * 2) * 0.5;
    }
};
