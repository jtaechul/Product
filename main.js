const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const scoreEl = document.getElementById('score');
const hpBarEl = document.getElementById('hp-bar-fill');
const xpBarEl = document.getElementById('xp-bar-fill');
const levelTextEl = document.getElementById('level-text');
const timerEl = document.getElementById('timer');
const levelUpScreen = document.getElementById('level-up-screen');
const skillOptionsEl = document.getElementById('skill-options');

// --- Multi-language Support ---
const translations = {
    ko: {
        score: "점수",
        timer: "시간",
        level: "레벨",
        lvlUpTitle: "레벨 업!",
        lvlUpSubtitle: "강화 능력을 선택하세요",
        gameOverTitle: "게임 오버",
        finalScoreLabel: "최종 점수",
        finalTimeLabel: "최종 시간",
        restartBtn: "다시 시작",
        skills: {
            atk_speed: { name: "신속한 타격", desc: "공격 속도가 20% 빨라집니다." },
            damage: { name: "날카로운 발톱", desc: "공격력이 30% 증가합니다." },
            move_speed: { name: "정글의 포식자", desc: "이동 속도가 15% 증가합니다." },
            multi_shot: { name: "무리 사냥꾼", desc: "추가 투사체를 발사합니다." },
            chain_lightning: { name: "연쇄 번개", desc: "공격이 주변 적 2명에게 전이됩니다." },
            dodge: { name: "회피", desc: "적의 공격을 회피할 확률이 10% 생깁니다." },
            heal: { name: "원시의 활력", desc: "체력을 40% 회복합니다." },
            max_hp: { name: "고대의 체력", desc: "최대 체력이 25% 증가합니다." }
        }
    },
    en: {
        score: "Score",
        timer: "Time",
        level: "LV.",
        lvlUpTitle: "LEVEL UP!",
        lvlUpSubtitle: "Choose an Upgrade",
        gameOverTitle: "GAME OVER",
        finalScoreLabel: "Score",
        finalTimeLabel: "Time",
        restartBtn: "RESTART",
        skills: {
            atk_speed: { name: "Rapid Strikes", desc: "Attack 20% faster." },
            damage: { name: "Serrated Claws", desc: "Increase damage by 30%." },
            move_speed: { name: "Jungle Predator", desc: "Increase speed by 15%." },
            multi_shot: { name: "Pack Hunter", desc: "Fire extra projectiles." },
            chain_lightning: { name: "Chain Lightning", desc: "Attacks jump to 2 nearby enemies" },
            dodge: { name: "Evasion", desc: "10% chance to dodge enemy attacks" },
            heal: { name: "Primal Vitality", desc: "Restore 40% health." },
            max_hp: { name: "Ancient Constitution", desc: "Increase Max HP by 25%." }
        }
    }
};

let currentLang = 'ko';

function setLanguage(lang) {
    currentLang = lang;
    const t = translations[lang];
    
    // Update static UI
    document.getElementById('lvl-up-title').textContent = t.lvlUpTitle;
    document.getElementById('lvl-up-subtitle').textContent = t.lvlUpSubtitle;
    document.getElementById('game-over-title').textContent = t.gameOverTitle;
    document.getElementById('final-score-label').textContent = t.finalScoreLabel;
    document.getElementById('final-time-label').textContent = t.finalTimeLabel;
    document.getElementById('restart-btn').textContent = t.restartBtn;
    
    // Update active HUD
    scoreEl.textContent = `${t.score}: ${score}`;
    levelTextEl.textContent = `${t.level} ${player.level}`;
}

// --- Joystick Logic ---
const joystickContainer = document.getElementById('joystick-container');
const joystickBase = document.getElementById('joystick-base');
const joystickHandle = document.getElementById('joystick-handle');
let joystickActive = false;
let joystickStartPos = { x: 0, y: 0 };
let joystickCurrentDir = { x: 0, y: 0 };

function initJoystick() {
    if (!('ontouchstart' in window)) return;
    
    joystickContainer.style.display = 'block';
    
    joystickContainer.addEventListener('touchstart', (e) => {
        const touch = e.touches[0];
        joystickActive = true;
        joystickStartPos = { x: touch.clientX, y: touch.clientY };
        
        joystickBase.style.display = 'block';
        joystickBase.style.left = `${joystickStartPos.x}px`;
        joystickBase.style.top = `${joystickStartPos.y}px`;
        joystickHandle.style.left = '50%';
        joystickHandle.style.top = '50%';
    });
    
    joystickContainer.addEventListener('touchmove', (e) => {
        if (!joystickActive) return;
        const touch = e.touches[0];
        const dx = touch.clientX - joystickStartPos.x;
        const dy = touch.clientY - joystickStartPos.y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        const maxDist = 60;
        
        const angle = Math.atan2(dy, dx);
        const moveDist = Math.min(dist, maxDist);
        
        const handleX = Math.cos(angle) * moveDist;
        const handleY = Math.sin(angle) * moveDist;
        
        joystickHandle.style.left = `calc(50% + ${handleX}px)`;
        joystickHandle.style.top = `calc(50% + ${handleY}px)`;
        
        joystickCurrentDir = { x: Math.cos(angle) * (moveDist/maxDist), y: Math.sin(angle) * (moveDist/maxDist) };
    });
    
    joystickContainer.addEventListener('touchend', () => {
        joystickActive = false;
        joystickBase.style.display = 'none';
        joystickCurrentDir = { x: 0, y: 0 };
    });
}

initJoystick();

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// --- Game State ---
let score = 0;
let keys = {};
let gameTime = 0;
let isPaused = false;
let gameOver = false;

window.addEventListener('keydown', e => keys[e.code] = true);
window.addEventListener('keyup', e => keys[e.code] = false);

const world = { width: 4000, height: 4000 };
const camera = { x: 0, y: 0 };

// --- Particle System ---
class Particle {
    constructor(x, y, color, type = 'dust') {
        this.x = x; this.y = y;
        const angle = Math.random() * Math.PI * 2;
        const speed = type === 'spark' ? Math.random() * 8 + 4 : (type === 'lightning' ? Math.random() * 4 + 2 : Math.random() * 2 + 0.5);
        this.vx = Math.cos(angle) * speed;
        this.vy = Math.sin(angle) * speed;
        this.life = 1.0;
        this.decay = type === 'spark' ? 0.02 + Math.random() * 0.02 : 0.01 + Math.random() * 0.01;
        this.color = color;
        this.size = type === 'spark' ? Math.random() * 4 + 2 : (type === 'lightning' ? Math.random() * 2 + 1 : Math.random() * 6 + 4);
        this.type = type;
    }
    update() {
        this.x += this.vx; this.y += this.vy;
        this.life -= this.decay;
        if (this.type === 'dust') {
            this.vy -= 0.02;
            this.size *= 1.01;
        }
    }
    draw(ctx, camX, camY) {
        ctx.save();
        ctx.globalAlpha = Math.max(0, this.life);
        ctx.fillStyle = this.color;
        if (this.type === 'spark' || this.type === 'lightning') {
            ctx.shadowBlur = 10;
            ctx.shadowColor = this.color;
        }
        ctx.beginPath();
        ctx.arc(this.x - camX, this.y - camY, this.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }
}

const particles = [];
function spawnParticles(x, y, color, count, type) {
    for (let i = 0; i < count; i++) {
        particles.push(new Particle(x, y, color, type));
    }
}

// --- Skill Definitions ---
const SKILLS = [
    { id: 'atk_speed', name: 'Rapid Strikes', desc: 'Attack 20% faster.', effect: (p) => p.attackSpeedMod *= 0.8 },
    { id: 'damage', name: 'Serrated Claws', desc: 'Increase damage by 30%.', effect: (p) => p.damageMod *= 1.3 },
    { id: 'move_speed', name: 'Jungle Predator', desc: 'Increase speed by 15%.', effect: (p) => p.speed += 0.8 },
    { id: 'multi_shot', name: 'Pack Hunter', desc: 'Fire extra projectiles.', effect: (p) => p.multiShot += 1 },
    { id: 'chain_lightning', name: 'Chain Lightning', desc: 'Attacks jump to 2 nearby enemies', effect: (p) => p.chainLightningCount += 2 },
    { id: 'dodge', name: 'Evasion', desc: '10% chance to dodge enemy attacks', effect: (p) => p.dodgeChance += 0.1 },
    { id: 'heal', name: 'Primal Vitality', desc: 'Restore 40% health.', effect: (p) => p.hp = Math.min(p.maxHp, p.hp + p.maxHp * 0.4) },
    { id: 'max_hp', name: 'Ancient Constitution', desc: 'Increase Max HP by 25%.', effect: (p) => { p.maxHp *= 1.25; p.hp *= 1.25; } }
];

class XPGem {
    constructor(x, y, value) {
        this.x = x; this.y = y;
        this.value = value;
        this.radius = 6;
        this.color = '#60a5fa';
        this.pulse = 0;
    }
    draw(ctx, camX, camY) {
        this.pulse += 0.1;
        const s = this.radius + Math.sin(this.pulse) * 2;
        ctx.save();
        ctx.translate(this.x - camX, this.y - camY);
        ctx.fillStyle = this.color;
        ctx.shadowBlur = 15; ctx.shadowColor = this.color;
        ctx.beginPath();
        ctx.moveTo(0, -s); ctx.lineTo(s, 0); ctx.lineTo(0, s); ctx.lineTo(-s, 0); ctx.closePath();
        ctx.fill();
        ctx.restore();
    }
}

class HealDrop {
    constructor(x, y) {
        this.x = x; this.y = y;
        this.radius = 10;
        this.pulse = 0;
    }
    draw(ctx, camX, camY) {
        this.pulse += 0.05;
        const s = this.radius + Math.sin(this.pulse) * 3;
        ctx.save();
        ctx.translate(this.x - camX, this.y - camY);
        ctx.fillStyle = '#ef4444';
        ctx.shadowBlur = 15; ctx.shadowColor = '#f87171';
        ctx.beginPath();
        ctx.rect(-s/2, -s, s/2, s*2); ctx.rect(-s, -s/2, s*2, s/2);
        ctx.fill();
        ctx.restore();
    }
}

class Player {
    constructor() {
        this.x = world.width / 2;
        this.y = world.height / 2;
        this.radius = 24;
        this.speed = 5.5;
        this.maxHp = 100;
        this.hp = this.maxHp;
        
        this.level = 1;
        this.xp = 0;
        this.xpToNext = 100;

        this.attackCooldown = 0;
        this.baseAttackSpeed = 35;
        this.attackSpeedMod = 1.0;
        this.damageMod = 1.0;
        this.multiShot = 0;
        this.chainLightningCount = 0;
        this.dodgeChance = 0;

        this.facingLeft = false;
        this.walkCycle = 0;
        this.lean = 0;
        this.targetLean = 0;
        this.knockbackX = 0;
        this.knockbackY = 0;

        // Dash System
        this.dashTimer = 0;
        this.dashCooldown = 0;
        this.dashSpeedMultiplier = 2.5;
    }

    update() {
        let dx = 0, dy = 0;
        if (keys['ArrowUp'] || keys['KeyW']) dy -= 1;
        if (keys['ArrowDown'] || keys['KeyS']) dy += 1;
        if (keys['ArrowLeft'] || keys['KeyA']) dx -= 1;
        if (keys['ArrowRight'] || keys['KeyD']) dx += 1;

        // Dash logic
        if (keys['ShiftLeft'] && this.dashCooldown <= 0 && (dx !== 0 || dy !== 0)) {
            this.dashTimer = 60; // 1 second at 60fps
            this.dashCooldown = 180; // 3 seconds
            spawnParticles(this.x, this.y, '#fff', 10, 'dust');
        }

        let currentSpeed = this.speed;
        if (this.dashTimer > 0) {
            currentSpeed *= this.dashSpeedMultiplier;
            this.dashTimer--;
            if (gameTime % 2 === 0) spawnParticles(this.x, this.y, 'rgba(255,255,255,0.3)', 1, 'dust');
        }
        if (this.dashCooldown > 0) this.dashCooldown--;

        if (dx !== 0 || dy !== 0) {
            const length = Math.sqrt(dx*dx + dy*dy);
            this.x += (dx/length) * currentSpeed + this.knockbackX;
            this.y += (dy/length) * currentSpeed + this.knockbackY;
            this.walkCycle += (this.dashTimer > 0 ? 0.5 : 0.25);
            if (dx < 0) this.facingLeft = true;
            if (dx > 0) this.facingLeft = false;
            this.targetLean = dx * (this.dashTimer > 0 ? 0.4 : 0.15);
            
            if (gameTime % 5 === 0) spawnParticles(this.x, this.y + 15, 'rgba(139, 115, 85, 0.4)', 1, 'dust');
        } else {
            this.walkCycle *= 0.8;
            this.targetLean = 0;
            this.x += this.knockbackX;
            this.y += this.knockbackY;
        }

        this.lean += (this.targetLean - this.lean) * 0.1;
        this.knockbackX *= 0.85;
        this.knockbackY *= 0.85;

        this.x = Math.max(this.radius, Math.min(world.width - this.radius, this.x));
        this.y = Math.max(this.radius, Math.min(world.height - this.radius, this.y));

        if (this.attackCooldown > 0) this.attackCooldown--;
    }

    takeDamage(amount, fromX, fromY) {
        if (Math.random() < this.dodgeChance) {
            spawnParticles(this.x, this.y - 30, '#fff', 5, 'spark');
            return; // Dodged!
        }
        this.hp -= amount;
        const dx = this.x - fromX;
        const dy = this.y - fromY;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist > 0) {
            this.knockbackX = (dx/dist) * 12;
            this.knockbackY = (dy/dist) * 12;
        }
        this.updateUI();
    }

    gainXP(amount) {
        this.xp += amount;
        if (this.xp >= this.xpToNext) this.levelUp();
        this.updateUI();
    }

    levelUp() {
        this.level++;
        this.xp -= this.xpToNext;
        this.xpToNext = Math.floor(this.xpToNext * 1.35);
        showLevelUpScreen();
    }

    updateUI() {
        xpBarEl.style.width = (this.xp / this.xpToNext * 100) + '%';
        levelTextEl.textContent = `LV. ${this.level}`;
        hpBarEl.style.width = (this.hp / this.maxHp * 100) + '%';
    }

    draw(ctx, camX, camY) {
        const drawX = this.x - camX;
        const drawY = this.y - camY;
        ctx.save();
        ctx.translate(drawX, drawY);
        ctx.rotate(this.lean);
        if (this.facingLeft) ctx.scale(-1, 1);
        const bob = Math.sin(this.walkCycle) * 4;
        const legAngle = Math.sin(this.walkCycle) * 0.5;
        ctx.fillStyle = 'rgba(0,0,0,0.4)';
        ctx.beginPath(); ctx.ellipse(0, 25, 30, 10, 0, 0, Math.PI*2); ctx.fill();
        const bodyGrad = ctx.createRadialGradient(0, 0, 5, 0, 0, 25);
        bodyGrad.addColorStop(0, '#3a5a40'); bodyGrad.addColorStop(1, '#1b4332');
        ctx.fillStyle = '#1b4332';
        ctx.save(); ctx.translate(-5, 10); ctx.rotate(legAngle); ctx.fillRect(-3, 0, 6, 15); ctx.restore();
        ctx.save(); ctx.translate(5, 10); ctx.rotate(-legAngle); ctx.fillRect(-3, 0, 6, 15); ctx.restore();
        ctx.beginPath(); ctx.moveTo(-15, 0); ctx.bezierCurveTo(-40, 5, -50, 25, -60, 20); ctx.bezierCurveTo(-50, 30, -30, 15, -15, 10); ctx.fillStyle = '#1b4332'; ctx.fill();
        ctx.translate(0, bob);
        ctx.fillStyle = bodyGrad;
        ctx.beginPath(); ctx.ellipse(0, 0, 22, 16, 0.1, 0, Math.PI * 2); ctx.fill();
        ctx.save(); ctx.translate(15, -5); ctx.rotate(-0.3 + bob * 0.05); ctx.fillStyle = '#1b4332'; ctx.fillRect(0, -10, 10, 20);
        const headGrad = ctx.createLinearGradient(0, -15, 25, -15);
        headGrad.addColorStop(0, '#3a5a40'); headGrad.addColorStop(1, '#4f772d');
        ctx.fillStyle = headGrad; ctx.beginPath(); ctx.roundRect(5, -22, 28, 16, [4, 10, 10, 4]); ctx.fill();
        ctx.fillStyle = '#fbbf24'; ctx.beginPath(); ctx.arc(22, -16, 3, 0, Math.PI*2); ctx.fill();
        ctx.fillStyle = 'black'; ctx.beginPath(); ctx.arc(23, -16, 1.5, 0, Math.PI*2); ctx.fill();
        ctx.restore();
        ctx.restore();
    }
}

class Enemy {
    constructor(isElite = false, isBoss = false) {
        const side = Math.floor(Math.random() * 4);
        const margin = 100;
        if (side === 0) { this.x = camera.x + Math.random() * canvas.width; this.y = camera.y - margin; }
        else if (side === 1) { this.x = camera.x + canvas.width + margin; this.y = camera.y + Math.random() * canvas.height; }
        else if (side === 2) { this.x = camera.x + Math.random() * canvas.width; this.y = camera.y + canvas.height + margin; }
        else { this.x = camera.x - margin; this.y = camera.y + Math.random() * canvas.height; }

        const timeMinutes = gameTime / 3600;
        const scale = 1 + timeMinutes * 0.5;

        this.isElite = isElite;
        this.isBoss = isBoss;
        this.radius = isBoss ? 80 : (isElite ? 38 : 18);
        this.speed = isBoss ? 2.5 : ((1.8 + Math.random()) * (isElite ? 0.75 : 1.2) * (1 + timeMinutes * 0.1));
        this.maxHp = (isBoss ? 2000 : (isElite ? 250 : 25)) * scale;
        this.hp = this.maxHp;
        this.walkCycle = Math.random() * 10;
        this.vx = 0; this.vy = 0;
        this.lean = 0;
        this.knockbackX = 0; this.knockbackY = 0;

        // Boss charge pattern
        this.chargeTimer = 0;
        this.isCharging = false;
        this.chargeDirX = 0; this.chargeDirY = 0;
    }

    update(player) {
        if (this.isBoss) {
            this.updateBossLogic(player);
        } else {
            const dx = player.x - this.x;
            const dy = player.y - this.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            this.vx = (dx / dist) * this.speed;
            this.vy = (dy / dist) * this.speed;
        }
        
        this.x += this.vx + this.knockbackX;
        this.y += this.vy + this.knockbackY;
        this.knockbackX *= 0.85;
        this.knockbackY *= 0.85;
        this.walkCycle += 0.2;
        this.lean = (this.vx * 0.1);
    }

    updateBossLogic(player) {
        this.chargeTimer++;
        if (!this.isCharging && this.chargeTimer > 180) { // Prep charge
            const dx = player.x - this.x;
            const dy = player.y - this.y;
            const dist = Math.sqrt(dx*dx + dy*dy);
            this.chargeDirX = (dx/dist);
            this.chargeDirY = (dy/dist);
            this.isCharging = true;
            this.chargeTimer = 0;
        }

        if (this.isCharging) {
            this.vx = this.chargeDirX * 12;
            this.vy = this.chargeDirY * 12;
            if (this.chargeTimer > 40) {
                this.isCharging = false;
                this.chargeTimer = 0;
            }
            if (gameTime % 2 === 0) spawnParticles(this.x, this.y, '#ef4444', 1, 'dust');
        } else {
            const dx = player.x - this.x;
            const dy = player.y - this.y;
            const dist = Math.sqrt(dx*dx + dy*dy);
            this.vx = (dx / dist) * this.speed;
            this.vy = (dy / dist) * this.speed;
        }
    }

    takeDamage(amount, fromX, fromY) {
        this.hp -= amount;
        const dx = this.x - fromX;
        const dy = this.y - fromY;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if (dist > 0 && !this.isBoss) {
            this.knockbackX = (dx/dist) * 8;
            this.knockbackY = (dy/dist) * 8;
        }
    }

    draw(ctx, camX, camY) {
        const drawX = this.x - camX;
        const drawY = this.y - camY;
        if (drawX < -200 || drawX > canvas.width + 200 || drawY < -200 || drawY > canvas.height + 200) return;
        ctx.save();
        ctx.translate(drawX, drawY);
        ctx.rotate(this.lean);
        if (this.vx < 0) ctx.scale(-1, 1);
        const bob = Math.sin(this.walkCycle) * (this.isBoss ? 5 : 2);
        const bodyGrad = ctx.createRadialGradient(0, 0, 2, 0, 0, this.radius);
        bodyGrad.addColorStop(0, this.isBoss ? '#450a0a' : (this.isElite ? '#991b1b' : '#a16207'));
        bodyGrad.addColorStop(1, this.isBoss ? '#000' : (this.isElite ? '#450a0a' : '#713f12'));
        ctx.fillStyle = 'rgba(0,0,0,0.3)';
        ctx.beginPath(); ctx.ellipse(0, this.radius * 1.1, this.radius * 1.2, this.radius * 0.4, 0, 0, Math.PI*2); ctx.fill();
        ctx.translate(0, bob);
        ctx.fillStyle = bodyGrad;
        ctx.beginPath(); ctx.ellipse(0, 0, this.radius, this.radius * 0.7, 0, 0, Math.PI*2); ctx.fill();
        ctx.fillStyle = this.isBoss ? '#ff0000' : (this.isElite ? '#ef4444' : '#facc15');
        ctx.beginPath(); ctx.ellipse(this.radius * 0.8, -this.radius * 0.4, this.radius * 0.7, this.radius * 0.4, 0.2, 0, Math.PI*2); ctx.fill();
        ctx.fillStyle = 'black'; ctx.beginPath(); ctx.arc(this.radius * 1.1, -this.radius * 0.5, this.isBoss ? 6 : 2, 0, Math.PI*2); ctx.fill();
        ctx.restore();
        ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(drawX - this.radius, drawY - this.radius - 20, this.radius*2, 6);
        ctx.fillStyle = '#ef4444'; ctx.fillRect(drawX - this.radius, drawY - this.radius - 20, this.radius*2 * (this.hp/this.maxHp), 6);
    }
}

class Projectile {
    constructor(x, y, targetX, targetY, angleOffset = 0) {
        this.x = x; this.y = y;
        this.radius = 6;
        this.speed = 14;
        this.damage = 10 * player.damageMod;
        const dx = targetX - x;
        const dy = targetY - y;
        let angle = Math.atan2(dy, dx) + angleOffset;
        this.vx = Math.cos(angle) * this.speed;
        this.vy = Math.sin(angle) * this.speed;
        this.trail = [];
    }
    update() {
        this.trail.push({x: this.x, y: this.y});
        if (this.trail.length > 8) this.trail.shift();
        this.x += this.vx; this.y += this.vy;
    }
    draw(ctx, camX, camY) {
        ctx.save(); ctx.shadowBlur = 15; ctx.shadowColor = '#67e8f9';
        this.trail.forEach((p, i) => {
            ctx.globalAlpha = i / this.trail.length;
            ctx.fillStyle = '#22d3ee';
            ctx.beginPath(); ctx.arc(p.x - camX, p.y - camY, this.radius * (i/this.trail.length), 0, Math.PI*2); ctx.fill();
        });
        ctx.globalAlpha = 1; ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(this.x - camX, this.y - camY, this.radius, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
    }
}

const player = new Player();
const enemies = [];
const projectiles = [];
const xpGems = [];
const healDrops = [];
let spawnTimer = 0;

function showLevelUpScreen() {
    isPaused = true;
    levelUpScreen.style.display = 'flex';
    skillOptionsEl.innerHTML = '';
    const shuffled = [...SKILLS].sort(() => 0.5 - Math.random());
    shuffled.slice(0, 3).forEach(skill => {
        const btn = document.createElement('button');
        btn.className = 'skill-btn';
        btn.innerHTML = `<span class="skill-name">${skill.name}</span><span class="skill-desc">${skill.desc}</span>`;
        btn.onclick = () => {
            skill.effect(player);
            isPaused = false;
            levelUpScreen.style.display = 'none';
            player.updateUI();
            animate();
        };
        skillOptionsEl.appendChild(btn);
    });
}

function updateCamera() {
    camera.x = player.x - canvas.width / 2;
    camera.y = player.y - canvas.height / 2;
    camera.x = Math.max(0, Math.min(world.width - canvas.width, camera.x));
    camera.y = Math.max(0, Math.min(world.height - canvas.height, camera.y));
}

function drawBackground() {
    ctx.fillStyle = '#141e15'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = 'rgba(255,255,255,0.03)'; ctx.lineWidth = 1;
    const gridSize = 150;
    const offsetX = -camera.x % gridSize;
    const offsetY = -camera.y % gridSize;
    for(let x = offsetX; x < canvas.width; x += gridSize) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke(); }
    for(let y = offsetY; y < canvas.height; y += gridSize) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke(); }
    ctx.fillStyle = 'rgba(5, 20, 10, 0.4)';
    for(let i=0; i<10; i++) {
        const px = (i * 800 - camera.x * 0.2) % (world.width);
        const py = (i * 600 - camera.y * 0.2) % (world.height);
        ctx.beginPath(); ctx.arc(px - camera.x*0.1, py - camera.y*0.1, 400, 0, Math.PI*2); ctx.fill();
    }
}

function applyChainLightning(targetEnemy, count) {
    if (count <= 0) return;
    let candidates = enemies.filter(e => e !== targetEnemy).sort((a, b) => {
        const da = Math.sqrt((a.x - targetEnemy.x)**2 + (a.y - targetEnemy.y)**2);
        const db = Math.sqrt((b.x - targetEnemy.x)**2 + (b.y - targetEnemy.y)**2);
        return da - db;
    });

    const jumps = candidates.slice(0, count);
    jumps.forEach(e => {
        e.takeDamage(10 * player.damageMod, targetEnemy.x, targetEnemy.y);
        // Visual effect
        ctx.save();
        ctx.strokeStyle = '#67e8f9'; ctx.lineWidth = 3; ctx.shadowBlur = 10; ctx.shadowColor = '#67e8f9';
        ctx.beginPath(); ctx.moveTo(targetEnemy.x - camera.x, targetEnemy.y - camera.y); ctx.lineTo(e.x - camera.x, e.y - camera.y); ctx.stroke();
        ctx.restore();
        spawnParticles(e.x, e.y, '#67e8f9', 5, 'lightning');
    });
}

function drawLighting() {
    ctx.save(); ctx.globalCompositeOperation = 'screen';
    const timeOffset = Math.sin(gameTime * 0.01) * 50;
    const rayGrad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    rayGrad.addColorStop(0, 'rgba(255, 255, 200, 0.05)'); rayGrad.addColorStop(0.5, 'rgba(255, 255, 200, 0)'); rayGrad.addColorStop(1, 'rgba(255, 255, 200, 0.05)');
    ctx.fillStyle = rayGrad;
    for(let i=0; i<5; i++) {
        ctx.beginPath(); ctx.moveTo(i*400 + timeOffset, -100); ctx.lineTo(i*400 + 200 + timeOffset, -100); ctx.lineTo(i*400 - 400 + timeOffset, canvas.height + 100); ctx.lineTo(i*400 - 600 + timeOffset, canvas.height + 100); ctx.fill();
    }
    ctx.restore();
    const drawX = player.x - camera.x; const drawY = player.y - camera.y;
    const playerGlow = ctx.createRadialGradient(drawX, drawY, 20, drawX, drawY, 300);
    playerGlow.addColorStop(0, 'rgba(255, 255, 255, 0.15)'); playerGlow.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.globalCompositeOperation = 'screen'; ctx.fillStyle = playerGlow; ctx.fillRect(0, 0, canvas.width, canvas.height);
    const vignette = ctx.createRadialGradient(canvas.width/2, canvas.height/2, canvas.width/4, canvas.width/2, canvas.height/2, canvas.width*0.8);
    vignette.addColorStop(0, 'rgba(0, 0, 0, 0)'); vignette.addColorStop(1, 'rgba(0, 0, 0, 0.8)');
    ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = vignette; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.globalCompositeOperation = 'source-over';
}

function formatTime(frames) {
    const totalSeconds = Math.floor(frames / 60);
    const mins = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
    const secs = (totalSeconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
}

window.restartGame = function() { location.reload(); }

function animate() {
    if (gameOver || isPaused) return;
    requestAnimationFrame(animate);
    gameTime++;
    timerEl.textContent = formatTime(gameTime);
    updateCamera();
    drawBackground();
    
    // Pickups
    for(let i = xpGems.length - 1; i >= 0; i--) {
        const gem = xpGems[i]; gem.draw(ctx, camera.x, camera.y);
        const dist = Math.sqrt((gem.x - player.x)**2 + (gem.y - player.y)**2);
        if (dist < 30) { player.gainXP(gem.value); xpGems.splice(i, 1); }
        else if (dist < 200) { gem.x += (player.x - gem.x) * 0.12; gem.y += (player.y - gem.y) * 0.12; }
    }
    for(let i = healDrops.length - 1; i >= 0; i--) {
        const d = healDrops[i]; d.draw(ctx, camera.x, camera.y);
        const dist = Math.sqrt((d.x - player.x)**2 + (d.y - player.y)**2);
        if (dist < 30) { player.hp = Math.min(player.maxHp, player.hp + 1); player.updateUI(); healDrops.splice(i, 1); }
    }

    for(let i = particles.length - 1; i >= 0; i--) {
        particles[i].update(); particles[i].draw(ctx, camera.x, camera.y);
        if (particles[i].life <= 0) particles.splice(i, 1);
    }
    player.update();
    player.draw(ctx, camera.x, camera.y);

    // Combat
    if (player.attackCooldown <= 0 && enemies.length > 0) {
        let nearest = null; let minDist = 800;
        enemies.forEach(e => {
            const d = Math.sqrt((e.x - player.x)**2 + (e.y - player.y)**2);
            if (d < minDist) { minDist = d; nearest = e; }
        });
        if (nearest) {
            projectiles.push(new Projectile(player.x, player.y, nearest.x, nearest.y));
            for(let i=0; i<player.multiShot; i++) {
                projectiles.push(new Projectile(player.x, player.y, nearest.x, nearest.y, (i+1)*0.2));
                projectiles.push(new Projectile(player.x, player.y, nearest.x, nearest.y, -(i+1)*0.2));
            }
            player.attackCooldown = player.baseAttackSpeed * player.attackSpeedMod;
        }
    }

    for (let i = projectiles.length - 1; i >= 0; i--) {
        const p = projectiles[i]; p.update(); p.draw(ctx, camera.x, camera.y);
        if (p.x < camera.x - 200 || p.x > camera.x + canvas.width + 200) { projectiles.splice(i, 1); continue; }
        for (let j = enemies.length - 1; j >= 0; j--) {
            const e = enemies[j];
            if (Math.sqrt((p.x - e.x)**2 + (p.y - e.y)**2) < p.radius + e.radius) {
                e.takeDamage(p.damage, p.x, p.y);
                if (player.chainLightningCount > 0) applyChainLightning(e, player.chainLightningCount);
                projectiles.splice(i, 1);
                if (e.hp <= 0) {
                    score += e.isBoss ? 5000 : (e.isElite ? 150 : 20);
                    scoreEl.textContent = `Score: ${score}`;
                    spawnParticles(e.x, e.y, '#fff', 15, 'spark');
                    xpGems.push(new XPGem(e.x, e.y, e.isBoss ? 1000 : (e.isElite ? 100 : 30)));
                    if (Math.random() < 0.05) healDrops.push(new HealDrop(e.x, e.y));
                    enemies.splice(j, 1);
                }
                break;
            }
        }
    }

    // Spawning
    spawnTimer++;
    if (gameTime > 0 && gameTime % (180 * 60) === 0) { // Every 3 minutes
        enemies.push(new Enemy(false, true));
    }
    const spawnRate = Math.max(8, 45 - Math.floor(gameTime / 600));
    if (spawnTimer > spawnRate) { enemies.push(new Enemy(gameTime % 2400 < 120, false)); spawnTimer = 0; }

    for (let i = enemies.length - 1; i >= 0; i--) {
        const e = enemies[i]; e.update(player); e.draw(ctx, camera.x, camera.y);
        if (Math.sqrt((e.x - player.x)**2 + (e.y - player.y)**2) < e.radius + player.radius) {
            player.takeDamage(0.4, e.x, e.y);
            if (player.hp <= 0) {
                gameOver = true;
                document.getElementById('game-over-screen').style.display = 'flex';
                document.getElementById('final-score').textContent = score;
                document.getElementById('final-time').textContent = formatTime(gameTime);
            }
        }
    }
    drawLighting();
}
animate();