import { Application } from "pixi.js";
import { COLORS } from "./config";
import { SceneManager } from "./core/SceneManager";
import { TitleScene } from "./scenes/TitleScene";

// PixiJS 애플리케이션 부트스트랩 (기획서 4번: GPU 렌더링).
async function boot(): Promise<void> {
  const app = new Application();
  await app.init({
    resizeTo: window,
    background: COLORS.navy,
    antialias: true,
    autoDensity: true,
    resolution: window.devicePixelRatio || 1,
  });

  const mount = document.getElementById("game");
  mount?.appendChild(app.canvas);

  const manager = new SceneManager(app);
  manager.change(new TitleScene());
}

boot();
