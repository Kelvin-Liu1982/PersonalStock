#!/usr/bin/env node
/**
 * 校验「IMF《WEO》全球 GDP 增速预测（逐期修正）」图的 ECharts 配置构建。
 *
 * 为什么用 DOM stub 而不是 playwright：本机未装 playwright（tools/verify_*.js 那一套跑不起来），
 * 而本图的关键风险都在「配置是否构建得出来」——选项拼错、字段取错、tooltip 回调抛异常，
 * 这些都能在 stub 里暴露，不需要真实浏览器。
 *
 * 做法：从 src/pipeline/templates/dashboard.js 里按大括号配对截出 renderWoeRevisions，
 * 用 new Function 注入最小依赖（STATE / $ / ecCharts / window.echarts / fmtX）后实跑，
 * 再对捕获到的 setOption 断言。数据直接读 data/dataset/macro.json（真实落库值）。
 *
 * 运行：node tools/verify_woe_revisions.js
 */
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const SRC = path.join(ROOT, "src", "pipeline", "templates", "dashboard.js");
const src = fs.readFileSync(SRC, "utf8");

// ---- 1) 截出 renderWoeRevisions 函数体（大括号配对，避免正则截断嵌套） ----
const start = src.indexOf("function renderWoeRevisions");
if (start < 0) { console.error("FAIL: 未找到 renderWoeRevisions"); process.exit(1); }
let i = src.indexOf("{", start), depth = 0, end = -1;
for (let j = i; j < src.length; j++) {
  if (src[j] === "{") depth++;
  else if (src[j] === "}") { depth--; if (depth === 0) { end = j + 1; break; } }
}
if (end < 0) { console.error("FAIL: 大括号未配对，截取失败"); process.exit(1); }
const code = src.slice(start, end);

// ---- 2) 真实落库数据 ----
const macro = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "dataset", "macro.json"), "utf8"));
const STATE = {
  imfWoeMonths: macro.imfWoeMonths || [],
  imfWoe2026Growth: macro.imfWoe2026Growth || [],
  imfWoe2027Growth: macro.imfWoe2027Growth || [],
  gdpYears: macro.gdpYears || [], gdpValues: macro.gdpValues || [], gdpActual: macro.gdpActual || []
};

// ---- 3) 最小 DOM / ECharts stub ----
const mkEl = () => ({ innerHTML: "", style: {} });
const els = {};
const $ = (id) => els[id] || (els[id] = mkEl());
const ecCharts = {};
let captured = null;
const echarts = { init: () => ({ setOption: (o) => { captured = o; }, dispose: () => {} }) };
const fmtX = (v) => String(v).slice(2).replace("-", "/");

// ⚠️ renderWoeRevisions 里用的是裸全局 `echarts`（与 renderPmiEcharts 一致：
//    守卫写 window.echarts、绘图写 echarts.init），故两个都要注入。
const fn = new Function("STATE", "$", "ecCharts", "window", "echarts", "fmtX",
  code + "; return renderWoeRevisions;")(STATE, $, ecCharts, { echarts }, echarts, fmtX);

// ---- 4) 实跑 ----
const box = mkEl();
const CFG_SRC = "<b>数据源：</b>IMF《世界经济展望》{latest}，逐期（1/4/7/10 月）…";
fn(box, "demand_macro_leading_gdp", { ec: true, ecH: 320, source: CFG_SRC });

// ---- 5) 断言 ----
const results = [];
const t = (name, ok, extra) => results.push([name, !!ok, extra === undefined ? "" : String(extra)]);

t("box 写入了 ec_ 容器", box.innerHTML.indexOf("id='ec_demand_macro_leading_gdp'") >= 0);
t("box 写入了页尾 .src", box.innerHTML.indexOf("class='src'") >= 0);
t("setOption 被调用（ECharts 实例已初始化）", !!captured);
if (captured) {
  const s = captured.series || [];
  t("序列 2 条（2026 / 2027）", s.length === 2, s.length);
  t("2026 线 = 3.3/3.1/3.0/3.1", JSON.stringify(s[0].data) === JSON.stringify([3.3, 3.1, 3.0, 3.1]), JSON.stringify(s[0].data));
  t("2027 线 = 3.2/3.2/3.4/3.4", JSON.stringify(s[1].data) === JSON.stringify([3.2, 3.2, 3.4, 3.4]), JSON.stringify(s[1].data));
  t("2026 线名", s[0].name === "2026 增速预测", s[0].name);
  t("2027 线名（虚线）", s[1].name === "2027 增速预测" && s[1].lineStyle.type === "dashed");
  t("x 轴 = 4 个期次", JSON.stringify(captured.xAxis.data) === JSON.stringify(["2026-01", "2026-04", "2026-07", "2026-10"]));
  const ml = (s[0].markLine && s[0].markLine.data) || [];
  t("2025 实际基准线 = 3.5", ml.length === 1 && ml[0].yAxis === 3.5, ml.length ? ml[0].yAxis : "无");
  t("y 轴下界低于最小值 3.0", captured.yAxis.min < 3.0, captured.yAxis.min);
  t("y 轴上界高于基准线 3.5", captured.yAxis.max > 3.5, captured.yAxis.max);
  t("末点数值标签（endLabel）已开", !!(s[0].endLabel && s[0].endLabel.show));
  // tooltip 回调实跑：第 3 期（2026-07）2026 线 = 3.0，上一期 3.1 → 应为 -0.1 pp
  let tip = "";
  try {
    tip = captured.tooltip.formatter([
      { name: "2026-07", seriesIndex: 0, dataIndex: 2, value: 3.0, marker: "<i>" },
      { name: "2026-07", seriesIndex: 1, dataIndex: 2, value: 3.4, marker: "<i>" }
    ]);
  } catch (e) { tip = "EX:" + e.message; }
  t("tooltip 回调不抛异常", tip.indexOf("EX:") !== 0, tip);
  t("tooltip 含「较上期 -0.1 pp」", tip.indexOf("较上期 -0.1 pp") >= 0, tip.replace(/<[^>]+>/g, "|"));
  // 首期不应出现 Δ（没有上一期可比）
  let tip0 = "";
  try {
    tip0 = captured.tooltip.formatter([{ name: "2026-01", seriesIndex: 0, dataIndex: 0, value: 3.3, marker: "<i>" }]);
  } catch (e) { tip0 = "EX:" + e.message; }
  t("首期 tooltip 无 Δ", tip0.indexOf("较上期") < 0, tip0.replace(/<[^>]+>/g, "|"));
}
// 数据缺失时不应抛错，应给出占位
const box2 = mkEl();
let emptyOk = true;
try {
  const fn2 = new Function("STATE", "$", "ecCharts", "window", "echarts", "fmtX",
    code + "; return renderWoeRevisions;")(
    { imfWoeMonths: [], imfWoe2026Growth: [], imfWoe2027Growth: [], gdpYears: [], gdpValues: [], gdpActual: [] },
    $, {}, { echarts }, echarts, fmtX);
  fn2(box2, "x", { ec: true });
} catch (e) { emptyOk = false; }
t("数据缺失时不抛错且给占位", emptyOk && box2.innerHTML.indexOf("IMF WEO 期次数据缺失") >= 0);

let bad = 0;
results.forEach(([n, ok, x]) => { if (!ok) bad++; console.log((ok ? "PASS " : "FAIL ") + n + (x ? "  [" + x + "]" : "")); });
console.log(bad ? `\n${bad} 项失败` : "\nALL OK");
process.exit(bad ? 1 : 0);
