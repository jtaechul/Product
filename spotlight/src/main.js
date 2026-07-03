import { Application } from "pixi.js";
import { COLORS } from "./config.js";
import { SceneManager } from "./core/SceneManager.js";
import { TitleScene } from "./scenes/TitleScene.js";
import { initPlatform, logScreen } from "./systems/platform.js";

// PixiJS 부트스트랩 (기획서 4번: GPU 렌더링, 빌드 없이 동작).
async function boot() {
  // 플랫폼(토스 앱인토스/웹) 준비: 저장소 hydrate + 안전영역. 세이브 여부 판단 전에 끝나야 한다.
  await initPlatform();

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
  logScreen("title");
  await manager.change(new TitleScene());
  // 타이틀 준비 완료 → 회사 로고 스플래시를 걷어내고 바로 초기화면 노출
  try { window.__hideSplash && window.__hideSplash(); } catch (e) {}
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
  try { window.__hideSplash && window.__hideSplash(); } catch (e) {} // 스플래시를 걷어 에러 메시지가 보이도록
  const el = document.getElementById("loading");
  if (el) el.textContent = "로드 실패: " + err.message;
});
