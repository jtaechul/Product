// 소싱 인벤토리에 **바로 제작 가능한 종**이 실제로 나오는지 확인(브라우저 없이).
// 운영자 지적: 확보한 영상이 별도 메뉴가 아니라 인벤토리에 들어가 바로 제작돼야 한다.
import { readFileSync } from "node:fs";
import worker from "./index.mjs";
const DISC = JSON.parse(readFileSync(new URL("../src/categories/deep_sea/discovered.json", import.meta.url)));
const res = await worker.fetch(new Request("https://x/"), {}, {});
const js = [...(await res.text()).matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");
const els = {};
const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {},
  classList:{toggle(){},add(){},remove(){}}, addEventListener(){}, querySelectorAll: () => [],
  insertAdjacentHTML(_p,h){this.innerHTML+=h;}, onclick:null, getAttribute:()=>null });
globalThis.window={location:{pathname:"/"}}; globalThis.location=window.location;
globalThis.document={getElementById:el,querySelector:s=>el(s.replace(/^#/,"")),
  querySelectorAll:()=>[],addEventListener(){},createElement:()=>({})};
globalThis.fetch=async(u)=>{const s=String(u);
  const body = s.includes("discovered.json") ? JSON.stringify(DISC) : "[]";
  return {ok:true,status:200,text:async()=>body,json:async()=>JSON.parse(body)};};
globalThis.localStorage={getItem:()=>null,setItem(){},removeItem(){}};
globalThis.setTimeout=(f)=>{try{if(typeof f==="function")f();}catch(e){}return 0;};
const api=new Function(js+"\n; return { loadCandidates, srcState:()=>({open:_srcOpen,shown:_srcShown}), srcOpen:(v)=>{_srcOpen=v;} };").call(null);
// ① 기본은 접힘 — 카드가 하나도 그려지지 않아야 한다(스크롤을 잡아먹지 않게)
await api.loadCandidates("deep_sea");
for(let i=0;i<20;i++) await new Promise(r=>queueMicrotask(r));
const collapsedHtml=el("srccands").innerHTML;
// ② 펼치면 일부만 + '더 보기'
api.srcOpen(true);
await api.loadCandidates("deep_sea");
for(let i=0;i<20;i++) await new Promise(r=>queueMicrotask(r));
const h=el("srccands").innerHTML;
const ready=DISC.filter(d=>d&&d.footage&&d.footage.url).length;
console.log(JSON.stringify({
  collapsedCards: (collapsedHtml.match(/class="ccard"/g)||[]).length,
  collapsedHasToggle: collapsedHtml.includes("펼치기"),
  hasMoreLink: h.includes("더 보기"),
  thumbPlaceholders: (h.match(/썸네일 생성 중/g)||[]).length,
  thumbMedia: (h.match(/class="cthumb"/g)||[]).length,
  readyInFile: ready,
  cardsShown: (h.match(/class="ccard"/g)||[]).length,
  readyBadges: (h.match(/확보 완료 · 바로 제작/g)||[]).length,
  hasMakeButton: (h.match(/이 대상으로 제작/g)||[]).length,
  tabCount: (h.match(/영상\+이미지 확보 <b>(\d+)<\/b>/)||[])[1]||"",
}));
