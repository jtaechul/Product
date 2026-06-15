import { Assets, Sprite, Graphics, Container, Text, TextStyle } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { COLORS, DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";

// 주인공 머리색 변형 (기획서 17번): A=브라운(기본), B=레드.
const HEROINE_SPRITES = {
  brown: "./assets/portraits/heroine_brown_idle.png",
  red: "./assets/portraits/heroine_red_idle.png",
};
// 스프라이트 시트에서 추출한 얼굴 포트레이트(대화·프로필용).
const HEROINE_FACES = {
  brown: "./assets/portraits/faces/heroine_brown_face.png",
  red: "./assets/portraits/faces/heroine_red_face.png",
};

// 두 색을 t(0~1)로 선형 보간 → 배경 그라데이션용.
function lerpColor(a, b, t) {
  const ar = (a >> 16) & 255, ag = (a >> 8) & 255, ab = a & 255;
  const br = (b >> 16) & 255, bg = (b >> 8) & 255, bb = b & 255;
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const c = Math.round(ab + (bb - ab) * t);
  return (r << 16) | (g << 8) | c;
}

// 메인 스케줄 화면 (기획서 16번).
// 현재 단계: 디자인 시트에서 추출한 주인공 일러스트를 GPU 스프라이트로 띄우고
// 상시 idle(숨쉬기·미세 흔들림) 모션을 준다 — "늘 살아 움직이는 캐릭터"(기획서 3·14번).
export class MainScene extends Scene {
  /** @param {{variant?: "brown"|"red"}} [opts] */
  constructor(opts = {}) {
    super();
    this.variant = opts.variant === "red" ? "red" : "brown";
    this.t = 0; // 애니메이션 시간 누적
  }

  async onEnter() {
    // ── 1) 파스텔 그라데이션 배경 (밴드 방식 — 어떤 Pixi 빌드에서도 안전)
    const bg = new Graphics();
    const top = 0xfff1e8;    // 크림 피치
    const bottom = 0xbfe6df; // 소프트 민트
    const bands = 32;
    for (let i = 0; i < bands; i++) {
      const tt = i / (bands - 1);
      bg.rect(0, Math.floor((DESIGN_HEIGHT * i) / bands), DESIGN_WIDTH, Math.ceil(DESIGN_HEIGHT / bands) + 1)
        .fill(lerpColor(top, bottom, tt));
    }
    this.addChild(bg);

    const groundY = 905;

    // ── 2) 무대 스포트라이트(캐릭터 뒤 부드러운 빛 원)
    const glow = new Graphics();
    glow.circle(DESIGN_WIDTH / 2, groundY - 300, 330).fill({ color: 0xffffff, alpha: 0.35 });
    glow.circle(DESIGN_WIDTH / 2, groundY - 300, 230).fill({ color: 0xfff6cf, alpha: 0.35 });
    this.addChild(glow);

    // ── 3) 바닥 그림자(접지감)
    const shadow = new Graphics();
    shadow.ellipse(DESIGN_WIDTH / 2, groundY + 6, 175, 34).fill({ color: 0x2a2a33, alpha: 0.18 });
    this.addChild(shadow);
    this.shadow = shadow;

    // ── 3.5) 프로필 아바타 칩 (스프라이트 시트에서 추출한 포트레이트 사용)
    await this.buildAvatarChip();

    // ── 4) 주인공 스프라이트 (디자인 시트 추출 일러스트)
    const tex = await Assets.load(HEROINE_SPRITES[this.variant]);
    const hero = new Sprite(tex);
    hero.anchor.set(0.5, 1.0); // 발끝 기준 → 바닥에 세움
    this.baseScale = 690 / hero.texture.height;
    hero.scale.set(this.baseScale);
    hero.position.set(DESIGN_WIDTH / 2, groundY);
    this.addChild(hero);
    this.hero = hero;
    this.groundY = groundY;

    // ── 5) 타이틀 + 한 줄 카피
    const title = new Text({
      text: "SPOTLIGHT",
      style: new TextStyle({
        fontFamily: "Georgia, 'Times New Roman', serif",
        fontSize: 64,
        fontWeight: "700",
        letterSpacing: 6,
        fill: COLORS.ink,
      }),
    });
    title.anchor.set(0.5);
    title.position.set(DESIGN_WIDTH / 2, 120);
    this.addChild(title);

    const sub = new Text({
      text: "어떤 배우가 되어 있을까?",
      style: new TextStyle({
        fontFamily: "system-ui, 'Apple SD Gothic Neo', sans-serif",
        fontSize: 28,
        fill: 0x6b5b53,
      }),
    });
    sub.anchor.set(0.5);
    sub.position.set(DESIGN_WIDTH / 2, 175);
    this.addChild(sub);

    document.getElementById("loading")?.remove();
  }

  // 좌상단 프로필 아바타 칩: 둥근 카드 + 원형 마스크 포트레이트 + 이름표.
  async buildAvatarChip() {
    const chip = new Container();
    const cardW = 250, cardH = 96, pad = 13, r = 18;

    // 카드 배경(흰색, 살짝 그림자)
    const shadow = new Graphics().roundRect(3, 5, cardW, cardH, r).fill({ color: 0x2a2a33, alpha: 0.12 });
    const card = new Graphics().roundRect(0, 0, cardW, cardH, r).fill(0xffffff);
    chip.addChild(shadow, card);

    // 원형 포트레이트
    const faceTex = await Assets.load(HEROINE_FACES[this.variant]);
    const face = new Sprite(faceTex);
    const d = cardH - pad * 2;             // 원 지름
    const fs = (d / Math.min(face.texture.width, face.texture.height)) * 1.15; // 얼굴이 원을 채우게
    face.scale.set(fs);
    face.anchor.set(0.5, 0.42);            // 얼굴 위주로 맞춤
    face.position.set(pad + d / 2, pad + d / 2);
    const mask = new Graphics().circle(pad + d / 2, pad + d / 2, d / 2).fill(0xffffff);
    face.mask = mask;
    const ring = new Graphics().circle(pad + d / 2, pad + d / 2, d / 2).stroke({ width: 3, color: COLORS.coral });
    chip.addChild(face, mask, ring);

    // 이름 + 학년
    const name = new Text({
      text: "주인공",
      style: new TextStyle({ fontFamily: "system-ui, 'Apple SD Gothic Neo', sans-serif", fontSize: 26, fontWeight: "700", fill: COLORS.ink }),
    });
    name.position.set(pad + d + 14, 24);
    const grade = new Text({
      text: "고1 · 배우 지망생",
      style: new TextStyle({ fontFamily: "system-ui, 'Apple SD Gothic Neo', sans-serif", fontSize: 18, fill: 0x8a7b72 }),
    });
    grade.position.set(pad + d + 14, 56);
    chip.addChild(name, grade);

    chip.position.set(24, 24);
    this.addChild(chip);
  }

  update(delta) {
    if (!this.hero) return;
    // delta는 약 1(60fps 기준). 시간 누적해 사인 모션.
    this.t += delta;
    const breathe = Math.sin(this.t * 0.045); // 숨쉬기(상하)
    const sway = Math.sin(this.t * 0.03);      // 좌우 미세 흔들림

    this.hero.position.y = this.groundY + breathe * 3;        // 살짝 떠오름
    this.hero.scale.y = this.baseScale * (1 + breathe * 0.012); // 숨쉬기 스케일
    this.hero.rotation = sway * 0.006;                          // 아주 약한 기울임

    this.shadow.scale.set(1 - breathe * 0.04, 1); // 뜨면 그림자 살짝 축소
  }
}
