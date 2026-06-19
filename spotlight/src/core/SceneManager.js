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
    if (this.current) {
      this.app.stage.removeChild(this.current);
      this.current.onExit();
    }
    this.current = scene;
    scene.bind(this);
    this.app.stage.addChild(scene);
    await scene.onEnter();
    this.resize();
  }

  // 설계 해상도를 화면에 맞춘다. 가로로 들어도 스테이지를 90° 회전해 '세로 화면'을 유지한다.
  resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const ins = this._safeInsets();
    const stage = this.app.stage;
    if (h >= w) {
      // 세로 모드
      const availH = Math.max(1, h - ins.top - ins.bottom);
      const scale = w / DESIGN_WIDTH;             // 가로를 화면 폭에 정확히 맞춤(가로 빈공간 0)
      stage.rotation = 0;
      stage.scale.set(scale);
      stage.position.set(0, ins.top);             // 노치(안전영역) 아래에서 시작
      const designH = Math.max(DESIGN_HEIGHT, Math.round(availH / scale));
      this.current?.resize(DESIGN_WIDTH, designH);
    } else {
      // 가로 모드: 세로 디자인을 90° 회전해 화면을 꽉 채워 세로 유지 (가로 안내문 없음)
      const scale = h / DESIGN_WIDTH;             // 세로 폭(720)을 화면 높이에 맞춤
      if (this._angle() === 90) { stage.rotation = -Math.PI / 2; stage.position.set(0, h); }
      else { stage.rotation = Math.PI / 2; stage.position.set(w, 0); }
      stage.scale.set(scale);
      const designH = Math.max(DESIGN_HEIGHT, Math.round(w / scale));
      this.current?.resize(DESIGN_WIDTH, designH);
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
