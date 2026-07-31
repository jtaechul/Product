// '확보 영상' 목록 화면이 **실제로 28건을 그리는지** 브라우저 없이 확인한다.
//
// 왜: 운영자가 "확보했다"는 말만 듣고는 확인할 방법이 없었다(제작 로그에만 찍혔다).
//   이 화면은 저장소의 src/data/noaa_clips.json — **제작이 읽는 바로 그 파일** — 을 그대로 보여준다.
//   따라서 화면에 뜬 건수/이름 = 실제 제작에 쓰이는 목록. 이 검사기가 그 등식을 확인한다.
//
// 사용: node worker/clips_page_check.mjs   (JSON 한 줄 출력 — 파이썬 테스트가 읽는다)
import { readFileSync } from "node:fs";
import worker from "./index.mjs";

const DATA = JSON.parse(readFileSync(new URL("../src/data/noaa_clips.json", import.meta.url)));

const res = await worker.fetch(new Request("https://x/clips"), {}, {});
const js = [...(await res.text()).matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

const els = {};
const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {},
  classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){}, querySelectorAll: () => [],
  insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null });
globalThis.window = { location: { pathname: "/clips" } };
globalThis.location = window.location;
globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
  querySelectorAll: () => [], addEventListener(){}, createElement: () => ({}) };
let asked = "";
globalThis.fetch = async (u) => {
  asked = String(u);
  return { ok: true, status: 200, text: async () => JSON.stringify(DATA),
           json: async () => DATA };
};
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.setTimeout = (f) => { try { if (typeof f === "function") f(); } catch (e) {} return 0; };

const run = new Function(js + "\n; return { renderClips };");
await run().renderClips();
for (let i = 0; i < 10; i++) await new Promise(r => queueMicrotask(r));

const html = el("view").innerHTML;
const shown = (html.match(/<video /g) || []).length;
console.log(JSON.stringify({
  fetched: asked,
  expected: DATA.clips.length,
  videos: shown,
  headerCount: (html.match(/영상 — (\d+)건/) || [])[1] || "",
  hasCredit: html.includes(DATA.credit),
  saysPublicDomain: html.includes("퍼블릭도메인"),
  showsMeasurements: html.includes("움직임"),
  linksToSource: (html.match(/NOAA 원본 페이지 열기/g) || []).length,
  proxied: (html.match(/\/api\/media\?u=/g) || []).length,
}));
