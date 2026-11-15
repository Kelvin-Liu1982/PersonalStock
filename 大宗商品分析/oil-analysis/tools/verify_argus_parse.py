# -*- coding: utf-8 -*-
"""argus.py 离线单测：解析归属 + 区间合并 + 增量去重。

不联网（Argus 有 AWS WAF，见 argus.py 头部注释），用构造的 HTML 片段验证
``parse_html()`` 的**块内归属**逻辑——这是最容易出错的地方：同一页里 N 条
新闻连续排列，若在「锚点 ±600 字符」固定窗口里取标题/日期，会跨块误取下一条
（实测两条新闻 title 全变成第二条）。

运行：python tools/verify_argus_parse.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.fetch.news import argus  # noqa: E402

PASS = FAIL = 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s  %s" % (name, extra))


# ---------- 构造页面片段：三条新闻连续排列 ----------
# ① 日期在锚点之前（Argus 常见版式）
# ② 日期在锚点之后
# ③ 同一 URL 先以图片链接出现（无锚文本）→ 再以文本链接出现
FIXTURE = """
<div class="news-list">
  <article>
    <div class="meta"><span class="date">14/10/26</span></div>
    <h4><a href="/en/news-and-insights/latest-market-news/2603901-global-oil-supply-rebounds-in-september-iea">Global oil supply rebounds in September: IEA</a></h4>
  </article>
  <article>
    <h4><a href="/en/news-and-insights/latest-market-news/2603910-iea-says-96mn-bl-yet-to-be-released-from-stocks">IEA says 96mn bl yet to be released from stocks</a></h4>
    <div class="meta"><span class="date">15/10/26</span></div>
  </article>
  <article>
    <a href="/en/news-and-insights/latest-market-news/2603920-opec-cuts-crude-output-in-september"><img src="/x.png" alt=""></a>
    <h4><a href="/en/news-and-insights/latest-market-news/2603920-opec-cuts-crude-output-in-september">Opec cuts crude output in September</a></h4>
    <div class="meta"><span class="date">13/10/26</span></div>
  </article>
</div>
"""


def main():
    print("== parse_html 归属 ==")
    items = argus.parse_html(FIXTURE, default_date="2026-10-15")
    ck("解析出 3 条（同 URL 去重后）", len(items) == 3, "got=%d" % len(items))
    by_url = {i["url"]: i for i in items}

    u1 = "https://www.argusmedia.com/en/news-and-insights/latest-market-news/2603901-global-oil-supply-rebounds-in-september-iea"
    u2 = "https://www.argusmedia.com/en/news-and-insights/latest-market-news/2603910-iea-says-96mn-bl-yet-to-be-released-from-stocks"
    u3 = "https://www.argusmedia.com/en/news-and-insights/latest-market-news/2603920-opec-cuts-crude-output-in-september"

    ck("① title 不串位", by_url.get(u1, {}).get("title") == "Global oil supply rebounds in September: IEA",
       "got=%r" % by_url.get(u1, {}).get("title"))
    ck("② title 不串位", by_url.get(u2, {}).get("title") == "IEA says 96mn bl yet to be released from stocks",
       "got=%r" % by_url.get(u2, {}).get("title"))
    ck("③ 图片链接去重后取真实锚文本",
       by_url.get(u3, {}).get("title") == "Opec cuts crude output in September",
       "got=%r" % by_url.get(u3, {}).get("title"))

    ck("① 日期取锚点前的 14/10/26", by_url.get(u1, {}).get("date") == "2026-10-14",
       "got=%r" % by_url.get(u1, {}).get("date"))
    ck("② 日期取锚点后的 15/10/26", by_url.get(u2, {}).get("date") == "2026-10-15",
       "got=%r" % by_url.get(u2, {}).get("date"))
    ck("③ 日期 13/10/26", by_url.get(u3, {}).get("date") == "2026-10-13",
       "got=%r" % by_url.get(u3, {}).get("date"))
    ck("source 均为 Argus", all(i.get("source") == "Argus" for i in items))

    print("== slug 兜底标题 ==")
    solo = '<a href="/en/news-and-insights/latest-market-news/1-a-slug-with-no-anchor-text"></a>'
    r = argus.parse_html(solo, default_date="2026-10-14")
    ck("无锚文本时回退 slug", r and r[0]["title"] == "A Slug With No Anchor Text", "got=%r" % (r and r[0]["title"]))
    ck("无日期时回落 default_date", r and r[0]["date"] == "2026-10-14")

    print("== last_date / merge 增量规则 ==")
    store = {"crudeNewsMeta": {"baseDate": "2026-10-14"}, "crudeNews": []}
    ck("空库回落 baseDate", argus.last_date(store) == "2026-10-14")
    store["crudeNews"] = [{"url": "u-a", "date": "2026-10-13"}, {"url": "u-b", "date": "2026-10-15"}]
    ck("取已有最大日期", argus.last_date(store) == "2026-10-15")

    # 区间 [2026-10-14, 2026-10-15]：③ 10-13 应被排除，② 10-15 重复 URL 应去重
    merged, added = argus.merge(store, items, "2026-10-14", "2026-10-15")
    urls = [n["url"] for n in merged]
    ck("区间外（10-13）被排除", u3 not in urls)
    ck("已存在 URL 不去重失败（无重复）", len(urls) == len(set(urls)))
    ck("新增 u1(10-14,含当天) 与 u2(10-15)", u1 in urls and u2 in urls and len(added) == 2,
       "added=%d" % len(added))
    ck("按日期倒序（最新在前）",
       [n.get("date") for n in merged] == sorted((n.get("date") for n in merged), reverse=True),
       "got=%s" % [n.get("date") for n in merged])

    print("== 真实 news.json ==")
    st = argus.load_store()
    ck("crudeNews 非空", len(st.get("crudeNews", [])) > 0)
    ck("每条都有 title/url/date",
       all(n.get("title") and n.get("url") and n.get("date") for n in st.get("crudeNews", [])))
    ck("baseDate = 2026-10-14", st.get("crudeNewsMeta", {}).get("baseDate") == "2026-10-14")
    ck("URL 均为 argusmedia", all("argusmedia.com" in n["url"] for n in st.get("crudeNews", [])))
    ck("日期倒序",
       [n["date"] for n in st["crudeNews"]] == sorted((n["date"] for n in st["crudeNews"]), reverse=True))

    print("\n%d/%d PASS" % (PASS, PASS + FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
