// 쿠팡 쇼츠 관리자 페이지 워커 — 정적 에셋 서빙 + GitHub Release 미디어 프록시(/media).
// 서버 시크릿·서버 로직 없음(노코드 원칙). GitHub API는 브라우저가 사용자 PAT로 직접 호출.
//
// 왜 /media 프록시가 필요한가(실제 결함): GitHub Release 다운로드 URL은
// Content-Type: application/octet-stream + Content-Disposition: attachment 로 응답해
// iOS Safari <video>가 인라인 재생을 거부한다(검은 화면 + 재생불가). 워커가 올바른
// video/mp4 + inline 으로 바꿔 중계하고 Range 요청을 그대로 전달해 스트리밍 탐색도 지원한다.
// (short-movie-generator/worker 의 검증된 패턴을 관리자 페이지에 이식.)

const OWNER = "jtaechul";
const REPO = "Product";
const MEDIA_PREFIX = "https://github.com/" + OWNER + "/" + REPO + "/releases/download/";
// gif: 후보 이미지에 Giphy/Openverse 움짤이 섞여 들어와 썸네일이 깨지던 문제(gif 미허용→403) 해결.
// mov: 아이폰 화면녹화 제품영상(.mov) 인라인 재생.
const MEDIA_TYPES = { mp4: "video/mp4", mov: "video/quicktime", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", gif: "image/gif", json: "application/json" };

function j(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

async function mediaProxy(request, url) {
  const u = url.searchParams.get("u") || "";
  if (!u.startsWith(MEDIA_PREFIX)) return j({ error: "url not allowed" }, 403); // 개방 프록시 방지
  const ext = ((u.split("?")[0] || "").split(".").pop() || "").toLowerCase();
  const type = MEDIA_TYPES[ext];
  if (!type) return j({ error: "type not allowed" }, 403);
  const h = { "User-Agent": "shorts-admin" };
  const range = request.headers.get("Range");
  if (range) h["Range"] = range; // 스트리밍 탐색(seek) 지원
  const resp = await fetch(u, { headers: h, redirect: "follow" });
  if (!resp.ok && resp.status !== 206) return j({ error: "upstream " + resp.status }, 502);
  const out = new Headers();
  out.set("Content-Type", type);
  out.set("Content-Disposition", "inline"); // iOS '파일 열기' 화면 전환 방지 → 인라인 재생
  out.set("Accept-Ranges", "bytes");
  out.set("Cache-Control", "public, max-age=3600");
  for (const k of ["Content-Length", "Content-Range"]) {
    const v = resp.headers.get(k);
    if (v) out.set(k, v);
  }
  return new Response(resp.body, { status: resp.status, headers: out });
}

// 제품 영상 릴리스 자산 업로드 프록시(/ghup): 브라우저 → uploads.github.com 직접 업로드가
// CORS로 막히는 환경 대비 폴백. 같은 출처(POST /ghup?u=...)로 받아 서버 측에서 중계한다.
// 개방 프록시 방지: 이 저장소의 releases 업로드 URL만 허용, 토큰은 요청 헤더의 사용자 PAT 그대로 전달.
const UPLOAD_PREFIX = "https://uploads.github.com/repos/" + OWNER + "/" + REPO + "/releases/";

async function ghUploadProxy(request, url) {
  if (request.method !== "POST") return j({ error: "POST only" }, 405);
  const u = url.searchParams.get("u") || "";
  if (!u.startsWith(UPLOAD_PREFIX)) return j({ error: "url not allowed" }, 403);
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return j({ error: "missing token" }, 401);
  const resp = await fetch(u, {
    method: "POST",
    headers: {
      "Authorization": auth,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": request.headers.get("Content-Type") || "application/octet-stream",
      "User-Agent": "shorts-admin",
    },
    body: request.body,
  });
  return new Response(resp.body, {
    status: resp.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

// 스토어(공개 상품 페이지) 이미지 프록시(/store-img): 쿠팡·네이버 등이 <img> 핫링크를 막거나
// http로 오는 이미지 주소를 안전하게 중계한다. 개방 프록시 방지로 이미지 호스트를 화이트리스트한다.
// (허용 밖 호스트는 store.html이 원본 URL로 자동 폴백하므로 여기선 403만 반환.)
const IMG_HOST_OK = [
  "coupangcdn.com", "coupang.com", "pstatic.net", "phinf.naver.net",
  "picsum.photos", "images.unsplash.com", "githubusercontent.com", "media.giphy.com",
];
// 이 저장소 릴리스 자산(상품 사진 후보 등)만 github.com에서 추가 허용 — 경로 prefix 고정(개방 프록시 방지).
const REPO_RELEASE_PREFIX = "/jtaechul/Product/releases/download/";
const EXT_CT = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp", gif: "image/gif" };
async function storeImgProxy(url) {
  let src = url.searchParams.get("u") || "";
  let u;
  try { u = new URL(src); } catch { return j({ error: "bad url" }, 400); }
  const h = u.hostname;
  const hostOk = IMG_HOST_OK.some((d) => h === d || h.endsWith("." + d));
  const relOk = h === "github.com" && u.pathname.startsWith(REPO_RELEASE_PREFIX);
  if (!hostOk && !relOk) return j({ error: "host not allowed" }, 403);
  const resp = await fetch(src, { headers: { "User-Agent": "shorts-admin", "Referer": "" }, redirect: "follow" });
  if (!resp.ok) return j({ error: "upstream " + resp.status }, 502);
  let ct = resp.headers.get("Content-Type") || "image/jpeg";
  if (!ct.startsWith("image/")) {
    const ext = (u.pathname.split(".").pop() || "").toLowerCase();
    if (relOk && EXT_CT[ext]) ct = EXT_CT[ext];   // 릴리스 자산은 octet-stream → 확장자로 보정
    else return j({ error: "not an image" }, 415);
  }
  const out = new Headers();
  out.set("Content-Type", ct);
  out.set("Cache-Control", "public, max-age=86400");
  out.set("Access-Control-Allow-Origin", "*");
  return new Response(resp.body, { status: 200, headers: out });
}

// /tik?u=<tiktok source_url> — 틱톡 원본 주소로 tikwm에서 '매번 신선한 재생 URL'을 받아 인라인 스트리밍.
// 왜: 관리자가 저장된 tikwm 재생주소를 직접 물리면 ① 만료 ② 핫링크/CORS 차단으로 검은 화면이 된다.
// 서버(워커)에서 재획득 후 중계하면 만료·차단이 동시에 해결된다(구간 편집기 미리보기 재생).
async function tikProxy(request, url) {
  const src = url.searchParams.get("u") || "";
  if (!/^https?:\/\/([\w.-]+\.)?(tiktok\.com|douyin\.com)\//i.test(src)) return j({ error: "url not allowed" }, 403);
  let play = "";
  try {
    const api = "https://www.tikwm.com/api/?hd=1&url=" + encodeURIComponent(src);
    const r = await fetch(api, { headers: { "User-Agent": "Mozilla/5.0", "Accept": "application/json" } });
    const data = ((await r.json()) || {}).data || {};
    play = data.hdplay || data.play || data.wmplay || "";
  } catch (_) { return j({ error: "resolve failed" }, 502); }
  if (!play) return j({ error: "no play url" }, 502);
  const playUrl = play.startsWith("http") ? play : ("https://www.tikwm.com" + play);
  const h = { "User-Agent": "Mozilla/5.0", "Referer": "https://www.tikwm.com/" };
  const range = request.headers.get("Range");
  if (range) h["Range"] = range;
  const resp = await fetch(playUrl, { headers: h, redirect: "follow" });
  if (!resp.ok && resp.status !== 206) return j({ error: "upstream " + resp.status }, 502);
  const out = new Headers();
  out.set("Content-Type", "video/mp4");
  out.set("Content-Disposition", "inline");
  out.set("Accept-Ranges", "bytes");
  out.set("Cache-Control", "public, max-age=600");
  out.set("Access-Control-Allow-Origin", "*");
  for (const k of ["Content-Length", "Content-Range"]) { const v = resp.headers.get(k); if (v) out.set(k, v); }
  return new Response(resp.body, { status: resp.status, headers: out });
}

// /stock?q=<kw>&src=<giphy|pixabay|pexels> — 서버 시크릿 키로 스톡 검색(브라우저가 별도 키를 받을 필요 없음).
// 반환: {items:[{url,thumb,type,id}]}. url은 produce가 제작 시점에 내려받아 삽입한다.
async function stockSearch(url, env) {
  const q = (url.searchParams.get("q") || "").trim();
  const src = (url.searchParams.get("src") || "giphy").toLowerCase();
  if (!q) return j({ items: [], error: "no query" });
  try {
    if (src === "giphy") {
      const k = env.SHORTS_GIPHY_API_KEY || env.GIPHY_API_KEY || "";
      if (!k) return j({ items: [], error: "no giphy key" });
      const r = await fetch("https://api.giphy.com/v1/gifs/search?api_key=" + encodeURIComponent(k)
        + "&q=" + encodeURIComponent(q) + "&limit=24&rating=pg-13");
      const data = ((await r.json()) || {}).data || [];
      const items = data.map((g) => ({
        url: ((((g.images || {}).original || {}).url) || "").split("?")[0],
        thumb: (((g.images || {}).fixed_width || {}).url) || "", type: "gif", id: "gy:" + g.id,
      })).filter((x) => x.url);
      return j({ items });
    }
    if (src === "pexels") {
      const k = env.SHORTS_PEXELS_API_KEY || "";
      if (!k) return j({ items: [], error: "no pexels key" });
      const r = await fetch("https://api.pexels.com/videos/search?query=" + encodeURIComponent(q) + "&per_page=24&orientation=portrait",
        { headers: { Authorization: k } });
      const vids = ((await r.json()) || {}).videos || [];
      const items = vids.map((v) => {
        const files = (v.video_files || []).filter((f) => f.file_type === "video/mp4").sort((a, b) => (a.width || 0) - (b.width || 0));
        const mid = files[Math.min(1, Math.max(0, files.length - 1))] || files[0];
        return { url: (mid && mid.link) || "", thumb: v.image || "", type: "mp4", id: "pe:" + v.id };
      }).filter((x) => x.url);
      return j({ items });
    }
    if (src === "pixabay") {
      const k = env.SHORTS_PIXABAY_API_KEY || "";
      if (!k) return j({ items: [], error: "no pixabay key" });
      const r = await fetch("https://pixabay.com/api/videos/?key=" + encodeURIComponent(k)
        + "&q=" + encodeURIComponent(q) + "&per_page=24&safesearch=true");
      const hits = ((await r.json()) || {}).hits || [];
      const items = hits.map((hp) => ({
        url: (((hp.videos || {}).medium || {}).url) || (((hp.videos || {}).small || {}).url) || "",
        thumb: "https://i.vimeocdn.com/video/" + hp.picture_id + "_295x166.jpg", type: "mp4", id: "px:" + hp.id,
      })).filter((x) => x.url);
      return j({ items });
    }
    return j({ items: [], error: "unknown src" });
  } catch (_) { return j({ items: [], error: "search failed" }); }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return new Response("ok");
    if (url.pathname === "/media") return mediaProxy(request, url);
    if (url.pathname === "/tik") return tikProxy(request, url);
    if (url.pathname === "/stock") return stockSearch(url, env);
    if (url.pathname === "/ghup") return ghUploadProxy(request, url);
    if (url.pathname === "/store-img") return storeImgProxy(url);
    // 공개 스토어 페이지: 깔끔한 URL(/store)로 정적 store.html을 서빙(프로필 링크용).
    if (url.pathname === "/store" || url.pathname === "/store/") {
      return env.ASSETS.fetch(new Request(new URL("/store.html", url), request));
    }
    // 그 외 경로는 정적 에셋(index.html 등). HTML은 배포 즉시 반영되도록 no-cache로 재발행
    // (브라우저가 옛 관리자 페이지를 캐시해 "안 바뀜"으로 보이던 문제 해결).
    const res = await env.ASSETS.fetch(request);
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("text/html")) {
      const h = new Headers(res.headers);
      h.set("Cache-Control", "no-cache, must-revalidate");
      return new Response(res.body, { status: res.status, statusText: res.statusText, headers: h });
    }
    return res;
  },
};
