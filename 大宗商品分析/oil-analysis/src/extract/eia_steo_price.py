# -*- coding: utf-8 -*-
"""从本地 data/raw/eia_steo/ 的各期 STEO PDF 提取「Table 2. Energy Prices」的原油价格预测。

权威源 = 每期 PDF 数据表区的 **Table 2. Energy Prices** → Crude Oil (dollars per barrel) 段：
    West Texas Intermediate Spot Average
    Brent Spot Average
取该段的**季度列（2025Q1–2027Q4）+ 年度列（2025 / 2026 / 2027）**，每期 PDF 一行。

为什么要按 PDF 而不是 xlsx：`data/raw/eia_steo/oct26_base.xlsx` 只有**最新一期**，
而本脚本要的是**逐月期次矩阵**（2026-01 ~ 2026-10 共 10 期），只能从各期 PDF 的表 2 取。
xlsx 的 2tab 与 PDF 表 2 口径一致（10 月期 Brent 年均 84.00 vs PDF 83.74，差 ≤0.26），
两源可互校，但矩阵本身以 PDF 为准（PDF 才有历史期次）。

产出 data/processed/eia_steo_price.json：
    {vintages: [...], brent: {期次: {2025Q1..2027Q4, Y2025, Y2026, Y2027}},
     wti: {...}, source, meta}

注入 data/dataset/ 由 src/pipeline/build_dataset.py 的 _offline_outlook() 负责，
本模块不写域数据。

用法：
    python src/extract/eia_steo_price.py            # 提取并写出 processed json（同时打印 diff）
    python src/extract/eia_steo_price.py --quiet    # 只写文件不打印
"""
import argparse
import glob
import json
import os
import re
import sys

if __package__ in (None, ""):  # 直接 python 跑脚本时补 sys.path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import src.paths as paths  # noqa: E402
from src.common.deps import require_pymupdf  # noqa: E402

fitz = require_pymupdf()  # 缺依赖时按约定打印指引并以退出码 3 退出

RAW_DIR = os.path.join(paths.DATA_RAW, "eia_steo")
OUT_JSON = os.path.join(paths.DATA_PROCESSED, "eia_steo_price.json")

# 表 2 的两条原油价格行（顺序即表内顺序）
SERIES = [
    ("West Texas Intermediate Spot Average", "wti"),
    ("Brent Spot Average", "brent"),
]
# 季度列 + 年度列的顺序：表头为 2025 Q1..Q4 / 2026 Q1..Q4 / 2027 Q1..Q4 / 2025 / 2026 / 2027
QUARTER_KEYS = ["%dQ%d" % (y, q) for y in (2025, 2026, 2027) for q in (1, 2, 3, 4)]
YEAR_KEYS = ["2025", "2026", "2027"]
NEED = len(QUARTER_KEYS) + len(YEAR_KEYS)  # 15

# steo_jan26.pdf → 2026-01
FILE_VINTAGE = re.compile(r"^steo_([a-z]{3})(\d{2})\.pdf$", re.IGNORECASE)
MONTHS = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
          "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _extract_series(doc, title):
    """在 PDF 里找 `title` 所在行，取其后的 NEED 个数值。

    返回 {quarter_key: v, "Y2025": v, ...}；找不到返回 None。
    注意：行名后紧跟的数值就是该行数据（表内无跨行折行），但为了防止把
    单位说明里的数字卷进来，只取该行及其后若干行里**前 NEED 个纯数值 token**。
    """
    for pno in range(doc.page_count):
        lines = [ln.strip() for ln in doc[pno].get_text().split("\n")]
        hit = [i for i, ln in enumerate(lines) if title in ln]
        if not hit:
            continue
        i = hit[0]
        nums = []
        for ln in lines[i:i + 60]:
            # 跳过行名自身与省略号（表 2 里行名后跟一串 "."）
            for tok in NUM_RE.findall(ln.replace(",", "")):
                nums.append(float(tok))
                if len(nums) >= NEED:
                    break
            if len(nums) >= NEED:
                break
        if len(nums) < NEED:
            continue
        out = {}
        for j, qk in enumerate(QUARTER_KEYS):
            out[qk] = nums[j]
        for j, yk in enumerate(YEAR_KEYS):
            out["Y" + yk] = nums[len(QUARTER_KEYS) + j]
        return out
    return None


def extract_all(quiet=False):
    files = sorted(glob.glob(os.path.join(RAW_DIR, "steo_*.pdf")))
    if not files:
        print("[steo_price] %s 下没有 steo_*.pdf" % RAW_DIR)
        return None
    vintages, brent, wti = [], {}, {}
    for f in files:
        m = FILE_VINTAGE.match(os.path.basename(f))
        if not m:
            continue
        vint = "20%s-%s" % (m.group(2), MONTHS[m.group(1).lower()])
        doc = fitz.open(f)
        rec = {}
        for title, tag in SERIES:
            rec[tag] = _extract_series(doc, title)
        doc.close()
        if rec["brent"] is None or rec["wti"] is None:
            print("[steo_price] %s：未取到 Brent/WTI 价格行，跳过" % os.path.basename(f))
            continue
        vintages.append(vint)
        brent[vint] = rec["brent"]
        wti[vint] = rec["wti"]
    if not vintages:
        return None
    order = sorted(vintages)
    return {
        "vintages": order,
        "brent": {k: brent[k] for k in order},
        "wti": {k: wti[k] for k in order},
        "source": ("数据：取自 EIA《STEO》「Table 2. Energy Prices」Crude Oil (dollars per barrel) 段的 "
                   "Brent Spot Average / West Texas Intermediate Spot Average 行。"),
        "meta": {
            "extractedFrom": "%d 期 STEO PDF（%s ~ %s）" % (len(order), order[0], order[-1]),
            "frequency": "月度发布（比 IMF WEO 的季度更细）",
            "latest": order[-1],
            "quarterKeys": QUARTER_KEYS,
            "口径": ("EIA = Brent 现货（单一品种）；IMF WEO = Brent+Dubai+WTI 三品种简单平均。"
                     "两者差 1~14 美元，横向对照时不可直接混线，只能比修订路径。"),
            "note": ("⚠️ 2025Q1–2026Q2 在多数期次里已是历史值（各期 PDF 的 Historical 边界不同），"
                     "把它当'预测'读会高估机构的先见之明；只有 forecast 段才是真预测。"),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    data = extract_all(quiet=args.quiet)
    if not data:
        sys.exit(1)

    os.makedirs(paths.DATA_PROCESSED, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    if args.quiet:
        return
    v = data["vintages"]
    print("[steo_price] 期次 %d 个：%s ~ %s" % (len(v), v[0], v[-1]))
    print("[steo_price] Brent 年度预测逐期（2026 / 2027）：")
    for k in v:
        print("   %s  %6.2f  %6.2f" % (k, data["brent"][k]["Y2026"], data["brent"][k]["Y2027"]))
    b = data["brent"][v[-1]]
    print("[steo_price] 最新期 %s 季度 Brent：%s" % (
        v[-1], " / ".join("%s %.2f" % (q, b[q]) for q in QUARTER_KEYS[-4:])))
    print("[steo_price] 已写出 %s" % OUT_JSON)


if __name__ == "__main__":
    main()
