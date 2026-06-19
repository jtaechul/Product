import { Assets, Sprite, Graphics, Text, TextStyle, Container } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { hasSave, loadGame, saveLabel } from "../systems/save.js";
import { GameState } from "../systems/game.js";
import { MainScene } from "./MainScene.js";

const FD = "GmarketSansBold, sans-serif";
const FB = "KoPubWorldDotumMedium, sans-serif";
const GOLD = 0xf3c969, CREAM = 0xfdf6e6, INK = 0x241a10;

// 오프닝 (기획서: 새로 시작 / 불러오기 / 종료). 배경은 무대 일러스트(타이틀·인물 포함), 버튼/글자는 코드로.
export class TitleScene extends Scene {
  constructor() { super(); this.t = 0; }

  async onEnter() {
    const tex = {};
    await Promise.all(
      ["title_bg", "icon_new", "icon_load", "icon_quit"].map(async (n) => { tex[n] = await Assets.load(`./assets/ui/${n}.png`).catch(() => null); })
    );
    this.tex = tex;

    this.bg = new Sprite(tex.title_bg); this.bg.anchor.set(0.5, 0); this.addChild(this.bg);

    // 메뉴 버튼
    this.menu = new Container(); this.addChild(this.menu);
    const canLoad = hasSave();
    this._btnNew = this._button("새로 시작하기", GOLD, INK, tex.icon_new, () => this._promptName((name) => this.manager.change(new MainScene(new GameState(name)))));
    this._btnLoad = this._button(canLoad ? `불러오기  (${saveLabel()})` : "불러오기  (없음)", canLoad ? CREAM : 0xb8ae94, canLoad ? INK : 0x6f6655, tex.icon_load, () => {
      const g = loadGame();
      if (g) this.manager.change(new MainScene(g)); else this._flash("저장된 게임이 없어요");
    });
    this._btnQuit = this._button("종료하기", CREAM, INK, tex.icon_quit, () => this._quit());
    this.menu.addChild(this._btnNew, this._btnLoad, this._btnQuit);

    this.sub = new Text({ text: "어느 배우의 40년", style: new TextStyle({ fontFamily: FD, fontSize: 22, fill: GOLD, stroke: { color: 0x231a2c, width: 4 } }) });
    this.sub.anchor.set(0.5); this.addChild(this.sub);

    document.getElementById("loading")?.remove();
    this._layout(this.H || DESIGN_HEIGHT);
  }

  _button(label, fill, textColor, iconTex, fn) {
    const c = new Container();
    const w = 470, h = 86;
    c.addChild(new Graphics().roundRect(-w / 2, -h / 2, w, h, 22).fill({ color: 0x1a2138, alpha: 0.92 }).stroke({ width: 3, color: 0x6b4a1e }));
    c.addChild(new Graphics().roundRect(-w / 2 + 5, -h / 2 + 5, w - 10, h - 10, 18).stroke({ width: 1.5, color: GOLD }));
    if (iconTex) {
      const ic = new Sprite(iconTex); ic.anchor.set(0.5);
      ic.scale.set(52 / Math.max(iconTex.width, iconTex.height));
      ic.position.set(-w / 2 + 48, 0); c.addChild(ic);
    }
    const t = new Text({ text: label, style: new TextStyle({ fontFamily: FD, fontSize: 27, fill }) });
    t.anchor.set(0, 0.5); t.position.set(-w / 2 + 92, 0); c.addChild(t);
    c.eventMode = "static"; c.cursor = "pointer";
    c.on("pointertap", fn);
    c.on("pointerover", () => c.scale.set(1.035));
    c.on("pointerout", () => c.scale.set(1.0));
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
    const baseY = H * 0.64, gap = H * 0.086;
    if (this._btnNew) this._btnNew.position.set(DESIGN_WIDTH / 2, baseY);
    if (this._btnLoad) this._btnLoad.position.set(DESIGN_WIDTH / 2, baseY + gap);
    if (this._btnQuit) this._btnQuit.position.set(DESIGN_WIDTH / 2, baseY + gap * 2);
    if (this.sub) this.sub.position.set(DESIGN_WIDTH / 2, baseY + gap * 2 + H * 0.05);
  }

  resize(_w, h) { this._layout(h); }

  update(delta) {
    this.t += delta;
    if (this._flashNode) { this._flashNode._life -= delta; this._flashNode.alpha = Math.min(1, this._flashNode._life / 30); if (this._flashNode._life <= 0) { this._flashNode.destroy({ children: true }); this._flashNode = null; } }
  }
}
