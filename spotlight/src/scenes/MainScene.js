import { Assets, Sprite, Graphics, Container, Text, TextStyle } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { COLORS, DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { GameState } from "../systems/game.js";
import { ACTIVITIES, CATEGORIES } from "../data/activities.js";

const IDLE_SPRITE = "./assets/portraits/heroine_brown_idle.png";
const POSE_PATH = (key) => `./assets/portraits/poses/soyoon_${key}.png`;
const BG_SCHOOL = "./assets/bg/school.png";

// 캐릭터: 상반신 중심으로 크게. 발은 패널 뒤(화면 밖 아래)로.
const CHAR_TARGET_H = 1000;
const GROUND_Y = 1090;
const PANEL_TOP = 812;     // 하단 명령 패널 상단 (다리를 가림)
const KFONT = "system-ui, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif";

const MANAGER_LINES = [
  "이번 달은 뭘 해볼까?",
  "무리하지 말고 컨디션도 챙기자.",
  "조금씩 쌓이면 큰 차이가 돼.",
  "좋아, 네 선택을 믿어볼게.",
];

// 메인 스케줄 화면 — 우마무스메식 2단 메뉴(카테고리→세부활동) (기획서 5·16번).
export class MainScene extends Scene {
  constructor() {
    super();
    this.game = new GameState();
    this.selected = [];          // 활동 id (최대 2)
    this.menuMode = "category";   // 'category' | 'sub'
    this.activeCat = null;
    this.t = 0;
  }

  async onEnter() {
    // 배경
    const bgTex = await Assets.load(BG_SCHOOL);
    const bg = new Sprite(bgTex);
    bg.anchor.set(0.5, 0);
    bg.scale.set(Math.max(DESIGN_WIDTH / bg.texture.width, DESIGN_HEIGHT / bg.texture.height));
    bg.position.set(DESIGN_WIDTH / 2, 0);
    this.addChild(bg);

    // 캐릭터 (배경 위, 패널 아래)
    this.shadow = new Graphics().ellipse(DESIGN_WIDTH / 2, GROUND_Y + 6, 170, 26).fill({ color: 0x2a2a33, alpha: 0.15 });
    this.addChild(this.shadow);
    const idleTex = await Assets.load(IDLE_SPRITE);
    this.hero = new Sprite(idleTex);
    this.hero.anchor.set(0.5, 1.0);
    this.hero.position.set(DESIGN_WIDTH / 2, GROUND_Y);
    this._fitHero();
    this.addChild(this.hero);

    await this.buildHUD();
    this.buildManagerBubble();
    this.buildPanel();      // 하단 명령 패널 + 메뉴 레이어
    this.buildNextButton();
    this.refreshHUD();
    this.renderMenu();

    document.getElementById("loading")?.remove();
  }

  _fitHero() {
    this.baseScale = CHAR_TARGET_H / this.hero.texture.height;
    this.hero.scale.set(this.baseScale);
  }

  async setPose(poseKey) {
    try {
      this.hero.texture = await Assets.load(poseKey ? POSE_PATH(poseKey) : IDLE_SPRITE);
      this._fitHero();
    } catch (e) { console.warn("pose load failed", poseKey, e); }
  }

  // ───────── 상단 상태바 ─────────
  async buildHUD() {
    const bar = new Container();
    bar.addChild(new Graphics().roundRect(12, 12, DESIGN_WIDTH - 24, 92, 18).fill({ color: 0xffffff, alpha: 0.92 }));
    this.turnText = new Text({ text: "", style: new TextStyle({ fontFamily: KFONT, fontSize: 30, fontWeight: "800", fill: COLORS.ink }) });
    this.turnText.position.set(30, 26);
    this.nameText = new Text({ text: "소윤", style: new TextStyle({ fontFamily: KFONT, fontSize: 20, fill: 0x8a7b72 }) });
    this.nameText.position.set(30, 64);
    bar.addChild(this.turnText, this.nameText);

    this.resText = {};
    const defs = [["stamina", "체력", 0xff6b6b], ["mental", "멘탈", 0x5aa9e6], ["money", "돈", 0xcdaa28], ["fans", "팬", 0xff8a7a]];
    const cw = 118, startX = DESIGN_WIDTH - 24 - cw * 2 - 6;
    defs.forEach(([key, label, color], i) => {
      const x = startX + (i % 2) * (cw + 6), y = 20 + Math.floor(i / 2) * 44;
      bar.addChild(new Graphics().roundRect(x, y, cw, 38, 10).fill({ color, alpha: 0.16 }));
      const lab = new Text({ text: label, style: new TextStyle({ fontFamily: KFONT, fontSize: 18, fontWeight: "700", fill: color }) });
      lab.position.set(x + 12, y + 8);
      const val = new Text({ text: "", style: new TextStyle({ fontFamily: KFONT, fontSize: 20, fontWeight: "800", fill: COLORS.ink }) });
      val.anchor.set(1, 0); val.position.set(x + cw - 12, y + 7);
      bar.addChild(lab, val);
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

  // ───────── 매니저 말풍선 (패널 위에 떠 있음) ─────────
  buildManagerBubble() {
    const y = 724, h = 66;
    const c = new Container();
    c.addChild(new Graphics().roundRect(16, y, DESIGN_WIDTH - 32, h, 16).fill({ color: 0x2c3c63, alpha: 0.94 }));
    const who = new Text({ text: "한지원", style: new TextStyle({ fontFamily: KFONT, fontSize: 18, fontWeight: "800", fill: COLORS.mint }) });
    who.position.set(32, y + 10);
    this.mgrText = new Text({ text: MANAGER_LINES[0], style: new TextStyle({ fontFamily: KFONT, fontSize: 21, fill: 0xffffff }) });
    this.mgrText.position.set(32, y + 34);
    c.addChild(who, this.mgrText);
    this.addChild(c);
  }

  // ───────── 하단 명령 패널 ─────────
  buildPanel() {
    const panel = new Graphics().roundRect(0, PANEL_TOP, DESIGN_WIDTH, DESIGN_HEIGHT - PANEL_TOP, 26).fill({ color: 0xfdfbf7, alpha: 0.98 });
    this.addChild(panel);

    // 슬롯 표시(2개)
    this.slotChips = [];
    const sy = PANEL_TOP + 18, sw = 330, sh = 46;
    for (let i = 0; i < 2; i++) {
      const x = 20 + i * (sw + 20);
      const chip = new Container();
      chip.position.set(x, sy);
      const g = new Graphics().roundRect(0, 0, sw, sh, 12).fill(0xf0ece4).stroke({ width: 2, color: 0xd8d0c4 });
      const txt = new Text({ text: `슬롯 ${i + 1}: 비어있음`, style: new TextStyle({ fontFamily: KFONT, fontSize: 18, fill: 0x8a7b72 }) });
      txt.position.set(14, 12);
      chip.addChild(g, txt);
      chip._txt = txt;
      chip.eventMode = "static"; chip.cursor = "pointer";
      chip.on("pointertap", () => { if (this.selected[i] !== undefined) { this.selected.splice(i, 1); this._afterSelectChange(); } });
      this.addChild(chip);
      this.slotChips.push(chip);
    }

    this.menuLayer = new Container();
    this.addChild(this.menuLayer);
  }

  _afterSelectChange() {
    // 슬롯 칩 갱신
    this.slotChips.forEach((chip, i) => {
      const act = ACTIVITIES.find((a) => a.id === this.selected[i]);
      chip._txt.text = act ? `슬롯 ${i + 1}: ${act.name}` : `슬롯 ${i + 1}: 비어있음`;
      chip._txt.style.fill = act ? COLORS.ink : 0x8a7b72;
    });
    // 마지막 선택 활동 포즈 미리보기
    const last = ACTIVITIES.find((a) => a.id === this.selected[this.selected.length - 1]);
    this.setPose(last ? last.pose : null);
    // 다음 달 버튼 활성 톤
    const ready = this.selected.length > 0;
    this.nextBtnBg.clear().roundRect(20, this._nextY, DESIGN_WIDTH - 40, 66, 20).fill(ready ? COLORS.coral : 0xd8c4bf);
  }

  // ───────── 메뉴 렌더 (카테고리 ↔ 세부) ─────────
  renderMenu() {
    this.menuLayer.removeChildren();
    if (this.menuMode === "category") this._renderCategories();
    else this._renderSub(this.activeCat);
  }

  _btn(x, y, w, h, fill, drawFn, onTap) {
    const c = new Container(); c.position.set(x, y);
    const g = new Graphics().roundRect(0, 0, w, h, 14).fill(fill);
    c.addChild(g);
    drawFn(c, w, h);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", onTap);
    this.menuLayer.addChild(c);
    return c;
  }

  _renderCategories() {
    const mx = 18, gap = 10, y = PANEL_TOP + 86, h = 150;
    const w = (DESIGN_WIDTH - mx * 2 - gap * 3) / 4;
    CATEGORIES.forEach((cat, i) => {
      const x = mx + i * (w + gap);
      this._btn(x, y, w, h, cat.color, (c) => {
        const e = new Text({ text: cat.emoji, style: new TextStyle({ fontFamily: KFONT, fontSize: 44 }) });
        e.anchor.set(0.5); e.position.set(w / 2, 44); c.addChild(e);
        const l = new Text({ text: cat.label, style: new TextStyle({ fontFamily: KFONT, fontSize: 24, fontWeight: "800", fill: 0xffffff }) });
        l.anchor.set(0.5); l.position.set(w / 2, 96); c.addChild(l);
        const d = new Text({ text: cat.desc, style: new TextStyle({ fontFamily: KFONT, fontSize: 12, fill: 0xffffff, align: "center", wordWrap: true, wordWrapWidth: w - 12 }) });
        d.anchor.set(0.5, 0); d.position.set(w / 2, 116); c.addChild(d);
      }, () => { this.menuMode = "sub"; this.activeCat = cat.id; this.renderMenu(); });
    });
  }

  _renderSub(catId) {
    const cat = CATEGORIES.find((c) => c.id === catId);
    // 뒤로 버튼
    this._btn(18, PANEL_TOP + 80, 150, 44, 0xece6dc, (c) => {
      const t = new Text({ text: "← 카테고리", style: new TextStyle({ fontFamily: KFONT, fontSize: 18, fontWeight: "700", fill: COLORS.ink }) });
      t.position.set(14, 11); c.addChild(t);
    }, () => { this.menuMode = "category"; this.renderMenu(); });
    const title = new Text({ text: `${cat.emoji} ${cat.label}`, style: new TextStyle({ fontFamily: KFONT, fontSize: 22, fontWeight: "800", fill: cat.color }) });
    title.position.set(186, PANEL_TOP + 88); this.menuLayer.addChild(title);

    // 세부 활동 2열 그리드
    const list = ACTIVITIES.filter((a) => a.cat === catId);
    const mx = 18, gap = 12, top = PANEL_TOP + 138, w = (DESIGN_WIDTH - mx * 2 - gap) / 2, h = 94;
    list.forEach((act, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = mx + col * (w + gap), y = top + row * (h + gap);
      this._btn(x, y, w, h, 0xffffff, (c) => {
        c.children[0].stroke({ width: 2, color: 0xe4ddd2 });
        const e = new Text({ text: act.emoji, style: new TextStyle({ fontFamily: KFONT, fontSize: 30 }) });
        e.position.set(12, 10); c.addChild(e);
        const n = new Text({ text: act.name, style: new TextStyle({ fontFamily: KFONT, fontSize: 20, fontWeight: "800", fill: COLORS.ink }) });
        n.position.set(54, 12); c.addChild(n);
        const d = new Text({ text: act.desc, style: new TextStyle({ fontFamily: KFONT, fontSize: 14, fill: 0x8a7b72 }) });
        d.position.set(14, 48); c.addChild(d);
        const cost = new Text({ text: this._costText(act), style: new TextStyle({ fontFamily: KFONT, fontSize: 13, fill: 0xb04a3a }) });
        cost.position.set(14, 70); c.addChild(cost);
      }, () => this.pickActivity(act.id));
    });
  }

  _costText(a) {
    const p = [];
    if (a.money) p.push(`돈 ${a.money > 0 ? "+" : ""}${Math.round(a.money / 10000)}만`);
    if (a.stamina) p.push(`체력 ${a.stamina > 0 ? "+" : ""}${a.stamina}`);
    if (a.mental) p.push(`멘탈 ${a.mental > 0 ? "+" : ""}${a.mental}`);
    return p.join("  ");
  }

  pickActivity(id) {
    if (this.selected.length >= 2) this.selected.shift();
    this.selected.push(id);
    this._afterSelectChange();
    this.menuMode = "category";   // 선택 후 카테고리로 복귀 (두 번째 선택)
    this.renderMenu();
  }

  // ───────── 다음 달 ─────────
  buildNextButton() {
    this._nextY = DESIGN_HEIGHT - 78;
    this.nextBtn = new Container();
    this.nextBtnBg = new Graphics().roundRect(20, this._nextY, DESIGN_WIDTH - 40, 66, 20).fill(0xd8c4bf);
    this.nextBtnLabel = new Text({ text: "▶  다음 달", style: new TextStyle({ fontFamily: KFONT, fontSize: 28, fontWeight: "800", fill: 0xffffff }) });
    this.nextBtnLabel.anchor.set(0.5); this.nextBtnLabel.position.set(DESIGN_WIDTH / 2, this._nextY + 33);
    this.nextBtn.addChild(this.nextBtnBg, this.nextBtnLabel);
    this.nextBtn.eventMode = "static"; this.nextBtn.cursor = "pointer";
    this.nextBtn.on("pointertap", () => this.onNextMonth());
    this.addChild(this.nextBtn);
  }

  onNextMonth() {
    if (this.selected.length === 0) { this.mgrText.text = "활동을 먼저 골라줘!"; return; }
    if (this.game.isLastTurn) { this.mgrText.text = "3년의 시간이 끝났어. 정말 수고했어!"; this.nextBtnLabel.text = "졸업 🎓"; return; }
    this.game.advance([...this.selected]);
    this.selected = [];
    this._afterSelectChange();
    this.refreshHUD();
    this.menuMode = "category"; this.renderMenu();
    this.mgrText.text = MANAGER_LINES[(this.game.turn - 1) % MANAGER_LINES.length];
  }

  update(delta) {
    if (!this.hero) return;
    this.t += delta;
    const b = Math.sin(this.t * 0.045);
    this.hero.position.y = GROUND_Y + b * 3;
    this.hero.scale.y = this.baseScale * (1 + b * 0.01);
    this.shadow.scale.set(1 - b * 0.04, 1);
  }
}
