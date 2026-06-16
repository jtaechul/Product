import { Assets, Sprite, Graphics, Container, Text, TextStyle } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { GameState } from "../systems/game.js";
import { ACTIVITIES, CATEGORIES } from "../data/activities.js";

const IDLE_SPRITE = "./assets/portraits/heroine_brown_idle.png";
const POSE_PATH = (k) => `./assets/portraits/poses/soyoon_${k}.png`;
const BG_SCHOOL = "./assets/bg/school.png";
const UI = (n) => `./assets/ui/${n}.png`;

const HERO_TOP_Y = 98;
const BUST_DISP_H = 1320;
const PANEL_TOP = 772;
const FD = "GmarketSansBold, sans-serif";
const FB = "KoPubWorldDotumMedium, sans-serif";
const S = { ink: 0x3a3a44, sub: 0x8a7b72, gold: 0xd8c7a0, mint: 0xeaf3ee, white: 0xffffff, coral: 0xec6f65 };
const LBL = { acting: 0xe2685e, charm: 0x2e9e8e, mind: 0xc07e1e, life: 0x6e7bd6 };
const PILL = [["stamina", "체력"], ["mental", "멘탈"], ["money", "돈"], ["fans", "팬"]];
const STAT_VIEW = [
  ["acting", "연기"], ["emotion", "감정"], ["vocal", "발성"], ["looks", "외모"], ["singing", "가창"],
  ["dance", "댄스"], ["study", "학업"], ["character", "인성"], ["network", "인맥"], ["fame", "인지"],
];
const MANAGER_LINES = [
  "이번 달은 뭘 해볼까?", "무리하지 말고 컨디션도 챙기자.",
  "조금씩 쌓이면 큰 차이가 돼.", "좋아, 네 선택을 믿어볼게.",
];

export class MainScene extends Scene {
  constructor() {
    super();
    this.game = new GameState();
    this.selected = [];
    this.menuMode = "category";
    this.activeCat = null;
    this.t = 0;
    this.tex = {};
  }

  async onEnter() {
    // 에셋 로드
    const uiNames = ["topbar", "manager_bubble", "slot_chip", "btn_next", "cat_acting", "cat_charm", "cat_mind", "cat_life"];
    const [bgTex, idleTex] = await Promise.all([Assets.load(BG_SCHOOL), Assets.load(IDLE_SPRITE)]);
    await Promise.all(uiNames.map(async (n) => { this.tex[n] = await Assets.load(UI(n)); }));
    this.tex.mgrface = await Assets.load("./assets/manager/hanjiwon.png");

    // 배경 + 캐릭터
    const bg = new Sprite(bgTex);
    bg.anchor.set(0.5, 0);
    bg.scale.set(Math.max(DESIGN_WIDTH / bg.texture.width, DESIGN_HEIGHT / bg.texture.height));
    bg.position.set(DESIGN_WIDTH / 2, 0);
    this.addChild(bg);
    this.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill({ color: 0xfff6f3, alpha: 0.16 }));

    this.hero = new Sprite(idleTex);
    this.hero.anchor.set(0.5, 0.0);
    this.hero.position.set(DESIGN_WIDTH / 2, HERO_TOP_Y);
    this._fitHero();
    this.addChild(this.hero);

    // 하단 패널 배경
    this.addChild(new Graphics().roundRect(0, PANEL_TOP, DESIGN_WIDTH, DESIGN_HEIGHT - PANEL_TOP + 30, 28)
      .fill({ color: S.mint, alpha: 0.96 }).stroke({ width: 2, color: S.gold }));

    this.buildManagerBubble();
    this.buildTopbar();
    this.buildSlots();
    this.buildNextButton();
    this.menuLayer = new Container();
    this.addChild(this.menuLayer);

    this.refreshHUD();
    this.renderMenu();
    document.getElementById("loading")?.remove();
  }

  _fitHero() { this.baseScale = BUST_DISP_H / this.hero.texture.height; this.hero.scale.set(this.baseScale); }
  async setPose(k) { try { this.hero.texture = await Assets.load(k ? POSE_PATH(k) : IDLE_SPRITE); this._fitHero(); } catch (e) { console.warn(e); } }
  _t(txt, size, fill, fam = FB) { return new Text({ text: txt, style: new TextStyle({ fontFamily: fam, fontSize: size, fill }) }); }
  _spr(name, x, y, w) {
    const s = new Sprite(this.tex[name]); s.scale.set(w / s.texture.width); s.position.set(x, y);
    return s;
  }

  // ───────── 상단 상태바 ─────────
  buildTopbar() {
    const bar = new Container();
    bar.addChild(this._spr("topbar", 10, 8, 700));
    const date = this._t("고1·3월", 26, S.ink, FD); date.position.set(40, 24); bar.addChild(date); this.turnText = date;
    const name = this._t("소윤", 17, S.sub); name.position.set(42, 60); bar.addChild(name);
    this.resText = {};
    const RES = [["stamina", "체력", 455, 28], ["money", "돈", 578, 28], ["mental", "멘탈", 455, 58], ["fans", "팬", 578, 58]];
    RES.forEach(([key, label, rx, ry]) => {
      const lab = this._t(label, 13, S.ink, FD); lab.position.set(rx, ry); bar.addChild(lab);
      const val = this._t("", 15, S.ink, FD); val.anchor.set(1, 0); val.position.set(rx + 112, ry); bar.addChild(val);
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
    const c = new Container();
    const spr = this._spr("manager_bubble", 100, 636, 520);
    c.addChild(spr);
    const mh = spr.height, dia = 72, acx = 147, acy = 636 + mh * 0.40;
    const face = new Sprite(this.tex.mgrface);
    face.anchor.set(0.5, 0.30); face.scale.set(dia / face.texture.width);
    face.position.set(acx, acy);
    const mask = new Graphics().circle(acx, acy, dia / 2).fill(0xffffff);
    face.mask = mask; c.addChild(face, mask);
    const who = this._t("한지원", 17, 0x22384a, FD); who.position.set(212, 636 + mh * 0.30); c.addChild(who);
    this.mgrText = this._t(MANAGER_LINES[0], 18, 0x22384a);
    this.mgrText.style.wordWrap = true; this.mgrText.style.wordWrapWidth = 360;
    this.mgrText.position.set(212, 636 + mh * 0.52); c.addChild(this.mgrText);
    this.addChild(c);
  }

  // ───────── 슬롯 ─────────
  buildSlots() {
    this.slotChips = [];
    for (let i = 0; i < 2; i++) {
      const sx = 22 + i * (326 + 24);
      const chip = new Container();
      const spr = this._spr("slot_chip", sx, 788, 326); chip.addChild(spr);
      const cyc = 788 + spr.height / 2;
      const num = this._t(String(i + 1), 18, S.white, FD); num.anchor.set(0.5); num.position.set(sx + 48, cyc); chip.addChild(num);
      const txt = this._t("비어있음", 16, S.sub); txt.anchor.set(0, 0.5); txt.position.set(sx + 96, cyc); chip.addChild(txt);
      chip._txt = txt;
      chip.eventMode = "static"; chip.cursor = "pointer";
      chip.on("pointertap", () => { if (this.selected[i] !== undefined) { this.selected.splice(i, 1); this._afterSelectChange(); } });
      this.addChild(chip); this.slotChips.push(chip);
    }
  }
  _afterSelectChange() {
    this.slotChips.forEach((chip, i) => {
      const act = ACTIVITIES.find((a) => a.id === this.selected[i]);
      chip._txt.text = act ? act.name : "비어있음";
      chip._txt.style.fill = act ? S.ink : S.sub;
    });
    const last = ACTIVITIES.find((a) => a.id === this.selected[this.selected.length - 1]);
    this.setPose(last ? last.pose : null);
  }

  // ───────── 메뉴 (카테고리 ↔ 세부) ─────────
  renderMenu() {
    this.menuLayer.removeChildren();
    if (this.menuMode === "category") { this._renderCategories(); this._renderStats(); }
    else this._renderSub(this.activeCat);
  }
  _tap(c, fn) { c.eventMode = "static"; c.cursor = "pointer"; c.on("pointertap", fn); }

  _renderCategories() {
    const cw = 140, gap = 10, startX = (DESIGN_WIDTH - (cw * 4 + gap * 3)) / 2, y = 874;
    CATEGORIES.forEach((cat, i) => {
      const cx = startX + i * (cw + gap);
      const c = new Container();
      const spr = this._spr(`cat_${cat.id}`, cx, y, cw); c.addChild(spr);
      const l = this._t(cat.label, 21, S.white, FD); l.anchor.set(0.5, 0.5); l.position.set(cx + cw / 2, y + spr.height * 0.42); c.addChild(l);
      this._tap(c, () => { this.menuMode = "sub"; this.activeCat = cat.id; this.renderMenu(); });
      this.menuLayer.addChild(c);
    });
  }

  _renderStats() {
    const x = 18, y = 1058, w = DESIGN_WIDTH - 36, h = 88;
    this.menuLayer.addChild(new Graphics().roundRect(x, y, w, h, 14).fill({ color: 0xfdfbf7, alpha: 0.96 }).stroke({ width: 2, color: S.gold }));
    const cols = 5, cwid = (w - 24) / cols, x0 = x + 12, y0 = y + 8;
    STAT_VIEW.forEach(([key, label], i) => {
      const cx = x0 + (i % cols) * cwid, cy = y0 + Math.floor(i / cols) * 40;
      const val = key === "fame" ? this.game.fans : this.game.stats[key];
      this.menuLayer.addChild(Object.assign(this._t(label, 14, S.sub), { x: cx, y: cy }));
      const v = this._t(String(val), 15, S.ink, FD); v.anchor.set(1, 0); v.position.set(cx + cwid - 22, cy - 1); this.menuLayer.addChild(v);
      const bw = cwid - 22;
      this.menuLayer.addChild(new Graphics().roundRect(cx, cy + 20, bw, 6, 3).fill(0xe9e2d6));
      const f = Math.max(0, Math.min(1, val / 100));
      if (f > 0) this.menuLayer.addChild(new Graphics().roundRect(cx, cy + 20, Math.max(4, bw * f), 6, 3).fill(S.coral));
    });
  }

  _renderSub(catId) {
    const cat = CATEGORIES.find((c) => c.id === catId);
    const back = new Container();
    back.addChild(new Graphics().roundRect(20, 864, 152, 44, 14).fill(0xfdfbf7).stroke({ width: 2, color: S.gold }));
    back.addChild(Object.assign(this._t("← 카테고리", 18, S.ink, FD), { x: 34, y: 875 }));
    this._tap(back, () => { this.menuMode = "category"; this.renderMenu(); });
    this.menuLayer.addChild(back);
    this.menuLayer.addChild(Object.assign(this._t(cat.label, 22, LBL[catId], FD), { x: 190, y: 874 }));

    const list = ACTIVITIES.filter((a) => a.cat === catId);
    const mx = 20, gap = 12, top = 922, w = (DESIGN_WIDTH - mx * 2 - gap) / 2, h = 92;
    list.forEach((act, i) => {
      const x = mx + (i % 2) * (w + gap), y = top + Math.floor(i / 2) * (h + gap);
      const c = new Container();
      c.addChild(new Graphics().roundRect(x, y, w, h, 14).fill(S.white).stroke({ width: 2, color: 0xefe7da }));
      c.addChild(Object.assign(this._t(act.name, 19, S.ink, FD), { x: x + 16, y: y + 12 }));
      c.addChild(Object.assign(this._t(act.desc, 13, S.sub), { x: x + 14, y: y + 48 }));
      c.addChild(Object.assign(this._t(this._cost(act), 12, S.coral), { x: x + 14, y: y + 68 }));
      this._tap(c, () => this.pickActivity(act.id));
      this.menuLayer.addChild(c);
    });
  }
  _cost(a) {
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
    this.menuMode = "category"; this.renderMenu();
  }

  // ───────── 다음 달 ─────────
  buildNextButton() {
    const c = new Container();
    const spr = this._spr("btn_next", 110, 1150, 500); c.addChild(spr);
    const lab = this._t("다음 달", 28, S.white, FD); lab.anchor.set(0.5); lab.position.set(DESIGN_WIDTH / 2, 1150 + spr.height / 2); c.addChild(lab);
    this._tap(c, () => this.onNextMonth());
    this.addChild(c);
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
    this.hero.position.y = HERO_TOP_Y + Math.sin(this.t * 0.045) * 2;
  }
}
