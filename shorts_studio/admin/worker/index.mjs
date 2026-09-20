// 숏폼 동화 스튜디오 관리자 페이지 워커.
//
// 설계는 verdict-theater/admin/worker.js 를 따른다(손님이 이미 쓰고 있는 검증된 방식):
//   · 손님은 **비밀번호 하나로 로그인**한다. GitHub 토큰을 폰에서 만질 일이 없다.
//   · GitHub 토큰은 **워커 시크릿**으로만 존재한다. 브라우저에 절대 내려보내지 않는다.
//   · 씬 영상은 브라우저 → 워커 → **깃허브 릴리스**. 워커가 자기 토큰으로 올린다.
//     깃허브로 직접 올리지 않으므로 CORS 문제도, 토큰 쓰기 권한도 필요 없다.
//
// 필요한 시크릿: GH_TOKEN · ADMIN_PASSWORD · SESSION_SECRET (배포 워크플로가 등록)
// 필요한 바인딩: ASSETS (정적 화면)

// 배포할 때 커밋 번호로 바뀐다. 손님이 "또 그러네" 하실 때 폰에 뜬 화면이
// 고치기 전 것인지 후의 것인지 /health 로 바로 알기 위해서다.
const BUILD = "dev";

const REPO = "jtaechul/Product";
const BRANCH = "main";
const GH = "https://api.github.com";
const DIR = "shorts_studio/content";
const WF_SCRIPT = "shorts-studio-script.yml";
const WF_RENDER = "shorts-studio-render.yml";

const UPLOADS = "https://uploads.github.com";
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

/* ── 씬 영상 보관 (GitHub Release) ──────────────────── */
// 브라우저 → 워커 → 깃허브. 워커가 자기 토큰으로 올리므로 브라우저는 토큰을
// 만질 일이 없고, 같은 출처로만 통신하니 CORS 문제도 없다.
// (예전엔 클라우드플레어 보관함을 거쳤는데, 그 토큰에 보관함 권한이 없어 막혔다.
//  깃허브에 바로 두면 14일 만료도, 용량 제한도, 배포 때 보관함 만드는 단계도 사라진다.)

const sceneName = (n) => `scene${String(n).padStart(2, "0")}.mp4`;
const CHAR_NAME = "character.png";   // 인물 참조 이미지 — 모든 씬의 기준

async function release(env, id, create) {
  const tag = `moviegen-${id}`;
  let rel = await gh(env, `/repos/${REPO}/releases/tags/${tag}`);
  if (!rel && create) {
    rel = await gh(env, `/repos/${REPO}/releases`, {
      method: "POST",
      body: JSON.stringify({
        tag_name: tag, name: `숏폼 동화 ${id}`,
        body: "관리자 페이지가 올린 씬 영상과 완성본이 담깁니다.",
        make_latest: "false",
      }),
    });
  }
  return rel;
}

async function uploadScene(req, env, url) {
  const id = url.searchParams.get("id") || "";
  const what = url.searchParams.get("scene") || "";
  const isChar = what === "character";
  const n = parseInt(what, 10);
  if (!/^[A-Za-z0-9._-]+$/.test(id) || (!isChar && !(n >= 1 && n <= 6)))
    return err("잘못된 요청입니다.");
  if (!req.body) return err("파일이 비었습니다.");

  const rel = await release(env, id, true);
  const name = isChar ? CHAR_NAME : sceneName(n);
  // 같은 이름이 남아 있으면 깃허브가 422 로 거절한다. 먼저 지운다.
  const old = (rel.assets || []).find((a) => a.name === name);
  if (old) await gh(env, `/repos/${REPO}/releases/assets/${old.id}`, { method: "DELETE" });

  const r = await fetch(`${UPLOADS}/repos/${REPO}/releases/${rel.id}/assets?name=${name}`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GH_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": req.headers.get("Content-Type")
        || (isChar ? "image/png" : "video/mp4"),
      "User-Agent": "shorts-studio-admin",
    },
    body: req.body,
  });
  if (!r.ok) {
    // 403 은 거의 항상 토큰 권한 문제다. 깃허브의 영어 답 대신 할 일을 알려 준다.
    if (r.status === 403 || r.status === 404) {
      return err("영상을 올릴 권한이 없습니다. MOVIEGEN_ADMIN_GH_TOKEN 의 "
                 + "Contents 권한을 'Read and write' 로 바꿔 주세요.", 403);
    }
    return err(`업로드 실패 ${r.status} ${(await r.text()).slice(0, 150)}`, 502);
  }
  return j({ ok: true, scene: isChar ? "character" : n });
}

async function uploadedScenes(env, id) {
  const rel = await release(env, id, false);
  const assets = (rel && rel.assets) || [];
  const names = new Set(assets.map((a) => a.name));
  const out = [];
  for (let n = 1; n <= 6; n += 1) if (names.has(sceneName(n))) out.push(n);
  const ch = assets.find((a) => a.name === CHAR_NAME);
  return { scenes: out, character: ch ? ch.browser_download_url : null };
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
  const isImg = /\.png(\?|$)/i.test(u);
  const out = new Headers({
    "Content-Type": isImg ? "image/png" : "video/mp4",
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

async function runRender(req, env) {
  const b = await req.json().catch(() => ({}));
  const id = String(b.id || "");
  const count = parseInt(b.count || "0", 10);
  const have = new Set((await uploadedScenes(env, id)).scenes);
  const missing = [];
  for (let n = 1; n <= count; n += 1) if (!have.has(n)) missing.push(n);
  if (missing.length) return err(`${missing.join(", ")}번 씬 영상을 먼저 올려 주세요.`);

  await gh(env, `/repos/${REPO}/actions/workflows/${WF_RENDER}/dispatches`, {
    method: "POST",
    body: JSON.stringify({
      ref: BRANCH,
      inputs: {
        content_id: id,
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
    if (p === "/health") return new Response("ok " + BUILD);
    if (p === "/api/login") return login(req, env);

    const ok = await authed(req, env);
    if (p.startsWith("/api/")) {
      if (!ok) return err("로그인이 필요합니다.", 401);
      try {
        if (p === "/api/me") return j({ ok: true });
        if (p === "/api/list") return j({ items: await listRecords(env) });
        if (p === "/api/uploaded")
          return j(await uploadedScenes(env, url.searchParams.get("id") || ""));
        if (p === "/api/upload") return uploadScene(req, env, url);
        if (p === "/api/script") return runScript(req, env);
        if (p === "/api/render") return runRender(req, env);
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
