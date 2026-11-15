/* 校验「拉取实时」的**故障隔离**（2026-10-22 改造）：
   任一源失败只让它自己没数据，后续源照常执行。
   用例：/api/fred 返回 502 + 非 JSON（复刻 FRED 维护期的真实故障），
        /api/eia 造数保证价格与周度成功 → 期望价格照常渲染、状态栏点名 FRED 缺失。
   用法（oil-analysis 目录）：
     python -m src.serve 8124 &
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_live_isolation.js */
const { chromium } = require('playwright');
const BASE = process.env.DASH_URL || 'http://localhost:8124/';

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 1200 } });
  const errs = [];
  p.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });

  // 源1 FRED：FRED_OK=1 时造数成功（对照场景），否则复刻维护期故障
  // （502 + 后端裸 JSONDecodeError 文案，与 2026-10-22 真实故障同形）
  await p.route('**/api/fred**', (route) => {
    if (process.env.FRED_OK) {
      const u = new URL(route.request().url());
      const ids = (u.searchParams.get('ids') || '').split(',').filter(Boolean);
      const days = [];
      const end = new Date(Date.UTC(2026, 9, 16));
      for (let i = 59; i >= 0; i--) {
        days.push(new Date(end.getTime() - i * 86400000).toISOString().slice(0, 10));
      }
      const m = {};
      days.forEach((d) => {
        m[d] = {};
        ids.forEach((sid, k) => { m[d][sid] = 100 + k * 10 + Math.random(); });
      });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ map: m }) });
    }
    return route.fulfill({
      status: 502, contentType: 'application/json',
      body: JSON.stringify({ error: 'Expecting value: line 1 column 1 (char 0)' }),
    });
  });
  // 源2/3 EIA：按请求里的 ids 造数（价格日度 + 周度都走这一路）
  await p.route('**/api/eia**', (route) => {
    const u = new URL(route.request().url());
    const ids = (u.searchParams.get('ids') || '').split(',').filter(Boolean);
    const map = {};
    const days = [];
    const end = new Date(Date.UTC(2026, 9, 16));
    for (let i = 59; i >= 0; i--) {
      days.push(new Date(end.getTime() - i * 86400000).toISOString().slice(0, 10));
    }
    ids.forEach((sid, k) => {
      const m = {};
      days.forEach((d, i) => { m[d] = 100 + k * 10 + i * 0.5; });
      map[sid] = m;
    });
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ map }) });
  });

  await p.goto(BASE);
  await p.waitForTimeout(5000);

  const out = await p.evaluate(() => {
    const st = document.getElementById('status');
    const g = (typeof STATE !== 'undefined') ? STATE : (window.STATE || {});
    const nn = (a) => Array.isArray(a) ? a.filter((v) => v != null).length : 0;
    return {
      status: st ? st.textContent.trim() : '(no #status)',
      brentNN: nn(g.brent), wtiNN: nn(g.wti),
      dxyNN: nn(g.dxy), dffNN: nn(g.dff), gasNN: nn(g.gas), crackNN: nn(g.crack),
      n: g.kpis ? g.kpis.n : null, latest: g.kpis ? g.kpis.latest_date : null,
      eiaHasSpr: !!(g.eiaWeekly && g.eiaWeekly.spr && g.eiaWeekly.spr.length),
    };
  });

  const okAll = !!process.env.FRED_OK;
  const chk = [];
  const push = (name, ok, val) => chk.push((ok ? 'OK   ' : 'FAIL ') + name + (val !== undefined ? ' [' + val + ']' : ''));
  push('价格轴已建成(n>0)', out.n > 0, out.n);
  push('brent 有数据（源2成功）', out.brentNN > 0, out.brentNN);
  push('wti 有数据（源2成功）', out.wtiNN > 0, out.wtiNN);
  push('EIA 周度已取到（源3成功）', out.eiaHasSpr === true || /含EIA/.test(out.status), out.eiaHasSpr);
  if (okAll) {
    push('全源正常：状态栏无缺失/快照标注', !/缺失|=快照/.test(out.status), out.status);
    push('全源正常：宏观序列有数据', out.dxyNN > 0 && out.dffNN > 0, 'dxy=' + out.dxyNN + ' dff=' + out.dffNN);
    push('全源正常：crack 有数据', out.crackNN > 0, out.crackNN);
  } else {
    push('状态栏标注 FRED宏观=快照', /FRED宏观=快照/.test(out.status), out.status);
    push('未误报整体拉取失败', !/^拉取失败/.test(out.status), out.status.slice(0, 40));
    push('宏观序列已回落快照（非空，非残留 null）', out.dxyNN > 0 && out.dffNN > 0, 'dxy=' + out.dxyNN + ' dff=' + out.dffNN);
    // 2026-10-22 用户截图的回归点：crack 依赖 FRED 汽油零售价，回落前会被 guardEmpty 判「本图暂无数据」
    push('crack 不再空白（快照回落生效）', out.crackNN > 0, out.crackNN);
  }

  console.log(JSON.stringify(out, null, 1));
  console.log('CHECKS=' + chk.join(' | '));
  console.log('ERRORS=' + errs.length + (errs.length ? '\n' + errs.join('\n') : ''));
  await b.close();
})();
