# Dino Survivors Deluxe

A browser-based survival game built with vanilla HTML5 Canvas, CSS, and JavaScript. The player controls a dinosaur, fights waves of enemies, collects XP, and picks upgrades on level-up. Deployed via Firebase Hosting.

## Project Structure

```
.
├── index.html       # Single-page HTML shell (canvas, HUD, level-up and game-over overlays)
├── main.js          # All game logic (~610 lines): player, enemies, projectiles, particles, game loop
├── style.css        # UI styling: HUD, glassmorphism overlays, skill buttons
├── firebase.json    # Firebase Hosting config (serves "." as the public directory)
├── .firebase/       # Firebase cache (auto-generated, gitignored content)
└── .idx/dev.nix     # Firebase Studio / IDX workspace config (Nix)
```

There is no build step, bundler, or package manager. The app is plain static files.

## Architecture

### Game Loop (`main.js`)
- `animate()` is the core `requestAnimationFrame` loop: advances `gameTime`, updates camera, draws background, processes pickups/particles/player/combat/spawning/lighting.
- Game pauses (`isPaused`) during the level-up screen; game stops (`gameOver`) on death.

### Key Classes
| Class | Purpose |
|-------|---------|
| `Player` | Movement (WASD/arrows), dash (Shift), auto-attack nearest enemy, XP/level system, knockback, procedural dino drawing |
| `Enemy` | Spawns off-screen, chases player. Variants: normal, elite (larger/tougher), boss (charges periodically). Stats scale with `gameTime`. |
| `Projectile` | Fired automatically toward nearest enemy. Trail rendering, chain lightning support. |
| `Particle` | Dust, spark, and lightning visual effects. |
| `XPGem` / `HealDrop` | Pickups dropped by enemies on death. |

### Skill / Upgrade System
`SKILLS` array defines 8 upgrades (attack speed, damage, move speed, multi-shot, chain lightning, evasion, heal, max HP). On level-up, 3 random skills are presented; each applies an `effect` function to the player.

### Rendering
All rendering is procedural Canvas 2D — no sprite sheets or images. Lighting uses composite operations (`screen`, `multiply`) for glow and vignette effects.

### Input
- Keyboard: WASD / arrow keys for movement, Left Shift for dash.
- No touch/mobile input is currently wired up (joystick code referenced in earlier commits was removed).

## Development

### Running Locally
Serve the project root with any static HTTP server:
```bash
python3 -m http.server 8000
# or
npx serve .
```
Then open `http://localhost:8000` in a browser.

### Deployment
The project deploys to Firebase Hosting. `firebase.json` serves the current directory as-is.

### No Build / No Tests
There is no build tool, no test framework, no linter, and no CI pipeline. Changes are tested manually in the browser.

## Conventions

- **Single-file JS**: all game logic lives in `main.js`. Keep it that way unless the file becomes unmanageable.
- **No external dependencies**: no npm, no libraries (except Google Fonts via CDN). Canvas API only.
- **Procedural art**: all graphics are drawn with Canvas primitives — don't introduce image assets without discussion.
- **Commit messages**: mixed Korean and English. Either language is acceptable.
- **World coordinates**: the game world is 4000×4000. Camera follows the player with clamping at edges.
- **Frame-based timing**: game time is counted in frames at 60fps (e.g., `180 * 60` frames = 3 minutes). There is no delta-time normalization.
- **Difficulty scaling**: enemy stats and spawn rate scale with `gameTime`. Bosses spawn every 3 minutes.
