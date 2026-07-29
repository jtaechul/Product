// 표지(오프닝 훅) 편집기에 **그림이 실제로 뜨는지** 확인(브라우저 없이) — 두 페이지 모두.
//
// 왜 필요한가(실사고 · 운영자 지적 IMG_4081 "오프닝 훅 수정 기능이 추가되긴 했는데 보기에서
//   아무것도 안 보인다"): 표지 편집기가 화면을 떠올 영상 요소 id를 **"ncvid"로 고정**해 두어,
//   영상 id가 다른 도감형(/c, "cevid")에서는 캡처가 조용히 실패하고 **격자 배경만** 남았다.
//   (사각형·안내문은 보이니 '기능은 있는데 그림만 없는' 상태로 보였다.)
//
// 이 검사기는 두 페이지의 실제 서빙 스크립트를 실행해, 프레임 사진(시트)이 없을 때도
//   ①표지 스테이지에 원본 화면이 들어가는지 ②고른 시각으로 원본을 옮겼는지를 본다.
//
// 사용: node worker/cover_stage_check.mjs   (JSON 한 줄 출력 — 파이썬 테스트가 읽는다)
import worker from "./index.mjs";

const STAGE_W = 320, STAGE_H = 180;

// page: {path, render, vid} — 나레이션형(/nv, ncvid) / 도감형(/c, cevid)
async function probe(page) {
  const REC = page.rec;
  const res = await worker.fetch(new Request("https://x" + page.path), {}, {});
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
    for (const [key, attr] of [["[data-cesel]", "cesel"], ["[data-fit]", "fit"],
                               ["[data-fitall]", "fitall"], ["[data-cvtile]", "cvtile"],
                               ["[data-cetile]", "cetile"]]) {
      if (sel === key) return [...rendered().matchAll(new RegExp('data-' + attr + '="([^"]+)"', "g"))]
        .map(x => x[1]).map(v => { const e = el(attr + ":" + v); e.dataset[attr] = v; return e; });
    }
    return [];
  };
  globalThis.window = { location: { pathname: page.path } };
  globalThis.location = window.location;
  globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
    querySelectorAll: qsa, addEventListener(){},
    createElement: () => ({ width: 0, height: 0, getContext: () => ({ drawImage() {} }),
                            toDataURL: () => "data:image/jpeg;base64,TEST" }) };
  globalThis.fetch = async (u) => {
    const url = String(u);
    // 도감형은 영상 캐시(JSON)를 읽어 원본·시트를 찾는다 — 시트 없음 상태를 흉내
    if (url.includes("_video_cache.json")) {
      return { ok: true, status: 200, text: async () => JSON.stringify(page.cache || {}),
               json: async () => (page.cache || {}) };
    }
    return { ok: true, status: 200, json: async () => REC, text: async () => JSON.stringify(REC) };
  };
  globalThis.localStorage = { getItem: () => null, setItem(){}, removeItem(){} };
  globalThis.setTimeout = (f) => { try { if (typeof f === "function") f(); } catch (e) {} return 0; };
  globalThis.confirm = () => true;

  const run = new Function(js + "\n; return { renderDetail, renderNarrateDetail, cvState, cvShow };");
  const api = run();
  // 원본 영상이 재생 가능한 상태를 흉내(크기·길이를 아는 상태)
  const vid = el(page.vid); vid.videoWidth = 854; vid.videoHeight = 480; vid.duration = 40;
  await (page.render === "narrate" ? api.renderNarrateDetail(page.id) : api.renderDetail(page.id));
  // 도감형은 원본·시트를 비동기로 찾은 뒤 편집기를 배선한다 → 그 마이크로태스크가 끝나길 기다린다
  for (let i = 0; i < 20; i++) await new Promise(r => queueMicrotask(r));
  // 운영자가 표지 시각을 골랐을 때
  const st = api.cvState();
  st.at = 12.5;
  el("cvat").value = "12.5";
  api.cvShow();
  return {
    page: page.name,
    vidId: page.vid,
    stateVid: String(st.vid || ""),
    stageBg: String(els["cvstage"]?.style.backgroundImage || "").includes("data:image"),
    stageAspect: String(els["cvstage"]?.style.aspectRatio || ""),
    seekedTo: Number(vid.currentTime || 0),
    boxW: parseFloat(String(els["cvbox"]?.style.width || "0")) || 0,
  };
}

const out = [];
out.push(await probe({
  name: "나레이션형(/nv)", path: "/nv/nv-test", id: "nv-test", render: "narrate", vid: "ncvid",
  rec: { id: "nv-test", kind: "narrate", mode: "shorts", body_dur: 30,
         source_url: "https://example.com/src.webm",
         media: { video_url: "https://example.com/v.mp4", sheet: null } },
}));
out.push(await probe({
  name: "도감형(/c)", path: "/c/048", id: "048", render: "reel", vid: "cevid",
  cache: {},                                     // 시트·미리보기 없음(운영자 화면과 동일)
  rec: { id: "048", kind: "reel",
         species: { scientific_name: "Test species", common_name_ko: "테스트" },
         media: { video_url: "https://example.com/v.mp4", duration: 30 } },
}));
console.log(JSON.stringify(out));
