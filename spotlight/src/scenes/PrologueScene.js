import { Assets, Sprite, Graphics, Text, TextStyle, Container } from "pixi.js";
import { Scene } from "../core/Scene.js";
import { DESIGN_WIDTH, DESIGN_HEIGHT } from "../config.js";
import { armBgm, stopBgm } from "../systems/sound.js";
import { BONDS } from "../data/bonds.js";
import { MainScene } from "./MainScene.js";

const FD = "GmarketSansBold, sans-serif";
const FB = "KoPubWorldDotumMedium, sans-serif";
const GOLD = 0xf3c969;

// 프롤로그 (이름 입력 후 ~ 본 게임 전): 배우를 꿈꾸게 된 배경 + 고교 입학 결의
export class PrologueScene extends Scene {
  constructor(game) { super(); this.game = game; this.idx = 0; }

  _pages() {
    const name = this.game?.heroName || "소윤";
    return [
      { bg: "home",   text: "어릴 적, 텔레비전 속 어느 배우의 한 장면에 마음이 멈췄다.\n\"나도… 누군가의 마음을 저렇게 흔들 수 있을까?\"" },
      { bg: "school", char: "hanjiwon", who: "한지원 · 매니저", text: "\"안녕. 난 한지원, 작은 소속사의 매니저야.\n…네 안에, 분명 빛나는 무언가가 보여. 배우, 해볼 생각 없니?\"" },
      { bg: "stage",  text: "그 한마디가 오래도록 마음에 남았다.\n나는 — 배우가 되기로 마음먹었다." },
      { bg: "school", text: `그리고 오늘, 고등학교 입학식.\n교복을 입은 ${name} — 거울 앞에서 마음을 다잡는다.` },
      { bg: "academy", char: "noh", who: "노교수 · 연기 선생", text: "\"연기는 재능이 아니라 태도다.\n기초부터 차근차근. 게으름은 용납 안 한다, 알겠지?\"" },
      { bg: "school", char: "haneul", who: "박하늘 · 단짝 친구", text: "\"우리 같은 반이네! 난 박하늘.\n앞으로 친하게 지내자—힘들 땐 내가 옆에 있어줄게!\"" },
      { bg: "stage",  char: "yusea", who: "유세아 · 라이벌", text: "\"너도 배우 지망생? …흥, 재밌겠네.\n난 유세아. 미리 말해두는데, 난 누구한테도 안 져.\"" },
      { bg: "stage",  text: "앞으로의 3년. 연기도, 공부도, 사람도 놓치지 않겠다.\n스포트라이트가 나를 비추는 그날까지." },
    ];
  }

  async onEnter() {
    this.pages = this._pages();
    // 인연 인물 이미지 미리 로드
    await Promise.all(BONDS.map(async (b) => { this.charTex = this.charTex || {}; try { this.charTex[b.id] = await Assets.load(b.img); } catch (e) {} }));
    this.bg = new Sprite(); this.bg.anchor.set(0.5, 0); this.addChild(this.bg);
    this.veil = new Graphics(); this.addChild(this.veil);
    this.charC = new Container(); this.addChild(this.charC);

    // 본문 박스
    this.box = new Graphics(); this.addChild(this.box);
    this.story = new Text({ text: "", style: new TextStyle({ fontFamily: FD, fontSize: 27, fill: 0xfdf6e6, align: "center", lineHeight: 40, stroke: { color: 0x1a1018, width: 4 } }) });
    this.story.anchor.set(0.5); this.addChild(this.story);
    this.who = new Text({ text: "", style: new TextStyle({ fontFamily: FD, fontSize: 21, fill: GOLD, stroke: { color: 0x1a1018, width: 4 } }) });
    this.who.anchor.set(0.5, 0); this.addChild(this.who);
    this.tip = new Text({ text: "화면을 누르면 계속 ▶", style: new TextStyle({ fontFamily: FB, fontSize: 16, fill: 0xcfc7d0 }) });
    this.tip.anchor.set(1, 1); this.addChild(this.tip);

    // 건너뛰기
    this.skip = new Container();
    this.skip.addChild(new Graphics().roundRect(0, 0, 120, 44, 14).fill({ color: 0x1a1420, alpha: 0.7 }).stroke({ width: 2, color: GOLD }));
    const st = new Text({ text: "건너뛰기", style: new TextStyle({ fontFamily: FD, fontSize: 18, fill: 0xfdf6e6 }) }); st.anchor.set(0.5); st.position.set(60, 22); this.skip.addChild(st);
    this.skip.eventMode = "static"; this.skip.cursor = "pointer"; this.skip.on("pointertap", (e) => { e.stopPropagation?.(); this._finish(); });
    this.addChild(this.skip);

    this.eventMode = "static";
    this.on("pointertap", () => this._next());

    armBgm("./assets/sfx/title_bgm.mp3", 0.55); // 프롤로그까지 타이틀 BGM 유지
    await this._show();
    this._layout(this.H || DESIGN_HEIGHT);
  }

  onExit() { stopBgm(); super.onExit(); }

  async _show() {
    const p = this.pages[this.idx];
    try { this.bg.texture = await Assets.load(`./assets/bg/${p.bg}.png`); } catch (e) {}
    this.story.text = p.text;
    this.who.text = p.who || "";
    this.charC.removeChildren();
    if (p.char && this.charTex && this.charTex[p.char]) {
      const sp = new Sprite(this.charTex[p.char]); sp.anchor.set(0.5, 1.0); sp._char = true; this.charC.addChild(sp);
    }
    this._layout(this.H || DESIGN_HEIGHT);
  }
  _next() { this.idx += 1; if (this.idx >= this.pages.length) this._finish(); else this._show(); }
  _finish() { this.manager.change(new MainScene(this.game)); }

  _layout(H) {
    this.H = H;
    if (this.bg && this.bg.texture && this.bg.texture.width) {
      const t = this.bg.texture; this.bg.scale.set(Math.max(DESIGN_WIDTH / t.width, H / t.height)); this.bg.position.set(DESIGN_WIDTH / 2, 0);
    }
    if (this.veil) this.veil.clear().rect(0, 0, DESIGN_WIDTH, H).fill({ color: 0x100b16, alpha: 0.55 });
    const boxY = H * 0.62, boxH = H * 0.3;
    // 인연 인물 (본문 박스 위쪽에 가슴까지 보이도록)
    if (this.charC && this.charC.children[0]) {
      const sp = this.charC.children[0]; sp.scale.set((H * 0.62) / sp.texture.height); sp.position.set(DESIGN_WIDTH / 2, boxY + 20);
    }
    if (this.box) this.box.clear().roundRect(40, boxY, DESIGN_WIDTH - 80, boxH, 24).fill({ color: 0x140f1a, alpha: 0.82 }).stroke({ width: 2, color: GOLD });
    if (this.who) this.who.position.set(DESIGN_WIDTH / 2, boxY + 14);
    if (this.story) { this.story.style.wordWrapWidth = DESIGN_WIDTH - 140; this.story.style.wordWrap = true; this.story.position.set(DESIGN_WIDTH / 2, boxY + boxH * 0.58); }
    if (this.tip) this.tip.position.set(DESIGN_WIDTH - 44, boxY + boxH - 14);
    if (this.skip) this.skip.position.set(DESIGN_WIDTH - 140, 40);
  }

  resize(_w, h) { this._layout(h); }
}
