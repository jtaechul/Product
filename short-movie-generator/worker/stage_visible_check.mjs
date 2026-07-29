// 구획(잘라낼 부분) 설정 화면이 **어떤 경우에도 보이는지** 확인(브라우저 없이).
//
// 왜 필요한가(실사고 · 운영자 지적 "영상 구획 설정하는 부분이 아예 보여지지가 않아"):
//   스테이지(사각형을 그리는 칸)에 높이를 주는 곳이 ceShowFrame 뿐이었는데, 그 함수는
//   **프레임 사진(시트)이 없으면 그냥 return** 했다 → 시트가 없는 회차에서 칸 높이가 0이 되어
//   구획 설정 화면이 통째로 사라졌다(사각형도 안 보임).
//   이 검사기는 ①스테이지 HTML이 자체 높이(aspect-ratio/min-height)를 갖는지
//   ②시트가 없어도 사각형이 실제 크기로 그려지는지를 확인한다.
//
// 사용: node worker/stage_visible_check.mjs   (JSON 한 줄 출력 — 파이썬 테스트가 읽는다)
import worker from "./index.mjs";

const STAGE_W = 320, STAGE_H = 180;

async function probe(withSheet) {
  const REC = {
    id: "nv-test", kind: "narrate", mode: "shorts", body_dur: 30,
    source_url: "https://example.com/src.webm",
    media: {
      video_url: "https://example.com/v.mp4",
      sheet: withSheet ? { url: "https://example.com/s.jpg", cols: 5, rows: 2, n: 10,
                           step: 3, tw: 480, th: 270 } : null,
    },
  };
  const res = await worker.fetch(new Request("https://x/nv/nv-test"), {}, {});
  const js = [...(await res.text()).matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

  const els = {};
  const el = id => (els[id] ??= { id, innerHTML: "", value: "", style: {}, dataset: {},
    classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){}, querySelectorAll: () => [],
    insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, oninput: null,
    scrollIntoView(){}, load(){}, src: "", currentTime: 0, duration: 0, videoWidth: 0, videoHeight: 0,
    clientWidth: STAGE_W, clientHeight: STAGE_H,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: STAGE_W, height: STAGE_H }) });
  const rendered = () => Object.values(els).map(e => e.innerHTML).join("\n");
  const qsa = sel => {
    const m = sel.match(/^\[data-mk\^='(.+)'\]$/);
    if (m) return [...rendered().matchAll(/data-mk="([^"]+)"/g)].map(x => x[1])
      .filter(v => v.startsWith(m[1])).map(v => { const e = el("btn:" + v); e.dataset.mk = v; return e; });
    if (sel === "[data-cesel]") return [...rendered().matchAll(/data-cesel="([^"]+)"/g)].map(x => x[1])
      .map(v => { const e = el("sel:" + v); e.dataset.cesel = v; return e; });
    if (sel === "[data-fit]") return [...rendered().matchAll(/data-fit="([^"]+)"/g)].map(x => x[1])
      .map(v => { const e = el("fit:" + v); e.dataset.fit = v; return e; });
    return [];
  };
  globalThis.window = { location: { pathname: "/nv/nv-test" } };
  globalThis.location = window.location;
  globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
    querySelectorAll: qsa, addEventListener(){},
    // 캔버스 흉내: 시트가 없을 때 '재생 중인 원본 화면'을 떠서 배경으로 쓰는 경로를 검사한다
    createElement: () => ({ width: 0, height: 0, getContext: () => ({ drawImage() {} }),
                            toDataURL: () => "data:image/jpeg;base64,TEST" }) };
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => REC,
    text: async () => JSON.stringify(REC) });
  globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
  globalThis.setTimeout = () => 0;

  const run = new Function(js + "\n; return { renderNarrateDetail, ceShowFrame };");
  const { renderNarrateDetail, ceShowFrame } = run();
  await renderNarrateDetail("nv-test");
  // 원본이 재생 가능한 상태(크기를 아는 상태)를 흉내
  const vid = el("ncvid"); vid.videoWidth = 854; vid.videoHeight = 480;
  ceShowFrame("nc");                       // 시트 유무와 무관하게 호출되는 경로
  const html = els["nvcard"]?.innerHTML || "";
  const px = v => parseFloat(String(v || "0").replace("px", "")) || 0;
  const stageTag = (html.match(/<div id="ncstage"[^>]*>/) || [""])[0];
  return {
    withSheet,
    // 스테이지가 스스로 높이를 갖는가(사진이 없어도 칸이 안 무너지게)
    stageHasOwnHeight: /aspect-ratio\s*:/.test(stageTag) && /min-height\s*:/.test(stageTag),
    // 사각형이 실제 크기로 그려졌는가
    boxW: px(els["ncbox"]?.style.width), boxH: px(els["ncbox"]?.style.height),
    coverStageTag: /aspect-ratio\s*:/.test((html.match(/<div id="cvstage"[^>]*>/) || [""])[0]),
    // 시트가 없을 때 재생 화면을 떠서 배경으로 넣었는가
    stageBgFromVideo: String(els["ncstage"]?.style.backgroundImage || "").includes("data:image"),
    stageAspect: String(els["ncstage"]?.style.aspectRatio || ""),
  };
}

console.log(JSON.stringify([await probe(true), await probe(false)]));
