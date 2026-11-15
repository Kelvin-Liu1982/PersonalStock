// 历史高点卡片 · 三锚动态描述校验（2026-11-15）
// 1) 静态「盘中最低 3959 / 回落 26%」字段已清零，note 由 #athNote 动态渲染
// 2) DOM-stub 实跑：三锚（ATH / 当前价+回落% / 最新月均）按数据正确拼装
// 3) 刷新联动：改 D.spot 后重算回落%（跌破 ATH 低点也不过时）
// 4) 空 goldMonthly 兜底不崩
// 用法：node tools/test_ath_note.js
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

// --- 1) 静态字段已清理 ---
check(html.includes('id="athNote"'), 'note 已改为 #athNote 动态容器');
for (const kw of ['data-field="first4k"', 'data-field="lowValue"', 'data-field="lowDrop"',
                  '2026 上半年宽幅震荡']) {
  check(!html.includes(kw), `静态字段/文案已清：${kw}`);
}
check(html.includes('window.__athNoteRender=renderAthNote'), '渲染函数已挂全局（刷新可重算）');
check(/renderAthNote\(\);/.test(html), 'applyData 内调用 renderAthNote');
check(html.includes('2025-10 首次突破 $4,000') && /6-24 盘中[^<]*<span class="k"/.test(html),
  '分析正文同类字样保留（不在历史高点区域）');

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

function run(withMonthly) {
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
  if (!withMonthly) {
    const obj = JSON.parse(gp[1].replace(/^\s*window\.GOLD_PANEL_DATA\s*=\s*/, '').replace(/;\s*$/, ''));
    delete obj.goldMonthly;
    panelSrc = 'window.GOLD_PANEL_DATA = ' + JSON.stringify(obj) + ';';
  }
  vm.runInContext(panelSrc, sandbox);
  let threw = null;
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
  const st = r.sandbox.__athNoteStat;
  check(!!st, '__athNoteStat 已产出');
  const h = r.els.athNote ? r.els.athNote._html : '';
  // 期望值改为从注入数据读取（2026-11-15 起不再硬编码 ath/spot，避免数据刷新后误报）
  const D = r.sandbox.GOLD_DATA;
  const athNum = Number(String(D.ath).replace(/[^\d.]/g, ''));
  const spotNum = Number(String(D.spot).replace(/[^\d.]/g, ''));
  const athDS = String(D.athDate).slice(5).replace(/^0/, '');
  check(h.indexOf('历史高点 <b>$' + athNum.toLocaleString('en-US') + '</b>（' + athDS + ' 盘中）') >= 0,
    '锚1：历史高点 + 日期', h.slice(0, 60));
  check(h.indexOf('当前 <b>$' + spotNum.toLocaleString('en-US') + '</b>') >= 0, '锚2a：当前价来自 spot');
  const expectDrop = ((athNum - spotNum) / athNum * 100).toFixed(1);
  check(h.includes('较 ATH 回落 <b>' + expectDrop + '%</b>'), '锚2b：回落% 按 (ATH−spot)/ATH 计算', expectDrop + '%');
  check(/最新月均 <b>\$4,105<\/b>（10月）/.test(h), '锚3：最新月均取 goldMonthly 末条');
  check(!/3,959|26%|首次突破|上半年/.test(h), '动态文案无静态低点残留');

  // --- 3) 刷新联动：模拟刷新按钮把 spot 改到 $3,888（已跌破旧低点） ---
  const REFRESH = '$3,500';   // 低于历史低点 3,959，验证回落%随之重算
  r.sandbox.GOLD_DATA.spot = REFRESH;
  r.sandbox.__athNoteRender();
  const h2 = r.els.athNote._html;
  const expectDrop2 = ((athNum - 3500) / athNum * 100).toFixed(1);
  check(h2.indexOf('当前 <b>' + REFRESH + '</b>') >= 0, '刷新联动：当前价同步更新');
  check(h2.includes('较 ATH 回落 <b>' + expectDrop2 + '%</b>'),
    '刷新联动：回落% 重算（跌破旧 3,959 也不过时）', expectDrop2 + '%');
  check(!/3,959/.test(h2), '新价低于旧低点时不再出现 3,959');

  // --- 4) 空 goldMonthly 兜底 ---
  const e = run(false);
  check(!e.threw, '空 goldMonthly 无异常', e.threw || '');
  const eh = e.els.athNote ? e.els.athNote._html : '';
  check(/历史高点 <b>/.test(eh) && !/最新月均/.test(eh), '空月度数据：省略月均锚但不崩');

  console.log('\nRESULT:', fail === 0 ? 'ATH NOTE OK' : `${fail} CHECK(S) FAILED`);
  process.exit(fail === 0 ? 0 : 1);
})();
