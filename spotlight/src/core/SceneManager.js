import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";

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

  // 설계 해상도를 화면에 맞춘다. 세로폰=폭채움, 태블릿(짧고 넓음)=전체 보이게 높이맞춤(가운데),
  // 가로=90° 회전 후 전체 보이게(contain). 어느 기기에서도 하단 메뉴가 잘리지 않게 한다.
  resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const ins = this._safeInsets();
    const stage = this.app.stage;
    if (h >= w) {
      // 세로
      const availH = Math.max(1, h - ins.top - ins.bottom);
      const scaleW = w / DESIGN_WIDTH;
      let scale, ox, designH;
      if (availH / scaleW >= DESIGN_HEIGHT) {
        // 충분히 긴 화면(폰): 폭을 꽉 채우고 남는 세로 공간 활용
        scale = scaleW; ox = 0; designH = Math.round(availH / scale);
      } else {
        // 짧고 넓은 화면(태블릿): 전체가 보이도록 높이에 맞추고 가로 가운데 정렬
        scale = availH / DESIGN_HEIGHT; designH = DESIGN_HEIGHT; ox = (w - DESIGN_WIDTH * scale) / 2;
      }
      stage.rotation = 0; stage.scale.set(scale); stage.position.set(ox, ins.top);
      this.current?.resize(DESIGN_WIDTH, designH);
    } else {
      // 가로: 90° 회전 + 전체 보이게(contain), 가운데 정렬
      const scale = Math.min(h / DESIGN_WIDTH, w / DESIGN_HEIGHT);
      const cw = DESIGN_WIDTH * scale, chh = DESIGN_HEIGHT * scale;
      stage.scale.set(scale);
      if (this._angle() === 90) { stage.rotation = -Math.PI / 2; stage.position.set((w - chh) / 2, (h + cw) / 2); }
      else { stage.rotation = Math.PI / 2; stage.position.set((w + chh) / 2, (h - cw) / 2); }
      this.current?.resize(DESIGN_WIDTH, DESIGN_HEIGHT);
    }
  }

  _angle() {
    try { return (window.screen && window.screen.orientation && window.screen.orientation.angle) || 0; } catch (e) { return 0; }
  }

  // iOS 안전영역(노치/홈바) 크기 측정
  _safeInsets() {
    const p = document.createElement("div");
    p.style.cssText = "position:fixed;top:0;left:0;width:0;height:0;visibility:hidden;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom);";
    document.body.appendChild(p);
    const cs = getComputedStyle(p);
    const top = parseFloat(cs.paddingTop) || 0;
    const bottom = parseFloat(cs.paddingBottom) || 0;
    p.remove();
    return { top, bottom };
  }
}
