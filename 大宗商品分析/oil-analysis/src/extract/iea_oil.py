# -*- coding: utf-8 -*-
""""从本地 data/raw/iea_oil/ 的 PDF 提取《Oil 20XX》中期需求展望的逐年需求水平。

权威源 = 各版「Demand」章的全球需求表：

    Global oil demand by product (mb/d), 2019-2028      （Oil 2023，p13/0-based p12）
    World oil demand by product (mb/d), 2019-2030       （Oil 2024，p14/0-based p13）
    World oil demand by product, 2019-2030 (mb/d)       （Oil 2025，p15/0-based p14）

取该表的 **Total products** 行 —— 全球石油总需求水平（mb/d）。
注意：2024/2025 版的标题把 Global 改成了 World，但仍是同一张表、同一行；
页内另有一张「Growth in world oil demand by product」图，不含 Total products 行，
本脚本按「标题后 N 字符内必须出现 Total products」判别，不会误取。

逐年数值取表内原值（2019 起的整列表），**不是**按累计增量线性插值的示意路径。

用法：
    python src/extract/iea_oil.py                 # 与 data/dataset/iea_forecast.json 对照 diff
    python src/extract/iea_oil.py --write         # 回写 dataset（只动 3 条 outlook 序列）
    python src/extract/iea_oil.py --json out.json # 另存纯提取结果
"""
import argparse
import json
import os
import re
import sys

if __package__ in (None, ""):  # 直接 python 跑脚本时补 sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import src.paths as paths  # noqa: E402
from src.common.deps import require_pymupdf  # noqa: E402

fitz = require_pymupdf()  # 缺依赖时按约定打印指引并以退出码 3 退出

# 图表 x 轴固定窗口（与 ieaOutlookYears 一致），序列对齐后长度固定
WIN_START = 2022
WIN_LEN = 9          # 2022 … 2030
SERIES_KEY = {"2023": "ieaOutlook2023", "2024": "ieaOutlook2024", "2025": "ieaOutlook2025"}

TITLE_RE = re.compile(r"(?:Global|World)\s+oil demand by product")
YEAR_RE = re.compile(r"^20\d\d$")
GROWTH_RE = re.compile(r"^\d{4}-\d{2}$")
NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

# 文件名 → 展望版次（ Oil2023.pdf → "2023"）
FILE_EDITION = re.compile(r"Oil(\d{4})\.pdf$", re.IGNORECASE)


def _page_lines(doc, idx):
    return [ln.strip() for ln in doc[idx].get_text().split("\n")]


def _years_above(lines, k):
    """从 'Total products' 行（下标 k）向上回溯年份列。

    年份列通常离表格主体百余行，回溯时把途中遇到的表头增长区间标签（如 “2023-30”）
    一并认领，用它推导各版展望的起点年（该版 forecasts 覆盖的整年窗口）。
    返回 (年份列表, 增长区间字符串)。
    """
    years, j = [], k - 1
    while j >= 0 and len(years) < 12 and (k - j) < 320:
        toks = lines[j].split()
        if toks and all(YEAR_RE.match(t) for t in toks):
            years.extend(int(t) for t in toks)
            j -= 1
            continue
        if years:  # 已吃到年份列，再遇非年份行即止
            break
        # 年份列之前还有产品行/表头（如 “2022-28 Growth Rate 2022-28 Growth”），先往上跳，
        # 顺手认领增长区间标签（7 字符，如 2023-30），它决定各版展望的起点年。
        if toks and GROWTH_RE.match(toks[0]) and len(toks[0]) == 7:
            growth = toks[0]
        j -= 1
    return sorted(years), growth


def _values_below(lines, k, n):
    """从 'Total products' 行（下标 k）向下取 n 个数值。"""
    vals = []
    for line in lines[k + 1:k + 1 + n + 4]:
        toks = line.split()
        if not toks or not all(NUM_RE.match(t) for t in toks):
            if vals:
                break
            continue
        vals.extend(float(t) for t in toks)
        if len(vals) >= n:
            break
    return vals[:n]


def parse_pdf(path):
    """返回 [{edition, page, title, years, values}]，每版一张表。"""
    doc = fitz.open(path)
    out = []
    for idx in range(len(doc)):
        lines = _page_lines(doc, idx)
        for i, line in enumerate(lines):
            m = TITLE_RE.search(line)
            if not m:
                continue
            # 页内可能另有构图标题（Growth in world oil demand by product），其下无 Total products 行 → 跳过
            if not any(lines[j] == "Total products" for j in range(i + 1, min(i + 200, len(lines)))):
                continue
            k = next(j for j in range(i + 1, len(lines)) if lines[j] == "Total products")
            years, growth = _years_above(lines, k)
            if not years or len(years) < 8:
                continue
            vals = _values_below(lines, k, len(years))
            if len(vals) != len(years):
                continue
            out.append({
                "edition": None, "page": doc[idx].number + 1, "title": line.strip(),
                "years": years, "growth": growth,
                "start": int(growth.split("-")[0]) if growth else min(years),
                "values": {str(y): v for y, v in zip(years, vals)},
            })
    doc.close()
    return out


def align(years_values, start=WIN_START, length=WIN_LEN):
    """按图表窗口（WIN_START 起）对齐，缺失年份填 None（图表 connectNulls:false）。

    start = 各表自己的增长区间首年（2022-28 / 2023-30 / 2024-30），即该版展望真正覆盖的
    起点；早于该起点的年份（上一版口径下的历史年）一律置空，不灌进预测线。
    对齐基准始终是 WIN_START，保证返回的数组下标与 ieaOutlookYears 严格对应。
    """
    arr = [None] * length
    for y, v in years_values.items():
        if int(y) < start:
            continue
        off = int(y) - WIN_START
        if 0 <= off < length:
            arr[off] = v
    return arr


def scan():
    """扫描 data/raw/iea_oil/ 下全部 PDF，返回 {edition: {...}}。"""
    res = {}
    for fn in sorted(os.listdir(paths.DATA_RAW_IEA_OIL)):
        m = FILE_EDITION.search(fn)
        if not m:
            continue
        ed = m.group(1)
        for t in parse_pdf(os.path.join(paths.DATA_RAW_IEA_OIL, fn)):
            t["edition"] = ed
            res[ed] = t
    return res


def load_dataset():
    with open(os.path.join(paths.DATASET_DIR, "iea_forecast.json"), encoding="utf-8") as f:
        return json.load(f)


def diff(scan_res, ds):
    lines = []
    for ed in sorted(SERIES_KEY):
        t = scan_res.get(ed)
        if not t:
            lines.append("[%s] 未在 PDF 中找到表" % ed)
            continue
        new = align(t["values"], t["start"])
        key = SERIES_KEY[ed]
        old = ds.get(key, [])
        lines.append("[Oil %s] p%d · %s · 表内增长区间 %s → 起点 %d"
                     % (ed, t["page"], t["title"], t["growth"] or "(未识别)", t["start"]))
        for off, y in enumerate(range(WIN_START, WIN_START + WIN_LEN)):
            o = old[off] if off < len(old) else None
            n = new[off]
            flag = "" if o == n else "   <-- 改"
            lines.append("    %d  pdf=%s  ds=%s%s" % (y, "null" if n is None else n, "null" if o is None else o, flag))
    return "\n".join(lines)


def write_dataset(scan_res, ds):
    for ed, key in SERIES_KEY.items():
        t = scan_res.get(ed)
        if not t:
            print("[skip] Oil %s 未在 PDF 中找到表" % ed)
            continue
        ds[key] = align(t["values"], t["start"])
    path = os.path.join(paths.DATASET_DIR, "iea_forecast.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ds, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("[write] %s" % path)


def main():
    ap = argparse.ArgumentParser(description="从 data/raw/iea_oil 本地 PDF 提取《Oil 20XX》逐年需求")
    ap.add_argument("--write", action="store_true", help="回写 data/dataset/iea_forecast.json（仅 3 条 outlook 序列）")
    ap.add_argument("--json", dest="json_out", help="另存纯提取结果到指定路径")
    args = ap.parse_args()

    res = scan()
    if not res:
        print("未找到任何 PDF：%s" % paths.DATA_RAW_IEA_OIL)
        return 1

    print(diff(res, load_dataset()))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({k: {kk: vv for kk, vv in v.items() if kk != "edition"} for k, v in res.items()},
                      f, ensure_ascii=False, indent=2)
        print("[write] %s" % args.json_out)
    if args.write:
        write_dataset(res, load_dataset())
    return 0


if __name__ == "__main__":
    sys.exit(main())
