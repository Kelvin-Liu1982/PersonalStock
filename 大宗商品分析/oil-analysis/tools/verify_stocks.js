/* 校验「库欣原油库存」与「全美商业原油库存」两张图的**口径与量级**（2026-10-07 订正后）。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_stocks.js
     实时段需先起服务：python -m src.serve 8123   （也可用 DASH_URL=... 改端口）

   【背景】这两张图此前**序列用反了**：库欣图挂的是 PET.WCESTUS1.W（全美商业 ex-SPR，427 Mbbl），
   全美商业图挂的是 PET.WCRSTUS1.W（含 SPR 总原油，711 Mbbl）。真正的库欣（Cushing, OK，WTI
   交割地）只有 22–30 Mbbl，量级差一个数量级。订正后：
       cushing → PET.W_EPC0_SAX_YCUOK_MBBL.W（约 24）
       total   → PET.WCESTUS1.W（约 427）
       含 SPR 总库存 = total + spr（派生序列 gross，≈711）
   本脚本把「量级」也做成断言，取错序列会当场 FAIL（tools/check_eia_series.js 只校 id 表，
   校不出「id 对了但值不是那个东西」）。

   两阶段：
     A 快照（file://）：图画出来 + 末值落档 + 徽章 + KPI 芯片 + gross 恒等
     B 实时（http + 桩接口）：开页自动拉取后两张图仍在、gross 仍在（前端派生）
   ⚠️ 读 element.y 前必须 c.update('none')：默认动画下 meta.data 是中间值。
*/
const { chromium } = require('playwright');
const ROOT = '/Users/sto1/WorkBuddy/业绩追踪看板/大宗商品分析/oil-analysis';
const SNAP = 'file://' + ROOT + '/output/crude_oil_dashboard.html';
const LIVE = process.env.DASH_URL || 'http://localhost:8123/';
const NODE = '/Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node';

// ⚠️ Chart 实例（charts[ID]）上**没有** .key 属性——徽章选择器必须显式给 STAT_MAP 的键，
// 早先用 c.key 拼出 [data-stat="undefined"]，徽章断言静默变成 (no .cstat)。
const IDS = { cushing: 'supply_inv_cushing', total: 'supply_inv_total' };
const STAT = { cushing: 'eia.cushing', total: 'eia.total' };
const STUB_ID = { cushing: 'PET.W_EPC0_SAX_YCUOK_MBBL.W', total: 'PET.WCESTUS1.W' };
// 期望末值档位（百万桶）：库欣 22–30，全美商业 425–430。取串了立刻掉出档位。
const BAND = { cushing: [15, 45], total: [380, 480] };

/* ---- EIA 桩：14 周（2026-06-27 ~ 2026-09-25），单位**千桶**（前端会 /1000 成百万桶） ---- */
const PERIODS = Array.from({ length: 14 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 8, 25) - i * 7 * 86400000);
  return d.toISOString().slice(0, 10);
});
const OVERLAP = '2026-09-29';   // 与 FRED 日度轴重叠，否则日度对齐整段 null
// ⚠️ OVERLAP（与 FRED 日度轴重叠的那一天）要给一个**邻近真实值**的取值：
// 早期写法 base - 13*370 会让它变成「13 周前的值」，图上末点因此离真实值差 4.8 百万桶，
// 看起来就像「实时拿到的数不对」。370 千桶 ≈ 0.37 百万桶，一次正常周度变动的量级。
const rawSeries = (base) => Object.assign(
  { [OVERLAP]: Math.round(base + 370) },
  Object.fromEntries(PERIODS.map((p, i) => [p, Math.round(base - i * 370)])));
// 千桶：24.301 / 427.320 / 283.767 百万桶。千万别再乘 1000（乘了前端 /1000 后正好差 1000 倍）。
// 其余四个序列给个能画的假值，否则桩里缺序列 → 那些图被 guardEmpty 判空并 console.error，
// 「实时段无报错」这条会被桩数据自己带偏。
const STUB_KV = {
  'PET.W_EPC0_SAX_YCUOK_MBBL.W': 24301,
  'PET.WCESTUS1.W': 427320,
  'PET.WCSSTUS1.W': 283767,
  'PET.WCRFPUS2.W': 13690,
  'PET.WGTSTUS1.W': 210982,
  'PET.WPULEUS3.W': 84,
  'PET.WGFUPUS2.W': 6621
};
const EIA_STUB = Object.fromEntries(Object.entries(STUB_KV).map(([id, v]) => [id, rawSeries(v)]));

// ⚠️ 传参而不是闭包取值：p.evaluate 会把函数**序列化**后丢进页面执行，
// 外面定义的 STAT / BAND 之类在页面里根本不存在（会 ReferenceError）。
const probe = ({ ID, stat }) => {
  const c = charts[ID];
  if (!c) return { err: 'chart not found: ' + ID };
  c.update('none');
  const d = c.data.datasets[0].data || [];
  const pts = c.getDatasetMeta(0).data || [];
  const ys = pts.filter(Boolean).map((e) => e.y);
  let li = -1;
  for (let i = d.length - 1; i >= 0; i--) if (d[i] != null) { li = i; break; }
  const badge = document.querySelector('.cstat[data-stat="' + stat + '"]');
  return {
    key: stat,
    n: d.length,
    last: li >= 0 ? d[li] : null,
    drawn: pts.length,
    collapsed: ys.length ? (Math.max.apply(null, ys) - Math.min.apply(null, ys) < 5) : null,
    yScale: { min: c.scales.y.min, max: c.scales.y.max },
    badge: badge ? badge.textContent.trim() : '(no .cstat)',
    nodata: !!document.querySelector('#box_' + ID + ' .nodata')
  };
};

/* 库欣图在 2026-10-08 起叠加了「周增减」柱（右轴 y1）。这条探针专校叠加层：
   柱必须是线的**逐周差分**、且值来自与折线**同一份**数组（取错数组会整体错一周）。 */
const deltaProbe = ({ ID }) => {
  const c = charts[ID];
  if (!c) return { err: 'chart not found: ' + ID };
  c.update('none');
  const line = c.data.datasets[0], bar = c.data.datasets[1];
  const nz = (a) => (a || []).filter((v) => v != null).length;
  let bad = 0;
  for (let i = 0; i < line.data.length; i++) {
    const lv = line.data[i], pv = i > 0 ? line.data[i - 1] : null;
    const bv = bar ? bar.data[i] : null;
    const want = (lv != null && pv != null) ? Math.round((lv - pv) * 100) / 100 : null;
    if (bv === null) { if (want !== null) bad++; }
    else if (want === null || Math.abs(bv - want) > 0.011) bad++;
  }
  const t = c.scales.y1 ? c.scales.y1.ticks : [];
  return {
    ds: (c.data.datasets || []).length,
    barType: bar ? bar.type : null,
    barAxis: bar ? bar.yAxisID : null,
    barNN: bar ? nz(bar.data) : 0,
    lineNN: nz(line.data),
    // 差分序列的第 0 个点无前值 → 恒为 null，故柱的非空点数 = 线非空点数 − 1。
    // 直接断言两者相等是错的（2026-10-08 假 FAIL：142 vs 143，白白调了一轮）。
    leadGap: nz(line.data) - nz(bar ? bar.data : []),
    diffMismatch: bad,
    lastBar: bar ? bar.data[bar.data.length - 1] : null,
    y1: c.scales.y1 ? { pos: c.scales.y1.position, min: c.scales.y1.min, max: c.scales.y1.max,
      has0: t.some((x) => x.value === 0) } : null,
    y0: c.scales.y ? { min: c.scales.y.min, max: c.scales.y.max } : null,
    // 页尾「数据源 / 注解 / 双轴」三段分行
    slines: (function () { const b = document.querySelector('#box_' + ID); return b ? b.parentNode.querySelectorAll('.src .sline').length : -1; })()
  };
};

const stateProbe = () => {
  const g = (typeof STATE !== 'undefined') ? STATE : (window.STATE || {});
  const last = (a) => { for (let i = (a || []).length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };
  const w = g.eiaWeekly || {}, e = g.eia || {};
  return {
    eiaKeys: Object.keys(e),
    weeklyLast: { cushing: last(w.cushing), total: last(w.total), spr: last(w.spr), gross: last(w.gross) },
    dailyHasGross: !!(e.gross && e.gross.some((v) => v != null)),
    grossIdentical: (() => {
      const t = last(w.total), s = last(w.spr), gr = last(w.gross);
      return (t != null && s != null && gr != null) ? Math.abs(gr - (t + s)) < 0.02 : null;
    })(),
    badgeDate: (g.eiaDates || []).slice(-1)[0]
  };
};

(async () => {
  const b = await chromium.launch();
  const chk = [];
  const push = (name, ok, val) => chk.push((ok ? 'OK   ' : 'FAIL ') + name + (val !== undefined ? ' [' + val + ']' : ''));

  /* ---------------- A. 快照 ---------------- */
  { const p = await b.newPage({ viewport: { width: 1440, height: 1400 } });
    const errs = [];
    p.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
    p.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
    await p.goto(SNAP); await p.waitForTimeout(2600);

    const out = {}, st = {};
    for (const k of Object.keys(IDS)) {
      const el = await p.$('#box_' + IDS[k]);
      await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(900);
      out[k] = await p.evaluate(probe, { ID: IDS[k], stat: STAT[k] });
    }
    st.snap = await p.evaluate(stateProbe);

    for (const k of Object.keys(IDS)) {
      const o = out[k];
      if (o.err) { push(k + ' 图存在', false, o.err); continue; }
      push(k + ' 图画出来(drawn>20)', o.drawn > 20 && o.collapsed === false, o.drawn);
      push(k + ' 末值落档 ' + BAND[k].join('~'), o.last != null && o.last >= BAND[k][0] && o.last <= BAND[k][1], o.last);
      push(k + ' 徽章含「截至」', /截至/.test(o.badge || ''), o.badge);
      push(k + ' 无 .nodata 占位', o.nodata === false, o.nodata);
    }
    // 叠加层：两张库存图（库欣 / 全美商业）的「周增减」柱 + 右轴
    for (const k of Object.keys(IDS)) {
      const dl = await p.evaluate(deltaProbe, { ID: IDS[k] });
      if (dl.err) { push(k + ' 周增减柱渲染', false, dl.err); continue; }
      push(k + ' 周增减柱已叠加（2 个数据集）', dl.ds === 2 && dl.barType === 'bar', dl.ds + ' / ' + dl.barType);
      push(k + ' 周增减柱走右轴 y1', dl.barAxis === 'y1', dl.barAxis);
      push(k + ' 周增减柱点数 == 折线逐点差分（同源同一数组）',
        dl.barNN > 0 && dl.leadGap === 1,
        '柱 ' + dl.barNN + ' / 线 ' + dl.lineNN + '（差 ' + dl.leadGap + '，首点无前值）');
      push(k + ' 柱值 == 折线逐周差分', dl.diffMismatch === 0, '不一致 ' + dl.diffMismatch + ' 点');
      push(k + ' 右轴在右侧且跨 0（含 0 刻度）', !!dl.y1 && dl.y1.pos === 'right' && dl.y1.has0 &&
        dl.y1.min < 0 && dl.y1.max > 0, dl.y1 ? (dl.y1.pos + ' ' + dl.y1.min + '~' + dl.y1.max + ' has0=' + dl.y1.has0) : 'no y1');
      push(k + ' 页尾三段分行（.src .sline）', dl.slines === 3, dl.slines + ' 段');
    }

    // 量级：库欣 y 轴上限必须远低于全美商业（错配时两者会在同一量级）
    const ys = { cushing: out.cushing.yScale, total: out.total.yScale };
    push('两图量级分明（库欣 max < 全美 max）', ys.cushing.max < ys.total.max * 0.5,
      ys.cushing.max + ' vs ' + ys.total.max);

    const wl = st.snap.weeklyLast;
    push('gross == total + spr（快照）', st.snap.grossIdentical === true,
      wl.gross + ' vs ' + wl.total + ' + ' + wl.spr);
    push('日度 STATE.eia.gross 有值', st.snap.dailyHasGross === true, st.snap.dailyHasGross);
    push('快照无报错', errs.length === 0, errs.length ? errs.join(' | ') : 0);

    for (const k of Object.keys(IDS)) {
      await p.$('#box_' + IDS[k]).then((e) => e.screenshot({ path: '/tmp/stocks_' + k + '.png' }).catch(() => {}));
    }
    await p.close(); }

  /* ---------------- B. 实时（桩接口） ---------------- */
  { const p = await b.newPage({ viewport: { width: 1440, height: 1400 } });
    const errs = [];
    p.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
    p.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
    // FRED 桩：260 天；⚠️ 响应形状必须是 {map:{date:{id:value}}}（loadLive 只读 fj.map），
    //  写成 {dates, series:[]} 会让 dates 为空 → STATE.eia 全空数组（键在、值全 null），
    //  图表因为走「原生周轴」照样画得出来，于是「gross 有键无值」这种假故障很难一眼看出。
    const fredMap = {};
    for (let i = 259; i >= 0; i--) {
      const d = new Date(Date.UTC(2026, 8, 29) - i * 86400000).toISOString().slice(0, 10);
      const t = 259 - i;
      const spike = (t % 43 === 0) ? 1.06 : ((t % 71 === 0) ? 0.93 : 1);
      const b = (70 + Math.sin(t / 9) * 3 + (t % 17) * 0.05) * spike;
      fredMap[d] = {
        DCOILBRENTEU: +b.toFixed(2), DCOILWTICO: +(b - 5 + Math.cos(t / 7) * 2).toFixed(2),
        DTWEXBGS: +(100 + Math.sin(t / 30) * 2).toFixed(2), DFF: +(3 + Math.sin(t / 40) * 0.2).toFixed(2),
        DGS10: +(4 + Math.cos(t / 45) * 0.25).toFixed(2), GASREGW: +(3.2 + Math.sin(t / 11) * 0.3).toFixed(2)
      };
    }
    await p.route('**/api/fred**', (route) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify({ map: fredMap })
    }));
    // EIA 桩：回全部 7 个序列（缺哪个哪个图就被 guardEmpty 判空），gross 由前端按恒等派生
    await p.route('**/api/eia**', (route) => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ dates: PERIODS.slice().concat([OVERLAP]).sort(), map: EIA_STUB })
    }));
    await p.goto(LIVE); await p.waitForTimeout(3200);   // 尾部的 setTimeout(loadLive, 400)

    const out = {}, st = {};
    for (const k of Object.keys(IDS)) {
      const el = await p.$('#box_' + IDS[k]);
      await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(900);
      out[k] = await p.evaluate(probe, { ID: IDS[k], stat: STAT[k] });
    }
    st.live = await p.evaluate(stateProbe);

    for (const k of Object.keys(IDS)) {
      const o = out[k];
      if (o.err) { push('[实时] ' + k + ' 图还在', false, o.err); continue; }
      push('[实时] ' + k + ' 图仍在且有数据', o.drawn > 5 && o.collapsed === false, o.drawn);
      // 桩里最后一天是 OVERLAP（2026-09-29），取值 = base + 370 千桶 → 除以 1000 即下界
      const want = (STUB_KV[STUB_ID[k]] + 370) / 1000;
      push('[实时] ' + k + ' 末值 == 桩值 ' + want,
        o.last != null && Math.abs(o.last - want) < 0.05, o.last);
      push('[实时] ' + k + ' 无 .nodata 占位', o.nodata === false, o.nodata);
    }
    // 实时态同样要验一次叠加层：柱/线错位只在「拉取实时」后出现（eiaAxis 回退日度轴那条路径）
    for (const k of Object.keys(IDS)) {
      const dl2 = await p.evaluate(deltaProbe, { ID: IDS[k] });
      push('[实时] ' + k + ' 周增减柱仍在且 == 逐周差分',
        !dl2.err && dl2.ds === 2 && dl2.diffMismatch === 0 && dl2.barNN > 0,
        dl2.err || (dl2.barNN + ' 点 / 不一致 ' + dl2.diffMismatch));
    }
    push('[实时] 前端派生 gross 仍在', st.live.dailyHasGross === true,
      st.live.dailyHasGross + ' / eiaKeys=' + (st.live.eiaKeys || []).join(','));
    push('[实时] gross == total + spr', st.live.grossIdentical === true,
      st.live.weeklyLast.gross + ' vs ' + st.live.weeklyLast.total + ' + ' + st.live.weeklyLast.spr);
    push('[实时] 无报错', errs.length === 0, errs.length ? errs.join(' | ') : 0);
    await p.close(); }

  console.log(chk.join('\n'));
  const bad = chk.filter((x) => x.startsWith('FAIL')).length;
  console.log('\n' + (bad ? 'FAILED: ' + bad + ' 项\n' + chk.filter((x) => x.startsWith('FAIL')).join('\n')
    : 'ALL OK — 库欣/全美商业库存口径与量级正确，gross 恒等与库欣「周增减」右轴叠加在快照与实时态均成立'));
  await b.close();
})();
