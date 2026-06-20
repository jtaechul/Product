import { Assets, Sprite, Graphics, Container, Text, TextStyle } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT, TOTAL_TURNS } from "../config.js";
import { GameState } from "../systems/game.js";
import { computeEnding, saveToDex, ENDING_COUNT } from "../systems/ending.js";
import { saveGame } from "../systems/save.js";
import { playBgm, stopBgm, setBgmOn, setSfxOn, isBgmOn, isSfxOn } from "../systems/sound.js";

// 계절별 인게임 BGM
const SEASON_BGM = { 봄: "bgm_spring", 여름: "bgm_summer", 가을: "bgm_autumn", 겨울: "bgm_winter" };
import { ACTIVITIES, CATEGORIES, ACT_LINES, SEASON_LINES, SPECIAL_ACTS, findActivity } from "../data/activities.js";
import { MEDIA, GRADE_COMMENTS } from "../data/media.js";
import { BONDS, BOND_THRESHOLD } from "../data/bonds.js";

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
  ["dance", "댄스", "charm"], ["study", "학업", "mind"], ["character", "인성", "mind"], ["network", "인맥", "soc"], ["fame", "팬", "soc"],
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
    const uiNames = ["topbar2", "stats_frame", "manager_bubble", "bond_frame", "slot_chip", "btn_next", "cat_acting", "cat_charm", "cat_mind", "cat_life",
      "menu_panel", "menu_btn", "offer_frame", "icon_back", "icon_save", "icon_list", "icon_flag", "icon_music", "icon_speaker"];
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
    this.buildSaveButton();
    this.menuLayer = new Container();
    this.bottomBlock.addChild(this.menuLayer);

    this.refreshHUD();
    this.renderMenu();
    this.mgrText.text = this._mgrLine();
    this._updateSeasonBgm();
    document.getElementById("loading")?.remove();
  }

  onExit() { stopBgm(); super.onExit(); }

  // 계절이 바뀌면 인게임 BGM 전환 (스케줄 화면 진입 시 시작)
  _updateSeasonBgm() {
    const s = this._season().name;
    if (s === this._bgmSeason) return;
    this._bgmSeason = s;
    playBgm(`./assets/sfx/${SEASON_BGM[s] || "bgm_spring"}.mp3`, 0.45);
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
    const RES = [["stamina", "체력", 366], ["mental", "멘탈", 460], ["money", "자금", 554], ["fans", "팬", 649]];
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
    if (this._bgmSeason) this._updateSeasonBgm();
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
    const n = this.game.offers.length + this._specialsAvailable().length;
    if (n > 0) return `이번 달 제안 ${n}개! (눌러서 보기)`;
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

  // 메뉴 버튼 (인연 버튼 아래) — 설정·저장·종료 등
  buildSaveButton() {
    const c = new Container(); c.position.set(0, 0);
    c.addChild(new Graphics().roundRect(628, 204, 80, 46, 14).fill(0xfdf8f2).stroke({ width: 2, color: S.gold }));
    const t = this._t("메뉴", 18, 0x4a5a8a, FD); t.anchor.set(0.5); t.position.set(668, 227); c.addChild(t);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", () => this.openMenu());
    this.addChild(c);
  }

  // 인게임 메뉴 (설정): 핑크 패널 + 버튼 프레임 + 커스텀 아이콘
  openMenu() {
    if (this.overlay) return;
    const ov = this._dim(); this.overlay = ov;
    const ptex = this.tex.menu_panel, pw = 548, ph = pw * ptex.height / ptex.width;
    const px = (DESIGN_WIDTH - pw) / 2, py = ((this.H || DESIGN_HEIGHT) - ph) / 2;
    const panel = new Sprite(ptex); panel.scale.set(pw / ptex.width); panel.position.set(px, py); ov.addChild(panel);
    ov.addChild((() => { const t = this._t("메 뉴", 30, 0xa84a64, FD); t.anchor.set(0.5); t.position.set(DESIGN_WIDTH / 2, py + ph * 0.072); return t; })());
    const rows = new Container(); ov.addChild(rows);
    const btex = this.tex.menu_btn, bw = pw * 0.80, bh = bw * btex.height / btex.width, bx = px + (pw - bw) / 2;
    const icons = ["icon_back", "icon_save", "icon_list", "icon_flag", "icon_music", "icon_speaker"];
    const top = py + ph * 0.155, gap = (ph * 0.80) / 6;
    const build = () => {
      rows.removeChildren();
      const items = [
        { label: "게임으로 돌아가기", fn: () => this._closeOverlay() },
        { label: "저장하기", fn: () => { const ok = saveGame(this.game); this._closeOverlay(); this._toast(ok ? "저장 완료!" : "저장 실패…"); } },
        { label: "메인 메뉴로", fn: () => { try { window.location.reload(); } catch (e) {} } },
        { label: "게임 종료하기", fn: () => this._quitGame() },
        { label: `배경음악  ${isBgmOn() ? "켜짐" : "꺼짐"}`, fn: () => { setBgmOn(!isBgmOn()); build(); } },
        { label: `효과음  ${isSfxOn() ? "켜짐" : "꺼짐"}`, fn: () => { setSfxOn(!isSfxOn()); build(); } },
      ];
      items.forEach((it, i) => {
        const by = top + i * gap, b = new Container();
        const spr = new Sprite(btex); spr.scale.set(bw / btex.width); spr.position.set(bx, by); b.addChild(spr);
        const ic = new Sprite(this.tex[icons[i]]); ic.anchor.set(0.5); ic.scale.set((bh * 0.5) / Math.max(ic.texture.width, ic.texture.height)); ic.position.set(bx + bw * 0.13, by + bh / 2); b.addChild(ic);
        const t = this._t(it.label, 23, 0xffffff, FD); t.anchor.set(0.5); t.position.set(bx + bw * 0.60, by + bh / 2); b.addChild(t);
        b.eventMode = "static"; b.cursor = "pointer"; b.on("pointertap", it.fn);
        rows.addChild(b);
      });
    };
    build();
    this.addChild(ov);
  }
  _quitGame() {
    this._closeOverlay();
    const H = this.H || DESIGN_HEIGHT;
    const ov = new Container(); this.overlay = ov;
    ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, H).fill(0x0c0a12));
    const t = this._t("플레이해 주셔서 고맙습니다.\n창을 닫으셔도 됩니다.", 30, S.gold, FD); t.anchor.set(0.5); t.style.align = "center"; t.style.lineHeight = 46; t.position.set(DESIGN_WIDTH / 2, H / 2); ov.addChild(t);
    this.addChild(ov);
    stopBgm();
    try { window.close(); } catch (e) {}
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

  // 이번 분기 특별활동(있으면) — 첫 턴 제외, 분기(turn 4·7·…)에만
  _specialsAvailable() { return ((this.game.turn - 1) % 3 === 0 && this.game.turn > 1) ? SPECIAL_ACTS : []; }

  // 이번 달 제안 팝업 (기획서 11·3): 출연 제안 + 분기 특별활동 병합
  openOffers() {
    if (this.overlay) return;
    const offers = this.game.offers, specials = this._specialsAvailable();
    const ov = this._dim(); this.overlay = ov;
    const cw = 624, x = (DESIGN_WIDTH - cw) / 2;
    let bodyH = 0;
    if (offers.length) bodyH += 34 + offers.length * 128;
    if (specials.length) bodyH += 34 + specials.length * 82;
    if (!offers.length && !specials.length) bodyH = 56;
    const ch = 112 + bodyH + 60, y = Math.max(40, (DESIGN_HEIGHT - ch) / 2);
    ov.addChild(new Graphics().roundRect(x, y, cw, ch, 24).fill(0xfdf8f2).stroke({ width: 3, color: S.gold }));
    ov.addChild(Object.assign(this._t("이번 달 제안", 24, S.ink, FD), { x: x + 30, y: y + 22 }));
    ov.addChild(Object.assign(this._t("한지원: 좋은 기회야. 잘 골라보자!", 14, S.sub), { x: x + 30, y: y + 56 }));
    let cy = y + 96;
    if (!offers.length && !specials.length) {
      ov.addChild(Object.assign(this._t("이번 달은 들어온 제안이 없어요.", 17, S.sub), { x: x + 36, y: cy + 6 }));
    }
    if (offers.length) {
      ov.addChild(Object.assign(this._t("출연 제안", 17, 0xb04a3a, FD), { x: x + 30, y: cy })); cy += 34;
      offers.forEach((id) => {
        const m = MEDIA.find((mm) => mm.id === id), card = new Container();
        card.addChild(new Graphics().roundRect(x + 24, cy, cw - 48, 116, 16).fill(0xffffff).stroke({ width: 2, color: 0xefe7da }));
        card.addChild(Object.assign(this._t(m.name, 22, S.ink, FD), { x: x + 44, y: cy + 14 }));
        const req = Object.entries(m.req).map(([k, v]) => `${this._statLabel(k)} ${v}`).join(" · ");
        card.addChild(Object.assign(this._t(`기대치  ${req}`, 14, S.sub), { x: x + 44, y: cy + 48 }));
        card.addChild(Object.assign(this._t(`출연료  ${m.pay}만원`, 14, 0xb04a3a), { x: x + 44, y: cy + 72 }));
        const gi = GRADE_INFO[this._predict(m)];
        card.addChild(new Graphics().roundRect(x + cw - 150, cy + 40, 100, 36, 12).fill(gi.color));
        card.addChild(Object.assign((() => { const t = this._t(`예상 ${gi.label}`, 14, 0xffffff, FD); t.anchor.set(0.5); t.position.set(x + cw - 100, cy + 58); return t; })(), {}));
        card.eventMode = "static"; card.cursor = "pointer"; card.on("pointertap", () => this.selectProduction(id));
        ov.addChild(card); cy += 128;
      });
    }
    if (specials.length) {
      ov.addChild(Object.assign(this._t("분기 특별활동", 17, 0x2e9e8e, FD), { x: x + 30, y: cy })); cy += 34;
      specials.forEach((a) => {
        const card = new Container();
        card.addChild(new Graphics().roundRect(x + 24, cy, cw - 48, 70, 16).fill(0xffffff).stroke({ width: 2, color: 0xefe7da }));
        card.addChild(Object.assign(this._t(a.name, 20, S.ink, FD), { x: x + 44, y: cy + 10 }));
        card.addChild(Object.assign(this._t(`${this._effText(a)}   ${this._cost(a)}`, 13, 0x2e9e8e), { x: x + 44, y: cy + 42 }));
        card.eventMode = "static"; card.cursor = "pointer"; card.on("pointertap", () => this.selectSpecial(a.id));
        ov.addChild(card); cy += 82;
      });
    }
    const close = new Container();
    close.addChild(new Graphics().roundRect(x + cw / 2 - 70, y + ch - 52, 140, 40, 14).fill(0xece6dc));
    close.addChild((() => { const t = this._t("닫기", 18, S.ink, FD); t.anchor.set(0.5); t.position.set(x + cw / 2, y + ch - 32); return t; })());
    close.eventMode = "static"; close.cursor = "pointer"; close.on("pointertap", () => this._closeOverlay());
    ov.addChild(close);
    this.addChild(ov);
  }
  _statLabel(k) { return ({ acting: "연기력", emotion: "감정", vocal: "발성", looks: "외모", singing: "가창", dance: "댄스", study: "학업", character: "인성", network: "인맥", fame: "팬" })[k] || k; }
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
        const act = findActivity(sel);
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

  selectSpecial(id) {
    if (this.selected.length >= 2) this.selected.shift();
    this.selected.push(id);
    this._afterSelectChange();
    this._closeOverlay();
  }

  // 학년 말 시상식 연출 (기획서 3·15): 시상식 배경 + 트로피 + 수상 결과
  _playCeremony(res) {
    return new Promise((resolve) => {
      const ov = new Container(); this.overlay = ov;
      ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill(0x0e0b14));
      const bgSpr = new Sprite(); bgSpr.anchor.set(0.5, 0); bgSpr.position.set(DESIGN_WIDTH / 2, 0); ov.addChild(bgSpr);
      ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, DESIGN_HEIGHT).fill({ color: 0x0e0b14, alpha: 0.45 }));
      const title = this._t(`${res.grade} 말 · 시상식`, 30, S.gold, FD); title.anchor.set(0.5); title.position.set(DESIGN_WIDTH / 2, 250); ov.addChild(title);
      const charC = new Container(); ov.addChild(charC);
      const awardBox = new Container(); ov.addChild(awardBox);
      ov.addChild(new Graphics().roundRect(60, 980, 600, 220, 24).fill({ color: 0x140f1a, alpha: 0.86 }).stroke({ width: 2, color: S.gold }));
      const awardT = this._t("", 40, S.gold, FD); awardT.anchor.set(0.5); awardT.position.set(DESIGN_WIDTH / 2, 1040); ov.addChild(awardT);
      const subT = this._t("", 20, 0xffffff); subT.anchor.set(0.5); subT.style.align = "center"; subT.position.set(DESIGN_WIDTH / 2, 1110); ov.addChild(subT);
      const tip = this._t("화면을 누르면 계속 ▶", 15, 0xcfc7d0); tip.anchor.set(1, 1); tip.position.set(676, 1232); ov.addChild(tip);
      ov.eventMode = "static";
      ov.on("pointertap", () => { this._closeOverlay(); resolve(); });
      this.addChild(ov);
      const won = res.fansGain > 0;
      Promise.all([Assets.load("./assets/bg/award.png").catch(() => null), Assets.load(POSE_PATH(won ? "cheer" : "good")).catch(() => null)]).then(([bgTex, pTex]) => {
        if (bgTex) { bgSpr.texture = bgTex; bgSpr.scale.set(Math.max(DESIGN_WIDTH / bgTex.width, DESIGN_HEIGHT / bgTex.height)); }
        if (pTex) { const sp = new Sprite(pTex); sp.anchor.set(0.5, 1.0); sp.scale.set(820 / pTex.height); sp.position.set(DESIGN_WIDTH / 2, 992); charC.addChild(sp); }
        awardT.text = res.award;
        subT.text = won ? `올해의 성과를 인정받았다!\n팬 +${res.fansGain}${res.best ? ` · 인생연기 ${res.best}편` : ""}` : "다음 해를 기약하며…";
      });
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
      c.addChild(Object.assign(this._t(this._effText(act), 13, 0x2e9e8e), { x: x + 80, y: y + 44 }));
      c.addChild(Object.assign(this._t(this._cost(act), 12, S.coral), { x: x + 80, y: y + 66 }));
      this._tap(c, () => this.pickActivity(act.id));
      this.menuLayer.addChild(c);
    });
  }
  // 활동의 실제 능력치 변동 텍스트 (카드 설명이 수치와 항상 일치하도록)
  _effText(a) {
    const p = [];
    for (const [k, v] of Object.entries(a.effects || {})) p.push(`${this._statLabel(k)}+${v}`);
    return p.join(" ");
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
    this.nextBtn = c;
  }
  onNextMonth() {
    if (this.overlay) return;
    if (this.game.turn > TOTAL_TURNS) { this.showEnding(); return; } // 이미 졸업 → 엔딩 재표시
    if (this.selected.length === 0) { this.mgrText.text = "활동을 먼저 골라줘!"; return; }
    const order = [...this.selected];                    // 슬롯에 올린 순서 보존
    const acts = order.filter((s) => !s.startsWith("prod:"));
    const season = this._season().name;
    // 적용: 출연(평가) → 활동/월정산. 연출은 아래에서 슬롯 순서대로.
    const resultMap = {};
    for (const s of order) if (s.startsWith("prod:")) { const r = this.game.runProduction(s.slice(5)); if (r) resultMap[s] = r; }
    this.game.advance(acts);
    this.selected = [];
    this._afterSelectChange();
    if (this.nextBtn) this.nextBtn.visible = false; // 진행 연출 동안 버튼 숨김
    // 연출: 슬롯에 올린 순서 그대로 진행 → (졸업이면 엔딩) → 랜덤 이벤트
    (async () => {
      let seasonShown = false;
      for (const s of order) {
        if (s.startsWith("prod:")) { if (resultMap[s]) await this._playScene(resultMap[s]); }
        else { await this._playActivities([s], season, !seasonShown); seasonShown = true; }
      }
      this.refreshHUD();
      // 학년 말 시상식 (기획서 3·15): 고1·고2·고3 말(턴 13·25·37)에 그 해 성과로 수상
      if (this.game.turn === 13 || this.game.turn === 25 || this.game.turn > TOTAL_TURNS) {
        await this._playCeremony(this.game.yearAward());
      }
      if (this.game.turn > TOTAL_TURNS) { this.showEnding(); return; } // 36턴 종료 → 40년 커리어 엔딩
      this.menuMode = "category"; this.renderMenu();
      this.mgrText.text = this._mgrLine();
      if (this.nextBtn) this.nextBtn.visible = true; // 행동 완료 → 버튼 다시 표시
      if (this.game.stamina <= 0) this._toast("체력이 바닥났어요! 능력치가 거의 안 올라요 — 휴식이 필요해요");
      else if (this.game.stamina < 20) this._toast("체력이 부족해요 — 능력치 상승이 줄어듭니다");
      this._afterTurn();
    })();
  }

  _actLine(id) { const p = ACT_LINES[id] || ["오늘도 한 걸음 나아갔다."]; return p[Math.floor(Math.random() * p.length)]; }

  // 활동 연출 (기획서 14B): 다음 달 진행 후 선택한 활동의 포즈 + 관련 대사를 차례로 노출
  _playActivities(actIds, season, showSeason = true) {
    return new Promise((resolve) => {
      const beats = [];
      const firstBg = (findActivity(actIds[0]) || {}).bg || "school";
      if (showSeason && Math.random() < 0.28 && SEASON_LINES[season]) beats.push({ who: "", pose: null, bg: firstBg, text: SEASON_LINES[season] });
      for (const id of actIds) {
        const a = findActivity(id);
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
    const L = { acting: "연기력", emotion: "감정", vocal: "발성", looks: "외모", singing: "가창", dance: "댄스", study: "학업", character: "인성", network: "인맥", fame: "팬", mental: "멘탈", stamina: "체력", money: "자금", fans: "팬" };
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
    // 엔딩 BGM: 배우=ending1 / 창작자(감독·작가·PD·제작자)=ending2 / 부정=ending3
    const creatorIds = ["film_director", "drama_producer", "broadcast_pd", "writer", "director_actor"];
    const bgm = res.id === "controversy" ? "ending_bad" : creatorIds.includes(res.id) ? "ending_creator" : "ending_actor";
    playBgm(`./assets/sfx/${bgm}.mp3`, 0.5);
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

    center(this._t("데뷔, 그리고 40년", 16, 0xcdbfa0, FB), 30);
    center(this._t(res.title, 34, S.gold, FD), 48);
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
    center(this._t(`엔딩 도감 ${total} / ${ENDING_COUNT} 수집`, 15, 0xb7ab93, FB), 40);
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
