/* 校验「美国战略石油储备 SPR」图改成**双轴**后的渲染（2026-10-07）。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_spr_share.js

   【背景】该图原先是单轴折线（只有 SPR 库存水平）。users 要求把此前为「全美商业库存」图
   写过的派生序列 **gross**（含 SPR 原油总库存 = 全美商业库存 + SPR）用起来：右轴画一条
   「SPR 占原油总库存比重」= spr ÷ gross（%），先按折线画。

   检查项：
     1) 两个数据集：左轴库存折线 + 右轴占比折线（yAxisID 必须为 y1）；
     2) 逐点核对 share[i] == spr[i] / gross[i] * 100（同源同窗口，错位会在这里暴露）；
     3) 占比量级落在 35–45%（取错序列/取错日度轴会掉出档位）；
     4) 右轴在右侧、刻度带 %；左轴仍是百万桶；
     5) 页尾「数据源 / 注解 / 双轴」三段 .sline 且文案正确；
     6) 末值气泡两枚（库存 + 占比）不影响其它图；pageerror / console error 栈。
   ⚠️ 读 element.y 前必须 c.update('none')：默认动画下 meta.data 里是动画中间值。
*/
const { chromium } = require('playwright');
const FILE = 'file:///Users/sto1/WorkBuddy/大宗商品分析追踪/oil-analysis/output/crude_oil_dashboard.html';
const ID = 'supply_inv_usspr';
const STAT = 'eia.spr';
/* 页尾三段定稿文案（2026-10-07 用户指定，逐字）。 */
const WANT_LINES = [
  '数据源：EIA 周度石油周报 API（序列 PET.WCSSTUS1.W = U.S. Ending Stocks of Crude Oil in SPR）· 抓取脚本 src/fetch/supply/eia_weekly.py',
  '注解：SPR 是国家战略储备，平时不参与商业流通；含 SPR 的原油总库存 gross = 全美商业库存 + SPR。',
  '双轴：蓝线=SPR 库存水平（左轴），橙虚线=SPR 占原油总库存比重（右轴）；占比抬升说明商业库存去化更快、SPR 缓冲垫相对变薄。'
];
// 期望：283.767 / (427.320 + 283.767) = 39.92%
const WANT_SHARE = 283.767 / 711.087 * 100;

const probe = ({ ID, STAT }) => {
  const c = charts[ID];
  if (!c) return { err: 'chart not found: ' + ID };
  c.update('none');
  const ds = c.data.datasets || [];
  const nz = (a) => (a || []).filter((v) => v != null).length;
  const g = (typeof STATE !== 'undefined') ? STATE : (window.STATE || {});
  const w = g.eiaWeekly || {};
  const wg = (w.gross || []).slice(-ds[0].data.length);
  let bad = 0;
  for (let i = 0; i < ds[0].data.length; i++) {
    const s = ds[0].data[i], gr = wg[i], v = ds[1].data[i];
    const want = (s != null && gr != null && gr > 0) ? s / gr * 100 : null;
    if (v === null) { if (want !== null) bad++; }
    else if (want === null || Math.abs(v - want) > 0.06) bad++;
  }
  const share = (ds[1].data || []).filter((v) => v != null);
  const box = document.querySelector('#box_' + ID);
  const slines = box ? Array.from(box.parentNode.querySelectorAll('.src .sline')).map((e) => e.textContent.trim()) : [];
  const badge = document.querySelector('.cstat[data-stat="' + STAT + '"]');
  return {
    ds: ds.length,
    dsCount: ds.map((d) => ({ label: d.label, axis: d.yAxisID, type: d.type || 'line', nn: nz(d.data) })),
    shareLast: (function () { const a = ds[1].data; for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; })(),
    shareNN: nz(ds[1].data),
    lineNN: nz(ds[0].data),
    diffMismatch: bad,
    shareBand: share.length ? [Math.min.apply(null, share), Math.max.apply(null, share)] : null,
    drawnShare: (c.getDatasetMeta(1) && c.getDatasetMeta(1).data || []).length,
    y: { min: c.scales.y.min, max: c.scales.y.max, title: c.scales.y.options.title ? c.scales.y.options.title.text : null },
    y1: c.scales.y1 ? { pos: c.scales.y1.position, min: c.scales.y1.min, max: c.scales.y1.max,
      ticks: c.scales.y1.ticks.map((t) => t.label != null ? t.label : t.value) } : null,
    xTicks: c.scales.x.ticks.length,
    slines: slines.length,
    slinesRaw: slines,
    slinesHaveHead: /数据源/.test(slines[0] || '') && /注解/.test(slines[1] || '') && /双轴/.test(slines[2] || ''),
    srcHasId: /PET\.WCSSTUS1\.W/.test(slines[0] || ''),
    srcHasMonthly: /us_spr\.py/.test(slines[0] || ''),   // 「月度口径供 KPI 芯片」一句话已按需求删掉
    annHasGross: /gross/.test(slines[1] || ''),
    barHasDup: /双轴/.test(slines[2] || ''),
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
    push('右轴序列走 y1 且仍是折线', out.dsCount[1] && out.dsCount[1].axis === 'y1' && out.dsCount[1].type === 'line',
      out.dsCount && out.dsCount[1] ? out.dsCount[1].axis + '/' + out.dsCount[1].type : '?');
    push('左轴序列走 y', out.dsCount[0] && out.dsCount[0].axis === 'y', out.dsCount[0] && out.dsCount[0].axis);
    push('share 逐点 == spr ÷ gross', out.diffMismatch === 0, '不一致 ' + out.diffMismatch + ' 点');
    push('share 非空（>20 点）', out.shareNN > 20, '占比 ' + out.shareNN + ' 点 / 库存 ' + out.lineNN + ' 点');
    push('share 末值 == 39.9（283.767/711.087）',
      out.shareLast != null && Math.abs(out.shareLast - WANT_SHARE) < 0.15, out.shareLast + ' vs ' + WANT_SHARE.toFixed(2));
    // 当前窗口（2024-01 起）占比 39.9%–49.7%：2024  SPR 回补期一度接近 50%，此后随商业库存回升落到 40% 上下。
    // 取错序列（如用 cushing 当地基）或分子分母错周，会直接掉出 35–55 这个档位。
    push('share 落在 35–55%（取错序列/错位会掉出）',
      out.shareBand && out.shareBand[0] > 35 && out.shareBand[1] < 55, JSON.stringify(out.shareBand));
    push('右轴序列已绘出（drawn>20）', out.drawnShare > 20, out.drawnShare);
    push('右轴在右侧且刻度带 %', !!out.y1 && out.y1.pos === 'right' && out.y1.ticks.every((t) => /%$/.test(String(t))),
      out.y1 ? out.y1.pos + ' ' + out.y1.min + '~' + out.y1.max : 'no y1');
    push('左轴仍是百万桶', /百万桶/.test(out.y.title || ''), out.y.title);
    push('x 轴 8~14 标签', out.xTicks >= 8 && out.xTicks <= 14, out.xTicks);
    push('页尾三段 .sline', out.slines === 3, out.slines + ' 段');
    push('页尾三段顺序=数据源/注解/双轴', out.slinesHaveHead === true, out.slinesHaveHead);
    // 逐字比对：页尾文案是给用户看的内容，允许它改口径，但改了必须在这里留痕，
    // 不能只靠「含 gross」「含 PET.…」这种模糊匹配（模糊匹配挡不住措辞悄悄走样）。
    push('页尾逐字 == 2026-10-07 定稿文案', JSON.stringify(out.slinesRaw) === JSON.stringify(WANT_LINES),
      JSON.stringify(out.slinesRaw));
    push('数据源段含 EIA 序列 id', out.srcHasId === true, out.srcHasId);
    push('注解段点明 gross 派生口径', out.annHasGross === true, out.annHasGross);
    push('双轴段存在', out.barHasDup === true, out.barHasDup);
    push('已移除「月度口径…KPI 芯片」旧尾巴', out.srcHasMonthly === false, out.srcHasMonthly);
    push('徽章仍在（末值+截至）', /截至/.test(out.badge || ''), out.badge);
  }
  // 全 tab 回归：双轴改动只应影响 SPR 图，别把别的面板带崩
  const tabs = await p.evaluate(() => Array.from(document.querySelectorAll('#tabs button')).map((x) => x.dataset.d || x.id));
  const before = errs.length;
  for (const t of tabs) {
    await p.evaluate((t) => { const btn = document.querySelector('#tabs button[data-d="' + t + '"]'); if (btn) btn.click(); }, t);
    await p.waitForTimeout(600);
  }
  const nCharts = await p.evaluate(() => Object.keys(charts).length);
  const empty = await p.evaluate(() => {
    const out = [];
    Object.keys(charts).forEach(function (k) {
      const c = charts[k];
      if (!c) return;
      let nn = 0;
      (c.data.datasets || []).forEach(function (d) { (d.data || []).forEach(function (v) { if (v != null) nn++; }); });
      if (nn === 0) out.push(k);
    });
    return out;
  });
  push('切换全部 tab 无新报错', errs.length === before, errs.slice(before).join(' | ') || ('tabs=' + tabs.join(',')));
  push('无空图（0 个数据集无值的 chart）', empty.length === 0, empty.join(',') || ('charts=' + nCharts));

  console.log(JSON.stringify(out, null, 1));
  // ⚠️ chk 里存的是**整条字符串**（push 时已带上 OK/FAIL 前缀），别再按 [name,ok,val] 元组解包：
  //   写 chk.map(x=>x[1]?…:…+x[0]) 会把整串当元组、取到的是字符串的第 2 个字符，
  //   输出变成「OK O」这种看不出是哪条断言的东西（2026-10-07 踩过）。
  console.log('CHECKS=' + chk.join(' | '));
  console.log('ERRORS=' + errs.length + (errs.length ? '\n' + errs.join('\n') : ''));
  await el.screenshot({ path: '/tmp/spr_share.png' }).catch(() => {});
  const bad = chk.filter((x) => !x[1]).length;
  console.log(bad ? '\nFAILED: ' + bad + ' 项' : '\nALL OK — SPR 图双轴（左轴库存 / 右轴占比）与 gross 派生口径成立');
  await b.close();
  process.exit(bad ? 1 : 0);
})();
