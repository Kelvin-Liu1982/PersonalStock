#!/usr/bin/env node
/**
 * 校验「未来展望」页 renderOutlook() 的分组结构（IEA / OPEC / EIA / 原油价格预测 四组）。
 *
 * 为什么单独校验：outlook 的 DOM 是运行时拼的，静态 HTML 里看不到，而「原油价格预测」
 * 组（outlook7 IMF + outlook8 EIA 一行两图）正好踩在布局风险上（grid1 还是 grid2、
 * 卡 id 是否挂对、dispose 列表是否漏、任一家缺数据时是否只渲染存在的那张）。
 * 沿用 DOM stub 套路：截出 renderOutlook，用 new Function 注入它的全部自由标识符后实跑，
 * 再对 el.innerHTML 与渲染调用情况断言。
 *
 * 运行：node tools/verify_outlook_groups.js
 */
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const SRC = path.join(ROOT, "src", "pipeline", "templates", "dashboard.js");
const src = fs.readFileSync(SRC, "utf8");

// ---- 1) 截出 renderOutlook ----
const start = src.indexOf("function renderOutlook()");
if (start < 0) { console.error("FAIL: 未找到 renderOutlook"); process.exit(1); }
let i = src.indexOf("{", start), depth = 0, end = -1;
for (let j = i; j < src.length; j++) {
  if (src[j] === "{") depth++;
  else if (src[j] === "}") { depth--; if (depth === 0) { end = j + 1; break; } }
}
const code = src.slice(start, end);

// ---- 2) 合并 data/dataset/*.json 当 STATE / SNAPSHOT ----
const DIR = path.join(ROOT, "data", "dataset");
const DATA = {};
fs.readdirSync(DIR).filter(f => f.endsWith(".json")).sort().forEach(f => {
  Object.assign(DATA, JSON.parse(fs.readFileSync(path.join(DIR, f), "utf8")));
});

// ---- 3) stub ----
const mkEl = () => ({ innerHTML: "", style: {}, addEventListener() {} });
const $ = (id) => els[id] || (els[id] = mkEl());
const els = {};
const ecCharts = {};
const called = [];
const echarts = { init: () => ({ setOption: () => {}, dispose: () => {} }) };
const fmtX = (v) => String(v).slice(2).replace("-", "/");
const noop = function (name) {
  return function () { called.push(name); };
};

const NAMES = ["STATE", "SNAPSHOT", "$", "ecCharts", "window", "echarts", "fmtX",
  "renderOutlookChart1", "renderOutlookChart2", "renderOutlookChart3",
  "renderOutlookChart4", "renderOutlookChart5", "renderOutlookChart6", "renderOutlookChart7",
  "renderOutlookChart8"];
const ARGS = [DATA, DATA, $, ecCharts, { echarts }, echarts, fmtX,
  noop("c1"), noop("c2"), noop("c3"), noop("c4"), noop("c5"), noop("c6"), noop("c7"),
  noop("c8")];

const renderOutlook = new Function(...NAMES, code + "; return renderOutlook;")(...ARGS);

// ---- 4) 实跑 ----
renderOutlook();
const html = els["p_outlook"].innerHTML;

// ---- 5) 断言 ----
const results = [];
const t = (name, ok, extra) => results.push([name, !!ok, extra === undefined ? "" : String(extra)]);

t("el 写入了内容（非 note 占位）", html.length > 500 && html.indexOf("class='note'") < 0, html.length);
t("四组标题条齐全",
  ["IEA 预测体系", "OPEC 预测体系", "EIA 预测体系", "原油价格预测"].every(s => html.indexOf(s) >= 0));
t("「原油价格预测」组排在 EIA 组之后",
  html.indexOf("EIA 预测体系") < html.indexOf("原油价格预测"));
t("旧的「IMF 预测体系」组名已移除", html.indexOf("IMF 预测体系") < 0);
t("IMF 卡片标题", html.indexOf("IMF 油价基准预测（逐期 WEO 修正）") >= 0);
t("EIA 油价卡片标题", html.indexOf("EIA 油价基准预测（逐月 STEO 修正）") >= 0);
t("IMF 卡片容器 = ec_outlook7", html.indexOf("id='ec_outlook7'") >= 0);
t("EIA 油价卡片容器 = ec_outlook8", html.indexOf("id='ec_outlook8'") >= 0);
t("两组油价卡同属一个 grid2（同行展示）",
  /class='grid2'>[^]*?id='ec_outlook7'[^]*?id='ec_outlook8'/.test(html));
t("四组全部用 grid2（outlook7 由 grid1 改 grid2）",
  (html.match(/class='grid2'/g) || []).length === 4,
  (html.match(/class='grid2'/g) || []).length);
t("面板内已无 grid1", html.indexOf("class='grid1'") < 0);
// 2026-10-15：IMF 油价页尾文案精简（用户需求）——口径改短写「Brent/Dubai/WTI 的简单平均值」，
// 去掉「非供需预测」从句，故断言同步改锁新文案（旧「迪拜法塔赫」长名已不在页尾）。
t("IMF 页尾带口径说明（Brent/Dubai/WTI）", html.indexOf("Brent/Dubai/WTI") >= 0);
t("IMF 页尾写明「全球假设」", html.indexOf("全球假设") >= 0);
// 2026-10-15：EIA 油价（outlook8）页尾文案精简（用户需求）——改「数据：取自 EIA《STEO》…」，
// 旧「Short-Term Energy Outlook / 各期 PDF / 季度列…」措辞已不在页尾；断言改锁新文案的
// 表名 + 行名（「Table 2. Energy Prices」「Brent Spot Average」，均不见于 outlook5 的 Table 3e 需求页尾）。
t("EIA 油价页尾带源说明（Table 2. Energy Prices / Brent Spot Average）",
  html.indexOf("Table 2. Energy Prices") >= 0 && html.indexOf("Brent Spot Average") >= 0);
t("八张图全部被调度渲染",
  ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"].every(c => called.indexOf(c) >= 0),
  called.join(","));
t("outlook1..8 容器 id 齐全",
  [1, 2, 3, 4, 5, 6, 7, 8].every(n => html.indexOf("id='ec_outlook" + n + "'") >= 0));
// IMF 油价卡右上角年份切换按钮组
t("IMF 卡含年份切换容器 imf_yr_switch", html.indexOf("id='imf_yr_switch'") >= 0);
t("年份切换按钮含 2025 与 2026 两项",
  html.indexOf("data-ed='2025'") >= 0 && html.indexOf("data-ed='2026'") >= 0);
t("默认高亮最新一辑（2026 带 on 类）",
  /id='imf_yr_switch'[^]*?data-ed='2026'[^]*?class='on'/.test(html) ||
  html.indexOf("data-ed='2026' class='on'") >= 0);

// ---- 6) 缺数据分支：任一家缺数据只渲染存在的那张，组头仍在 ----
function runWith(overrides, label) {
  const elsX = {}; const $X = (id) => elsX[id] || (elsX[id] = mkEl());
  const calledX = [];
  const noopX = function (name) { return function () { calledX.push(name); }; };
  const DX = Object.assign({}, DATA, overrides);
  const fn = new Function(...NAMES, code + "; return renderOutlook;")(
    DX, DX, $X, {}, { echarts }, echarts, fmtX,
    noopX("c1"), noopX("c2"), noopX("c3"), noopX("c4"), noopX("c5"), noopX("c6"),
    noopX("c7"), noopX("c8"),
    () => 94.84);
  let ok = true, msg = "";
  try { fn(); } catch (e) { ok = false; msg = e.message; }
  return { ok, msg, html: elsX["p_outlook"].innerHTML, called: calledX, label };
}

// IMF 油价缺数据：EIA 卡仍在、c7 不调度
const rNoImf = runWith({ imfOilEditions: [], imfOilByEdition: {} }, "no-imf");
t("IMF 油价为空时不抛异常", rNoImf.ok, rNoImf.msg);
t("IMF 油价为空时不渲染 IMF 卡", rNoImf.html.indexOf("ec_outlook7") < 0);
t("IMF 油价为空时 EIA 卡仍在", rNoImf.html.indexOf("ec_outlook8") >= 0);
t("IMF 油价为空时不调度 outlook7", rNoImf.called.indexOf("c7") < 0, rNoImf.called.join(","));
t("IMF 油价为空时仍调度 outlook8", rNoImf.called.indexOf("c8") >= 0, rNoImf.called.join(","));

// EIA 油价缺数据：IMF 卡仍在、c8 不调度
const rNoEia = runWith({ eiaSteoPriceMonths: [], eiaSteoBrent2026: [], eiaSteoBrent2027: [] }, "no-eia");
t("EIA 油价为空时不抛异常", rNoEia.ok, rNoEia.msg);
t("EIA 油价为空时不渲染 EIA 油价卡", rNoEia.html.indexOf("ec_outlook8") < 0);
t("EIA 油价为空时 IMF 卡仍在", rNoEia.html.indexOf("ec_outlook7") >= 0);
t("EIA 油价为空时不调度 outlook8", rNoEia.called.indexOf("c8") < 0, rNoEia.called.join(","));
t("EIA 油价为空时仍调度 outlook7", rNoEia.called.indexOf("c7") >= 0, rNoEia.called.join(","));

// 两家油价全缺：组头与 grid2 都不出现
const rNoPrice = runWith({
  imfOilEditions: [], imfOilByEdition: {},
  eiaSteoPriceMonths: [], eiaSteoBrent2026: [], eiaSteoBrent2027: [],
}, "no-price");
t("两家油价全缺时不抛异常", rNoPrice.ok, rNoPrice.msg);
t("两家油价全缺时无「原油价格预测」组头", rNoPrice.html.indexOf("原油价格预测") < 0);
t("两家油价全缺时前三组仍在",
  ["IEA 预测体系", "OPEC 预测体系", "EIA 预测体系"].every(s => rNoPrice.html.indexOf(s) >= 0));

let fail = 0;
results.forEach(([n, ok, extra]) => {
  if (!ok) fail++;
  console.log((ok ? "PASS " : "FAIL ") + n + (extra ? "  [" + extra + "]" : ""));
});
console.log("\n" + (results.length - fail) + "/" + results.length + " passed");
process.exit(fail ? 1 : 0);
