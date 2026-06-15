import { Assets, Sprite, Graphics } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { COLORS, DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";

// 메인 스케줄 화면 (기획서 16번).
// 현재 단계: 고퀄 목업 아트(래스터 PNG)를 PixiJS로 렌더링 — "이 퀄리티가 목표"를 화면으로 확정.
// 다음 단계: 캐릭터/패널/활동 아이콘을 개별 아트로 분리해 상호작용 UI로 조립.
export class MainScene extends Scene {
  async onEnter() {
    // 배경
    const bg = new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill(COLORS.navy);
    this.addChild(bg);

    // 목표 아트 로드 (래스터 일러스트)
    const tex = await Assets.load("./assets/mockups/main_screen_target.png");
    const art = new Sprite(tex);
    art.anchor.set(0.5);

    // 9:16 스테이지에 비율 유지로 꽉 차게(contain)
    const scale = Math.min(DESIGN_WIDTH / art.texture.width, DESIGN_HEIGHT / art.texture.height);
    art.scale.set(scale);
    art.position.set(DESIGN_WIDTH / 2, DESIGN_HEIGHT / 2);
    this.addChild(art);

    document.getElementById("loading")?.remove();
  }
}
