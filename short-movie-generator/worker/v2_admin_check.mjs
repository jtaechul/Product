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
// 아이폰 화면 넘침 방지(2026-09-28 실사고: 긴 URL·일본어가 카드 밖으로 밀려 나감)
res.mobile_no_overflow = /html\{-webkit-text-size-adjust:100%/.test(html) && /\.v2copytxt\{[^}]*min-width:0[^}]*overflow-wrap:anywhere/.test(html)
  && /@media \(max-width:520px\)\{\.dual\{grid-template-columns:1fr\}\}/.test(html);
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

{ // 영상 단계가 '승인 대기'일 때 승인 버튼이 켜지는지(실제 파일의 현재 단계와 무관하게 상태를 만들어 확인)
  const sv = JSON.parse(readFileSync(path.join(ROOT, "short-movie-generator/v2/pilots/bathynomus_giganteus/status.json"), "utf-8"));
  sv.stages.video.state = "review"; sv.stages.upload.state = "locked";
  statusOverride = sv; const keepEls = els; els = {}; await api.renderV2Episode("bathynomus_giganteus");
  const ev = els.view.innerHTML; const vid0 = ev.slice(ev.indexOf('id="stg-video"'), ev.indexOf('id="stg-upload"'));
  res.video_approve_enabled = /data-act="approve" data-stage="video">/.test(vid0);
  const upl = ev.slice(ev.indexOf('id="stg-upload"')); res.locked_upload_has_no_buttons = !upl.includes("data-act=");
  statusOverride = null; els = keepEls; }
const vid = ep.slice(ep.indexOf('id="stg-video"'), ep.indexOf('id="stg-upload"'));
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
{ // 미반영 대사가 없는 상태를 만들어 확인(실제 파일은 3번 컷 교정이 미반영 상태일 수 있다)
  const st0 = JSON.parse(readFileSync(path.join(ROOT, "short-movie-generator/v2/pilots/bathynomus_giganteus/status.json"), "utf-8"));
  st0.artifacts.script.pending_lines = []; st0.artifacts.script.cuts.forEach(c => { c.pending = false; });
  statusOverride = st0; const keep = els; els = {}; await api.renderV2Episode("bathynomus_giganteus");
  const e0 = els.view.innerHTML; res.no_apply_button_without_edits = !e0.includes('id="v2apply"') && e0.includes('id="v2asm"');
  statusOverride = null; els = {}; await api.renderV2Episode("bathynomus_giganteus"); }
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
// ── 검증 ①② : 근거 원문 표시 + AI 의심 표시·제안 ──
const scr3 = ep.slice(ep.indexOf('id="stg-script"'), ep.indexOf('id="stg-storyboard"'));
res.fact_text_per_cut = (scr3.match(/class="v2fact"/g) || []).length;
res.crosscheck_button = scr3.includes('id="v2cc"');
const st3 = JSON.parse(readFileSync(path.join(ROOT, "short-movie-generator/v2/pilots/bathynomus_giganteus/status.json"), "utf-8"));
st3.artifacts.script.crosscheck = { at: "2026-09-28T00:00:00Z", issues: [{ cut: 3, type: "scope", problem_ko: "범위 착오", facts: ["F9"], suggestion_jp: "等脚類の中では、世界最大です。", suggestion_ko: "등각류 중 최대" }] };
st3.stages.script.state = "review";
statusOverride = st3; els = {}; await api.renderV2Episode("bathynomus_giganteus"); const ep3 = els.view.innerHTML;
res.flag_shown = ep3.includes("AI 의심") && ep3.includes("의심 1건") && ep3.includes('data-usesug="0"');
const sug = (lists["[data-usesug]"] || [])[0]; els["edjp-3"] = makeEl("edjp-3");
if (sug?.onclick) sug.onclick();
res.suggestion_fills_editor = els["edjp-3"].value === "等脚類の中では、世界最大です。";
statusOverride = null;
// ── 컷 수정 방향 → 콘티 → 승인 ──
els = {}; await api.renderV2Episode("bathynomus_giganteus"); const ep4 = els.view.innerHTML;
res.recut_open_buttons = (ep4.match(/data-rcopen="/g) || []).length;
const d1 = dispatched.length;
els["rcdir-8"] = makeEl("rcdir-8"); els["rcdir-8"].value = "뱃속이 텅 빈 묘사 + 물음표";
els["rcmin-8"] = makeEl("rcmin-8"); els["rcmin-8"].value = "2";
const go8 = (lists["[data-rcgo]"] || []).find(b => b.dataset.rcgo === "8"); if (go8?.onclick) await go8.onclick();
res.recut_plan_dispatch = dispatched.slice(d1).map(d => ({ action: d.body.inputs.action, stage: d.body.inputs.stage, note: JSON.parse(d.body.inputs.note) }));
const st5 = JSON.parse(readFileSync(path.join(ROOT, "short-movie-generator/v2/pilots/bathynomus_giganteus/status.json"), "utf-8"));
st5.artifacts.recut = { "8": { state: "conti_review", direction: "뱃속", min_transitions: 2, estimate_usd: 0.53,
  conti: { sheet: "out/x/conti.jpg", panels: [] }, plan: { summary_ko: "요약", shots: [
  { t0: 0, t1: 2.2, panel: 1, motion: "omni", overlay: "none", desc_ko: "표본" },
  { t0: 2.2, t1: 4, panel: 2, motion: "still", overlay: "none", desc_ko: "빈 위" },
  { t0: 4, t1: 6, panel: 3, motion: "still", overlay: "question_mark", desc_ko: "물음표" }] } } };
statusOverride = st5; els = {}; await api.renderV2Episode("bathynomus_giganteus"); const ep5 = els.view.innerHTML;
res.recut_review_shown = ep5.includes('data-rcok="8"') && ep5.includes("화면 전환 2회") && ep5.includes("빨간 물음표") && ep5.includes("conti.jpg");
const d2 = dispatched.length; const ok8 = (lists["[data-rcok]"] || []).find(b => b.dataset.rcok === "8"); if (ok8?.onclick) await ok8.onclick();
res.recut_approve_dispatch = dispatched.slice(d2).map(d => d.body.inputs.action + ":" + d.body.inputs.stage);
statusOverride = null;
// ── 업로드 카드: 제목·설명·해시태그 칸 + 업로드 버튼(수정 요청 칸 없음) ──
const st6 = JSON.parse(readFileSync(path.join(ROOT, "short-movie-generator/v2/pilots/bathynomus_giganteus/status.json"), "utf-8"));
st6.stages.video.state = "approved"; st6.stages.upload.state = "review";
st6.artifacts.upload = { meta: { title_jp: "題 #ダイオウグソクムシ #深海", title_ko: "제목", desc_jp: "説明", desc_ko: "설명",
  tags_jp: ["#ダイオウグソクムシ", "#深海"], tags_ko: ["#대왕구족충", "#심해"], pinned_comment: "次に見たい深海の生き物は？", privacy: "private" } };
statusOverride = st6; els = {}; await api.renderV2Episode("bathynomus_giganteus"); const ep6 = els.view.innerHTML;
const up6 = ep6.slice(ep6.indexOf('id="stg-upload"'));
res.upload_fields = ['id="up_tj"', 'id="up_dj"', 'id="up_dk"', 'id="up_pv"', 'id="upsave"', "#ダイオウグソクムシ"].every(x => up6.includes(x));
res.upload_no_revise_box = !up6.includes('id="note-upload"') && up6.includes("승인 → 유튜브 업로드");
res.download_buttons = (ep6.match(/data-v2dl="/g) || []).length;   // 영상 카드 + 업로드 카드
{ // 저장 버튼 → 워커 프록시의 완성본 주소로 받는지(아이폰 공유 창 경로)
  const fetched = []; const of = globalThis.fetch;
  globalThis.fetch = async (u, o) => { if (String(u).includes("/api/media")) { fetched.push(String(u)); return { ok: true, status: 200, blob: async () => new Blob(["x"]) }; } return of(u, o); };
  Object.defineProperty(globalThis, "navigator", { value: { canShare: () => true, share: async () => {} }, configurable: true }); globalThis.File = class { constructor(p, n) { this.name = n; } };
  const b = (lists["[data-v2dl]"] || [])[0]; if (b?.onclick) await b.onclick(); for (let i = 0; i < 20; i++) await Promise.resolve();
  res.download_fetches_final = fetched.some(u => decodeURIComponent(u).includes("out/24_final/bathynomus_v5.mp4"));
  globalThis.fetch = of; }
statusOverride = null;
// ── 업로드 뒤에도 복사 칸 유지 + 복사 버튼 + 업로드 버튼이 화면 값을 보냄 ──
{
  const meta = { title_jp: "題 #ダイオウグソクムシ #深海", title_ko: "제목 #대왕구족충 #심해", desc_jp: "説明本文\n#ダイオウグソクムシ #深海",
    desc_ko: "설명", tags_jp: ["#ダイオウグソクムシ", "#深海"], tags_ko: ["#대왕구족충", "#심해"], pinned_comment: "次に見たい深海の生き物は？", privacy: "private", category: "15" };
  const s7 = JSON.parse(readFileSync(path.join(ROOT, "short-movie-generator/v2/pilots/bathynomus_giganteus/status.json"), "utf-8"));
  s7.stages.video.state = "approved"; s7.stages.upload.state = "approved";
  s7.artifacts.upload = { meta, result: { url: "https://youtu.be/X", privacy: "public", category: "28" } };
  statusOverride = s7; els = {}; await api.renderV2Episode("bathynomus_giganteus"); const e7 = els.view.innerHTML;
  const u7 = e7.slice(e7.indexOf('id="stg-upload"'));
  res.after_upload_copy_boxes = ["cp_tj", "cp_dj", "cp_hj", "cp_tk", "cp_dk", "cp_pc"].every(x => u7.includes('id="' + x + '"')) && u7.includes("説明本文") && u7.includes("공개") && u7.includes("과학기술");
  let copied = ""; Object.defineProperty(globalThis, "navigator", { value: { clipboard: { writeText: async t => { copied = t; } } }, configurable: true });
  els["cp_dj"] = makeEl("cp_dj"); delete els["cp_dj"].value; els["cp_dj"].textContent = meta.desc_jp;
  const cb = (lists["[data-copyfrom]"] || []).find(b => b.dataset.copyfrom === "cp_dj"); if (cb?.onclick) cb.onclick(); for (let i = 0; i < 10; i++) await Promise.resolve();
  res.copy_button_copies_description = copied === meta.desc_jp;
  // 업로드 전: 화면에서 '공개'·'과학기술'을 고르고 저장 없이 바로 업로드 → 그 값이 그대로 전송
  const s8 = JSON.parse(JSON.stringify(s7)); s8.stages.upload.state = "review"; delete s8.artifacts.upload.result;
  statusOverride = s8; els = {}; await api.renderV2Episode("bathynomus_giganteus");
  for (const [id, v] of [["up_tj", "画面の題名"], ["up_pv", "public"], ["up_ct", "28"], ["up_dj", "説明"]]) { els[id] = makeEl(id); els[id].value = v; }
  const d3 = dispatched.length; const ap = (lists["[data-act]"] || []).find(b => b.dataset.act === "approve" && b.dataset.stage === "upload");
  if (ap?.onclick) await ap.onclick();
  const sent = dispatched.slice(d3)[0]; const note = sent ? JSON.parse(sent.body.inputs.note) : {};
  res.upload_sends_screen_values = !!sent && sent.body.inputs.action === "approve" && note.privacy === "public" && note.category === "28" && note.title_jp === "画面の題名";
  statusOverride = null;
}

els = {}; window.location.pathname = "/legacy"; api.renderHome(); res.legacy_home_renders = (els.view?.innerHTML || "").includes("쇼츠 생성 시작");
console.log(JSON.stringify(res, null, 1));
