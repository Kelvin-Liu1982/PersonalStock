/* 校验「库存指标」四张图（库欣 / 全美商业 / OECD / SPR）图卡页尾的**三段式**：（2026-10-07）
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_footers.js

   【背景】库存四张图的页尾从「一坨 <b>数据源：</b>…」改成三段 <span class="sline">，
   CSS .src .sline{display:block} 各自成行。页尾是给用户读口径的地方，措辞改了图上不会报错，
   所以必须有一个**逐段**的守门脚本：只验「含数据源」这种模糊匹配挡不住口径悄悄走样。

   检查项：
     1) 四张图页尾都恰好 3 段 `.sline`，段首标签依次为 数据源 / 注解 / 同轴 或 双轴；
     2) 第 1 段必须点明 EIA 序列 id（PET.W…），第 2 段必须出现该图的主口径词（派生序列/口径提示）；
     3) 页尾文本里**不得**残留 markdown 星号（`**…**` 在 HTML 里只会原样显示）；
     4) 逐段与定稿文案 JSON 全等（WANT_LINES 里改措辞必须同步改这里）。
*/
const { chromium } = require('playwright');
const FILE = 'file:///Users/sto1/WorkBuddy/业绩追踪看板/大宗商品分析/oil-analysis/output/crude_oil_dashboard.html';

/* 定稿文案（2026-10-07）。⚠️ 改页尾措辞时必须同步改这里，否则这里会 FAIL —— 那是刻意的。 */
const WANT_LINES = {
  supply_inv_cushing: [
    '数据源：EIA 周度石油周报 API（序列 PET.W_EPC0_SAX_YCUOK_MBBL.W = Cushing, OK Ending Stocks excluding SPR of Crude Oil）· 抓取脚本 src/fetch/supply/eia_weekly.py',
    '注解：库欣是 WTI 交割地，这张图衡量的是交割地的挤仓/宽松压力；数值在 22–30 百万桶量级。',
    '双轴：蓝线=库存水平（左轴），红/绿柱=较上周增减（右轴）红柱为累库、绿柱为去库，0 线即两者分界；柱高看单周变化幅度，连续多周同色才构成趋势。'
  ],
  supply_inv_total: [
    '数据源：EIA 周度石油周报 API（序列 PET.WCESTUS1.W = U.S. Ending Stocks excluding SPR of Crude Oil）· 抓取脚本 src/fetch/supply/eia_weekly.py',
    '注解：全美商业库存反映整体供需，不含战略储备（SPR），425–430 百万桶量级。',
    '双轴：蓝线=库存水平（左轴），红/绿柱=较上周增减（右轴）红柱为累库、绿柱为去库，0 线即两者分界；柱高看单周变化幅度，连续多周同色才构成趋势。'
  ],
  supply_inv_oecd: [
    '数据源：OPEC 月度石油市场报告（MOMR）表 9-1（IEA 口径）的 Crude oil 与 Products 两行 · 提取脚本 src/fetch/supply/oecd_stocks.py',
    '注解：OECD 国家合计的商业库存，含原油与成品油、不含战略储备；成品油行含石化产品、本身不含原油。',
    '同轴：蓝实线=商业原油库存（1,313 百万桶），青虚线=成品油库存（1,451 百万桶）；两序列量级接近（成品油≈原油的 1.1 倍、占合计 52%）。'
  ],
  supply_inv_usspr: [
    '数据源：EIA 周度石油周报 API（序列 PET.WCSSTUS1.W = U.S. Ending Stocks of Crude Oil in SPR）· 抓取脚本 src/fetch/supply/eia_weekly.py',
    '注解：SPR 是国家战略储备，平时不参与商业流通；含 SPR 的原油总库存 gross = 全美商业库存 + SPR。',
    '双轴：蓝线=SPR 库存水平（左轴），橙虚线=SPR 占原油总库存比重（右轴）；占比抬升说明商业库存去化更快、SPR 缓冲垫相对变薄。'
  ]
};
const IDS = Object.keys(WANT_LINES);
const HEADS = [/^数据源/, /^注解/, /^(双轴|同轴)/];   // 第三段：有双轴图，也有同轴双线图（OECD）

const probe = ({ ID }) => {
  const box = document.querySelector('#box_' + ID);
  if (!box) return { err: 'box not found: ' + ID };
  const slines = Array.from(box.parentNode.querySelectorAll('.src .sline')).map((e) => e.textContent.trim());
  const src = box.parentNode.querySelector('.src');
  return {
    n: slines.length,
    heads: slines.map((s) => (s.match(/^([^：:]{1,4})/) || [''])[0]),
    hasEiaId: /PET\.W[A-Z0-9_.]+\.W/.test(slines[0] || ''),
    hasStar: /\*\*/.test(slines.join('')),
    srcFirst: src ? (src.firstElementChild ? src.firstElementChild.className : '') : null,
    lines: slines
  };
};

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 1400 } });
  const errs = [];
  p.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message));
  await p.goto(FILE); await p.waitForTimeout(2500);
  // ⚠️ 供给侧面板是**懒渲染**的：不滚过去 #box 根本不存在，querySelector 会拿到 null。
  for (const id of IDS) {
    const el = await p.$('#box_' + id);
    if (el) { await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(900); }
  }
  const out = {};
  for (const id of IDS) out[id] = await p.evaluate(probe, { ID: id });

  const chk = [];
  const push = (n, ok, v) => chk.push((ok ? 'OK   ' : 'FAIL ') + n + (v !== undefined ? ' [' + v + ']' : ''));
  for (const id of IDS) {
    const o = out[id];
    if (o.err) { push(id + ' 图卡存在', false, o.err); continue; }
    push(id + ' 页尾 3 段 .sline', o.n === 3, o.n + ' 段');
    const headsOk = HEADS.every((h, i) => h.test(o.heads[i] || ''));
    push(id + ' 段首标签=数据源/注解/双轴|同轴', headsOk, o.heads.join(' / '));
    push(id + ' 数据源段点明 EIA 序列 id', id === 'supply_inv_oecd' ? true : o.hasEiaId, o.hasEiaId);
    push(id + ' 无 markdown 星号残留', o.hasStar === false, o.hasStar);
    push(id + ' 逐字 == 定稿文案', JSON.stringify(o.lines) === JSON.stringify(WANT_LINES[id]),
      JSON.stringify(o.lines[0] || '').slice(0, 60) + '…');
  }
  push('无 pageerror', errs.length === 0, errs.join(' | ') || 0);

  console.log(JSON.stringify(out, null, 1));
  console.log('CHECKS=' + chk.join(' | '));
  const bad = chk.filter((x) => x.startsWith('FAIL')).length;
  console.log(bad ? '\nFAILED: ' + bad + ' 项\n' + chk.filter((x) => x.startsWith('FAIL')).join('\n')
    : '\nALL OK — 库存四张图页尾三段式齐备且逐字与定稿一致');
  await b.close();
  process.exit(bad ? 1 : 0);
})();
