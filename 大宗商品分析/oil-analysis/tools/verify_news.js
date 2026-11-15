#!/usr/bin/node
/**
 * 校验首屏「Crude Oil News」卡（2026-10-15 新增，占原「各维度风险贡献（当前）」卡位）。
 *
 * 锁住三件事：
 *   ① 数据：data/dataset/news.json 的 crudeNews（纯手工维护域，无 extract 脚本）。
 *   ② 渲染：renderNews() 输出「标题 + 超链接」，标题下追加 date·source 元信息，新窗口打开，条目数与数据一致。
 *   ③ 布局改版：原「各维度风险贡献（当前）」整卡取消，缩小为 riskmini 并入
 *      「整体风险概览」卡（riskbar 画布仍在，只是换了容器与高度）。
 *
 * 与 tools/verify_imf_oil.js 同一套路：本机无 playwright，改用 DOM stub。
 * 从 src/pipeline/templates/dashboard.js 按大括号配对截出 renderNews 后实跑。
 *
 * 运行：node tools/verify_news.js
 */
"use strict";
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const SRC = path.join(ROOT, "src", "pipeline", "templates", "dashboard.js");
const HTML_TPL = path.join(ROOT, "src", "pipeline", "templates", "dashboard.html");
const src = fs.readFileSync(SRC, "utf8");
const tpl = fs.readFileSync(HTML_TPL, "utf8");

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
// esc 是 renderNews 依赖的独立函数（定义在 renderNews 之后，真实页面里是顶层
// 函数声明会被提升；但本 stub 只抽出 renderNews，需把 esc 一并注入作用域）
const codeNews = grab("function esc") + "\n" + grab("function renderNews");
const codeFetch = grab("function fetchNews");

// ---- 真实落库数据 ----
const news = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "dataset", "news.json"), "utf8"));
const list = news.crudeNews || [];

// ---- DOM stub ----
const mkEl = () => ({ innerHTML: "" });
const els = {};
const $ = (id) => els[id] || (els[id] = mkEl());
const SNAPSHOT = { crudeNews: list };

const renderNews = new Function("$", "SNAPSHOT", "STATE",
  codeNews + "; return renderNews;")($, SNAPSHOT, undefined);

// ---- 断言 ----
// 与 dashboard.js 的 esc() 保持一致：验证「标题在输出里以转义形式存在」
function escTest(v) {
  return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
    return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
  });
}
const results = [];
const t = (name, ok, extra) => results.push([name, !!ok, extra === undefined ? "" : String(extra)]);

// 数据层
t("落库：crudeNews 非空", list.length > 0, list.length);
t("落库：每条都有 title 与 url",
  list.every(n => n && n.title && n.url), list.length);
t("落库：url 均为 argusmedia 绝对链接",
  list.every(n => /^https:\/\/www\.argusmedia\.com\//.test(n.url)), list.length);

// 渲染层
renderNews();
const html = els["news"].innerHTML;
t("渲染：写入 #news 容器", !!html && html.length > 0, html.length);
t("渲染：条目数 = 数据条数",
  (html.match(/class='newsitem'/g) || []).length === list.length,
  (html.match(/class='newsitem'/g) || []).length + " vs " + list.length);
t("渲染：每条都是 <a> 超链接",
  (html.match(/<a href='/g) || []).length === list.length,
  (html.match(/<a href='/g) || []).length);
t("渲染：新窗口打开（target=_blank + rel=noopener）",
  /target='_blank'/.test(html) && /rel='noopener noreferrer'/.test(html));
t("渲染：全部 URL 都出现在输出里",
  list.every(n => html.indexOf(n.url) >= 0));
t("渲染：全部标题都出现在输出里（含 HTML 转义，如 Sana'a→Sana&#39;a）",
  list.every(n => html.indexOf(escTest(n.title)) >= 0));
// 2026-10-15 需求 C：每条新闻标题下方追加 news.json 里的 date 与 source（"日期 · 来源"）
t("渲染：每条都带 date·source 元信息（newsmeta）",
  (html.match(/class='newsmeta'/g) || []).length === list.length,
  (html.match(/class='newsmeta'/g) || []).length + " vs " + list.length);
t("渲染：元信息含「日期 · 来源」",
  list.filter(n => n.date && n.source)
      .every(n => html.indexOf(n.date + " · " + n.source) >= 0),
  list.filter(n => n.date && n.source).length);

// 空数据兜底
const els2 = {};
const $2 = (id) => els2[id] || (els2[id] = mkEl());
const fnEmpty = new Function("$", "SNAPSHOT", "STATE",
  codeNews + "; return renderNews;")($2, { crudeNews: [] }, undefined);
let okE = true, msgE = "";
try { fnEmpty(); } catch (e) { okE = false; msgE = e.message; }
t("空数据不抛异常", okE, msgE);
t("空数据写入占位「暂无原油快讯」",
  els2["news"].innerHTML.indexOf("暂无原油快讯") >= 0, els2["news"].innerHTML);

// 排序：日期倒序（最新在前）
const mixed = [
  { title: "AAA-10-13", url: "https://www.argusmedia.com/a", date: "2026-10-13" },
  { title: "BBB-10-15", url: "https://www.argusmedia.com/b", date: "2026-10-15" },
  { title: "CCC-10-14", url: "https://www.argusmedia.com/c", date: "2026-10-14" },
];
const els3 = {};
const $3 = (id) => els3[id] || (els3[id] = mkEl());
const fnSort = new Function("$", "SNAPSHOT", "STATE",
  codeNews + "; return renderNews;")($3, { crudeNews: mixed }, undefined);
fnSort();
const h3 = els3["news"].innerHTML;
t("排序：按 date 倒序（最新在前）",
  h3.indexOf("BBB-10-15") < h3.indexOf("CCC-10-14") &&
  h3.indexOf("CCC-10-14") < h3.indexOf("AAA-10-13"), h3.replace(/<[^>]+>/g, "|"));

// 布局改版（模板层）
t("模板：出现 Crude Oil News 卡", tpl.indexOf("Crude Oil News") >= 0);
t("模板：新闻卡容器 id=news", /id="news"/.test(tpl));
t("模板：riskbar 仍在（并入概览卡）", /id="riskbar"/.test(tpl));
t("模板：风险贡献缩为 riskmini 且位于整体风险概览卡内",
  /riskmini/.test(tpl) &&
  tpl.indexOf("整体风险概览") < tpl.indexOf("riskmini") &&
  tpl.indexOf("riskmini") < tpl.indexOf("Crude Oil News"));
t("模板：不再有独占的「各维度风险贡献」卡（原 158px 画布）",
  tpl.indexOf("height:158px") < 0);

// Fetch 按钮（模板层）
t("模板：右上角有 Fetch 按钮 id=newsfetch", /id="newsfetch"/.test(tpl));
t("模板：按钮挂在 .card-hd 里（与标题同行右对齐）",
  /class="card-hd"[\s\S]{0,200}id="newsfetch"/.test(tpl));
t("模板：按钮 onclick=fetchNews(this)", /onclick="fetchNews\(this\)"/.test(tpl));
t("模板：有状态行容器 id=newsstatus", /id="newsstatus"/.test(tpl));

// 高度匹配卡片（样式层）：卡片 flex 列 + 列表 flex:1 内部滚动
const css = fs.readFileSync(path.join(ROOT, "src", "pipeline", "templates", "dashboard.css"), "utf8");
t("样式：新闻卡为 flex 列容器", /\.newscard\{display:flex;flex-direction:column\}/.test(css));
t("样式：列表 flex:1 + min-height:0 + overflow-y:auto（填满卡高再滚动）",
  /\.newslist\{flex:1;min-height:0;overflow-y:auto/.test(css));
t("样式：状态行 .ok / .warn 两种配色",
  /\.newsstatus\.ok\{/.test(css) && /\.newsstatus\.warn\{/.test(css));

// ---- fetchNews 三种返回路径 ----
async function runFetch(res, opts) {
  opts = opts || {};
  const e = {};
  const $f = (id) => e[id] || (e[id] = mkEl());
  const btn = { disabled: false, textContent: "↻ Fetch" };
  let rendered = 0;
  const fakeFetch = () => opts.reject
    ? Promise.reject(new Error("404"))
    : Promise.resolve({ json: () => Promise.resolve(res) });
  const fn = new Function("$", "fetch", "STATE", "renderNews",
    codeFetch + "; return fetchNews;")($f, fakeFetch, { crudeNews: [] }, () => { rendered++; });
  fn(btn);   // fetchNews 不返回 promise，链在微任务里跑完，故让出两轮事件循环
  await new Promise(r => setTimeout(r, 0));
  await new Promise(r => setTimeout(r, 0));
  return { st: e["newsstatus"] || {}, btn, rendered };
}

(async () => {
  // ① 成功且有新增
  const a = await runFetch({ ok: true, added: 2, since: "2026-10-14", until: "2026-10-15",
    items: [{ title: "X", url: "https://www.argusmedia.com/x", date: "2026-10-15" }] });
  t("fetch 成功：状态行显示「新增 N 条」+ 区间",
    /新增 2 条/.test(a.st.textContent) && /2026-10-14 → 2026-10-15/.test(a.st.textContent),
    a.st.textContent);
  t("fetch 成功：状态行 class 含 ok", /\bok\b/.test(a.st.className), a.st.className);
  t("fetch 成功：重渲染列表", a.rendered === 1, a.rendered);
  t("fetch 成功：按钮恢复可用且文案还原",
    a.btn.disabled === false && a.btn.textContent === "↻ Fetch", a.btn.textContent);

  // ② 成功但无新增
  const b = await runFetch({ ok: true, added: 0, since: "2026-10-14", until: "2026-10-15", items: [] });
  t("fetch 无新增：显示「已是最新」", /已是最新/.test(b.st.textContent), b.st.textContent);

  // ③ 被 WAF 拦：如实显示原因，不假装成功
  const c = await runFetch({ ok: false, blocked: true,
    message: "Argus 返回 AWS WAF 挑战页（非浏览器请求取不到新闻）。" });
  t("WAF 拦截：状态行显示 WAF 原因", /WAF/.test(c.st.textContent), c.st.textContent);
  t("WAF 拦截：class 为 warn 而非 ok",
    /\bwarn\b/.test(c.st.className) && !/\bok\b/.test(c.st.className), c.st.className);
  t("WAF 拦截：不重渲染列表（数据没变）", c.rendered === 0, c.rendered);

  // ④ 网络失败（静态页 404）：提示用 run.py serve 打开
  const d = await runFetch(null, { reject: true });
  t("请求失败：提示请用 python run.py serve 打开",
    /run\.py serve/.test(d.st.textContent), d.st.textContent);
  t("请求失败：按钮仍恢复可用", d.btn.disabled === false);

  report();
})();

function report() {
  let fail = 0;
  results.forEach(([n, ok, extra]) => {
    if (!ok) fail++;
    console.log((ok ? "PASS " : "FAIL ") + n + (extra ? "  [" + extra + "]" : ""));
  });
  console.log("\n" + (results.length - fail) + "/" + results.length + " passed");
  process.exit(fail ? 1 : 0);
}
