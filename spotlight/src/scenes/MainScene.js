import { Assets, Sprite, Graphics, Container, Text, TextStyle } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { COLORS, DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { GameState } from "../systems/game.js";
import { ACTIVITIES } from "../data/activities.js";

const IDLE_SPRITE = "./assets/portraits/heroine_brown_idle.png";
const POSE_PATH = (key) => `./assets/portraits/poses/soyoon_${key}.png`;
const BG_SCHOOL = "./assets/bg/school.png";

const CHAR_TARGET_H = 560;
const GROUND_Y = 700;
const KFONT = "system-ui, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif";

const MANAGER_LINES = [
  "이번 달도 알차게 써보자!",
  "무리하지 말고, 컨디션도 챙겨야 해.",
  "조금씩 쌓이는 게 결국 큰 차이를 만들어.",
  "어떤 배우가 되고 싶은지, 그 길로 가는 거야.",
  "좋아, 네 선택을 믿어볼게.",
];

// 메인 스케줄 화면 (기획서 5·16번): 월별 활동 2슬롯 선택 → 정산 → 다음 달.
export class MainScene extends Scene {
  constructor() {
    super();
    this.game = new GameState();
    this.selected = [];      // 선택한 활동 id (최대 2)
    this.cards = new Map();   // id → 카드 컨테이너(하이라이트용)
    this.t = 0;
  }

  async onEnter() {
    // 배경
    const bgTex = await Assets.load(BG_SCHOOL);
    const bg = new Sprite(bgTex);
    const bs = Math.max(DESIGN_WIDTH / bg.texture.width, DESIGN_HEIGHT / bg.texture.height);
    bg.scale.set(bs);
    bg.anchor.set(0.5, 0);
    bg.position.set(DESIGN_WIDTH / 2, 0);
    this.addChild(bg);
    // 가독성용 밝은 베일
    this.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill({ color: 0xffffff, alpha: 0.12 }));

    // 바닥 그림자 + 캐릭터
    this.shadow = new Graphics().ellipse(DESIGN_WIDTH / 2, GROUND_Y + 6, 150, 28).fill({ color: 0x2a2a33, alpha: 0.18 });
    this.addChild(this.shadow);
    const idleTex = await Assets.load(IDLE_SPRITE);
    this.hero = new Sprite(idleTex);
    this.hero.anchor.set(0.5, 1.0);
    this.hero.position.set(DESIGN_WIDTH / 2, GROUND_Y);
    this._fitHero();
    this.addChild(this.hero);

    await this.buildHUD();
    this.buildManagerBubble();
    this.buildActivityGrid();
    this.buildNextButton();
    this.refreshHUD();

    document.getElementById("loading")?.remove();
  }

  _fitHero() {
    this.baseScale = CHAR_TARGET_H / this.hero.texture.height;
    this.hero.scale.set(this.baseScale);
  }

  async setPose(poseKey) {
    const path = poseKey ? POSE_PATH(poseKey) : IDLE_SPRITE;
    try {
      const tex = await Assets.load(path);
      this.hero.texture = tex;
      this._fitHero();
    } catch (e) {
      console.warn("pose load failed", path, e);
    }
  }

  // ───────────── 상단 상태바 ─────────────
  async buildHUD() {
    const bar = new Container();
    bar.addChild(new Graphics().roundRect(12, 12, DESIGN_WIDTH - 24, 92, 18).fill({ color: 0xffffff, alpha: 0.92 }));

    this.turnText = new Text({ text: "", style: new TextStyle({ fontFamily: KFONT, fontSize: 30, fontWeight: "800", fill: COLORS.ink }) });
    this.turnText.position.set(30, 26);
    bar.addChild(this.turnText);

    this.nameText = new Text({ text: "소윤", style: new TextStyle({ fontFamily: KFONT, fontSize: 20, fill: 0x8a7b72 }) });
    this.nameText.position.set(30, 64);
    bar.addChild(this.nameText);

    // 자원 칩 4종 (오른쪽)
    this.resText = {};
    const defs = [
      ["stamina", "체력", 0xff6b6b],
      ["mental", "멘탈", 0x5aa9e6],
      ["money", "돈", COLORS.gold],
      ["fans", "팬", 0xff8a7a],
    ];
    const cw = 118, startX = DESIGN_WIDTH - 24 - cw * 2 - 6, gx = 6, gy = 6;
    defs.forEach(([key, label, color], i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = startX + col * (cw + gx), y = 20 + row * (38 + gy);
      const chip = new Container();
      chip.addChild(new Graphics().roundRect(x, y, cw, 38, 10).fill({ color, alpha: 0.16 }));
      const lab = new Text({ text: label, style: new TextStyle({ fontFamily: KFONT, fontSize: 18, fontWeight: "700", fill: color }) });
      lab.position.set(x + 12, y + 8);
      const val = new Text({ text: "", style: new TextStyle({ fontFamily: KFONT, fontSize: 20, fontWeight: "800", fill: COLORS.ink }) });
      val.anchor.set(1, 0);
      val.position.set(x + cw - 12, y + 7);
      chip.addChild(lab, val);
      bar.addChild(chip);
      this.resText[key] = val;
    });

    this.addChild(bar);
  }

  refreshHUD() {
    this.turnText.text = this.game.label;
    this.resText.stamina.text = String(this.game.stamina);
    this.resText.mental.text = String(this.game.mental);
    this.resText.money.text = this.game.moneyShort();
    this.resText.fans.text = String(this.game.fans);
  }

  // ───────────── 매니저 말풍선 ─────────────
  buildManagerBubble() {
    const y = 716, h = 64;
    const c = new Container();
    c.addChild(new Graphics().roundRect(16, y, DESIGN_WIDTH - 32, h, 16).fill({ color: 0x2c3c63, alpha: 0.92 }));
    const who = new Text({ text: "한지원", style: new TextStyle({ fontFamily: KFONT, fontSize: 18, fontWeight: "800", fill: COLORS.mint }) });
    who.position.set(32, y + 10);
    this.mgrText = new Text({ text: MANAGER_LINES[0], style: new TextStyle({ fontFamily: KFONT, fontSize: 21, fill: 0xffffff, wordWrap: true, wordWrapWidth: DESIGN_WIDTH - 70 }) });
    this.mgrText.position.set(32, y + 32);
    c.addChild(who, this.mgrText);
    this.addChild(c);
  }

  // ───────────── 활동 카드 그리드 ─────────────
  buildActivityGrid() {
    const headerY = 794;
    const header = new Text({ text: "이번 달 활동 — 2개 선택", style: new TextStyle({ fontFamily: KFONT, fontSize: 22, fontWeight: "800", fill: COLORS.ink }) });
    header.position.set(20, headerY);
    this.addChild(header);

    this.slotText = new Text({ text: "선택: —", style: new TextStyle({ fontFamily: KFONT, fontSize: 18, fill: 0x3a3a44 }) });
    this.slotText.anchor.set(1, 0);
    this.slotText.position.set(DESIGN_WIDTH - 20, headerY + 4);
    this.addChild(this.slotText);

    const cols = 3, mx = 18, gap = 12, top = 832;
    const cardW = (DESIGN_WIDTH - mx * 2 - gap * (cols - 1)) / cols;
    const cardH = 80;
    ACTIVITIES.forEach((act, i) => {
      const col = i % cols, row = Math.floor(i / cols);
      const x = mx + col * (cardW + gap), y = top + row * (cardH + gap);
      const card = this._makeCard(act, x, y, cardW, cardH);
      this.addChild(card);
      this.cards.set(act.id, card);
    });
  }

  _makeCard(act, x, y, w, h) {
    const card = new Container();
    card.position.set(x, y);
    const bg = new Graphics().roundRect(0, 0, w, h, 12).fill({ color: 0xffffff, alpha: 0.95 });
    const border = new Graphics();
    const emoji = new Text({ text: act.emoji, style: new TextStyle({ fontFamily: KFONT, fontSize: 28 }) });
    emoji.position.set(10, 8);
    const name = new Text({ text: act.name, style: new TextStyle({ fontFamily: KFONT, fontSize: 19, fontWeight: "800", fill: COLORS.ink }) });
    name.position.set(48, 10);
    const desc = new Text({ text: act.desc, style: new TextStyle({ fontFamily: KFONT, fontSize: 14, fill: 0x8a7b72 }) });
    desc.position.set(10, 50);
    card.addChild(bg, border, emoji, name, desc);
    card._border = border;
    card._w = w; card._h = h;

    card.eventMode = "static";
    card.cursor = "pointer";
    card.on("pointertap", () => this.toggleSelect(act.id));
    return card;
  }

  toggleSelect(id) {
    const idx = this.selected.indexOf(id);
    if (idx >= 0) {
      this.selected.splice(idx, 1);
    } else {
      if (this.selected.length >= 2) this.selected.shift(); // 가장 오래된 것 교체
      this.selected.push(id);
    }
    this._refreshSelection();
    // 마지막 선택 활동 포즈 미리보기 (없으면 idle)
    const last = this.selected[this.selected.length - 1];
    const act = ACTIVITIES.find((a) => a.id === last);
    this.setPose(act ? act.pose : null);
  }

  _refreshSelection() {
    for (const [id, card] of this.cards) {
      const on = this.selected.includes(id);
      card._border.clear();
      if (on) card._border.roundRect(0, 0, card._w, card._h, 12).stroke({ width: 4, color: COLORS.coral });
    }
    const names = this.selected.map((id) => ACTIVITIES.find((a) => a.id === id)?.name).filter(Boolean);
    this.slotText.text = names.length ? `선택: ${names.join(" · ")}` : "선택: —";
  }

  // ───────────── 다음 달 버튼 ─────────────
  buildNextButton() {
    const y = 1196, h = 66;
    this.nextBtn = new Container();
    this.nextBtn.position.set(0, 0);
    this.nextBtnBg = new Graphics().roundRect(20, y, DESIGN_WIDTH - 40, h, 20).fill(COLORS.coral);
    const label = new Text({ text: "▶  다음 달", style: new TextStyle({ fontFamily: KFONT, fontSize: 28, fontWeight: "800", fill: 0xffffff }) });
    label.anchor.set(0.5);
    label.position.set(DESIGN_WIDTH / 2, y + h / 2);
    this.nextBtn.addChild(this.nextBtnBg, label);
    this.nextBtnLabel = label;
    this.nextBtn.eventMode = "static";
    this.nextBtn.cursor = "pointer";
    this.nextBtn.on("pointertap", () => this.onNextMonth());
    this.addChild(this.nextBtn);
  }

  onNextMonth() {
    if (this.game.isLastTurn) {
      this.mgrText.text = "3년의 시간이 끝났어. 정말 수고했어!";
      this.nextBtnLabel.text = "졸업 🎓";
      return;
    }
    this.game.advance([...this.selected]);
    this.selected = [];
    this._refreshSelection();
    this.setPose(null); // idle 복귀
    this.refreshHUD();
    this.mgrText.text = MANAGER_LINES[(this.game.turn - 1) % MANAGER_LINES.length];
    if (this.game.isLastTurn) this.nextBtnLabel.text = "▶  마지막 달";
  }

  update(delta) {
    if (!this.hero) return;
    this.t += delta;
    const breathe = Math.sin(this.t * 0.045);
    this.hero.position.y = GROUND_Y + breathe * 3;
    this.hero.scale.y = this.baseScale * (1 + breathe * 0.012);
    this.shadow.scale.set(1 - breathe * 0.04, 1);
  }
}
