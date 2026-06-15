import { Application } from "pixi.js";
import { COLORS } from "./config.js";
import { SceneManager } from "./core/SceneManager.js";
import { MainScene } from "./scenes/MainScene.js";

// PixiJS 부트스트랩 (기획서 4번: GPU 렌더링, 빌드 없이 동작).
async function boot() {
  const app = new Application();
  await app.init({
    resizeTo: window,
    background: COLORS.navy,
    antialias: true,
    autoDensity: true,
    resolution: window.devicePixelRatio || 1,
  });

  document.getElementById("game")?.appendChild(app.canvas);

  const manager = new SceneManager(app);
  await manager.change(new MainScene());
}

boot().catch((err) => {
  console.error("[SPOTLIGHT] boot failed:", err);
  const el = document.getElementById("loading");
  if (el) el.textContent = "로드 실패: " + err.message;
});
