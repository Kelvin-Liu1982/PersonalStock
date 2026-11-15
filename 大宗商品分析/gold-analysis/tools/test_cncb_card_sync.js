// 功能测试：卡片三项信息随 cnMonthly 自动更新
// 场景 A = 当前 xlsx 数据；场景 B = 假设追加 2026-10(储备 7800 / 增持 53 / 连续 24)
// ⚠️ 2026-11-15 起断言改为**数据驱动**：A 只校验格式与自洽，不写死 xlsx 当前值
//    （原断言写死 2,410t / 23 / 103t / 9 月储备 7,747，xlsx 更新到 2026-10 后即误报 FAIL）。
//    B/C 的期望值来自脚本自己注入的固定数据，仍可硬编码。
const fs = require('fs');
const P = '/Users/sto1/WorkBuddy/大宗商品分析追踪/gold-analysis/output/gold-terminal.html';
const html = fs.readFileSync(P, 'utf8');
const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);

function run(mutate) {
  const nodes = {};
  ['cnCbOwnT', 'cnCbStreak', 'cnCbYtdYear', 'cnCbYtd', 'CNCB_sub'].forEach(id => {
    nodes[id] = { id, _t: '', set textContent(v) { this._t = v; }, get textContent() { return this._t; } };
  });
  const svg = { id: 'cnCbMonthly', _html: '', set innerHTML(v) { this._html = v; }, get innerHTML() { return this._html; } };
  const byId = Object.assign({ cnCbMonthly: svg }, nodes);
  const mk = () => ({ setAttribute() {}, getAttribute: () => null, addEventListener() {}, classList: { add() {}, toggle() {}, contains: () => false }, querySelector: () => mk(), querySelectorAll: () => [], style: {}, scrollIntoView() {}, hasAttribute: () => false, removeAttribute() {}, focus() {} });
  global.window = { GOLD_PANEL_DATA: {}, addEventListener() {}, location: { protocol: 'file:' }, confirm: () => false, alert() {}, prompt() {} };
  global.navigator = {};
  global.IntersectionObserver = class { constructor() {} observe() {} unobserve() {} };
  global.document = {
    getElementById: (id) => (byId[id] || null),
    querySelector: () => mk(), querySelectorAll: () => [],
    createElement: () => mk(), body: { appendChild() {}, removeChild() {} },
  };
  global.setInterval = () => {};
  eval(scripts[1]);                 // GOLD_PANEL_DATA
  mutate(window.GOLD_PANEL_DATA);
  eval(scripts[2]);                 // 主脚本
  return {
    own: nodes.cnCbOwnT.textContent,
    streak: nodes.cnCbStreak.textContent,
    year: nodes.cnCbYtdYear.textContent,
    ytd: nodes.cnCbYtd.textContent,
    sub: nodes.CNCB_sub.textContent,
    chartLen: svg.innerHTML.length,
  };
}

const A = run(() => {});
console.log('A 当前 xlsx 数据:');
console.log('   持金吨数:', A.own, '| 连续:', A.streak, '| 年份:', A.year, '| YTD:', A.ytd);
console.log('   副行:', A.sub);

const B = run((d) => { d.cnMonthly.push({ month: '2026-11', reserve: 7860, add: 30, streak: 25 }); });
console.log('B 追加 2026-11 后（同一份代码）:');
console.log('   持金吨数:', B.own, '| 连续:', B.streak, '| 年份:', B.year, '| YTD:', B.ytd);
console.log('   副行:', B.sub);

const C = run((d) => {
  // 跨年重置需要上一年 12 月作 YTD 基准，故构造 2026-12 → 2027-01 两行
  d.cnMonthly = [
    { month: '2026-12', reserve: 7800, add: 0, streak: 24 },
    { month: '2027-01', reserve: 7850, add: 51, streak: 25 },
  ];
});
console.log('C 跨年（2027-01）:');
console.log('   持金吨数:', C.own, '| 连续:', C.streak, '| 年份:', C.year, '| YTD:', C.ytd);
console.log('   副行:', C.sub);

const isT = (v) => /^[\d,]+t$/.test(v || '');
const numOf = (v) => parseInt(String(v || '').replace(/[^\d]/g, ''), 10) || 0;
// A：只校验格式、自洽与图表已渲染（不依赖 xlsx 具体数值）
const Aok = isT(A.own) && /^\d+$/.test(A.streak) && /^\d{4}$/.test(A.year)
  && isT(A.ytd) && /储备/.test(A.sub) && /万盎司/.test(A.sub) && A.chartLen > 0;
// B：追加 2026-10 后，卡片应改取注入行的值，且 YTD 必须增长
const Bok = B.own === '2,445t' && B.streak === '25'
  && B.sub.indexOf('11 月储备 7,860 万盎司') === 0
  && isT(B.ytd) && numOf(B.ytd) > numOf(A.ytd);
// C：跨年时 YTD 重置为当年累计（51 万盎司 ≈ 16t）
const Cok = C.year === '2027' && C.ytd === '16t';
const ok = Aok && Bok && Cok;
console.log('\n断言明细: A(格式/自洽)=' + Aok + ' B(随新数据更新)=' + Bok + ' C(跨年重置)=' + Cok);
console.log('结论:', ok ? 'PASS（卡片随图自动更新，含跨年重置 YTD）' : 'FAIL');
process.exit(ok ? 0 : 1);