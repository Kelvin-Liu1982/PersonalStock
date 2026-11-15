// 事件条（event bar）校验：确认 event 三字段是「数据驱动 + 可自动刷新」，不是硬编码。
// 检查项：
//   1) GOLD_DATA 里 eventDate/eventText/eventSource 三个显示字段齐全且非空
//   2) HTML 中 .eventbar 三个可见元素全部绑了 data-field（evdate/evtxt/evsrc）；
//       evpct（涨跌幅显示）已按用户要求移除，数据块 eventPct 字段仍保留供回溯
//   3) 旧 HERO note（涨幅/事件描述两行）已于 2026-11-15 被月度金价小图替换；事件信息仅由 eventbar 承载
//   4) GOLD_PANEL_DATA.events 第 0 条 === event 条显示的这条（首行一致性）
//   5) eventText 长度未超过 config 的截断上限；eventDate 形如 YYYY-MM-DD
//   6) EVENT 是可点按钮（#evBtn）：点击在候选中切换——首点切最新、循环后回到默认条
// 用法：node tools/test_event_bar.js
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const HTML = path.join(__dirname, '..', 'output', 'gold-terminal.html');
const html = fs.readFileSync(HTML, 'utf8');

const gd = html.match(/\/\*GOLD_DATA_START\*\/([\s\S]*?)\/\*GOLD_DATA_END\*\//);
const gp = html.match(/\/\*GOLD_PANEL_DATA_START\*\/([\s\S]*?)\/\*GOLD_PANEL_DATA_END\*\//);
if (!gd || !gp) { console.error('✗ HTML 中未找到数据块标记'); process.exit(1); }

const sandbox = { window: {}, Math, Date, JSON };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(gd[1], sandbox);
vm.runInContext(gp[1], sandbox);
const D = sandbox.GOLD_DATA || sandbox.window.GOLD_DATA;
const P = sandbox.GOLD_PANEL_DATA || sandbox.window.GOLD_PANEL_DATA;

let fail = 0;
function check(cond, msg, extra) {
  console.log(`${cond ? '✓' : '✗'} ${msg}${extra ? '  ' + extra : ''}`);
  if (!cond) fail++;
}

// --- 1) 字段齐全 ---
const FIELDS = ['eventDate', 'eventText', 'eventSource'];
const BACKFIELD = 'eventPct'; // 数据块保留，但页面不再显示
for (const k of FIELDS) {
  check(D && typeof D[k] === 'string' && D[k].trim() !== '' && D[k] !== '—',
    `GOLD_DATA.${k} 非空`, D ? `= ${D[k]}` : '');
}
// 数据块字段保留（xlsx 事件流 pct 列供回溯），但页面已不显示
check(D && typeof D[BACKFIELD] === 'string', `GOLD_DATA.${BACKFIELD} 数据块字段仍保留`);

// --- 2) eventbar 三个可见 span 绑定 ---
const bar = (html.match(/<div class="eventbar"[\s\S]*?<\/div>/) || [''])[0];
check(bar.length > 0, '找到 .eventbar 容器');
const want = { evdate: 'eventDate', evtxt: 'eventText', evsrc: 'eventSource' };
for (const [cls, field] of Object.entries(want)) {
  // class 可能是 "evdate mono"，不能只匹配 class="evdate"
  const re = new RegExp(
    `class="[^"]*\\b${cls}\\b[^"]*"[^>]*data-field="${field}"` +
    `|data-field="${field}"[^>]*class="[^"]*\\b${cls}\\b[^"]*"`);
  check(re.test(bar), `.eventbar .${cls} 绑定 data-field="${field}"`);
}

// --- 3) 旧两行文字已被月度金价小图替换，事件信息只在 eventbar ---
check(!html.includes('▲ 自 6 月低点') && !html.includes('上半年受「加息交易」'),
  '「自低点反弹 / 宏观背景」两行静态文字已移除');
check(html.includes('id="goldMonthlyChart"') && html.includes('class="spot-trend"'),
  '当前报盘卡片已改为月度金价小图');
check((html.match(/data-field="eventText"/g) || []).length === 1,
  'eventText 仅剩 eventbar 一处绑定');
for (const kw of ['class="evpct', 'data-field="eventPct"', 'tintEvent', '.eventbar .evpct{']) {
  check(!html.includes(kw), `页面已移除涨跌幅显示相关：${kw}`);
}
check(/\.eventbar \.evdate\{[^}]*color:var\(--txt-dim\)/.test(html),
  'evdate 恢复中性色（不再按涨跌上色）');

// --- 4) 事件流首行一致 ---
const ev = (P && P.events) || [];
check(ev.length > 0, 'GOLD_PANEL_DATA.events 非空', `=${ev.length} 条`);
if (ev.length) {
  const e0 = ev[0];
  check(e0.date === D.eventDate, 'events[0].date === eventDate', `${e0.date} / ${D.eventDate}`);
  check(e0.title === D.eventText, 'events[0].title === eventText');
  check(e0.source === D.eventSource, 'events[0].source === eventSource');
  check(typeof e0.link === 'string' && /^https?:/.test(e0.link), 'events[0].link 为 http(s) 链接');
}

// --- 5) 格式 ---
const latin = (s) => [...s].filter((c) => c.charCodeAt(0) < 0x2e80).length / s.length > 0.6;
const limit = latin(D.eventText || '') ? 78 : 34;
check((D.eventText || '').length <= limit + 1, 'eventText 未超截断长度',
  `${(D.eventText || '').length} ≤ ${limit}`);
check(/^\d{4}-\d{2}-\d{2}$/.test((D.eventDate || '').trim()), 'eventDate 形如 YYYY-MM-DD', D.eventDate);

// --- 6) EVENT 按钮：DOM-stub 实跑主脚本，模拟点击验证切换逻辑 ---
const barBtn = /<button[^>]*id="evBtn"[^>]*>/.test(html);
check(barBtn, 'EVENT 标签是按钮（<button id="evBtn">）');

// 轻量 DOM stub（与 verify_render.js 同款思路）：按 id 缓存元素、捕获 addEventListener
function makeEl(id) {
  const el = {
    id, _html: '', _text: '', attrs: {}, style: {}, listeners: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    appendChild() {}, setAttribute(k, v) { this.attrs[k] = v; },
    getAttribute(k) { return (k in this.attrs) ? this.attrs[k] : null; },
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
const els = {};
const getEl = (id) => (els[id] || (els[id] = makeEl(id)));
const stub = {
  console, Math, Date, JSON, parseInt, parseFloat, isNaN,
  String, Number, Array, Object, RegExp,
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
stub.window = stub;
stub.window.addEventListener = () => {};
vm.createContext(stub);
vm.runInContext(gd[1], stub, { filename: 'GOLD_DATA.js' });
vm.runInContext(gp[1], stub, { filename: 'GOLD_PANEL_DATA.js' });

let threw = false;
for (const [i, sc] of [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).entries()) {
  if (!sc.trim()) continue;
  try { vm.runInContext(sc, stub, { filename: `inline#${i}.js` }); }
  catch (e) { threw = true; console.error(`  ✗ script #${i} threw: ${e.message}`); }
}
check(!threw, '全部内联脚本在 stub 中无异常');

const DB = stub.GOLD_DATA;
const handlers = (els.evBtn && els.evBtn.listeners.click) || [];
check(handlers.length > 0, 'evBtn 注册了 click 处理器');
if (handlers.length && ev.length > 2) {
  const click = () => handlers.forEach((fn) => fn());
  click(); // 第 1 次：切到最新候选
  check(DB.eventDate === ev[1].date && DB.eventText === ev[1].title,
    '第 1 次点击 → 切到候选[1]（日期最新）', `${DB.eventDate} · ${DB.eventSource}`);
  click(); click(); // 第 2/3 次：继续循环
  check(DB.eventDate === ev[3].date, '第 3 次点击 → 候选[3]', DB.eventDate);
  // 已到 idx3，再点 len-3 次走完一圈（第 len 次点击回到 events[0]）
  for (let k = 0; k < ev.length - 3; k++) click();
  check(DB.eventDate === ev[0].date && DB.eventText === ev[0].title,
    `循环走完（${ev.length} 次点击）回到默认条 events[0]`, `${DB.eventDate} · ${DB.eventText.slice(0, 18)}`);
  click();
  check(DB.eventDate === ev[1].date, '再点一次重新进入循环 → 候选[1]', DB.eventDate);
  check(/^https?:/.test(ev[1].link || ''), '候选[1] 也带链接');
}

console.log('\nRESULT:', fail === 0 ? 'EVENT BAR OK' : `${fail} CHECK(S) FAILED`);
process.exit(fail === 0 ? 0 : 1);
