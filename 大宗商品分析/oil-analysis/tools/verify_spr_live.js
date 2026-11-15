/* 复现「首屏正常 → 开页自动拉取实时 → 图没了」并验证修复。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_spr_live.js

   背景：dashboard.js 末尾 `if(API_KEYS.fred){setTimeout(loadLive,400)}` —— 开页 400ms
   就会自动拉一次实时。SPR 图那次的故障是前端「拉取实时」用的 id 表漏了 spr，
   拉完之后 STATE.eia.spr 不存在，图渲染成空画布。

   本脚本用 route 拦截 /api/fred 与 /api/eia，返回**带 spr** 的 EIA 响应（模拟修复后的行为），
   并在另一种情形下故意**不给 spr**（回归实验，可加 --drop-spr 打开），
   后者应当看到「本图暂无数据」占位（guardEmpty 生效），而不是静默空白。

   判定：
     --drop-spr       期望：图表被 guardEmpty 换成 .nodata 占位 + console.error 点名 spr
     （默认，带 spr）   期望：图表仍在，末点==注入值，且不是空画布
*/
const { chromium } = require('playwright');
const ROOT = '/Users/sto1/WorkBuddy/大宗商品分析追踪/oil-analysis';
// ⚠️ 必须走 http：dashboard.js::loadLive() 在非 http(s) 协议下会直接 return
// （"实时拉取需本地服务"），那样根本测不到开页自动拉取那一次重绘。
// 先起服务：python -m src.serve 8123
const FILE = process.env.DASH_URL || 'http://localhost:8123/';
const ID = 'supply_inv_usspr';
const DROP_SPR = process.argv.includes('--drop-spr');
// EIA 原始值单位为千桶；只对 MILLION_UNITS 名单里的序列 /1000（spr/cushing/total 属此类）
// 造 14 周（2026-06-27 ~ 2026-09-25）)：太少会让 x 轴抽稀到 1~2 个标签，测不出「周轴」这件事
const PERIODS = Array.from({ length: 14 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 8, 25) - i * 7 * 86400000);
  return d.toISOString().slice(0, 10);
});
// ⚠️ 必须塞一个与 FRED 日期轴重叠的期次（本例 2026-09-29）：EIA 日度对齐是按
// 「FRED 的 dates」遍历原始 period 做前向填充，若两边日期完全不相交，日度版会整段 null，
// 徽章（取日度版末值）就空了 —— 那是桩数据的问题，不是看板的问题。真实链路上 EIA 每周五
// 发布、FRED  daily 也覆盖到周五，所以能对齐。
const OVERLAP = '2026-09-29';
const byPeriod = (base) => Object.assign(
  { [OVERLAP]: Math.round(base - 13 * 370) },
  Object.fromEntries(PERIODS.map((p, i) => [p, Math.round(base - i * 370)])));
/* ⚠️ 不要在这里手抄 series id（2026-10-07 踩过）：库欣序列 10-07 从 PET.WCESTUS1.W
   换成 PET.W_EPC0_SAX_YCUOK_MBBL.W，本桩手抄的 id 表就整体过期，
   实时拉取后 cushing 取不到值 → guardEmpty 报「数据为空」，把真信号淹掉。
   这里改为**从构建产物反查**：EIA_SERIES 的键序（python 的 EIA_SERIES 字典序）与
   请求里的 ids 顺序一致，于是把 ids 与 EIA_SERIES.ids 的键逐一配对，
   直接用快照 SNAPSHOT.eiaWeekly[key] 的**千桶原值**当桩值 —— 永远跟着事实源走。 */
const fs = require('fs');
const HTML = fs.readFileSync(ROOT + '/output/crude_oil_dashboard.html', 'utf8');
const injM = HTML.match(/const EIA_SERIES\s*=\s*(\{[\s\S]*?\n?\});/);
const EIA_INJ = injM ? JSON.parse(injM[1]) : { ids: {}, million: [] };
const snapM = HTML.match(/const SNAPSHOT\s*=\s*(\{[\s\S]*?\});/);
const SNAP = snapM ? JSON.parse(snapM[1]) : {};
const SNAP_WEEK = (SNAP.eiaWeekly) || {};
const idToKey = {};                     // seriesid → 序列名（cushing / total / ...）
Object.keys(EIA_INJ.ids).forEach((k, i) => { idToKey[EIA_INJ.ids[k]] = k; });
const stubOf = (id) => {
  const key = idToKey[id];
  const w = key && SNAP_WEEK[key];
  if (!w) return null;                  // 造不出来的序列：返回 null，让调用方跳过
  const dates = SNAP.eiaDates || [];
  const out = {};
  w.forEach((v, i) => {
    const p = dates[i];
    // 快照是百万桶，桩要给千桶（前端 /MILLION_UNITS → /1000）
    if (p && v != null && key !== 'util') out[p] = Math.round(v * 1000);
    else if (p && v != null) out[p] = v;    // util 是百分比，不除 1000
  });
  return out;
};
const SPR_ID = 'PET.WCSSTUS1.W';

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 1400 } });
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE ' + m.text().slice(0, 160)); });

  /* FRED 桩：造 260 个自然日（≈252 交易日窗口 RANGE），而不是只给 2~3 天 ——
     vol20 需要 20 个交易日才有点、jump 事件条需要足够长的序列才有跳空，
     桩太短会让「本该有数据的图」被 guardEmpty 判成空，反而淹掉真正要验的信号。 */
  await p.route('**/api/fred**', route => {
    const map = {};
    for (let i = 259; i >= 0; i--) {
      const d = new Date(Date.UTC(2026, 8, 30) - i * 86400000).toISOString().slice(0, 10);
      // 简化随机游走（无 seeded rng 依赖，逐日线性+三角波足够让 vol20 / jump 有值）
      const t = 259 - i;
      // 每隔一段插一次 >JUMP_THRESHOLD(2.5%) 的跳空，让「跳变事件」bar 图有点可画
      const spike = (t % 43 === 0) ? 1.06 : ((t % 71 === 0) ? 0.93 : 1);
      const b = (70 + Math.sin(t / 9) * 3 + (t % 17) * 0.05) * spike;
      const w = b - 5 + Math.cos(t / 7) * 2;
      map[d] = {
        DCOILBRENTEU: +b.toFixed(2),
        DCOILWTICO: +w.toFixed(2),
        DTWEXBGS: +(100 + Math.sin(t / 30) * 2).toFixed(2),
        DFF: +(3.0 + Math.sin(t / 40) * 0.2).toFixed(2),
        DGS10: +(4.0 + Math.cos(t / 45) * 0.25).toFixed(2),
        GASREGW: +(3.2 + Math.sin(t / 11) * 0.3).toFixed(2),
      };
    }
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ map }) });
  });
  await p.route('**/api/eia**', route => {
    const ids = (new URL(route.request().url()).searchParams.get('ids') || '').split(',');
    const map = {};
    ids.forEach(id => {
      if (DROP_SPR && id === SPR_ID) return;         // 回归实验：故意漏掉 spr
      const src = stubOf(id);                        // 值直接取自快照，id 反查自构建注入的 EIA_SERIES
      if (src) map[id] = src;
    });
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ map }) });
  });

  await p.goto(FILE);
  await p.waitForTimeout(3000);                      // 等 loadLive（400ms 定时）与重渲染完成
  const el = await p.$('#box_' + ID);
  if (el) await el.scrollIntoViewIfNeeded();
  await p.waitForTimeout(900);

  const out = await p.evaluate((ID) => {
    const g = (typeof STATE !== 'undefined') ? STATE : (window.STATE || {});
    const c = charts[ID];
    let r = { present: !!c };
    if (c) {
      c.update('none');
      const d = (c.data.datasets[0].data || []);
      let nn = 0; d.forEach(v => { if (v != null) nn++; });
      const pts = c.getDatasetMeta(0).data || [];
      r.n = d.length; r.nonNull = nn; r.last = d[d.length - 1];
      r.drawn = pts.length;
      r.collapsed = pts.length ? (Math.max.apply(null, pts.map(e => e.y)) - Math.min.apply(null, pts.map(e => e.y)) < 5) : null;
      r.xTicks = (c.scales.x.ticks || []).length;
    }
    const box = document.querySelector('#box_' + ID);
    r.nodata = box ? !!box.querySelector('.nodata') : null;
    r.nodataText = box && box.querySelector('.nodata') ? box.querySelector('.nodata').textContent.trim() : null;
    r.canvasBlank = box ? !box.querySelector('canvas') : null;
    r.badge = (document.querySelector('.cstat[data-stat="eia.spr"]') || {}).textContent || null;
    /* 双轴占比（2026-10-07 起 SPR 图右轴）= spr ÷ gross。实时拉取后 gross 由前端派生
       （fetchEIA 里 weekly.gross = total + spr），这里必须**在实时态**再核一遍：
       快照态对得上不代表拉取后对得上（日度/周度数组不同源就会整体错位）。 */
    if (c) {
      const ds = c.data.datasets || [];
      r.shareDs = ds.length;
      r.shareAxis = ds[1] ? ds[1].yAxisID : null;
      r.shareNN = (ds[1] ? (ds[1].data || []).filter((v) => v != null).length : 0);
      const w = g.eiaWeekly || {}, wk2 = w.spr || [], wg = w.gross || [];
      let k = -1; for (let i = wk2.length - 1; i >= 0; i--) if (wk2[i] != null) { k = i; break; }
      r.shareCalc = (k >= 0 && wg[k] != null && wk2[k] != null) ? Math.round(wk2[k] / wg[k] * 1000) / 10 : null;
      r.shareLast = (function () { const a = ds[1] ? ds[1].data : []; for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; })();
    }
    const wk = (g.eiaWeekly && g.eiaWeekly.spr) || [];
    let lastWkDate = null;
    for (let i = wk.length - 1; i >= 0; i--) if (wk[i] != null) { lastWkDate = (g.eiaDates || [])[i] || null; break; }
    const badgeD = ((r.badge || '').match(/(\d\d)\/(\d\d)\/(\d\d)/) || []).slice(1);
    r.badgeDate = badgeD.length ? '20' + badgeD.join('-') : null;
    r.state = {
      eiaSpr: g.eia && g.eia.spr ? g.eia.spr.slice(-2) : null,
      weeklySpr: wk.slice(-2),
      eiaDatesTail: (g.eiaDates || []).slice(-2),
      lastWeeklyObsDate: lastWkDate   // 徽章「截至」必须等于它，不能漂到日轴末日
    };
    return r;
  }, ID);

  const chk = [];
  chk.push(['图实例存在', out.present === true || out.nodata === true, 'present=' + out.present + ' nodata=' + out.nodata]);
  if (DROP_SPR) {
    chk.push(['缺序列 → 显示占位而非空白', out.nodata === true && out.canvasBlank === true, out.nodataText]);
    chk.push(['占位点名 spr', !!out.nodataText && /spr/.test(out.nodataText), out.nodataText]);
    // 这一轮允许 Console 报错：那条 [dashboard] 日志本来就是守卫的诊断输出，
    // 但必须点名 spr，且不能有任何未捕获的 pageerror。
    const guardLog = errs.filter(e => /supply_inv_usspr/.test(e) && /数据为空/.test(e));
    chk.push(['诊断日志点名 spr', guardLog.length === 1 && /spr/.test(guardLog[0]), guardLog.length]);
    chk.push(['无未捕获 pageerror', !errs.some(e => /^PAGEERROR/.test(e)), errs.filter(e => /^PAGEERROR/.test(e)).length]);
  } else {
    chk.push(['实时拉取后图仍在', !!out.present, out.present]);
    chk.push(['有数据点', (out.nonNull || 0) > 0, out.nonNull + '/' + out.n]);
    chk.push(['未塌底', out.collapsed === false, out.collapsed]);
    chk.push(['x 轴周度标签', (out.xTicks || 0) >= 5, out.xTicks]);
    chk.push(['STATE.eiaWeekly.spr 已注入', !!(out.state && out.state.weeklySpr && out.state.weeklySpr.length), JSON.stringify(out.state && out.state.weeklySpr)]);
    chk.push(['徽章非空（末值+截至日）', !!out.badge && /截至/.test(out.badge), out.badge]);
    chk.push(['徽章截至==最后真实观测周', out.badgeDate === out.state.lastWeeklyObsDate, out.badgeDate + ' vs ' + out.state.lastWeeklyObsDate]);
    // 右轴「SPR 占原油总库存比重」= spr ÷ gross，实时态必须仍然成立
    chk.push(['右轴占比数据集存在且非空', out.shareDs === 2 && out.shareAxis === 'y1' && out.shareNN > 0,
      out.shareDs + ' / ' + out.shareAxis + ' / ' + out.shareNN + ' 点']);
    chk.push(['右轴占比末值 == spr ÷ gross（实时）',
      out.shareLast != null && out.shareCalc != null && Math.abs(out.shareLast - out.shareCalc) < 0.06,
      out.shareLast + ' vs ' + out.shareCalc]);
  }
  // 实时拉取后把每个 tab 都切一遍：guardEmpty 是**全局**守卫，
  // 不能只验供给侧一张图，别的面板被它误伤（或反过来漏掉）也要在这里暴露。
  const tabErrBefore = errs.length;
  const tabs = await p.evaluate(() => Array.from(document.querySelectorAll('#tabs button')).map(b => b.dataset.d || b.id));
  for (const t of tabs) {
    await p.evaluate((t) => { const b = document.querySelector('#tabs button[data-d="' + t + '"]'); if (b) b.click(); }, t);
    await p.waitForTimeout(700);
  }
  // DROP_SPR 轮次里守卫必然再报一次 supply_inv_usspr，那是本轮预期输出，不算"新报错"
  const newErrs = errs.slice(tabErrBefore).filter(e =>
    !(DROP_SPR && /supply_inv_usspr/.test(e) && /数据为空/.test(e)));
  chk.push(['实时拉取后切全部 tab 无新报错', newErrs.length === 0, newErrs.join(' | ') || ('tabs=' + tabs.join(','))]);

  // 汇总：DROP_SPR 轮次的守卫日志是本轮预期输出，从「是否干净」里剔除
  const stray = errs.filter(e => DROP_SPR ? !(/supply_inv_usspr/.test(e) && /数据为空/.test(e)) : true);
  chk.push(['无预期外报错', stray.length === 0, stray.length ? stray.join(' | ') : 0]);

  console.log('mode = ' + (DROP_SPR ? 'DROP_SPR（回归实验）' : '带 spr（正常实时拉取）'));
  console.log(JSON.stringify(out, null, 1));
  console.log('CHECKS=' + chk.map(x => (x[1] ? 'OK ' : 'FAIL ') + x[0]).join(' | '));
  if (errs.length) console.log('ERRORS=\n' + errs.join('\n'));
  if (el) await el.screenshot({ path: DROP_SPR ? '/tmp/spr_drop.png' : '/tmp/spr_live.png' }).catch(() => {});
  await b.close();
  process.exit(chk.some(x => !x[1]) ? 1 : 0);
})();
