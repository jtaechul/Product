// v2 관리자 페이지 검사기(브라우저 없이): 실제 저장소 파일(index.json·topics.json·status.json)로
// ① 메뉴가 '영상 목록'·'새 영상' 두 개만인지 ② 목록·새 영상·한 편 페이지가 그려지는지
// ③ 잠긴 단계엔 버튼이 없고 승인 대기 단계엔 승인 버튼이 켜지는지 ④ 버튼이 v2-admin.yml 을 올바른 입력으로 부르는지
// ⑤ 예전 화면(/legacy)이 살아 있는지 확인한다.  실행: node worker/v2_admin_check.mjs
import worker from "./index.mjs";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const html = await (await worker.fetch(new Request("https://x/"), {})).text();
const js = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).join("\n");

function makeEl(id){
  return { id, innerHTML: "", value: "", style: {}, dataset: {}, disabled: false, open: false, className: "",
    classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){}, querySelectorAll: () => [],
    insertAdjacentHTML(_p, h){ this.innerHTML += h; }, onclick: null, getAttribute: () => null };
}
let els = {}, buttons = [], lists = {};
const el = id => (els[id] ??= makeEl(id));
// data-* 버튼을 innerHTML 에서 뽑아 가짜 요소로 만든다(클릭 시뮬레이션용)
function scanButtons(sel){
  const attr = sel.replace(/^\[|\]$/g, "");
  const re = new RegExp("<button[^>]*" + attr + '="([^"]*)"[^>]*>', "g");
  const out = [];
  for (const m of (els.view?.innerHTML || "").matchAll(re)) {
    const b = makeEl("btn"); const tag = m[0];
    for (const a of tag.matchAll(/data-([a-z]+)="([^"]*)"/g)) b.dataset[a[1]] = a[2];
    b.disabledAttr = / disabled/.test(tag); out.push(b);
  }
  buttons = out; lists[sel] = out; return out;
}
const dispatched = [];
globalThis.window = { location: { pathname: "/" } }; globalThis.location = window.location;
globalThis.document = { getElementById: el, querySelector: s => el(s.replace(/^#/, "")),
  querySelectorAll: s => (s === "#nav a" ? [] : scanButtons(s)), addEventListener(){}, createElement: () => ({}) };
globalThis.localStorage = { getItem: k => (k === "gh_pat" ? "tok" : null), setItem(){}, removeItem(){} };
globalThis.confirm = () => true; globalThis.alert = () => {};
globalThis.setTimeout = () => 0;
let statusOverride = null;
globalThis.fetch = async (url, opts) => {
  url = String(url);
  if (statusOverride && url.includes("status.json")) return { ok: true, status: 200, text: async () => JSON.stringify(statusOverride) };
  if (url.includes("/dispatches")) { dispatched.push({ url, body: JSON.parse(opts.body) }); return { status: 204, ok: true, text: async () => "" }; }
  const m = url.match(/\/api\/pub\?path=([^&]+)/);
  if (m) {
    try { const t = readFileSync(path.join(ROOT, decodeURIComponent(m[1])), "utf-8"); return { ok: true, status: 200, text: async () => t }; }
    catch { return { ok: false, status: 404, text: async () => "" }; }
  }
  return { ok: false, status: 404, text: async () => "", json: async () => ({}) };
};

const api = new Function(js.replace(/\ninit\(\);\s*$/, "\n") +
  "\n; return { renderV2List, renderV2New, renderV2Episode, renderHome };").call(null);
const res = {};
res.nav_two_menus = /<div class="nav" id="nav"><a href="\/" data-p="v2list">영상 목록<\/a><a href="\/new" data-p="v2new">새 영상<\/a><\/div>/.test(html)
  && !/data-p="library"|data-p="clips"/.test(html);

await api.renderV2List(); const list = els.view.innerHTML;
res.list_has_pilot = list.includes("/v/bathynomus_giganteus") && list.includes("대왕구족충");
res.list_groups = list.includes("승인 대기") && list.includes("작업 중") && list.includes("완성");

els = {}; await api.renderV2New(); const nw = els.view.innerHTML;
res.new_lists_ready_topics = (nw.match(/data-new="/g) || []).length;
res.new_hides_in_progress = !nw.includes('data-new="bathynomus_giganteus"');
const nb = (lists["[data-new]"] || [])[0]; if (nb?.onclick) await nb.onclick();

els = {}; await api.renderV2Episode("bathynomus_giganteus"); const ep = els.view.innerHTML;
res.episode_five_stages = ["stg-topic", "stg-script", "stg-storyboard", "stg-video", "stg-upload"].every(k => ep.includes(k));
res.video_final_via_proxy = ep.includes("/api/media?u=" + encodeURIComponent("https://raw.githubusercontent.com/jtaechul/Product/claude/gemini-shorts-reels-generator-dhjfdt/short-movie-generator/v2/pilots/bathynomus_giganteus/out/24_final/bathynomus_v5.mp4"));
res.clip_redo_buttons = (ep.match(/data-cut="/g) || []).length;
const upload = ep.slice(ep.indexOf('id="stg-upload"'));
res.locked_upload_has_no_buttons = !upload.includes("data-act=");
const vid = ep.slice(ep.indexOf('id="stg-video"'), ep.indexOf('id="stg-upload"'));
res.video_approve_enabled = /data-act="approve" data-stage="video">/.test(vid);
const scr = ep.slice(ep.indexOf('id="stg-script"'), ep.indexOf('id="stg-storyboard"'));
res.approved_script_approve_disabled = /data-act="approve" data-stage="script" disabled/.test(scr);
res.auto_checks_shown = vid.includes("가장자리 흰 줄") && vid.includes("통과");

// 버튼 → 디스패치 입력 확인(새 영상 시작 · 승인 · 컷 재생성) — 페이지가 붙인 핸들러를 그대로 누른다
const appr = (lists["[data-act]"] || []).find(b => b.dataset.act === "approve" && b.dataset.stage === "video");
if (appr?.onclick) await appr.onclick();
const c1 = (lists["[data-cut]"] || []).find(b => b.dataset.cut === "1");
if (c1?.onclick) await c1.onclick();
res.dispatches = dispatched.map(d => ({ wf: d.url.split("/workflows/")[1].split("/")[0], ref: d.body.ref, ...d.body.inputs }));

// ── 컷별 대사 수정(운영자 확정 2026-09-28): 저장은 대본만 · 영상 반영은 별도 버튼 ──
const scr2 = ep.slice(ep.indexOf('id="stg-script"'), ep.indexOf('id="stg-storyboard"'));
res.line_edit_buttons = (scr2.match(/data-edit="/g) || []).length;
res.line_save_says_video_unchanged = scr2.includes("영상은 안 바뀜");
res.no_apply_button_without_edits = !ep.includes('id="v2apply"') && ep.includes('id="v2asm"');
const d0 = dispatched.length;
const sv = (lists["[data-saveline]"] || []).find(b => b.dataset.saveline === "3");
els["edjp-3"] = makeEl("edjp-3"); els["edjp-3"].value = "大きさは最大50センチ近く。世界最大の仲間です。";
els["edko-3"] = makeEl("edko-3"); els["edko-3"].value = "크기는 최대 50cm 가까이. 세계 최대 무리입니다.";
if (sv?.onclick) await sv.onclick();
const ed = dispatched.slice(d0);
res.edit_dispatch = ed.map(d => ({ action: d.body.inputs.action, stage: d.body.inputs.stage, note: JSON.parse(d.body.inputs.note) }));
res.edit_does_not_touch_video = ed.every(d => !["redo_cut", "assemble", "apply_lines"].includes(d.body.inputs.action));
// 미반영 대사가 있는 상태: 반영 버튼이 나타나고 재조립 버튼도 그대로 있어야 한다
const stNow = JSON.parse(readFileSync(path.join(ROOT, "short-movie-generator/v2/pilots/bathynomus_giganteus/status.json"), "utf-8"));
stNow.artifacts.script.pending_lines = [3]; stNow.artifacts.script.cuts[2].pending = true;
statusOverride = stNow; els = {}; await api.renderV2Episode("bathynomus_giganteus"); const ep2 = els.view.innerHTML;
res.pending_shows_apply_and_asm = ep2.includes('id="v2apply"') && ep2.includes('id="v2asm"') && ep2.includes("아직 영상에 반영 안 된 컷: 3번");
statusOverride = null;

els = {}; window.location.pathname = "/legacy"; api.renderHome(); res.legacy_home_renders = (els.view?.innerHTML || "").includes("쇼츠 생성 시작");
console.log(JSON.stringify(res, null, 1));
