#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载《中国出口集装箱运输市场周度报告》（上海航运交易所 / 上海航运交易研究所(筹) 微信公众号）到本地 HTML。

两种用法：
  1) 显式 URL 列表（最可靠，适合拿到公众号历史文章链接后批量存档）：
       python download_weekly_reports.py --urls-file urls.txt
     urls.txt 每行：  [YYYY-MM-DD ]<文章URL>
     例：
       2026-09-11 https://mp.weixin.qq.com/s/xxxxxxxx
       2024-01-05 https://mp.weixin.qq.com/s/yyyyyyyy

  2) 按日期区间 best-effort 自动发现（依赖 Bing 检索，可能被限流/不兜底）：
       python download_weekly_reports.py --start 2024-01-05 --end 2026-09-11

输出：<outdir>/<YYYYMMDD>.html  +  <YYYYMMDD>.meta.json（来源 URL、标题、抓取时间）。
断点续传：已存在同名 html 则跳过。
"""
import argparse, base64, json, re, ssl, sys, time, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

MIRROR_PREFER = [
    "mp.weixin.qq.com",            # 公众号原文（优先）
    "cctv.com", "news.cn", "cnr.cn", "yicai.com", "jwview.com",
    "sse.net.cn", "qq.com", "163.com", "sina.com.cn", "qdcdxh2021.com",
]

def fetch(url, timeout=25, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read().decode("utf-8", "ignore"), r.geturl()
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last

def extract_title(html):
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'<title>([^<]+)</title>', html, re.I)
    if m:
        return m.group(1).strip()
    return ""

def extract_date(html, fallback=None):
    # 标题/正文里的 (2026.09.11) 或 2026-09-11
    for pat in [r"(\d{4})\.(\d{2})\.(\d{2})", r"(\d{4})-(\d{2})-(\d{2})"]:
        m = re.search(pat, html)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return fallback

def decode_bing_ck(href):
    m = re.search(r"u=a1([^&]+)", href)
    if not m:
        return None
    s = m.group(1).replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        raw = base64.b64decode(s)
        mm = re.search(rb"https?://[^\x00-\x1f\s\"'<>]+", raw)
        return mm.group(0).decode() if mm else None
    except Exception:
        return None

def discover_via_bing(date_str):
    y, m, d = date_str.split("-")
    q = f"中国出口集装箱运输市场周度报告 {y}.{m}.{d}"
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": q, "setlang": "zh-CN"})
    try:
        html, _ = fetch(url)
    except Exception as e:
        print(f"  [discover] Bing 检索失败 {date_str}: {e}")
        return None
    cand = []
    for href in re.findall(r'href="([^"]+)"', html):
        real = None
        if "bing.com" in href or href.startswith("/"):
            real = decode_bing_ck(href)
        elif href.startswith("http"):
            real = href
        if not real:
            continue
        host = re.sub(r"^https?://", "", real).split("/")[0]
        if "bing.com" in host or "microsoft" in host:
            continue
        cand.append((MIRROR_PREFER.index(host, 0) if host in MIRROR_PREFER else 99, real))
    cand.sort()
    return cand[0][1] if cand else None

def save(outdir, date_str, html, url, title):
    stem = date_str.replace("-", "")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{stem}.html").write_text(html, encoding="utf-8")
    meta = {
        "date": date_str, "url": url, "title": title,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "bytes": len(html.encode("utf-8")),
    }
    (outdir / f"{stem}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [save] {stem}.html  ({meta['bytes']} bytes)  {title[:40]}")

def weeks(start, end):
    d = date(*map(int, start.split("-")))
    de = date(*map(int, end.split("-")))
    while d <= de:
        yield d.strftime("%Y-%m-%d")
        d += timedelta(days=7)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls-file", help="每行: [YYYY-MM-DD ]<url>")
    ap.add_argument("--start", help="YYYY-MM-DD")
    ap.add_argument("--end", help="YYYY-MM-DD")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--delay", type=float, default=2.0, help="请求间隔秒")
    ap.add_argument("--limit", type=int, default=0, help="最多处理几条(0=不限制)")
    args = ap.parse_args()
    outdir = Path(args.out).resolve()

    jobs = []  # (date_str, url_or_None)
    if args.urls_file:
        for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2 and re.match(r"^\d{4}-\d{2}-\d{2}$", parts[0]):
                jobs.append((parts[0], parts[1]))
            else:
                jobs.append((None, parts[0]))
    elif args.start and args.end:
        for ds in weeks(args.start, args.end):
            jobs.append((ds, None))
    else:
        print("用法：--urls-file FILE  或  --start X --end Y")
        sys.exit(2)

    if args.limit:
        jobs = jobs[:args.limit]

    done = skipped = fail = 0
    for date_str, url in jobs:
        stem = (date_str or "x").replace("-", "")
        if date_str and (outdir / f"{stem}.html").exists():
            print(f"  [skip] {stem}.html 已存在")
            skipped += 1
            continue
        try:
            if not url:
                print(f"  [discover] {date_str}")
                url = discover_via_bing(date_str)
                if not url:
                    print(f"  [fail] {date_str} 未发现可用链接")
                    fail += 1
                    time.sleep(args.delay)
                    continue
            html, final = fetch(url)
            title = extract_title(html)
            d = extract_date(html, fallback=date_str) or date_str
            save(outdir, d, html, final, title)
            done += 1
        except Exception as e:
            print(f"  [fail] {date_str or url} : {e}")
            fail += 1
        time.sleep(args.delay)

    print(f"\n完成：新增 {done}  |  跳过 {skipped}  |  失败 {fail}  ->  {outdir}")

if __name__ == "__main__":
    main()
