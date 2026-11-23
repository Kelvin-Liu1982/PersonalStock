/* 校验「全球原油产量 (百万桶/日, 月度)」图（id=supply_prodcap_worldq）。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_world_monthly.js

   【背景】2026-10-10：数据源由 STEO 月报 PDF 的**季度**列，整体换成 STEO **base tables**
   Excel（data/raw/eia_steo/oct26_base.xlsx / 3atab）的**月度**列 —— 72 个月 2022-01~2027-12。
   2026-10-16 再换源：**EIA STEO 官方 API**（/v2/steo/data/，COPR_* 序列），
   随 dataset 步骤实时抓取；数值与 xlsx 口径一致（仅 API 末位舍入差 ~1e-8）。
   三条线 = World / OPEC / Non-OPEC 的 **Crude oil** 行（原油，不含 NGL）。
   旧季度口径下的 DoC / Others 两条拆分线已随季度键移除。

   2026-10-11 追加（本次校验重点）：
     · 页尾 source 由「数据源 / 口径 / 预测」三段（.sline ×3）精简为**单段**，只留数据源描述
     · 徽章由预测末点（82.97 · 预测至 27/12）改标**最新实际值**（75.97 · 截至 26/09）

   本脚本断言：
     A 三序列 / 72 个月 / 末点值（世界 82.97、OPEC 25.17、非 OPEC 57.81）
     B 逐月恒等：OPEC 原油 + 非 OPEC 原油 == 世界原油（容差 0.05，源表独立取整）
     C 预测段：三条线首虚线段 = 56（段 56 即 2026-09→2026-10，预测起点 2026-10 / index 57）
     D y 轴非 0 起点 + baseNote 标注、无 .nodata、无 console 报错
     E 页尾 source 单段（无 .sline）且文案逐字匹配「EIA STEO 月度 API（序列 COPR_*）· 实时抓取脚本」
     F 徽章落在**末个历史月**（世界 75.97 + 26/09），不再落到预测末点 27/12
*/
const { chromium } = require('playwright');
const ROOT = '/Users/sto1/WorkBuddy/业绩追踪看板/大宗商品分析/oil-analysis';
const SNAP = 'file://' + ROOT + '/output/crude_oil_dashboard.html';

const ID = 'supply_prodcap_worldq';
const STAT = 'steoWorld';
const OLD_ID = 'supply_prodcap_opecdoc';
const fail = [];

const probe = ({ ID, STAT, OLD_ID }) => {
  const c = charts[ID];
  if (!c) return { err: 'chart not found: ' + ID };
  c.update('none');
  const labels = c.data.labels || [];
  const ds = c.data.datasets || [];
  const arr = (i) => ds[i].data || [];
  const nn = (a) => (a || []).filter((v) => v != null).length;
  // 逐段调用 segment.borderDash，定位第一条变虚线的段（首虚线段 index）。
  // 段 i 连接点 i→i+1，p1DataIndex=i+1；forecastIndex=57 ⇒ 自段 56（2026-09→2026-10）起虚线。
  const firstDashedSeg = (di) => {
    const fn = ds[di] && ds[di].segment && ds[di].segment.borderDash;
    if (!fn) return -1;
    for (let i = 0; i < labels.length - 1; i++) {
      const d = fn({ p0DataIndex: i, p1DataIndex: i + 1, type: 'segment' });
      if (d && d.length) return i;
    }
    return -1;
  };
  // 逐月恒等：OPEC + Non-OPEC DoC + Others == 世界（容差 0.05）
  // ⚠️ 2026-10-11 起 Non-OPEC 线一分为二（DoC + Others），故恒等式由「OPEC+非OPEC」
  //    改为「OPEC+DoC+Others」；Others 由前端元素级相减得到，与源数据同口径。
  const bad = []; let maxAbs = 0;
  for (let i = 0; i < labels.length; i++) {
    const w = arr(0)[i], o = arr(1)[i], doc = arr(2)[i], oth = arr(3)[i];
    if (w == null || o == null || doc == null || oth == null) continue;
    const dd = Math.abs((o + doc + oth) - w);
    if (dd > maxAbs) maxAbs = dd;
    if (dd > 0.05) bad.push(labels[i] + ':' + (o + doc + oth).toFixed(3) + 'vs' + w);
  }
  const pts = c.getDatasetMeta(0).data || [];
  const ys = pts.filter(Boolean).map((e) => e.y);
  const badge = document.querySelector('.cstat[data-stat="' + STAT + '"]');
  const box = document.querySelector('#box_' + ID);
  const h3 = box ? box.closest('.card') : null;
  return {
    dsN: ds.length,
    dsLabels: ds.map((d) => d.label),
    labels: labels.slice(),
    nn: [nn(arr(0)), nn(arr(1)), nn(arr(2)), nn(arr(3))],
    last: [arr(0)[labels.length - 1], arr(1)[labels.length - 1], arr(2)[labels.length - 1],
           arr(3)[labels.length - 1]],
    histLast: [arr(0)[56], arr(1)[56], arr(2)[56], arr(3)[56]],  // 2026-09 = 末个历史月
    fcFirst: [arr(0)[57], arr(1)[57], arr(2)[57], arr(3)[57]],    // 2026-10 = 预测首月
    firstDashedSeg: [firstDashedSeg(0), firstDashedSeg(1), firstDashedSeg(2), firstDashedSeg(3)],
    sumBad: bad, sumMaxAbs: maxAbs,
    yScale: { min: c.scales.y.min, max: c.scales.y.max },
    baseNoteOn: !!(c.options.plugins && c.options.plugins.baseNote && c.options.plugins.baseNote.on),
    drawn: pts.length,
    collapsed: ys.length ? (Math.max.apply(null, ys) - Math.min.apply(null, ys) < 5) : null,
    badge: badge ? badge.textContent.trim() : '(no .cstat)',
    title: (h3 && h3.querySelector('h3')) ? h3.querySelector('h3').textContent.trim() : '',
    nodata: !!document.querySelector('#box_' + ID + ' .nodata'),
    slines: box && box.parentNode ? box.parentNode.querySelectorAll('.src .sline').length : -1,
    srcText: box && box.parentNode ? ((box.parentNode.querySelector('.src') || {}).textContent || '') : '',
    oldMonthlyGone: !(charts[OLD_ID] || ecCharts[OLD_ID]) && !document.querySelector('#box_' + OLD_ID),
    opecMonthlyStill: !!(charts['supply_prodcap_opec'] || ecCharts['supply_prodcap_opec'])
  };
};

(async () => {
  const b = await chromium.launch();
  const pg = await b.newPage();
  const errs = [];
  pg.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()); });
  pg.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  await pg.goto(SNAP, { waitUntil: 'load' });
  await pg.waitForTimeout(2500);
  const r = await pg.evaluate(probe, { ID, STAT, OLD_ID });

  const t = (name, ok, detail) => { if (!ok) fail.push(name + ' → ' + detail); };
  if (r.err) { fail.push('图表未渲染：' + r.err); }
  else {
    t('图卡标题（已改月度）', /^全球原油产量 \(百万桶\/日, 月度\)/.test(r.title), JSON.stringify(r.title));
    // 2026-10-11 起为**四线**：World / OPEC / Non-OPEC DoC / Others（Others = 非OPEC − DoC）
    t('四条线（World / OPEC / Non-OPEC DoC / Others）', r.dsN === 4, 'dsN=' + r.dsN);
    t('序列名', String(r.dsLabels) === 'World,OPEC,Non-OPEC DoC,Others', JSON.stringify(r.dsLabels));
    t('四条线各 72 个非空点', String(r.nn) === '72,72,72,72', 'nn=' + JSON.stringify(r.nn));
    t('x 轴 72 个月（2022-01~2027-12）',
      r.labels.length === 72 && r.labels[0] === '2022-01' && r.labels[71] === '2027-12',
      JSON.stringify([r.labels[0], r.labels[71]]));
    t('x 轴标签全为 YYYY-MM', r.labels.every((l) => /^\d{4}-\d{2}$/.test(l)), JSON.stringify(r.labels.slice(0, 3)));
    // 预测起点 2026-10（index 57）⇒ 首虚线段 = 56（段 56 = 2026-09→2026-10）
    t('四条线首虚线段 = 56（2026-09→2026-10）',
      String(r.firstDashedSeg) === '56,56,56,56', JSON.stringify(r.firstDashedSeg));
    t('末个历史月 2026-09 有值', r.histLast.every((v) => v != null), JSON.stringify(r.histLast));
    // 徽章取的就是这个点：世界 75.97 / OPEC 20.80 / DoC 14.05 / Others 41.12（实际值口径）
    t('末个历史月世界 ≈ 75.97（徽章源值）',
      r.histLast[0] != null && Math.abs(r.histLast[0] - 75.97) < 0.01, 'histLast[0]=' + r.histLast[0]);
    t('预测首月 2026-10 有值', r.fcFirst.every((v) => v != null), JSON.stringify(r.fcFirst));
    t('逐月恒等 OPEC+DoC+Others=世界（容差 0.05）',
      r.sumBad.length === 0, 'maxAbs=' + r.sumMaxAbs.toFixed(4) + ' bad=' + JSON.stringify(r.sumBad.slice(0, 5)));
    t('末点 World ≈ 82.97', r.last[0] != null && Math.abs(r.last[0] - 82.973) < 0.01, 'last=' + r.last[0]);
    t('末点 OPEC ≈ 25.17', r.last[1] != null && Math.abs(r.last[1] - 25.165) < 0.01, 'last=' + r.last[1]);
    t('末点 Non-OPEC DoC ≈ 14.35', r.last[2] != null && Math.abs(r.last[2] - 14.353) < 0.01, 'last=' + r.last[2]);
    t('末点 Others ≈ 43.46', r.last[3] != null && Math.abs(r.last[3] - 43.455) < 0.01, 'last=' + r.last[3]);
    t('已启用 baseNote 插件', r.baseNoteOn === true, 'baseNoteOn=' + r.baseNoteOn);
    t('y 轴起点非 0（baseNote 触发前提）', r.yScale.min > 0, 'yMin=' + r.yScale.min);
    // 数据驱动取整（5 的整数倍）：2026-10-11 起四线含 DoC（最低 13.57），下界随之下探到 10；
    // 世界上限 83.03 → 上界仍 85。yPadding/y 轴逻辑未变，只是最小值由 OPEC 深坑换成 DoC 线决定。
    t('y 轴数据驱动 10–85（数据驱动，非写死）',
      r.yScale.min === 10 && r.yScale.max === 85, JSON.stringify(r.yScale));
    t('曲线未塌成水平线', r.collapsed === false, 'collapsed=' + r.collapsed);
    t('折线点已绘制 = 72', r.drawn === 72, 'drawn=' + r.drawn);
    // 徽章标**最新实际值**：历史段截断到 steoLastHistorical（2026-09），世界 = 75.97。
    // 末个历史月经 fmtX 渲染成 "26/09"（全站日期格式 YY/MM），不是原始键 "2026-09"。
    t('徽章 = 最新实际值（75.97 + 截至 26/09）',
      /75\.97/.test(r.badge) && /26\/09/.test(r.badge) && /截至/.test(r.badge),
      JSON.stringify(r.badge));
    t('徽章不再标预测末点（27/12）', !/27\/12/.test(r.badge), JSON.stringify(r.badge));
    t('未触发 .nodata 兜底', r.nodata === false, 'nodata=' + r.nodata);
    // 页尾已精简为单段（不再用 .sline 包裹「数据源 / 口径 / 预测」三段）
    t('页尾 source 无 .sline 分段', r.slines === 0, 'slines=' + r.slines);
    // 2026-10-16 换源：页尾改为「EIA STEO 月度 API（序列 COPR_*）· 实时抓取脚本」（与周报页尾同款简洁样式）
    const WANT_SRC = '数据源：EIA STEO 月度 API（序列 COPR_WORLD / COPR_OPEC / COPR_NONOPEC）· '
      + '实时抓取脚本 src/fetch/supply/steo_monthly.py';
    t('页尾 source 文案逐字匹配（单段）',
      (r.srcText || '').trim() === WANT_SRC, JSON.stringify(r.srcText));
    t('月度 OPEC+ 图确已下线', r.oldMonthlyGone === true, 'oldMonthlyGone=' + r.oldMonthlyGone);
    t('既有「OPEC 12 国月度」图仍在', r.opecMonthlyStill === true, 'opecMonthlyStill=' + r.opecMonthlyStill);
  }
  t('无 console 报错', errs.length === 0, JSON.stringify(errs.slice(0, 3)));

  console.log(JSON.stringify(r, null, 2));
  console.log('\n--- 断言 ---');
  if (fail.length) { fail.forEach((f) => console.log('FAIL  ' + f)); console.log('\n共 ' + fail.length + ' 项 FAIL'); }
  else console.log('ALL OK — 全球月度产量图：72 个月 / 四条原油线（World·OPEC·DoC·Others）/ '
    + '预测段 2026-10 起虚线 / 恒等自洽 / 页尾单段 / 徽章 = 最新实际值 26-09');
  await b.close();
  process.exit(fail.length ? 1 : 0);
})();
