import { Assets, Sprite, Graphics, Container, Text, TextStyle } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { GameState } from "../systems/game.js";
import { ACTIVITIES, CATEGORIES } from "../data/activities.js";
import { MEDIA, GRADE_COMMENTS } from "../data/media.js";

const GRADE_INFO = {
  best: { label: "인생 연기", color: 0xf5c451 },
  good: { label: "호평", color: 0x3fae9e },
  fair: { label: "무난", color: 0x8a7b72 },
  bad: { label: "혹평", color: 0xd6655e },
};

const IDLE_SPRITE = "./assets/portraits/heroine_brown_idle.png";
const POSE_PATH = (k) => `./assets/portraits/poses/soyoon_${k}.png`;
const BG_SCHOOL = "./assets/bg/school.png";
const UI = (n) => `./assets/ui/${n}.png`;

const HERO_TOP_Y = 100;
const BUST_DISP_H = 1320;
const PANEL_TOP = 742;
const FD = "GmarketSansBold, sans-serif";
const FB = "KoPubWorldDotumMedium, sans-serif";
const S = { ink: 0x3a3a44, sub: 0x8a7b72, gold: 0xd8c7a0, mint: 0xeaf3ee, white: 0xffffff, coral: 0xec6f65 };
const LBL = { acting: 0xe2685e, charm: 0x2e9e8e, mind: 0xc07e1e, life: 0x6e7bd6 };
const SCOL = { act: 0xec6f65, charm: 0x2e9e8e, mind: 0xc07e1e, soc: 0x6e7bd6 };
const STAT_VIEW = [
  ["acting", "연기", "act"], ["emotion", "감정", "act"], ["vocal", "발성", "act"], ["looks", "외모", "charm"], ["singing", "가창", "charm"],
  ["dance", "댄스", "charm"], ["study", "학업", "mind"], ["character", "인성", "mind"], ["network", "인맥", "soc"], ["fame", "인지", "soc"],
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
    this.overlay = null;
  }

  async onEnter() {
    const uiNames = ["topbar2", "stats_frame", "manager_bubble", "slot_chip", "btn_next", "cat_acting", "cat_charm", "cat_mind", "cat_life"];
    const [bgTex, idleTex] = await Promise.all([Assets.load(BG_SCHOOL), Assets.load(IDLE_SPRITE)]);
    await Promise.all(uiNames.map(async (n) => { this.tex[n] = await Assets.load(UI(n)); }));
    await Promise.all(ACTIVITIES.map(async (a) => { this.tex[`actico_${a.id}`] = await Assets.load(UI(`actico_${a.id}`)); }));
    await Promise.all(CATEGORIES.map(async (c) => { this.tex[`catico_${c.id}`] = await Assets.load(UI(`catico_${c.id}`)); }));
    this.tex.mgrface = await Assets.load("./assets/manager/hanjiwon.png");
    this.idleTex = idleTex;

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
    this.mgrText.text = this._mgrLine();
    document.getElementById("loading")?.remove();
  }

  _fitHero() { this.baseScale = BUST_DISP_H / this.hero.texture.height; this.hero.scale.set(this.baseScale); }
  async setPose(k) { try { this.hero.texture = await Assets.load(k ? POSE_PATH(k) : IDLE_SPRITE); this._fitHero(); } catch (e) { console.warn(e); } }
  _t(txt, size, fill, fam = FB) { return new Text({ text: txt, style: new TextStyle({ fontFamily: fam, fontSize: size, fill }) }); }
  _spr(name, x, y, w) { const s = new Sprite(this.tex[name]); s.scale.set(w / s.texture.width); s.position.set(x, y); return s; }

  // 얼굴을 원형 프레임에 꽉 차게 (얼굴 크롭 + 마스크)
  _faceCircle(parent, tex, cx, cy, dia, wfrac, cyfrac) {
    const f = new Sprite(tex);
    f.anchor.set(0.5, cyfrac);
    f.scale.set(dia / (wfrac * tex.width));
    f.position.set(cx, cy);
    const mk = new Graphics().circle(cx, cy, dia / 2).fill(0xffffff);
    f.mask = mk; parent.addChild(f, mk);
  }

  // ───────── 상단 상태바 (topbar2) ─────────
  buildTopbar() {
    const bar = new Container();
    bar.addChild(this._spr("topbar2", 10, 8, 700));
    // ② 얼굴 대신 계절명만 (프레임 안 중앙)
    this.seasonText = this._t("", 26, 0xffffff, FD); this.seasonText.anchor.set(0.5); this.seasonText.position.set(87, 78); bar.addChild(this.seasonText);
    // ① 날짜·이름 크게 + 중앙정렬
    const date = this._t("고1·3월", 24, S.ink, FD); date.anchor.set(0.5); date.position.set(215, 66); bar.addChild(date); this.turnText = date;
    const name = this._t("소윤", 18, S.sub, FD); name.anchor.set(0.5); name.position.set(215, 98); bar.addChild(name);
    // ③ 자원칩: 라벨/값 2줄 중앙정렬
    this.resText = {};
    const RES = [["stamina", "체력", 366], ["mental", "멘탈", 460], ["money", "자금", 554], ["fans", "인지도", 649]];
    RES.forEach(([key, label, x]) => {
      const lab = this._t(label, 11, S.ink, FB); lab.anchor.set(0.5); lab.position.set(x, 64); bar.addChild(lab);
      const val = this._t("", 15, S.ink, FD); val.anchor.set(0.5); val.position.set(x, 90); bar.addChild(val);
      this.resText[key] = val;
    });
    this.addChild(bar);
  }

  _season() {
    let m = ((this.game.turn - 1) % 12) + 3; if (m > 12) m -= 12;
    if (m >= 3 && m <= 5) return { name: "봄", color: 0xf6c6d4, fg: 0xc23b5a };
    if (m >= 6 && m <= 8) return { name: "여름", color: 0x9bd7f0, fg: 0x1c6e92 };
    if (m >= 9 && m <= 11) return { name: "가을", color: 0xf0b878, fg: 0x8a4e16 };
    return { name: "겨울", color: 0xd2e6f4, fg: 0x3a6e92 };
  }
  refreshHUD() {
    this.turnText.text = this.game.label;
    const s = this._season();
    this.seasonText.text = s.name; this.seasonText.style.fill = s.fg;
    this.resText.stamina.text = String(this.game.stamina);
    this.resText.mental.text = String(this.game.mental);
    this.resText.money.text = `${this.game.moneyShort()}원`;
    this.resText.fans.text = String(this.game.fans);
  }

  // ───────── 매니저 말풍선 ─────────
  buildManagerBubble() {
    const c = new Container();
    const spr = this._spr("manager_bubble", 120, 608, 480); c.addChild(spr);
    const mh = spr.height, acx = 171, acy = 668;
    this._faceCircle(c, this.tex.mgrface, acx, acy, 54, 0.50, 0.24);
    const who = this._t("한지원", 16, 0x22384a, FD); who.position.set(260, 608 + mh * 0.30); c.addChild(who);
    this.mgrText = this._t(MANAGER_LINES[0], 17, 0x22384a);
    this.mgrText.style.wordWrap = true; this.mgrText.style.wordWrapWidth = 300;
    this.mgrText.position.set(260, 608 + mh * 0.54); c.addChild(this.mgrText);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", () => this.openOffers());
    this.addChild(c);
  }

  _mgrLine() {
    const n = this.game.offers.length;
    if (n > 0) return `이번 달 출연 제안 ${n}개! (눌러서 보기)`;
    return MANAGER_LINES[(this.game.turn - 1) % MANAGER_LINES.length];
  }

  _closeOverlay() {
    if (this.overlay) { this.removeChild(this.overlay); this.overlay.destroy({ children: true }); this.overlay = null; }
  }
  _dim() {
    const ov = new Container();
    const bg = new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill({ color: 0x1a1420, alpha: 0.62 });
    bg.eventMode = "static"; ov.addChild(bg);
    return ov;
  }

  // 작품 출연 제안 팝업 (기획서 11번)
  openOffers() {
    if (this.overlay) return;
    const ov = this._dim(); this.overlay = ov;
    const cw = 600, x = (DESIGN_WIDTH - cw) / 2, n = this.game.offers.length;
    const ch = 150 + n * 132, y = (DESIGN_HEIGHT - ch) / 2;
    ov.addChild(new Graphics().roundRect(x, y, cw, ch, 24).fill(0xfdf8f2).stroke({ width: 3, color: S.gold }));
    ov.addChild(Object.assign(this._t("🎬 이번 달 출연 제안", 24, S.ink, FD), { x: x + 30, y: y + 24 }));
    ov.addChild(Object.assign(this._t("선택하면 슬롯에 담겨 이번 달에 출연해요", 14, S.sub), { x: x + 30, y: y + 58 }));
    this.game.offers.forEach((id, i) => {
      const m = MEDIA.find((mm) => mm.id === id);
      const cy = y + 92 + i * 132, card = new Container();
      card.addChild(new Graphics().roundRect(x + 24, cy, cw - 48, 116, 16).fill(0xffffff).stroke({ width: 2, color: 0xefe7da }));
      card.addChild(Object.assign(this._t(m.name, 22, S.ink, FD), { x: x + 44, y: cy + 16 }));
      const req = Object.entries(m.req).map(([k, v]) => `${this._statLabel(k)} ${v}`).join(" · ");
      card.addChild(Object.assign(this._t(`기대치  ${req}`, 14, S.sub), { x: x + 44, y: cy + 50 }));
      card.addChild(Object.assign(this._t(`출연료  ${m.pay}만원`, 14, 0xb04a3a), { x: x + 44, y: cy + 74 }));
      const grade = this._predict(m);
      const gi = GRADE_INFO[grade];
      card.addChild(new Graphics().roundRect(x + cw - 150, cy + 40, 100, 36, 12).fill(gi.color));
      card.addChild(Object.assign((() => { const t = this._t(`예상 ${gi.label}`, 14, 0xffffff, FD); t.anchor.set(0.5); t.position.set(x + cw - 100, cy + 58); return t; })(), {}));
      card.eventMode = "static"; card.cursor = "pointer";
      card.on("pointertap", () => this.selectProduction(id));
      ov.addChild(card);
    });
    const close = new Container();
    close.addChild(new Graphics().roundRect(x + cw / 2 - 70, y + ch - 52, 140, 40, 14).fill(0xece6dc));
    close.addChild((() => { const t = this._t("닫기", 18, S.ink, FD); t.anchor.set(0.5); t.position.set(x + cw / 2, y + ch - 32); return t; })());
    close.eventMode = "static"; close.cursor = "pointer"; close.on("pointertap", () => this._closeOverlay());
    ov.addChild(close);
    this.addChild(ov);
  }
  _statLabel(k) { return ({ acting: "연기력", emotion: "감정", vocal: "발성", looks: "외모", singing: "가창", dance: "댄스", study: "학업", character: "인성", network: "인맥", fame: "인지도" })[k] || k; }
  _predict(m) {
    let P = 0, E = 0;
    for (const [k, v] of Object.entries(m.req)) { E += v; P += k === "fame" ? this.game.fans : (this.game.stats[k] || 0); }
    const r = E ? P / E : 1;
    return r >= 1.25 ? "best" : r >= 1.0 ? "good" : r >= 0.8 ? "fair" : "bad";
  }
  selectProduction(id) {
    if (this.selected.length >= 2) this.selected.shift();
    this.selected.push(`prod:${id}`);
    this._afterSelectChange();
    this._closeOverlay();
  }

  // 출연 평가 연출 팝업
  showEval(results) {
    let idx = 0;
    const render = () => {
      this._closeOverlay();
      if (idx >= results.length) { this.refreshHUD(); this.menuMode = "category"; this.renderMenu(); return; }
      const { media, grade } = results[idx];
      const gi = GRADE_INFO[grade], comments = GRADE_COMMENTS[grade];
      const ov = this._dim(); this.overlay = ov;
      const cw = 600, x = (DESIGN_WIDTH - cw) / 2, chh = 480, y = (DESIGN_HEIGHT - chh) / 2;
      ov.addChild(new Graphics().roundRect(x, y, cw, chh, 24).fill(0xfdf8f2).stroke({ width: 3, color: S.gold }));
      ov.addChild((() => { const t = this._t(`「${media.name}」 방영!`, 22, S.ink, FD); t.anchor.set(0.5); t.position.set(DESIGN_WIDTH / 2, y + 40); return t; })());
      // 등급 배지
      ov.addChild(new Graphics().roundRect(DESIGN_WIDTH / 2 - 110, y + 70, 220, 64, 18).fill(gi.color));
      ov.addChild((() => { const t = this._t(gi.label, 30, 0xffffff, FD); t.anchor.set(0.5); t.position.set(DESIGN_WIDTH / 2, y + 102); return t; })());
      // 댓글 연출
      comments.forEach((cm, i) => {
        const cyc = y + 158 + i * 56;
        ov.addChild(new Graphics().roundRect(x + 34, cyc, cw - 68, 46, 12).fill(0xffffff).stroke({ width: 1, color: 0xeee6da }));
        ov.addChild(Object.assign(this._t(`💬 ${cm}`, 15, S.ink), { x: x + 48, y: cyc + 13 }));
      });
      const tip = this._t("화면을 누르면 계속", 14, S.sub); tip.anchor.set(0.5); tip.position.set(DESIGN_WIDTH / 2, y + chh - 28); ov.addChild(tip);
      ov.children[0].on("pointertap", () => { idx += 1; render(); });
      this.addChild(ov);
    };
    render();
  }

  // ───────── 슬롯 ─────────
  buildSlots() {
    this.slotChips = [];
    for (let i = 0; i < 2; i++) {
      const sx = 22 + i * (326 + 24);
      const chip = new Container();
      const spr = this._spr("slot_chip", sx, 754, 326); chip.addChild(spr);
      const cyc = 754 + spr.height / 2;
      const num = this._t(String(i + 1), 18, S.white, FD); num.anchor.set(0.5); num.position.set(sx + 48, cyc); chip.addChild(num);
      const txt = this._t("비어있음", 18, S.sub, FD); txt.anchor.set(0, 0.5); txt.position.set(sx + 96, cyc); chip.addChild(txt);
      chip._txt = txt;
      chip.eventMode = "static"; chip.cursor = "pointer";
      chip.on("pointertap", () => { if (this.selected[i] !== undefined) { this.selected.splice(i, 1); this._afterSelectChange(); } });
      this.addChild(chip); this.slotChips.push(chip);
    }
  }
  _afterSelectChange() {
    this.slotChips.forEach((chip, i) => {
      const sel = this.selected[i];
      if (!sel) { chip._txt.text = "비어있음"; chip._txt.style.fill = S.sub; return; }
      if (sel.startsWith("prod:")) {
        const m = MEDIA.find((x) => x.id === sel.slice(5));
        chip._txt.text = `🎬 ${m.name}`; chip._txt.style.fill = S.coral;
      } else {
        const act = ACTIVITIES.find((a) => a.id === sel);
        chip._txt.text = act ? act.name : "비어있음"; chip._txt.style.fill = act ? S.ink : S.sub;
      }
    });
    const last = this.selected[this.selected.length - 1];
    let pose = null;
    if (last) pose = last.startsWith("prod:") ? "filming" : (ACTIVITIES.find((a) => a.id === last) || {}).pose || null;
    this.setPose(pose);
  }

  // ───────── 메뉴 ─────────
  renderMenu() {
    this.menuLayer.removeChildren();
    if (this.menuMode === "category") { this._renderCategories(); this._renderStats(); }
    else this._renderSub(this.activeCat);
  }
  _tap(c, fn) { c.eventMode = "static"; c.cursor = "pointer"; c.on("pointertap", fn); }

  _renderCategories() {
    const cw = 122, gap = 10, startX = (DESIGN_WIDTH - (cw * 4 + gap * 3)) / 2, y = 842;
    CATEGORIES.forEach((cat, i) => {
      const cx = startX + i * (cw + gap);
      const c = new Container();
      const spr = this._spr(`cat_${cat.id}`, cx, y, cw); c.addChild(spr);
      const l = this._t(cat.label, 20, S.white, FD); l.anchor.set(0.5, 0.5); l.position.set(cx + cw / 2, y + spr.height * 0.30); c.addChild(l);
      const ico = new Sprite(this.tex[`catico_${cat.id}`]); ico.anchor.set(0.5); ico.scale.set(56 / Math.max(ico.texture.width, ico.texture.height)); ico.position.set(cx + cw / 2, y + spr.height * 0.60); c.addChild(ico);
      this._tap(c, () => { this.menuMode = "sub"; this.activeCat = cat.id; this.renderMenu(); });
      this.menuLayer.addChild(c);
    });
  }

  _renderStats() {
    this.menuLayer.addChild(this._spr("stats_frame", 18, 1000, 684));
    const statHead = this._t("능력치", 18, S.white, FD); statHead.anchor.set(0.5); statHead.position.set(121, 1019); this.menuLayer.addChild(statHead);
    const colx = [35, 165, 295, 425, 555], ty = [1070, 1129], tw = 93;
    STAT_VIEW.forEach(([key, label, cat], i) => {
      const c = i % 5, r = Math.floor(i / 5), x = 18 + colx[c], y = ty[r];
      const val = key === "fame" ? this.game.fans : this.game.stats[key];
      const nm = this._t(label, 16, S.ink, FB); nm.anchor.set(0, 1); nm.position.set(x, y); this.menuLayer.addChild(nm);
      const v = this._t(String(val), 17, SCOL[cat], FD); v.anchor.set(1, 1); v.position.set(x + tw, y); this.menuLayer.addChild(v);
    });
  }

  _renderSub(catId) {
    const cat = CATEGORIES.find((c) => c.id === catId);
    const back = new Container();
    back.addChild(new Graphics().roundRect(20, 842, 150, 44, 14).fill(0xfdfbf7).stroke({ width: 2, color: S.gold }));
    back.addChild(Object.assign(this._t("← 카테고리", 18, S.ink, FD), { x: 34, y: 853 }));
    this._tap(back, () => { this.menuMode = "category"; this.renderMenu(); });
    this.menuLayer.addChild(back);
    this.menuLayer.addChild(Object.assign(this._t(cat.label, 22, LBL[catId], FD), { x: 190, y: 850 }));

    const list = ACTIVITIES.filter((a) => a.cat === catId);
    const mx = 20, gap = 12, top = 896, w = (DESIGN_WIDTH - mx * 2 - gap) / 2, h = 92;
    list.forEach((act, i) => {
      const x = mx + (i % 2) * (w + gap), y = top + Math.floor(i / 2) * (h + gap);
      const c = new Container();
      c.addChild(new Graphics().roundRect(x, y, w, h, 14).fill(S.white).stroke({ width: 2, color: 0xefe7da }));
      const ico = new Sprite(this.tex[`actico_${act.id}`]); ico.anchor.set(0.5); ico.scale.set(60 / Math.max(ico.texture.width, ico.texture.height));
      ico.position.set(x + 42, y + h / 2); c.addChild(ico);
      c.addChild(Object.assign(this._t(act.name, 19, S.ink, FD), { x: x + 80, y: y + 14 }));
      c.addChild(Object.assign(this._t(act.desc, 13, S.sub), { x: x + 80, y: y + 44 }));
      c.addChild(Object.assign(this._t(this._cost(act), 12, S.coral), { x: x + 80, y: y + 66 }));
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

  buildNextButton() {
    const c = new Container();
    const spr = this._spr("btn_next", 140, 1172, 440); c.addChild(spr);
    const lab = this._t("다음 달 일정 진행하기", 20, S.white, FD); lab.anchor.set(0.5); lab.position.set(DESIGN_WIDTH / 2, 1172 + spr.height / 2); c.addChild(lab);
    this._tap(c, () => this.onNextMonth());
    this.addChild(c);
  }
  onNextMonth() {
    if (this.overlay) return;
    if (this.selected.length === 0) { this.mgrText.text = "활동을 먼저 골라줘!"; return; }
    if (this.game.isLastTurn) { this.mgrText.text = "3년의 시간이 끝났어. 정말 수고했어!"; return; }
    const prods = this.selected.filter((s) => s.startsWith("prod:")).map((s) => s.slice(5));
    const acts = this.selected.filter((s) => !s.startsWith("prod:"));
    const results = prods.map((id) => this.game.runProduction(id)).filter(Boolean);
    this.game.advance(acts);
    this.selected = [];
    this._afterSelectChange();
    this.refreshHUD();
    this.menuMode = "category"; this.renderMenu();
    this.mgrText.text = this._mgrLine();
    if (results.length) this.showEval(results);
  }

  update(delta) {
    if (!this.hero) return;
    this.t += delta;
    this.hero.position.y = HERO_TOP_Y + Math.sin(this.t * 0.045) * 2;
  }
}
