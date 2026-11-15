/* EIA 周度序列「四处必须一致」的防回归校验（纯 node，不依赖浏览器）。
   用法（oil-analysis 目录下）：
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/check_eia_series.js
   【背景 / 2026-10-07 故障】
   SPR 图「首屏正常、开页自动拉取实时后整张图空白」的根因是：**序列 id 表抄了两份**。
   python `src/fetch/supply/eia_weekly.py::EIA_SERIES` 是事实源，前端 `dashboard.js::fetchEIA`
   却手抄了第二份 id 表；那天给 python 加了 `spr`、前端漏了，于是「拉取实时」后
   STATE.eia.spr 不存在 → eiaAxis() 回退 null → __default__ 用空数组当数据集 → 空白画布。
   现在前端改为读构建注入的 EIA_SERIES，但「四处不一致」仍可能从别的地方发生，
   所以固化成本脚本，改动序列后必跑。

   校四处：
     1) python EIA_SERIES（抓取/快照的事实源）
     2) 构建产物注入的 EIA_SERIES 常量（前端 fetchEIA 用的那份）
     3) 看板图配置里实际引用到的 `eia.*` key（漏了就是「声明了但图上不更新」）
     4) 快照数据本身（STATE.eia / STATE.eiaWeekly 里得真有值）

   另：MILLION_UNITS（千桶→百万桶换算名单）与前端 EIA_SERIES.million 也必须一致，
   否则实时取值与离线快照差 1000 倍。
*/
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const PY = read('src/fetch/supply/eia_weekly.py');
const HTML = read('output/crude_oil_dashboard.html');
const JS = read('src/pipeline/templates/dashboard.js');

/* ---- 1) 解析 python 的 EIA_SERIES / MILLION_UNITS / DERIVED ----
   python 源里是 `    "cushing": "PET.W_EPC0_SAX_YCUOK_MBBL.W",   # 注释`，逐行取引号内容。
   ⚠️ id 字符集要含下划线：库欣序列 PET.W_EPC0_SAX_YCUOK_MBBL.W 就是这么写的，
   早先用 [A-Z0-9.]+ 会把库欣这个 key 直接漏掉（静默通过 = 最糟的失败方式）。 */
const pyIds = {};
for (const m of PY.matchAll(/^\s*"([A-Za-z_]\w*)"\s*:\s*"([A-Za-z0-9_.\-]+)"\s*,/gm)) {
  pyIds[m[1]] = m[2];
}
const pyMillionBlock = (PY.match(/MILLION_UNITS\s*=\s*\(([^)]*)\)/) || [, ''])[1];
const pyMillion = [...pyMillionBlock.matchAll(/"([A-Za-z_]\w*)"/g)].map((m) => m[1]);
const pyDerivedBlock = (PY.match(/DERIVED\s*=\s*\(([^)]*)\)/) || [, ''])[1];
const pyDerived = [...pyDerivedBlock.matchAll(/"([A-Za-z_]\w*)"/g)].map((m) => m[1]);

/* ---- 2) 构建产物里注入的常量 ----
   产物里长这样：const EIA_SERIES = {"ids":{"cushing":"PET.WCESTUS1.W",...},"million":[...]}; */
const injM = HTML.match(/const EIA_SERIES\s*=\s*(\{[\s\S]*?\n?\});/);
let inj = null;
if (injM) { try { inj = JSON.parse(injM[1]); } catch (e) { /* 下面统一报错 */ } }

/* ---- 3) 图配置里引用到的 eia.* key ----
   形如 {id:"usspr",title:"...",key:"eia.spr",...} 或 cfg.main.key / cfg.third.key 等 */
const usedKeys = new Set();
for (const m of JS.matchAll(/key\s*:\s*"(eia\.[A-Za-z_]\w*)"/g)) usedKeys.add(m[1]);
for (const m of HTML.matchAll(/key\s*:\s*"(eia\.[A-Za-z_]\w*)"/g)) usedKeys.add(m[1]);

/* ---- 4) 快照数据 ----
   快照是嵌入 HTML 的 const SNAPSHOT = {...}; 其余路径都走 window STATE，这里只校验结构 */
const snapM = HTML.match(/const SNAPSHOT\s*=\s*(\{[\s\S]*?\});/);
let snap = null;
if (snapM) { try { snap = JSON.parse(snapM[1]); } catch (e) { /* 下面统一报错 */ } }

const errs = [];
const push = (ok, msg) => { console.log((ok ? 'OK   ' : 'FAIL ') + msg); if (!ok) errs.push(msg); };

console.log('python EIA_SERIES =', JSON.stringify(pyIds));
console.log('python MILLION_UNITS =', JSON.stringify(pyMillion));
console.log('');

/* 1) 注入常量存在且完整 */
if (!inj) {
  push(false, '构建产物里找不到注入的 `const EIA_SERIES = {...}`（产物过期或 build 失败），请先 `python -m src.pipeline.build_html`');
} else if (JSON.stringify(inj.ids) !== JSON.stringify(pyIds)) {
  const a = Object.keys(inj.ids), b = Object.keys(pyIds);
  const diff = b.filter((k) => !a.includes(k)).map((k) => 'python 有前端无:' + k)
    .concat(a.filter((k) => !b.includes(k)).map((k) => '前端有 python 无:' + k))
    .concat(a.filter((k) => pyIds[k] !== inj.ids[k]).map((k) => 'id 不一致:' + k));
  push(false, '构建注入的 id 表与 python EIA_SERIES 不一致 → ' + diff.join('; '));
} else {
  push(true, `构建注入的 id 表 == python EIA_SERIES（${Object.keys(inj.ids).length} 个序列：${Object.keys(inj.ids).join(', ')}）`);
}

/* 2) 千桶换算名单一致（防实时/离线差 1000 倍） */
if (inj) {
  const sameMillion = JSON.stringify([...inj.million].sort()) === JSON.stringify([...pyMillion].sort());
  push(sameMillion, `MILLION_UNITS == EIA_SERIES.million（${pyMillion.join(',')}）` +
    (sameMillion ? '' : ` → 注入值 [${(inj.million || []).join(',')}]`));
}

/* 3) 图上引用到的 eia.* key 都在 id 表里 */
const usedNames = [...usedKeys].map((k) => k.split('.')[1]);
const unknown = usedNames.filter((n) => !pyIds[n]);
if (!usedNames.length) {
  push(false, '没解析到任何 `key:"eia.*"` 引用（模板格式变了？请检查本脚本的正则）');
} else {
  push(unknown.length === 0, `看板引用 ${usedNames.length} 个 eia.* 序列且全部已声明` +
    (unknown.length ? ' → 缺失: ' + unknown.join(',') : '：' + [...new Set(usedNames)].sort().join(', ')));
}

/* 4) 快照里每个序列都有日度 + 周度值 */
if (!snap) {
  push(false, '构建产物里找不到 `const SNAPSHOT = {...}`（产物过期）');
} else {
  const names = [...new Set(usedNames)];
  const badDaily = [], badWeekly = [], emptyVal = [];
  names.forEach((n) => {
    if (!(snap.eia && Array.isArray(snap.eia[n]))) badDaily.push(n);
    if (!(snap.eiaWeekly && snap.eiaWeekly[n] && Array.isArray(snap.eiaWeekly[n]))) badWeekly.push(n);
    const v = snap.eiaWeekly && snap.eiaWeekly[n];
    if (v && !v.some((x) => x != null)) emptyVal.push(n);
  });
  push(badDaily.length === 0, `快照 STATE.eia.* 全齐全（日度对齐）` + (badDaily.length ? ' → 缺: ' + badDaily.join(',') : ''));
  push(badWeekly.length === 0, `快照 STATE.eiaWeekly.* 全齐全（原生周度）` + (badWeekly.length ? ' → 缺: ' + badWeekly.join(',') : ''));
  push(emptyVal.length === 0, `周度序列都有非空点` + (emptyVal.length ? ' → 全空: ' + emptyVal.join(',') : ''));

  /* 5) 派生序列（gross 等）：不在 ids 里，但快照与实时态都必须有 */
  const missDerived = pyDerived.filter((d) => !(snap.eia && Array.isArray(snap.eia[d])));
  push(pyDerived.length > 0 && missDerived.length === 0,
    `派生序列齐全（${pyDerived.join(',')}：无独立 seriesid，由已抓序列恒等算出）`
    + (missDerived.length ? ' → 缺: ' + missDerived.join(',') : ''));

  /* 6) 口径量级守卫 —— 2026-10-07 那次「标题与序列对反」的回归防线。
        库欣 ≈ 22–30、全美商业 ≈ 425–430、SPR ≈ 280–410（百万桶）。
        三者量级差一个数量级，一旦哪个序列取串了，这里立刻 FAIL。 */
  const last = (a) => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };
  const band = (name, lo, hi) => {
    const v = last(snap.eiaWeekly && snap.eiaWeekly[name] || []);
    push(v != null && v >= lo && v <= hi,
      `${name} 末值量级合理（应 ${lo}–${hi}）→ 实测 ${v == null ? 'null' : v}`);
  };
  band('cushing', 10, 60);
  band('total', 350, 520);
  band('spr', 200, 500);
  const g = last(snap.eiaWeekly && snap.eiaWeekly.gross || []);
  const t = last(snap.eiaWeekly && snap.eiaWeekly.total || []);
  const s = last(snap.eiaWeekly && snap.eiaWeekly.spr || []);
  push(g != null && t != null && s != null && Math.abs(g - (t + s)) < 0.05,
    `gross == total + spr（恒等自校验）→ ${g} vs ${t} + ${s}`);

  const asOf = (snap.eiaDates || []).slice(-1)[0];
  console.log('\n周度轴末点 = ' + asOf + '（图中徽章「截至」应与之相同）');

  /* 7) 日度油价（2026-10-08 换源新增）：EIA_PRICE_IDS 注入必须与 python 一致 */
  const PYPRICE = read('src/fetch/prices.py');
  const grab = (src, name) => {
    const m = src.match(new RegExp(name + '\\s*=\\s*\\{([\\s\\S]*?)\\}'));
    const o = {};
    if (m) for (const x of m[1].matchAll(/^\s*"([A-Za-z_]\w*)"\s*:\s*"([A-Za-z0-9_.\-]+)"\s*,/gm)) o[x[1]] = x[2];
    return o;
  };
  const pyPriceIds = grab(PYPRICE, 'EIA_PRICE_SERIES');
  const pyPriceFb = grab(PYPRICE, 'FRED_PRICE_FALLBACK');
  const injPriceM = HTML.match(/const EIA_PRICE_IDS\s*=\s*(\{[\s\S]*?\});/);
  let injPrice = null;
  if (injPriceM) { try { injPrice = JSON.parse(injPriceM[1]); } catch (e) { /* 下面统一报错 */ } }

  if (!injPrice) {
    push(false, '构建产物里找不到注入的 `const EIA_PRICE_IDS = {...}`（产物过期？先 `python run.py html`）');
  } else {
    const okIds = Object.keys(pyPriceIds).length > 0 &&
      JSON.stringify(injPrice.ids) === JSON.stringify(pyPriceIds);
    push(okIds, `EIA_PRICE_IDS.ids == python prices.EIA_PRICE_SERIES（${JSON.stringify(pyPriceIds)}）`
      + (okIds ? '' : ` → 注入值 ${JSON.stringify(injPrice.ids)}`));
    const okFb = JSON.stringify(injPrice.fallback) === JSON.stringify(pyPriceFb);
    push(okFb, `EIA_PRICE_IDS.fallback == python prices.FRED_PRICE_FALLBACK（${JSON.stringify(pyPriceFb)}）`
      + (okFb ? '' : ` → 注入值 ${JSON.stringify(injPrice.fallback)}`));
  }

  /* 8) 反向守卫 —— 坑 1 的回归防线：周度表绝不能出现日度油价。
     fetchEIA() 用 EIA_SERIES.ids 的 period 并集生成「周轴」，一旦 brent/wti
     （日度）混进那张表，周轴会从约 2296 个周点膨胀到几千个日点，周度图 x 轴整片塌掉。
     日度油价只允许出现在 EIA_PRICE_IDS 里。 */
  const PRICE_KEYS = ['brent', 'wti'];
  const leakedPy = PRICE_KEYS.filter((k) => Object.prototype.hasOwnProperty.call(pyIds, k));
  const leakedInj = PRICE_KEYS.filter((k) => inj && inj.ids && Object.prototype.hasOwnProperty.call(inj.ids, k));
  push(leakedPy.length === 0 && leakedInj.length === 0,
    '周度 EIA_SERIES 不含 brent/wti（日度油价只走 EIA_PRICE_IDS，防周轴被日点撑爆）'
    + (leakedPy.length || leakedInj.length ? ` → 泄漏: python[${leakedPy}] / 注入[${leakedInj}]` : ''));

  /* 9) 日度价量级守卫（换源不换值，但仍防取串序列 / 单位错） */
  const lastBrent = last(snap.brent || []);
  push(lastBrent != null && lastBrent > 10 && lastBrent < 300,
    `快照 brent 末值量级合理（10–300 美元/桶）→ 实测 ${lastBrent}`);
  const lastWti = last(snap.wti || []);
  push(lastWti != null && lastWti > 10 && lastWti < 300,
    `快照 wti 末值量级合理（10–300 美元/桶）→ 实测 ${lastWti}`);
  const asOfPrice = (snap.dates || []).slice(-1)[0];
  console.log('日度轴末点 = ' + asOfPrice
    + '（换源后应接近构建当天；落后约 1 周说明走的是 FRED 回落分支）');
}

console.log('\n' + (errs.length ? `FAILED: ${errs.length} 项不一致\n` + errs.map((e) => ' - ' + e).join('\n') : 'ALL OK — EIA 序列四处口径一致'));
process.exit(errs.length ? 1 : 0);
