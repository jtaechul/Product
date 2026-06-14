import { Application } from "pixi.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config";
import type { Scene } from "./Scene";

// 씬 전환 + 세로 비율 유지 스케일링을 담당.
export class SceneManager {
  readonly app: Application;
  private current?: Scene;

  constructor(app: Application) {
    this.app = app;
    app.ticker.add((ticker) => this.current?.update(ticker.deltaTime));
    window.addEventListener("resize", () => this.resize());
  }

  change(scene: Scene): void {
    if (this.current) {
      this.app.stage.removeChild(this.current);
      this.current.onExit();
    }
    this.current = scene;
    scene.bind(this);
    this.app.stage.addChild(scene);
    scene.onEnter();
    this.resize();
  }

  // 9:16 설계 해상도를 화면에 꽉 차되 비율 유지(letterbox)로 맞춘다.
  private resize(): void {
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
