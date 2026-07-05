// 쇼츠/릴스 대시보드 — Cloudflare Worker (컨테이너 프록시 + 간단 접근 토큰)
// 요청 → Durable Object 기반 컨테이너(파이썬 대시보드 :8000)로 전달.
import { Container, getContainer } from "@cloudflare/containers";

export class Dashboard extends Container {
  defaultPort = 8000;
  sleepAfter = "20m"; // 마지막 요청 후 20분 뒤 절전 (생성 중엔 폴링이 깨어있게 유지)

  constructor(ctx, env) {
    super(ctx, env);
    // 워커 시크릿 → 컨테이너 환경변수 (Veo·Claude 호출용, 없으면 panzoom만 동작)
    this.envVars = {
      GEMINI_API_KEY: env.GEMINI_API_KEY ?? "",
      ANTHROPIC_API_KEY: env.ANTHROPIC_API_KEY ?? "",
    };
  }
}

const COOKIE = "dash_token";

function unauthorized() {
  return new Response(
    "<!doctype html><meta charset='utf-8'><body style='background:#070b10;color:#e8eef2;font-family:sans-serif;display:grid;place-items:center;height:100vh'>" +
    "<form method='GET' style='text-align:center'><h2>DEEP DIVE LOG</h2><p>접근 토큰을 입력하세요</p>" +
    "<input name='key' style='padding:10px;border-radius:8px;border:1px solid #345;background:#0a1018;color:#fff'>" +
    "<button style='padding:10px 16px;margin-left:8px'>입장</button></form></body>",
    { status: 401, headers: { "Content-Type": "text/html; charset=utf-8" } });
}

export default {
  async fetch(request, env) {
    // 선택적 토큰 게이트: DASH_TOKEN 시크릿이 설정된 경우에만 요구
    if (env.DASH_TOKEN) {
      const url = new URL(request.url);
      const qKey = url.searchParams.get("key");
      const cookies = request.headers.get("Cookie") || "";
      const hasCookie = cookies.split(/;\s*/).some((c) => c === `${COOKIE}=${env.DASH_TOKEN}`);
      if (qKey === env.DASH_TOKEN && !hasCookie) {
        url.searchParams.delete("key");
        return new Response(null, {
          status: 302,
          headers: {
            Location: url.pathname + (url.search || ""),
            "Set-Cookie": `${COOKIE}=${env.DASH_TOKEN}; Path=/; HttpOnly; Secure; Max-Age=2592000`,
          },
        });
      }
      if (!hasCookie && qKey !== env.DASH_TOKEN) return unauthorized();
    }
    return getContainer(env.DASHBOARD).fetch(request);
  },
};
