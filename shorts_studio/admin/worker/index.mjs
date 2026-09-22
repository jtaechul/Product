// 숏폼 동화 스튜디오 관리자 페이지 워커.
//
// 설계는 verdict-theater/admin/worker.js 를 따른다(손님이 이미 쓰고 있는 검증된 방식):
//   · 손님은 **아이디 + 비밀번호로 로그인**한다. GitHub 토큰을 폰에서 만질 일이 없다.
//   · GitHub 토큰은 **워커 시크릿**으로만 존재한다. 브라우저에 절대 내려보내지 않는다.
//   · 씬 영상은 브라우저 → 워커 → **깃허브 릴리스**. 워커가 자기 토큰으로 올린다.
//     깃허브로 직접 올리지 않으므로 CORS 문제도, 토큰 쓰기 권한도 필요 없다.
//
// 필요한 시크릿: GH_TOKEN · USERS(또는 ADMIN_PASSWORD) · SESSION_SECRET · KEY_SECRET
//                (배포 워크플로가 등록한다)
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

/* ── 로그인 (아이디 + 비밀번호, 서명 쿠키) ───────────── */
// 사용자 목록은 워커 시크릿 USERS 에 JSON 으로 둔다. 브라우저로 내려가지 않는다.
//   [{"id":"jt","pw":"비밀번호","name":"보여줄 이름"}, ...]
// USERS 가 없으면 예전처럼 ADMIN_PASSWORD 하나로 쓰는 1인 모드로 동작한다.
function users(env) {
  const out = [];
  try {
    const list = JSON.parse(env.USERS || "[]");
    if (Array.isArray(list)) {
      for (const u of list) {
        if (u && u.id && u.pw) {
          out.push({ id: String(u.id), pw: String(u.pw), name: String(u.name || u.id) });
        }
      }
    }
  } catch (_) { /* 시크릿이 깨져도 아래 관리자 계정으로 들어올 수 있다 */ }

  // ⭐ 관리자 계정은 **언제나** 살려 둔다.
  // 예전엔 USERS 가 있으면 ADMIN_PASSWORD 를 통째로 무시했다. 그래서 사용자 칸을
  // 하나 등록한 순간 관리자 비밀번호가 죽었고, 그걸 아무리 바꿔도 안 들어가졌다
  // (실제로 겪었다). 목록을 잘못 넣어도 주인은 못 잠기게 한다.
  if (env.ADMIN_PASSWORD && !out.some((u) => u.id === "admin")) {
    out.push({ id: "admin", pw: env.ADMIN_PASSWORD, name: "관리자" });
  }
  return out;
}

async function sign(env, value) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(env.SESSION_SECRET || "ss"),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value));
  return [...new Uint8Array(mac)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// 로그인했으면 사용자 아이디를, 아니면 빈 문자열을 돌려준다.
async function whoami(req, env) {
  const m = (req.headers.get("Cookie") || "").match(/ss=([^;]+)/);
  if (!m) return "";
  const raw = decodeURIComponent(m[1]);
  const at = raw.lastIndexOf(".");
  if (at < 0) return "";
  const val = raw.slice(0, at);
  if ((await sign(env, val)) !== raw.slice(at + 1)) return "";
  const uid = val.split("|")[0];
  // 목록에서 빠진 사용자는 바로 막힌다(시크릿에서 지우면 그 즉시 로그아웃).
  return users(env).some((u) => u.id === uid) ? uid : "";
}

async function login(req, env) {
  const b = await req.json().catch(() => ({}));
  const list = users(env);
  if (!list.length) return err("서버에 사용자가 설정되지 않았습니다.", 503);
  const id = String(b.id || "").trim();
  const pw = String(b.password || "");
  // 아이디를 비워도 들어가진다. 예전엔 비밀번호 하나로 쓰던 화면이라, 아이디를 꼭
  // 치게 만들면 쓰던 사람이 멀쩡한 비밀번호로도 막힌다.
  const hit = id
    ? list.find((u) => u.id === id && u.pw === pw)
    : list.find((u) => u.pw === pw);
  if (!hit) return err("아이디나 비밀번호가 틀렸습니다.", 401);
  const val = `${hit.id}|${Date.now()}`;
  const cookie = `ss=${encodeURIComponent(val + "." + await sign(env, val))}` +
    "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000";
  return new Response(JSON.stringify({ ok: true, id: hit.id, name: hit.name }), {
    headers: { ...JSON_H, "Set-Cookie": cookie },
  });
}

// 쿠키를 지운다. 쿠키가 이미 망가졌어도 눌리게 로그인 검사 앞에 둔다
// — 못 들어가는데 로그아웃도 안 되면 손쓸 방법이 없다.
function logout() {
  return new Response(JSON.stringify({ ok: true }), {
    headers: {
      ...JSON_H,
      "Set-Cookie": "ss=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0",
    },
  });
}

/* ── 개인 API 키 봉하기 ─────────────────────────────── */
// 실제 작업은 GitHub Actions 에서 돌아가는데, 이 저장소는 **공개**라
// 워크플로 입력값이 실행 기록 화면에 그대로 보인다. 사용자의 API 키를 날것으로
// 넘기면 전 세계에 공개된다. 그래서 워커가 자물쇠를 채워 보내고,
// 같은 열쇠(KEY_SECRET)를 가진 Actions 만 연다. 기록에는 알아볼 수 없는 문자열만 남는다.
async function sealKey(env, plain) {
  const text = String(plain || "").trim();
  if (!text) return "";
  const secret = env.KEY_SECRET || env.SESSION_SECRET || "ss";
  const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(secret));
  const key = await crypto.subtle.importKey("raw", hash, { name: "AES-GCM" }, false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv }, key, new TextEncoder().encode(text)));
  const out = new Uint8Array(iv.length + ct.length);
  out.set(iv); out.set(ct, iv.length);
  let bin = "";
  for (const byte of out) bin += String.fromCharCode(byte);
  return btoa(bin);
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

// 작품 주인 판정. owner 가 없는 옛 기록은 1인 모드 시절 것이라 admin 소유로 본다.
const ownerOf = (rec) => String((rec && rec.owner) || "admin");

async function loadRecord(env, id) {
  if (!/^[A-Za-z0-9._-]+$/.test(id)) return null;
  const r = await gh(env, `/repos/${REPO}/contents/${DIR}/${id}.json?ref=${BRANCH}`);
  if (!r || !r.content) return null;
  try { return JSON.parse(b64utf8(r.content)); } catch (_) { return null; }
}

// 남의 작품을 건드리지 못하게 한다. 없는 작품은 통과시킨다(아직 대본 커밋 전일 수 있다).
async function mine(env, id, uid) {
  const rec = await loadRecord(env, id);
  return !rec || ownerOf(rec) === uid;
}

async function listRecords(env, uid) {
  const files = await gh(env, `/repos/${REPO}/contents/${DIR}?ref=${BRANCH}`) || [];
  const jsons = files.filter((f) => f.name && f.name.endsWith(".json"));
  const out = [];
  for (const f of jsons) {
    const r = await gh(env, `/repos/${REPO}/contents/${f.path}?ref=${BRANCH}`);
    if (r && r.content) {
      try {
        const rec = JSON.parse(b64utf8(r.content));
        if (ownerOf(rec) === uid) out.push(rec);     // 남의 작품은 목록에 안 보인다
      } catch (_) { /* 깨진 파일은 건너뛴다 */ }
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

const MAX_SCENES = 20;
const MAX_CHARS = 3;
const sceneName = (n) => `scene${String(n).padStart(2, "0")}.mp4`;
// 인물 참조 이미지 — 모든 씬의 기준. 등장인물이 여럿이면 사람마다 한 장씩 둔다.
// character.png 는 인물이 한 명뿐이던 시절의 이름이라 1번으로 함께 읽어 준다.
const charName = (n) => `character${String(n).padStart(2, "0")}.png`;
const LEGACY_CHAR = "character.png";
const COVER_NAME = "cover.png";      // 맨 앞 1.8초에 뜨는 표지

// 같은 이름으로 다시 올리면 주소가 그대로라, 폰이 옛 그림을 계속 보여 준다.
// 자산 번호는 올릴 때마다 바뀌므로 주소 뒤에 붙여 "다른 주소"로 만든다.
const fresh = (a) => (a ? `${a.browser_download_url}?v=${a.id}` : null);

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

async function uploadScene(req, env, url, uid) {
  const id = url.searchParams.get("id") || "";
  if (!(await mine(env, id, uid))) return err("내 작품이 아닙니다.", 403);
  const what = url.searchParams.get("scene") || "";
  // "3" = 3번 씬 영상 / "char2" = 2번 등장인물 이미지 / "character" = 옛 이름(1번 인물)
  // "cover" = 표지 이미지
  const isCover = what === "cover";
  const cm = /^char(?:acter)?(\d*)$/.exec(what);
  const isChar = !!cm;
  const ci = isChar ? (parseInt(cm[1], 10) || 1) : 0;
  const n = parseInt(what, 10);
  const okTarget = isCover ? true
    : isChar ? (ci >= 1 && ci <= MAX_CHARS)
    : (n >= 1 && n <= MAX_SCENES);
  if (!/^[A-Za-z0-9._-]+$/.test(id) || !okTarget)
    return err("잘못된 요청입니다.");
  if (!req.body) return err("파일이 비었습니다.");

  const rel = await release(env, id, true);
  const name = isCover ? COVER_NAME : isChar ? charName(ci) : sceneName(n);
  const isImage = isCover || isChar;
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
        || (isImage ? "image/png" : "video/mp4"),
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
  return j({ ok: true, scene: isCover ? "cover" : isChar ? `char${ci}` : n });
}

async function uploadedScenes(env, id) {
  const rel = await release(env, id, false);
  const assets = (rel && rel.assets) || [];
  const names = new Set(assets.map((a) => a.name));
  const out = [];
  for (let n = 1; n <= MAX_SCENES; n += 1) if (names.has(sceneName(n))) out.push(n);
  // characters[i] = i+1 번 인물의 이미지 주소(없으면 null)
  const characters = [];
  for (let i = 1; i <= MAX_CHARS; i += 1) {
    let a = assets.find((x) => x.name === charName(i));
    if (!a && i === 1) a = assets.find((x) => x.name === LEGACY_CHAR);
    characters.push(fresh(a));
  }
  const cover = fresh(assets.find((x) => x.name === COVER_NAME));
  return { scenes: out, characters, character: characters[0], cover };
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
    // 같은 주소에 새 파일을 올리는 일이 잦다(인물 이미지 교체, 다시 렌더).
    // 여기서 캐시를 허용하면 폰이 옛 그림·옛 영상을 계속 보여 준다 — 실제로 겪었다.
    "Cache-Control": isImg ? "no-store" : "private, max-age=60",
  });
  for (const k of ["Content-Length", "Content-Range"]) {
    const v = r.headers.get(k);
    if (v) out.set(k, v);
  }
  return new Response(r.body, { status: r.status, headers: out });
}

/* ── 워크플로 실행 ──────────────────────────────────── */
async function runScript(req, env, uid) {
  const b = await req.json().catch(() => ({}));
  const topic = String(b.topic || "").trim();
  if (!topic) return err("동화 주제를 입력하세요.");
  const scenes = Math.max(5, Math.min(MAX_SCENES, parseInt(b.scenes, 10) || 8));
  await gh(env, `/repos/${REPO}/actions/workflows/${WF_SCRIPT}/dispatches`, {
    method: "POST",
    body: JSON.stringify({
      ref: BRANCH,
      inputs: {
        topic,
        scenes: String(scenes),
        tool: String(b.tool || "Runway (Gen-3/Gen-4)"),
        owner: uid,
        gemini_key_enc: await sealKey(env, b.gemini_key),
      },
    }),
  });
  return j({ ok: true });
}

async function runRender(req, env, uid) {
  const b = await req.json().catch(() => ({}));
  const id = String(b.id || "");
  if (!(await mine(env, id, uid))) return err("내 작품이 아닙니다.", 403);
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
        engine: String(b.engine || "gemini"),
        voice: String(b.voice || "Sulafat"),
        gemini_key_enc: await sealKey(env, b.gemini_key),
        band_bottom: String(b.band_bottom || "0.16"),
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
    if (p === "/api/logout") return logout();

    const uid = await whoami(req, env);
    if (p.startsWith("/api/")) {
      if (!uid) return err("로그인이 필요합니다.", 401);
      try {
        if (p === "/api/me") {
          const me = users(env).find((u) => u.id === uid);
          return j({ ok: true, id: uid, name: (me && me.name) || uid });
        }
        if (p === "/api/list") return j({ items: await listRecords(env, uid) });
        if (p === "/api/uploaded")
          return j(await uploadedScenes(env, url.searchParams.get("id") || ""));
        if (p === "/api/upload") return uploadScene(req, env, url, uid);
        if (p === "/api/script") return runScript(req, env, uid);
        if (p === "/api/render") return runRender(req, env, uid);
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
