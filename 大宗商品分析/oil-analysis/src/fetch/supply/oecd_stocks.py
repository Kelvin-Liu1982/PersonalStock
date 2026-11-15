#!/usr/bin/posix/python3
"""从 OPEC MOMR PDF（第 9 章 Commercial Stock Movements, Table 9-1）提取 OECD 商业原油/产品/总库存。

说明：
  IEA 官网（iea.org）的 OECD 商业库存可下载数据被 Cloudflare 挡死，无法程序化抓取；
  但 IEA 编制的 OECD 商业库存序列由 OPEC 在自己的 MOMR 第 9 章 Table 9-1 转引，且用户本地
  已存有 1-8 月 MOMR PDF。本脚本解析这些 PDF 的 Table 9-1，按「每期月报取最近 3 个月、
  跨期取最新修订值」的方式拼成连续月度序列（与 OPEC 产量提取同源同法）。

  ⚠️ 关键的提取可靠性问题（已在 2026-08 修订）：
    一份 MOMR PDF 里 Table 9-1 实际有两处渲染——正文叙述旁一个「乱版」表格（单元格被拆开，
    如 Total 行的 May 值被拆成 '2,7'+'56'，且缺列），以及页末一个「干净版」正式表格
    （列对齐规整、含 Jun 25 / Apr 26 / May 26 / Jun 26 / Change 五列）。pdfplumber 的
    extract_tables 默认会先命中乱版表，导致：
      (a) Total 行最新月解析失败（拆分单元格 + 缺 3 值分支）→ 最新月变 null；
      (b) 乱版表部分数值与干净版不一致（如 crude May 乱版 1,327 vs 干净版 1,312，且乱版
          与同表 Change 列 -15.3 矛盾）。
    因此本脚本**按列位（word x 坐标）解析页末的干净版 Table 9-1**，彻底绕开乱版表的缺陷，
    不再需要手工回填。

  Table 9-1 干净版列结构（以 August 报告为例，列从左到右）：
    Jun 25(上年同月) | Apr 26(L-2) | May 26(L-1) | Jun 26(L) | Change(m-o-m)
  行标签：Crude oil / Products / Total / Days of forward cover
  每期月报 L = preliminary <Month> <Year> data 中的 (Year, Month)；取 (L-2, L-1, L) 三列。

输出：data/processed/oecd_stocks.json
  { "months":[...], "crude":[...], "products":[...], "total":[...], "days":[...], "source":..., "retrieved":... }
  其中 products = 成品油/石化产品等非原油商业库存；total = crude + products（含原油，勿当成品油用）

输入 PDF 目录：data/raw/opec_momr
运行：在仓库根目录执行 `python -m src.fetch.supply.oecd_stocks`
"""
import json, re, glob, os, datetime

from src.common.deps import require_pdfplumber
from src.common.months import from_name as month_num, pub_month, key as month_key, shift as prev_month
from src.paths import DATA_PROCESSED, DATA_RAW_OPEC

PRELIM = re.compile(r"preliminary ([A-Z][a-z]+) (\d{4}) data", re.I)
# 叙述句兜底：OECD commercial crude oil stocks stood at 1,296 mb in June.
NARR_CRUDE = re.compile(r"OECD commercial crude oil stocks stood at ([\d,]+) mb in ([A-Z][a-z]+)\.", re.I)

def find_table9_page(pdf):
    """返回含 'Table 9 - 1' 的页索引（干净版正式表所在页）。"""
    for pi, p in enumerate(pdf.pages):
        if "Table 9 - 1" in (p.extract_text() or ""):
            return pi
    return None

def get_row_top(words, *tokens):
    """定位某数据行的 y 坐标：该行标签包含全部 tokens（同 y 带内）。

    一份 PDF 里 Table 9-1 常出现两处（正文叙述旁的乱版 + 页末干净版），两者标签相同。
    干净版正式表位于页末（top 更大），故优先返回 top 最大的匹配。
    """
    toks = list(tokens)
    best = None
    for w in words:
        if w["text"] == toks[0]:
            rt = w["top"]
            others = [ww for ww in words if abs(ww["top"] - rt) < 6 and ww is not w]
            texts = [ww["text"] for ww in others]
            if all(t in texts for t in toks[1:]):
                if best is None or rt > best:
                    best = rt
    return best

def cluster_centers(xs, tol=18):
    """把数值单词的 x0 聚类成列中心。"""
    xs = sorted(xs)
    clusters = []
    for x in xs:
        if clusters and x - clusters[-1][-1] < tol:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return [sum(c) / len(c) for c in clusters]

def parse_row(words, row_top, centers):
    """按最近列中心把某行的数值单词归列，同列内按 x 顺序拼接（修复 '2,7'+'56'→'2,756'），解析为数字。"""
    rw = [w for w in words
          if abs(w["top"] - row_top) < 6
          and (w["text"][0].isdigit() or (w["text"][0] == "-" and len(w["text"]) > 1 and w["text"][1].isdigit()))]
    by_col = {i: [] for i in range(len(centers))}
    for w in rw:
        best = min(range(len(centers)), key=lambda i: abs(centers[i] - w["x0"]))
        by_col[best].append((w["x0"], w["text"]))
    out = []
    for i in range(len(centers)):
        items = sorted(by_col[i], key=lambda t: t[0])
        text = "".join(t[1] for t in items).replace(" ", "")
        try:
            v = float(text.replace(",", ""))
        except ValueError:
            v = None
        out.append(v)
    return out

def parse_table9_columns(pdf, L):
    """按列位解析干净版 Table 9-1，返回 {crude,total,days} 各为 [L-2, L-1, L] 三值列表。

    列判定：所有数值单词聚类出列中心，最右一列是 Change（排除），其余为库存列；
    库存列按 x 排序后取最右 3 列 = (L-2, L-1, L)。
    """
    pi = find_table9_page(pdf)
    if pi is None:
        return None
    words = pdf.pages[pi].extract_words()
    r_crude = get_row_top(words, "Crude", "oil")
    # Products 行 = 成品油/石化产品等非原油商业库存（IEA 口径 commercial product stocks）。
    # 与 Total 行（= crude + products）的区别：Total 含原油，Products 不含——两者不可混用。
    r_prod = get_row_top(words, "Products")
    r_total = get_row_top(words, "Total")
    r_days = get_row_top(words, "Days", "forward")
    row_tops = [t for t in (r_crude, r_prod, r_total, r_days) if t]
    if not row_tops:
        return None
    # 收集数据行内数值单词的 x0，聚类出列中心
    xs = []
    for w in words:
        if (w["text"][0].isdigit() or (w["text"][0] == "-" and len(w["text"]) > 1 and w["text"][1].isdigit())):
            if any(abs(w["top"] - rt) < 6 for rt in row_tops):
                xs.append(w["x0"])
    centers = cluster_centers(xs)
    if len(centers) < 4:
        return None
    # 最右列为 Change，排除；库存列按 x 排序后取最右 3 列 = (L-2, L-1, L)
    stock_idx = list(range(len(centers) - 1))
    window_idx = stock_idx[-3:] if len(stock_idx) >= 3 else stock_idx  # 指向 centers/vals 的下标

    def rowvals(rt):
        if rt is None:
            return [None] * len(window_idx)
        vals = parse_row(words, rt, centers)
        return [vals[i] if i < len(vals) else None for i in window_idx]

    res = {
        "crude": rowvals(r_crude),
        "products": rowvals(r_prod),
        "total": rowvals(r_total),
        "days": rowvals(r_days),
    }
    # crude 最新月（L）兜底：若列解析缺失，用叙述句
    if res["crude"] and res["crude"][-1] is None:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
        nm = NARR_CRUDE.search(txt)
        if nm and month_num(nm.group(2)) == L[1]:
            res["crude"][-1] = int(nm.group(1).replace(",", ""))
    return res

def main():
    files = sorted(glob.glob(os.path.join(DATA_RAW_OPEC, "*.pdf")),
                   key=lambda f: pub_month(f) or (0, 0))  # 按发布月排序：后发布的月报修订值覆盖先前
    by_month = {}   # (y,m) -> {"crude":, "total":, "days":}
    for f in files:
        pm = pub_month(f)
        if not pm:
            print(f"{os.path.basename(f):30s} SKIP (no pub_month)"); continue
        with require_pdfplumber().open(f) as pdf:
            txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
            mp = PRELIM.search(txt)
            if not mp:
                print(f"{os.path.basename(f):30s} SKIP (no 'preliminary ... data')"); continue
            L = (int(mp.group(2)), month_num(mp.group(1)))
            parsed = parse_table9_columns(pdf, L)
        if not parsed:
            print(f"{os.path.basename(f):30s} SKIP (no clean Table 9-1 / columns)"); continue
        months3 = [prev_month(*L, 2), prev_month(*L, 1), L]
        for key in ("crude", "products", "total", "days"):
            seq = parsed.get(key) or []
            for (y, m), v in zip(months3, seq):
                if v is None:
                    continue
                rec = by_month.setdefault((y, m), {})
                # 库存量级取整；days 保留 1 位小数
                rec[key] = round(v, 1) if key == "days" else int(round(v))
        print(f"{os.path.basename(f):30s} L={month_key(*L)} crude={parsed['crude']} products={parsed.get('products')} total={parsed['total']} days={parsed['days']}")
    keys = sorted(by_month.keys())
    out = {
        "months": [month_key(*k) for k in keys],
        "crude": [by_month[k].get("crude") for k in keys],
        "products": [by_month[k].get("products") for k in keys],
        "total": [by_month[k].get("total") for k in keys],
        "days": [by_month[k].get("days") for k in keys],
        "source": "OPEC MOMR Ch.9 Table 9-1 (IEA-compiled OECD commercial crude/product/total stocks) — 按列位解析干净版正式表；products 行为成品油/石化产品等非原油商业库存（不含原油），total = crude + products",
        "retrieved": datetime.date.today().isoformat(),
    }
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    op = os.path.join(DATA_PROCESSED, "oecd_stocks.json")
    with open(op, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nWrote", op)
    print("months:", out["months"])
    print("crude :", out["crude"])
    print("products:", out["products"])
    print("total :", out["total"])
    print("days  :", out["days"])

if __name__ == "__main__":
    main()
