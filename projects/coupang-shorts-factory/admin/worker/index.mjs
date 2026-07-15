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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return new Response("ok");
    if (url.pathname === "/media") return mediaProxy(request, url);
    if (url.pathname === "/ghup") return ghUploadProxy(request, url);
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
