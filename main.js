document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('gameCanvas');
    const ctx = canvas.getContext('2d');

    const xpBarEl = document.getElementById('xp-bar-fill');
    const levelTextEl = document.getElementById('level-text');
    const hpBarEl = document.getElementById('hp-bar-fill');
    const scoreEl = document.getElementById('score-value');
    const timerEl = document.getElementById('timer-value');
    const levelUpScreen = document.getElementById('level-up-screen');
    const skillOptionsEl = document.getElementById('skill-options');
    const gameOverScreen = document.getElementById('game-over-screen');

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
            lvlUpSubtitle: "Choose your upgrade",
            gameOverTitle: "GAME OVER",
            finalScoreLabel: "Final Score",
            finalTimeLabel: "Final Time",
            restartBtn: "RESTART",
            skills: {
                atk_speed: { name: "Rapid Strikes", desc: "Increases attack speed by 20%." },
                damage: { name: "Sharp Claws", desc: "Increases attack damage by 30%." },
                move_speed: { name: "Jungle Predator", desc: "Increases movement speed by 15%." },
                multi_shot: { name: "Pack Hunter", desc: "Fires an additional projectile." },
                chain_lightning: { name: "Chain Lightning", desc: "Attacks chain to 2 nearby enemies." },
                dodge: { name: "Dodge", desc: "10% chance to dodge enemy attacks." },
                heal: { name: "Primal Vigor", desc: "Heals for 40% of max HP." },
                max_hp: { name: "Ancient Vigor", desc: "Increases max HP by 25%." }
            }
        }
    };
    let currentLang = 'ko';

    let player, enemies, projectiles, xpOrbs, score, time, gameOver, isPaused;
    let spawnTimer = 0;
    let timerInterval;

    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    window.addEventListener('resize', resizeCanvas);

    class Player {
        constructor(x, y, radius) {
            this.x = x;
            this.y = y;
            this.radius = radius;
            this.speed = 3;
            this.hp = 100;
            this.maxHp = 100;
            this.xp = 0;
            this.xpToNext = 100;
            this.level = 1;
            this.attackSpeed = 1.2;
            this.attackCooldown = 0;
            this.damage = 10;
            this.dodgeChance = 0;
            this.multiShot = 1;
            this.chainLightning = 0;
            this.facing = 'right';
        }

        draw(ctx) {
            ctx.save();
            ctx.translate(this.x, this.y);
            
            // Body
            ctx.beginPath();
            ctx.arc(0, 0, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = '#4CAF50';
            ctx.fill();
            ctx.strokeStyle = '#2E7D32';
            ctx.lineWidth = 3;
            ctx.stroke();

            // Eye
            ctx.fillStyle = 'white';
            const eyeX = this.facing === 'right' ? 8 : -8;
            ctx.beginPath();
            ctx.arc(eyeX, -5, 5, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = 'black';
            ctx.beginPath();
            ctx.arc(eyeX + (this.facing === 'right' ? 2 : -2), -5, 2, 0, Math.PI * 2);
            ctx.fill();
            
            ctx.restore();
        }

        update(joystick) {
            const dx = joystick.horizontal;
            const dy = joystick.vertical;

            if (dx > 0) this.facing = 'right';
            else if (dx < 0) this.facing = 'left';

            this.x += dx * this.speed;
            this.y += dy * this.speed;
            
            this.x = Math.max(this.radius, Math.min(canvas.width - this.radius, this.x));
            this.y = Math.max(this.radius, Math.min(canvas.height - this.radius, this.y));

            if (this.attackCooldown > 0) {
                this.attackCooldown -= 1 / 60;
            } else {
                autoAttack();
                this.attackCooldown = 1 / this.attackSpeed;
            }
        }

        takeDamage(amount) {
            if (Math.random() < this.dodgeChance) return;
            this.hp -= amount;
            if (this.hp <= 0) {
                this.hp = 0;
                endGame();
            }
        }

        gainXp(amount) {
            this.xp += amount;
            if (this.xp >= this.xpToNext) {
                this.levelUp();
            }
        }

        levelUp() {
            this.level++;
            this.xp -= this.xpToNext;
            this.xpToNext = Math.floor(this.xpToNext * 1.35);
            showLevelUpScreen();
        }

        updateUI() {
            const t = translations[currentLang];
            xpBarEl.style.width = (this.xp / this.xpToNext * 100) + '%';
            levelTextEl.textContent = `${t.level} ${this.level}`;
            hpBarEl.style.width = (this.hp / this.maxHp * 100) + '%';
            scoreEl.textContent = score;
        }
    }

    class Enemy {
        constructor(x, y, radius, color, speed, hp, damage) {
            this.x = x;
            this.y = y;
            this.radius = radius;
            this.color = color;
            this.speed = speed;
            this.hp = hp;
            this.maxHp = hp;
            this.damage = damage;
        }

        draw(ctx) {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = this.color;
            ctx.fill();
            ctx.strokeStyle = '#B71C1C';
            ctx.lineWidth = 2;
            ctx.stroke();
            
            const barWidth = this.radius * 2;
            const barHeight = 4;
            ctx.fillStyle = 'rgba(0,0,0,0.5)';
            ctx.fillRect(this.x - this.radius, this.y - this.radius - 10, barWidth, barHeight);
            ctx.fillStyle = '#ff4d4d';
            ctx.fillRect(this.x - this.radius, this.y - this.radius - 10, barWidth * (this.hp / this.maxHp), barHeight);
        }

        update(player) {
            const angle = Math.atan2(player.y - this.y, player.x - this.x);
            this.x += Math.cos(angle) * this.speed;
            this.y += Math.sin(angle) * this.speed;
        }
    }

    class Projectile {
        constructor(x, y, radius, color, velocity, damage, chainCount = 0) {
            this.x = x;
            this.y = y;
            this.radius = radius;
            this.color = color;
            this.velocity = velocity;
            this.damage = damage;
            this.chainCount = chainCount;
            this.hitEnemies = new Set();
        }

        draw(ctx) {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = this.color;
            ctx.fill();
            ctx.shadowBlur = 10;
            ctx.shadowColor = this.color;
            ctx.fill();
            ctx.shadowBlur = 0;
        }

        update() {
            this.x += this.velocity.x;
            this.y += this.velocity.y;
        }
    }
    
    class XpOrb {
        constructor(x, y) {
            this.x = x;
            this.y = y;
            this.radius = 5;
            this.value = 20;
        }

        draw(ctx) {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = '#00f2ff';
            ctx.fill();
            ctx.strokeStyle = 'white';
            ctx.lineWidth = 1;
            ctx.stroke();
        }
    }

    function init() {
        resizeCanvas();
        score = 0;
        time = 0;
        gameOver = false;
        isPaused = false;
        spawnTimer = 0;
        
        player = new Player(canvas.width / 2, canvas.height / 2, 20);
        enemies = [];
        projectiles = [];
        xpOrbs = [];
        
        if (timerInterval) clearInterval(timerInterval);
        timerInterval = setInterval(updateTimer, 1000);
        
        levelUpScreen.style.display = 'none';
        gameOverScreen.style.display = 'none';

        updateLanguageUI();
        requestAnimationFrame(animate);
    }
    
    function animate() {
        if (gameOver) return;
        if (isPaused) {
            requestAnimationFrame(animate);
            return;
        }
        
        ctx.fillStyle = '#050505';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        spawnTimer -= 1/60;
        if (spawnTimer <= 0) {
            spawnEnemy();
            spawnTimer = Math.max(0.4, 2.5 - time * 0.01);
        }

        player.update(joystick);
        player.draw(ctx);
        
        for (let i = enemies.length - 1; i >= 0; i--) {
            const enemy = enemies[i];
            enemy.update(player);
            enemy.draw(ctx);
            
            if (checkCollision(player, enemy)) {
                player.takeDamage(enemy.damage);
            }
        }
        
        for (let i = projectiles.length - 1; i >= 0; i--) {
            const proj = projectiles[i];
            proj.update();
            proj.draw(ctx);
            
            let hit = false;
            for (let j = enemies.length - 1; j >= 0; j--) {
                const enemy = enemies[j];
                if (checkCollision(proj, enemy) && !proj.hitEnemies.has(enemy)) {
                    enemy.hp -= proj.damage;
                    proj.hitEnemies.add(enemy);
                    
                    if (enemy.hp <= 0) {
                        score += 10;
                        xpOrbs.push(new XpOrb(enemy.x, enemy.y));
                        enemies.splice(j, 1);
                    }
                    
                    if (proj.chainCount > 0) {
                        proj.chainCount--;
                        const nextEnemy = enemies.find(e => e !== enemy && !proj.hitEnemies.has(e) && Math.hypot(e.x - proj.x, e.y - proj.y) < 200);
                        if (nextEnemy) {
                            const angle = Math.atan2(nextEnemy.y - proj.y, nextEnemy.x - proj.x);
                            proj.velocity = { x: Math.cos(angle) * 8, y: Math.sin(angle) * 8 };
                        } else {
                            hit = true;
                        }
                    } else {
                        hit = true;
                    }
                    break;
                }
            }
            
            if (hit || proj.x < 0 || proj.x > canvas.width || proj.y < 0 || proj.y > canvas.height) {
                projectiles.splice(i, 1);
            }
        }
        
        for (let i = xpOrbs.length - 1; i >= 0; i--) {
            const orb = xpOrbs[i];
            orb.draw(ctx);
            if (checkCollision(player, orb)) {
                player.gainXp(orb.value);
                xpOrbs.splice(i, 1);
            }
        }

        player.updateUI();
        requestAnimationFrame(animate);
    }
    
    function checkCollision(obj1, obj2) {
        const dist = Math.hypot(obj1.x - obj2.x, obj1.y - obj2.y);
        return dist < obj1.radius + obj2.radius;
    }

    function spawnEnemy() {
        const radius = 15 + Math.random() * 10;
        const edge = Math.floor(Math.random() * 4);
        let x, y;
        if (edge === 0) { x = -radius; y = Math.random() * canvas.height; }
        else if (edge === 1) { x = canvas.width + radius; y = Math.random() * canvas.height; }
        else if (edge === 2) { x = Math.random() * canvas.width; y = -radius; }
        else { x = Math.random() * canvas.width; y = canvas.height + radius; }
        
        const speed = 1.2 + (time * 0.012);
        const hp = 20 + (time * 0.6);
        const damage = 5;
        enemies.push(new Enemy(x, y, radius, '#D32F2F', speed, hp, damage));
    }
    
    function autoAttack() {
        if (enemies.length === 0) return;
        
        const sortedEnemies = [...enemies].sort((a, b) => {
            return Math.hypot(player.x - a.x, player.y - a.y) - Math.hypot(player.x - b.x, player.y - b.y);
        });

        for (let i = 0; i < Math.min(player.multiShot, sortedEnemies.length); i++) {
            const target = sortedEnemies[i];
            const angle = Math.atan2(target.y - player.y, target.x - player.x);
            const velocity = { x: Math.cos(angle) * 8, y: Math.sin(angle) * 8 };
            projectiles.push(new Projectile(player.x, player.y, 6, '#FFEB3B', velocity, player.damage, player.chainLightning));
        }
    }
    
    function updateTimer() {
        if (isPaused || gameOver) return;
        time++;
        const minutes = Math.floor(time / 60).toString().padStart(2, '0');
        const seconds = (time % 60).toString().padStart(2, '0');
        timerEl.textContent = `${minutes}:${seconds}`;
    }
    
    function showLevelUpScreen() {
        isPaused = true;
        levelUpScreen.style.display = 'flex';
        skillOptionsEl.innerHTML = '';
        
        const skillKeys = Object.keys(translations[currentLang].skills);
        const shuffled = skillKeys.sort(() => 0.5 - Math.random());
        const selected = shuffled.slice(0, 3);
        
        selected.forEach(key => {
            const skill = translations[currentLang].skills[key];
            const btn = document.createElement('button');
            btn.className = 'skill-btn';
            btn.innerHTML = `
                <span class="skill-name">${skill.name}</span>
                <span class="skill-desc">${skill.desc}</span>
            `;
            btn.onclick = () => applySkill(key);
            skillOptionsEl.appendChild(btn);
        });
    }

    function applySkill(key) {
        switch(key) {
            case 'atk_speed': player.attackSpeed *= 1.2; break;
            case 'damage': player.damage *= 1.3; break;
            case 'move_speed': player.speed *= 1.15; break;
            case 'multi_shot': player.multiShot += 1; break;
            case 'chain_lightning': player.chainLightning += 2; break;
            case 'dodge': player.dodgeChance += 0.1; break;
            case 'heal': player.hp = Math.min(player.maxHp, player.hp + player.maxHp * 0.4); break;
            case 'max_hp': 
                const gain = player.maxHp * 0.25;
                player.maxHp += gain;
                player.hp += gain;
                break;
        }
        isPaused = false;
        levelUpScreen.style.display = 'none';
    }
    
    function endGame() {
        gameOver = true;
        isPaused = true;
        if (timerInterval) clearInterval(timerInterval);
        gameOverScreen.style.display = 'flex';
        document.getElementById('final-score-value').textContent = score;
        document.getElementById('final-time-value').textContent = timerEl.textContent;
    }

    window.restartGame = function() {
        init();
    }
    
    window.setLanguage = function(lang) {
        currentLang = lang;
        updateLanguageUI();
        if (isPaused && levelUpScreen.style.display === 'flex') {
            showLevelUpScreen();
        }
    }
    
    function updateLanguageUI() {
        const t = translations[currentLang];
        document.getElementById('score-label').textContent = t.score;
        document.getElementById('timer-label').textContent = t.timer;
        document.getElementById('lvl-up-title').textContent = t.lvlUpTitle;
        document.getElementById('lvl-up-subtitle').textContent = t.lvlUpSubtitle;
        document.getElementById('game-over-title').textContent = t.gameOverTitle;
        document.getElementById('final-score-label').textContent = t.finalScoreLabel;
        document.getElementById('final-time-label').textContent = t.finalTimeLabel;
        document.getElementById('restart-btn').textContent = t.restartBtn;
    }
    
    // Floating Joystick Logic
    const joystickContainer = document.getElementById('joystick-container');
    const joystickBase = document.getElementById('joystick-base');
    const joystickHandle = document.getElementById('joystick-handle');
    const joystick = { horizontal: 0, vertical: 0 };
    let joystickActive = false;
    let joystickStartX = 0;
    let joystickStartY = 0;
    
    function onJoystickStart(e) {
        if (isPaused || gameOver) return;
        joystickActive = true;
        const touch = e.type === 'touchstart' ? e.touches[0] : e;
        
        joystickStartX = touch.clientX;
        joystickStartY = touch.clientY;
        
        joystickBase.style.left = joystickStartX + 'px';
        joystickBase.style.top = joystickStartY + 'px';
        joystickBase.style.display = 'block';
        joystickBase.style.opacity = '1';
    }

    function onJoystickMove(e) {
        if (!joystickActive) return;
        const touch = e.type === 'touchmove' ? e.touches[0] : e;
        const deltaX = touch.clientX - joystickStartX;
        const deltaY = touch.clientY - joystickStartY;
        const distance = Math.min(60, Math.hypot(deltaX, deltaY));
        const angle = Math.atan2(deltaY, deltaX);
        
        joystick.horizontal = Math.cos(angle) * (distance / 60);
        joystick.vertical = Math.sin(angle) * (distance / 60);
        
        joystickHandle.style.transform = `translate(calc(-50% + ${Math.cos(angle) * distance}px), calc(-50% + ${Math.sin(angle) * distance}px))`;
    }

    function onJoystickEnd() {
        joystickActive = false;
        joystick.horizontal = 0;
        joystick.vertical = 0;
        joystickBase.style.display = 'none';
        joystickHandle.style.transform = `translate(-50%, -50%)`;
    }
    
    joystickContainer.addEventListener('mousedown', onJoystickStart);
    window.addEventListener('mousemove', onJoystickMove);
    window.addEventListener('mouseup', onJoystickEnd);
    joystickContainer.addEventListener('touchstart', onJoystickStart, { passive: false });
    window.addEventListener('touchmove', onJoystickMove, { passive: false });
    window.addEventListener('touchend', onJoystickEnd);

    init();
});
