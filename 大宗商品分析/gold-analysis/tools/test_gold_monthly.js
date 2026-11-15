// 当年月度金价小图校验（2026-11-15）
// 1) GOLD_PANEL_DATA.goldMonthly 为当年各月、升序、数值合理
// 2) 旧两行静态文字已移除，卡片内是空 SVG 容器 + spot-trend 结构
// 3) DOM-stub 实跑 IIFE：10 点折线 / 圆点 / 月份标签 / 标题年份 / 末月值
// 4) 空数据兜底
// 用法：node tools/test_gold_monthly.js
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const HTML = path.join(__dirname, '..', 'output', 'gold-terminal.html');
const html = fs.readFileSync(HTML, 'utf8');
let fail = 0;
const check = (ok, msg, extra) => {
  console.log(`${ok ? '✓' : '✗'} ${msg}${extra ? '  ' + extra : ''}`);
  if (!ok) fail++;
};

const gd = html.match(/\/\*GOLD_DATA_START\*\/([\s\S]*?)\/\*GOLD_DATA_END\*\//);
const gp = html.match(/\/\*GOLD_PANEL_DATA_START\*\/([\s\S]*?)\/\*GOLD_PANEL_DATA_END\*\//);

// --- 1) 数据块 ---
const probe = { window: {}, Math, Date, JSON };
probe.window = probe; vm.createContext(probe);
vm.runInContext(gd[1], probe); vm.runInContext(gp[1], probe);
const GM = (probe.GOLD_PANEL_DATA || probe.window.GOLD_PANEL_DATA).goldMonthly || [];
check(GM.length >= 1 && GM.length <= 12, 'goldMonthly 为当年各月', `${GM.length} 个月`);
const years = [...new Set(GM.map(r => String(r.month).slice(0, 4)))];
check(years.length === 1, '同一年份', years.join(','));
check(GM.every(r => /^\d{4}-\d{2}$/.test(r.month) && Number(r.price) > 0), '月份格式与价格合法');
const sorted = GM.every((r, i) => i === 0 || GM[i - 1].month <= r.month);
check(sorted, '按月份升序');
if (GM.length) {
  console.log(`     ${GM[0].month} $${GM[0].price} → ${GM[GM.length - 1].month} $${GM[GM.length - 1].price}`);
}

// --- 2) 页面结构 ---
check(!html.includes('▲ 自 6 月低点') && !html.includes('上半年受「加息交易」'),
  '两行静态文字已删');
check(html.includes('class="spot-trend"') && html.includes('id="goldMonthlyChart"'),
  '小图容器结构齐全');
for (const kw of ['gmTitle', 'gmLast', 'class="st-head"', 'class="st-foot"',
                  'Math.round(mx)', '口径：世界银行 Pink Sheet 月度 Gold']) {
  check(!html.includes(kw), `已移除：${kw}`);
}
check(html.includes('viewBox="0 0 460 80"'), '图已缩小为 460×80');
const svgBody = (html.match(/<svg id="goldMonthlyChart"[^>]*>([\s\S]*?)<\/svg>/) || [])[1] || '';
check(svgBody.trim() === '', 'SVG 为空容器（图形全由 IIFE 渲染）');
check(html.includes('.gm-vlabel{'), '左侧竖排标签样式存在');
check((html.match(/class="hist-chart"/g) || []).length === 1, '主页面年均价图仍在（模板区 A1 历史图已删）');

// --- DOM stub ---
function makeEl(id) {
  const el = {
    id, _html: '', _text: '', attrs: {}, style: {}, listeners: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    appendChild() {}, setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    removeAttribute(k) { delete this.attrs[k]; }, hasAttribute(k) { return k in this.attrs; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    removeEventListener() {}, scrollIntoView() {},
    querySelector() { return makeEl('q'); }, querySelectorAll() { return []; },
  };
  Object.defineProperty(el, 'innerHTML', { get() { return this._html; }, set(v) { this._html = v; } });
  Object.defineProperty(el, 'textContent', { get() { return this._text; }, set(v) { this._text = v; } });
  Object.defineProperty(el, 'viewBox', { get() { return { baseVal: { width: 920, height: 290 } }; } });
  return el;
}

function run(withData) {
  const els = {};
  const getEl = (id) => (els[id] || (els[id] = makeEl(id)));
  const sandbox = {
    console, Math, Date, JSON, parseInt, parseFloat, isNaN,
    String, Number, Array, Object, RegExp, Promise,
    setInterval: () => 0, clearInterval: () => {}, setTimeout: () => 0, clearTimeout: () => {},
    requestAnimationFrame: () => 0,
    fetch: () => Promise.resolve({ json: () => Promise.resolve({}) }),
    location: { protocol: 'http:', href: 'http://localhost/' },
    navigator: { userAgent: 'node' },
    IntersectionObserver: class { observe() {} unobserve() {} },
    document: {
      getElementById: getEl, querySelector: () => makeEl('q'), querySelectorAll: () => [],
      createElement: () => makeEl('c'), addEventListener: () => {},
    },
  };
  sandbox.window = sandbox;
  sandbox.window.addEventListener = () => {};
  vm.createContext(sandbox);
  vm.runInContext(gd[1], sandbox);
  let panelSrc = gp[1];
  if (!withData) {
    const raw = gp[1].replace(/^\s*window\.GOLD_PANEL_DATA\s*=\s*/, '').replace(/;\s*$/, '');
    const obj = JSON.parse(raw);
    delete obj.goldMonthly;
    panelSrc = 'window.GOLD_PANEL_DATA = ' + JSON.stringify(obj) + ';';
  }
  vm.runInContext(panelSrc, sandbox);
  let threw = null;
  // 必须用精确的 '<script>'：数据块是 <script id="...">，若也匹配会把上面自定义的
  // panelSrc（已删 goldMonthly）覆盖回去，空数据兜底测试就永远测不到。
  for (const [i, sc] of [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).entries()) {
    if (!sc.trim()) continue;
    try { vm.runInContext(sc, sandbox, { filename: `inline#${i}.js` }); }
    catch (e) { threw = e.message; }
  }
  return { sandbox, els, threw };
}

(async () => {
  const r = run(true);
  check(!r.threw, '内联脚本无异常', r.threw || '');
  const st = r.sandbox.__goldMonthlyStat;
  check(!!st && !st.empty && st.points === GM.length, 'IIFE 渲染全部月份点',
    st ? `${st.points} 点 / ${st.year} 年` : '');
  const svg = r.els.goldMonthlyChart;
  check(!!svg && /<path class="gm-line"/.test(svg._html) && /<path class="gm-area"/.test(svg._html),
    '产出折线与面积路径');
  check((svg._html.match(/<circle class="gm-dot"/g) || []).length === GM.length,
    '每月一个圆点', String((svg._html.match(/<circle class="gm-dot"/g) || []).length));
  check(/月<\/text>/.test(svg._html), 'X 轴月份标签已渲染');
  const vchars = [...svg._html.matchAll(/<text class="gm-vlabel"[^>]*>([^<]*)<\/text>/g)]
    .map(m => m[1]);
  check(vchars.length === 6 && vchars.join('') === GM[0].month.slice(0, 4) + '月度',
    '左侧竖排「年份+月度」',
    vchars.join('') + ' | ' + (svg._html.match(/gm-vlabel[^<]*/g) || []).slice(0, 2).join(' ; '));
  check(!/class="gm-lbl"[^>]*>5\d{3}</.test(svg._html), 'Y 轴上限数字（5162 类）已删');

  const e = run(false);
  check(!e.threw, '空数据路径无异常', e.threw || '');
  check(e.sandbox.__goldMonthlyStat && e.sandbox.__goldMonthlyStat.empty === true,
    '空数据走兜底');
  check(/暂无月度数据/.test(e.els.goldMonthlyChart._html), '空态提示文案正确');

  console.log('\nRESULT:', fail === 0 ? 'GOLD MONTHLY OK' : `${fail} CHECK(S) FAILED`);
  process.exit(fail === 0 ? 0 : 1);
})();
