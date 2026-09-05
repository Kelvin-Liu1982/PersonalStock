const { JSDOM, VirtualConsole } = require('jsdom');
const path = require('path');
const fs = require('fs');
const WS = '/Users/sto1/WorkBuddy/业绩追踪看板';
const DASH = {
  coal: 'china-coal/china-coal-dashboard.html',
  mobile: 'china-mobile/china-mobile-dashboard.html',
  telecom: 'china-telecom/china-telecom-dashboard.html',
};

async function check(name, rel) {
  const file = path.join(WS, rel);
  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push('jsdomError: ' + (e && (e.detail ? e.detail.message || e.detail : e.message))));
  let html = fs.readFileSync(file, 'utf8');
  // 内联 common/charts.js，避免 jsdom 去 fetch 外部 file:// 资源导致挂起
  const chartsJs = fs.readFileSync(path.join(WS, 'common/charts.js'), 'utf8');
  html = html.replace('<script src="../common/charts.js"></script>', '<script>' + chartsJs + '</script>');
  // 去掉其它外部脚本（本校验不需要）
  html = html.replace(/<script src="\.\.\/quote-live\.js"[^>]*><\/script>/g, '');
  html = html.replace(/<script src="\.\.\/chart-zoom\.js"[^>]*><\/script>/g, '');
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    virtualConsole: vc,
    pretendToBeVisual: true,
  });
  await new Promise(res => setTimeout(res, 300));
  const doc = dom.window.document;
  const placeholders = [...doc.querySelectorAll('[data-img]')];
  const injected = placeholders.filter(n => n.querySelector('svg'));

  let modalOpened = false, modalHasSvg = false;
  if (name === 'coal') {
    const btn = doc.querySelector('.tbtn');
    if (btn) btn.click();
    const modal = doc.querySelector('#trendModal');
    modalOpened = !!(modal && modal.classList.contains('active'));
    const body = doc.querySelector('#trendModalBody');
    modalHasSvg = !!(body && body.querySelector('svg'));
  } else {
    const btn = doc.querySelector('.trend-btn[data-svg]');
    if (btn) btn.click();
    const modal = doc.querySelector('#trendModal');
    modalOpened = !!(modal && modal.classList.contains('open'));
    const body = doc.querySelector('#trendModal .trend-body');
    modalHasSvg = !!(body && body.querySelector('svg'));
  }
  console.log(`[${name}] placeholders=${placeholders.length} injected=${injected.length} modalOpened=${modalOpened} modalHasSvg=${modalHasSvg} errors=${errors.length}`);
  if (errors.length) console.log(errors.join('\n'));
  const ok = injected.length === placeholders.length && modalOpened && modalHasSvg && errors.length === 0;
  dom.window.close();
  return ok;
}

(async () => {
  setTimeout(() => { console.log('\nHARD TIMEOUT'); process.exit(2); }, 25000).unref();
  const only = process.argv[2];
  const items = only ? [[only, DASH[only]]] : Object.entries(DASH);
  let allOk = true;
  for (const [n, r] of items) {
    const ok = await check(n, r);
    if (!ok) allOk = false;
  }
  console.log(allOk ? '\nOK ✅' : '\nFAIL ❌');
  process.exit(allOk ? 0 : 1);
})();
