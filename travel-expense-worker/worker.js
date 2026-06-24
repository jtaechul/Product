const ALLOWED_ORIGIN = 'https://jtaechul.github.io';

const cors = {
  'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: cors });
    }

    const json = (body, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { ...cors, 'Content-Type': 'application/json' },
      });

    if (request.method === 'GET') {
      const opinetKey = (await env.CONFIG.get('opinetKey')) ?? '';
      return json({ opinetKey });
    }

    if (request.method === 'POST') {
      let body;
      try { body = await request.json(); } catch { return json({ error: 'invalid json' }, 400); }
      if (typeof body.opinetKey === 'string') {
        await env.CONFIG.put('opinetKey', body.opinetKey);
      }
      return json({ ok: true });
    }

    return json({ error: 'method not allowed' }, 405);
  },
};
