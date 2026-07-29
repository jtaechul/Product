// 화면에 그린 사각형 == 제작이 실제로 잘라내는 사각형 인지 확인(브라우저 없이).
//
// 왜 필요한가(실사고 · 운영자 지적 "지정한 곳과 전혀 다른 곳이 제작된다"):
//   편집기는 사각형을 **가로 폭** 기준으로 그리고 줌을 1/폭으로 보냈는데, 제작(reframe)은
//   **높이** 기준('잘라낼 높이 = 원본 높이 ÷ 줌')으로 자른다 → 그린 것과 잘린 것이 완전히 달랐다.
//   이 검사기는 편집기가 실제로 그린 상자(px)를 원본 좌표로 되돌려, 제작이 계산할 크롭 사각형과
//   같은지 비교한다. 두 값이 어긋나면 즉시 드러난다.
//
// 사용: node worker/crop_wysiwyg_check.mjs   (JSON 한 줄 출력 — 파이썬 테스트가 읽는다)
import worker from "./index.mjs";

const SRC_W = 1280, SRC_H = 720;          // 원본(16:9)
const OUT_W = 720, OUT_H = 1280;          // 완성본(9:16)
const STAGE_W = 320, STAGE_H = Math.round(STAGE_W * SRC_H / SRC_W);   // 편집기 스테이지(원본 비율)

const REC = {
  id: "nv-test", kind: "narrate", mode: "shorts", body_dur: 30,
  source_url: "https://example.com/src.webm",
  media: { video_url: "https://example.com/v.mp4",
           sheet: { url: "https://example.com/sheet.jpg", cols: 5, rows: 2, n: 10,
                    step: 3, tw: 480, th: 270 } },
};

const res = await worker.fetch(new Request("https://x/nv/nv-test"), {}, {});
const js = [...(await res.text()).matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

const els = {};
const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {},
  classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){}, querySelectorAll: () => [],
  insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, oninput: null,
  scrollIntoView(){}, load(){}, src: "", currentTime: 0, duration: 0,
  clientWidth: STAGE_W, clientHeight: STAGE_H,
  getBoundingClientRect: () => ({ left: 0, top: 0, width: STAGE_W, height: STAGE_H }) });
const rendered = () => Object.values(els).map(e => e.innerHTML).join("\n");
const qsa = sel => {
  const m = sel.match(/^\[data-mk\^='(.+)'\]$/);
  if (m) return [...rendered().matchAll(/data-mk="([^"]+)"/g)].map(x => x[1])
    .filter(v => v.startsWith(m[1])).map(v => { const e = el("btn:" + v); e.dataset.mk = v; return e; });
  if (sel === "[data-cesel]") return [...rendered().matchAll(/data-cesel="([^"]+)"/g)].map(x => x[1])
    .map(v => { const e = el("sel:" + v); e.dataset.cesel = v; return e; });
  return [];
};
globalThis.window = { location: { pathname: "/nv/nv-test" } };
globalThis.location = window.location;
globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
  querySelectorAll: qsa, addEventListener(){} };
globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => REC,
  text: async () => JSON.stringify(REC) });
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.setTimeout = () => 0;

const run = new Function(js + "\n; return { renderNarrateDetail, ceState, ceSet, ceDrawBox, cutEditorInputs };");
const { renderNarrateDetail, ceState, ceSet, ceDrawBox, cutEditorInputs } = run();
await renderNarrateDetail("nv-test");

// 운영자가 컷1에 구간을 넣고, 사각형을 왼쪽 위로 옮긴 뒤 크기를 줄인 상황
const cases = [
  { x: 0.50, y: 0.50, h: 1.00, fit: "cover" },   // 꽉 채우기 · 높이 전체
  { x: 0.25, y: 0.50, h: 0.60, fit: "cover" },   // 꽉 채우기 · 왼쪽 중간 크기
  { x: 0.80, y: 0.30, h: 0.45, fit: "cover" },   // 꽉 채우기 · 오른쪽 위 확대
  { x: 0.50, y: 0.50, h: 1.00, fit: "square" },  // 정방형 · 전체
  { x: 0.30, y: 0.40, h: 0.70, fit: "square" },  // 정방형 · 왼쪽 위
  { x: 0.50, y: 0.50, h: 1.00, fit: "full" },    // 좌우 전체
  { x: 0.50, y: 0.45, h: 0.75, fit: "full" },    // 좌우 전체 · 살짝 확대
];
const out = [];
for (const c of cases) {
  const st = ceState("nc");
  st.sel = 0;
  st.cuts[0].fit = c.fit || "cover";        // ★화면 구성은 컷마다
  st.cuts[0].box = { x: c.x, y: c.y, h: c.h };
  ceSet("nc", 0, "a", 2.0); ceSet("nc", 0, "b", 9.0);
  ceDrawBox("nc");
  const b = els["ncbox"].style;                       // 화면에 실제로 그려진 사각형(px)
  const px = v => parseFloat(String(v).replace("px", ""));
  const spec = JSON.parse(cutEditorInputs("nc").cut_specs)[0];
  out.push({
    state: c,
    // 화면 사각형 → 원본 좌표(스테이지는 원본 비율이므로 단순 비례)
    drawn: { x: px(b.left) * SRC_W / STAGE_W, y: px(b.top) * SRC_H / STAGE_H,
             w: px(b.width) * SRC_W / STAGE_W, h: px(b.height) * SRC_H / STAGE_H },
    sent: { zoom: spec.zoom, crop_x: spec.crop_x, crop_y: spec.crop_y,
            fit: spec.fit || "cover" },       // 컷 지정 안에 담겨 나가는 값
  });
}
// ★컷마다 다른 화면 구성(운영자 확정): 컷1 꽉 채우기 · 컷2 정방형 · 컷3 좌우 전체를 동시에.
const stx = ceState("nc");
const mixed = ["cover", "square", "full", "cover"];
mixed.forEach((f, i) => { stx.cuts[i].fit = f; stx.cuts[i].box = { x: 0.5, y: 0.5, h: 0.8 };
                          ceSet("nc", i, "a", 1 + i * 5); ceSet("nc", i, "b", 5 + i * 5); });
const perCut = JSON.parse(cutEditorInputs("nc").cut_specs).map(c => c.fit);

console.log(JSON.stringify({ src: [SRC_W, SRC_H], out: [OUT_W, OUT_H], cases: out,
                             perCut, perCutWant: mixed }));
