# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Dino Survivors Deluxe** — a browser-based, Vampire Survivors-style action game. The player controls a dinosaur that auto-attacks the nearest enemy; the goal is to survive as long as possible while gaining XP, leveling up, and selecting upgrades. There is no build system, no package manager, and no test suite. The entire game is three files: `index.html`, `main.js`, `style.css`.

## Development

### Running locally

Open `index.html` directly in a browser, or serve the root directory over HTTP to avoid any CORS quirks:

```bash
python3 -m http.server 8080
# then open http://localhost:8080
```

### Deployment (Firebase Hosting)

```bash
firebase deploy --only hosting
```

`firebase.json` sets the public root to `.` (the repo root), so all three files are served as-is.

## Architecture

### File layout

| File | Role |
|------|------|
| `index.html` | DOM shell: canvas, HUD overlay elements, level-up and game-over screens |
| `main.js` | All game logic — ~610 lines of vanilla JS |
| `style.css` | HUD, overlay screens (glassmorphism), skill buttons |

### Game loop (`main.js`)

`animate()` is driven by `requestAnimationFrame`. It is halted when `isPaused` or `gameOver` is `true`, and **must be restarted explicitly** (e.g. `animate()` call inside the level-up skill selection handler) after unpausing.

Each frame increments the global `gameTime` counter. One second of real time ≈ 60 frames (`gameTime / 60`). Time-scaled values (spawn rate, enemy HP scaling) are derived from `gameTime / 3600` (minutes).

### World & camera

The world is a fixed 4000×4000 grid. `camera` is an object `{x, y}` updated each frame to center on the player while clamped to world bounds. All `draw()` methods accept `(ctx, camX, camY)` and subtract the camera offset from world coordinates.

### Entity classes

- **`Player`** — Singleton (`const player = new Player()`). Holds all upgrade state: `damageMod`, `attackSpeedMod`, `multiShot`, `chainLightningCount`, `dodgeChance`. `update()` reads the `keys` map for WASD/arrow movement and handles the dash system (Shift key).
- **`Enemy`** — Spawns off the visible viewport edges. Three tiers: normal / elite (`isElite`) / boss (`isBoss`). Bosses use a charge pattern (`updateBossLogic`). HP and speed scale with elapsed time.
- **`Projectile`** — Fired automatically toward the nearest enemy within 800 px. `angleOffset` enables multi-shot spread.
- **`Particle`** — Three visual types: `dust`, `spark`, `lightning`. Managed in the global `particles` array; dead particles (`.life <= 0`) are spliced out each frame.
- **`XPGem` / `HealDrop`** — Dropped on enemy death; magnetically pulled toward the player within 200 px.

### Upgrade system (SKILLS)

`SKILLS` is a plain array of objects `{ id, name, desc, effect(player) }`. On level-up, 3 are picked at random and rendered as buttons. Selecting a button calls `skill.effect(player)`, directly mutating the player's stat fields — there is no separate upgrade-tracking state.

### Spawning schedule

| Event | Trigger |
|-------|---------|
| Normal enemy | Every `spawnRate` frames; `spawnRate` starts at 45 and decreases by 1 every 600 frames, floored at 8 |
| Elite wave | When `gameTime % 2400 < 120` (a 2-second window every 40 seconds) |
| Boss | `gameTime % (180 * 60) === 0` — every 3 minutes |

### Rendering order (per frame)

1. `drawBackground()` — dark fill + subtle grid + parallax blobs
2. XP gems & heal drops
3. Particles
4. Player
5. Projectiles → hit detection → enemy death handling
6. Enemy spawning + enemy update/draw + player collision
7. `drawLighting()` — additive player glow, vignette, animated light rays (drawn last, on top of everything)
