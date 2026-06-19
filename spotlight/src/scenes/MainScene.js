import { Assets, Sprite, Graphics, Container, Text, TextStyle } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT, TOTAL_TURNS } from "../config.js";
import { GameState } from "../systems/game.js";
import { computeEnding, saveToDex } from "../systems/ending.js";
import { saveGame } from "../systems/save.js";
import { ACTIVITIES, CATEGORIES, ACT_LINES, SEASON_LINES } from "../data/activities.js";
import { MEDIA, GRADE_COMMENTS } from "../data/media.js";
import { BONDS, BOND_THRESHOLD } from "../data/bonds.js";
import { ITEMS } from "../data/items.js";

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

const HERO_TOP_Y = 128;
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
const BOND_INNER = 0.671; // bond_frame.png 안쪽 개구부 / 프레임 크기

export class MainScene extends Scene {
  constructor(game) {
    super();
    this.game = game || new GameState();   // 불러오기 시 기존 GameState 주입
    this.selected = [];
    this.menuMode = "category";
    this.activeCat = null;
    this.t = 0;
    this.tex = {};
    this.overlay = null;
    this.heroDispH = BUST_DISP_H;
  }

  async onEnter() {
    const uiNames = ["topbar2", "stats_frame", "manager_bubble", "bond_frame", "slot_chip", "btn_next", "cat_acting", "cat_charm", "cat_mind", "cat_life"];
    const [bgTex, idleTex] = await Promise.all([Assets.load(BG_SCHOOL), Assets.load(IDLE_SPRITE)]);
    await Promise.all(uiNames.map(async (n) => { this.tex[n] = await Assets.load(UI(n)); }));
    await Promise.all(ACTIVITIES.map(async (a) => { this.tex[`actico_${a.id}`] = await Assets.load(UI(`actico_${a.id}`)); }));
    await Promise.all(CATEGORIES.map(async (c) => { this.tex[`catico_${c.id}`] = await Assets.load(UI(`catico_${c.id}`)); }));
    await Promise.all(["academy", "home", "set", "stage"].map((n) => Assets.load(`./assets/bg/${n}.png`))); // 활동별 배경 프리로드
    this.tex.mgrface = await Assets.load("./assets/manager/hanjiwon.png");
    await Promise.all(BONDS.map(async (b) => { this.tex[`bond_${b.id}`] = await Assets.load(b.img); }));
    this.idleTex = idleTex;

    this.bgSprite = new Sprite(bgTex);
    this.bgSprite.anchor.set(0.5, 0);
    this.bgSprite.scale.set(Math.max(DESIGN_WIDTH / bgTex.width, DESIGN_HEIGHT / bgTex.height));
    this.bgSprite.position.set(DESIGN_WIDTH / 2, 0);
    this.addChild(this.bgSprite);
    this.veil = new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill({ color: 0xfff6f3, alpha: 0.16 });
    this.addChild(this.veil);

    this.hero = new Sprite(idleTex);
    this.hero.anchor.set(0.5, 0.0);
    this.hero.position.set(DESIGN_WIDTH / 2, HERO_TOP_Y);
    this._fitHero();
    this.addChild(this.hero);
    this.heroMask = new Graphics().rect(0, 0, DESIGN_WIDTH, PANEL_TOP).fill(0xffffff);
    this.addChild(this.heroMask);
    this.hero.mask = this.heroMask;

    this.bottomBlock = new Container();
    this.addChild(this.bottomBlock);
    this.panelBg = new Graphics().roundRect(0, PANEL_TOP, DESIGN_WIDTH, DESIGN_HEIGHT - PANEL_TOP + 30, 28)
      .fill({ color: S.mint, alpha: 0.96 }).stroke({ width: 2, color: S.gold });
    this.bottomBlock.addChild(this.panelBg);

    this.buildManagerBubble();
    this.buildTopbar();
    this.buildSlots();
    this.buildNextButton();
    this.buildBondButton();
    this.buildShopButton();
    this.buildSaveButton();
    this.menuLayer = new Container();
    this.bottomBlock.addChild(this.menuLayer);

    this.refreshHUD();
    this.renderMenu();
    this.mgrText.text = this._mgrLine();
    document.getElementById("loading")?.remove();
  }

  _fitHero() { this.baseScale = (this.heroDispH || BUST_DISP_H) / this.hero.texture.height; this.hero.scale.set(this.baseScale); }
  resize(W, H) {
    this.H = H;
    if (this.bgSprite) { const t = this.bgSprite.texture; this.bgSprite.scale.set(Math.max(DESIGN_WIDTH / t.width, H / t.height)); }
    if (this.veil) this.veil.clear().rect(0, 0, DESIGN_WIDTH, H).fill({ color: 0xfff6f3, alpha: 0.16 });
    if (this.bottomBlock) this.bottomBlock.y = H - DESIGN_HEIGHT;
    this.heroDispH = Math.max(1180, (H - 828) / 0.38);
    if (this.hero) this._fitHero();
    if (this.heroMask) this.heroMask.clear().rect(0, 0, DESIGN_WIDTH, H - 538).fill(0xffffff);
  }
  async setPose(k) { try { this.hero.texture = await Assets.load(k ? POSE_PATH(k) : IDLE_SPRITE); this._fitHero(); } catch (e) { console.warn(e); } }
  _t(txt, size, fill, fam = FB) { return new Text({ text: txt, style: new TextStyle({ fontFamily: fam, fontSize: size, fill }) }); }
  _spr(name, x, y, w) { const s = new Sprite(this.tex[name]); s.scale.set(w / s.texture.width); s.position.set(x, y); return s; }

  // 사각 프레임 안에 얼굴 배치 (기획서 17): 가로 중앙 정렬(좌우 여백 동일) + 머리끝 보존 + 목젖 아래 직선 크롭.
  // lm: { cx, top, throat } = 이미지 내 가로중심·머리끝·목젖 위치(비율). 머리끝~목젖을 rh 높이에 맞춰 채운다.
  _faceInRect(parent, tex, rx, ry, rw, rh, lm) {
    const span = (lm.throat - lm.top) * tex.height;     // 머리끝→목젖 (이미지 px)
    const f = new Sprite(tex);
    f.scale.set(rh / span);
    f.anchor.set(lm.cx, lm.top);                         // (가로중심, 머리끝)을
    f.position.set(rx + rw / 2, ry);                     // (칸 가로중앙, 칸 위)에 맞춤
    const mk = new Graphics().rect(rx, ry, rw, rh).fill(0xffffff);
    f.mask = mk; parent.addChild(f, mk);
  }

  // 가로 폭(x0f~x1f)을 칸 폭에 맞춰 채우고, 위(y0f)는 머리끝, 아래는 직선 크롭 — 명시적 크롭 박스용.
  _faceFitW(parent, tex, rx, ry, rw, rh, x0f, x1f, y0f) {
    const f = new Sprite(tex);
    f.scale.set(rw / ((x1f - x0f) * tex.width));
    f.anchor.set((x0f + x1f) / 2, y0f);
    f.position.set(rx + rw / 2, ry);
    const mk = new Graphics().rect(rx, ry, rw, rh).fill(0xffffff);
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
    const name = this._t(this.game.heroName, 18, S.sub, FD); name.anchor.set(0.5); name.position.set(215, 98); bar.addChild(name);
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
    const mh = spr.height;
    // 사각 사진칸: 크롭 박스 x150~490 · y0~410 (가로맞춤·머리끝 보존·아래 직선 크롭, 기획서 17)
    this._faceFitW(c, this.tex.mgrface, 148.8, 628.4, 76.8, 74.4, 150 / 701, 490 / 701, 0);
    const who = this._t("한지원", 16, 0x22384a, FD); who.position.set(262, 634); c.addChild(who);
    this.mgrText = this._t(MANAGER_LINES[0], 17, 0x22384a);
    this.mgrText.style.wordWrap = true; this.mgrText.style.wordWrapWidth = 300;
    this.mgrText.position.set(262, 662); c.addChild(this.mgrText);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", () => this.openOffers());
    this.bottomBlock.addChild(c);
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

  // 인연 보기 버튼 (캐릭터 우측 상단)
  buildBondButton() {
    const c = new Container(); c.position.set(0, 0);
    c.addChild(new Graphics().roundRect(628, 150, 80, 46, 14).fill(0xfdf8f2).stroke({ width: 2, color: S.gold }));
    const t = this._t("인연", 18, S.coral, FD); t.anchor.set(0.5); t.position.set(668, 173); c.addChild(t);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", () => this.openBonds());
    this.addChild(c);
  }

  // 상점 버튼 (인연 버튼 아래)
  buildShopButton() {
    const c = new Container(); c.position.set(0, 0);
    c.addChild(new Graphics().roundRect(628, 204, 80, 46, 14).fill(0xfdf8f2).stroke({ width: 2, color: S.gold }));
    const t = this._t("상점", 18, 0xc07e1e, FD); t.anchor.set(0.5); t.position.set(668, 227); c.addChild(t);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", () => this.openShop());
    this.addChild(c);
  }

  // 저장 버튼 (상점 버튼 아래)
  buildSaveButton() {
    const c = new Container(); c.position.set(0, 0);
    c.addChild(new Graphics().roundRect(628, 258, 80, 46, 14).fill(0xfdf8f2).stroke({ width: 2, color: S.gold }));
    const t = this._t("저장", 18, 0x2e9e8e, FD); t.anchor.set(0.5); t.position.set(668, 281); c.addChild(t);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", () => { const ok = saveGame(this.game); this._toast(ok ? "💾 저장 완료!" : "저장 실패…"); });
    this.addChild(c);
  }

  // 잠깐 떴다 사라지는 안내 토스트
  _toast(msg) {
    if (this._toastNode) { this.removeChild(this._toastNode); this._toastNode.destroy({ children: true }); }
    const c = new Container();
    const t = this._t(msg, 22, 0xffffff, FD); t.anchor.set(0.5);
    const w = t.width + 60, y = (this.H || DESIGN_HEIGHT) * 0.42;
    c.addChild(new Graphics().roundRect(DESIGN_WIDTH / 2 - w / 2, y - 30, w, 60, 18).fill({ color: 0x1a1420, alpha: 0.9 }).stroke({ width: 2, color: S.gold }));
    t.position.set(DESIGN_WIDTH / 2, y); c.addChild(t);
    this.addChild(c); this._toastNode = c;
    let life = 90;
    const tick = () => { life -= 1; c.alpha = Math.min(1, life / 30); if (life <= 0) { this.removeChild(c); c.destroy({ children: true }); if (this._toastNode === c) this._toastNode = null; this._app?.ticker.remove(tick); } };
    this._app = this.manager?.app; this._app?.ticker.add(tick);
  }

  // 상점 팝업 (기획서 8단계): 돈으로 아이템 구매 → 즉시 효과
  openShop() {
    if (this.overlay) return;
    const ov = this._dim(); this.overlay = ov;
    const cw = 640, x = (DESIGN_WIDTH - cw) / 2, rows = ITEMS.length, ch = 150 + rows * 78, y = (DESIGN_HEIGHT - ch) / 2;
    ov.addChild(new Graphics().roundRect(x, y, cw, ch, 24).fill(0xfdf8f2).stroke({ width: 3, color: S.gold }));
    ov.addChild(Object.assign(this._t("🛍️ 상점", 24, S.ink, FD), { x: x + 30, y: y + 24 }));
    const money = this._t(`보유 ${this.game.moneyShort()}원`, 16, 0xb04a3a, FD); money.anchor.set(1, 0); money.position.set(x + cw - 30, y + 30); ov.addChild(money);
    const rebuild = () => {
      ITEMS.forEach((it, i) => {
        const ry = y + 72 + i * 78, can = this.game.money >= it.cost;
        const row = new Container(); row._row = true;
        row.addChild(new Graphics().roundRect(x + 22, ry, cw - 44, 66, 14).fill(0xffffff).stroke({ width: 2, color: 0xefe7da }));
        row.addChild(Object.assign(this._t(`${it.emoji} ${it.name}`, 19, S.ink, FD), { x: x + 40, y: ry + 12 }));
        row.addChild(Object.assign(this._t(it.desc, 13, S.sub), { x: x + 40, y: ry + 40 }));
        const btn = new Container();
        const bx = x + cw - 168, by = ry + 14;
        btn.addChild(new Graphics().roundRect(bx, by, 146, 40, 12).fill(can ? 0xc07e1e : 0xd8d0c4));
        const bt = this._t(`${Math.round(it.cost / 10000)}만원`, 16, 0xffffff, FD); bt.anchor.set(0.5); bt.position.set(bx + 73, by + 20); btn.addChild(bt);
        if (can) { btn.eventMode = "static"; btn.cursor = "pointer"; btn.on("pointertap", () => { if (this.game.buyItem(it.id)) { this.refreshHUD(); this.renderMenu(); money.text = `보유 ${this.game.moneyShort()}원`; redraw(); } }); }
        row.addChild(btn);
        ov.addChild(row);
      });
    };
    const redraw = () => { for (let i = ov.children.length - 1; i >= 0; i--) if (ov.children[i]._row) { const c = ov.removeChildAt(i); c.destroy({ children: true }); } rebuild(); };
    rebuild();
    const close = new Container();
    close.addChild(new Graphics().roundRect(x + cw / 2 - 70, y + ch - 50, 140, 38, 14).fill(0xece6dc));
    close.addChild((() => { const t = this._t("닫기", 18, S.ink, FD); t.anchor.set(0.5); t.position.set(x + cw / 2, y + ch - 31); return t; })());
    close.eventMode = "static"; close.cursor = "pointer"; close.on("pointertap", () => this._closeOverlay());
    ov.addChild(close);
    this.addChild(ov);
  }

  // 인연(Bond) 팝업 (기획서 12번)
  openBonds() {
    if (this.overlay) return;
    const ov = this._dim(); this.overlay = ov;
    const cw = 620, x = (DESIGN_WIDTH - cw) / 2, rows = BONDS.length, ch = 132 + rows * 110, y = (DESIGN_HEIGHT - ch) / 2;
    ov.addChild(new Graphics().roundRect(x, y, cw, ch, 24).fill(0xfdf8f2).stroke({ width: 3, color: S.gold }));
    ov.addChild(Object.assign(this._t("🤝 인연", 24, S.ink, FD), { x: x + 30, y: y + 24 }));
    ov.addChild(Object.assign(this._t(`인연 ${BOND_THRESHOLD} 이상이면 보너스가 발동돼요`, 14, S.sub), { x: x + 30, y: y + 58 }));
    BONDS.forEach((b, i) => {
      const ry = y + 92 + i * 110, val = this.game.bonds[b.id], active = val >= BOND_THRESHOLD;
      ov.addChild(new Graphics().roundRect(x + 22, ry, cw - 44, 96, 16).fill(0xffffff).stroke({ width: 2, color: 0xefe7da }));
      const acx = x + 78, acy = ry + 48, FS = 96, iw = FS * BOND_INNER;
      if (active) ov.addChild(new Graphics().roundRect(acx - FS / 2 - 2, acy - FS / 2 - 2, FS + 4, FS + 4, 14).fill(0xfff1d6));
      // 사각 프레임 사진칸: 얼굴(좌우 여백 동일·머리끝 보존·목젖 직선 크롭) → 금색 프레임 덮기
      this._faceInRect(ov, this.tex[`bond_${b.id}`], acx - iw / 2, acy - iw / 2, iw, iw, b.lm);
      const fr = new Sprite(this.tex.bond_frame); fr.anchor.set(0.5); fr.scale.set(FS / fr.texture.width); fr.position.set(acx, acy); ov.addChild(fr);
      ov.addChild(Object.assign(this._t(b.name, 20, S.ink, FD), { x: x + 138, y: ry + 12 }));
      ov.addChild(Object.assign(this._t(b.role, 13, S.sub), { x: x + 138 + b.name.length * 22 + 8, y: ry + 18 }));
      // 게이지
      const gx = x + 138, gw = 286, gy = ry + 44;
      ov.addChild(new Graphics().roundRect(gx, gy, gw, 12, 6).fill(0xe9e2d6));
      ov.addChild(new Graphics().roundRect(gx, gy, Math.max(6, gw * (val / 100)), 12, 6).fill(active ? S.coral : 0xd8b8b2));
      ov.addChild(Object.assign((() => { const t = this._t(`${val}/100`, 14, S.ink, FD); t.anchor.set(1, 0.5); t.position.set(gx + gw + 60, gy + 6); return t; })(), {}));
      ov.addChild(Object.assign(this._t(active ? `✓ ${b.bonus}` : `🔒 ${b.bonus}`, 13, active ? 0x2e9e8e : S.sub), { x: x + 138, y: ry + 66 }));
    });
    const close = new Container();
    close.addChild(new Graphics().roundRect(x + cw / 2 - 70, y + ch - 50, 140, 38, 14).fill(0xece6dc));
    close.addChild((() => { const t = this._t("닫기", 18, S.ink, FD); t.anchor.set(0.5); t.position.set(x + cw / 2, y + ch - 31); return t; })());
    close.eventMode = "static"; close.cursor = "pointer"; close.on("pointertap", () => this._closeOverlay());
    ov.addChild(close);
    this.addChild(ov);
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

  // 출연 연출 씬 (기획서 11번): 화면 전환 → 촬영장 → 등급별 스토리·포즈
  async playProduction(results) {
    for (const res of results) await this._playScene(res);
    this.refreshHUD();
    this.menuMode = "category"; this.renderMenu();
    this.mgrText.text = this._mgrLine();
  }
  _rewardText(m, grade) {
    const fameMult = { best: 1.6, good: 1.0, fair: 0.3, bad: 0 }[grade];
    const payMult = { best: 1.0, good: 1.0, fair: 0.7, bad: 0.4 }[grade];
    return `팬 +${Math.round(m.fame * fameMult)} · 출연료 ${Math.round(m.pay * payMult)}만원`;
  }
  _beats(m, grade) {
    const end = {
      best: { text: `정적… 그리고 박수가 터졌다. "이게 신인이라고?" 현장이 술렁였다. 인생 연기였다.`, pose: "cheer", tint: 0xfff3c4, tintA: 0.16 },
      good: { text: `안정적인 호흡과 표현. 모니터를 본 감독이 흡족하게 고개를 끄덕였다.`, pose: "cheer", tint: 0xd8f0e8, tintA: 0.12 },
      fair: { text: `큰 실수도 큰 인상도 없이, 무난하게 촬영을 마쳤다.`, pose: "good", tint: 0x000000, tintA: 0 },
      bad: { text: `대사가 자꾸 겉돌았다. "컷, 다시 갈게요…" 아쉬움이 남는 현장이었다.`, pose: "panned", tint: 0x0c0c14, tintA: 0.34 },
    }[grade];
    return [
      { who: "감독", text: `「${m.name}」 촬영장. 카메라에 빨간 불이 들어온다. "자, 갈게요. 레디… 액션!"`, pose: "filming", tint: 0x000000, tintA: 0 },
      { who: "", text: `${end.text}\n\n🎁 ${this._rewardText(m, grade)}`, pose: end.pose, tint: end.tint, tintA: end.tintA, badge: grade },
    ];
  }
  _playScene(result) {
    return new Promise((resolve) => {
      const { media, grade } = result;
      const beats = this._beats(media, grade);
      const bgName = media.id === "musical" ? "stage" : "set";
      const ov = new Container(); this.overlay = ov;
      ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill(0x101018));
      const bgSpr = new Sprite(); bgSpr.anchor.set(0.5, 0); bgSpr.position.set(DESIGN_WIDTH / 2, 0); ov.addChild(bgSpr);
      const tint = new Graphics(); ov.addChild(tint);
      const charC = new Container(); ov.addChild(charC);
      const badgeC = new Container(); ov.addChild(badgeC);
      ov.addChild(new Graphics().roundRect(28, 968, 664, 256, 26).fill({ color: 0x140f1a, alpha: 0.84 }).stroke({ width: 2, color: S.gold }));
      const whoT = this._t("", 20, S.gold, FD); whoT.position.set(54, 988); ov.addChild(whoT);
      const storyT = this._t("", 22, 0xffffff); storyT.style.wordWrap = true; storyT.style.wordWrapWidth = 600; storyT.position.set(54, 1024); ov.addChild(storyT);
      const tip = this._t("화면을 누르면 계속 ▶", 15, 0xcfc7d0); tip.anchor.set(1, 1); tip.position.set(676, 1212); ov.addChild(tip);
      ov.eventMode = "static";
      let idx = 0;
      const show = async () => {
        const b = beats[idx];
        charC.removeChildren(); badgeC.removeChildren();
        const ptex = await Assets.load(b.pose ? POSE_PATH(b.pose) : IDLE_SPRITE);
        const sp = new Sprite(ptex); sp.anchor.set(0.5, 1.0); sp.scale.set(880 / sp.texture.height); sp.position.set(DESIGN_WIDTH / 2, 985); charC.addChild(sp);
        tint.clear(); if (b.tintA) tint.rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill({ color: b.tint, alpha: b.tintA });
        whoT.text = b.who || ""; storyT.text = b.text;
        if (b.badge) {
          const gi = GRADE_INFO[b.badge];
          badgeC.addChild(new Graphics().roundRect(DESIGN_WIDTH / 2 - 120, 150, 240, 72, 20).fill(gi.color).stroke({ width: 3, color: 0xffffff }));
          const t = this._t(gi.label, 34, 0xffffff, FD); t.anchor.set(0.5); t.position.set(DESIGN_WIDTH / 2, 186); badgeC.addChild(t);
        }
      };
      ov.on("pointertap", async () => { idx += 1; if (idx >= beats.length) { this._closeOverlay(); resolve(); } else await show(); });
      this.addChild(ov);
      Assets.load(`./assets/bg/${bgName}.png`).then((tex) => {
        bgSpr.texture = tex; bgSpr.scale.set(Math.max(DESIGN_WIDTH / tex.width, DESIGN_HEIGHT / tex.height));
        show();
      });
    });
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
      this.bottomBlock.addChild(chip); this.slotChips.push(chip);
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
    // 메인 화면 캐릭터는 항상 idle 유지 — 활동 이미지는 '다음 달 진행' 후 연출에서만 노출(기획서 14B)
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
    const spr = this._spr("btn_next", 116, 1172, 488); c.addChild(spr);
    const lab = this._t("다음 달 일정 진행하기", 27, S.white, FD); lab.anchor.set(0.5); lab.position.set(DESIGN_WIDTH / 2, 1172 + spr.height / 2); c.addChild(lab);
    this._tap(c, () => this.onNextMonth());
    this.bottomBlock.addChild(c);
  }
  onNextMonth() {
    if (this.overlay) return;
    if (this.game.turn > TOTAL_TURNS) { this.showEnding(); return; } // 이미 졸업 → 엔딩 재표시
    if (this.selected.length === 0) { this.mgrText.text = "활동을 먼저 골라줘!"; return; }
    const prods = this.selected.filter((s) => s.startsWith("prod:")).map((s) => s.slice(5));
    const acts = this.selected.filter((s) => !s.startsWith("prod:"));
    const season = this._season().name;
    const results = prods.map((id) => this.game.runProduction(id)).filter(Boolean);
    this.game.advance(acts);
    this.selected = [];
    this._afterSelectChange();
    // 연출 순서: 활동 이미지+대사 → 작품 출연 평가 → (졸업이면 엔딩) → 랜덤 이벤트
    (async () => {
      if (acts.length) await this._playActivities(acts, season);
      if (results.length) await this.playProduction(results);
      this.refreshHUD();
      if (this.game.turn > TOTAL_TURNS) { this.showEnding(); return; } // 36턴 종료 → 40년 커리어 엔딩
      this.menuMode = "category"; this.renderMenu();
      this.mgrText.text = this._mgrLine();
      this._afterTurn();
    })();
  }

  _actLine(id) { const p = ACT_LINES[id] || ["오늘도 한 걸음 나아갔다."]; return p[Math.floor(Math.random() * p.length)]; }

  // 활동 연출 (기획서 14B): 다음 달 진행 후 선택한 활동의 포즈 + 관련 대사를 차례로 노출
  _playActivities(actIds, season) {
    return new Promise((resolve) => {
      const beats = [];
      const firstBg = (ACTIVITIES.find((x) => x.id === actIds[0]) || {}).bg || "school";
      if (Math.random() < 0.28 && SEASON_LINES[season]) beats.push({ who: "", pose: null, bg: firstBg, text: SEASON_LINES[season] });
      for (const id of actIds) {
        const a = ACTIVITIES.find((x) => x.id === id);
        beats.push({ who: a ? a.name : "", pose: a ? a.pose : null, bg: (a && a.bg) || "school", text: this._actLine(id) });
      }
      if (!beats.length) { resolve(); return; }
      const ov = new Container(); this.overlay = ov;
      ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill(0x101018));
      const bgSpr = new Sprite(this.bgSprite.texture); bgSpr.anchor.set(0.5, 0); bgSpr.position.set(DESIGN_WIDTH / 2, 0); ov.addChild(bgSpr);
      const fitBg = () => bgSpr.scale.set(Math.max(DESIGN_WIDTH / bgSpr.texture.width, DESIGN_HEIGHT / bgSpr.texture.height));
      fitBg();
      ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill({ color: 0x2a2030, alpha: 0.34 }));
      const charC = new Container(); ov.addChild(charC);
      ov.addChild(new Graphics().roundRect(28, 968, 664, 256, 26).fill({ color: 0x140f1a, alpha: 0.84 }).stroke({ width: 2, color: S.gold }));
      const whoT = this._t("", 20, S.gold, FD); whoT.position.set(54, 988); ov.addChild(whoT);
      const storyT = this._t("", 22, 0xffffff); storyT.style.wordWrap = true; storyT.style.wordWrapWidth = 600; storyT.position.set(54, 1024); ov.addChild(storyT);
      const tip = this._t("화면을 누르면 계속 ▶", 15, 0xcfc7d0); tip.anchor.set(1, 1); tip.position.set(676, 1212); ov.addChild(tip);
      ov.eventMode = "static";
      let idx = 0;
      const show = async () => {
        const b = beats[idx]; charC.removeChildren();
        // 행동마다 다른 배경 (기획서 14B)
        try { bgSpr.texture = await Assets.load(`./assets/bg/${b.bg}.png`); fitBg(); } catch (e) {}
        const ptex = await Assets.load(b.pose ? POSE_PATH(b.pose) : IDLE_SPRITE);
        const sp = new Sprite(ptex); sp.anchor.set(0.5, 1.0); sp.scale.set(880 / sp.texture.height); sp.position.set(DESIGN_WIDTH / 2, 985); charC.addChild(sp);
        whoT.text = b.who || ""; storyT.text = b.text;
      };
      ov.on("pointertap", async () => { idx += 1; if (idx >= beats.length) { this._closeOverlay(); resolve(); } else await show(); });
      this.addChild(ov);
      show();
    });
  }

  // 다음 달 진행 후 랜덤 이벤트 (기획서 13번)
  _afterTurn() {
    const ev = this.game.rollEvent();
    if (ev) this.showEvent(ev);
  }
  _effSummary(c) {
    const L = { acting: "연기력", emotion: "감정", vocal: "발성", looks: "외모", singing: "가창", dance: "댄스", study: "학업", character: "인성", network: "인맥", fame: "인지도", mental: "멘탈", stamina: "체력", money: "자금", fans: "인지도" };
    const p = [];
    for (const [k, v] of Object.entries(c.effects || {})) p.push(`${L[k] || k} ${v > 0 ? "+" : ""}${k === "money" ? Math.round(v / 10000) + "만" : v}`);
    if (c.flag) p.push("✦숨은 평판");
    return p.join("   ");
  }
  showEvent(ev) {
    const ov = this._dim(); this.overlay = ov;
    const cw = 604, x = (DESIGN_WIDTH - cw) / 2;
    const build = (chosen) => {
      while (ov.children.length > 1) { const c = ov.removeChildAt(ov.children.length - 1); c.destroy && c.destroy({ children: true }); }
      if (chosen) {
        const ch = 296, y = (DESIGN_HEIGHT - ch) / 2;
        ov.addChild(new Graphics().roundRect(x, y, cw, ch, 24).fill(0xfdf8f2).stroke({ width: 3, color: S.gold }));
        ov.addChild(Object.assign(this._t(`${ev.emoji} ${ev.title}`, 22, S.ink, FD), { x: x + 30, y: y + 26 }));
        const r = this._t(chosen.result, 20, 0x4a4a55); r.style.wordWrap = true; r.style.wordWrapWidth = cw - 60; r.position.set(x + 30, y + 78); ov.addChild(r);
        ov.addChild(Object.assign(this._t(this._effSummary(chosen), 16, S.coral, FD), { x: x + 30, y: y + ch - 104 }));
        const btn = new Container();
        btn.addChild(new Graphics().roundRect(x + cw / 2 - 84, y + ch - 62, 168, 46, 16).fill(S.coral));
        btn.addChild((() => { const t = this._t("확인", 20, 0xffffff, FD); t.anchor.set(0.5); t.position.set(x + cw / 2, y + ch - 39); return t; })());
        btn.eventMode = "static"; btn.cursor = "pointer"; btn.on("pointertap", () => this._closeOverlay());
        ov.addChild(btn);
      } else {
        const ch = 168 + ev.choices.length * 72, y = (DESIGN_HEIGHT - ch) / 2;
        ov.addChild(new Graphics().roundRect(x, y, cw, ch, 24).fill(0xfdf8f2).stroke({ width: 3, color: S.gold }));
        ov.addChild(Object.assign(this._t(`${ev.emoji} ${ev.title}`, 24, S.ink, FD), { x: x + 30, y: y + 24 }));
        const txt = this._t(ev.text, 19, 0x4a4a55); txt.style.wordWrap = true; txt.style.wordWrapWidth = cw - 60; txt.position.set(x + 30, y + 66); ov.addChild(txt);
        ev.choices.forEach((c, i) => {
          const by = y + 144 + i * 72;
          const btn = new Container();
          btn.addChild(new Graphics().roundRect(x + 28, by, cw - 56, 60, 14).fill(0xffffff).stroke({ width: 2, color: 0xefe7da }));
          btn.addChild(Object.assign(this._t(c.label, 19, S.ink, FD), { x: x + 48, y: by + 10 }));
          btn.addChild(Object.assign(this._t(this._effSummary(c), 13, S.sub), { x: x + 48, y: by + 35 }));
          btn.eventMode = "static"; btn.cursor = "pointer";
          btn.on("pointertap", () => { this.game.applyEventEffects(c.effects, c.flag); this.refreshHUD(); this.renderMenu(); build(c); });
          ov.addChild(btn);
        });
      }
    };
    build(null);
    this.addChild(ov);
  }

  // ───────── 40년 커리어 엔딩 (기획서 15번) ─────────
  async showEnding() {
    this._closeOverlay();
    const res = computeEnding(this.game);
    const total = saveToDex(res.id);
    const H = this.H || DESIGN_HEIGHT;
    const ov = new Container(); ov._isEnding = true; this.overlay = ov;
    ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, H).fill(0x0e0b14));
    try {
      const bgTex = await Assets.load("./assets/bg/award.png");
      const bg = new Sprite(bgTex); bg.anchor.set(0.5, 0); bg.position.set(DESIGN_WIDTH / 2, 0);
      bg.scale.set(Math.max(DESIGN_WIDTH / bgTex.width, H / bgTex.height)); bg.alpha = 0.45; ov.addChild(bg);
    } catch (e) {}
    ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, H).fill({ color: 0x0e0b14, alpha: 0.5 }));

    // 스크롤 가능한 본문
    const viewH = H - 132;
    const view = new Container(); ov.addChild(view);
    const vMask = new Graphics().rect(0, 0, DESIGN_WIDTH, viewH).fill(0xffffff); ov.addChild(vMask); view.mask = vMask;
    const content = new Container(); view.addChild(content);
    let y = 36;
    const center = (node, dy) => { node.anchor?.set?.(0.5, 0); node.position.set(DESIGN_WIDTH / 2, y); content.addChild(node); y += dy ?? (node.height + 16); };

    try {
      const ilTex = await Assets.load(`./assets/endings/${res.illust}.png`);
      const il = new Sprite(ilTex); il.anchor.set(0.5, 0); il.scale.set(440 / ilTex.width); il.position.set(DESIGN_WIDTH / 2, y);
      content.addChild(il); y += il.height + 18;
    } catch (e) {}

    center(this._t("🎬 데뷔, 그리고 40년", 16, 0xcdbfa0, FB), 30);
    center(this._t(`${res.emoji} ${res.title}`, 34, S.gold, FD), 48);
    center(this._t(`― ${res.trait} ―`, 18, 0xe8dcc4, FD), 42);

    const story = this._t(res.story, 19, 0xf2ecdf);
    story.style.wordWrap = true; story.style.wordWrapWidth = DESIGN_WIDTH - 96; story.style.lineHeight = 30; story.style.align = "center";
    story.anchor.set(0.5, 0); story.position.set(DESIGN_WIDTH / 2, y); content.addChild(story); y += story.height + 30;

    if (res.filmography.length) {
      center(this._t("대표 필모그래피", 19, S.gold, FD), 34);
      for (const f of res.filmography.slice(0, 6)) {
        const tag = f.grade === "best" ? "★ 인생연기" : "호평";
        center(this._t(`${f.label} · 「${f.name}」 · ${tag}`, 16, 0xeae0cf, FB), 28);
      }
      y += 10;
    }
    if (res.awards.length) {
      center(this._t("수상 이력", 19, S.gold, FD), 34);
      for (const a of res.awards) center(this._t(`🏆 ${a}`, 16, 0xeae0cf, FB), 28);
      y += 10;
    }
    if (res.people.length) {
      center(this._t("함께한 사람들", 19, S.gold, FD), 34);
      center(this._t(res.people.join("  ·  "), 17, 0xeae0cf, FB), 30);
      y += 10;
    }
    center(this._t(`📖 엔딩 도감 ${total} / 15 수집`, 15, 0xb7ab93, FB), 40);
    const contentH = y;

    // 드래그 스크롤
    const scrollMin = Math.min(0, viewH - contentH - 24);
    const scale = () => (window.innerWidth || DESIGN_WIDTH) / DESIGN_WIDTH;
    let dragging = false, lastY = 0, moved = 0;
    vMask.eventMode = "static";
    ov.eventMode = "static";
    ov.on("pointerdown", (e) => { dragging = true; lastY = e.global.y; moved = 0; });
    ov.on("pointermove", (e) => {
      if (!dragging) return;
      const dy = (e.global.y - lastY) / scale(); lastY = e.global.y; moved += Math.abs(dy);
      content.y = Math.max(scrollMin, Math.min(0, content.y + dy));
    });
    const endDrag = () => { dragging = false; };
    ov.on("pointerup", endDrag); ov.on("pointerupoutside", endDrag);

    // 하단 고정 버튼
    const mkBtn = (label, bx, color, fn) => {
      const c = new Container();
      c.addChild(new Graphics().roundRect(bx, H - 96, 300, 60, 18).fill(color).stroke({ width: 2, color: 0xffffff }));
      const t = this._t(label, 22, 0xffffff, FD); t.anchor.set(0.5); t.position.set(bx + 150, H - 66); c.addChild(t);
      c.eventMode = "static"; c.cursor = "pointer"; c.on("pointertap", fn);
      ov.addChild(c);
    };
    mkBtn("🔄 다시 도전", 40, S.coral, () => this.manager.change(new MainScene(new GameState())));
    mkBtn("🏠 메인으로", DESIGN_WIDTH - 340, 0x4a5a8a, () => { try { window.location.reload(); } catch (e) { this.manager.change(new MainScene(new GameState())); } });

    this.addChild(ov);
  }

  update(delta) {
    if (!this.hero) return;
    this.t += delta;
    this.hero.position.y = HERO_TOP_Y + Math.sin(this.t * 0.045) * 2;
  }
}
