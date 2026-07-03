import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { getNativeInsets } from "../systems/platform.js";

// 씬 전환 + 세로(9:16) 비율 유지 스케일링.
export class SceneManager {
  /** @param {import('pixi.js').Application} app */
  constructor(app) {
    this.app = app;
    this.current = undefined;
    app.ticker.add((ticker) => this.current?.update(ticker.deltaTime));
    window.addEventListener("resize", () => this.resize());
  }

  /** @param {import('./Scene.js').Scene} scene */
  async change(scene) {
    try { window.__setLoading && window.__setLoading(true); } catch (e) {} // 전환 중 로딩 표시
    if (this.current) {
      this.app.stage.removeChild(this.current);
      this.current.onExit();
    }
    this.current = scene;
    scene.bind(this);
    this.app.stage.addChild(scene);
    try {
      await scene.onEnter();
    } finally {
      this.resize();
      try { window.__setLoading && window.__setLoading(false); } catch (e) {} // 준비 완료 → 숨김
    }
  }

  // 설계 해상도를 화면에 맞춘다. 세로폰=폭채움, 태블릿·데스크톱(짧고 넓음)=세로 중앙 배치(양옆 여백),
  // 터치 기기를 가로로 든 경우만 90° 회전해 세로 유지. 어느 기기에서도 하단 메뉴가 잘리지 않게 한다.
  resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const ins = this._safeInsets();
    const stage = this.app.stage;
    // 데스크톱 브라우저(마우스)는 창이 가로여도 회전하지 않는다 — 세로 게임을 중앙에 필러박스로.
    // 회전은 '폰·태블릿을 실제로 눕혔을 때'(터치 기기 가로)만.
    if (h >= w || !this._isTouch()) {
      // 세로 렌더
      const availH = Math.max(1, h - ins.top - ins.bottom);
      const scaleW = w / DESIGN_WIDTH;
      let scale, ox, designH;
      if (availH / scaleW >= DESIGN_HEIGHT) {
        // 충분히 긴 화면(폰): 폭을 꽉 채우고 남는 세로 공간 활용
        scale = scaleW; ox = 0; designH = Math.round(availH / scale);
      } else {
        // 짧고 넓은 화면(태블릿·데스크톱 창): 전체가 보이도록 높이에 맞추고 가로 가운데 정렬
        scale = availH / DESIGN_HEIGHT; designH = DESIGN_HEIGHT; ox = (w - DESIGN_WIDTH * scale) / 2;
      }
      stage.rotation = 0; stage.scale.set(scale); stage.position.set(ox, ins.top);
      this.current?.resize(DESIGN_WIDTH, designH);
    } else {
      // 터치 기기를 가로로 든 경우: 90° 회전 + 전체 보이게(contain), 가운데 정렬
      const scale = Math.min(h / DESIGN_WIDTH, w / DESIGN_HEIGHT);
      const cw = DESIGN_WIDTH * scale, chh = DESIGN_HEIGHT * scale;
      stage.scale.set(scale);
      if (this._angle() === 90) { stage.rotation = -Math.PI / 2; stage.position.set((w - chh) / 2, (h + cw) / 2); }
      else { stage.rotation = Math.PI / 2; stage.position.set((w + chh) / 2, (h - cw) / 2); }
      this.current?.resize(DESIGN_WIDTH, DESIGN_HEIGHT);
    }
  }

  // 터치(모바일·태블릿) 기기인지 — 데스크톱 마우스 환경과 구분해 가로 회전을 결정.
  _isTouch() {
    try {
      if (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) return true;
      return (navigator.maxTouchPoints || 0) > 0 || "ontouchstart" in window;
    } catch (e) { return false; }
  }

  _angle() {
    try { return (window.screen && window.screen.orientation && window.screen.orientation.angle) || 0; } catch (e) { return 0; }
  }

  // 안전영역(노치/다이나믹 아일랜드/홈바) 크기 측정.
  // env(safe-area-inset)와 토스 SDK(getSafeAreaInsets) 값 중 큰 쪽을 쓴다 —
  // 토스 WebView에서는 env()가 0으로 나올 수 있어 SDK 값이 필요하다(풀스크린 심사 필수 항목).
  _safeInsets() {
    const p = document.createElement("div");
    p.style.cssText = "position:fixed;top:0;left:0;width:0;height:0;visibility:hidden;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom);";
    document.body.appendChild(p);
    const cs = getComputedStyle(p);
    const top = parseFloat(cs.paddingTop) || 0;
    const bottom = parseFloat(cs.paddingBottom) || 0;
    p.remove();
    const nat = getNativeInsets();
    return { top: Math.max(top, nat.top), bottom: Math.max(bottom, nat.bottom) };
  }
}
