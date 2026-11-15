/* 校验「价格换源 EIA 日度」后**实时拉取链路**成立（2026-10-08 新增）。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_price_live.js

   背景：2026-10-08 把 Brent/WTI 从 FRED（DCOILBRENTEU / DCOILWTICO，每周批量补更、
   最长滞后 7 天）换成 EIA 日度现货（PET.RBRTE.D / PET.RWTC.D，T+1）。
   换源有两个结构性风险，本脚本各守一道：

     坑 1  日度价格混进 **EIA_SERIES（周度）** → fetchEIA 用那张表的 period 并集
           生成「周轴」，混入日点会让周轴从约 2297 个周点膨胀到几千个日点，
           所有周度图 x 轴整片塌掉。
           → 断言：周轴 eiaDates.length 仍在 2200–2400 区间。
     坑 2  快照走 EIA 而 loadLive 仍走 FRED，两个滞后窗口不同
           → 断言：状态栏出现「油价EIA日度」，且 latest_date 与快照同步推进。

   ⚠️ 必须走 http（loadLive 在非 http 协议下直接 return），先起服务：
        python -m src.serve 8123
   ⚠️ 本脚本**不做 route 拦截**，走真实 EIA / FRED 链路（区别于 verify_spr_live.js 的桩测试）。
*/
const { chromium } = require('playwright');
const URL = process.env.DASH_URL || 'http://localhost:8123/';

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 1200 } });
  const errs = [];
  p.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text().slice(0, 160)); });

  await p.goto(URL, { waitUntil: 'load' });
  /* 开页 400ms 自动 loadLive。真实链路要打 3 个大请求（FRED + EIA 价格 + EIA 周度），
     且 src/serve.py 是**单线程** HTTPServer，请求是串行的 —— 用轮询等到状态栏落地，
     顺便把耗时打出来（耗时本身是要盯的指标：换源后多了一个 EIA 日度请求）。
     ⚠️ 不要用固定 waitForTimeout：慢的时候会误判成「还在拉取」，快的时候又白等。 */
  const t0 = Date.now();
  let status = '';
  for (let i = 0; i < 60; i++) {
    await p.waitForTimeout(1000);
    status = await p.evaluate(() => (document.getElementById('status') || {}).textContent || '');
    if (!/拉取实时数据中/.test(status)) break;
  }
  const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
  console.log('实时拉取耗时 = ' + elapsed + 's，状态栏 = ' + (status || '(空)'));

  const out = await p.evaluate(() => {
    const g = (typeof STATE !== 'undefined') ? STATE : (window.STATE || {});
    const last = (a) => { for (let i = (a || []).length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };
    const nn = (a) => (a || []).filter((v) => v != null).length;
    const blank = Object.keys(charts || {}).filter((k) => {
      const c = charts[k];
      return c && !(c.data.datasets || []).some((d) => nn(d.data) > 0);
    });
    return {
      status: (document.getElementById('status') || {}).textContent || '',
      latestDate: g.kpis ? g.kpis.latest_date : null,
      brentLast: last(g.brent),
      wtiLast: last(g.wti),
      dailyLen: (g.dates || []).length,
      weeklyLen: (g.eiaDates || []).length,
      weeklyTail: (g.eiaDates || []).slice(-2),
      priceIds: (typeof EIA_PRICE_IDS !== 'undefined') ? EIA_PRICE_IDS.ids : null,
      weeklyIds: (typeof EIA_SERIES !== 'undefined') ? Object.keys(EIA_SERIES.ids) : null,
      blankCharts: blank.length,
      chartCount: Object.keys(charts || {}).length
    };
  });

  const chk = [];
  const push = (ok, msg, detail) => chk.push((ok ? 'OK   ' : 'FAIL ') + msg + (detail != null ? ' [' + detail + ']' : ''));

  /* 坑 2：价格通道确实走了 EIA 日度（而不是 FRED 回落） */
  push(/油价EIA日度/.test(out.status), '状态栏标注价格源 = EIA日度', out.status || '(空)');
  push(!/拉取失败/.test(out.status), '状态栏无「拉取失败」', out.status || '(空)');

  /* 新鲜度：换源后应只落后 1–2 个交易日；落后约一周说明走的是 FRED 回落分支 */
  const fresh = out.latestDate >= '2026-10-05';
  push(fresh, '实时 latest_date 新鲜（>= 2026-10-05，落后一周即说明回落 FRED）', out.latestDate);

  /* 坑 1：周轴绝不能被日度价格撑爆 */
  push(out.weeklyLen >= 2200 && out.weeklyLen <= 2400,
    '周轴 eiaDates 仍是周度规模（2200–2400，未被日点膨胀）',
    out.weeklyLen + ' 点，末 ' + JSON.stringify(out.weeklyTail));
  push(Array.isArray(out.weeklyIds) && !out.weeklyIds.includes('brent') && !out.weeklyIds.includes('wti'),
    'EIA_SERIES（周度）不含 brent/wti', JSON.stringify(out.weeklyIds));
  push(out.priceIds && out.priceIds.brent === 'PET.RBRTE.D' && out.priceIds.wti === 'PET.RWTC.D',
    'EIA_PRICE_IDS 指向 EIA 日度序列', JSON.stringify(out.priceIds));

  /* 日度轴不能被 EIA 的 2006 年历史拉长 */
  push(out.dailyLen >= 990 && out.dailyLen <= 1100,
    '日度轴规模正常（990–1100，未被 EIA 历史拉回 2006）', out.dailyLen);

  /* 量级 */
  push(out.brentLast > 10 && out.brentLast < 300, 'brent 末值量级合理', out.brentLast);
  push(out.wtiLast > 10 && out.wtiLast < 300, 'wti 末值量级合理', out.wtiLast);
  push(out.blankCharts === 0, '无空图', out.blankCharts + ' / ' + out.chartCount);
  push(errs.length === 0, '无 pageerror / console error', errs.length ? errs.slice(0, 2).join(' | ') : '0');

  console.log('CHECKS=' + chk.join(' | '));
  console.log('\n' + (chk.some((c) => c.startsWith('FAIL')) ? '有 FAIL，见上' : 'ALL OK — 价格换源后实时链路成立'));
  await b.close();
  process.exit(chk.some((c) => c.startsWith('FAIL')) ? 1 : 0);
})();
