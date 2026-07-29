// 편집기 두 가지를 브라우저 없이 확인한다(실제 서빙 스크립트를 그대로 실행).
//
//  ① 표지(오프닝 훅)도 **화면 구성 3종**(꽉 채우기·정방형·좌우 전체)을 고를 수 있는가
//     — 고른 모양대로 사각형 비율이 바뀌고, 워크플로로 보내는 값(cover JSON)에 fit이 담기는가.
//
//  ② 원본 재생 중 **playhead가 끌려다니지 않는가**(실사고 · 운영자 지적:
//     "재생 중에 다른 버튼을 누르거나 다른 구간으로 옮겨도 0.5초 구간만 계속 반복된다").
//     원인: 영상의 loadeddata/seeked/pause 이벤트에서 표지 편집기는 '표지 시각'으로,
//     컷 편집기는 '컷 시작 시각'으로 각각 원본을 되돌렸다(seek). 두 편집기가 **같은 영상**에
//     걸려 있어 seeked가 서로를 다시 깨우며 두 시각 사이를 무한 왕복했다.
//     → 이제 이벤트에서는 화면만 떠온다(seek 금지). 이 검사기가 그것을 재현해 확인한다.
//
// 사용: node worker/edit_playback_check.mjs   (JSON 한 줄 출력 — 파이썬 테스트가 읽는다)
import worker from "./index.mjs";

const STAGE_W = 320, STAGE_H = 180;
const REC = { id: "nv-test", kind: "narrate", mode: "shorts", body_dur: 30,
              source_url: "https://example.com/src.webm",
              media: { video_url: "https://example.com/v.mp4", sheet: null } };

const res = await worker.fetch(new Request("https://x/nv/nv-test"), {}, {});
const js = [...(await res.text()).matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

const els = {};
const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {}, _ls: {},
  classList: { toggle(){}, add(){}, remove(){} }, querySelectorAll: () => [],
  addEventListener(ev, fn){ (this._ls[ev] ??= []).push(fn); },
  insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, oninput: null,
  scrollIntoView(){}, load(){}, src: "", currentTime: 0, duration: 0, videoWidth: 0, videoHeight: 0,
  clientWidth: STAGE_W, clientHeight: STAGE_H, paused: true,
  fire(ev){ (this._ls[ev] || []).forEach(f => { try { f(); } catch (e) {} }); },
  getBoundingClientRect: () => ({ left: 0, top: 0, width: STAGE_W, height: STAGE_H }) });
const rendered = () => Object.values(els).map(e => e.innerHTML).join("\n");
const qsa = sel => {
  const m = sel.match(/^\[data-mk\^='(.+)'\]$/);
  if (m) return [...rendered().matchAll(/data-mk="([^"]+)"/g)].map(x => x[1])
    .filter(v => v.startsWith(m[1])).map(v => { const e = el("btn:" + v); e.dataset.mk = v; return e; });
  for (const [key, attr] of [["[data-cesel]", "cesel"], ["[data-fit]", "fit"],
                             ["[data-fitall]", "fitall"], ["[data-cvfit]", "cvfit"],
                             ["[data-cvtile]", "cvtile"], ["[data-cetile]", "cetile"]]) {
    if (sel === key) return [...rendered().matchAll(new RegExp('data-' + attr + '="([^"]+)"', "g"))]
      .map(x => x[1]).map(v => { const e = el(attr + ":" + v); e.dataset[attr] = v; return e; });
  }
  return [];
};
globalThis.window = { location: { pathname: "/nv/nv-test" } };
globalThis.location = window.location;
globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
  querySelectorAll: qsa, addEventListener(){},
  createElement: () => ({ width: 0, height: 0, getContext: () => ({ drawImage() {} }),
                          toDataURL: () => "data:image/jpeg;base64,TEST" }) };
globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => REC,
                                  text: async () => JSON.stringify(REC) });
globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
globalThis.setTimeout = (f) => { try { if (typeof f === "function") f(); } catch (e) {} return 0; };
globalThis.confirm = () => true;

const run = new Function(js + "\n; return { renderNarrateDetail, cvState, cvShow, cvDraw, ceState, coverInputs, allEditInputs };");
const api = run();
const vid = el("ncvid"); vid.videoWidth = 854; vid.videoHeight = 480; vid.duration = 60;
await api.renderNarrateDetail("nv-test");
for (let i = 0; i < 20; i++) await new Promise(r => queueMicrotask(r));

// ── 운영자가 표지 시각 12.5초, 컷1 시작 3초를 정한 상태를 만든다 ──────────────
const st = api.cvState();
st.at = 12.5; el("cvat").value = "12.5";
api.cvShow();
el("nc0a").value = "3"; el("nc0b").value = "9";

const box = () => ({ w: parseFloat(String(els["cvbox"]?.style.width || "0")) || 0,
                     h: parseFloat(String(els["cvbox"]?.style.height || "0")) || 0 });
const fitBox = (f) => {
  const b = qsa("[data-cvfit]").find(x => x.dataset.cvfit === f);
  if (b && b.onclick) b.onclick();
  const r = box();
  return { fit: api.cvState().fit, ar: r.h > 0 ? r.w / r.h : 0 };
};

const out = {
  fitButtons: qsa("[data-cvfit]").map(b => b.dataset.cvfit),
  cover: fitBox("cover"),
  square: fitBox("square"),
  full: fitBox("full"),
  stageAr: STAGE_W / STAGE_H,
};
out.coverInput = (() => { try { return JSON.parse(api.coverInputs().cover || "{}"); } catch (e) { return {}; } })();

// ── 재생 중 다른 구간으로 옮겼을 때 playhead가 끌려오지 않아야 한다 ──────────
api.cvState().fit = "cover";
vid.paused = false;
vid.currentTime = 30;                 // 운영자가 30초로 이동
vid.fire("seeked");                   // 브라우저가 알리는 이벤트
const after1 = vid.currentTime;
vid.fire("seeked"); vid.fire("pause"); vid.fire("loadeddata");   // 연달아 와도 마찬가지
out.afterSeek = after1;
out.afterMore = vid.currentTime;

// '여기 끝' 버튼을 눌러도 재생 위치가 컷 시작으로 끌려가지 않아야 한다
vid.currentTime = 42;
const mk = qsa("[data-mk^='nc']").find(b => b.dataset.mk === "nc0b");
if (mk && mk.onclick) mk.onclick();
out.afterMark = vid.currentTime;

console.log(JSON.stringify(out));
