// 판매 페이지 전용 주소. 첫 화면(/)이 곧 판매 페이지이고, 판매 페이지가 쓰는 상품 사진 주소(/api/cover)만 본체로 넘긴다.
const ALLOW = [/^\/$/, /^\/shop\/?$/, /^\/books(\.html)?\/?$/, /^\/api\/cover$/, /^\/favicon/, /^\/robots\.txt$/];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('Method Not Allowed', { status: 405 });
    if (!ALLOW.some(r => r.test(url.pathname))) return Response.redirect(`${url.origin}/`, 302);
    const target = new URL(url.pathname === '/' ? '/shop' : url.pathname, 'https://book-carousel.jtaechul.workers.dev');
    target.search = url.search;
    return env.MAIN.fetch(new Request(target, request));
  },
};
