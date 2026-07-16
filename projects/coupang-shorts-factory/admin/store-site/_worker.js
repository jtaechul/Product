// 미래마켓 공개 스토어 — Cloudflare Pages(_worker.js 고급 모드)용 진입점.
// 정적 index.html(store.html) + store-catalog.json 을 서빙하고, /store-img 이미지 프록시만 코드로 처리.
// (관리자 워커 admin/worker/index.mjs 의 storeImgProxy 와 동일 로직 — 개방 프록시 방지 화이트리스트.)
// 배포: .github/workflows/deploy-store-page.yml 이 admin/public/store.html·store-catalog.json 변경 시
//       dist/ 로 스테이징해 `wrangler pages deploy` → https://miraemarket.pages.dev

const IMG_HOST_OK = [
  "coupangcdn.com", "coupang.com", "pstatic.net", "phinf.naver.net",
  "picsum.photos", "images.unsplash.com", "githubusercontent.com", "media.giphy.com",
];

const j = (obj, status = 200) => new Response(JSON.stringify(obj), {
  status, headers: { "Content-Type": "application/json; charset=utf-8" },
});

async function storeImgProxy(url) {
  let src = url.searchParams.get("u") || "";
  try {
    const h = new URL(src).hostname;
    if (!IMG_HOST_OK.some((d) => h === d || h.endsWith("." + d))) return j({ error: "host not allowed" }, 403);
  } catch { return j({ error: "bad url" }, 400); }
  const resp = await fetch(src, { headers: { "User-Agent": "miraemarket-store", "Referer": "" }, redirect: "follow" });
  if (!resp.ok) return j({ error: "upstream " + resp.status }, 502);
  const ct = resp.headers.get("Content-Type") || "image/jpeg";
  if (!ct.startsWith("image/")) return j({ error: "not an image" }, 415);
  const out = new Headers();
  out.set("Content-Type", ct);
  out.set("Cache-Control", "public, max-age=86400");
  out.set("Access-Control-Allow-Origin", "*");
  return new Response(resp.body, { status: 200, headers: out });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/store-img") return storeImgProxy(url);
    if (url.pathname === "/health") return new Response("ok");
    // /store 로 들어와도 홈으로(옛 워커 경로 습관 호환)
    if (url.pathname === "/store" || url.pathname === "/store/") {
      return Response.redirect(new URL("/", url).toString() + url.hash, 301);
    }
    return env.ASSETS.fetch(request);
  },
};
