// 숙소 쇼츠 관리실 — Cloudflare Worker (2026-10-14 운영자 "관리자 페이지는 언제 만들어?")
//
// 하는 일
//   - 비밀번호 하나로 로그인(쿠키 30일). 화면은 public/index.html (A 운영실 카드).
//   - GET  /api/state : 이번 달 쓴 돈 · 지금 도는 실행 · 최근 실행 · 후보 숙소 · 최근 결과(대본·검수)를 저장소에서 읽어 모은다.
//   - POST /api/run   : 미리보기(약 80원) / 정식 제작(약 2,500원, 화면에서 한 번 더 확인) — request.json 을 새 nonce 로 커밋한다.
//                       그 푸시가 stay-shorts-produce 워크플로를 깨운다(기존 돈 잠금·nonce 가드는 워크플로 쪽에 그대로).
//   - 실행 중이면 버튼을 막는다(운영 규칙: 제작 워크플로가 도는 동안 같은 브랜치에 푸시하지 않는다).
//   - 텔레그램은 진행 알림 전용(운영자 2026-10-14) — 이 페이지는 텔레그램을 쓰지 않는다.
//
// 비밀값(Cloudflare Worker secret — 배포 워크플로가 넣는다): GH_TOKEN · ADMIN_PASSWORD · SESSION_SECRET
// 토큰은 화면으로 절대 내보내지 않고, 오류 문구에도 담지 않는다.

const BUILD = "dev";
const REPO = "jtaechul/Product";
const BRANCH = "claude/stay-shorts-video-conversion-67hiin";
const P = "projects/stay-shorts-factory";
const WF = "stay-shorts-produce.yml";
const REQ_PATH = `${P}/requests/produce/request.json`;
const MONTH_CAP = 50000;                    // 운영자 확정 월 한도(veo.py MONTH_KRW 와 같은 값)
const COST = { preview: 80, produce: 2500 };  // 실측 평균: 미리보기 글·음성 약 80원 / 정식 제작(미니어처 3컷 + Veo 1컷 + 글·음성) 약 2,500원
const LABEL = { preview: "미리보기", produce: "정식 제작" };
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
  return r.status === 204 ? null : r.json();
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

async function listRuns(env, n = 8) {
  const d = await gh(env, `/repos/${REPO}/actions/workflows/${WF}/runs?branch=${encodeURIComponent(BRANCH)}&per_page=${n}`);
  return (d.workflow_runs || []).map((r) => ({
    id: r.id,
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
    krw: (rep.gemini_usage || {}).krw_est || 0,
    cuts: (s.cuts || []).map((c) => ({ i: c.i, caption: c.caption, narration: c.narration })),
  };
}

async function state(env) {
  const now = kstNow();
  const ym = now.toISOString().slice(0, 7);
  const [req, ledger, cands, folders, rep, titles, runs] = await Promise.all([
    readJson(env, REQ_PATH, {}),
    readJson(env, `${P}/state/spend.json`, []),
    readJson(env, `${P}/data/discover/latest/candidates.json`, {}),
    readJson(env, `${P}/link/data/folders.json`, {}),
    readJson(env, `${P}/data/runs/latest/report.json`, null),
    readJson(env, `${P}/state/hook_titles.json`, []),
    listRuns(env).catch((e) => ({ error: e.message })),
  ]);
  const runList = Array.isArray(runs) ? runs : [];
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
  }));
  return {
    build: BUILD,
    now: now.toISOString().slice(0, 16).replace("T", " "),
    money: monthSpend(ledger, ym),
    cost: COST,
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
    theme: { theme: cands.theme || req.theme || "", region: cands.region || req.region || "", month: cands.month || req.month || "" },
    folders: (folders.folders || []).map((f) => ({ title: f.title, hotels: (f.hotels || []).map((h) => ({ rank: h.rank, name: h.name })) })),
    last: lastResult(rep),
    hook_titles: (Array.isArray(titles) ? titles : []).slice(-4).reverse().map((t) => ({ title: t.title, type: t.type, stay: t.stay })),
  };
}

async function startRun(env, body) {
  const action = String(body.action || "");
  if (!(action in COST)) throw new HttpError(400, "알 수 없는 실행입니다");
  const stay = String(body.stay || "").trim();
  if (!stay) throw new HttpError(400, "숙소를 고르세요");
  const [req, ledger, cands, runs, last] = await Promise.all([
    gh(env, `/repos/${REPO}/contents/${encodeURI(REQ_PATH)}?ref=${encodeURIComponent(BRANCH)}`),
    readJson(env, `${P}/state/spend.json`, []),
    readJson(env, `${P}/data/discover/latest/candidates.json`, {}),
    listRuns(env, 5),
    gh(env, `/repos/${REPO}/commits?sha=${encodeURIComponent(BRANCH)}&path=${encodeURIComponent(REQ_PATH)}&per_page=1`).catch(() => []),
  ]);
  const cur = JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(String(req.content || "").replace(/\s/g, "")), (c) => c.charCodeAt(0))));
  const names = new Set([...(cands.candidates || []).map((c) => c.name), ...Object.keys(cur.official_urls || {})]);
  if (!names.has(stay)) throw new HttpError(400, "후보 목록에 없는 숙소입니다");
  if (runs.some((r) => r.active)) throw new HttpError(409, "지금 다른 실행이 돌고 있습니다. 끝난 뒤 다시 누르세요");
  // 커밋 직후 몇 초는 GitHub 에 실행이 아직 안 보인다 → 요청 파일이 2분 안에 바뀌었으면 연달아 누른 것으로 보고 막는다
  const lastAt = Date.parse((((last || [])[0] || {}).commit || {}).committer?.date || "") || 0;
  if (Date.now() - lastAt < 120 * 1000) throw new HttpError(409, "방금 시작한 실행이 준비 중입니다. 1~2분 뒤 '지금 상태'를 확인하세요");
  const now = kstNow();
  const money = monthSpend(ledger, now.toISOString().slice(0, 7));
  if (money.total + COST[action] > MONTH_CAP) {
    throw new HttpError(403, `이번 달 한도를 넘습니다 (쓴 돈 ${money.total.toLocaleString()}원 + 예상 ${COST[action].toLocaleString()}원 > ${MONTH_CAP.toLocaleString()}원)`);
  }
  if (action === "produce" && body.confirm !== true) throw new HttpError(400, "정식 제작은 화면에서 한 번 더 확인해야 합니다");

  const next = { ...cur };
  delete next.stage;
  delete next.reuse_only;
  delete next.reuse_runs;
  delete next.reuse_clips;
  const stamp = now.toISOString().slice(0, 10);
  const rand = b64url(crypto.getRandomValues(new Uint8Array(3)));
  next.nonce = `${stamp}-admin-${action}-${rand}`;
  next.mode = "solo";
  next.stay = stay;
  next.veo_approved = action === "produce";
  if (action === "preview") next.stage = "preview";
  next.note = `관리자 페이지 ${LABEL[action]} — ${stay} · 예상 약 ${COST[action].toLocaleString()}원 · ${now.toISOString().slice(0, 16).replace("T", " ")} KST`;
  const msg = `stay-shorts: 관리자 페이지 ${LABEL[action]} — ${stay} (${next.nonce})`;
  const put = await gh(env, `/repos/${REPO}/contents/${encodeURI(REQ_PATH)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: msg, content: b64utf8(JSON.stringify(next, null, 1) + "\n"), sha: req.sha, branch: BRANCH }),
  }).catch((e) => {
    if (e.status === 409 || e.status === 422) throw new HttpError(409, "요청 파일이 방금 바뀌었습니다. 새로고침 후 다시 누르세요");
    if (e.status === 403 || e.status === 404) throw new HttpError(502, "GitHub 토큰에 이 저장소 파일 쓰기 권한이 없습니다 (Contents: Read and write 필요)");
    throw e;
  });
  return { ok: true, nonce: next.nonce, action, stay, cost: COST[action], commit: (put.commit || {}).html_url || "" };
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
        if (await sameText(String(body.password || ""), env.ADMIN_PASSWORD)) {
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
        return json({ error: "없는 주소" }, 404);
      }

      return env.ASSETS.fetch(request);
    } catch (e) {
      const status = e instanceof HttpError ? e.status : 500;
      return json({ error: String(e.message || e).replace(/gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+/g, "***") }, status >= 400 && status < 600 ? status : 500);
    }
  },
};
