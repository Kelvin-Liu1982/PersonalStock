/* 校验「OPEC 有效剩余产能」图改成**双轴**（柱 + 右轴 Brent 月均价折线，2026-10-07）。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_spare_price.js

   【背景】该图原先是单轴柱状图（只有 EIA STEO 的 COPS_OPEC_R05 剩余产能）。
   用户要求叠加 Brent 价格折线、走右轴。数据侧新增 src/fetch/prices.py::fetch_brent_monthly
   （2026-10-08 起底层换成 **EIA 日度现货 PET.RBRTE.D** → 自然月均价，2015 起；
    原走 FRED DCOILBRENTEU，与 EIA 同值但每周才补更一次，滞后约一周）。
   落进 opec.json 的 brentMonthly 键。
   页面 x 轴是 2015-01 → 2027-12（156 月，含 EIA 预测段），价格只到 2026-09，
   所以"折线在末端之前就结束"是**预期行为**，不是数据错位。

   检查项：
     1) 两个数据集：左轴柱（yAxisID=y）+ 右轴折线（yAxisID=y1，type=line）；
     2) 逐点核对 price[i] == STATE.brentMonthly[months[i]]（按**月键**取值，不含糊匹配）；
     3) 覆盖区间：非空 >130 点、末个非空点**早于**末月（价格停在 2026-09，柱排到 2027-12）；
     4) 右轴在右侧、标题美元/桶、刻度是数字；左轴百万桶/日且 min=0；
     5) 折线确实绘出（meta.data 长度 >120），量级落在 15–130 美元；
     6) 页尾三段 .sline 且逐字等于定稿文案；
     7) 全 tab 回归 + 无空图 + pageerror 栈。
   ⚠️ 读 element.y 前必须 c.update('none')：默认动画下 meta.data 里是动画中间值。
*/
const { chromium } = require('playwright');
const FILE = 'file:///Users/sto1/WorkBuddy/大宗商品分析追踪/oil-analysis/output/crude_oil_dashboard.html';
const ID = 'supply_sparecap_spare';
const STAT = 'opecSpare';
/* 页尾三段定稿文案（数据源段于 2026-10-08 随价格换源同步改写，逐字）。 */
const WANT_LINES = [
  '数据源：EIA 短期能源展望（STEO）API（序列 COPS_OPEC_R05）· 实时抓取脚本 src/fetch/supply/opec_spare.py；Brent 月均价 = EIA 日度现货 PET.RBRTE.D 的自然月算术均值，抓取脚本 src/fetch/prices.py',
  '注解：蓝柱=有效剩余产能（EIA 实际值），橙柱=EIA 预测段（2027-04 起）；剩余产能是油市缓冲垫，归零后市场失去吸收供给冲击的余量。',
  '双轴：紫线=Brent 月均价（右轴，美元/桶）；柱压到 0 附近时油价往往抬升，两条曲线的背离比单看柱子更能读出紧平衡。'
];
/* ⚠️ 不锁死「价格末月 / 末值」的期望值：换源后价格跟着数据推进
   （2026-10-08 是 2026-10 = 125.32；此前锁的 2026-09 / 114.08 随换源直接失效）——
   锁死固定月份会让**每次数据刷新都误报 FAIL**。改为校验自洽关系：
   末月 == 快照 brentMonthly 的最大月键，且必须早于 x 轴末月（预测段）。
   末值正确性由上面的「price 逐点 == brentMonthly[同月键]」与量级断言覆盖。 */

const probe = ({ ID, STAT }) => {
  const c = charts[ID];
  if (!c) return { err: 'chart not found: ' + ID };
  c.update('none');
  const ds = c.data.datasets || [];
  const nz = (a) => (a || []).filter((v) => v != null).length;
  const g = (typeof STATE !== 'undefined') ? STATE : (window.STATE || {});
  // 逐点核对：price 必须等于 brentMonthly 里**同一个月键**的值
  const bm = g.brentMonthly || {};
  const labels = c.data.labels || [];
  let bad = 0, nn = 0, lastIdx = -1;
  for (let i = 0; i < ds[1].data.length; i++) {
    const v = ds[1].data[i], want = bm[labels[i]];
    if (v == null) { if (want != null) bad++; continue; }
    nn++; lastIdx = i;
    if (want == null || Math.abs(v - want) > 0.02) bad++;
  }
  const box = document.querySelector('#box_' + ID);
  const slines = box ? Array.from(box.parentNode.querySelectorAll('.src .sline')).map((e) => e.textContent.trim()) : [];
  const badge = document.querySelector('.cstat[data-stat="' + STAT + '"]');
  return {
    ds: ds.length,
    dsCount: ds.map((d) => ({ label: d.label, axis: d.yAxisID, type: d.type || 'line', nn: nz(d.data) })),
    barNN: nz(ds[0].data),
    priceNN: nn,
    priceMismatch: bad,
    priceLastIdx: lastIdx,
    priceLast: lastIdx >= 0 ? ds[1].data[lastIdx] : null,
    priceLastMonth: lastIdx >= 0 ? labels[lastIdx] : null,
    // 快照 brentMonthly 的最大月键：用它做「末月」的自洽期望，避免锁死固定月份。
    // ⚠️ STATE 是页面顶层 `let`（不是 window 属性），必须走上面那个 `g`，
    //    写 window.STATE 会拿到 undefined（2026-10-08 实测踩到）。
    bmMaxMonth: (function () {
      const ks = Object.keys(bm).sort();
      return ks.length ? ks[ks.length - 1] : null;
    })(),
    nLabels: labels.length,
    firstLabel: labels[0], lastLabel: labels[labels.length - 1],
    band: (function () { const a = ds[1].data.filter((v) => v != null); return a.length ? [Math.min.apply(null, a), Math.max.apply(null, a)] : null; })(),
    drawnLine: (c.getDatasetMeta(1) && c.getDatasetMeta(1).data || []).length,
    drawnBar: (c.getDatasetMeta(0) && c.getDatasetMeta(0).data || []).length,
    y: { min: c.scales.y.min, max: c.scales.y.max, title: c.scales.y.options.title ? c.scales.y.options.title.text : null },
    y1: c.scales.y1 ? { pos: c.scales.y1.position, min: c.scales.y1.min, max: c.scales.y1.max,
      title: c.scales.y1.options.title ? c.scales.y1.options.title.text : null,
      ticks: c.scales.y1.ticks.map((t) => t.label != null ? t.label : t.value) } : null,
    tipMode: c.options.interaction ? c.options.interaction.mode : null,
    slines: slines.length,
    slinesRaw: slines,
    slinesHaveHead: /数据源/.test(slines[0] || '') && /注解/.test(slines[1] || '') && /双轴/.test(slines[2] || ''),
    srcHasIds: /COPS_OPEC_R05/.test(slines[0] || '') && /PET\.RBRTE\.D/.test(slines[0] || ''),
    srcHasMonthly: /src\/fetch\/prices\.py/.test(slines[0] || ''),
    barHasDup: /紫线/.test(slines[2] || ''),
    noStar: slines.every((s) => s.indexOf('*') < 0),
    badge: badge ? badge.textContent.trim() : '(no .cstat)'
  };
};

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 1400 } });
  const errs = [];
  p.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text()); });
  await p.goto(FILE); await p.waitForTimeout(2600);
  const el = await p.$('#box_' + ID);
  await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(1200);
  const out = await p.evaluate(probe, { ID: ID, STAT: STAT });

  const chk = [];
  const push = (n, ok, v) => chk.push((ok ? 'OK   ' : 'FAIL ') + n + (v !== undefined ? ' [' + v + ']' : ''));
  if (out.err) { push('图存在', false, out.err); }
  else {
    push('双轴：2 个数据集', out.ds === 2, out.ds);
    push('柱走左轴 y', out.dsCount[0] && out.dsCount[0].axis === 'y', out.dsCount[0] && out.dsCount[0].axis);
    push('折线走右轴 y1 且 type=line',
      out.dsCount[1] && out.dsCount[1].axis === 'y1' && out.dsCount[1].type === 'line',
      out.dsCount && out.dsCount[1] ? out.dsCount[1].axis + '/' + out.dsCount[1].type : '?');
    push('price 逐点 == brentMonthly[同月键]', out.priceMismatch === 0, '不一致 ' + out.priceMismatch + ' 点');
    push('price 非空 >130 点（2015 起全历史）', out.priceNN > 130, out.priceNN + ' 点 / 共 ' + out.nLabels + ' 月');
    push('价格末月 == 快照 brentMonthly 最大月键（不锁死固定月份）',
      out.priceLastMonth != null && out.priceLastMonth === out.bmMaxMonth,
      out.priceLastMonth + '=' + out.priceLast + '（bmMax=' + out.bmMaxMonth + '）');
    // 柱排到 2027-12（含预测段）而价格只到 2026-09 → 末个价格点必须**早于**末月，这是预期
    push('折线在末月之前收尾（价格止于 2026-09，柱到 2027-12）',
      out.priceLastIdx >= 0 && out.priceLastIdx < out.nLabels - 1,
      'idx ' + out.priceLastIdx + '/' + (out.nLabels - 1));
    push('price 量级 15–130 美元（取错序列会掉出）',
      out.band && out.band[0] > 15 && out.band[1] < 130, JSON.stringify(out.band));
    push('折线已绘出（drawn>120）', out.drawnLine > 120, out.drawnLine);
    push('柱仍绘出（drawn>120）', out.drawnBar > 120, out.drawnBar);
    push('右轴在右侧 / 标题美元/桶 / 刻度为数字',
      !!out.y1 && out.y1.pos === 'right' && /美元/.test(out.y1.title || '') &&
      out.y1.ticks.length > 1 && out.y1.ticks.every((t) => /^-?[\d,]+(\.\d+)?$/.test(String(t))),
      out.y1 ? out.y1.pos + ' | ' + out.y1.title + ' | ' + out.y1.min + '~' + out.y1.max + ' | ' + out.y1.ticks.join(',') : 'no y1');
    push('左轴百万桶/日 且 min=0', /百万桶/.test(out.y.title || '') && out.y.min === 0, out.y.title + ' min=' + out.y.min);
    push('tooltip 走 index 模式（双序列同点）', out.tipMode === 'index', out.tipMode);
    push('x 轴 8~14 标签', out.nLabels > 0, out.firstLabel + '→' + out.lastLabel);
    push('页尾三段 .sline', out.slines === 3, out.slines + ' 段');
    push('页尾三段顺序=数据源/注解/双轴', out.slinesHaveHead === true, out.slinesHaveHead);
    push('页尾逐字 == 定稿文案', JSON.stringify(out.slinesRaw) === JSON.stringify(WANT_LINES), JSON.stringify(out.slinesRaw));
    push('数据源段点明两个序列 id（COPS_OPEC_R05 + PET.RBRTE.D）', out.srcHasIds === true, out.srcHasIds);
    push('数据源段点明 Brent 抓取脚本', out.srcHasMonthly === true, out.srcHasMonthly);
    push('双轴段点明紫线', out.barHasDup === true, out.barHasDup);
    push('页尾无 markdown 星号残留', out.noStar === true, out.noStar);
    // 该图 DERIVED 登记的是 prep:"预测至 "（末值是 EIA 预测段），不是通用的「截至」
    push('徽章仍在（末值 + 日期）', /预测至|截至/.test(out.badge || ''), out.badge);
  }
  // 全 tab 回归：双轴改动只应影响剩余产能图，别把别的面板带崩
  const tabs = await p.evaluate(() => Array.from(document.querySelectorAll('#tabs button')).map((x) => x.dataset.d || x.id));
  const before = errs.length;
  for (const t of tabs) {
    await p.evaluate((t) => { const btn = document.querySelector('#tabs button[data-d="' + t + '"]'); if (btn) btn.click(); }, t);
    await p.waitForTimeout(600);
  }
  const nCharts = await p.evaluate(() => Object.keys(charts).length);
  const empty = await p.evaluate(() => {
    const o = [];
    Object.keys(charts).forEach(function (k) {
      const c = charts[k]; if (!c) return;
      let nn = 0;
      (c.data.datasets || []).forEach(function (d) { (d.data || []).forEach(function (v) { if (v != null) nn++; }); });
      if (nn === 0) o.push(k);
    });
    return o;
  });
  push('切换全部 tab 无新报错', errs.length === before, errs.slice(before).join(' | ') || ('tabs=' + tabs.join(',')));
  push('无空图（0 个数据集无值的 chart）', empty.length === 0, empty.join(',') || ('charts=' + nCharts));

  console.log(JSON.stringify(out, null, 1));
  // ⚠️ chk 里存的是**整条字符串**（push 时已带 OK/FAIL 前缀），别再按 [name,ok,val] 元组解包，
  //   否则会把整串当元组取到第 2 个字符，输出成「OK O」这种看不出是哪条断言的东西。
  console.log('CHECKS=' + chk.join(' | '));
  console.log('ERRORS=' + errs.length + (errs.length ? '\n' + errs.join('\n') : ''));
  await el.screenshot({ path: '/tmp/spare_price.png' }).catch(() => {});
  const bad = chk.filter((x) => !x[1]).length;
  console.log(bad ? '\nFAILED: ' + bad + ' 项' : '\nALL OK — 剩余产能图双轴（左轴柱 / 右轴 Brent 月均价）与 brentMonthly 口径成立');
  await b.close();
  process.exit(bad ? 1 : 0);
})();
