import { Graphics, Text } from "pixi.js";
import { Scene } from "../core/Scene";
import { COLORS, DESIGN_WIDTH, DESIGN_HEIGHT, TOUCH_MIN } from "../config";

// 시작 화면 (기획서 16번 화면 목록의 '시작').
// 아직 게임 로직 전 단계 — 룩 확인용 placeholder.
export class TitleScene extends Scene {
  onEnter(): void {
    // 배경
    const bg = new Graphics()
      .rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT)
      .fill(COLORS.paper);
    this.addChild(bg);

    // 로고
    const logo = new Text({
      text: "🌟 SPOTLIGHT",
      style: { fill: COLORS.navy, fontSize: 72, fontWeight: "700" },
    });
    logo.anchor.set(0.5);
    logo.position.set(DESIGN_WIDTH / 2, DESIGN_HEIGHT * 0.32);
    this.addChild(logo);

    // 태그라인
    const tagline = new Text({
      text: "연기만 잘한다고 국민배우가 되는 건 아니다.",
      style: { fill: COLORS.navy2, fontSize: 28 },
    });
    tagline.anchor.set(0.5);
    tagline.position.set(DESIGN_WIDTH / 2, DESIGN_HEIGHT * 0.32 + 70);
    this.addChild(tagline);

    // 시작 버튼 (하단 엄지존, 터치 48px↑)
    const btnW = 360;
    const btnH = Math.max(96, TOUCH_MIN);
    const btn = new Graphics()
      .roundRect(-btnW / 2, -btnH / 2, btnW, btnH, 20)
      .fill(COLORS.coral);
    btn.position.set(DESIGN_WIDTH / 2, DESIGN_HEIGHT * 0.7);
    btn.eventMode = "static";
    btn.cursor = "pointer";
    btn.on("pointertap", () => this.onStart());

    const btnLabel = new Text({
      text: "시작하기",
      style: { fill: 0xffffff, fontSize: 34, fontWeight: "700" },
    });
    btnLabel.anchor.set(0.5);
    btn.addChild(btnLabel);
    this.addChild(btn);
  }

  private onStart(): void {
    // TODO: CreateScene(캐릭터 생성)으로 전환
    console.log("[SPOTLIGHT] start pressed — 캐릭터 생성 화면 예정");
  }
}
