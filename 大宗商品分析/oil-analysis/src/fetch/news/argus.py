# -*- coding: utf-8 -*-
"""原油快讯抓取：Argus Media 原油页 → data/dataset/news.json 的 crudeNews。

存储选型：**JSON**（不是 xlsx）。理由见 README「首屏改版」节——本域是机器产出、
需按 URL 去重 / 按日期排序 / 区间合并，且 data/dataset/*.json 会被 dataio.GROUPS
直接注入看板，零额外管线。

**抓取规则**：
    新闻源 = Argus「filtered 完整 feed」第一页（latest-market-news?filter_commodity=crude…），
    即最近 ~27 条原油快讯（整页），而非 commodities 页只 5 条的精选 widget。
    每次抓取**整页**解析，按 URL 去重后合并（保留已有 + 新增），按日期倒序写回。
    因页内都是最近窗口，news.json 自然收敛到「最近 ~27 条」，无需 last_date 下界过滤。
    注：早期版本用 lastDate→until 区间增量抓 commodities 页 5 条精选，会系统性漏掉同日
    其余快讯——这正是「fetch 永远只有 5 条」的根因，现已改为整页完整 feed。

⚠️ **已知硬约束：Argus 有 AWS WAF 挑战**
    非浏览器请求（curl / urllib / requests）一律拿到 status 202 的
    ``window.gokuProps`` 挑战页（Server: CloudFront, x-cache: Error from cloudfront），
    拿不到新闻正文。所以 ``fetch_html()`` 会**主动探测** WAF 并返回
    ``{"ok": false, "blocked": true, "reason": "waf"}``，而不是假装成功。
    → 真正自动化需要可执行 JS 的通道（headless 浏览器），或由人工/可渲染通道
      把结果写进本文件。解析逻辑 ``parse_html()`` 已按页面结构写好，
      可用 ``--from-file`` 拿一份真实 HTML 离线验证。

运行：
    python -m src.fetch.news.argus                    # 抓 [lastDate, 今天]
    python -m src.fetch.news.argus --until 2026-10-15 # 指定截止日
    python -m src.fetch.news.argus --from-file page.html   # 离线解析（不联网）
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta

from src.paths import DATASET_DIR

STORE = os.path.join(DATASET_DIR, "news.json")
# ⚠️ 默认抓取值得注意：
#   /en/commodities/crude 的「Latest crude oil news」只是 **5 条精选** 卡片（qa-combinedfeed-*），
#   会漏掉同日的其余快讯；而 filtered 列表页（latest-market-news?filter_commodity=crude…）
#   是 **完整 feed**（实测 27 条，含同日全部），且用不同版式（qa-item-title + 月名 dateline）。
#   所以默认源锁定 filtered 列表页，保证 fetch 不漏条；可用环境变量 ARGUS_LIST_URL 覆盖。
LIST_URL = ("https://www.argusmedia.com/en/news-and-insights/latest-market-news"
            "?filter_language=en-gb&filter_commodity=crude:crude+oil,condensate&page=1")
ARTICLE_RE = re.compile(
    r"/en/news-and-insights/latest-market-news/(\d+)-([a-z0-9\-]+)")
DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{2})\b")   # Argus 页内日期形如 14/10/26
# filtered 列表页（latest-market-news?filter_commodity=crude）的日期在摘要里是
# 「City, 14 October (Argus)」月名写法，需要映射成数字。
_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], start=1)}
BASE_DATE = "2026-10-14"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
}


# ---------- 存储读写 ----------
def load_store():
    if not os.path.exists(STORE):
        return {"crudeNewsMeta": {"baseDate": BASE_DATE}, "crudeNews": []}
    with open(STORE, "r", encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("crudeNews", [])
    d.setdefault("crudeNewsMeta", {})
    d["crudeNewsMeta"].setdefault("baseDate", BASE_DATE)
    return d


def save_store(store):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def last_date(store):
    """已有新闻的最大日期；没有时回落 baseDate。"""
    ds = [n.get("date") for n in store.get("crudeNews", []) if n.get("date")]
    return max(ds) if ds else store.get("crudeNewsMeta", {}).get("baseDate", BASE_DATE)


# ---------- 抓取 ----------
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta

from src.paths import DATASET_DIR

# 仓库根目录（src/fetch/news/argus.py → 上四级）
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# 无头浏览器渲染脚本（tools/fetch_argus_news.cjs）实测渲染 Argus 的超时上限
_BROWSER_TIMEOUT = 90


def fetch_html(url=LIST_URL, timeout=30):
    """抓取页面 HTML（urllib 直连）。命中 WAF 时返回 (html, True)。"""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        html = raw.decode("utf-8", "ignore")
    # WAF 挑战页特征：AWS WAF 注入 window.gokuProps，且没有真实内容
    blocked = ("gokuProps" in html) or ("aws-waf-token" in html)
    return html, blocked


def _find_node():
    """定位 node 可执行文件：优先托管运行时，回落 which。"""
    for c in ("/Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node",
              "/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if os.path.exists(c):
            return c
    import shutil
    return shutil.which("node")


def fetch_html_browser():
    """用无头 Chromium 渲染 Argus 页（tools/fetch_argus_news.cjs）。

    返回 (html, error)：html 为 None 表示通道不可用（无 node / playwright-core /
    chromium 二进制，或渲染超时/报错），此时调用方应回落 urllib 直连。
    成功时 html 是渲染后的完整 HTML（若 AWS WAF 仍拦，里面会带 gokuProps，
    由调用方判定）。"""
    node = _find_node()
    if not node:
        return None, "未找到 node 可执行文件"
    script = os.path.join(_REPO_ROOT, "tools", "fetch_argus_news.cjs")
    if not os.path.exists(script):
        return None, "未找到 tools/fetch_argus_news.cjs"
    env = dict(os.environ)
    env["NODE_PATH"] = "/Users/sto1/.workbuddy/binaries/node/workspace/node_modules"
    try:
        out = subprocess.run([node, script], capture_output=True, text=True,
                              timeout=_BROWSER_TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return None, "无头浏览器渲染超时（%ds）" % _BROWSER_TIMEOUT
    except Exception as e:
        return None, "启动无头浏览器失败：" + str(e)
    if out.returncode != 0:
        return None, "渲染通道报错(exit=%d): %s" % (out.returncode, out.stderr.strip()[:300])
    try:
        obj = json.loads(out.stdout)
    except Exception as e:
        return None, "渲染通道输出非 JSON：" + str(e)
    if not obj.get("ok"):
        return None, "渲染通道返回失败"
    return obj.get("html") or "", None


def _acquire_html():
    """取得可解析的 Argus 页面 HTML。

    返回 (html, waf_blocked, via_browser)：
      - 优先无头浏览器（能过 AWS WAF）；
      - 浏览器不可用或仍被 WAF 拦 → 回落 urllib 直连，并据结果判定 waf。
      - html 为 None 表示两条路都没拿到（网络异常等），由 run() 上报 error。
    """
    html, err = fetch_html_browser()
    if html is not None:
        if ("gokuProps" in html) or ("aws-waf-token" in html):
            return html, True, True      # 浏览器也被 WAF 拦
        return html, False, True
    # 浏览器通道不可用：回落 urllib
    try:
        u, blocked = fetch_html()
    except Exception:
        return None, False, False        # 连 urllib 都失败
    return u, blocked, False


def _slug_to_title(slug):
    """URL slug 回退成标题（拿不到锚文本时兜底）：连字符→空格，首字母大写。"""
    words = slug.split("-")
    keep = {"a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "as", "is"}
    out = []
    for i, w in enumerate(words):
        if not w:
            continue
        out.append(w if (i and w in keep) else w.capitalize())
    return " ".join(out)


def parse_html(html, default_date=None):
    """从 Argus 列表页 HTML 解析 [(title, url, date)]。

    页面里每条新闻形如：锚点 href="/en/news-and-insights/latest-market-news/<id>-<slug>"，
    附近带 ``DD/MM/YY`` 日期。

    ⚠️ **归属窗口很关键**：同一页里 N 条新闻是连续的 HTML 块，若用「锚点 ±600 字符」
    这种固定窗口取值，会跨块误取到**下一条**的标题/日期（实测两条新闻 title 全变成
    第二条）。所以这里把每条的取值窗口严格限定为
    ``[上一条锚点结束, 下一条锚点开始)``，块内再定位。

    ⚠️ **Argus 的真实结构（实测）**：每条新闻是一张大卡片，整张卡被一个 `<a>` 包住，
    里面依次是「Latest crude oil news」样板字 + 日期 + **标题（可能重复两次）** +
    正文导语（``City, DD Month (Argus) — …``）。所以：
      - 标题不能取「整个 <a> 内部文本」（会连正文一起捞进来）；
      - 可靠分隔是 dateline 的 ``(Argus)``：标题 = 日期之后、``(Argus)`` 之前的文本，
        再去掉样板字与重复片段；取不到（无 dateline）时回落 slug 兜底。
      - 日期可能在锚点**前**（列表式）也可能在**后**（卡片式），两边都查。
    """
    ms = list(ARTICLE_RE.finditer(html))
    best = {}          # url -> item（同一 URL 在页内可能多次出现，保留信息更全的那次）
    for i, m in enumerate(ms):
        url = "https://www.argusmedia.com" + m.group(0)
        left = ms[i - 1].end() if i > 0 else max(0, m.start() - 800)
        right = ms[i + 1].start() if i + 1 < len(ms) else min(len(html), m.end() + 1500)
        before, after = html[left:m.start()], html[m.end():right]

        # --- 日期：两种版式分别取 ---
        #   ① commodities 页：日期徽标 DD/MM/YY（qa-combinedfeed-item-date）
        #   ② filtered 列表页：摘要里「City, 14 October (Argus)」月名写法
        #   ③ 兜底：锚点前后找 DD/MM/YY
        d = None
        dm_date = re.search(r'qa-combinedfeed-item-date[^>]*>(\d{2})/(\d{2})/(\d{2})', after)
        if dm_date:
            dd, mm, yy = dm_date.groups()
        else:
            dl = re.search(
                r',\s*(\d{1,2})\s+(January|February|March|April|May|June|July|'
                r'August|September|October|November|December)\b', after)
            if dl:
                dd, mm = dl.group(1), str(_MONTHS[dl.group(2).lower()])
                yy = str(date.today().year)[2:]
            else:
                dms = DATE_RE.findall(before)
                if dms:
                    dd, mm, yy = dms[-1]
                else:
                    dma = DATE_RE.search(after)
                    dd, mm, yy = dma.groups() if dma else (None, None, None)
        if dd:
            try:
                d = date(2000 + int(yy), int(mm), int(dd)).isoformat()
            except ValueError:
                d = None

        # --- 标题：两种版式的稳定 QA 钩子都认（commodities 用 qa-combinedfeed-item-title，
        #     filtered 列表页用 qa-item-title），取不到再回落「剥标签 + 截 (Argus) / 锚点内文本」，
        #     再不行用 slug 兜底。 ---
        hm = (re.search(r'qa-combinedfeed-item-title[^>]*>(.*?)</h3>', after, re.S)
              or re.search(r'qa-item-title[^>]*>(.*?)</h3>', after, re.S))
        if hm:
            title = re.sub(r"<[^>]+>", "", hm.group(1)).strip()
            from_slug = False
        else:
            # 兜底：整段剥标签后截到 dateline 的 (Argus) 之前；再不行取锚点内文本
            gt = after.find(">")
            seg0 = after[gt + 1:] if gt >= 0 else after
            seg = re.sub(r"<[^>]+>", " ", seg0)
            seg = re.sub(r"\s+", " ", seg).strip()
            seg = re.sub(r"(?i)^latest crude oil news\s*", "", seg)
            dlpos = seg.find("(Argus)")
            if dlpos > 0:
                cand = re.sub(r"^\d{2}/\d{2}/\d{2}\s*", "", seg[:dlpos]).strip(" :|-").strip()
                # 有的卡片标题重复两次（可见 + 屏幕阅读副本），去重取前半
                if len(cand) >= 4 and len(cand) % 2 == 0 and cand[:len(cand) // 2] == cand[len(cand) // 2:]:
                    cand = cand[:len(cand) // 2].strip()
                title, from_slug = cand, False
            else:
                ea = after.find("</a>")
                body = after[gt + 1:ea] if (gt >= 0 and ea >= 0) else (after[:ea] if ea >= 0 else after)
                cand = re.sub(r"<[^>]+>", " ", body)
                cand = re.sub(r"\s+", " ", cand).strip()
                if cand and len(cand) >= 6:
                    title, from_slug = cand, False
                else:
                    title, from_slug = _slug_to_title(m.group(2)), True

        prev = best.get(url)
        # 同一 URL 多次出现时，优先保留「有真实标题」的那次
        if prev is None or (prev.get("_slug") and not from_slug):
            best[url] = {"title": title, "url": url, "date": d or default_date,
                         "source": "Argus", "_slug": from_slug}

    items = list(best.values())
    for it in items:
        it.pop("_slug", None)
    return items


# ---------- 区间合并 ----------
def merge(store, items, since, until):
    """按 URL 去重，只保留 [since, until] 区间，按日期倒序返回合并后的列表。"""
    have = {n.get("url") for n in store.get("crudeNews", [])}
    added = []
    for it in items:
        if not it.get("url") or it["url"] in have:
            continue
        d = it.get("date")
        if d and since and d < since:
            continue
        if d and until and d > until:
            continue
        added.append(it)
        have.add(it["url"])
    merged = list(store.get("crudeNews", [])) + added
    merged.sort(key=lambda n: (n.get("date") or ""), reverse=True)  # 最新在前
    return merged, added


def run(until=None, from_file=None, dry_run=False):
    """执行一次抓取/合并。返回结果 dict（供 CLI 与 /api/news 共用）。"""
    until = until or date.today().isoformat()
    store = load_store()
    since = last_date(store)

    if from_file:
        with open(from_file, "r", encoding="utf-8") as f:
            html = f.read()
        blocked = "gokuProps" in html
        items = parse_html(html, default_date=until)
    else:
        html, waf, via_browser = _acquire_html()
        if html is None:
            return {"ok": False, "blocked": False,
                    "error": "无法获取 Argus 页面（无头浏览器通道不可用，且 urllib 直连也失败）。",
                    "since": since, "until": until, "added": 0}
        if waf:
            msg = ("Argus 返回 AWS WAF 挑战页（"
                   + ("即便经无头浏览器渲染仍被拦截；可尝试更新浏览器指纹，或人工更新 news.json）。"
                      if via_browser else
                      "非浏览器请求无法取到新闻。需可执行 JS 的抓取通道，或人工更新 news.json。"))
            return {"ok": False, "blocked": True, "reason": "waf", "message": msg,
                    "since": since, "until": until, "added": 0}
        items = parse_html(html, default_date=until)

    # ⚠️ 新闻源已改为「filtered 完整 feed」（整页第一页 = 最近 ~27 条），不再是
    #    commodities 页的 5 条精选 widget。因此这里**不再用 last_date 做下界过滤**
    #    （否则只会保留 >= 最后日期的当日条，把更早但仍在页内的快讯漏掉）；改为整页
    #    抓取 + 按 URL 去重。页内都是最近窗口，news.json 会自然收敛到「最近 ~27 条」，
    #    不会无限膨胀。since 仅用于上报展示。
    merged, added = merge(store, items, None, until)
    if not dry_run:
        store["crudeNews"] = merged
        store.setdefault("crudeNewsMeta", {})["lastFetched"] = until
        save_store(store)
    return {"ok": True, "blocked": False, "since": since, "until": until,
            "parsed": len(items), "added": len(added), "total": len(merged),
            "items": merged, "addedItems": added}


def main(argv=None):
    p = argparse.ArgumentParser(description="抓取 Argus 原油快讯（增量：最后日期 → 今天）")
    p.add_argument("--until", help="截止日期 YYYY-MM-DD，默认今天")
    p.add_argument("--from-file", help="离线解析本地 HTML（不联网），用于验证解析逻辑")
    p.add_argument("--dry-run", action="store_true", help="只打印不写盘")
    a = p.parse_args(argv)
    r = run(until=a.until, from_file=a.from_file, dry_run=a.dry_run)
    print(json.dumps({k: v for k, v in r.items() if k != "items"},
                     ensure_ascii=False, indent=2))
    if not r.get("ok"):
        print("\n⚠️ 未取到新闻：" + (r.get("message") or r.get("error") or ""), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
