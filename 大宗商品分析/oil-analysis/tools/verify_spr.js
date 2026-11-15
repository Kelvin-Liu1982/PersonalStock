/* 校验 SPR 图「月度 → 周度」改造后的渲染（2026-10-07）。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_spr.js
   检查项：
     1) 图是否画出来（点数/末值/是否塌底）→ c.update('none') 后读 meta.data；
     2) 是否走**原生周轴**（x 轴末标签 == STATE.eiaDates 末值，且为 09-25 这类周日口径），
        而不是日度前向填充轴（那样末段会一堆重复值）；
     3) 徽章 .cstat[data-stat="eia.spr"] 文案（末值 + 截至周）；
     4) 月度序列只供维度 KPI 芯片，图上不再引用（STATE.usSpr 仍在属预期）；
     5) pageerror / console error 栈。
   ⚠️ 读 element.y 前必须 c.update('none')：默认动画下 meta.data 里是动画中间值。 */
const { chromium } = require('playwright');
const FILE = 'file:///Users/sto1/WorkBuddy/大宗商品分析追踪/oil-analysis/output/crude_oil_dashboard.html';
const ID = 'supply_inv_usspr';

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 1400 } });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  await p.goto(FILE); await p.waitForTimeout(2600);

  const el = await p.$('#box_' + ID);
  await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(1200);

  const out = await p.evaluate((ID) => {
    const c = charts[ID];
    if (!c) return { err: 'chart not found: ' + ID };
    c.update('none');
    const d = c.data.datasets[0].data || [];
    const pts = c.getDatasetMeta(0).data || [];
    const ys = pts.filter(Boolean).map(e => e.y);
    const xs = pts.filter(Boolean).map(e => e.x);
    const nn = (() => { let k = -1; for (let i = d.length - 1; i >= 0; i--) if (d[i] != null) { k = i; break; } return { i: k, v: d[k] }; })();
    const badge = document.querySelector('.cstat[data-stat="eia.spr"]');
    return {
      n: d.length,
      tail: d.slice(-6),
      lastNonNull: nn,
      drawn: pts.length,
      collapsed: ys.length ? (Math.max.apply(null, ys) - Math.min.apply(null, ys) < 5) : null,
      yPx: ys.length ? { min: Math.round(Math.min.apply(null, ys)), max: Math.round(Math.max.apply(null, ys)) } : null,
      xPx: xs.length ? { min: Math.round(Math.min.apply(null, xs)), max: Math.round(Math.max.apply(null, xs)) } : null,
      area: { l: Math.round(c.chartArea.left), r: Math.round(c.chartArea.right), t: Math.round(c.chartArea.top), b: Math.round(c.chartArea.bottom) },
      canvas: { w: c.canvas.clientWidth, h: c.canvas.clientHeight },
      y: { min: c.scales.y.min, max: c.scales.y.max },
      xTicks: c.scales.x.ticks.map(t => String(t.label != null ? t.label : t.value)),
      xMin: c.scales.x.min, xMax: c.scales.x.max,
      badge: badge ? badge.textContent.trim() : '(no .cstat[data-stat=eia.spr])',
      // 旧的月度渲染器若还残留，SUPPLY_RENDERERS 里不该再有 usSpr 键
      hasUsSprRenderer: typeof SUPPLY_RENDERERS !== 'undefined' && Object.keys(SUPPLY_RENDERERS).indexOf('usSpr') >= 0
    };
  }, ID);

  const st = await p.evaluate(() => {
    const g = (typeof STATE !== 'undefined') ? STATE : (window.STATE || {});
    return {
      eiaDatesLen: (g.eiaDates || []).length,
      eiaDatesTail: (g.eiaDates || []).slice(-3),
      weeklyTail: (g.eiaWeekly && g.eiaWeekly.spr) ? g.eiaWeekly.spr.slice(-3) : null,
      dailyTail: (g.eia && g.eia.spr) ? g.eia.spr.slice(-3) : null,
      monthlyMonths: (g.usSprMonths || []).slice(-2),   // 只供 KPI 芯片
      monthlyTail: (g.usSpr || []).slice(-2)
    };
  });

  const chk = [];
  if (out.err) chk.push('chart not found');
  else {
    const lastWeek = (st.eiaDatesTail || [])[st.eiaDatesTail.length - 1];
    chk.push(['drawn>20', out.drawn > 20, out.drawn]);
    chk.push(['not collapsed', out.collapsed === false, out.collapsed]);
    // 2026-10-07 起 SPR 图改绘 EIA 周度序列，末值 = 周度末值（非旧月度 283.767）。
    // 校验「图末值 == 周度 EIA 末值」即确认图仍由 EIA API 数据驱动（MOMR 兜底已于 2026-10-16 移除）。
    const wkLast = (st.weeklyTail || []).slice(-1)[0];
    chk.push(['末值==周度EIA末值', wkLast != null && Math.abs(out.lastNonNull.v - wkLast) < 0.01 && wkLast !== 283.767, out.lastNonNull.v + ' vs weekly ' + wkLast]);
    // x 轴是「周标签索引」线性轴：0..n-1；周度的判据 = 点数≈2.8 年周数（周度轴只取窗口内 143 点，
    // 若塌成日度前向填充轴则点数会是 900+）。徽章日期必须落在 eiaDates 末值上。
    chk.push(['x 索引连续 0..n-1', out.xMin === 0 && out.xMax === out.n - 1, out.xMin + '..' + out.xMax + '/' + out.n]);
    chk.push(['周度轴(点数 140~150)', out.n >= 140 && out.n <= 150, out.n]);
    // 徽章 "283.8 · 截至 26/09/25" → "2026/09/25" 与周轴末值比对
    const badgeD = ((out.badge || '').match(/(\d\d)\/(\d\d)\/(\d\d)/) || []).slice(1).join('/');
    const norm = badgeD ? '20' + badgeD.split('/').map(x => ('0' + x).slice(-2)).join('-') : '';
    chk.push(['徽章截至==eiaDates 末值', norm === String(lastWeek), norm + ' vs ' + lastWeek]);
    chk.push(['x 轴 8~14 标签', out.xTicks.length >= 8 && out.xTicks.length <= 14, out.xTicks.length]);
    chk.push(['徽章含"截至"', /截至/.test(out.badge || ''), out.badge]);
    chk.push(['无 usSpr 渲染器', out.hasUsSprRenderer === false, out.hasUsSprRenderer]);
  }

  console.log(JSON.stringify({ chart: out, state: st }, null, 1));
  console.log('CHECKS=' + chk.map(x => (x[1] ? 'OK ' : 'FAIL ') + x[0] + (x[2] !== undefined ? ' [' + x[2] + ']' : '')).join(' | '));
  console.log('ERRORS=' + errs.length + (errs.length ? '\n' + errs.join('\n') : ''));
  await el.screenshot({ path: '/tmp/spr.png' }).catch(() => {});
  await b.close();
})();
