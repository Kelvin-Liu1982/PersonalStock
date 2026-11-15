#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_gold_monthly.py —— 抓世界银行 Pink Sheet 月度 Gold 参考价，写入 data/gold_data.xlsx。

用途：页面「当前报盘」卡片下方的「当年月度金价」小图。
数据源：World Bank Commodity Price Data (Pink Sheet)
        CMO-Historical-Data-Monthly.xlsx → `Monthly Prices` sheet → `Gold` 列
        单位 USD/troy oz；口径见该文件 Description sheet：
        "Gold, spot average of daily rates, from June 2025; previously (UK), 99.5% fine,
         London afternoon fixing, average of daily rates"
        → 日均价按月平均，**不是**实时现货价，也不是年均价。

取数规则：读全部月份 → 取**最新有值年份**的所有月份（自动跨年，不必改代码）→
          写「黄金月度均价」sheet（月份 YYYY-MM / 月度均价 / 口径说明）。

用法（在 gold-analysis/ 下运行）：
  python3 src/fetch_gold_monthly.py                 抓最新版并写入
  python3 src/fetch_gold_monthly.py --dry-run       只打印，不落盘
  python3 src/fetch_gold_monthly.py --force         强制重下官方 xlsx
  python3 src/fetch_gold_monthly.py --file PATH     用本地 Pink Sheet xlsx（离线）

抓取后需再跑 build_html.py 才会写进 HTML。
"""
import argparse
import datetime
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import excelio
import paths

SHEET = "Monthly Prices"
HEADER_ROW = 5          # 第 5 行为商品名，第 6 行单位，第 7 行起数据
DATA_ROW = 7
NOTE = "世界银行 Pink Sheet Monthly Prices · Gold（$/troy oz，日均价月平均）"


def ensure_source(force=False, local=None):
    """返回可用的 Pink Sheet 月度 xlsx 路径。"""
    if local:
        assert os.path.exists(local), f"本地文件不存在：{local}"
        print(f"  ✓ 使用本地文件 {local}")
        return local
    p = config.CMO_MONTHLY_CACHE
    if os.path.exists(p) and not force:
        print(f"  ✓ 使用缓存 {os.path.basename(p)}（--force 可重下）")
        return p
    try:
        req = urllib.request.Request(config.CMO_MONTHLY_URL,
                                     headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(raw)
        print(f"  ✓ 已下载 {len(raw):,} 字节 -> {p}")
        return p
    except Exception as e:
        if os.path.exists(p):
            print(f"  ! 下载失败（{type(e).__name__}），沿用缓存")
            return p
        raise RuntimeError(f"Pink Sheet 下载失败且无缓存：{e}")


def parse(path):
    """返回 [(YYYY-MM, price_float), ...]（全历史，按月份升序）。"""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb[SHEET]
    gold_col = None
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=HEADER_ROW, column=c).value
        if v and str(v).strip().lower() == "gold":
            gold_col = c
            break
    if gold_col is None:
        raise RuntimeError("未在 Monthly Prices 第 5 行找到 Gold 列")

    out = []
    for r in range(DATA_ROW, ws.max_row + 1):
        tag = ws.cell(row=r, column=1).value
        v = ws.cell(row=r, column=gold_col).value
        if tag is None or v is None or v == "":
            continue
        m = re.match(r"^(\d{4})M(\d{2})$", str(tag).strip())
        if not m:
            continue
        try:
            price = float(v)
        except (TypeError, ValueError):
            continue
        out.append((f"{m.group(1)}-{m.group(2)}", price))
    out.sort()
    return out


def main():
    ap = argparse.ArgumentParser(description="Pink Sheet 月度金价 -> data/gold_data.xlsx")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="强制重下官方 xlsx")
    ap.add_argument("--file", metavar="PATH", help="用本地 Pink Sheet 月度 xlsx")
    args = ap.parse_args()

    excelio.ensure_workbook()
    src = ensure_source(args.force, args.file)
    all_rows = parse(src)
    if not all_rows:
        print("  ✗ 未解析到任何月度数据")
        return 1
    year = all_rows[-1][0][:4]
    rows = [{"month": m, "price": p, "note": NOTE} for m, p in all_rows if m.startswith(year)]
    print(f"  ✓ 官方月度表共 {len(all_rows)} 个月（{all_rows[0][0]} → {all_rows[-1][0]}）")
    print(f"  ✓ 取当年 {year} 年共 {len(rows)} 个月：")
    for r in rows:
        print(f"      {r['month']}  ${r['price']:,.0f}")

    if args.dry_run:
        print("\n[dry-run] 未写入文件")
        return 0
    n = excelio.write_gold_monthly(rows)
    excelio.touch_meta()
    print(f"\n✓ 已写入 {n} 行 -> {paths.DATA_XLSX}「黄金月度均价」")
    print("  下一步：python3 src/build_html.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
