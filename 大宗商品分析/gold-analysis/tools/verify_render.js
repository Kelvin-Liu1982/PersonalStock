// 渲染校验：在 Node DOM-stub 中执行 gold-terminal.html 的内联脚本，
// 确认数据驱动的 SVG（中国央行购金月度折线 cnCbMonthly 等）真实产出图形，
// 而非死 SVG。校验脚本留在项目内（勿放 /tmp，会被清）。
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const html = fs.readFileSync(
  path.join(__dirname, '..', 'output', 'gold-terminal.html'), 'utf8');

// 抽取所有 <script>...</script> 内联块（含 GOLD_DATA / GOLD_PANEL_DATA 数据块 + 主脚本）
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);

function makeEl(id) {
  const el = {
    id,
    _html: '',
    _text: '',
    attrs: {},
    style: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    children: [],
    appendChild(c) { this.children.push(c); },
    setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
    removeAttribute(k) { delete this.attrs[k]; },
    hasAttribute(k) { return k in this.attrs; },
    addEventListener() {},
    removeEventListener() {},
    scrollIntoView() {},
    querySelector() { return makeEl('q'); },
    querySelectorAll() { return []; },
  };
  Object.defineProperty(el, 'innerHTML', { get() { return this._html; }, set(v) { this._html = v; } });
  Object.defineProperty(el, 'textContent', { get() { return this._text; }, set(v) { this._text = v; } });
  Object.defineProperty(el, 'viewBox', { get() { return { baseVal: { width: 920, height: 290 } }; } });
  return el;
}

const els = {};
function getEl(id) { if (!els[id]) els[id] = makeEl(id); return els[id]; }

// 2026-11-15：价格时间轴已改为与 A1 共用 renderHist()，页面现有 2 个 .hist-chart 容器。
// stub 需要提供这两个元素，才能验证 renderHist() 真的把图形写进去了。
const histEls = [getEl('histChartTop'), getEl('histChartA1')];

const sandbox = {
  console,
  Math, Date, JSON, parseInt, parseFloat, isNaN,
  String, Number, Array, Object, RegExp,
  setInterval: () => 0, clearInterval: () => {},
  setTimeout: () => 0, clearTimeout: () => {},
  requestAnimationFrame: () => 0,
  fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
  location: { protocol: 'http:', href: 'http://localhost/' },
  navigator: { userAgent: 'node' },
  IntersectionObserver: class { constructor(cb) { this.cb = cb; } observe() {} unobserve() {} },
  document: {
    getElementById: getEl,
    querySelector: () => makeEl('q'),
    querySelectorAll: (sel) => sel === '.hist-chart' ? histEls : [],
    createElement: () => makeEl('c'),
    addEventListener: () => {},
  },
};
sandbox.window = sandbox;
sandbox.window.addEventListener = () => {};

vm.createContext(sandbox);

// 先显式把两个数据块注入 sandbox，保证图表 IIFE 执行时 GOLD_PANEL_DATA 已就绪
// （不依赖 <script> 在文档中的先后次序）。
const gd = html.match(/\/\*GOLD_DATA_START\*\/([\s\S]*?)\/\*GOLD_DATA_END\*\//);
const gp = html.match(/\/\*GOLD_PANEL_DATA_START\*\/([\s\S]*?)\/\*GOLD_PANEL_DATA_END\*\//);
if (gd) vm.runInContext(gd[1], sandbox, { filename: 'GOLD_DATA.js' });
if (gp) vm.runInContext(gp[1], sandbox, { filename: 'GOLD_PANEL_DATA.js' });

let ran = 0;
for (const sc of scripts) {
  if (!sc.trim()) continue;
  try {
    vm.runInContext(sc, sandbox, { filename: `inline#${ran}.js` });
  } catch (e) {
    console.error(`✗ script #${ran} threw:`, e.message);
  }
  ran++;
}
console.log('GOLD_PANEL_DATA.cnMonthly present:', !!(sandbox.GOLD_PANEL_DATA && sandbox.GOLD_PANEL_DATA.cnMonthly));


function report(id) {
  const h = getEl(id)._html || '';
  return {
    id,
    len: h.length,
    hasPolyline: h.includes('<polyline'),
    circles: (h.match(/<circle/g) || []).length,
    paths: (h.match(/<path/g) || []).length,
    rects: (h.match(/<rect/g) || []).length,
    lines: (h.match(/<line/g) || []).length,
  };
}

const targets = ['cnCbMonthly', 'cbCountry', 'cbMonthly', 'cbAnnual', 'gdtDemandChart', 'gdtSupplyChart', 'dtDebt', 'histChartTop', 'histChartA1', 'goldMonthlyChart'];
let ok = true;
for (const id of targets) {
  const r = report(id);
  const good = r.len > 0 && (r.hasPolyline || r.circles > 0 || r.paths > 0 || r.rects > 0);
  if (!good) ok = false;
  console.log(`${good ? '✓' : '✗'} ${id.padEnd(12)} len=${String(r.len).padStart(5)} polyline=${r.hasPolyline} circle=${r.circles} rect=${r.rects} path=${r.paths} line=${r.lines}`);
}
const cn = getEl('cnCbMonthly')._html || '';
const m = cn.match(/<polyline points="([^"]+)"/);
console.log('\ncnCbMonthly polyline points:', m ? m[1] : '(none)');
// 校验连续增持月数在图内（数据驱动：点数量 = 8）
// 2026-10 起改为双轴：每月一个储备圆点（33 点 = 数据行数），柱仅非零月绘制
console.log('cnCbMonthly circle count (应=数据行数):', (cn.match(/<circle/g) || []).length);
console.log('cnCbMonthly rect count (应=非零月数):', (cn.match(/<rect/g) || []).length);
console.log('\nRESULT:', ok ? 'ALL CHARTS RENDERED' : 'SOME CHARTS EMPTY');
process.exit(ok ? 0 : 1);
