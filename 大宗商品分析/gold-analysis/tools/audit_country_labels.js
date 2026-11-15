// 校验图 1 几何：国名 / 数值标签是否重叠、是否出界、数值与数据是否一致
const fs = require('fs');
const html = fs.readFileSync(__dirname + '/../output/gold-terminal.html', 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);

let vb = '', inner = '';
const svg = { id: 'cbCountry', set innerHTML(v) { inner = v; }, get innerHTML() { return inner; },
  setAttribute(k, v) { if (k === 'viewBox') vb = v; }, getAttribute() { return null; } };
const mk = id => ({ id, _h: '', set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h; },
  setAttribute() {}, getAttribute() { return null; }, style: {} });
const el = id => ({ id, _t: '', set textContent(v) { this._t = v; }, get textContent() { return this._t; },
  setAttribute() {}, getAttribute: () => null, addEventListener() {},
  classList: { add() {}, toggle() {}, contains: () => false }, style: {} });
const byId = { cbCountry: svg };
['cbMonthly', 'cnCbMonthly'].forEach(i => byId[i] = mk(i));
global.window = { GOLD_PANEL_DATA: {}, addEventListener() {}, location: { protocol: 'file:' }, confirm: () => false, alert() {}, prompt() {} };
global.navigator = {}; global.setInterval = () => {};
global.IntersectionObserver = class { constructor() {} observe() {} unobserve() {} };
global.document = { getElementById: id => byId[id] || el(id), querySelector: () => el('q'), querySelectorAll: () => [],
  createElement: () => el('t'), body: { appendChild() {}, removeChild() {} } };
try { eval(scripts[1]); } catch (e) {}
try { eval(scripts[2]); } catch (e) {}

const m = (vb.match(/0 0 (\d+) (\d+)/) || []);
const W = +m[1], H = +m[2];
const rows = window.GOLD_PANEL_DATA.cbCountry || [];
const texts = [...inner.matchAll(/<text[^>]*x="(-?[\d.]+)"[^>]*y="(-?[\d.]+)"[^>]*text-anchor="(\w+)"[^>]*>([^<]*)</g)]
  .map(t => ({ x: +t[1], y: +t[2], a: t[3], t: t[4] }));
const rects = [...inner.matchAll(/<rect x="(-?[\d.]+)" y="(-?[\d.]+)" width="([\d.]+)" height="([\d.]+)"/g)]
  .map(r => ({ x: +r[1], y: +r[2], w: +r[3], h: +r[4] }));
const CW = 7.2;                                   // mono 12px 约 7.2px/字符
const box = o => {
  const w = o.t.length * CW;
  const x = o.a === 'end' ? o.x - w : (o.a === 'middle' ? o.x - w / 2 : o.x);
  return { x0: x, x1: x + w, y0: o.y - 10, y1: o.y + 3, t: o.t };
};
const nameLabels = texts.filter(o => rows.some(r => r.name === o.t)).map(box);
const valLabels = texts.filter(o => /^[+-]?\d+(\.\d+)?$/.test(o.t)).map(box);

console.log('viewBox =', vb, '| 国名', nameLabels.length, '| 数值标签', valLabels.length, '| 条', rects.length);

const oob = [...nameLabels, ...valLabels].filter(b => b.x0 < 0 || b.x1 > W || b.y0 < 0 || b.y1 > H);
console.log('越界元素:', oob.length, oob.slice(0, 3));

let hit = 0; const detail = [];
for (const a of nameLabels) for (const b of valLabels) {
  if (a.y1 > b.y0 && b.y1 > a.y0 && a.x1 > b.x0 && b.x1 > a.x0) { hit++; if (detail.length < 4) detail.push(a.t + ' × ' + b.t); }
}
console.log('国名×数值 重叠:', hit, detail);

const shown = valLabels.map(b => b.t).filter(t => /[+-]/.test(t));
const expect = rows.map(r => (r.value > 0 ? '+' : '') + r.value);
const miss = expect.filter(v => !shown.includes(v));
console.log('数据值缺失:', miss.length ? miss : '无', '| 条数 == 行数:', rects.length === rows.length);

const nameRight = Math.max(...nameLabels.map(b => b.x1));
const leftRect = Math.min(...rects.map(r => r.x));
console.log('国名右边界', nameRight.toFixed(1), '| 最左条起点', leftRect.toFixed(1), '| 不侵入:', leftRect > nameRight);
const bad = inner.match(/NaN|undefined/g);
console.log('异常值:', bad ? bad.length : 0);
console.log('结论:', (!oob.length && !hit && !miss.length && !bad && leftRect > nameRight) ? 'PASS' : 'FAIL');