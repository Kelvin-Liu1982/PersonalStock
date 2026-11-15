#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_event.py —— 抓「最新一条重要黄金事件」，写回 data/gold_data.xlsx。

背景：页面 HERO 上的 event 条（eventDate / eventPct / eventText）原先是**人工快照**，
没有任何 fetch 会碰它，跑多少次 fetch_gold_data.py 都会停在旧日期。本脚本把它接上：

    eventText   <- 新闻标题（Google News RSS，免费无 key）
    eventDate   <- 该新闻的发布日期
    eventPct    <- 该日/此前最近交易日的金价单日涨跌幅（Yahoo GC=F 日线）
    eventSource <- 来源媒体名

同时在 xlsx 新建「黄金事件流」sheet，保留最近 N 条候选（含链接），便于回溯与人工替换。

用法（在 gold-analysis/ 下运行）:
  python3 src/fetch_event.py                抓取并写入（窗口内取分最高的一条）
  python3 src/fetch_event.py --days 7       把候选窗口放宽到 7 天
  python3 src/fetch_event.py --list 10      只打印候选 Top10，不写 Excel
  python3 src/fetch_event.py --dry-run      打印将要写入的三个字段，不落盘
  python3 src/fetch_event.py --no-price     跳过日线抓取，eventPct 沿用 Excel 原值

抓取后需再跑 build_html.py 才会写进 HTML：
  python3 src/fetch_event.py && python3 src/build_html.py

- 相关性：标题必须命中 EVENT_CORE_WORDS（黄金/金价/gold/XAU…）才进入候选；
  score = 来源权重 × (1 + 0.35 × 信号词命中数) × 1/(1 + 1.2 × 天数) × 噪音惩罚
  信号词 = 央行/美联储/降息/CPI/关税/地缘…（EVENT_SIGNAL_WORDS）
  噪音词 = 饰品/柜台/克重/促销…（EVENT_NOISE_WORDS，命中 score ×= 0.25）
  ⚠️ 去重必须按**清洗后标题**：同一篇文章会被 Google News 不同地区版收录（raw title
  带不同后缀骗过 RSS 层去重、清洗后同名），只按 raw title 去重会让「黄金事件流」
  出现重复行，页面 EVENT 按钮循环时也会踩到。
"""
import argparse
import datetime
import email.utils
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import excelio
import paths


# ---------------- 网络 ----------------
def http_get(url, as_json=False):
    """GET；全部重试失败后返回 None 并打印原因（不抛异常）。"""
    last = ""
    for attempt in range(config.HTTP_RETRIES):
        if attempt:
            time.sleep(config.HTTP_RETRY_DELAY * attempt)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(
                req, timeout=config.REQUEST_TIMEOUT, context=ssl.create_default_context()
            ) as r:
                raw = r.read()
            return json.loads(raw.decode("utf-8")) if as_json else raw
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:160]}"
    print(f"  ! 请求失败（已重试 {config.HTTP_RETRIES} 次）{last}")
    return None


# ---------------- 日线价格 → 单日涨跌 ----------------
def fetch_daily(sym=None, rng=None):
    """返回 [{date:'YYYY-MM-DD', close:float, pct:float}]（按日期升序，首日 pct=None）。"""
    sym = sym or config.YAHOO_GOLD_SYM
    rng = rng or config.YAHOO_RANGE
    url = config.YAHOO_CHART.format(sym=sym, rng=rng)
    j = http_get(url, as_json=True)
    if not j or not j.get("chart", {}).get("result"):
        print("  ! 日线抓取失败（Yahoo），eventPct 将沿用原值")
        return []
    res = j["chart"]["result"][0]
    stamps = res.get("timestamp") or []
    closes = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    out = []
    prev = None
    for t, c in zip(stamps, closes):
        if c is None:
            continue
        d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")
        pct = None if prev in (None, 0) else (c - prev) / prev * 100.0
        out.append({"date": d, "close": float(c), "pct": pct})
        prev = float(c)
    return out


def pct_on_or_before(daily, day):
    """取 <= day 的最近一个交易日的涨跌幅（float, %）；取不到返回 None。"""
    hit = None
    for r in daily:
        if r["date"] <= day:
            hit = r
        else:
            break
    return hit["pct"] if hit else None


def fmt_pct(v):
    """1.234 -> '+1.23%'"""
    if v is None:
        return None
    return f"{v:+.2f}%"


# ---------------- 新闻 RSS ----------------
def _is_latin(s):
    """拉丁字符占比 > 60% 视为英文标题（对应更长的截断长度）。"""
    if not s:
        return False
    lat = sum(1 for ch in s if ord(ch) < 0x2E80)
    return lat / len(s) > 0.6


def clean_title(title, source):
    """清洗 Google News 标题：
    1) 去掉尾部 ' - 来源名'（Google News 的固定格式）
    2) 去掉中文站常见的关键词堆砌 '标题|COMEX黄金|美元指数|…'（取 | 前的主标题）
    3) 按中/英分别截断
    """
    t = re.sub(r"\s+", " ", (title or "").strip())
    if source and t.endswith(f" - {source}"):
        t = t[: -(len(source) + 3)].strip()
    # 关键词堆砌：只保留第一个 | 之前的主标题（主标题太短则保留原文）
    head = re.split(r"\s*[|｜]\s*", t)[0].strip()
    if len(head) >= 8:
        t = head
    # 某些源后缀不是 source 名，兜底去掉最后一个 ' - xxx'（仅当剩余仍够长）
    if len(t) > 24:
        t2 = re.sub(r"\s+-\s+[^-]{2,24}$", "", t).strip()
        if len(t2) >= 12:
            t = t2
    limit = config.EVENT_TEXT_MAX_LATIN if _is_latin(t) else config.EVENT_TEXT_MAX_CJK
    if len(t) > limit:
        t = t[:limit].rstrip() + "…"
    return t


def fetch_items():
    """抓所有 EVENT_FEEDS，返回去重后的条目列表。"""
    items, seen = [], set()
    for feed in config.EVENT_FEEDS:
        url = feed["url"].format(q=urllib.parse.quote(feed["query"]))
        raw = http_get(url)
        if not raw:
            print(f"  ! 源失败：{feed['name']}")
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            print(f"  ! XML 解析失败：{feed['name']} -> {e}")
            continue
        n = 0
        for it in root.findall(".//item"):
            title = it.findtext("title") or ""
            pub = it.findtext("pubDate") or ""
            src_el = it.find("source")
            source = (src_el.text if src_el is not None and src_el.text else feed["name"])
            link = it.findtext("link") or ""
            try:
                dt = email.utils.parsedate_to_datetime(pub)
                day = dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                continue
            key = title.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            items.append({
                "date": day,
                "title": clean_title(title, source),
                "source": source,
                "link": link,
                "feed_weight": feed.get("weight", 1.0),
                "raw_title": title,
            })
            n += 1
        print(f"  ✓ {feed['name']}：{n} 条")
    return items


# ---------------- 打分 ----------------
def source_weight(src):
    s = (src or "").strip().lower()
    for k, w in config.EVENT_SOURCE_PENALTY.items():
        if k.lower() in s:
            return w
    for k, w in config.EVENT_SOURCE_WEIGHT.items():
        if k.lower() in s:
            return w
    return 0.9


def score(item, today):
    text = (item["raw_title"] + " " + item["title"]).lower()
    if not any(w.lower() in text for w in config.EVENT_CORE_WORDS):
        return 0.0
    sig = sum(1 for w in config.EVENT_SIGNAL_WORDS if w.lower() in text)
    noise = any(w.lower() in text for w in config.EVENT_NOISE_WORDS)

    try:
        age = (today - datetime.date.fromisoformat(item["date"])).days
    except ValueError:
        return 0.0
    age = max(age, 0)

    s = source_weight(item["source"]) * item["feed_weight"]
    s *= (1 + 0.35 * sig)
    s *= 1.0 / (1 + 1.2 * age)  # 新鲜度衰减：越新的条目越优先（每天跑一次即"最新"）
    if noise:
        s *= 0.25
    return round(s, 4)


def pick(items, daily, days):
    """在窗口内选分最高的一条；窗口内无候选则放宽到 EVENT_WINDOW_FALLBACK。"""
    today = datetime.date.today()
    for win in (days, config.EVENT_WINDOW_FALLBACK):
        pool = []
        for it in items:
            try:
                age = (today - datetime.date.fromisoformat(it["date"])).days
            except ValueError:
                continue
            if age < 0 or age > win:
                continue
            sc = score(it, today)
            if sc > 0:
                pool.append((sc, it))
        if pool:
            pool.sort(key=lambda x: (-x[0], x[1]["date"]))
            return pool, win
    return [], None


# ---------------- 主流程 ----------------
def main():
    ap = argparse.ArgumentParser(description="抓取最新黄金事件 -> data/gold_data.xlsx")
    ap.add_argument("--days", type=int, default=config.EVENT_WINDOW_DAYS,
                    help=f"候选窗口天数（默认 {config.EVENT_WINDOW_DAYS}）")
    ap.add_argument("--list", type=int, default=0, metavar="N",
                    help="只打印候选 TopN，不写 Excel")
    ap.add_argument("--dry-run", action="store_true", help="只打印将写入的字段")
    ap.add_argument("--no-price", action="store_true", help="跳过日线抓取")
    args = ap.parse_args()

    excelio.ensure_workbook()
    today = datetime.date.today()
    print(f"[事件抓取] 今天 {today.isoformat()} · 窗口 {args.days} 天")

    print("[1] 新闻源")
    items = fetch_items()
    print(f"  合计去重 {len(items)} 条")

    print("[2] 日线涨跌幅（Yahoo " + config.YAHOO_GOLD_SYM + "）")
    daily = [] if args.no_price else fetch_daily()
    if daily:
        print(f"  ✓ {len(daily)} 个交易日，最新 {daily[-1]['date']} "
              f"收 {daily[-1]['close']:.1f}（{fmt_pct(daily[-1]['pct'])}）")

    print("[3] 打分与筛选")
    pool, win = pick(items, daily, args.days)
    if not pool:
        print("  ✗ 窗口内没有命中核心词（黄金/金价/gold…）的候选，Excel 保持原值")
        return 1
    if win != args.days:
        print(f"  ! {args.days} 天内无候选，已放宽到 {win} 天")

    if args.list:
        print(f"\n候选 Top{args.list}（窗口 {win} 天）：")
        for sc, it in pool[: args.list]:
            p = fmt_pct(pct_on_or_before(daily, it["date"])) if daily else "—"
            print(f"  {sc:6.3f} | {it['date']} | {p or '—':>7} | {it['source']:<12} | {it['title']}")
        return 0

    best_sc, best = pool[0]
    pct = fmt_pct(pct_on_or_before(daily, best["date"])) if daily else None
    updates = {
        "eventDate": best["date"],
        "eventText": best["title"],
        "eventSource": best["source"],
    }
    if pct:
        updates["eventPct"] = pct

    print("\n选中事件：")
    print(f"  分数   {best_sc}")
    print(f"  日期   {best['date']}")
    print(f"  涨跌   {pct or '（沿用原值）'}")
    print(f"  来源   {best['source']}")
    print(f"  标题   {best['title']}")
    print(f"  链接   {best['link'][:100]}")

    if args.dry_run:
        print("\n[dry-run] 将写入：")
        for k, v in updates.items():
            print(f"  {k} = {v}")
        return 0

    # 「黄金事件流」：旧表 + 新候选，按清洗后标题去重（同一篇文章会被 Google News
    # 不同地区版收录，raw title 带不同后缀骗过 RSS 层去重、清洗后同名），再按日期倒序保留 N 条
    print("\n[4] 写入 Excel")
    old = excelio.read_events()
    merged = []
    for sc_, it in pool:
        p = fmt_pct(pct_on_or_before(daily, it["date"])) if daily else ""
        merged.append({"date": it["date"], "title": it["title"],
                       "source": it["source"], "pct": p or "", "link": it["link"]})
    merged += old
    dedup, seen_t = [], set()
    for r in merged:
        if r["title"] in seen_t:
            continue
        seen_t.add(r["title"])
        dedup.append(r)
    dedup.sort(key=lambda r: r["date"], reverse=True)
    dedup = dedup[: config.EVENT_KEEP_ROWS]
    # 首行固定为本次选中、页面 event 条正在显示的那条（其余按日期倒序），
    # 保证「黄金事件流」第 1 行 === event 条，便于人工核对与回溯。
    chosen = {"date": best["date"], "title": best["title"], "source": best["source"],
              "pct": pct or "", "link": best["link"]}
    merged = [chosen] + [r for r in dedup if r["title"] != best["title"]]

    n_rows = excelio.write_events(merged)
    n_fields = excelio.update_snapshot(updates)
    excelio.touch_meta()
    print(f"  ✓ 「黄金事件流」{n_rows} 行 -> {paths.DATA_XLSX}")
    print(f"  ✓ 「行情快照」写入 {n_fields} 个字段")
    print("  下一步：python3 src/build_html.py   # 把 Excel 注入 output/gold-terminal.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
