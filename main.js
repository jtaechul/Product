
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('gameCanvas');
    const ctx = canvas.getContext('2d');

    const gameContainer = document.getElementById('game-container');
    const xpBarEl = document.getElementById('xp-bar-fill');
    const levelTextEl = document.getElementById('level-text');
    const hpBarEl = document.getElementById('hp-bar-fill');
    const scoreEl = document.getElementById('score-value');
    const timerEl = document.getElementById('timer-value');
    const levelUpScreen = document.getElementById('level-up-screen');
    const gameOverScreen = document.getElementById('game-over-screen');

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

    // --- NEW: Player Sprite Images ---
    const dinoIdleImg = new Image();
    dinoIdleImg.src = 'dino_idle.png';

    const dinoWalkImg = new Image();
    dinoWalkImg.src = 'dino_walk.png';
    // ---

    let player, enemies, projectiles, xpOrbs, score, time, gameInterval, gameOver, isPaused;
    let gameFrameCounter = 0; // For animations

    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    window.addEventListener('resize', resizeCanvas);

    class Player {
        constructor(x, y, radius) {
            this.x = x;
            this.y = y;
            this.radius = radius; // For collision detection
            this.speed = 3;
            this.hp = 100;
            this.maxHp = 100;
            this.xp = 0;
            this.xpToNext = 100;
            this.level = 1;
            this.attackSpeed = 1; // attacks per second
            this.attackCooldown = 0;
            this.damage = 10;
            this.dodgeChance = 0;
            this.multiShot = 1;

            // --- NEW: Animation and State ---
            this.state = 'idle'; // 'idle', 'walking'
            this.facing = 'right'; // 'left', 'right'
            this.animationFrame = 0;
            this.walkSpriteFrames = 5; // Number of frames in the walk animation
            this.animationSpeed = 8; // Animation speed, lower is faster
            this.internalFrameCounter = 0;
        }

        draw(ctx) {
            let currentSprite;
            let frameCount;

            if (this.state === 'walking') {
                currentSprite = dinoWalkImg;
                frameCount = this.walkSpriteFrames;
            } else {
                currentSprite = dinoIdleImg;
                frameCount = 1;
            }

            if (currentSprite.complete && currentSprite.naturalWidth > 0) {
                const spriteSheetWidth = currentSprite.width;
                const spriteSheetHeight = currentSprite.height;
                const spriteWidth = spriteSheetWidth / frameCount;
                const spriteHeight = spriteSheetHeight;

                if (this.state === 'walking') {
                    this.animationFrame = Math.floor(this.internalFrameCounter / this.animationSpeed) % frameCount;
                } else {
                    this.animationFrame = 0;
                }

                const aspectRatio = spriteWidth / spriteHeight;
                const drawHeight = this.radius * 3.5;
                const drawWidth = drawHeight * aspectRatio;

                ctx.save();
                ctx.translate(this.x, this.y);
                if (this.facing === 'left') {
                    ctx.scale(-1, 1);
                }
                ctx.drawImage(
                    currentSprite,
                    this.animationFrame * spriteWidth, 0, spriteWidth, spriteHeight,
                    -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight
                );
                ctx.restore();
            }
        }

        update(joystick) {
            this.internalFrameCounter++;
            const dx = joystick.horizontal;
            const dy = joystick.vertical;

            if (dx === 0 && dy === 0) {
                this.state = 'idle';
            } else {
                this.state = 'walking';
                if (dx > 0) this.facing = 'right';
                else if (dx < 0) this.facing = 'left';
            }

            this.x += dx * this.speed;
            this.y += dy * this.speed;
            
            // Boundary checks
            this.x = Math.max(this.radius, Math.min(canvas.width - this.radius, this.x));
            this.y = Math.max(this.radius, Math.min(canvas.height - this.radius, this.y));

            // Attack cooldown
            if (this.attackCooldown > 0) {
                this.attackCooldown -= 1 / 60; // Assuming 60 FPS
            }
        }

        takeDamage(amount) {
            if (Math.random() < this.dodgeChance) {
                // Dodge successful
                return;
            }
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
            levelTextEl.textContent = \`${t.level} ${this.level}\`;
            hpBarEl.style.width = (this.hp / this.maxHp * 100) + '%';
            scoreEl.textContent = \`${t.score}: ${score}\`;
        }
    }
    
    // ... (Keep Enemy, Projectile, XpOrb classes the same)
    class Enemy {
        constructor(x, y, radius, color, speed, hp, damage) {
            this.x = x;
            this.y = y;
            this.radius = radius;
            this.color = color;
            this.speed = speed;
            this.hp = hp;
            this.damage = damage;
        }

        draw(ctx) {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = this.color;
            ctx.fill();
        }

        update(player) {
            const angle = Math.atan2(player.y - this.y, player.x - this.x);
            this.x += Math.cos(angle) * this.speed;
            this.y += Math.sin(angle) * this.speed;
        }
    }

    class Projectile {
        constructor(x, y, radius, color, velocity, damage) {
            this.x = x;
            this.y = y;
            this.radius = radius;
            this.color = color;
            this.velocity = velocity;
            this.damage = damage;
            this.chainTargets = 0; // for chain lightning
        }

        draw(ctx) {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = this.color;
            ctx.fill();
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
            ctx.fillStyle = 'cyan';
            ctx.fill();
        }
    }


    function init() {
        resizeCanvas();
        score = 0;
        time = 0;
        gameOver = false;
        isPaused = false;
        
        player = new Player(canvas.width / 2, canvas.height / 2, 20);
        enemies = [];
        projectiles = [];
        xpOrbs = [];
        
        spawnEnemy();

        gameInterval = setInterval(gameLoop, 1000 / 60);
        setInterval(updateTimer, 1000);
        
        levelUpScreen.style.display = 'none';
        gameOverScreen.style.display = 'none';

        updateLanguageUI();
        animate();
    }
    
    function gameLoop() {
        if (isPaused) return;
        gameFrameCounter++;

        // Player attack
        if (player.attackCooldown <= 0) {
            autoAttack();
            player.attackCooldown = 1 / player.attackSpeed;
        }
    }

    function animate() {
        if (isPaused || gameOver) return;
        
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        player.update(joystick);
        player.draw(ctx);
        
        enemies.forEach((enemy, eIndex) => {
            enemy.update(player);
            enemy.draw(ctx);
            // Player-Enemy collision
            if (checkCollision(player, enemy)) {
                player.takeDamage(enemy.damage);
            }
        });
        
        projectiles.forEach((proj, pIndex) => {
            proj.update();
            proj.draw(ctx);
            
            // Projectile-Enemy collision
            enemies.forEach((enemy, eIndex) => {
                if (checkCollision(proj, enemy)) {
                    enemy.hp -= proj.damage;
                    if (enemy.hp <= 0) {
                        score += 10;
                        xpOrbs.push(new XpOrb(enemy.x, enemy.y));
                        enemies.splice(eIndex, 1);
                    }
                    projectiles.splice(pIndex, 1);
                }
            });
            
            // Remove off-screen projectiles
            if (proj.x < 0 || proj.x > canvas.width || proj.y < 0 || proj.y > canvas.height) {
                projectiles.splice(pIndex, 1);
            }
        });
        
        xpOrbs.forEach((orb, oIndex) => {
            orb.draw(ctx);
            if (checkCollision(player, orb)) {
                player.gainXp(orb.value);
                xpOrbs.splice(oIndex, 1);
            }
        });

        player.updateUI();
        
        requestAnimationFrame(animate);
    }
    
    function checkCollision(obj1, obj2) {
        const dist = Math.hypot(obj1.x - obj2.x, obj1.y - obj2.y);
        return dist < obj1.radius + obj2.radius;
    }

    function spawnEnemy() {
        if (isPaused || gameOver) return;
        const radius = 15 + Math.random() * 10;
        const edge = Math.floor(Math.random() * 4);
        let x, y;
        if (edge === 0) { x = 0 - radius; y = Math.random() * canvas.height; }
        else if (edge === 1) { x = canvas.width + radius; y = Math.random() * canvas.height; }
        else if (edge === 2) { x = Math.random() * canvas.width; y = 0 - radius; }
        else { x = Math.random() * canvas.width; y = canvas.height + radius; }
        
        const speed = 1 + (time / 60);
        const hp = 20 + (time / 10);
        const damage = 5;
        enemies.push(new Enemy(x, y, radius, 'red', speed, hp, damage));
        
        setTimeout(spawnEnemy, Math.max(500, 3000 - time * 10));
    }
    
    function autoAttack() {
        if (enemies.length === 0) return;
        let closestEnemy = null;
        let minDistance = Infinity;

        enemies.forEach(enemy => {
            const distance = Math.hypot(player.x - enemy.x, player.y - enemy.y);
            if (distance < minDistance) {
                minDistance = distance;
                closestEnemy = enemy;
            }
        });

        if (closestEnemy) {
            const angle = Math.atan2(closestEnemy.y - player.y, closestEnemy.x - player.x);
            const velocity = { x: Math.cos(angle) * 5, y: Math.sin(angle) * 5 };
            projectiles.push(new Projectile(player.x, player.y, 5, 'yellow', velocity, player.damage));
        }
    }
    
    function updateTimer() {
        if (isPaused || gameOver) return;
        time++;
        const minutes = Math.floor(time / 60).toString().padStart(2, '0');
        const seconds = (time % 60).toString().padStart(2, '0');
        timerEl.textContent = \`${minutes}:${seconds}\`;
    }
    
    function showLevelUpScreen() {
        isPaused = true;
        levelUpScreen.style.display = 'flex';
        // Logic to show 3 random skills
    }
    
    function endGame() {
        gameOver = true;
        isPaused = true;
        clearInterval(gameInterval);
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
    }
    
    function updateLanguageUI() {
        const t = translations[currentLang];
        document.querySelector('#hud-top #stats-row #score-label').textContent = \`${t.score}:\`;
        document.querySelector('#hud-top #stats-row #timer-label').textContent = \`${t.timer}:\`;
        document.querySelector('#level-up-screen h1').textContent = t.lvlUpTitle;
        document.querySelector('#level-up-screen p').textContent = t.lvlUpSubtitle;
        document.querySelector('#game-over-screen h1').textContent = t.gameOverTitle;
        document.querySelector('#game-over-labels p:nth-child(1)').textContent = t.finalScoreLabel;
        document.querySelector('#game-over-labels p:nth-child(2)').textContent = t.finalTimeLabel;
        document.getElementById('restart-btn').textContent = t.restartBtn;
    }
    
    // Joystick Logic
    const joystickContainer = document.getElementById('joystick-container');
    const joystickHandle = document.getElementById('joystick-handle');
    const joystick = { horizontal: 0, vertical: 0 };
    let joystickActive = false;
    let joystickStartX = 0;
    let joystickStartY = 0;
    
    function onJoystickStart(e) {
        joystickActive = true;
        const touch = e.type === 'touchstart' ? e.touches[0] : e;
        joystickStartX = touch.clientX;
        joystickStartY = touch.clientY;
        joystickContainer.style.opacity = '1';
    }
    function onJoystickMove(e) {
        if (!joystickActive) return;
        e.preventDefault();
        const touch = e.type === 'touchmove' ? e.touches[0] : e;
        const deltaX = touch.clientX - joystickStartX;
        const deltaY = touch.clientY - joystickStartY;
        const distance = Math.min(75, Math.hypot(deltaX, deltaY));
        const angle = Math.atan2(deltaY, deltaX);
        
        joystick.horizontal = Math.cos(angle) * (distance / 75);
        joystick.vertical = Math.sin(angle) * (distance / 75);
        
        joystickHandle.style.transform = \`translate(\${Math.cos(angle) * distance}px, \${Math.sin(angle) * distance}px)\`;
    }
    function onJoystickEnd(e) {
        joystickActive = false;
        joystick.horizontal = 0;
        joystick.vertical = 0;
        joystickHandle.style.transform = \`translate(0px, 0px)\`;
        joystickContainer.style.opacity = '0.5';
    }
    
    gameContainer.addEventListener('mousedown', onJoystickStart);
    gameContainer.addEventListener('mousemove', onJoystickMove);
    gameContainer.addEventListener('mouseup', onJoystickEnd);
    gameContainer.addEventListener('mouseleave', onJoystickEnd);
    gameContainer.addEventListener('touchstart', onJoystickStart, { passive: false });
    gameContainer.addEventListener('touchmove', onJoystickMove, { passive: false });
    gameContainer.addEventListener('touchend', onJoystickEnd);

    // Init and start the game
    init();
});
