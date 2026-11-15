#!/usr/bin/env node
/**
 * Argus 原油快讯 —— 无头浏览器渲染抓取（路径 B）。
 *
 * 为什么需要它：Argus 站点是 AWS WAF + CloudFront，非浏览器请求（curl/urllib）
 * 一律拿到 HTTP 202 + 内嵌 window.gokuProps 的 JS 挑战页，正文只在该页由浏览器
 * 执行 JS 后才渲染。本项目服务端（src/serve.py → /api/news）是单线程 HTTPServer，
 * 无法在请求内执行 JS，所以把「渲染」这一步交给本脚本：用**已经装好的**
 * playwright-core + chromium-1217 无头渲染 Argus 原油页，等新闻锚点出现后把
 * 渲染后的 HTML 以 JSON 吐出，交给 Python 侧的 parse_html() 解析。
 *
 * 复用既有资产（避免再装 Python playwright / 再下浏览器）：
 *   - playwright-core：/Users/sto1/.workbuddy/binaries/node/workspace/node_modules/playwright-core
 *   - chromium-1217  ：~/Library/Caches/ms-playwright/chromium-1217（Playwright 默认缓存目录）
 *
 * 退出码：
 *   0  = 成功（stdout 是一行 JSON {"ok":true,"html":...}）
 *   2  = 浏览器/通道不可用（无 node / 无 playwright-core / 无 chromium 二进制）
 *   3  = 启动或渲染过程中报错（stderr 有详情）
 *
 * 注意：即便本脚本成功返回 HTML，若 AWS WAF 仍拦（无头被识别），HTML 里会带
 * gokuProps —— Python 侧会据此继续报 blocked，不会假装成功。本脚本不负责判断 WAF，
 * 只负责「尽力渲染并交还 HTML」。
 *
 * 运行（由 argus.py 调起，也可手动）：
 *   node tools/fetch_argus_news.cjs
 *   ARGUS_CHROME_BIN=/path/to/chrome node tools/fetch_argus_news.cjs
 */
"use strict";
const fs = require("fs");
const path = require("path");
const PW_CORE = "/Users/sto1/.workbuddy/binaries/node/workspace/node_modules/playwright-core";
const LIST_URL = process.env.ARGUS_LIST_URL
  || "https://www.argusmedia.com/en/news-and-insights/latest-market-news"
     + "?filter_language=en-gb&filter_commodity=crude:crude+oil,condensate&page=1";
const ANCHOR = '/en/news-and-insights/latest-market-news/';

function findChrome() {
  if (process.env.ARGUS_CHROME_BIN && fs.existsSync(process.env.ARGUS_CHROME_BIN))
    return process.env.ARGUS_CHROME_BIN;
  const home = process.env.HOME || "/Users/sto1";
  const cand = [
    path.join(home, "Library/Caches/ms-playwright/chromium-1217/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ];
  for (const c of cand) if (fs.existsSync(c)) return c;
  return null;
}

function fail(code, msg) {
  process.stderr.write("[fetch_argus_news] " + msg + "\n");
  process.exit(code);
}

(async () => {
  let chromium;
  try {
    ({ chromium } = require(PW_CORE));
  } catch (e) {
    fail(2, "找不到 playwright-core（" + PW_CORE + "）：" + e.message);
  }
  const exe = findChrome();
  if (!exe) fail(2, "找不到可用的 Chromium/Chrome 二进制（chromium-1217 或系统 Chrome）");

  let browser;
  try {
    browser = await chromium.launch({
      executablePath: exe,
      headless: true,
      args: [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        // 尽量抹掉无头特征，提升过 AWS WAF 的概率
        "--disable-blink-features=AutomationControlled",
      ],
    });
  } catch (e) {
    fail(3, "Chromium 启动失败：" + e.message);
  }

  let code = 3;
  try {
    const ctx = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      locale: "en-GB",
    });
    const page = await ctx.newPage();
    await page.goto(LIST_URL, { waitUntil: "domcontentloaded", timeout: 30000 });
    // 等新闻卡片被 JS 渲染出来。⚠️ 不能只等「出现 1 个锚点」就截图——首张卡片一出来
    // page.content() 就可能只含 1 条（实测 /api/news 经服务调用时抓到 parsed=1）。
    // 用**锚点数量**判定（两种版式都通用）：commodities 页 5 锚点、filtered 列表页 27 锚点，
    // 要求出现 >=5 个新闻锚点再取 HTML；若 20s 内仍未凑齐（挑战页/异常），也照常返回
    // 当前 HTML（由 Python 侧判 WAF）。
    await page
      .waitForFunction(
        () => document.querySelectorAll('a[href*="/en/news-and-insights/latest-market-news/"]').length >= 5,
        { timeout: 20000 }
      )
      .catch(() => {});
    // 再多等一小段，避免最后 1-2 张卡片在边界处还没进 DOM
    await page.waitForTimeout(800).catch(() => {});
    const html = await page.content();
    process.stdout.write(JSON.stringify({ ok: true, html: html }));
    code = 0;
  } catch (e) {
    fail(3, "渲染过程出错：" + e.message);
  } finally {
    await browser.close().catch(() => {});
  }
  process.exit(code);
})();
