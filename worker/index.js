/**
 * personalstock · 行情代理 Worker
 * ------------------------------------------------------------------
 * 端点：GET /api/quote?a=sh601919&h=hk01919
 *   a = A 股代码（腾讯格式：sh600941 / sz000651），可省略
 *   h = H 股代码（腾讯格式：hk01919），可省略
 *
 * 上游数据源：
 *   1) 腾讯行情  http://qt.gtimg.cn/q=<code>,<code>   （GBK 编码，~ 分隔）
 *   2) 新浪外汇  https://hq.sinajs.cn/list=fx_shkdcny （港元兑人民币，需 Referer）
 *
 * 其余请求全部交给静态资源（wrangler.toml 的 assets.directory = "."）。
 * ------------------------------------------------------------------
 */

// —— 已验证的字段索引 ——
// A 股（sh/sz）
const A = {
  price: 3, prevClose: 4, open: 5, change: 31, pct: 32,
  high: 33, low: 34, volume: 36, amount: 37, turnover: 38,
  floatCap: 44, totalCap: 45, pb: 46, peDyn: 52,
};
// H 股（hk）
const H = {
  price: 3, prevClose: 4, open: 5, change: 31, pct: 32,
  high: 33, low: 34, volume: 36, amount: 37, amplitude: 43,
  floatCap: 44, totalCap: 45, divYield: 47, high52: 48, low52: 49,
  shares: 69, peDyn: 71, dps: 72, avgPrice: 73, currency: 75,
};

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, OPTIONS',
};
const CODE_RE = /^(sh|sz|hk)\d{5,6}$/;
const UPSTREAM_TIMEOUT = 6000; // ms
const CACHE_TTL = 30;          // s

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS });
    }

    if (url.pathname === '/api/quote') {
      return handleQuote(request, url, ctx);
    }

    // 其余路径：回落到仓库根的静态资源
    if (env.ASSETS) {
      const assetRes = await env.ASSETS.fetch(request);
      // 未加 content-hash 的 HTML 若长期缓存，push 新版本后仍会命中旧缓存。
      // 让 HTML 走 no-cache（每次重新校验），部署后自动失效，避免线上停留在旧版。
      const ct = assetRes.headers.get('Content-Type') || '';
      if (ct.includes('text/html')) {
        const h = new Headers(assetRes.headers);
        h.set('Cache-Control', 'no-cache');
        return new Response(assetRes.body, { status: assetRes.status, headers: h });
      }
      return assetRes;
    }
    return new Response('Not Found', { status: 404 });
  },
};

async function handleQuote(request, url, ctx) {
  const a = (url.searchParams.get('a') || '').toLowerCase().trim();
  const h = (url.searchParams.get('h') || '').toLowerCase().trim();

  if (!a && !h) {
    return json({ ok: false, error: 'missing code: need ?a= and/or ?h=' }, 400, 0);
  }
  if ((a && !CODE_RE.test(a)) || (h && !CODE_RE.test(h))) {
    return json({ ok: false, error: 'bad code format' }, 400, 0);
  }

  // 边缘缓存：30s，避免频繁打上游
  const cache = caches.default;
  const cacheKey = new Request(url.toString(), { method: 'GET' });
  try {
    const hit = await cache.match(cacheKey);
    if (hit) {
      const out = new Response(hit.body, hit);
      out.headers.set('X-Quote-Cache', 'HIT');
      out.headers.set('Access-Control-Allow-Origin', '*');
      return out;
    }
  } catch (_) { /* 缓存不可用时直接回源 */ }

  try {
    const codes = [a, h].filter(Boolean);
    const [quotes, fx] = await Promise.all([
      fetchGtimg(codes),
      (a && h) ? fetchFx() : Promise.resolve(null),
    ]);

    const data = {
      ok: true,
      source: 'gtimg+sinajs',
      fetchedAt: new Date().toISOString(),
      fx: fx,                       // 1 港元 = ? 人民币
      a: a ? buildLeg(quotes[a], A) : null,
      h: h ? buildLeg(quotes[h], H) : null,
    };
    decorate(data);

    const res = json(data, 200, CACHE_TTL);
    res.headers.set('X-Quote-Cache', 'MISS');
    ctx.waitUntil(cache.put(cacheKey, res.clone()).catch(() => {}));
    return res;
  } catch (err) {
    return json({ ok: false, error: String(err && err.message || err) }, 502, 0);
  }
}

/* ------------------------------ 上游抓取 ------------------------------ */

async function fetchGtimg(codes) {
  const url = 'http://qt.gtimg.cn/q=' + codes.join(',');
  const res = await fetch(url, {
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT),
    headers: { 'User-Agent': 'Mozilla/5.0 personalstock-worker' },
  });
  if (!res.ok) throw new Error('gtimg HTTP ' + res.status);

  const buf = await res.arrayBuffer();
  // GBK 与 ASCII 兼容（汉字字节均为 0x81-0xFE 开头），
  // 按 latin1 逐字节解码不会破坏 ~ 分隔符与数字，够用且各环境都支持。
  const text = decodeLatin1(buf);

  const out = {};
  const re = /v_([\w]+)="([^"]*)"/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    out[m[1]] = m[2].split('~');
  }
  for (const c of codes) {
    if (!out[c] || out[c].length < 10) throw new Error('no data for ' + c);
  }
  return out;
}

async function fetchFx() {
  const res = await fetch('https://hq.sinajs.cn/list=fx_shkdcny', {
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT),
    headers: {
      'Referer': 'https://finance.sina.com.cn',
      'User-Agent': 'Mozilla/5.0 personalstock-worker',
    },
  });
  if (!res.ok) throw new Error('fx HTTP ' + res.status);
  const text = decodeLatin1(await res.arrayBuffer());
  const m = text.match(/hq_str_fx_shkdcny="([^"]*)"/);
  if (!m) throw new Error('fx parse failed');
  const parts = m[1].split(',');
  const rate = parseFloat(parts[1]);
  if (!isFinite(rate) || rate <= 0) throw new Error('fx value invalid');
  return rate; // 1 HKD = rate CNY
}

function decodeLatin1(buf) {
  if (typeof TextDecoder !== 'undefined') {
    try { return new TextDecoder('latin1').decode(buf); } catch (_) { /* fall through */ }
  }
  // 兜底：手动逐字节
  const b = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return s;
}

/* ------------------------------ 字段组装 ------------------------------ */

function num(v) {
  const n = parseFloat(v);
  return isFinite(n) ? n : null;
}

function buildLeg(p, map) {
  if (!p) return null;
  const get = (k) => num(p[map[k]]);
  const leg = {
    code: p[2] || null,
    name: p[1] || null,
    price: get('price'),
    change: get('change'),
    pct: get('pct'),
    prevClose: get('prevClose'),
    open: get('open'),
    high: get('high'),
    low: get('low'),
    peDyn: get('peDyn'),
    totalCap: get('totalCap'), // 单位：亿（本币）
  };
  if (map.pb !== undefined) leg.pb = get('pb');
  if (map.volume !== undefined) leg.volume = get('volume');
  // 单位统一为「元」：A 股上游给的是万元，H 股上游给的就是元
  if (map.amount !== undefined) {
    const amt = get('amount');
    leg.amount = amt == null ? null : amt * (map === A ? 10000 : 1);
  }
  if (map.turnover !== undefined) leg.turnover = get('turnover');
  if (map.floatCap !== undefined) leg.floatCap = get('floatCap');
  if (map.divYield !== undefined) leg.divYield = get('divYield');
  if (map.dps !== undefined) leg.dps = get('dps');
  if (map.amplitude !== undefined) leg.amplitude = get('amplitude');
  if (map.high52 !== undefined) leg.high52 = get('high52');
  if (map.low52 !== undefined) leg.low52 = get('low52');
  if (map.shares !== undefined) leg.shares = get('shares');
  return leg;
}

/**
 * 派生字段：
 *  - premium : H 股折/溢价 = H价(CNY) / A价 - 1
 *  - h.pb    : 同一份净资产，按汇率与价差从 A 股 PB 推导
 *              PB_H = PB_A × (P_H × fx) / P_A
 */
function decorate(d) {
  const a = d.a, h = d.h;
  if (!a || !h || !d.fx) return;
  const pa = a.price, ph = h.price;
  if (!pa || !ph) return;
  const phCny = ph * d.fx;
  d.premium = phCny / pa - 1;
  if (a.pb != null) h.pb = a.pb * phCny / pa;
  h.priceCny = phCny;
}

/* ------------------------------ 响应 ------------------------------ */

function json(obj, status = 200, ttl = 0) {
  const headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Cache-Control': ttl > 0
      ? `public, max-age=${ttl}`
      : 'no-store',
  };
  return new Response(JSON.stringify(obj), { status, headers });
}
