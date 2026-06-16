import { Assets, Sprite, Graphics, Container, Text, TextStyle } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { GameState } from "../systems/game.js";
import { ACTIVITIES, CATEGORIES } from "../data/activities.js";

const IDLE_SPRITE = "./assets/portraits/heroine_brown_idle.png";
const POSE_PATH = (key) => `./assets/portraits/poses/soyoon_${key}.png`;
const BG_SCHOOL = "./assets/bg/school.png";

// 캐릭터 상반신(얼굴~가슴) 프레이밍: 머리 위쪽을 화면 상단에 고정하고 크게 키워
// 하반신은 패널 뒤로 — 모든 포즈가 동일한 노출 형식이 되도록 통일.
const HERO_TOP_Y = 96;       // 머리 꼭대기 y
const BUST_DISP_H = 1980;    // 전신 표시 높이(상단 일부만 노출)
const PANEL_TOP = 812;
// 게임 폰트 (index.html @font-face): 디스플레이=Gmarket Bold, 본문=KoPub 돋움, 강조=배민 도현
const FD = "GmarketSansBold, sans-serif";
const FB = "KoPubWorldDotumMedium, sans-serif";
const FA = "BMDOHYEON, sans-serif";

// 시안에서 추출한 디자인 토큰
const S = {
  cream: 0xfdf8f2, gold: 0xd8c7a0, navy: 0x292838, coral: 0xec6f65, coralLo: 0xd6655e,
  ink: 0x3a3a44, sub: 0x8a7b72, panelMint: 0xeaf3ee, white: 0xffffff,
  hp: 0xe2685e, mp: 0x5aa9e6, money: 0xd98e2c, fans: 0xe0a93a,
  tile: { acting: 0xf6cfcb, charm: 0xcde8e4, mind: 0xf6e3c6, life: 0xd7def4 },
  lbl: { acting: 0xe2685e, charm: 0x3fae9e, mind: 0xd98e2c, life: 0x6e7bd6 },
};
const PILL = [["stamina", "체력", S.hp], ["mental", "멘탈", S.mp], ["money", "돈", S.money], ["fans", "팬", S.fans]];

const MANAGER_LINES = [
  "이번 달은 뭘 해볼까?", "무리하지 말고 컨디션도 챙기자.",
  "조금씩 쌓이면 큰 차이가 돼.", "좋아, 네 선택을 믿어볼게.",
];

// 크림 둥근 패널(골드 테두리 + 부드러운 그림자) — 시안 부품 스타일
function creamPanel(x, y, w, h, r, fill = S.cream) {
  const g = new Graphics();
  g.roundRect(x + 2, y + 4, w, h, r).fill({ color: 0x2a2a33, alpha: 0.10 }); // shadow
  g.roundRect(x, y, w, h, r).fill(fill).stroke({ width: 2, color: S.gold });
  return g;
}

export class MainScene extends Scene {
  constructor() {
    super();
    this.game = new GameState();
    this.selected = [];
    this.menuMode = "category";
    this.activeCat = null;
    this.t = 0;
  }

  async onEnter() {
    const bgTex = await Assets.load(BG_SCHOOL);
    const bg = new Sprite(bgTex);
    bg.anchor.set(0.5, 0);
    bg.scale.set(Math.max(DESIGN_WIDTH / bg.texture.width, DESIGN_HEIGHT / bg.texture.height));
    bg.position.set(DESIGN_WIDTH / 2, 0);
    this.addChild(bg);
    this.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill({ color: 0xfff6f3, alpha: 0.18 }));

    const idleTex = await Assets.load(IDLE_SPRITE);
    this.hero = new Sprite(idleTex);
    this.hero.anchor.set(0.5, 0.0);                 // 머리(상단) 기준
    this.hero.position.set(DESIGN_WIDTH / 2, HERO_TOP_Y);
    this._fitHero();
    this.addChild(this.hero);

    this.buildHUD();
    this.buildManagerBubble();
    this.buildPanel();
    this.buildNextButton();
    this.refreshHUD();
    this.renderMenu();
    document.getElementById("loading")?.remove();
  }

  _fitHero() { this.baseScale = BUST_DISP_H / this.hero.texture.height; this.hero.scale.set(this.baseScale); }
  async setPose(k) { try { this.hero.texture = await Assets.load(k ? POSE_PATH(k) : IDLE_SPRITE); this._fitHero(); } catch (e) { console.warn(e); } }

  _text(t, size, fill, weight = "400", fam = FB) {
    return new Text({ text: t, style: new TextStyle({ fontFamily: fam, fontSize: size, fontWeight: weight, fill }) });
  }

  // ───────── 상단 상태바 ─────────
  buildHUD() {
    const bar = new Container();
    bar.addChild(creamPanel(12, 14, DESIGN_WIDTH - 24, 92, 18));
    const cal = this._text("📅", 30); cal.position.set(28, 26); bar.addChild(cal);
    this.turnText = this._text("", 30, S.ink, "800", FD); this.turnText.position.set(70, 24); bar.addChild(this.turnText);
    const name = this._text("⭐ 소윤", 20, S.sub); name.position.set(70, 66); bar.addChild(name);

    this.resText = {};
    const cw = 116, startX = DESIGN_WIDTH - 24 - cw * 2 - 8;
    PILL.forEach(([key, label, color], i) => {
      const x = startX + (i % 2) * (cw + 8), y = 22 + Math.floor(i / 2) * 42;
      bar.addChild(new Graphics().roundRect(x, y, cw, 36, 12).fill(S.white).stroke({ width: 2, color: 0xefe7da }));
      const lab = this._text(label, 17, color, "800", FD); lab.position.set(x + 12, y + 8); bar.addChild(lab);
      const val = this._text("", 19, S.ink, "800", FD); val.anchor.set(1, 0); val.position.set(x + cw - 12, y + 8); bar.addChild(val);
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

  // ───────── 매니저 말풍선 ─────────
  buildManagerBubble() {
    const y = 724, h = 66;
    const c = new Container();
    const g = new Graphics();
    g.roundRect(16, y, DESIGN_WIDTH - 32, h, 18).fill(S.navy);
    g.moveTo(60, y + h).lineTo(84, y + h).lineTo(60, y + h + 16).fill(S.navy); // tail
    c.addChild(g);
    const who = this._text("🎧 한지원", 18, 0x9fe0d0, "800", FD); who.position.set(32, y + 10); c.addChild(who);
    this.mgrText = this._text(MANAGER_LINES[0], 21, S.white); this.mgrText.position.set(32, y + 34); c.addChild(this.mgrText);
    this.addChild(c);
  }

  // ───────── 하단 패널 ─────────
  buildPanel() {
    this.addChild(creamPanel(0, PANEL_TOP, DESIGN_WIDTH, DESIGN_HEIGHT - PANEL_TOP + 30, 28, S.panelMint));

    this.slotChips = [];
    const sy = PANEL_TOP + 16, sw = 326, sh = 48;
    for (let i = 0; i < 2; i++) {
      const x = 22 + i * (sw + 24);
      const chip = new Container(); chip.position.set(x, sy);
      chip.addChild(new Graphics().roundRect(0, 0, sw, sh, 14).fill(S.cream).stroke({ width: 2, color: S.gold }));
      chip.addChild(new Graphics().circle(28, sh / 2, 16).fill(S.coral));
      const num = this._text(String(i + 1), 20, S.white, "800", FD); num.anchor.set(0.5); num.position.set(28, sh / 2); chip.addChild(num);
      const txt = this._text("비어있음", 18, S.sub); txt.position.set(54, 14); chip.addChild(txt);
      chip._txt = txt;
      chip.eventMode = "static"; chip.cursor = "pointer";
      chip.on("pointertap", () => { if (this.selected[i] !== undefined) { this.selected.splice(i, 1); this._afterSelectChange(); } });
      this.addChild(chip); this.slotChips.push(chip);
    }
    this.menuLayer = new Container();
    this.addChild(this.menuLayer);
  }

  _afterSelectChange() {
    this.slotChips.forEach((chip, i) => {
      const act = ACTIVITIES.find((a) => a.id === this.selected[i]);
      chip._txt.text = act ? act.name : "비어있음";
      chip._txt.style.fill = act ? S.ink : S.sub;
    });
    const last = ACTIVITIES.find((a) => a.id === this.selected[this.selected.length - 1]);
    this.setPose(last ? last.pose : null);
    const ready = this.selected.length > 0;
    this._drawCTA(ready);
  }

  // ───────── 메뉴 ─────────
  renderMenu() {
    this.menuLayer.removeChildren();
    if (this.menuMode === "category") this._renderCategories();
    else this._renderSub(this.activeCat);
  }
  _tap(c, fn) { c.eventMode = "static"; c.cursor = "pointer"; c.on("pointertap", fn); }

  _renderCategories() {
    const mx = 20, gap = 12, y = PANEL_TOP + 88, h = 150;
    const w = (DESIGN_WIDTH - mx * 2 - gap * 3) / 4;
    CATEGORIES.forEach((cat, i) => {
      const x = mx + i * (w + gap);
      const c = new Container(); c.position.set(x, y);
      c.addChild(new Graphics().roundRect(2, 4, w, h, 16).fill({ color: 0x2a2a33, alpha: 0.08 }));
      c.addChild(new Graphics().roundRect(0, 0, w, h, 16).fill(S.tile[cat.id]).stroke({ width: 2, color: S.lbl[cat.id], alpha: 0.4 }));
      const e = this._text(cat.emoji, 44); e.anchor.set(0.5); e.position.set(w / 2, 46); c.addChild(e);
      const l = this._text(cat.label, 24, S.lbl[cat.id], "800", FA); l.anchor.set(0.5); l.position.set(w / 2, 96); c.addChild(l);
      const d = this._text(cat.desc, 12, S.sub); d.anchor.set(0.5, 0); d.style.align = "center"; d.style.wordWrap = true; d.style.wordWrapWidth = w - 10;
      d.position.set(w / 2, 118); c.addChild(d);
      this._tap(c, () => { this.menuMode = "sub"; this.activeCat = cat.id; this.renderMenu(); });
      this.menuLayer.addChild(c);
    });
  }

  _renderSub(catId) {
    const cat = CATEGORIES.find((c) => c.id === catId);
    const back = new Container(); back.position.set(20, PANEL_TOP + 82);
    back.addChild(new Graphics().roundRect(0, 0, 152, 44, 14).fill(S.cream).stroke({ width: 2, color: S.gold }));
    back.addChild(this._text("← 카테고리", 18, S.ink, "700", FD)).position.set(14, 11);
    this._tap(back, () => { this.menuMode = "category"; this.renderMenu(); });
    this.menuLayer.addChild(back);
    const title = this._text(`${cat.emoji} ${cat.label}`, 22, S.lbl[catId], "800", FD);
    title.position.set(188, PANEL_TOP + 90); this.menuLayer.addChild(title);

    const list = ACTIVITIES.filter((a) => a.cat === catId);
    const mx = 20, gap = 12, top = PANEL_TOP + 140, w = (DESIGN_WIDTH - mx * 2 - gap) / 2, h = 96;
    list.forEach((act, i) => {
      const x = mx + (i % 2) * (w + gap), y = top + Math.floor(i / 2) * (h + gap);
      const c = new Container(); c.position.set(x, y);
      c.addChild(new Graphics().roundRect(2, 3, w, h, 14).fill({ color: 0x2a2a33, alpha: 0.07 }));
      c.addChild(new Graphics().roundRect(0, 0, w, h, 14).fill(S.white).stroke({ width: 2, color: 0xefe7da }));
      const e = this._text(act.emoji, 30); e.position.set(12, 10); c.addChild(e);
      const n = this._text(act.name, 20, S.ink, "800", FD); n.position.set(54, 12); c.addChild(n);
      const d = this._text(act.desc, 14, S.sub); d.position.set(14, 50); c.addChild(d);
      const cost = this._text(this._costText(act), 13, S.coral); cost.position.set(14, 72); c.addChild(cost);
      this._tap(c, () => this.pickActivity(act.id));
      this.menuLayer.addChild(c);
    });
  }
  _costText(a) {
    const p = [];
    if (a.money) p.push(`💰${a.money > 0 ? "+" : ""}${Math.round(a.money / 10000)}만`);
    if (a.stamina) p.push(`❤️${a.stamina > 0 ? "+" : ""}${a.stamina}`);
    if (a.mental) p.push(`🧠${a.mental > 0 ? "+" : ""}${a.mental}`);
    return p.join("  ");
  }

  pickActivity(id) {
    if (this.selected.length >= 2) this.selected.shift();
    this.selected.push(id);
    this._afterSelectChange();
    this.menuMode = "category"; this.renderMenu();
  }

  // ───────── 다음 달 (코랄 글로시) ─────────
  buildNextButton() {
    this._nextY = DESIGN_HEIGHT - 80;
    this.nextBtn = new Container();
    this.ctaG = new Graphics();
    this.nextBtn.addChild(this.ctaG);
    const label = new Container();
    const play = this._text("▶", 24, S.white); play.position.set(DESIGN_WIDTH / 2 - 78, this._nextY + 18);
    const txt = this._text("다음 달", 30, S.white, "800", FA); txt.position.set(DESIGN_WIDTH / 2 - 48, this._nextY + 14);
    label.addChild(play, txt);
    this.nextBtn.addChild(label);
    this._drawCTA(false);
    this._tap(this.nextBtn, () => this.onNextMonth());
    this.addChild(this.nextBtn);
  }
  _drawCTA(ready) {
    const y = this._nextY, h = 68, x = 20, w = DESIGN_WIDTH - 40;
    const base = ready ? S.coral : 0xd8c4bf, hi = ready ? 0xf2897e : 0xe2d2cd;
    this.ctaG.clear();
    this.ctaG.roundRect(x + 2, y + 5, w, h, 22).fill({ color: 0x2a2a33, alpha: 0.12 });
    this.ctaG.roundRect(x, y, w, h, 22).fill(base);
    this.ctaG.roundRect(x + 8, y + 6, w - 16, h * 0.42, 16).fill({ color: hi, alpha: 0.55 }); // gloss
  }

  onNextMonth() {
    if (this.selected.length === 0) { this.mgrText.text = "활동을 먼저 골라줘!"; return; }
    if (this.game.isLastTurn) { this.mgrText.text = "3년의 시간이 끝났어. 정말 수고했어!"; return; }
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
    this.hero.position.y = HERO_TOP_Y + b * 2;          // 위치만 미세 흔들림(형태 변형 없음)
  }
}
