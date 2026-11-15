// 白底浅色主题校验（方案 2 · 2026-11-15）
// 1) :root 14 个颜色变量为浅色板，且关键前景色满足 WCAG AA 对比度
// 2) 无暗色 hex 残留（42 种原暗色 / 低对比色）
// 3) 暗色专用效果已改写（斜纹 / 渐变 / 阴影 / 反白文字）
// 4) 数据块与结构锚点未受影响
// 用法：node tools/test_light_theme.js
const fs = require('fs');
const path = require('path');

const HTML = path.join(__dirname, '..', 'output', 'gold-terminal.html');
const html = fs.readFileSync(HTML, 'utf8');

let fail = 0;
const check = (ok, msg, extra) => {
  console.log(`${ok ? '✓' : '✗'} ${msg}${extra ? '  ' + extra : ''}`);
  if (!ok) fail++;
};

// --- 1) 变量板 ---
const VARS = {
  '--bg': '#ffffff', '--bg-2': '#f7f8fa', '--panel': '#ffffff',
  '--line': '#e3e7ed', '--line-2': '#cbd3dd',
  '--txt': '#1f2933', '--txt-dim': '#5b6672', '--txt-faint': '#8a94a1',
  '--gold': '#9A6B00', '--gold-2': '#8A6508', '--gold-dim': '#E8D9A8',
  '--up': '#1f7a4d', '--down': '#c0392b', '--accent-cool': '#2E6D9E',
};
const root = (html.match(/:root\{([\s\S]*?)\}/) || [])[1] || '';
check(root.length > 0, '找到 :root 变量块');
for (const [k, v] of Object.entries(VARS)) {
  const m = root.match(new RegExp(k.replace(/[-]/g, '\\$&') + ':\\s*(#[0-9a-fA-F]{3,6})'));
  check(!!m && m[1].toLowerCase() === v.toLowerCase(), `${k} = ${v}`, m ? m[1] : '(缺失)');
}

// WCAG 相对亮度 / 对比度
function lum(h) {
  const s = h.replace('#', '');
  const c = [0, 2, 4].map(i => parseInt(s.slice(i, i + 2), 16) / 255)
    .map(v => v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
const cr = (a, b = '#ffffff') => {
  const l = [lum(a), lum(b)].sort((x, y) => y - x);
  return (l[0] + 0.05) / (l[1] + 0.05);
};
for (const [name, color, min] of [
  ['--txt 主文字', VARS['--txt'], 4.5],
  ['--txt-dim 次文字', VARS['--txt-dim'], 4.5],
  ['--gold 强调金', VARS['--gold'], 4.5],
  ['--up 涨绿', VARS['--up'], 4.5],
  ['--down 跌红', VARS['--down'], 4.5],
  ['金徽章白字', '#ffffff', 4.5],
]) {
  const bg = name === '金徽章白字' ? VARS['--gold'] : '#ffffff';
  const v = cr(color, bg);
  check(v >= min, `${name} 对比度 ≥ ${min}`, `${v.toFixed(2)}:1`);
}

// --- 2) 暗色残留 ---
const DARK = ['#0a0d12', '#0d1118', '#0c1118', '#1b222c', '#262f3b', '#c7d0db',
  '#76828f', '#0e131b', '#0c1119', '#0f141d', '#0b0f16', '#0b1017', '#14202c',
  '#1b2a38', '#11161f', '#0a0e14', '#141922', '#101821', '#17202b', '#080b10',
  '#1a222c', '#7d8a98', '#3a4653', '#131a24', '#4a5562', '#6b7785',
  '#E0B84C', '#C9A227', '#8a7223', '#4fb477', '#d65745', '#5a8db5',
  '#8B5CF6', '#C026D3', '#7FA8C9', '#B8860B', '#2e8b57'];
const resid = DARK.filter(c => new RegExp(c + '(?![0-9a-fA-F])', 'i').test(html));
check(resid.length === 0, '无暗色 / 低对比色残留', resid.length ? resid.join(' ') : `检查 ${DARK.length} 种`);

// --- 3) 暗色专用效果 ---
check(!html.includes('rgba(0,0,0,.55)'), 'tooltip 深阴影已改浅');
check(!html.includes('rgba(255,255,255,.035)'), '白色 hover 高亮已改深色');
check(!/repeating-linear-gradient\([^)]*#0c1118/.test(html), '事件条暗色斜纹已改写');
check(!/linear-gradient\(180deg,#0e131b/.test(html), '顶栏暗色渐变已改写');
check(html.includes('repeating-linear-gradient(45deg,#f7f8fa'), '浅色斜纹已生效');
check(html.includes('color:#ffffff;background:var(--gold)'), 'EVENT 徽章反白文字已改');
check(html.includes(".hline{fill:none;stroke:#9A6B00") && html.includes(".hpeak{fill:#ffffff;stroke:#9A6B00"),
  '历史年均价图主线/极值圆点已改白底深金');
check(html.includes("fill:'#ffffff', size:'12'"), 'JS 条内数值标签已改白字');
check(html.includes("fill:'var(--txt)', size:'12.5'"), 'JS 负值标签已改主文字色');
// --gold-dim 是浅金，只能做 border / 渐变；不得再作为文字色或 SVG fill
check(!/(^|[;{])color:var\(--gold-dim\)/.test(html), '浅金未用于文字色');
check(!html.includes("fill:'var(--gold-dim)'"), '浅金未用于图表标签');
check(html.includes("fill:'var(--gold-2)'"), '储备轴标签已改深金');

// --- 4) 数据块 / 结构 ---
for (const mk of ['/*GOLD_DATA_START*/', '/*GOLD_DATA_END*/',
                  '/*GOLD_PANEL_DATA_START*/', '/*GOLD_PANEL_DATA_END*/']) {
  check(html.includes(mk), `数据标记 ${mk} 仍在`);
}
check(html.includes('id="evBtn"'), '交互锚点仍在（事件切换按钮）');
const opens = (html.match(/<div\b/g) || []).length;
const closes = (html.match(/<\/div>/g) || []).length;
check(opens === closes, 'div 标签平衡', `${opens} / ${closes}`);

console.log('\nRESULT:', fail === 0 ? 'LIGHT THEME OK' : `${fail} CHECK(S) FAILED`);
process.exit(fail === 0 ? 0 : 1);
