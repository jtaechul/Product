// 나레이션 상세(/nv/<id>)의 **편집 카드 1·2·3단계**가 실제로 렌더되고, 표지+구간이 **함께**
// 워크플로 입력으로 나가는지 확인하는 검사기(브라우저 없이).
//
// 왜 필요한가(실사고): "표지 + 구간 설정으로 다시 만들기"를 눌렀는데 **표지만 반영**됐다.
//   ①워크플로 따옴표 문제(백엔드)와 별개로, 화면이 두 값을 실제로 함께 담아 보내는지
//   ②구간을 프로그램이 채워도(사진 띠 탭·복원) 요약이 갱신되는지 — 렌더 확인만으론 못 잡는다.
//
// 사용: node worker/narrate_edit_check.mjs
import worker from "./index.mjs";

const REC = {
  id: "nv-test", kind: "narrate", mode: "shorts", body_dur: 30,
  source_url: "https://example.com/src.webm",
  applied: { cover: { at: 56, zoom: 1.0, x: 0.5, y: 0.5 },
             cuts: [{ start: 1.2, end: 8.4, zoom: 1.67 }], cuts_manual: true },
  edit: { cover: '{"at":56,"zoom":1,"x":0.5,"y":0.5}',
          cut_specs: '[{"start":1.2,"end":8.4,"zoom":1.67,"crop_x":0.5,"crop_y":0.5}]' },
  media: { video_url: "https://example.com/v.mp4", sheet: null },
};

const res = await worker.fetch(new Request("https://x/nv/nv-test"), {}, {});
const js = [...(await res.text()).matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

const els = {};
const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {},
  classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){}, querySelectorAll: () => [],
  insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, oninput: null,
  scrollIntoView(){}, load(){}, src: "", currentTime: 0, duration: 0, clientWidth: 320, clientHeight: 180,
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 320, height: 180 }) });
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
globalThis.confirm = () => true;

const run = new Function(js + "\n; return { renderNarrateDetail, BUILD, allEditInputs, ceSet, editSummary };");
const { renderNarrateDetail, BUILD, allEditInputs, ceSet } = run();
await renderNarrateDetail("nv-test");
const out = els["nvcard"]?.innerHTML || "";
const idx = s => out.indexOf(s);
const ok = b => (b ? "정상" : "★문제");

console.log("[배포 예정본 · 나레이션 /nv 편집 카드]");
console.log("  빌드 표시            :", BUILD);
console.log("  통합 카드            :", ok(idx('id="editstudio"') >= 0));
console.log("  1→2→3 순서          :",
  ok(idx('id="coverbox"') > 0 && idx('id="nvcutbox"') > idx('id="coverbox"')
     && idx('id="applyedits"') > idx('id="nvcutbox"')));
console.log("  영상 바로 아래 배치  :", ok(idx('id="editstudio"') < idx("이 나레이션 영상 관리")));
console.log("  적용 내역 표시       :", ok(out.includes("실제로 반영된 설정") && out.includes("1.2~8.4초")));
console.log("  쇼츠 썸네일 버튼 없음:", ok(idx('id="cvthumb"') < 0));

// ── 동작: 지난 설정 복원 → 표지·구간이 **둘 다** 입력으로 나가는가
const restored = allEditInputs("nc");
console.log("\n[동작 · 지난 설정 복원 후 보내지는 값]");
console.log("  표지                 :", restored.cover || "(없음)");
console.log("  구간                 :", restored.cut_specs || "(없음)");
console.log("  둘 다 전달           :", ok(!!restored.cover && !!restored.cut_specs));
console.log("  표지 안내문          :", els["cvinfo"]?.innerHTML.replace(/<[^>]+>/g, ""));
console.log("  반영 요약            :", els["applysum"]?.innerHTML.replace(/<[^>]+>/g, ""));

// ── 동작: 코드가 값을 채워도(사진 띠 탭 = ceSet) 요약이 따라오는가
ceSet("nc", 1, "a", 12.0); ceSet("nc", 1, "b", 20.0);
const after = allEditInputs("nc");
console.log("\n[동작 · 사진 띠 탭처럼 코드가 칸을 채운 뒤]");
console.log("  컷 수                :", JSON.parse(after.cut_specs || "[]").length);
console.log("  요약 자동 갱신       :", ok((els["applysum"]?.innerHTML || "").includes("2컷")));
console.log("  요약 내용            :", els["applysum"]?.innerHTML.replace(/<[^>]+>/g, ""));
