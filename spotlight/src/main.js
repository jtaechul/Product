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

  // 폰트가 준비된 뒤 텍스트를 그려야 PixiJS가 올바른 글꼴로 렌더한다.
  await loadFonts();

  const manager = new SceneManager(app);
  await manager.change(new MainScene());
}

// @font-face 폰트를 실제 로드(브라우저가 글리프를 갖추도록).
async function loadFonts() {
  const fams = ["GmarketSansBold", "GmarketSansMedium", "BMDOHYEON", "BMJUA", "KoPubWorldDotumMedium", "KoPubWorldDotumBold"];
  try {
    await Promise.all(fams.map((f) => document.fonts.load(`24px "${f}"`)));
    await document.fonts.ready;
  } catch (e) {
    console.warn("[SPOTLIGHT] font load issue:", e);
  }
}

boot().catch((err) => {
  console.error("[SPOTLIGHT] boot failed:", err);
  const el = document.getElementById("loading");
  if (el) el.textContent = "로드 실패: " + err.message;
});
