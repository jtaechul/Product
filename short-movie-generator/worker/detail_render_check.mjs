// 상세 페이지의 '구간·줌 편집 메뉴'가 실제로 렌더되고 **동작하는지** 확인하는 검사기(브라우저 없이).
//
// 왜 필요한가(실사고 2건):
//  ① 소스에 코드가 있어도 renderDetail이 그걸 그리는지는 별개다 → 워커가 내려주는 스크립트를 실행해
//     렌더 결과를 본다.
//  ② "여기 시작/여기 끝을 눌러도 칸이 안 채워진다" → 렌더만 확인하면 못 잡는다. 그래서 **버튼을
//     실제로 눌러(handler 호출) 입력칸 값이 채워지는지**까지 검사한다.
//
// 사용: node worker/detail_render_check.mjs   (네트워크로 실제 레코드를 읽는다)
import { execFileSync } from "node:child_process";
import worker from "./index.mjs";

// 워커가 실제로 내려보내는 HTML을 그대로 받는다(테스트 가드와 동일 경로)
const res = await worker.fetch(new Request("https://x/c/048"), {}, {});
const html = await res.text();
const js = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

const els = {};
const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {},
  classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){}, querySelectorAll: () => [],
  insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, scrollIntoView(){}, load(){},
  src: "", currentTime: 0, duration: 0, getBoundingClientRect: () => ({left:0,top:0,width:320,height:180}) });
// 렌더된 HTML에서 속성 선택자([data-mk^='ce'] / [data-cesel])에 해당하는 요소를 되돌려준다.
// ★같은 선택자를 두 번 부르면 **같은 객체**를 줘야 한다(핸들러가 붙었는지 확인 가능).
const rendered = () => Object.values(els).map(e => e.innerHTML).join("\n");
const qsa = sel => {
  let m = sel.match(/^\[data-mk\^='(.+)'\]$/);
  if (m) {
    const pfx = m[1];
    return [...rendered().matchAll(/data-mk="([^"]+)"/g)].map(x => x[1])
      .filter(v => v.startsWith(pfx))
      .map(v => { const e = el("btn:" + v); e.dataset.mk = v; return e; });
  }
  if (sel === "[data-cesel]") {
    return [...rendered().matchAll(/data-cesel="([^"]+)"/g)].map(x => x[1])
      .map(v => { const e = el("sel:" + v); e.dataset.cesel = v; return e; });
  }
  return [];
};
globalThis.window = { location: { pathname: "/c/048" } };
globalThis.location = window.location;
globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
  querySelectorAll: qsa, addEventListener(){} };
globalThis.fetch = async u => {
  const url = String(u).startsWith("http") ? String(u) : "https://shorts-dashboard.jtaechul.workers.dev" + u;
  try { const out = execFileSync("curl", ["-s", url], { maxBuffer: 1e8 }).toString();
    return { ok: true, status: 200, text: async () => out, json: async () => JSON.parse(out) }; }
  catch { return { ok: false, status: 500, text: async () => "", json: async () => ({}) }; }
};
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.setTimeout = () => 0;

const run = new Function(js + "\n; return { renderDetail, BUILD, cutEditorInputs, allEditInputs, cvState, cvDraw };");
const { renderDetail, BUILD, cutEditorInputs, allEditInputs, cvState, cvDraw } = run();
await renderDetail("048");
const out = els["dcard"]?.innerHTML || "";
const has = s => (out.includes(s) ? "있음" : "없음");
console.log("[배포 예정본 · 도감형 /c/048 실제 렌더]");
console.log("  빌드 표시            :", BUILD);
console.log("  버튼그리드 진입버튼  :", has("표지·구간 직접 지정해서 다시 만들기"));
console.log("  편집 카드(항상 표시) :", has("영상 직접 고쳐 만들기"));
console.log("  1단계 표지 편집기    :", has('id="coverbox"') === "있음" && has('id="cvat"') === "있음" ? "있음" : "없음");
console.log("  화면 구성 선택       :", has("data-fit="));
console.log("  컷별 시작·끝 입력칸  :", has('id="ce0a"') === "있음" && has('id="ce3b"') === "있음" ? "있음(4컷)" : "없음");
console.log("  여기 시작/끝 버튼    :", has("여기 시작"));
console.log("  필요 총 길이 표시칸  :", has('id="ceneed"'));
console.log("  프레임 사진 스트립   :", has("사진 띠"));
console.log("  크롭 사각형          :", has('id="cebox"'));
console.log("  줌 슬라이더          :", has('type="range"'));
console.log("  실행 버튼(통합)      :", has('id="applyedits"'));
console.log("  접힘 여부            :", out.includes('<details class="tok" id="cutbox"') ? "접힘(문제)" : "항상 표시(정상)");

// 비동기 배선(소싱 캐시를 읽은 뒤 bindCutEditor 실행)이 끝나길 기다린다
for (let i = 0; i < 50; i++) await new Promise(r => setImmediate(r));

// ── 동작 검사: 영상을 12.3초에 두고 '여기 시작', 27.5초에 '여기 끝'을 실제로 눌러 본다 ──
const vid = el("cevid"); vid.currentTime = 12.3; vid.duration = 122.5;
const btns = qsa("[data-mk^='ce']");
const bA = btns.find(b => b.dataset.mk === "ce0a"), bB = btns.find(b => b.dataset.mk === "ce0b");
console.log("\n[동작 검사 · 여기 시작/여기 끝 → 칸 채워지는가]");
console.log("  버튼 개수(4컷×2)     :", btns.length);
console.log("  핸들러 연결          :", bA && typeof bA.onclick === "function" ? "됨" : "안 됨(문제)");
if (bA && bA.onclick) bA.onclick();
vid.currentTime = 27.5;
if (bB && bB.onclick) bB.onclick();
console.log("  컷1 시작 칸          :", el("ce0a").value || "(빈칸 · 문제)");
console.log("  컷1 끝 칸            :", el("ce0b").value || "(빈칸 · 문제)");
console.log("  필요 길이 안내       :", (el("ceneed").innerHTML || "").replace(/<[^>]+>/g, ""));
console.log("  워크플로 입력값      :", JSON.stringify(cutEditorInputs("ce")));

// ── 동작 검사 · 표지(오프닝 훅) + 구간이 **함께** 제작으로 나가는가(도감형)
const cvat = el("cvat"); cvat.value = "18.5";
const cst = cvState(); cst.at = 18.5; cst.box = { x: 0.4, y: 0.55, h: 0.7 };
cvDraw();
const all = allEditInputs("ce");
console.log("\n[동작 검사 · 도감형 표지+구간 동시 전달]");
console.log("  표지                 :", all.cover || "(없음)");
console.log("  구간                 :", all.cut_specs ? "있음(" + JSON.parse(all.cut_specs).length + "컷)" : "(없음)");
console.log("  둘 다 전달           :", (all.cover && all.cut_specs) ? "정상" : "★문제");
console.log("  반영 요약            :", (els["applysum"] || {}).innerHTML?.replace(/<[^>]+>/g, "") || "(없음)");
