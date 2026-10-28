// 合言葉（KEY）を知っている人だけが開ける。?k= で来たらクッキーに移して URL から消す。
// GET /api/answers … 全部の答え  PUT /api/answers/:id … 1件を保存（上書き）
const COOKIE = 'tk';

function key(req) {
  const m = (req.headers.get('Cookie') || '').match(/(?:^|;\s*)tk=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : req.headers.get('X-Key') || '';
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const k = url.searchParams.get('k');
    if (k === env.KEY) {
      url.searchParams.delete('k');
      return new Response(null, { status: 302, headers: {
        Location: url.pathname + url.search,
        'Set-Cookie': `${COOKIE}=${encodeURIComponent(k)}; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax` } });
    }
    if (!env.KEY || key(req) !== env.KEY) return new Response('合言葉つきのリンクから開いてください', { status: 401 });

    if (url.pathname === '/api/answers' && req.method === 'GET') {
      const { results } = await env.DB.prepare('SELECT id, data FROM answers').all();
      return Response.json(Object.fromEntries(results.map(r => [r.id, JSON.parse(r.data)])));
    }
    const m = url.pathname.match(/^\/api\/answers\/([A-Za-z0-9-]{1,80})$/);
    if (m && req.method === 'PUT') {
      const data = await req.json();
      data.at = Date.now();
      await env.DB.prepare('INSERT INTO answers (id, data, at) VALUES (?1, ?2, ?3) ON CONFLICT(id) DO UPDATE SET data = ?2, at = ?3')
        .bind(m[1], JSON.stringify(data), data.at).run();
      return Response.json({ ok: true });
    }
    const res = await env.ASSETS.fetch(req);
    const h = new Headers(res.headers);
    h.set('Cache-Control', 'no-store');
    // 音声は1本にまとめてあるので、再生位置へ飛ぶには途中だけ返せないと全部の読み込みを待つことになる
    const r = (req.headers.get('Range') || '').match(/^bytes=(\d+)-(\d*)$/);
    if (r && res.status === 200) {
      const buf = await res.arrayBuffer();
      const a = +r[1], b = Math.min(r[2] ? +r[2] : buf.byteLength - 1, buf.byteLength - 1);
      if (a > b) return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${buf.byteLength}` } });
      h.set('Content-Range', `bytes ${a}-${b}/${buf.byteLength}`);
      h.set('Content-Length', String(b - a + 1));
      return new Response(buf.slice(a, b + 1), { status: 206, headers: h });
    }
    h.set('Accept-Ranges', 'bytes');
    return new Response(res.body, { status: res.status, headers: h });
  },
};
