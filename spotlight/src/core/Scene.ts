import { Container } from "pixi.js";
import type { SceneManager } from "./SceneManager";

// 모든 화면(타이틀·캐릭터생성·메인스케줄·평가·엔딩)의 베이스.
// Pixi Container를 상속해 그대로 스테이지에 붙일 수 있다.
export abstract class Scene extends Container {
  protected manager!: SceneManager;

  bind(manager: SceneManager): void {
    this.manager = manager;
  }

  // 씬 진입 시 1회 호출 — UI 구성
  abstract onEnter(): void;

  // 화면 크기 변경 시 호출 — 레이아웃 재배치
  resize(_width: number, _height: number): void {}

  // 매 프레임 호출 — 애니메이션 업데이트 (delta: 프레임 보정값)
  update(_delta: number): void {}

  // 씬 종료 시 정리
  onExit(): void {
    this.destroy({ children: true });
  }
}
