import { Assets, Sprite, Graphics, Text, TextStyle, Container } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { hasSave, loadGame, saveLabel } from "../systems/save.js";
import { GameState } from "../systems/game.js";
import { MainScene } from "./MainScene.js";

const FD = "GmarketSansBold, sans-serif";
const FB = "KoPubWorldDotumMedium, sans-serif";
const GOLD = 0xf3c969, CREAM = 0xfdf6e6, INK = 0x2a2230;

// 프린세스 메이커 풍 오프닝 (기획서: 새로 시작 / 불러오기 / 종료)
export class TitleScene extends Scene {
  constructor() { super(); this.t = 0; }

  async onEnter() {
    const [bgTex, heroTex] = await Promise.all([
      Assets.load("./assets/bg/award.png").catch(() => null),
      Assets.load("./assets/portraits/heroine_brown_idle.png").catch(() => null),
    ]);

    this.bg = new Sprite(bgTex || Assets.cache.get("./assets/bg/school.png"));
    this.bg.anchor.set(0.5, 0); this.addChild(this.bg);
    this.veil = new Graphics(); this.addChild(this.veil);

    if (heroTex) { this.hero = new Sprite(heroTex); this.hero.anchor.set(0.5, 1); this.addChild(this.hero); }

    // 타이틀
    this.titleWrap = new Container(); this.addChild(this.titleWrap);
    const glow = new Text({ text: "SPOTLIGHT", style: new TextStyle({ fontFamily: FD, fontSize: 78, fill: 0xfff4cf }) });
    glow.anchor.set(0.5); glow.alpha = 0.35; glow.scale.set(1.06);
    const title = new Text({ text: "SPOTLIGHT", style: new TextStyle({ fontFamily: FD, fontSize: 76, fill: GOLD, stroke: { color: 0x5b3d1a, width: 6 } }) });
    title.anchor.set(0.5);
    const sub = new Text({ text: "어느 배우의 40년", style: new TextStyle({ fontFamily: FD, fontSize: 26, fill: CREAM }) });
    sub.anchor.set(0.5); sub.position.set(0, 60);
    this.titleWrap.addChild(glow, title, sub); this._glow = glow;

    // 메뉴 버튼
    this.menu = new Container(); this.addChild(this.menu);
    const canLoad = hasSave();
    this._btnNew = this._button("🎬  새로 시작하기", GOLD, INK, () => this._promptName((name) => this.manager.change(new MainScene(new GameState(name)))));
    this._btnLoad = this._button(canLoad ? `📂  불러오기  (${saveLabel()})` : "📂  불러오기  (없음)", canLoad ? CREAM : 0xcfc6b8, canLoad ? INK : 0x8a8276, () => {
      const g = loadGame();
      if (g) this.manager.change(new MainScene(g)); else this._flash("저장된 게임이 없어요");
    });
    this._btnQuit = this._button("🚪  종료하기", CREAM, INK, () => this._quit());
    this.menu.addChild(this._btnNew, this._btnLoad, this._btnQuit);

    this.hint = new Text({ text: "한정된 3년, 당신의 선택이 어떤 배우를 만들까", style: new TextStyle({ fontFamily: FB, fontSize: 17, fill: 0xe7ddc7 }) });
    this.hint.anchor.set(0.5); this.addChild(this.hint);

    document.getElementById("loading")?.remove();
    this._layout(this.H || DESIGN_HEIGHT);
  }

  _button(label, fill, textColor, fn) {
    const c = new Container();
    const w = 460, h = 84;
    const g = new Graphics().roundRect(-w / 2, -h / 2, w, h, 22).fill(fill).stroke({ width: 3, color: 0x6b4a1e });
    const t = new Text({ text: label, style: new TextStyle({ fontFamily: FD, fontSize: 27, fill: textColor }) });
    t.anchor.set(0.5);
    c.addChild(g, t);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", fn);
    c.on("pointerover", () => { c.scale.set(1.04); });
    c.on("pointerout", () => { c.scale.set(1.0); });
    return c;
  }

  // 주인공 이름 입력 (DOM 오버레이 — 모바일 키보드 호출)
  _promptName(cb) {
    if (document.getElementById("name-prompt")) return;
    const wrap = document.createElement("div");
    wrap.id = "name-prompt";
    wrap.style.cssText = "position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;background:rgba(10,8,16,.74);";
    const box = document.createElement("div");
    box.style.cssText = "background:#1b1524;border:3px solid #f3c969;border-radius:20px;padding:26px 24px;width:82%;max-width:360px;text-align:center;font-family:GmarketSansBold,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.5);";
    box.innerHTML = '<div style="color:#f3c969;font-size:22px;margin-bottom:6px;">주인공 이름</div><div style="color:#cdbfa0;font-size:13px;font-family:sans-serif;margin-bottom:16px;">배우를 꿈꾸는 우리 주인공의 이름은?</div>';
    const input = document.createElement("input");
    input.type = "text"; input.maxLength = 8; input.placeholder = "소윤";
    input.style.cssText = "width:100%;box-sizing:border-box;font-size:20px;padding:12px 14px;border-radius:12px;border:2px solid #6b4a1e;text-align:center;font-family:inherit;outline:none;";
    const btn = document.createElement("button");
    btn.textContent = "시작하기";
    btn.style.cssText = "margin-top:18px;width:100%;font-size:20px;padding:12px;border:none;border-radius:14px;background:#f3c969;color:#2a2230;font-family:inherit;font-weight:bold;cursor:pointer;";
    box.appendChild(input); box.appendChild(btn); wrap.appendChild(box); document.body.appendChild(wrap);
    input.focus();
    const done = () => { const name = (input.value || "").trim().slice(0, 8) || "소윤"; wrap.remove(); cb(name); };
    btn.addEventListener("click", done);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") done(); });
  }

  _flash(msg) {
    if (this._flashNode) this._flashNode.destroy({ children: true });
    const c = new Container();
    const t = new Text({ text: msg, style: new TextStyle({ fontFamily: FD, fontSize: 22, fill: 0xffffff }) }); t.anchor.set(0.5);
    const w = t.width + 56, y = (this.H || DESIGN_HEIGHT) * 0.5;
    c.addChild(new Graphics().roundRect(DESIGN_WIDTH / 2 - w / 2, y - 30, w, 60, 16).fill({ color: 0x1a1420, alpha: 0.92 }).stroke({ width: 2, color: GOLD }));
    t.position.set(DESIGN_WIDTH / 2, y); c.addChild(t);
    this.addChild(c); this._flashNode = c; c._life = 110;
  }

  _quit() {
    const H = this.H || DESIGN_HEIGHT;
    const ov = new Container();
    ov.addChild(new Graphics().rect(0, 0, DESIGN_WIDTH, H).fill(0x0c0a12));
    const t = new Text({ text: "플레이해 주셔서 고맙습니다.\n창을 닫으셔도 됩니다.", style: new TextStyle({ fontFamily: FD, fontSize: 30, fill: GOLD, align: "center", lineHeight: 46 }) });
    t.anchor.set(0.5); t.position.set(DESIGN_WIDTH / 2, H / 2); ov.addChild(t);
    this.addChild(ov);
    try { window.close(); } catch (e) {}
  }

  _layout(H) {
    this.H = H;
    if (this.bg) {
      const tx = this.bg.texture;
      this.bg.scale.set(Math.max(DESIGN_WIDTH / tx.width, H / tx.height));
      this.bg.position.set(DESIGN_WIDTH / 2, 0);
    }
    if (this.veil) this.veil.clear().rect(0, 0, DESIGN_WIDTH, H).fill({ color: 0x140f1c, alpha: 0.5 });
    if (this.hero) {
      this.hero.scale.set(Math.min(1, (H * 0.52) / this.hero.texture.height));
      this.hero.position.set(DESIGN_WIDTH / 2, H * 0.74);
    }
    if (this.titleWrap) this.titleWrap.position.set(DESIGN_WIDTH / 2, H * 0.16);
    // 메뉴: 하단 엄지존
    const baseY = H * 0.62, gap = 104;
    if (this._btnNew) this._btnNew.position.set(DESIGN_WIDTH / 2, baseY);
    if (this._btnLoad) this._btnLoad.position.set(DESIGN_WIDTH / 2, baseY + gap);
    if (this._btnQuit) this._btnQuit.position.set(DESIGN_WIDTH / 2, baseY + gap * 2);
    if (this.hint) this.hint.position.set(DESIGN_WIDTH / 2, baseY + gap * 2 + 70);
  }

  resize(_w, h) { this._layout(h); }

  update(delta) {
    this.t += delta;
    if (this._glow) this._glow.alpha = 0.28 + Math.sin(this.t * 0.05) * 0.12;
    if (this._flashNode) { this._flashNode._life -= delta; this._flashNode.alpha = Math.min(1, this._flashNode._life / 30); if (this._flashNode._life <= 0) { this._flashNode.destroy({ children: true }); this._flashNode = null; } }
  }
}
