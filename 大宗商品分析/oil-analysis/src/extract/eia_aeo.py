# -*- coding: utf-8 -*-
"""从 data/raw/eia_aeo/AEO20XX_Narrative_Figures.xlsx 提取 EIA 中长期美国液体燃料消费路径。

权威源 = AEO2026 的官方配套工作簿「Narrative Figures」中的
**sheet `14_RefinThruPut` 第二块：「U.S. total product supplied」**：

    Series = PSD000:fa_Total      单位 million barrels per day
    列      = 2010 … 2050（逐年）
    行      = 11 个情景（Counterfactual Baseline / Alt Transportation / Low ZTC …）

这就是听报告里「petroleum and other liquids」所指的那条量——用 narrative p14 的
「Alternative Transportation 情形 2050 液体燃料消费比 Counterfactual Baseline 高 3 mb/d」
反证：xlsx 里 20.0516 − 17.1240 = 2.93 ≈ 3，口径吻合。

⚠️ 历史教训（2026-10-06）：此前本卡用的是「narrative 原话『2050 较 2025 下降 11%–23%』×
   2025 基准 20.6」折算出的 18.3 / 15.9，属于自己算的推导值，不是 EIA 模型输出。
   同时发现该 11%–23% 区间与官方表内任何一个情景都对不上（情景实际散布 −1.8% … −21.5%），
   所以现在改成直接取官方逐年原值，推导值全部下架。

用法：
    python src/extract/eia_aeo.py                  # 读 xlsx 并与 data/dataset/eia_forecast.json 对照
    python src/extract/eia_aeo.py --write          # 回写 dataset（年份 / 上界 / 基准 / 下界 / 情景名）
    python src/extract/eia_aeo.py --json out.json  # 另存整张表（逐年 × 11 情景）为纯结果
    python src/extract/eia_aeo.py --all            # 同时扫同目录的 AEO_20XX.pdf 找区间原话（可选）
"""
import argparse
import json
import os
import re
import sys

if __package__ in (None, ""):  # 直接 python 跑脚本时补 sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import src.paths as paths  # noqa: E402
from src.common.deps import require_openpyxl  # noqa: E402

openpyxl = require_openpyxl()

# ---- 取数口径 ------------------------------------------------------------------
BLOCK_TITLE = "U.S.total product supplied"   # xlsx 里标题就是这串（TOTAL 小写、无空格）
UNIT_RE = re.compile(r"million barrels per day", re.I)
# 图表 x 轴：官方表给的是 2010–2050 逐年 41 个点，看板只画这几个等距年份
PLOT_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
# 上/下界情景：看板把 11 个情景压成「扇面 + 三条线」。
# 上/下界取 **宏观增长同一维度的一对**（High / Low Economic Growth），而不是「2050 极值对」——
# 极值会把上界给需求侧政策组合 Combination（20.11）、下界给 Low EG，上下界不同维度，图例读起来像一根轴的两端其实不是。
# High EG / Low EG 是本组里唯一横跨基准两侧、两侧都显著（2050 +1.48 / −1.06）的单一维度对称对，带宽 2.54 mb/d。
# 第三条是 EIA 自己的基准情景。三者都是官方表内的真实情景，不是插值。
# ⚠️ 若改回极值口径：--case-high "Combination" 即可（下界仍为 Low Economic Growth）。
CASE_HIGH, CASE_LOW, CASE_BASE = "High Economic Growth", "Low Economic Growth", "Counterfactual Baseline"
# 交叉校验用的原话（narrative「Alt Transportation 比 Counterfactual Baseline 高 3 mb/d」）
CHECK_DELTA_TOL = 0.2


def _cell(row, i):
    return row[i] if i < len(row) else None


def load_workbook(path):
    """返回 {sheet_name: [[cell, ...], ...]}（只读、带公式结果）。"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        out[ws.title] = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return out


def find_block(rows, title=BLOCK_TITLE):
    """定位「U.S.total product supplied」块，返回 (header_row_index, {col: year})。"""
    for i, r in enumerate(rows):
        if not any(isinstance(c, str) and c.strip() == title for c in r):
            continue
        # 往后找含「Series / Case」且带年份列的表头行
        for j in range(i + 1, min(i + 5, len(rows))):
            hr = rows[j]
            if _cell(hr, 10) != "Series" or _cell(hr, 11) != "Case":
                continue
            years = {}
            for c, v in enumerate(hr):
                if isinstance(v, int) and v >= 2000:
                    years[c] = int(v)
            if years:
                return j, years
        return None, {}
    return None, {}


def extract_series(rows, header_i, years):
    """按表头年份列取值；返回 {case_name: {year: value}}。"""
    out = {}
    for r in rows[header_i + 1:]:
        series, case = _cell(r, 10), _cell(r, 11)
        if not isinstance(series, str) or not isinstance(case, str):
            continue
        if not series.startswith("PSD000"):
            continue
        vals = {}
        for col, y in years.items():
            v = _cell(r, col)
            if isinstance(v, (int, float)):
                vals[y] = round(float(v), 2)
        if vals:
            out[case] = vals
    return out


def sample(case_vals, case, years=PLOT_YEARS):
    return [case_vals.get(case, {}).get(y) for y in years]


def scan_pdf_range(path):
    """可选：从 narrative PDF 里抓「2050 较 BASE 年下降 X%–Y%」原话。PDF 缺失时返回 None。"""
    from src.common.deps import require_pymupdf  # 仅在 --all 时才真正导入
    fitz = require_pymupdf()
    rng = re.compile(
        r"decrease[sd]?\s+by\s+(\d{1,2})\s*%\s*[\u2013\-]\s*(\d{1,2})\s*%[^.]{0,160}?"
        r"in\s+(\d{4})\s+compared with\s+(\d{4})", re.I)
    doc = fitz.open(path)
    hits = []
    for idx in range(doc.page_count):
        t = doc[idx].get_text()
        for m in rng.finditer(t):
            ctx = t[max(0, m.start() - 160):m.end() + 60].lower()
            if re.search(r"(petroleum|liquid|oil)", ctx):
                hits.append({"page": idx + 1, "text": " ".join(m.group(0).split())})
    doc.close()
    return hits


def main():
    ap = argparse.ArgumentParser(description="从 AEO Narrative Figures xlsx 提取美国液体燃料消费路径")
    ap.add_argument("--write", action="store_true", help="回写 data/dataset/eia_forecast.json")
    ap.add_argument("--json", dest="json_out", help="另存逐年提取结果为指定路径")
    ap.add_argument("--case-high", default=CASE_HIGH, help="上界情景名（默认 %s）" % CASE_HIGH)
    ap.add_argument("--case-low", default=CASE_LOW, help="下界情景名（默认 %s）" % CASE_LOW)
    ap.add_argument("--case-base", default=CASE_BASE, help="基准情景名（默认 %s）" % CASE_BASE)
    ap.add_argument("--all", action="store_true", help="同时扫同目录 AEO PDF 找区间原话（可选）")
    args = ap.parse_args()

    if not os.path.isdir(paths.DATA_RAW_EIA_AEO):
        print("目录不存在：%s" % paths.DATA_RAW_EIA_AEO)
        return 1

    sheets = {}
    for fn in sorted(os.listdir(paths.DATA_RAW_EIA_AEO)):
        if not fn.lower().endswith(".xlsx") or fn.startswith("~$"):
            continue
        sheets.update(load_workbook(os.path.join(paths.DATA_RAW_EIA_AEO, fn)))

    if "14_RefinThruPut" not in sheets:
        print("未找到 sheet 14_RefinThruPut —— 目录里没有 AEO2026 Narrative Figures 工作簿？")
        print("（现有：%s）" % ", ".join(sorted(sheets)))
        return 1

    rows = sheets["14_RefinThruPut"]
    h_i, years = find_block(rows)
    if h_i is None:
        print("未在 14_RefinThruPut 里定位到「%s」块" % BLOCK_TITLE)
        return 1

    cases = extract_series(rows, h_i, years)
    print("块定位：14_RefinThruPut 第 %d 行为表头，年份列 %d…%d" % (h_i + 1, min(years.values()), max(years.values())))
    print("情景数 %d：%s" % (len(cases), " / ".join(sorted(cases))))

    hi, lo, bs = args.case_high, args.case_low, args.case_base
    for c in (hi, lo, bs):
        if c not in cases:
            print("情景名不在表里：%s；可用 %s" % (c, sorted(cases)))
            return 1

    base = cases[hi].get(PLOT_YEARS[0])
    print("\n口径 = PSD000:fa_Total「U.S. total product supplied」（百万桶/日，逐年官方原值）")
    print("%-24s %s" % ("情景", " → ".join(str(y) for y in PLOT_YEARS)))
    for c in (hi, lo, bs):
        print("%-24s %s" % ("%s ★" % c if c == bs else c, " → ".join("%.2f" % v for v in sample(cases, c))))

    # 交叉校验：Alt Transportation − Counterfactual Baseline ≈ 报告里的 3 mb/d
    alt, cbf = cases.get("Alt Transportation", {}).get(2050), cases.get("Counterfactual Baseline", {}).get(2050)
    if alt and cbf and abs((alt - cbf) - 3) <= CHECK_DELTA_TOL:
        print("\n交叉校验 ✓ 2050 Alt Transportation − Counterfactual Baseline = %.2f mb/d"
              "（报告叙事称「高 3 mb/d」）→ 口径确认无误" % (alt - cbf))
    else:
        print("\n交叉校验 ✗ Alt Transportation − Counterfactual Baseline = %s（应≈3）"
              % (None if not (alt and cbf) else round(alt - cbf, 2)))

    # --all：可选地看一眼 PDF 原话，用来解释「为什么不再折百分比」
    if args.all:
        print("\n[AEO PDF 原话扫描（可选）]")
        import re as _re
        pdfs = [f for f in sorted(os.listdir(paths.DATA_RAW_EIA_AEO)) if f.lower().endswith(".pdf")]
        if not pdfs:
            print("  目录里没有 AEO PDF，跳过")
        for f in pdfs:
            for h in scan_pdf_range(os.path.join(paths.DATA_RAW_EIA_AEO, f)):
                print("  %s p%d：%s" % (f, h["page"], h["text"][:150]))

    ds_path = os.path.join(paths.DATASET_DIR, "eia_forecast.json")
    with open(ds_path, encoding="utf-8") as f:
        ds = json.load(f)
    print("\n看板现状：years=%s\n            high=%s（%s）\n            base=%s（%s）\n            low =%s（%s）"
          % (ds.get("eiaAeoYears", []), ds.get("eiaAeoConsHigh", []), ds.get("eiaAeoCaseHigh", ""),
             ds.get("eiaAeoConsBase", []), ds.get("eiaAeoCaseBase", ""),
             ds.get("eiaAeoConsLow", []), ds.get("eiaAeoCaseLow", "")))

    new_y, new_h, new_b, new_l = PLOT_YEARS, sample(cases, hi), sample(cases, bs), sample(cases, lo)
    print("将改为：years=%s\n          high=%s（%s）\n          base=%s（%s）\n          low =%s（%s）"
          % (new_y, new_h, hi, new_b, bs, new_l, lo))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)
        print("\n[write] %s（逐年 × 情景）" % args.json_out)

    if args.write:
        ds["eiaAeoYears"] = new_y
        ds["eiaAeoConsHigh"] = new_h
        ds["eiaAeoConsBase"] = new_b
        ds["eiaAeoConsLow"] = new_l
        ds["eiaAeoCaseHigh"] = hi
        ds["eiaAeoCaseBase"] = bs
        ds["eiaAeoCaseLow"] = lo
        with open(ds_path, "w", encoding="utf-8") as f:
            json.dump(ds, f, ensure_ascii=False, indent=2)
        print("\n[write] 已更新 %s" % ds_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
