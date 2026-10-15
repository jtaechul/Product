// 숙소 쇼츠 관리실 — Cloudflare Worker (2026-10-14 운영자 "관리자 페이지는 언제 만들어?")
//
// 하는 일
//   - 비밀번호 하나로 로그인(쿠키 30일). 화면은 public/index.html (A 운영실 카드).
//   - GET  /api/state : 이번 달 쓴 돈 · 지금 도는 실행 · 최근 실행 · 후보 숙소 · 최근 결과(대본·검수)를 저장소에서 읽어 모은다.
//   - POST /api/run   : 미리보기(약 80원) / 정식 제작(약 2,500원, 화면에서 한 번 더 확인) — request.json 을 새 nonce 로 커밋한다.
//                       그 푸시가 stay-shorts-produce 워크플로를 깨운다(기존 돈 잠금·nonce 가드는 워크플로 쪽에 그대로).
//   - POST /api/cancel  : 도는 실행 멈추기(잘못 누른 정식 제작 — 영상 만들기 전이면 돈이 거의 안 나간다).
//   - POST /api/discover: 테마·지역·월로 후보 순위표 새로 만들기(stay-shorts-discover · 수십 원).
//   - GET  /api/media : 실행별 Release 의 완성 영상·나레이션·미리보기 글(preview.md)을 이 페이지 안에서 재생·표시(2026-10-14 운영자 "결과 바로 보기").
//   - 실행 중이면 버튼을 막는다(운영 규칙: 제작 워크플로가 도는 동안 같은 브랜치에 푸시하지 않는다).
//   - 텔레그램은 진행 알림 전용(운영자 2026-10-14) — 이 페이지는 텔레그램을 쓰지 않는다.
//
// 비밀값(Cloudflare Worker secret — 배포 워크플로가 넣는다): GH_TOKEN · ADMIN_PASSWORD · SESSION_SECRET
// 토큰은 화면으로 절대 내보내지 않고, 오류 문구에도 담지 않는다.

const BUILD = "dev";
const REPO = "jtaechul/Product";
const BRANCH = "claude/stay-shorts-video-conversion-67hiin";
const P = "projects/stay-shorts-factory";
const WF = { "stay-shorts-produce.yml": "produce", "stay-shorts-discover.yml": "discover" };
const REQ_PATH = `${P}/requests/produce/request.json`;
const DISC_PATH = `${P}/requests/discover/request.json`;
const REGIONS = ["강원", "경기", "제주", "부산", "경남", "경북", "전남", "전북", "충남", "충북", "서울", "인천", "대전", "대구", "광주", "울산", "세종"];
const MEDIA = { "video.mp4": "video/mp4", "narration_preview.mp3": "audio/mpeg", "preview.md": "text/plain; charset=utf-8" };
const MONTH_CAP = 50000;                    // 운영자 확정 월 한도(veo.py MONTH_KRW 와 같은 값)
// 형식별 예상 비용(원). 기존 9컷: 미리보기 글·음성 약 80 / 정식 제작(미니어처 3컷 + Veo 1컷) 약 2,500 (실측).
// 시그니처 v3(2026-10-15 운영자 "있는 사진으로 AI 영상"): 미리보기부터 컷마다 실제 사진 → Veo 4초(약 294원) + 글·비전 약 60
//   몽타주 최대 5컷 ≈ 1,550 · 한 장면 2컷 ≈ 650. 제작 = 미리보기 AI 클립 재사용 0원(사진 무빙으로 남은 컷만 다시 — 컷당 약 294), 미리보기 없이 = 미리보기와 같음
const COST = {
  signature: { preview: 1550, produce: 0, produce_fresh: 1550 },
  signature_single: { preview: 650, produce: 0, produce_fresh: 650 },
  solo: { preview: 80, produce: 2500, produce_fresh: 2500 },
};
const costOf = (mode, format) => (mode === "signature" && format === "single" ? COST.signature_single : COST[mode]);
const BLOCK_DAYS = 14;                      // make_sig 가 '사진·사실 부족'으로 멈춘 숙소는 이 기간 시그니처 버튼을 잠근다(state/sig_blocked.json)
const MODES = { signature: "시그니처", solo: "기존 9컷" };
const SIG_PREVIEW_RX = /관리자 페이지 시그니처(\(한 장면\))? AI 미리보기 — (.+?) \(/;   // 형식이 같아야 재사용된다(make_sig.find_reuse · v3 계획만 — v1·v2 '미리보기'는 안 맞음)
const LABEL = { preview: "미리보기", produce: "정식 제작" };
const DISCOVER_NOTE = "수십 원(AI 확인 몇 번 · 장부 미기록)";
const ACTIVE = new Set(["queued", "in_progress", "waiting", "requested", "pending"]);
const COOKIE = "stay_admin";
const SESSION_DAYS = 30;

const enc = new TextEncoder();
const fails = new Map();                   // 로그인 실패 횟수(같은 isolate 안에서만 — 지연과 함께 무차별 대입을 늦춘다)

class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers },
  });
}

function b64url(buf) {
  let s = "";
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64utf8(text) {
  let s = "";
  for (const b of enc.encode(text)) s += String.fromCharCode(b);
  return btoa(s);
}

async function hmac(key, msg) {
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", k, enc.encode(msg)));
}

async function sameText(a, b) {
  // 길이가 달라도 시간이 새지 않게 해시끼리 비교한다
  const [x, y] = await Promise.all([crypto.subtle.digest("SHA-256", enc.encode(a)), crypto.subtle.digest("SHA-256", enc.encode(b))]);
  return crypto.subtle.timingSafeEqual(x, y);
}

function sessionKey(env) {
  return env.SESSION_SECRET || env.ADMIN_PASSWORD || "";
}

async function makeSession(env) {
  const exp = Math.floor(Date.now() / 1000) + SESSION_DAYS * 86400;
  return `${exp}.${await hmac(sessionKey(env), `stay-admin|${exp}`)}`;
}

async function authed(request, env) {
  if (!env.ADMIN_PASSWORD) return false;
  const m = (request.headers.get("Cookie") || "").match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
  if (!m) return false;
  const [exp, sig] = m[1].split(".");
  if (!exp || !sig || Number(exp) < Date.now() / 1000) return false;
  return sameText(sig, await hmac(sessionKey(env), `stay-admin|${exp}`));
}

function cookie(value, maxAge) {
  return `${COOKIE}=${value}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${maxAge}`;
}

// ── GitHub ─────────────────────────────────────────────────────────────────────────────
async function gh(env, path, init = {}) {
  const r = await fetch(`https://api.github.com${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "stay-admin",
      ...(init.headers || {}),
    },
  });
  if (!r.ok) {
    const t = (await r.text()).slice(0, 160);
    throw new HttpError(r.status, `GitHub ${r.status}: ${t}`);
  }
  const t = await r.text();                   // 실행 멈추기(202)·204 는 본문이 비어 있다
  return t ? JSON.parse(t) : null;
}

async function readRaw(env, path) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/contents/${encodeURI(path)}?ref=${encodeURIComponent(BRANCH)}`, {
    headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github.raw", "User-Agent": "stay-admin", "X-GitHub-Api-Version": "2022-11-28" },
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new HttpError(r.status, `GitHub ${r.status}: ${path}`);
  return r.text();
}

async function readJson(env, path, fallback = null) {
  try {
    const t = await readRaw(env, path);
    return t == null ? fallback : JSON.parse(t);
  } catch (e) {
    return fallback;
  }
}

async function listRuns(env, n = 10) {
  const d = await gh(env, `/repos/${REPO}/actions/runs?branch=${encodeURIComponent(BRANCH)}&per_page=30`);
  return (d.workflow_runs || []).filter((r) => WF[String(r.path || "").split("/").pop()]).slice(0, n).map((r) => ({
    id: r.id,
    kind: WF[String(r.path || "").split("/").pop()],
    number: r.run_number,
    status: r.status,
    conclusion: r.conclusion,
    active: ACTIVE.has(r.status),
    title: String(r.display_title || "").slice(0, 120),
    created: r.created_at,
    updated: r.updated_at,
    url: r.html_url,
  }));
}

async function releaseMedia(env) {
  // stay-run-N 릴리스(제작 워크플로가 올림) → 실행 번호별 들어 있는 파일. 사진 시트는 원래 릴리스에 없다(공식 사진 재배포 금지)
  const out = {};
  const d = await gh(env, `/repos/${REPO}/releases?per_page=40`).catch(() => []);
  for (const r of d || []) {
    const m = String(r.tag_name || "").match(/^stay-run-(\d+)$/);
    if (m) out[m[1]] = (r.assets || []).map((a) => a.name).filter((n) => n in MEDIA);
  }
  return out;
}

async function recentRequestCommit(env) {
  // 커밋 직후 몇 초는 GitHub 에 실행이 아직 안 보인다 → 요청 폴더가 2분 안에 바뀌었으면 연달아 누른 것으로 본다
  const last = await gh(env, `/repos/${REPO}/commits?sha=${encodeURIComponent(BRANCH)}&path=${encodeURIComponent(P + "/requests")}&per_page=1`).catch(() => []);
  const at = Date.parse((((last || [])[0] || {}).commit || {}).committer?.date || "") || 0;
  return Date.now() - at < 120 * 1000;
}

async function readWithSha(env, path) {
  const f = await gh(env, `/repos/${REPO}/contents/${encodeURI(path)}?ref=${encodeURIComponent(BRANCH)}`);
  const text = new TextDecoder().decode(Uint8Array.from(atob(String(f.content || "").replace(/\s/g, "")), (c) => c.charCodeAt(0)));
  return { sha: f.sha, data: JSON.parse(text) };
}

async function commitJson(env, path, sha, data, message) {
  return gh(env, `/repos/${REPO}/contents/${encodeURI(path)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, content: b64utf8(JSON.stringify(data, null, 1) + "\n"), sha, branch: BRANCH }),
  }).catch((e) => {
    if (e.status === 409 || e.status === 422) throw new HttpError(409, "요청 파일이 방금 바뀌었습니다. 새로고침 후 다시 누르세요");
    if (e.status === 403 || e.status === 404) throw new HttpError(502, "GitHub 토큰에 이 저장소 파일 쓰기 권한이 없습니다 (Contents: Read and write 필요)");
    throw e;
  });
}

// ── 날짜·돈 ────────────────────────────────────────────────────────────────────────────
function kstNow() {
  return new Date(Date.now() + 9 * 3600 * 1000);
}

function monthSpend(ledger, ym) {
  const rows = (Array.isArray(ledger) ? ledger : []).filter((x) => String(x.date || "").startsWith(ym));
  const byKind = {};
  let total = 0;
  for (const x of rows) {
    const k = Number(x.krw) || 0;
    total += k;
    byKind[x.kind] = (byKind[x.kind] || 0) + k;
  }
  return { ym, total: Math.round(total), cap: MONTH_CAP, by_kind: byKind, recent: rows.slice(-6).reverse().map((x) => ({ date: x.date, kind: x.kind, krw: x.krw, note: String(x.note || "").slice(0, 80) })) };
}

function screenOk(qa) {
  const rows = (qa || []).map((q) => ({ thr: q.threshold ?? 7, sc: q.score2 ?? q.score })).filter((q) => q.sc != null);
  return { ok: rows.filter((q) => q.sc >= q.thr).length, total: rows.length };
}

function lastResult(rep) {
  if (!rep || typeof rep !== "object") return null;
  const s = rep.script || {};
  const nq = rep.narration_qa || [];
  return {
    mode: rep.mode || "",
    signature: (rep.signature || {}).name || "",
    image_krw: (rep.images || {}).image_krw || 0,
    nonce: rep.nonce,
    stay: rep.stay,
    stage: rep.stage || "제작",
    ok: !!rep.ok,
    error: rep.error ? String(rep.error).slice(0, 200) : "",
    hook_title: s.hook_title || "",
    title: s.title || "",
    narration_ok: nq.filter((q) => q.ok).length,
    narration_total: nq.length,
    screen: screenOk(rep.screen_qa),
    info: rep.info_test ? { ok: !!rep.info_test.ok, matched: rep.info_test.matched || 0, need: rep.info_test.need || 0 } : null,
    krw: (rep.gemini_usage || {}).krw_est || 0,
    cuts: (s.cuts || []).map((c) => ({ i: c.i, caption: c.caption, narration: c.narration })),
  };
}

function activeBlocks(blocked, now) {
  // 기한(BLOCK_DAYS)이 지나지 않은 잠금만 — 사진이 새로 생겼을 수 있어 오래된 잠금은 푼다
  const out = {};
  const today = now.toISOString().slice(0, 10);
  for (const [name, b] of Object.entries(blocked && typeof blocked === "object" ? blocked : {})) {
    const at = String((b || {}).at || "");
    const days = at ? (Date.parse(today) - Date.parse(at)) / 86400000 : 0;
    if (!(days > BLOCK_DAYS)) out[name] = { at, reason: String((b || {}).reason || "").slice(0, 160) };
  }
  return out;
}

function sigPreviewIndex(runs) {
  // 숙소별 가장 최근의 성공한 시그니처 미리보기 실행(제작 때 그 사진·글을 재사용 — 이미지 0원)
  const out = {};
  for (const r of runs) {
    if (r.kind !== "produce" || r.conclusion !== "success") continue;
    const m = String(r.title || "").match(SIG_PREVIEW_RX);
    const key = m ? `${m[1] ? "single" : "montage"}|${m[2]}` : "";
    if (m && !out[key]) out[key] = { id: r.id, number: r.number };
  }
  return out;
}

async function state(env) {
  const now = kstNow();
  const ym = now.toISOString().slice(0, 7);
  const [req, ledger, cands, folders, rep, titles, runs, media, disc, blocked] = await Promise.all([
    readJson(env, REQ_PATH, {}),
    readJson(env, `${P}/state/spend.json`, []),
    readJson(env, `${P}/data/discover/latest/candidates.json`, {}),
    readJson(env, `${P}/link/data/folders.json`, {}),
    readJson(env, `${P}/data/runs/latest/report.json`, null),
    readJson(env, `${P}/state/hook_titles.json`, []),
    listRuns(env).catch((e) => ({ error: e.message })),
    releaseMedia(env),
    readJson(env, DISC_PATH, {}),
    readJson(env, `${P}/state/sig_blocked.json`, {}),
  ]);
  const blocks = activeBlocks(blocked, now);
  const runList = (Array.isArray(runs) ? runs : []).map((r) => ({ ...r, media: r.kind === "produce" ? media[String(r.number)] || [] : [] }));
  const sigPreviews = sigPreviewIndex(Array.isArray(runs) ? runs : []);
  const done = new Set();
  for (const f of folders.folders || []) for (const h of f.hotels || []) done.add(h.name);
  const officials = req.official_urls || {};
  const list = (cands.candidates || []).slice(0, 12).map((c, i) => ({
    rank: i + 1,
    name: c.name,
    city: c.city || "",
    score: c.score,
    done: done.has(c.name),
    official: !!officials[c.name],
    sig_block: blocks[c.name] || null,
  }));
  return {
    build: BUILD,
    now: now.toISOString().slice(0, 16).replace("T", " "),
    money: monthSpend(ledger, ym),
    cost: COST,
    modes: MODES,
    sig_previews: sigPreviews,
    request: {
      nonce: req.nonce || "",
      stay: req.stay || "",
      stage: req.stage || "",
      veo_approved: req.veo_approved === true,
      theme: req.theme || "",
      region: req.region || "",
      month: req.month || "",
    },
    runs: runList,
    runs_error: Array.isArray(runs) ? "" : runs.error,
    running: runList.some((r) => r.active),
    candidates: list,
    theme: { theme: cands.theme || req.theme || "", region: cands.region || req.region || "", month: cands.month || req.month || "", ran_at: cands.ran_at || "" },
    discover: { theme: disc.theme || "", region: disc.region || "", month: disc.month || "", keywords: (disc.keywords || []).join(", "), note: DISCOVER_NOTE },
    regions: REGIONS,
    folders: (folders.folders || []).map((f) => ({ title: f.title, hotels: (f.hotels || []).map((h) => ({ rank: h.rank, name: h.name })) })),
    last: lastResult(rep),
    hook_titles: (Array.isArray(titles) ? titles : []).slice(-4).reverse().map((t) => ({ title: t.title, type: t.type, stay: t.stay })),
  };
}

async function startRun(env, body) {
  const action = String(body.action || "");
  if (!["preview", "produce"].includes(action)) throw new HttpError(400, "알 수 없는 실행입니다");
  const mode = String(body.mode || "signature") in MODES ? String(body.mode || "signature") : "signature";
  const format = String(body.format || "") === "single" ? "single" : "montage";
  const stay = String(body.stay || "").trim();
  if (!stay) throw new HttpError(400, "숙소를 고르세요");
  const [req, ledger, cands, runs, recent, blocked] = await Promise.all([
    readWithSha(env, REQ_PATH),
    readJson(env, `${P}/state/spend.json`, []),
    readJson(env, `${P}/data/discover/latest/candidates.json`, {}),
    listRuns(env, 30),
    recentRequestCommit(env),
    readJson(env, `${P}/state/sig_blocked.json`, {}),
  ]);
  const cur = req.data;
  const names = new Set([...(cands.candidates || []).map((c) => c.name), ...Object.keys(cur.official_urls || {})]);
  if (!names.has(stay)) throw new HttpError(400, "후보 목록에 없는 숙소입니다");
  if (runs.some((r) => r.active)) throw new HttpError(409, "지금 다른 실행이 돌고 있습니다. 끝난 뒤 다시 누르세요");
  if (recent) throw new HttpError(409, "방금 시작한 실행이 준비 중입니다. 1~2분 뒤 '지금 상태'를 확인하세요");
  const blk = mode === "signature" ? activeBlocks(blocked, kstNow())[stay] : null;
  if (blk) throw new HttpError(409, `이 숙소는 시그니처 영상을 만들 재료가 부족합니다(${blk.at}): ${blk.reason}. 다른 숙소를 고르거나 '기존 9컷' 형식을 쓰세요`);
  const reuse = mode === "signature" && action === "produce" ? sigPreviewIndex(runs)[`${format}|${stay}`] || null : null;
  const c = costOf(mode, format);
  const cost = action === "preview" ? c.preview : reuse ? c.produce : c.produce_fresh;
  const paid = action === "produce" || mode === "signature";                  // 시그니처 v3: 미리보기도 AI 영상(돈) → 화면 확인 + veo_approved
  const now = kstNow();
  const money = monthSpend(ledger, now.toISOString().slice(0, 7));
  if (money.total + cost > MONTH_CAP) {
    throw new HttpError(403, `이번 달 한도를 넘습니다 (쓴 돈 ${money.total.toLocaleString()}원 + 예상 ${cost.toLocaleString()}원 > ${MONTH_CAP.toLocaleString()}원)`);
  }
  if (paid && body.confirm !== true) {
    throw new HttpError(400, action === "produce" ? "정식 제작은 화면에서 한 번 더 확인해야 합니다" : "시그니처 AI 미리보기는 돈이 들어 화면에서 한 번 더 확인해야 합니다");
  }

  const next = { ...cur };
  for (const k of ["stage", "reuse_only", "reuse_runs", "reuse_clips", "format", "people"]) delete next[k];
  next.nonce = `${now.toISOString().slice(0, 10)}-admin-${mode === "signature" ? "sig" : "solo"}-${action}-${b64url(crypto.getRandomValues(new Uint8Array(3)))}`;
  next.mode = mode;
  next.stay = stay;
  // 후보표를 새로 만들었으면(후보 다시 찾기) 그 테마·지역·월로 만든다 — 폴더 이름·대본 계절이 후보표와 어긋나지 않게
  for (const k of ["theme", "region", "month"]) if (cands[k]) next[k] = cands[k];
  if (mode === "signature") {
    next.format = format;
    if (reuse) next.reuse_runs = [{ run_id: reuse.id, name: `stay-run-${reuse.number}` }];
  }
  next.veo_approved = paid;                                                   // 버튼 + 금액 확인 = 운영자 허락(make_stay 돈 잠금 · 실행 뒤 워크플로가 다시 잠근다)
  if (action === "preview") next.stage = "preview";
  const what = `${MODES[mode]}${mode === "signature" && format === "single" ? "(한 장면)" : ""} ${mode === "signature" && action === "preview" ? "AI 미리보기" : LABEL[action]}`;
  next.note = `관리자 페이지 ${what} — ${stay} · 예상 약 ${cost.toLocaleString()}원${reuse ? ` · 미리보기 #${reuse.number} 재사용` : ""} · ${now.toISOString().slice(0, 16).replace("T", " ")} KST`;
  const put = await commitJson(env, REQ_PATH, req.sha, next, `stay-shorts: 관리자 페이지 ${what} — ${stay} (${next.nonce})`);
  return { ok: true, nonce: next.nonce, action, mode, stay, cost, reuse: reuse ? reuse.number : null, commit: (put.commit || {}).html_url || "" };
}

async function cancelRun(env, body) {
  const id = Number(body.id);
  if (!Number.isInteger(id) || id <= 0) throw new HttpError(400, "실행 번호가 없습니다");
  const r = await gh(env, `/repos/${REPO}/actions/runs/${id}`);
  if (!WF[String(r.path || "").split("/").pop()] || r.head_branch !== BRANCH) throw new HttpError(400, "이 페이지에서 멈출 수 없는 실행입니다");
  if (!ACTIVE.has(r.status)) throw new HttpError(409, "이미 끝난 실행입니다");
  await gh(env, `/repos/${REPO}/actions/runs/${id}/cancel`, { method: "POST" }).catch((e) => {
    if (e.status === 403 || e.status === 404) throw new HttpError(502, "GitHub 토큰에 실행 멈추기 권한이 없습니다 (Actions: Read and write 필요)");
    throw e;
  });
  return { ok: true, id };
}

function monthOk(m, now) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(m)) return false;
  const [y, mo] = m.split("-").map(Number);
  const diff = (y - now.getUTCFullYear()) * 12 + (mo - (now.getUTCMonth() + 1));
  return diff >= 0 && diff <= 12;
}

async function startDiscover(env, body) {
  const now = kstNow();
  const theme = String(body.theme || "").trim().replace(/\s+/g, " ");
  const region = String(body.region || "").trim();
  const month = String(body.month || "").trim();
  const keywords = String(body.keywords || "").split(/[,，]/).map((k) => k.trim()).filter(Boolean);
  if (!/^[가-힣A-Za-z0-9·,\s]{2,24}$/.test(theme)) throw new HttpError(400, "테마는 2~24자 한글·영문·숫자로 적어 주세요 (예: 키즈풀·워터파크)");
  if (!REGIONS.includes(region)) throw new HttpError(400, "지역을 목록에서 고르세요");
  if (!monthOk(month, now)) throw new HttpError(400, "월은 이번 달부터 12개월 안에서 고르세요");
  if (keywords.length > 12 || keywords.some((k) => !/^[가-힣A-Za-z0-9 ]{1,12}$/.test(k))) throw new HttpError(400, "키워드는 쉼표로 나눠 12개까지, 각 12자 안으로");
  const [req, ledger, runs, recent] = await Promise.all([readWithSha(env, DISC_PATH), readJson(env, `${P}/state/spend.json`, []), listRuns(env, 10), recentRequestCommit(env)]);
  if (runs.some((r) => r.active)) throw new HttpError(409, "지금 다른 실행이 돌고 있습니다. 끝난 뒤 다시 누르세요");
  if (recent) throw new HttpError(409, "방금 시작한 실행이 준비 중입니다. 1~2분 뒤 다시 누르세요");
  if (monthSpend(ledger, now.toISOString().slice(0, 7)).total >= MONTH_CAP) throw new HttpError(403, "이번 달 한도를 이미 다 썼습니다");
  const next = { nonce: `${now.toISOString().slice(0, 10)}-admin-discover-${b64url(crypto.getRandomValues(new Uint8Array(3)))}`, theme, region, month, count: Number(req.data.count) || 20 };
  if (keywords.length) next.keywords = keywords;
  const put = await commitJson(env, DISC_PATH, req.sha, next, `stay-shorts: 관리자 페이지 후보 다시 찾기 — ${month} ${region} ${theme} (${next.nonce})`);
  return { ok: true, nonce: next.nonce, commit: (put.commit || {}).html_url || "" };
}

async function media(env, url, request) {
  // 공개 Release 파일을 이 페이지 주소로 다시 내보낸다 — 아이폰 사파리는 octet-stream 영상을 못 틀 수 있어 형식을 붙이고, 구간 요청(Range)을 넘긴다
  const tag = url.searchParams.get("tag") || "";
  const name = url.searchParams.get("name") || "";
  if (!/^stay-run-\d{1,6}$/.test(tag) || !(name in MEDIA)) return json({ error: "잘못된 파일" }, 400);
  const headers = { "User-Agent": "stay-admin" };
  const range = request.headers.get("Range");
  if (range) headers.Range = range;
  const r = await fetch(`https://github.com/${REPO}/releases/download/${tag}/${name}`, { headers, redirect: "follow" });
  if (!r.ok && r.status !== 206) return json({ error: `파일 없음 (${r.status})` }, r.status === 404 ? 404 : 502);
  const out = new Headers({ "Content-Type": MEDIA[name], "Cache-Control": "private, max-age=3600", "Accept-Ranges": "bytes" });
  for (const h of ["Content-Length", "Content-Range"]) if (r.headers.get(h)) out.set(h, r.headers.get(h));
  return new Response(r.body, { status: r.status, headers: out });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    try {
      if (path === "/api/health") return json({ ok: true, build: BUILD, configured: !!(env.GH_TOKEN && env.ADMIN_PASSWORD) });

      if (path.startsWith("/api/") && request.method === "POST") {
        // 다른 사이트에서 대신 누르기(CSRF) 방지: 쿠키 SameSite=Strict + 사용자 지정 머리글(교차 출처에서는 사전 확인 없이 못 붙인다)
        if (request.headers.get("X-Stay-Admin") !== "1") return json({ error: "잘못된 요청" }, 400);
      }

      if (path === "/api/login" && request.method === "POST") {
        if (!env.ADMIN_PASSWORD) return json({ error: "관리자 비밀번호가 아직 설정되지 않았습니다" }, 503);
        const ip = request.headers.get("CF-Connecting-IP") || "?";
        const f = fails.get(ip) || { n: 0, t: Date.now() };
        if (Date.now() - f.t > 10 * 60 * 1000) { f.n = 0; f.t = Date.now(); }
        if (f.n >= 8) return json({ error: "잠시 뒤 다시 시도하세요 (10분)" }, 429);
        const body = await request.json().catch(() => ({}));
        // 붙여넣기로 앞뒤에 들어간 공백·줄바꿈은 무시한다(시크릿 칸에 복사해 넣을 때 흔함 — 2026-10-14 로그인 실패 문의)
        if (await sameText(String(body.password || "").trim(), String(env.ADMIN_PASSWORD).trim())) {
          fails.delete(ip);
          return json({ ok: true }, 200, { "Set-Cookie": cookie(await makeSession(env), SESSION_DAYS * 86400) });
        }
        f.n += 1;
        fails.set(ip, f);
        await new Promise((r) => setTimeout(r, 800));
        return json({ error: "비밀번호가 맞지 않습니다" }, 401);
      }

      if (path === "/api/logout" && request.method === "POST") {
        return json({ ok: true }, 200, { "Set-Cookie": cookie("", 0) });
      }

      if (path.startsWith("/api/")) {
        if (!(await authed(request, env))) return json({ error: "로그인이 필요합니다" }, 401);
        if (!env.GH_TOKEN) return json({ error: "GitHub 토큰이 아직 설정되지 않았습니다" }, 503);
        if (path === "/api/state" && request.method === "GET") return json(await state(env));
        if (path === "/api/run" && request.method === "POST") return json(await startRun(env, await request.json().catch(() => ({}))));
        if (path === "/api/cancel" && request.method === "POST") return json(await cancelRun(env, await request.json().catch(() => ({}))));
        if (path === "/api/discover" && request.method === "POST") return json(await startDiscover(env, await request.json().catch(() => ({}))));
        if (path === "/api/media" && (request.method === "GET" || request.method === "HEAD")) return media(env, url, request);
        return json({ error: "없는 주소" }, 404);
      }

      return env.ASSETS.fetch(request);
    } catch (e) {
      const status = e instanceof HttpError ? e.status : 500;
      return json({ error: String(e.message || e).replace(/gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+/g, "***") }, status >= 400 && status < 600 ? status : 500);
    }
  },
};
