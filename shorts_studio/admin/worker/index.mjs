// 숏폼 동화 스튜디오 관리자 페이지 워커 — 정적 에셋 서빙 + 두 개의 프록시.
// 서버 시크릿 없음: GitHub API는 브라우저가 사용자 개인 토큰으로 직접 호출한다.
//
// /media — GitHub Release 다운로드 URL은 octet-stream + attachment 로 응답해
//   iOS Safari <video>가 인라인 재생을 거부한다(검은 화면). video/mp4 + inline 으로
//   바꿔 중계하고 Range 요청을 넘겨 스트리밍 탐색도 되게 한다.
// /ghup — 브라우저 → uploads.github.com 직접 업로드가 CORS로 막히는 경우의 폴백.
// (둘 다 projects/coupang-shorts-factory/admin 의 검증된 구현을 이식.)

const OWNER = "jtaechul";
const REPO = "Product";
const MEDIA_PREFIX = `https://github.com/${OWNER}/${REPO}/releases/download/`;
const UPLOAD_PREFIX = `https://uploads.github.com/repos/${OWNER}/${REPO}/releases/`;
const MEDIA_TYPES = { mp4: "video/mp4", mov: "video/quicktime", m4v: "video/x-m4v" };

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
  const h = { "User-Agent": "shorts-studio-admin" };
  const range = request.headers.get("Range");
  if (range) h["Range"] = range;
  const resp = await fetch(u, { headers: h, redirect: "follow" });
  if (!resp.ok && resp.status !== 206) return j({ error: "upstream " + resp.status }, 502);
  const out = new Headers();
  out.set("Content-Type", type);
  out.set("Content-Disposition", "inline");
  out.set("Accept-Ranges", "bytes");
  out.set("Cache-Control", "public, max-age=3600");
  for (const k of ["Content-Length", "Content-Range"]) {
    const v = resp.headers.get(k);
    if (v) out.set(k, v);
  }
  return new Response(resp.body, { status: resp.status, headers: out });
}

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
      "User-Agent": "shorts-studio-admin",
    },
    body: request.body,
  });
  return new Response(resp.body, {
    status: resp.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return new Response("ok");
    if (url.pathname === "/media") return mediaProxy(request, url);
    if (url.pathname === "/ghup") return ghUploadProxy(request, url);

    // 그 외는 정적 에셋. HTML은 배포 즉시 반영되도록 캐시를 끈다.
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
