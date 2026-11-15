#!/usr/bin/node
/**
 * 校验「未来展望」模块 outlook7「IMF 油价基准预测（逐期 WEO 修正）」。
 *
 * 2026-10-14（续）改为**按 WEO 辑（edition）分组 + 右上角年份按钮切换**：
 * 数据层 imf_woe_oil.json 产出 editions=["2025","2026"] 与 byEdition[辑年]；
 * 渲染层 renderOutlookChart7(edKey, ed) 只渲染**单辑**视图，
 * 各辑独立成图（2025 辑 = 4 期次 / 目标年 2025+2026；2026 辑 = 4 期次 / 目标年 2026+2027）。
 * 本脚本据此断言两辑各自的数据与渲染结果，并验证「切换不同辑得到不同视图」。
 *
 * 与 tools/verify_woe_revisions.js 同一套路：本机无 playwright，改用 DOM stub。
 * 从 src/pipeline/templates/dashboard.js 按大括号配对截出 renderOutlookChart7，
 * 用 new Function 注入最小依赖后实跑，对捕获到的 setOption 断言。
 * ⚠️ 参考线 = **本辑当年实际**（按辑取 actual[edKey]，非全局最新已实年份）：
 *      2025 辑 → 2025 实际 67.74（OIL_ACTUAL 有）
 *      2026 辑 → 2026 全年实际尚未披露（2026 年未走完）→ 无参考线
 *    原「Brent 当年日均」②号线已于 2026-10-14 应需求移除。
 *
 * 运行：node tools/verify_imf_oil.js
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
const codeChart = grab("function renderOutlookChart7");

// ---- 2) 真实落库数据 ----
const imf = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "dataset", "imf_forecast.json"), "utf8"));
const prices = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "dataset", "prices.json"), "utf8"));
const STATE = {
  imfOilEditions: imf.imfOilEditions || [],
  imfOilByEdition: imf.imfOilByEdition || {},
  dates: prices.dates || [],
  brent: prices.brent || [],
};

// ---- 3) 最小 DOM / ECharts stub ----
const mkEl = () => ({ innerHTML: "", style: {} });
const els = {};
const $ = (id) => els[id] || (els[id] = mkEl());
const ecCharts = {};
let captured = null, inited = null;
const echarts = { init: (el) => { inited = el; return { setOption: (o) => { captured = o; }, dispose: () => {} }; } };
const fmtX = (v) => String(v).slice(2).replace("-", "/");

const renderOutlookChart7 = new Function("STATE", "$", "ecCharts", "window", "echarts", "fmtX",
  codeChart + "; return renderOutlookChart7;")(STATE, $, ecCharts, { echarts }, echarts, fmtX);

// ---- 4) 实跑 ----
const ed25 = (imf.imfOilByEdition || {})["2025"];
const ed26 = (imf.imfOilByEdition || {})["2026"];

// ---- 5) 断言 ----
const results = [];
const t = (name, ok, extra) => results.push([name, !!ok, extra === undefined ? "" : String(extra)]);

// ---- 数据集层 ----
t("落库：editions = [2025, 2026]", JSON.stringify(STATE.imfOilEditions) === JSON.stringify(["2025", "2026"]),
  JSON.stringify(STATE.imfOilEditions));
t("落库：byEdition 含 2025 / 2026 两辑", !!ed25 && !!ed26);
t("落库：2025 辑 4 个期次", ed25 && ed25.months.length === 4, ed25 && ed25.months.join(","));
t("落库：2026 辑 4 个期次", ed26 && ed26.months.length === 4, ed26 && ed26.months.join(","));
t("落库：2025 辑目标年 = 2025 / 2026", ed25 && JSON.stringify(Object.keys(ed25.price).sort()) === JSON.stringify(["2025", "2026"]),
  ed25 && Object.keys(ed25.price).join(","));
t("落库：2026 辑目标年 = 2026 / 2027", ed26 && JSON.stringify(Object.keys(ed26.price).sort()) === JSON.stringify(["2026", "2027"]),
  ed26 && Object.keys(ed26.price).join(","));
t("落库：2025 辑 2025 线 = 69.76/66.94/68.18/68.92",
  ed25 && JSON.stringify(ed25.price["2025"]) === JSON.stringify([69.76, 66.94, 68.18, 68.92]),
  ed25 && JSON.stringify(ed25.price["2025"]));
t("落库：2025 辑 2026 线 = 67.96/62.38/64.33/65.84",
  ed25 && JSON.stringify(ed25.price["2026"]) === JSON.stringify([67.96, 62.38, 64.33, 65.84]),
  ed25 && JSON.stringify(ed25.price["2026"]));
t("落库：2026 辑 2026 线 = 62.13/82.22/89.27/95.74",
  ed26 && JSON.stringify(ed26.price["2026"]) === JSON.stringify([62.13, 82.22, 89.27, 95.74]),
  ed26 && JSON.stringify(ed26.price["2026"]));
t("落库：2026 辑 2027 线 = 62.17/75.97/78.70/87.39",
  ed26 && JSON.stringify(ed26.price["2027"]) === JSON.stringify([62.17, 75.97, 78.70, 87.39]),
  ed26 && JSON.stringify(ed26.price["2027"]));
t("落库：2025 辑 actual = {2025: 67.74}（本辑当年实际）",
  ed25 && JSON.stringify(ed25.actual || {}) === JSON.stringify({ "2025": 67.74 }),
  ed25 && JSON.stringify(ed25.actual));
t("落库：2026 辑 actual 为空（2026 全年实际未披露，不拿年内迄今冒充）",
  ed26 && Object.keys(ed26.actual || {}).length === 0, ed26 && JSON.stringify(ed26.actual));

// ---- 渲染层：2026 辑 ----
renderOutlookChart7("2026", ed26);
let c26 = captured;
t("2026 辑：setOption 被调用", !!c26);
t("2026 辑：实例挂在 ec_outlook7", !!inited && inited === els["ec_outlook7"]);
t("2026 辑：ecCharts.outlook7 已登记", !!ecCharts.outlook7);
if (c26) {
  const s = c26.series || [];
  t("2026 辑：序列 2 条（2026 / 2027）", s.length === 2, s.length);
  t("2026 辑：线名 = 2026/2027 油价假设",
    s.map(x => x.name).join("|") === "2026 油价假设|2027 油价假设", s.map(x => x.name).join("|"));
  const s26 = s.filter(x => x.name === "2026 油价假设")[0];
  const s27 = s.filter(x => x.name === "2027 油价假设")[0];
  t("2026 辑：2026 线数据 = 62.13/82.22/89.27/95.74", JSON.stringify(s26.data) === JSON.stringify([62.13, 82.22, 89.27, 95.74]), JSON.stringify(s26.data));
  t("2026 辑：2027 线数据 = 62.17/75.97/78.70/87.39", JSON.stringify(s27.data) === JSON.stringify([62.17, 75.97, 78.70, 87.39]), JSON.stringify(s27.data));
  t("2026 辑：x 轴 = 4 个期次", JSON.stringify(c26.xAxis.data) === JSON.stringify(ed26.months), JSON.stringify(c26.xAxis.data));
  t("2026 辑：y 轴单位 = 美元/桶", c26.yAxis.name === "美元/桶", c26.yAxis.name);
  t("2026 辑：y 轴上界 >= 最高值 95.74", c26.yAxis.max >= 95.74, c26.yAxis.max);
  // 参考线 = 本辑当年实际。2026 年未走完 → OIL_ACTUAL 无 2026 全年实际 → 不画线
  const ml = (s[0].markLine && s[0].markLine.data) || [];
  t("2026 辑：无参考线（2026 全年实际未披露）", ml.length === 0, ml.length);
  t("2026 辑：不再画 2025 实际（已改为按辑取当年）",
    !ml.some(d => String(d.label && d.label.formatter).indexOf("2025 实际") >= 0));
  t("2026 辑：无跨辑边界竖线（无 xAxis 标注）", !ml.some(d => "xAxis" in d));
  t("2026 辑：已移除 Brent 当年日均参考线", !ml.some(d => String(d.label && d.label.formatter).indexOf("看板实测") >= 0));
  // tooltip 回调实跑
  const fmt = c26.tooltip.formatter;
  let out = "";
  try {
    out = fmt([
      { name: "2026-10", value: 95.74, seriesIndex: 0, dataIndex: 3, marker: "*", seriesName: "2026 油价假设" },
      { name: "2026-10", value: 87.39, seriesIndex: 1, dataIndex: 3, marker: "*", seriesName: "2027 油价假设" },
    ]);
  } catch (e) { out = "THROW:" + e.message; }
  t("2026 辑：tooltip 含末点值 95.74", out.indexOf("THROW:") !== 0 && out.indexOf("95.74") >= 0, out);
  t("2026 辑：tooltip 含「较上期 +6.47」", out.indexOf("+6.47") >= 0, out);
  t("2026 辑：tooltip 单位 = $…/桶", out.indexOf("/桶") >= 0);
  // endLabel 回调
  let el = "";
  try { el = s26.endLabel.formatter({ value: 95.74 }); } catch (e) { el = "THROW:" + e.message; }
  t("2026 辑：endLabel 输出 95.7", el === "95.7", el);
}

// ---- 渲染层：2025 辑（验证切换得到不同视图）----
renderOutlookChart7("2025", ed25);
let c25 = captured;
t("2025 辑：setOption 再次被调用（切换生效）", !!c25);
if (c25) {
  const s = c25.series || [];
  t("2025 辑：序列 2 条（2025 / 2026）", s.length === 2, s.length);
  t("2025 辑：x 轴 = 4 个期次（2025 辑）", JSON.stringify(c25.xAxis.data) === JSON.stringify(ed25.months), JSON.stringify(c25.xAxis.data));
  const s25 = s.filter(x => x.name === "2025 油价假设")[0];
  const s26 = s.filter(x => x.name === "2026 油价假设")[0];
  t("2025 辑：2025 线数据 = 69.76/66.94/68.18/68.92", JSON.stringify(s25.data) === JSON.stringify([69.76, 66.94, 68.18, 68.92]), JSON.stringify(s25.data));
  t("2025 辑：2026 线数据 = 67.96/62.38/64.33/65.84", JSON.stringify(s26.data) === JSON.stringify([67.96, 62.38, 64.33, 65.84]), JSON.stringify(s26.data));
  // 关键：两辑视图确实不同（x 轴期次集不同、2026 线数值不同）
  t("切换验证：2025 辑与 2026 辑 x 轴不同", JSON.stringify(c25.xAxis.data) !== JSON.stringify(c26.xAxis.data));
  t("切换验证：2025 辑 2026 线 ≠ 2026 辑 2026 线", JSON.stringify(s26.data) !== JSON.stringify(c26.series.filter(x => x.name === "2026 油价假设")[0].data));
  // 参考线按辑取当年：2025 辑应画出 2025 实际 67.74
  const ml25 = ((s[0].markLine && s[0].markLine.data) || []);
  t("2025 辑：参考线 1 条 = 本辑当年（2025）实际 67.74",
    ml25.length === 1 && typeof ml25[0].yAxis === "number" && Math.abs(ml25[0].yAxis - 67.74) < 1e-9,
    JSON.stringify(ml25.map(d => d.yAxis)));
  t("2025 辑：参考线文案含「2025 实际」",
    ml25.some(d => String(d.label && d.label.formatter).indexOf("2025 实际") >= 0));
}

// ---- 6) 空数据兜底：不能抛异常、应写入 note ----
const $2 = (id) => els[id] || (els[id] = mkEl());
const ecCharts2 = {};
const fn2 = new Function("STATE", "$", "ecCharts", "window", "echarts", "fmtX",
  codeChart + "; return renderOutlookChart7;")(STATE, $2, ecCharts2, { echarts }, echarts, fmtX);
let emptyOk = true, emptyMsg = "";
try { fn2("2025", {}, null); } catch (e) { emptyOk = false; emptyMsg = e.message; }
t("空数据不抛异常", emptyOk, emptyMsg);
t("空数据写入 note 占位", $2("ec_outlook7").innerHTML.indexOf("note") >= 0, $2("ec_outlook7").innerHTML);

// ---- 输出 ----
let fail = 0;
results.forEach(([n, ok, extra]) => {
  if (!ok) fail++;
  console.log((ok ? "PASS " : "FAIL ") + n + (extra ? "  [" + extra + "]" : ""));
});
console.log("\n" + (results.length - fail) + "/" + results.length + " passed");
process.exit(fail ? 1 : 0);
