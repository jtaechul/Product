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

    // ── 오피넷 유가 중계: 제3자 CORS 프록시 대체 (서버가 직접 오피넷 호출) ──
    //   /opinet?type=daily&date=YYYYMMDD | type=recent | type=all
    if (request.method === 'GET' && url.pathname === '/opinet') {
      const opinetKey = url.searchParams.get('key') || await env.CONFIG.get('opinetKey');
      if (!opinetKey) return json({ error: 'no_opinet_key' }, 400);
      const type = url.searchParams.get('type') || 'daily';
      const date = (url.searchParams.get('date') || '').replace(/[^0-9]/g, '');
      let target;
      if (type === 'daily' && date.length === 8)
        target = `https://www.opinet.co.kr/api/dateAvgRecentPrice.do?code=${opinetKey}&out=json&date=${date}`;
      else if (type === 'recent')
        target = `https://www.opinet.co.kr/api/avgRecentPrice.do?code=${opinetKey}&out=json`;
      else if (type === 'all')
        target = `https://www.opinet.co.kr/api/avgAllPrice.do?code=${opinetKey}&out=json`;
      else return json({ error: 'bad_type' }, 400);
      try {
        const r = await fetch(target);
        const text = await r.text();
        let data;
        try { data = JSON.parse(text); } catch { return json({ error: 'parse_fail', raw: text.slice(0, 200) }, 502); }
        return json(data);
      } catch (e) {
        return json({ error: 'opinet_fetch_fail', detail: String(e).slice(0, 200) }, 502);
      }
    }

    // ── 지도 타일 중계: 브라우저가 OSM에 직접 못 가는 환경(사내망 등) 대응 ──
    //   /tile/{z}/{x}/{y} → OpenStreetMap 타일을 서버가 받아 CORS 허용으로 반환
    if (request.method === 'GET' && url.pathname.startsWith('/tile/')) {
      const m = url.pathname.match(/^\/tile\/(\d{1,2})\/(\d{1,7})\/(\d{1,7})$/);
      const tileHdr = {
        'Access-Control-Allow-Origin': '*',
        'Content-Type': 'image/png',
        'Cache-Control': 'public, max-age=604800',
      };
      if (!m) return new Response('bad tile', { status: 400, headers: tileHdr });
      const [, z, tx, ty] = m;
      try {
        const r = await fetch(`https://tile.openstreetmap.org/${z}/${tx}/${ty}.png`, {
          headers: { 'User-Agent': 'KOEM-travel-expense/1.0 (+https://jtaechul.github.io)' },
          cf: { cacheTtl: 604800, cacheEverything: true },
        });
        if (!r.ok) return new Response('tile fail', { status: 502, headers: tileHdr });
        return new Response(await r.arrayBuffer(), { status: 200, headers: tileHdr });
      } catch (e) {
        return new Response('tile err', { status: 502, headers: tileHdr });
      }
    }

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
          + '&priority=DISTANCE&car_fuel=DIESEL&summary=false',
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

// 주소 → 좌표. 여러 변형으로 재시도해 인식 성공률을 높임
//   ① 주소검색(원문) ② 키워드검색(원문) ③ 읍/면/리 제거 후 주소검색 ④ 키워드검색(제거본)
async function geocode(query, key) {
  const auth = { headers: { Authorization: `KakaoAK ${key}` } };

  const tryAddress = async (q) => {
    const r = await fetch('https://dapi.kakao.com/v2/local/search/address.json?query=' + encodeURIComponent(q), auth);
    if (!r.ok) return null;
    const doc = (await r.json())?.documents?.[0];
    return doc ? { x: doc.x, y: doc.y, label: doc.address_name || q } : null;
  };
  const tryKeyword = async (q) => {
    const r = await fetch('https://dapi.kakao.com/v2/local/search/keyword.json?query=' + encodeURIComponent(q), auth);
    if (!r.ok) return null;
    const doc = (await r.json())?.documents?.[0];
    return doc ? { x: doc.x, y: doc.y, label: doc.place_name || doc.address_name || q } : null;
  };

  // 읍/면/리 행정구역 토큰 제거 변형 (예: "청주시 흥덕구 오송읍 봉산2길 70" → "청주시 흥덕구 봉산2길 70")
  const stripped = query.replace(/\s*\S+?(?:읍|면|리)(?=\s)/g, '').replace(/\s+/g, ' ').trim();

  return (await tryAddress(query))
      || (await tryKeyword(query))
      || (stripped !== query ? await tryAddress(stripped) : null)
      || (stripped !== query ? await tryKeyword(stripped) : null);
}

// 경로 좌표 다운샘플 (최대 max개로 균등 추출, 시작·끝 보존)
function downsample(pts, max) {
  if (pts.length <= max) return pts;
  const step = (pts.length - 1) / (max - 1);
  const out = [];
  for (let i = 0; i < max; i++) out.push(pts[Math.round(i * step)]);
  return out;
}
