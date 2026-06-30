const ALLOWED_ORIGIN = 'https://jtaechul.github.io';

const cors = {
  'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const DEFAULT_ORIGIN = '서울특별시 송파구 송파대로28길 28';

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    const url = new URL(request.url);
    const json = (body, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { ...cors, 'Content-Type': 'application/json' },
      });

    // ── 카카오 길찾기: 출발→목적지 자동차 경로(거리·소요시간·경로좌표) ──
    if (request.method === 'GET' && url.pathname === '/directions') {
      const dest = url.searchParams.get('dest');
      const origin = url.searchParams.get('origin') || DEFAULT_ORIGIN;
      if (!dest) return json({ error: 'no_dest' }, 400);

      const kakaoKey = await env.CONFIG.get('kakaoKey');
      if (!kakaoKey) return json({ error: 'no_kakao_key' }, 400);

      try {
        const oc = await geocode(origin, kakaoKey);
        const dc = await geocode(dest, kakaoKey);
        if (!oc) return json({ error: 'origin_geocode_failed', origin }, 422);
        if (!dc) return json({ error: 'dest_geocode_failed', dest }, 422);

        const dir = await fetch(
          'https://apis-navi.kakaomobility.com/v1/directions'
          + `?origin=${oc.x},${oc.y}&destination=${dc.x},${dc.y}`
          + '&priority=RECOMMEND&car_fuel=DIESEL&summary=false',
          { headers: { Authorization: `KakaoAK ${kakaoKey}` } }
        );
        if (!dir.ok) {
          const t = await dir.text();
          return json({ error: 'directions_failed', status: dir.status, detail: t.slice(0, 300) }, 502);
        }
        const data = await dir.json();
        const route = data?.routes?.[0];
        if (!route || route.result_code !== 0) {
          return json({ error: 'no_route', detail: route?.result_msg || '' }, 422);
        }

        // 경로 좌표 추출 (vertexes: [x,y,x,y,...]) → [[x,y],...], 다운샘플
        const pts = [];
        for (const sec of route.sections || []) {
          for (const road of sec.roads || []) {
            const v = road.vertexes || [];
            for (let i = 0; i + 1 < v.length; i += 2) pts.push([v[i], v[i + 1]]);
          }
        }
        const path = downsample(pts, 300);

        return json({
          ok: true,
          oneWayMeters: route.summary?.distance ?? null,
          durationSec: route.summary?.duration ?? null,
          tollFare: route.summary?.fare?.toll ?? null,
          origin: { x: oc.x, y: oc.y, label: oc.label, address: origin },
          dest:   { x: dc.x, y: dc.y, label: dc.label, address: dest },
          path,
        });
      } catch (e) {
        return json({ error: 'exception', detail: String(e).slice(0, 300) }, 500);
      }
    }

    // ── 설정 조회: opinet 키 + kakao 키 보유 여부 ──
    if (request.method === 'GET') {
      const opinetKey = (await env.CONFIG.get('opinetKey')) ?? '';
      const hasKakao = !!(await env.CONFIG.get('kakaoKey'));
      return json({ opinetKey, hasKakao });
    }

    // ── 설정 저장 ──
    if (request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch { return json({ error: 'invalid json' }, 400); }
      if (typeof body.opinetKey === 'string') await env.CONFIG.put('opinetKey', body.opinetKey);
      if (typeof body.kakaoKey === 'string')  await env.CONFIG.put('kakaoKey', body.kakaoKey);
      return json({ ok: true });
    }

    return json({ error: 'method not allowed' }, 405);
  },
};

// 주소 → 좌표 (도로명/지번 주소검색 우선, 실패 시 키워드검색)
async function geocode(query, key) {
  const auth = { headers: { Authorization: `KakaoAK ${key}` } };

  const addr = await fetch(
    'https://dapi.kakao.com/v2/local/search/address.json?query=' + encodeURIComponent(query),
    auth
  );
  if (addr.ok) {
    const d = await addr.json();
    const doc = d?.documents?.[0];
    if (doc) return { x: doc.x, y: doc.y, label: doc.address_name || query };
  }

  const kw = await fetch(
    'https://dapi.kakao.com/v2/local/search/keyword.json?query=' + encodeURIComponent(query),
    auth
  );
  if (kw.ok) {
    const d = await kw.json();
    const doc = d?.documents?.[0];
    if (doc) return { x: doc.x, y: doc.y, label: doc.place_name || doc.address_name || query };
  }
  return null;
}

// 경로 좌표 다운샘플 (최대 max개로 균등 추출, 시작·끝 보존)
function downsample(pts, max) {
  if (pts.length <= max) return pts;
  const step = (pts.length - 1) / (max - 1);
  const out = [];
  for (let i = 0; i < max; i++) out.push(pts[Math.round(i * step)]);
  return out;
}
