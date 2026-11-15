#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_gdt.py —— 从 WGC《Gold Demand Trends》季度表刷新「黄金供需季度」sheet。

数据源：data/GDT_Tables_Q2'26_EN.xlsx → sheet「Gold Balance」
  · 结构：第 22 列（0-based 21）为行标签（带缩进空格），第 23 列起为季度列（Q1'10 – Q2'26）
  · 需求口径：Jewellery Fabrication / Technology / Investment / Central Bank and Other Institutions
  · 供应口径：Mine Production / Net Producer Hedging / Total Mine Supply / Recycled Gold

用法：
  python3 src/fetch_gdt.py --dry-run    # 只打印
  python3 src/fetch_gdt.py              # 写入 data/gold_data.xlsx（自动备份）
  python3 src/fetch_gdt.py --quarters 20
"""
import argparse
import datetime as dt
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import paths
import schema
from openpyxl import load_workbook

# 源表行标签（用前缀匹配，避开缩进空格）→ 输出列 key
ROW_MAP = [
    ("Total Supply", "src_supply_total"),
    ("Mine Production", "mine"),
    ("Net Producer Hedging", "hedging"),
    ("Total Mine Supply", "mine_total"),
    ("Recycled Gold", "recycled"),
    ("Total Demand", "src_demand_total"),
    ("Jewellery Fabrication", "jewellery"),
    ("Technology", "technology"),
    ("Investment", "investment"),
    ("Central Bank and Other Institution", "cb"),
    ("Gold Demand", "gold_demand"),
    ("OTC and other", "otc"),
]
NEED_KEYS = ["jewellery", "technology", "investment", "cb"]
SUPPLY_KEYS = ["mine", "hedging", "mine_total", "recycled"]

# 中文版源表（WGC 中文《黄金供需》）行标签 → 与英文版相同的 key，取数规则一致。
ROW_MAP_ZH = [
    ("总供应量", "src_supply_total"),
    ("金矿产量", "mine"),
    ("生产商净套保", "hedging"),
    ("金矿总产量", "mine_total"),
    ("回收金", "recycled"),
    ("总需求量", "src_demand_total"),
    ("金饰制造", "jewellery"),
    ("科技", "technology"),
    ("投资", "investment"),
    ("各央行和官方机构", "cb"),
    ("黄金需求量", "gold_demand"),
    ("场外投资及其他", "otc"),
]
SHEET_CANDIDATES = ["Gold Balance", "黄金供需"]

_QRE_EN = re.compile(r"^Q\d'\d{2}$")
_QRE_ZH = re.compile(r"^(\d{4})年([一二三四])季度$")
_CN_Q = {"一": 1, "二": 2, "三": 3, "四": 4}


def norm_quarter(c):
    """把两种季度表头统一成 Qn'yy：Q1'10 / 2010年一季度 -> Q1'10。非季度列返回 None。"""
    if not isinstance(c, str):
        return None
    s = c.strip()
    if _QRE_EN.match(s):
        return s
    m = _QRE_ZH.match(s)
    if m:
        return "Q%d'%s" % (_CN_Q[m.group(2)], m.group(1)[2:])
    return None


def read_gdt(path, quarters):
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        sheet = next((s for s in SHEET_CANDIDATES if s in wb.sheetnames), None)
        if sheet is None:
            raise SystemExit("  ✗ 源表缺少工作表：" + " / ".join(SHEET_CANDIDATES))
        rows = list(wb[sheet].iter_rows(values_only=True))
    finally:
        wb.close()
    is_zh = sheet == "黄金供需"

    # 季度表头行：首个含 Q1'10 / 2010年一季度 之类单元格的行；表头名统一为 Qn'yy
    hdr_i = None
    for i, r in enumerate(rows):
        if r and any(norm_quarter(c) for c in r):
            hdr_i = i
            break
    if hdr_i is None:
        raise SystemExit("  ✗ 未找到季度表头行")
    cols = [(j, norm_quarter(c)) for j, c in enumerate(rows[hdr_i])
            if norm_quarter(c)]
    # 去重（中文版同表既有年度列也有季度列，季度表头只认带"季度"的；以防万一保留首个）
    seen = set()
    cols = [(j, q) for j, q in cols if not (q in seen or seen.add(q))]

    # 行标签 → 行号（标签列 = 季度首列 - 1）
    lab_col = cols[0][0] - 1
    row_map = ROW_MAP_ZH if is_zh else ROW_MAP
    lab = {}
    for i, r in enumerate(rows):
        v = r[lab_col] if lab_col < len(r) else None
        if not isinstance(v, str):
            continue
        s = v.strip()
        for name, key in row_map:
            if s.startswith(name) and key not in lab:
                lab[key] = i
    missing = [k for _, k in row_map if k not in lab]
    if missing:
        raise SystemExit("  ✗ 源表缺少行：" + "、".join(missing))

    def cell(key, j):
        v = rows[lab[key]][j] if j < len(rows[lab[key]]) else None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    data = []
    for j, q in cols:
        rec = {"quarter": q}
        ok = False
        for _, key in ROW_MAP:
            rec[key] = cell(key, j)
            if key in NEED_KEYS + SUPPLY_KEYS and rec[key] is not None:
                ok = True
        if not ok:
            continue
        # 合计（源表四舍五入后相加可能与官方 Total 差 ~1t，故自行汇总并保留源表值备用）
        d = [rec.get(k) or 0.0 for k in NEED_KEYS]
        s = (rec.get("mine_total") or 0.0) + (rec.get("recycled") or 0.0)
        rec["demand_sum"] = round(sum(d), 1)
        rec["supply_sum"] = round(s, 1)
        data.append(rec)
    data.sort(key=lambda r: _qkey(r["quarter"]))
    return data[-quarters:] if quarters and quarters > 0 else data


def _qkey(q):
    m = re.match(r"^Q(\d)'(\d{2})$", q)
    return (2000 + int(m.group(2)), int(m.group(1))) if m else (0, 0)


def to_rows(data):
    out = []
    for r in data:
        out.append((
            r["quarter"],
            round(r.get("jewellery") or 0.0, 1),
            round(r.get("technology") or 0.0, 1),
            round(r.get("investment") or 0.0, 1),
            round(r.get("cb") or 0.0, 1),
            r["demand_sum"],
            round(r.get("mine") or 0.0, 1),
            round(r.get("hedging") or 0.0, 1),
            round(r.get("mine_total") or 0.0, 1),
            round(r.get("recycled") or 0.0, 1),
            r["supply_sum"],
        ))
    return out


def write_excel(rows, xlsx):
    shutil.copy2(xlsx, os.path.join(
        os.path.dirname(xlsx), "_bak-gold_data-%s.xlsx" % dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
    wb = load_workbook(xlsx)
    if schema.SHEET_GDT in wb.sheetnames:
        ws = wb[schema.SHEET_GDT]
    else:
        ws = wb.create_sheet(schema.SHEET_GDT)
        for c, h in enumerate(schema.HEAD_GDT, start=1):
            ws.cell(row=1, column=c).value = h
    for r in range(2, ws.max_row + 1):
        for c in range(1, len(schema.HEAD_GDT) + 1):
            ws.cell(row=r, column=c).value = None
    for i, row in enumerate(rows, start=2):
        for c, v in enumerate(row, start=1):
            ws.cell(row=i, column=c).value = v
    wb.save(xlsx)


def main():
    ap = argparse.ArgumentParser(description="WGC GDT Gold Balance -> 黄金供需季度")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quarters", type=int, default=config.GDT_QUARTERS)
    ap.add_argument("--gdt", default=config.GDT_XLSX)
    args = ap.parse_args()

    if not os.path.exists(args.gdt):
        print(f"  ✗ 未找到 GDT 源文件：{args.gdt}")
        return 1

    data = read_gdt(args.gdt, args.quarters)
    rows = to_rows(data)
    print(f"源文件：{os.path.basename(args.gdt)} · 取最近 {len(rows)} 个季度（{rows[0][0]} – {rows[-1][0]}）")
    print("\n季度      金饰    科技   投资    央行  | 需求合计 |矿产  套保  矿产合计 回收 | 供应合计")
    for r in rows:
        print("%-7s %7.1f %6.1f %6.1f %6.1f | %8.1f |%6.1f %6.1f %8.1f %6.1f | %8.1f"
              % (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]))

    last, prev = rows[-1], rows[-5] if len(rows) >= 5 else rows[0]
    dy = (last[5] / prev[5] - 1) * 100 if prev[5] else 0
    gap = last[5] - last[10]
    print(f"\n最新季度 {last[0]}：需求 {last[5]:.1f}t · 供应 {last[10]:.1f}t · 缺口 {gap:+.1f}t · 需求同比 {dy:+.1f}%")

    if args.dry_run:
        print("\n[--dry-run] 未写入 Excel。")
        return 0
    write_excel(rows, paths.DATA_XLSX)
    print(f"\n✓ 已写入 {paths.DATA_XLSX} → sheet「{schema.SHEET_GDT}」")
    print("  下一步：python3 src/build_html.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())