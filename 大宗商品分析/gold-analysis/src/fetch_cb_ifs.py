#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_cb_ifs.py —— 从 IMF IFS 官方「货币黄金变动」文件刷新央行购金两张表。

数据源：data/Changes_latest_as_of_Sep2026_IFS.xlsx
  · Monthly sheet：行=国家、列=月份  -> 图 2「全球月度净购金」（各月列求和）
  · Annual  sheet：行=国家、列=年份  -> 图 1「各央行净购金量对比」（当年列，
                     取截止今年当月净买入前 N + 净卖出前 N，国家名沿用源表英文）

用法（在 gold-analysis/ 下运行）:
  python3 src/fetch_cb_ifs.py --dry-run     # 只打印结果，不写 Excel
  python3 src/fetch_cb_ifs.py               # 写入 data/gold_data.xlsx
  python3 src/fetch_cb_ifs.py --year 2025   # 指定年份（默认取系统当年）

写入前自动备份到 data/_bak-gold_data-<时间戳>.xlsx。
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
from openpyxl import load_workbook

MONTH_CN = ["", "1 月", "2 月", "3 月", "4 月", "5 月", "6 月",
            "7 月", "8 月", "9 月", "10 月", "11 月", "12 月"]


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _excluded(name):
    for pat, _ in config.IFS_EXCLUDE:
        if re.match(pat, name or ""):
            return True
    return False


def read_ifs(path, year):
    """返回 (monthly, annual)：
       monthly = {"months": [(月份号, 列号)], "data": {name: {月: 值}}, "excluded": {...}}
       annual  = {name: 值}
    """
    wb = load_workbook(path, data_only=True, read_only=True)
    out = {}
    try:
        # ---------- Monthly ----------
        ws = wb["Monthly"]
        rows = list(ws.iter_rows(values_only=True))
        # 兼容两种官方导出格式（取数规则完全一致，仅表头布局不同）：
        #   旧版 Sep2026：元数据行 + A="Country Lookup Column" / B=Country / C=Comments，月份自 index 3
        #   新版 Nov2026：首行即表头 A="Country" / B=Comments，月份自 index 2
        hdr_i, name_col, month_start = None, 1, 3
        for i, r in enumerate(rows):
            a = str(r[0] or "").strip() if r else ""
            if a == "Country Lookup Column":
                hdr_i, name_col, month_start = i, 1, 3
                break
            if a == "Country":
                hdr_i, name_col, month_start = i, 0, 2
                break
        if hdr_i is None:
            raise SystemExit("  ✗ Monthly 表未找到国家列表头（Country Lookup Column / Country）")
        hdr = rows[hdr_i]
        col_month = {}
        for j in range(month_start, len(hdr)):
            h = hdr[j]
            if isinstance(h, (dt.datetime, dt.date)):
                if h.year == year:
                    col_month[h.month] = j
            elif isinstance(h, str):
                m = re.match(r"^([A-Z][a-z]{2})\s+(\d{4})$", h.strip())
                if m and int(m.group(2)) == year:
                    col_month[dt.datetime.strptime(m.group(1), "%b").month] = j
        data, excl = {}, {}
        for r in rows[hdr_i + 1:]:
            if not r or len(r) < 2:
                continue
            name = str(r[name_col] or "").strip()   # 国家名列（旧版 B / 新版 A）= 源表英文简称
            if not name:
                continue
            if _excluded(name):
                excl[name] = next((why for p, why in config.IFS_EXCLUDE if re.match(p, name)), "")
                continue
            vals = {m: (_num(r[j]) if j < len(r) else None) for m, j in col_month.items()}
            if any(v is not None for v in vals.values()):
                data[name] = vals
        out["monthly"] = {"months": sorted(col_month.items()), "data": data, "excluded": excl}

        # ---------- Annual ----------
        ws2 = wb["Annual"]
        rows2 = list(ws2.iter_rows(values_only=True))
        hdr2 = rows2[0]
        year_col = None
        year_cols = {}
        for j in range(2, len(hdr2)):
            v = hdr2[j]
            yy = None
            if isinstance(v, (int, float)):
                yy = int(v)
            elif str(v).strip().isdigit():
                yy = int(str(v).strip())
            if yy is not None:
                year_cols[yy] = j
                if yy == year:
                    year_col = j
        if year_col is None:
            raise SystemExit(f"  ✗ Annual sheet 未找到 {year} 年列（表头: {hdr2[:6]}…）")
        annual, excl2 = {}, dict(excl)
        for r in rows2[1:]:
            if not r or not r[0]:
                continue
            name = str(r[0]).strip()
            if _excluded(name):
                excl2.setdefault(name, "同 Monthly 表剔除项")
                continue
            v = _num(r[year_col] if year_col < len(r) else None)
            if v:
                annual[name] = v
        out["annual"] = annual
        out["annual_excluded"] = excl2
        # 年度全球序列：各年份列求和（与图 1/图 2 同一剔除规则）
        series = {}
        for yy, jj in year_cols.items():
            tot = 0.0
            for r in rows2[1:]:
                if not r or not r[0]:
                    continue
                if _excluded(str(r[0]).strip()):
                    continue
                v = _num(r[jj] if jj < len(r) else None)
                if v:
                    tot += v
            series[yy] = tot
        out["annual_series"] = series
    finally:
        wb.close()
    return out


def build(year, path):
    d = read_ifs(path, year)
    mon = d["monthly"]
    # 截止当月 = 最后一个有数据的月份
    last_m = 0
    for m, _col in mon["months"]:
        if any((mon["data"][n].get(m) or 0) for n in mon["data"]):
            last_m = m
    months = [(m, j) for m, j in mon["months"] if m <= last_m]

    # ---- 图 2：Monthly 各月列求和 ----
    monthly_rows = []
    for m, _ in months:
        total = sum((mon["data"][n].get(m) or 0.0) for n in mon["data"])
        mv = sorted(((mon["data"][n].get(m) or 0.0), n) for n in mon["data"])
        buyer = next((x for x in mv[::-1] if x[0] > 0), (0, "—"))
        seller = next((x for x in mv if x[0] < 0), (0, "—"))
        if buyer[0] > 0:
            b = f"最大买家 {buyer[1]} {buyer[0]:+.1f}t"
        else:
            b = "当月无净买入国"
        if seller[0] < 0:
            s = f"最大卖家 {seller[1]} {seller[0]:+.1f}t"
        else:
            s = "当月无净卖家"
        verb = "净买入" if total > 0 else "净卖出"
        note = f"{year} 年 {m} 月全球央行{verb} {abs(total):.1f}t；{b}；{s}"
        monthly_rows.append((f"{m} 月", round(total, 1), note))

    # ---- 图 1：Annual 当年列，Top N 买家 + Top N 卖家 ----
    annual = d["annual"]
    buyers = sorted(((v, n) for n, v in annual.items() if v > 0), reverse=True)[:config.IFS_TOP_BUYERS]
    sellers = sorted(((v, n) for n, v in annual.items() if v < 0))[:config.IFS_TOP_SELLERS]
    picked = sorted(buyers + sellers, key=lambda t: -t[0])
    country_rows = []
    for v, n in picked:
        series = [(mm, mon["data"].get(n, {}).get(mm)) for mm, _ in months]
        vals = [x for _, x in series if x is not None]
        pos = sum(1 for x in vals if x > 0)
        span = f"{months[0][0]}–{months[-1][0]} 月" if months else "—"
        bits = [f"{span} 合计 {v:+.1f}t"]
        if vals:
            peak = max(vals)
            if peak > 0:
                pm = [mm for mm, x in series if x == peak][0]
                bits.append(f"最大单月买入 {peak:+.1f}t（{pm} 月）")
            pmin = min(vals)
            if pmin < 0:
                sm = [mm for mm, x in series if x == pmin][0]
                bits.append(f"最大单月卖出 {pmin:+.1f}t（{sm} 月）")
        bits.append(f"当月净买入 {pos} 个月" if pos else "期内无净买入月")
        country_rows.append((n, round(v, 1), config.IFS_SOURCE_LABEL, "；".join(bits)))

    # ---- 图 3：Annual 各年份列求和 ----
    series = d.get("annual_series", {})
    annual_rows = []
    for yy in sorted(series):
        if not (2002 <= yy <= year):
            continue
        note = f"截至 {last_m} 月（YTD，非全年）" if yy == year else "年度合计"
        annual_rows.append((yy, round(series[yy], 1), note))

    return {
        "year": year, "last_month": last_m, "monthly": monthly_rows,
        "annual_rows": annual_rows,
        "country": country_rows, "excluded": d.get("annual_excluded", {}),
        "buyers": len(buyers), "sellers": len(sellers),
    }


def write_excel(res, xlsx):
    shutil.copy2(xlsx, os.path.join(
        os.path.dirname(xlsx), "_bak-gold_data-%s.xlsx" % dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
    wb = load_workbook(xlsx)
    ws = wb["央行购金国别"]
    for r in range(2, ws.max_row + 1):
        for c in range(1, 5):
            ws.cell(row=r, column=c).value = None
    for i, row in enumerate(res["country"], start=2):
        for c, v in enumerate(row, start=1):
            ws.cell(row=i, column=c).value = v
    ws2 = wb["央行购金月度"]
    for r in range(2, ws2.max_row + 1):
        for c in range(1, 4):
            ws2.cell(row=r, column=c).value = None
    for i, row in enumerate(res["monthly"], start=2):
        for c, v in enumerate(row, start=1):
            ws2.cell(row=i, column=c).value = v
    ws3 = wb["央行购金年度"]
    for r in range(2, ws3.max_row + 1):
        for c in range(1, 4):
            ws3.cell(row=r, column=c).value = None
    for i, row in enumerate(res["annual_rows"], start=2):
        for c, v in enumerate(row, start=1):
            ws3.cell(row=i, column=c).value = v
    wb.save(xlsx)


def main():
    ap = argparse.ArgumentParser(description="IMF IFS -> 央行购金国别 / 月度")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写 Excel")
    ap.add_argument("--year", type=int, default=dt.date.today().year)
    ap.add_argument("--ifs", default=config.IFS_XLSX)
    args = ap.parse_args()

    if not os.path.exists(args.ifs):
        print(f"  ✗ 未找到 IFS 源文件：{args.ifs}")
        return 1

    res = build(args.year, args.ifs)
    print(f"IFS 源文件：{os.path.basename(args.ifs)}")
    print(f"年份 {res['year']} · 数据覆盖至 {res['last_month']} 月 · "
          f"图 1 选入 买家 {res['buyers']} + 卖家 {res['sellers']} = {len(res['country'])} 国")
    if res["excluded"]:
        print("已剔除行：")
        for k, v in res["excluded"].items():
            print(f"   - {k}：{v}")

    print("\n图 2｜全球央行月度净购金（Monthly 各月列求和，吨）")
    for m, v, _ in res["monthly"]:
        print(f"   {m:>5} {v:+7.1f}")
    print(f"   合计 {sum(v for _, v, _ in res['monthly']):+7.1f}")

    print("\n图 1｜各央行净购金量对比（Annual 当年列，吨）")
    for n, v, _, note in res["country"]:
        print(f"   {n:<44} {v:+7.1f}   {note}")

    print("\n图 3｜全球央行年度净购金（Annual 各年列求和，吨）")
    for yy, v, _ in res["annual_rows"]:
        print(f"   {yy} {v:+8.1f}")

    if args.dry_run:
        print("\n[--dry-run] 未写入 Excel。")
        return 0
    write_excel(res, paths.DATA_XLSX)
    print(f"\n✓ 已写入 {paths.DATA_XLSX}")
    print("  下一步：python3 src/build_html.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
