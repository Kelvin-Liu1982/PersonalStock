// 「刷新实时金价」按钮迁移校验（2026-11-15）
// 1) 原数据状态条整块已删（dbMode / dbTime / databar 均不存在）
// 2) 按钮位于 HERO「当前报盘」卡片的 .spot-head 右上角；结果提示元素已彻底删除
// 3) DOM-stub 实跑：成功 → spot/tickerXau 更新 + spotAsOf 写当天日期；失败 → 静默不更新日期
// 4) 全程无任何结果提示文案；file:// 下按钮禁用
// 用法：node tools/test_refresh_button.js
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

// --- 1) 结构 ---
for (const kw of ['class="databar"', 'id="databar"', 'id="dbMode"', 'id="dbTime"',
                  'id="dbHint"', '.hero .rf-hint', '.databar{']) {
  check(!html.includes(kw), `状态条 / 结果提示已清除：${kw}`);
}
for (const kw of ['已通过 ', '获取最新现货价。', '✓ 已刷新', '✗ 获取失败', 'setMode(']) {
  check(!html.includes(kw), `无结果提示文案/逻辑：${kw}`);
}
check(html.includes('class="spot-head"') && html.includes('class="spot-actions"'), 'HERO 新增 spot-head 布局');
const hero = html.slice(html.indexOf('<div class="hero reveal"'), html.indexOf('<div class="eventbar"'));
check(hero.includes('id="refreshBtn"'), '按钮位于 HERO 区域内');
check(/class="spot-head"[\s\S]{0,700}id="refreshBtn"/.test(hero), '按钮在 spot-head 行（右上角）');
check(html.includes('.hero .rf-btn{'), '按钮样式已迁移到 HERO');
check((html.match(/id="refreshBtn"/g) || []).length === 1, 'refreshBtn 唯一');
check(html.includes("D.spot=s; D.tickerXau=s; D.spotAsOf=todayStr(); applyData();"),
  '核心逻辑：成功时回写 spotAsOf 日期');

// --- DOM stub ---
const gd = html.match(/\/\*GOLD_DATA_START\*\/([\s\S]*?)\/\*GOLD_DATA_END\*\//);
const gp = html.match(/\/\*GOLD_PANEL_DATA_START\*\/([\s\S]*?)\/\*GOLD_PANEL_DATA_END\*\//);
function makeEl(id) {
  const el = {
    id, _html: '', _text: '', attrs: {}, style: {}, listeners: {}, disabled: false,
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

function makeFieldEl(field) {
  const el = makeEl('field:' + field);
  el.attrs['data-field'] = field;
  return el;
}

function run(protocol, price, fail) {
  const els = {};
  // 真实 DOM 里 [data-field] 由 applyData() 回填；这里造一个 spotAsOf 元素验证日期确实落到标签上
  const fieldEls = ['spotAsOf', 'spot', 'tickerXau'].map(makeFieldEl);
  // 关键：真实 DOM 里 dbMode / dbTime 已删除，这里也返回 null 以验证 null 保护
  const getEl = (id) => (id === 'dbMode' || id === 'dbTime' || id === 'dbHint') ? null
    : (els[id] || (els[id] = makeEl(id)));
  const sandbox = {
    console, Math, Date, JSON, parseInt, parseFloat, isNaN,
    String, Number, Array, Object, RegExp, Promise,
    setInterval: () => 0, clearInterval: () => {}, setTimeout: () => 0, clearTimeout: () => {},
    requestAnimationFrame: () => 0,
    fetch: fail ? () => Promise.reject(new Error('network'))
                : () => Promise.resolve({ json: () => Promise.resolve(price ? { price } : {}) }),
    location: { protocol, href: 'http://localhost/' },
    navigator: { userAgent: 'node' },
    IntersectionObserver: class { observe() {} unobserve() {} },
    document: {
      getElementById: getEl, querySelector: () => makeEl('q'),
      querySelectorAll: (sel) => sel === '[data-field]' ? fieldEls : [],
      createElement: () => makeEl('c'), addEventListener: () => {},
    },
  };
  sandbox.window = sandbox;
  sandbox.window.addEventListener = () => {};
  vm.createContext(sandbox);
  vm.runInContext(gd[1], sandbox);
  vm.runInContext(gp[1], sandbox);
  let threw = null;
  for (const [i, sc] of [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]).entries()) {
    if (!sc.trim()) continue;
    try { vm.runInContext(sc, sandbox, { filename: `inline#${i}.js` }); }
    catch (e) { threw = e.message; }
  }
  return { sandbox, els, fieldEls, threw };
}

(async () => {
  // --- 2) http 下点击 ---
  const r = run('http:', 3887.600098);
  check(!r.threw, '状态元素缺失时内联脚本无异常', r.threw || '');
  const btn = r.els.refreshBtn;
  check(!!btn && (btn.listeners.click || []).length === 1, 'click 处理器已注册');
  check(btn && btn.disabled === false, 'http 下按钮可用');
  const d0 = new Date();
  const today = d0.getFullYear() + '-' + ('0' + (d0.getMonth() + 1)).slice(-2)
    + '-' + ('0' + d0.getDate()).slice(-2);
  const D0 = r.sandbox.GOLD_DATA;
  check(/^\d{4}-\d{2}$/.test(String(D0.spotAsOf)), '初始标签为构建期快照月份', D0.spotAsOf);
  if (btn && btn.listeners.click) {
    btn.listeners.click[0]();
    await new Promise(res => setImmediate(res));
    await new Promise(res => setImmediate(res));
    const D = r.sandbox.GOLD_DATA;
    check(D.spot === '$3,888' && D.tickerXau === '$3,888', '点击后 spot / tickerXau 同步更新',
      `${D.spot} / ${D.tickerXau}`);
    check(D.spotAsOf === today, '成功时 SPOT 标签更新为当天日期', D.spotAsOf);
    const tag = r.fieldEls.find(f => f.getAttribute('data-field') === 'spotAsOf');
    check(tag && tag.textContent === today, 'applyData 已把日期写入「当前报盘 · SPOT (…)」标签',
      tag ? tag.textContent : '(缺失)');
    check(btn.textContent === '⟳ 刷新实时金价', '按钮恢复原文字，无结果提示', btn.textContent);
    check(!r.els.dbHint, '不存在结果提示元素');
  }

  // --- 失败：静默，不更新日期 ---
  // 期望值从注入数据读取（而非硬编码），否则每次数据刷新都会误报失败
  const f2 = run('http:', 0, false);      // 返回体无 price
  const D2 = f2.sandbox.GOLD_DATA;
  const d2Init = { asOf: D2.spotAsOf, spot: D2.spot };
  f2.els.refreshBtn.listeners.click[0]();
  await new Promise(res => setImmediate(res));
  await new Promise(res => setImmediate(res));
  check(D2.spotAsOf === d2Init.asOf && D2.spot === d2Init.spot, '无 price 时日期与价格均不更新',
    `${D2.spotAsOf} / ${D2.spot}`);
  check(f2.els.refreshBtn.textContent === '⟳ 刷新实时金价', '无 price 时按钮静默恢复');

  const f3 = run('http:', 3887.6, true);  // fetch reject
  const D3 = f3.sandbox.GOLD_DATA;
  const d3Init = { asOf: D3.spotAsOf, spot: D3.spot };
  f3.els.refreshBtn.listeners.click[0]();
  await new Promise(res => setImmediate(res));
  await new Promise(res => setImmediate(res));
  check(D3.spotAsOf === d3Init.asOf && D3.spot === d3Init.spot, '网络失败时日期与价格均不更新');
  check(f3.els.refreshBtn.textContent === '⟳ 刷新实时金价', '网络失败时按钮静默恢复');
  check(!f3.threw, '失败路径无异常', f3.threw || '');

  // --- 3) file:// 应禁用 ---
  const f = run('file:', 3887.600098);
  check(!f.threw, 'file:// 下无异常', f.threw || '');
  check(f.els.refreshBtn && f.els.refreshBtn.disabled === true, 'file:// 下按钮禁用');
  check(!((f.els.refreshBtn.listeners || {}).click || []).length, 'file:// 下不注册点击');

  // --- 4) 数据块未受影响 ---
  check([...html.matchAll(/<div\b/g)].length === [...html.matchAll(/<\/div>/g)].length, 'div 标签平衡');

  console.log('\nRESULT:', fail === 0 ? 'REFRESH BUTTON OK' : `${fail} CHECK(S) FAILED`);
  process.exit(fail === 0 ? 0 : 1);
})();
