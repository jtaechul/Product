// 상세 페이지에 '구간·줌 편집 메뉴'가 실제로 렌더되는지 확인하는 검사기(브라우저 없이).
//
// 왜 필요한가(실사고): 소스 파일에 코드가 있고 서빙 HTML에 문자열이 들어 있어도, **renderDetail이
// 실제로 그 조각을 그리는지**는 별개다. 운영자가 "메뉴가 아예 없다"고 했을 때 소스·문자열만 보고
// '있다'고 답했다가 헛다리를 짚었다 → 워커가 내려주는 스크립트를 그대로 실행해 렌더 결과를 본다.
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
  insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, scrollIntoView(){}, load(){}, src: "" });
globalThis.window = { location: { pathname: "/c/048" } };
globalThis.location = window.location;
globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
  querySelectorAll: () => [], addEventListener(){} };
globalThis.fetch = async u => {
  const url = String(u).startsWith("http") ? String(u) : "https://shorts-dashboard.jtaechul.workers.dev" + u;
  try { const out = execFileSync("curl", ["-s", url], { maxBuffer: 1e8 }).toString();
    return { ok: true, status: 200, text: async () => out, json: async () => JSON.parse(out) }; }
  catch { return { ok: false, status: 500, text: async () => "", json: async () => ({}) }; }
};
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.setTimeout = () => 0;

const run = new Function(js + "\n; return { renderDetail, BUILD };");
const { renderDetail, BUILD } = run();
await renderDetail("048");
const out = els["dcard"]?.innerHTML || "";
const has = s => (out.includes(s) ? "있음" : "없음");
console.log("[배포 예정본 · 도감형 /c/048 실제 렌더]");
console.log("  빌드 표시            :", BUILD);
console.log("  버튼그리드 진입버튼  :", has("구간·줌 직접 지정해서 다시 만들기"));
console.log("  편집 카드(항상 표시) :", has("구간·줌 직접 지정 — 내가 정해서 다시 만들기"));
console.log("  컷별 탭(1~4)        :", has("data-cetab"));
console.log("  프레임 사진 스트립   :", has("구간 고르기"));
console.log("  크롭 사각형          :", has("cebox") || has("ncbox") ? "있음" : "없음");
console.log("  줌 슬라이더          :", has('type="range"'));
console.log("  실행 버튼            :", has("이 설정으로 다시 만들기"));
console.log("  접힘 여부            :", out.includes('<details class="tok" id="cutbox"') ? "접힘(문제)" : "항상 표시(정상)");
console.log("  렌더 길이            :", out.length);
