#!/usr/bin/node
/**
 * 校验「未来展望」模块 outlook8「EIA 油价基准预测（逐月 STEO 修正）」。
 *
 * 2026-10-15 两条应需求改动，本脚本锁住这两条（防回归）：
 *   ① 参考线改为与 outlook7 **同一逻辑**——按「当年（2026）」取实际，不再用「上年实际」作锚。
 *      2026 年未走完 → 官方全年 Brent 实际未披露 → **无参考线**（原「2025 实际 69.04」已移除）。
 *      ⚠️ 尤其要锁住：不得回退到「取 actual 里最大年份」，否则 2025 线会复活。
 *   ② 2026 / 2027 **两条都是实线**，且与 outlook7 的 2026 辑**同色**：
 *      2026 = #dc2626（红）、2027 = #2563eb（蓝）。
 *
 * 与 tools/verify_imf_oil.js 同一套路：本机无 playwright，改用 DOM stub。
 * 从 src/pipeline/templates/dashboard.js 按大括号配对截出 renderOutlookChart8，
 * 用 new Function 注入最小依赖后实跑，对捕获到的 setOption 断言。
 *
 * 运行：node tools/verify_eia_oil.js
 */
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const SRC = path.join(ROOT, "src", "pipeline", "templates", "dashboard.js");
const src = fs.readFileSync(SRC, "utf8");

// ---- 1) 按大括号配对截出函数 ----
function grab(sig) {
  const start = src.indexOf(sig);
  if (start < 0) { console.error("FAIL: 未找到 " + sig); process.exit(1); }
  let i = src.indexOf("{", start), depth = 0, end = -1;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}") { depth--; if (depth === 0) { end = j + 1; break; } }
  }
  if (end < 0) { console.error("FAIL: " + sig + " 大括号未配对"); process.exit(1); }
  return src.slice(start, end);
}
const codeChart = grab("function renderOutlookChart8");

// ---- 2) 真实落库数据 ----
const eia = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "dataset", "eia_forecast.json"), "utf8"));
const months = eia.eiaSteoPriceMonths || [];
const p26 = eia.eiaSteoBrent2026 || [];
const p27 = eia.eiaSteoBrent2027 || [];
const actual = eia.eiaSteoBrentActual2025 || {};

// ---- 3) 最小 DOM / ECharts stub ----
const mkEl = () => ({ innerHTML: "", style: {} });
const els = {};
const $ = (id) => els[id] || (els[id] = mkEl());
const ecCharts = {};
let captured = null, inited = null;
const echarts = { init: (el) => { inited = el; return { setOption: (o) => { captured = o; }, dispose: () => {} }; } };
const fmtX = (v) => String(v).slice(2).replace("-", "/");

const renderOutlookChart8 = new Function("$", "ecCharts", "window", "echarts", "fmtX",
  codeChart + "; return renderOutlookChart8;")($, ecCharts, { echarts }, echarts, fmtX);

// ---- 4) 实跑 ----
renderOutlookChart8(months, p26, p27, actual);
const c = captured;

// ---- 5) 断言 ----
const results = [];
const t = (name, ok, extra) => results.push([name, !!ok, extra === undefined ? "" : String(extra)]);

// ---- 数据层 ----
t("落库：期次轴 10 期（月度）", months.length === 10, months.length);
t("落库：2026 线 10 个值", p26.length === 10, p26.length);
t("落库：2027 线 10 个值", p27.length === 10, p27.length);
t("落库：2026 末值 = 96.32", p26[p26.length - 1] === 96.32, p26[p26.length - 1]);
t("落库：2027 末值 = 83.74", p27[p27.length - 1] === 83.74, p27[p27.length - 1]);
t("落库：actual 只有 2025（尚无 2026 全年实际）",
  JSON.stringify(Object.keys(actual)) === JSON.stringify(["2025"]), JSON.stringify(Object.keys(actual)));

// ---- 渲染层 ----
t("setOption 被调用", !!c);
t("实例挂在 ec_outlook8", !!inited && inited === els["ec_outlook8"]);
t("ecCharts.outlook8 已登记", !!ecCharts.outlook8);
if (c) {
  const s = c.series || [];
  t("序列 2 条（2026 / 2027）", s.length === 2, s.length);
  const s26 = s.filter(x => x.name === "2026 油价预测")[0];
  const s27 = s.filter(x => x.name === "2027 油价预测")[0];
  t("线名 = 2026/2027 油价预测", !!s26 && !!s27, s.map(x => x.name).join("|"));
  t("2026 线数据 = 落库 p26", JSON.stringify(s26.data) === JSON.stringify(p26));
  t("2027 线数据 = 落库 p27", JSON.stringify(s27.data) === JSON.stringify(p27));

  // ★ 线型：两条都必须是实线（solid），不得有虚线
  t("2026 线为实线", s26.lineStyle.type === "solid", s26.lineStyle.type);
  t("2027 线为实线", s27.lineStyle.type === "solid", s27.lineStyle.type);
  t("两条线均无虚线（dashed）",
    s.every(x => x.lineStyle.type !== "dashed"), s.map(x => x.lineStyle.type).join("|"));

  // ★ 配色：与 outlook7 的 2026 辑一致（2026 红 #dc2626 / 2027 蓝 #2563eb）
  t("2026 线色 = #dc2626（对齐 outlook7 2026 辑）",
    s26.lineStyle.color === "#dc2626", s26.lineStyle.color);
  t("2027 线色 = #2563eb（对齐 outlook7 2026 辑）",
    s27.lineStyle.color === "#2563eb", s27.lineStyle.color);
  t("2026 线 itemStyle 色同步", s26.itemStyle.color === "#dc2626", s26.itemStyle.color);
  t("2027 线 itemStyle 色同步", s27.itemStyle.color === "#2563eb", s27.itemStyle.color);
  t("2026 末值标签色同步", s26.endLabel.color === "#dc2626", s26.endLabel.color);
  t("2027 末值标签色同步", s27.endLabel.color === "#2563eb", s27.endLabel.color);
  t("不再使用旧 EIA 身份色（#d97706 / #0891b2）",
    s.every(x => x.lineStyle.color !== "#d97706" && x.lineStyle.color !== "#0891b2"),
    s.map(x => x.lineStyle.color).join("|"));

  // ★ 参考线：当年（2026）实际未披露 → 无参考线；且不得复活 2025 实际
  const ml = (s[0].markLine && s[0].markLine.data) || [];
  t("无参考线（2026 全年实际未披露）", ml.length === 0, JSON.stringify(ml.map(d => d.yAxis)));
  t("不再画「2025 实际」（已改为按当年取）",
    !ml.some(d => String(d.label && d.label.formatter).indexOf("2025 实际") >= 0));
  t("不再画「看板实测 Brent 当年日均」",
    !ml.some(d => String(d.label && d.label.formatter).indexOf("看板实测") >= 0));
  t("无 xAxis 竖线标注", !ml.some(d => "xAxis" in d));

  // y 轴仍覆盖全部预测值（移除参考线不应把轴压坏）
  t("y 轴上界 >= 2026 峰值 96.32", c.yAxis.max >= 96.32, c.yAxis.max);
  t("y 轴下界 <= 2027 谷值 53.00", c.yAxis.min <= 53.00, c.yAxis.min);
  t("y 轴单位 = 美元/桶", c.yAxis.name === "美元/桶", c.yAxis.name);
  t("x 轴 = 10 个月度期次", JSON.stringify(c.xAxis.data) === JSON.stringify(months));
  t("图例 = 2026/2027 油价预测",
    JSON.stringify(c.legend.data) === JSON.stringify(["2026 油价预测", "2027 油价预测"]),
    JSON.stringify(c.legend.data));

  // endLabel 回调
  let el26 = "";
  try { el26 = s26.endLabel.formatter({ value: 96.32 }); } catch (e) { el26 = "THROW:" + e.message; }
  t("endLabel 输出 96.3", el26 === "96.3", el26);
}

// ---- 6) 前置兼容性：一旦 2026 实际披露，参考线应自动出现 ----
const els2 = {};
const $2 = (id) => els2[id] || (els2[id] = mkEl());
const ecCharts2 = {};
let cap2 = null;
const echarts2 = { init: () => ({ setOption: (o) => { cap2 = o; }, dispose: () => {} }) };
const fn2 = new Function("$", "ecCharts", "window", "echarts", "fmtX",
  codeChart + "; return renderOutlookChart8;")($2, ecCharts2, { echarts: echarts2 }, echarts2, fmtX);
fn2(months, p26, p27, { "2025": 69.04, "2026": 88.10 });
const ml2 = (((cap2 || {}).series || [{}])[0].markLine || {}).data || [];
t("前置兼容：actual 含 2026 时画出 2026 实际参考线",
  ml2.length === 1 && Math.abs(ml2[0].yAxis - 88.10) < 1e-9, JSON.stringify(ml2.map(d => d.yAxis)));
t("前置兼容：该线文案含「2026 实际」",
  ml2.some(d => String(d.label && d.label.formatter).indexOf("2026 实际") >= 0));

// ---- 7) 空数据兜底 ----
const els3 = {};
const $3 = (id) => els3[id] || (els3[id] = mkEl());
const fn3 = new Function("$", "ecCharts", "window", "echarts", "fmtX",
  codeChart + "; return renderOutlookChart8;")($3, {}, { echarts }, echarts, fmtX);
let ok3 = true, msg3 = "";
try { fn3([], [], [], {}); } catch (e) { ok3 = false; msg3 = e.message; }
t("空数据不抛异常", ok3, msg3);
t("空数据写入 note 占位", $3("ec_outlook8").innerHTML.indexOf("note") >= 0, $3("ec_outlook8").innerHTML);

// ---- 输出 ----
let fail = 0;
results.forEach(([n, ok, extra]) => {
  if (!ok) fail++;
  console.log((ok ? "PASS " : "FAIL ") + n + (extra ? "  [" + extra + "]" : ""));
});
console.log("\n" + (results.length - fail) + "/" + results.length + " passed");
process.exit(fail ? 1 : 0);
