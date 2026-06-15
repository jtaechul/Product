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

  // 설계 해상도를 화면에 비율 유지로 맞춘다(letterbox).
  resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    const scale = Math.min(w / DESIGN_WIDTH, h / DESIGN_HEIGHT);
    const stage = this.app.stage;
    stage.scale.set(scale);
    stage.position.set(
      (w - DESIGN_WIDTH * scale) / 2,
      (h - DESIGN_HEIGHT * scale) / 2,
    );
    this.current?.resize(DESIGN_WIDTH, DESIGN_HEIGHT);
  }
}
