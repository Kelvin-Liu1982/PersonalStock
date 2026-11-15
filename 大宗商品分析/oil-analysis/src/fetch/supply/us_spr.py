# -*- coding: utf-8 -*-
"""美国战略石油储备（SPR）月度库存。

唯一数据源：**EIA 周度石油周报 API** 序列 ``PET.WCSSTUS1.W``
= "U.S. Ending Stocks of Crude Oil in SPR"（千桶 / 周）。

⚠️ 2026-10-07 起已**完全脱离本地文件**：此前看板 SPR 走 OPEC MOMR 表 9-2（PDF 解析），
口径绕手且发布滞后；现改为直接读 EIA 官方 API。**2026-10-16 进一步移除 MOMR 兜底分支**，
实现**零本地依赖**（不再解析 data/raw 下任何 PDF）。

月度口径：取**每月最后一个周度观测值**（= EIA 自己月度表的月末口径），
不是周度均值 —— SPR 是存量，月末值才是官方公布的月度数字。

看板那张 SPR 图读 **EIA 原生周度轴**（`STATE.eiaWeekly.spr`，出自
`src/fetch/supply/eia_weekly.py` 的 `PET.WCSSTUS1.W`）；本脚本只负责给
**维度 KPI 芯片**提供月末月度口径（`STATE.usSpr` / `usSprMonths`）。
改这里的值不会改动图上曲线，改图上曲线去 `eia_weekly.py`。

⚠️ 容错：若 EIA API 拉取失败（网络 / key 失效），本脚本**不写文件、保留上次产物**
（已提交的 `data/processed/us_spr.json` 快照），KPI 芯片回落到快照值；不再回落 MOMR PDF。

输出 ``data/processed/us_spr.json``：``months`` / ``spr``（百万桶）/ ``unit`` / ``source`` / ``retrieved``。
运行：在仓库根目录执行 ``python -m src.fetch.supply.us_spr``
"""
import os, json, datetime

from src import config
from src.common.http import fetch_json_curl
from src.paths import DATA_PROCESSED

EIA_SPR_SERIES = "PET.WCSSTUS1.W"   # U.S. Ending Stocks of Crude Oil in SPR (Thousand Barrels), weekly

SOURCE_EIA = ("EIA 周度石油周报 API（序列 PET.WCSSTUS1.W，美国 SPR 原油期末库存，千桶/周）"
              "· 月度值取每月最后一个周度观测值（月末口径）· 抓取脚本 src/fetch/supply/us_spr.py"
              "（2026-10-07 起替换 OPEC MOMR 表 9-2；2026-10-16 移除 MOMR 兜底，零本地依赖）")


# --------------------------------------------------------------------------
# 1) 主路径：EIA 周度 API
# --------------------------------------------------------------------------
def fetch_eia_monthly():
    """返回 ``(months, vals)``，vals 单位百万桶。EIA 不可用时返回 ``(None, None)``。"""
    url = f"https://api.eia.gov/v2/seriesid/{EIA_SPR_SERIES}?api_key={config.EIA_KEY}"
    payload = fetch_json_curl(url, timeout=40)
    points = payload.get("response", {}).get("data", [])
    last_of_month = {}          # YYYY-MM -> (date, mbbl)
    for p in points:
        period, raw = p.get("period"), p.get("value")
        if not period or raw is None:
            continue
        try:
            mbbl = float(raw) / 1000.0           # 千桶 → 百万桶
        except (TypeError, ValueError):
            continue
        mk = period[:7]
        if mk not in last_of_month or period > last_of_month[mk][0]:
            last_of_month[mk] = (period, mbbl)

    months = sorted(last_of_month.keys())
    vals = [last_of_month[m][1] for m in months]
    if not months:
        return None, None
    print(f"  [supply]  eia SPR weekly: {len(points)} pts, "
          f"{months[0]} ~ {months[-1]}（月度 {len(months)} 月，月末口径）")
    return months, vals


# --------------------------------------------------------------------------
# 注：原「OPEC MOMR 表 9-2 PDF 兜底」分支已于 2026-10-16 移除。
#     SPR 现**仅**依赖 EIA 周报 API（PET.WCSSTUS1.W），实现零本地文件依赖，
#     不再解析 data/raw 下任何 PDF。
# --------------------------------------------------------------------------


def main():
    months, vals = fetch_eia_monthly()
    if not months:
        # 零本地依赖：EIA 失败时不回落 MOMR，保留已提交的 data/processed/us_spr.json 快照
        print("  [supply]  EIA SPR 拉取失败：不写文件，保留 data/processed/us_spr.json 原快照")
        return

    print("\nUS SPR monthly:")
    print(" months:", months)
    print(" spr   :", vals)
    out = {
        "months": months,
        "spr": vals,
        "unit": "mb",
        "source": SOURCE_EIA,
        "retrieved": datetime.date.today().isoformat(),
    }
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    out_path = os.path.join(DATA_PROCESSED, "us_spr.json")
    with open(out_path, "w") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=2)
    print("wrote us_spr.json")


if __name__ == "__main__":
    main()
