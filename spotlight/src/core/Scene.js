import { Container } from "pixi.js";

// 모든 화면(타이틀·메인스케줄·평가·엔딩)의 베이스.
export class Scene extends Container {
  /** @param {import('./SceneManager.js').SceneManager} manager */
  bind(manager) {
    this.manager = manager;
  }

  // 씬 진입 시 1회 호출 — UI 구성 (async 가능)
  async onEnter() {}

  // 화면 크기 변경 시 호출
  resize(_width, _height) {}

  // 매 프레임 호출
  update(_delta) {}

  // 씬 종료 시 정리
  onExit() {
    this.destroy({ children: true });
  }
}
