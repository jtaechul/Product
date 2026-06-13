# Dino Survivors Deluxe

> ## ⭐ 핵심 응답 원칙 (모든 작업에 항상 적용)
> **매 작업이 끝나면, 마지막에 "방금 한 일"을 비전문가도 이해할 수 있게 아주 간단히
> 정리한다.** 규칙:
> - 3~5줄 이내, 쉬운 한국어. 전문용어는 풀어서 또는 괄호로 설명.
> - "무엇을 / 왜 / 결과" 위주. 코드·수치 나열 최소화.
> - 길고 자세한 내용이 필요하면 그건 정리 *뒤*에 따로 둔다(요약이 먼저).
>
> ## ⭐ 터미널/SSH 안내 원칙 (사용자는 터미널 초보)
> 사용자는 SSH·터미널·명령어를 다룰 줄 모른다. 서버(클라우드) 작업을 안내할 때는:
> - **키 하나, 한 단계까지** 빠짐없이. (예: "`q` 를 누르세요", "Ctrl 키를 누른 채 X")
> - 화면에 뜬 낯선 것(`(END)`, 편집기, 에러 등)은 **무슨 화면인지 + 어떻게 빠져나오는지** 설명.
> - **왜 하는지 원리**를 한두 줄로 쉽게 곁들인다(비유 환영).
> - 막히면 "그 화면을 캡처해서 보내달라"고 안내하고, 추측 대신 확인 후 진행.

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

## Night Hunter Development

Night Hunter는 `night-hunter/` 디렉토리에서 개발 중인 3D 웹 게임 (Three.js).

### 개발 규칙

- **매 단계 완료 후 반드시 테스트**: 코딩 완료 → 로컬 서버 기동 → 브라우저에서 게임 정상 작동 검증 → 문제 발견 시 즉시 수정 → 검증 통과 후 커밋/배포
- **파일 구조**: `index.html`, `style.css`, `js/` 하위 모듈별 분리 (world.js, main.js, daynight.js 등)

## 자동 배포 규칙 (기본 동작)

**코드 수정 작업이 완료되면 항상 자동으로 다음을 수행한다 (사용자가 명시적으로 막지 않는 한):**

1. 작업 브랜치(예: `claude/*`)에 커밋 후 push
2. `main` 브랜치로 checkout → 최신 pull
3. 작업 브랜치를 `main`에 `--no-ff` 머지
4. `main` push → GitHub Pages 자동 배포 트리거
5. 사용자에게 다음을 보고:
   - 머지된 커밋 목록
   - 배포 URL: `https://jtaechul.github.io/Product/night-hunter/` (Night Hunter 기준)
   - 브라우저 캐시 강력 새로고침 안내 (Ctrl/Cmd+Shift+R)
6. 작업 브랜치로 다시 checkout (다음 작업 준비)

**예외:**
- 사용자가 "머지 금지", "PR만 생성해", "main 푸시 금지" 등을 명시한 경우
- 머지 충돌 발생 시: 자동 해결 시도 후 실패하면 사용자에게 보고
- 작업이 중단됐거나 QA 미완료 상태인 경우
