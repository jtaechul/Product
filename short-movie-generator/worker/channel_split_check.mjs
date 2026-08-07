// 상세 화면(/c/<id>)의 업로드 카드가 **올라갈 채널**을 실제로 표기하는지 확인(브라우저 없이).
// 난파선(shipwreck) 레코드와 생물(deep_sea) 레코드를 각각 렌더해 문구가 갈리는지 본다.
import worker from "./index.mjs";

const res = await worker.fetch(new Request("https://x/"), {}, {});
const js = [...(await res.text()).matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

const els = {};
const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {},
  classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){}, querySelectorAll: () => [],
  insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, getAttribute: () => null });
globalThis.window = { location: { pathname: "/" } }; globalThis.location = window.location;
globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
  querySelectorAll: () => [], addEventListener(){}, createElement: () => ({}) };
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.setTimeout = (f) => { try { if (typeof f === "function") f(); } catch (e) {} return 0; };

function record(category) {
  return { id: "999", category, species: { common_name_ko: "테스트", common_name_en: "Test" },
    reels: { caption: "", hashtags: [] },
    media: { video_url: "https://example.invalid/v.mp4", rev: "r1" }, source: {} };
}
let CUR = record("deep_sea");
globalThis.fetch = async () => ({ ok: true, status: 200,
  text: async () => JSON.stringify(CUR), json: async () => CUR });

const api = new Function(js + "\n; return { renderDetail };").call(null);

async function render(category) {
  CUR = record(category);
  els["dcard"] = undefined; delete els["dcard"];
  els["view"] = undefined; delete els["view"];
  await api.renderDetail("999");
  for (let i = 0; i < 20; i++) await new Promise(r => queueMicrotask(r));
  return el("dcard").innerHTML;
}

const bio = await render("deep_sea");
const wreck = await render("shipwreck");
console.log(JSON.stringify({
  bioHasChannelLine: bio.includes("올라갈 채널"),
  bioChannel: /올라갈 채널: <b>([^<]*)<\/b>/.exec(bio)?.[1] || "",
  wreckHasChannelLine: wreck.includes("올라갈 채널"),
  wreckChannel: /올라갈 채널: <b>([^<]*)<\/b>/.exec(wreck)?.[1] || "",
  wreckHasWarning: wreck.includes("전용 채널 미연결"),
  bioHasWarning: bio.includes("전용 채널 미연결"),
}));
