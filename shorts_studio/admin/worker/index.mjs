// 숏폼 동화 스튜디오 관리자 페이지 워커.
//
// 설계는 verdict-theater/admin/worker.js 를 따른다(손님이 이미 쓰고 있는 검증된 방식):
//   · 손님은 **비밀번호 하나로 로그인**한다. GitHub 토큰을 폰에서 만질 일이 없다.
//   · GitHub 토큰은 **워커 시크릿**으로만 존재한다. 브라우저에 절대 내려보내지 않는다.
//   · 큰 영상은 브라우저 → **보관함(KV)** 으로 조각내어 올리고, 워크플로가 받아 간다.
//     깃허브로 직접 올리지 않으므로 CORS 문제도, 토큰 쓰기 권한도 필요 없다.
//
// 필요한 시크릿: GH_TOKEN · ADMIN_PASSWORD · SESSION_SECRET (배포 워크플로가 등록)
// 필요한 바인딩: BLOB (KV) · ASSETS (정적 화면)

const REPO = "jtaechul/Product";
const BRANCH = "main";
const GH = "https://api.github.com";
const DIR = "shorts_studio/content";
const WF_SCRIPT = "shorts-studio-script.yml";
const WF_RENDER = "shorts-studio-render.yml";

const KV_CHUNK = 8 * 1024 * 1024;          // 조각 하나 8MB (KV 한 값 상한 25MB 안쪽)
const KV_MAX = 90 * 1024 * 1024;           // 영상 하나 최대 크기
const KV_TTL = 60 * 60 * 24 * 14;          // 14일 보관 — 며칠에 걸쳐 만드셔도 남아 있게
const MEDIA_PREFIX = `https://github.com/${REPO}/releases/download/`;

const JSON_H = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" };
const j = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: JSON_H });
const err = (msg, s = 400) => j({ error: msg }, s);

/* ── 로그인 (서명 쿠키) ─────────────────────────────── */
async function sign(env, value) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(env.SESSION_SECRET || "ss"),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function authed(req, env) {
  const m = (req.headers.get("Cookie") || "").match(/ss=([^;]+)/);
  if (!m) return false;
  const [val, mac] = decodeURIComponent(m[1]).split(".");
  if (!val || !mac) return false;
  return (await sign(env, val)) === mac;
}

async function login(req, env) {
  const { password } = await req.json().catch(() => ({}));
  if (!env.ADMIN_PASSWORD) return err("서버에 비밀번호가 설정되지 않았습니다.", 503);
  if (password !== env.ADMIN_PASSWORD) return err("비밀번호가 틀렸습니다.", 401);
  const val = String(Date.now());
  const cookie = `ss=${encodeURIComponent(val + "." + await sign(env, val))}` +
    "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000";
  return new Response(JSON.stringify({ ok: true }), {
    headers: { ...JSON_H, "Set-Cookie": cookie },
  });
}

/* ── GitHub (서버에서만 호출) ───────────────────────── */
async function gh(env, path, init = {}) {
  const r = await fetch(GH + path, {
    ...init,
    // 깃허브는 답에 '1분 재사용 가능'을 붙인다. 그대로 두면 방금 만든 대본이
    // 목록에 안 보여 "안 만들어졌다"로 오해하게 된다.
    cf: { cacheTtl: 0, cacheEverything: false },
    headers: {
      "Cache-Control": "no-cache",
      "Authorization": `Bearer ${env.GH_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "shorts-studio-admin",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers || {}),
    },
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.status === 204 ? {} : r.json();
}

function b64utf8(b64) {
  const bin = atob(String(b64 || "").replace(/\n/g, ""));
  return new TextDecoder("utf-8").decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

async function listRecords(env) {
  const files = await gh(env, `/repos/${REPO}/contents/${DIR}?ref=${BRANCH}`) || [];
  const jsons = files.filter((f) => f.name && f.name.endsWith(".json"));
  const out = [];
  for (const f of jsons) {
    const r = await gh(env, `/repos/${REPO}/contents/${f.path}?ref=${BRANCH}`);
    if (r && r.content) {
      try { out.push(JSON.parse(b64utf8(r.content))); } catch (_) { /* 깨진 파일은 건너뛴다 */ }
    }
  }
  out.sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  return out;
}

/* ── 보관함(KV) ─────────────────────────────────────── */
const bin_ = (env) => (env && env.BLOB ? env.BLOB : null);

// 흘러 들어오는 것을 조각내어 넣는다. 통째로 메모리에 올리면 워커가 죽는다.
async function blobPutStream(env, body, key) {
  const kv = bin_(env);
  const rd = body.getReader();
  let hold = [], held = 0, part = 0, total = 0;
  const flush = async () => {
    if (!held) return;
    await kv.put(`${key}.${part}`, await new Blob(hold).arrayBuffer(), { expirationTtl: KV_TTL });
    part += 1; total += held; hold = []; held = 0;
  };
  for (;;) {
    const { value, done } = await rd.read();
    if (done) break;
    hold.push(value); held += value.length;
    if (total + held > KV_MAX) throw new Error("TOO_BIG");
    if (held >= KV_CHUNK) await flush();
  }
  await flush();
  await kv.put(key, JSON.stringify({ parts: part, size: total, type: "video/mp4" }),
    { expirationTtl: KV_TTL });
  return total;
}

async function uploadScene(req, env, url) {
  const kv = bin_(env);
  if (!kv) return err("보관함(KV)이 붙어 있지 않습니다. 관리자 페이지를 다시 배포하세요.", 503);
  const id = url.searchParams.get("id") || "";
  const n = parseInt(url.searchParams.get("scene") || "0", 10);
  if (!/^[A-Za-z0-9가-힣._-]+$/.test(id) || !(n >= 1 && n <= 6)) return err("잘못된 요청입니다.");
  if (!req.body) return err("영상이 비었습니다.");

  // 열쇠에 임의 번호를 붙인다. 같은 이름을 다시 쓰면 보관함이 전 세계에 퍼지는
  // 1분 사이에 워크플로가 **옛 영상**을 받아 갈 수 있다.
  const key = `scene/${id}-${n}-${crypto.randomUUID()}`;
  let size;
  try {
    size = await blobPutStream(env, req.body, key);
  } catch (e) {
    if (String(e.message) === "TOO_BIG") return err("영상이 너무 큽니다(90MB 이하로 올려 주세요).", 413);
    throw e;
  }

  const idxKey = `idx/${id}`;
  const idx = JSON.parse((await kv.get(idxKey)) || "{}");
  idx[n] = { key, size, at: new Date().toISOString() };
  await kv.put(idxKey, JSON.stringify(idx), { expirationTtl: KV_TTL });
  return j({ ok: true, scene: n, size });
}

async function serveBlob(req, env, url, ok) {
  const kv = bin_(env);
  if (!kv) return err("보관함이 없습니다.", 503);
  const key = url.searchParams.get("key") || "";
  if (!/^[a-z]+\/[A-Za-z0-9가-힣._-]+$/.test(key)) return err("열쇠가 이상합니다.");
  // 워크플로(깃허브 러너)는 쿠키가 없다. 비밀번호 헤더로 들어온다.
  const pass = req.headers.get("x-ss-pass") || "";
  if (!ok && !(env.ADMIN_PASSWORD && pass === env.ADMIN_PASSWORD))
    return err("unauthorized", 401);
  const head = await kv.get(key);
  if (!head) return err("없습니다(14일이 지나 지워졌을 수 있습니다).", 404);
  const m = JSON.parse(head);
  let i = 0;
  const rs = new ReadableStream({
    async pull(c) {
      if (i >= m.parts) { c.close(); return; }
      const b = await kv.get(`${key}.${i}`, "arrayBuffer");
      i += 1;
      if (b) c.enqueue(new Uint8Array(b)); else c.error(new Error("조각이 없습니다"));
    },
  });
  return new Response(rs, {
    headers: { "Content-Type": m.type || "application/octet-stream", "Cache-Control": "no-store" },
  });
}

/* ── 완성본 재생 ────────────────────────────────────── */
// 깃허브 릴리스 주소는 attachment 로 내려와 아이폰 사파리가 인라인 재생을 거부한다.
// video/mp4 + inline 으로 바꿔 중계하고, Range(몇 번째 바이트부터)를 그대로 넘겨
// 탐색(seek)도 되게 한다. Range 를 무시하면 재생 자체가 안 된다.
async function playVideo(req, url) {
  const u = url.searchParams.get("u") || "";
  if (!u.startsWith(MEDIA_PREFIX)) return err("url not allowed", 403);
  const h = { "User-Agent": "shorts-studio-admin" };
  const range = req.headers.get("Range");
  if (range) h["Range"] = range;
  const r = await fetch(u, { headers: h, redirect: "follow" });
  if (!r.ok && r.status !== 206) return err("upstream " + r.status, 502);
  const out = new Headers({
    "Content-Type": "video/mp4",
    "Content-Disposition": "inline",
    "Accept-Ranges": "bytes",
    "Cache-Control": "public, max-age=3600",
  });
  for (const k of ["Content-Length", "Content-Range"]) {
    const v = r.headers.get(k);
    if (v) out.set(k, v);
  }
  return new Response(r.body, { status: r.status, headers: out });
}

/* ── 워크플로 실행 ──────────────────────────────────── */
async function runScript(req, env) {
  const b = await req.json().catch(() => ({}));
  const topic = String(b.topic || "").trim();
  if (!topic) return err("동화 주제를 입력하세요.");
  await gh(env, `/repos/${REPO}/actions/workflows/${WF_SCRIPT}/dispatches`, {
    method: "POST",
    body: JSON.stringify({
      ref: BRANCH,
      inputs: {
        topic,
        scenes: String(b.scenes || "4"),
        tool: String(b.tool || "Runway (Gen-3/Gen-4)"),
      },
    }),
  });
  return j({ ok: true });
}

async function runRender(req, env, url) {
  const kv = bin_(env);
  const b = await req.json().catch(() => ({}));
  const id = String(b.id || "");
  const count = parseInt(b.count || "0", 10);
  if (!kv) return err("보관함이 없습니다.", 503);
  const idx = JSON.parse((await kv.get(`idx/${id}`)) || "{}");
  const missing = [];
  for (let n = 1; n <= count; n += 1) if (!idx[n]) missing.push(n);
  if (missing.length) return err(`${missing.join(", ")}번 씬 영상을 먼저 올려 주세요.`);

  const origin = new URL(url).origin;
  const blobs = [];
  for (let n = 1; n <= count; n += 1) {
    blobs.push(`${origin}/api/blob?key=${encodeURIComponent(idx[n].key)}`);
  }
  await gh(env, `/repos/${REPO}/actions/workflows/${WF_RENDER}/dispatches`, {
    method: "POST",
    body: JSON.stringify({
      ref: BRANCH,
      inputs: {
        content_id: id,
        blobs: JSON.stringify(blobs),
        voice: String(b.voice || "ko-KR-SunHiNeural"),
        highlight: String(b.highlight || "노란색"),
        hq: String(b.hq || "false"),
      },
    }),
  });
  return j({ ok: true });
}

/* ── 라우팅 ─────────────────────────────────────────── */
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;
    if (p === "/health") return new Response("ok");
    if (p === "/api/login") return login(req, env);

    const ok = await authed(req, env);
    // 보관함은 워크플로도 받아 가므로 로그인 검사 전에 따로 처리한다.
    if (p === "/api/blob") return serveBlob(req, env, url, ok);

    if (p.startsWith("/api/")) {
      if (!ok) return err("로그인이 필요합니다.", 401);
      try {
        if (p === "/api/me") return j({ ok: true });
        if (p === "/api/list") return j({ items: await listRecords(env) });
        if (p === "/api/uploaded") {
          const idx = bin_(env)
            ? JSON.parse((await bin_(env).get(`idx/${url.searchParams.get("id") || ""}`)) || "{}")
            : {};
          return j({ scenes: Object.keys(idx).map(Number) });
        }
        if (p === "/api/upload") return uploadScene(req, env, url);
        if (p === "/api/script") return runScript(req, env);
        if (p === "/api/render") return runRender(req, env, url);
        if (p === "/api/video") return playVideo(req, url);
      } catch (e) {
        return err(String(e.message || e), 500);
      }
      return err("없는 주소입니다.", 404);
    }

    // 화면은 절대 캐시하지 않는다. 고쳐 배포해도 폰이 옛 화면을 계속 보여 주는 일이 있었다.
    const res = await env.ASSETS.fetch(req);
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("text/html")) {
      const h = new Headers(res.headers);
      h.set("Cache-Control", "no-store, must-revalidate");
      return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
    }
    return res;
  },
};
