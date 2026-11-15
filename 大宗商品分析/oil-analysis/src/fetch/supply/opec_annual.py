# -*- coding: utf-8 -*-
"""供给侧 · OPEC 主要成员国年度原油产量（FRED 国别年度序列）。

口径提醒（重要）：
FRED 仅覆盖 7 个成员国（沙特/伊朗/伊拉克/科威特/阿联酋/利比亚/阿尔及利亚），
委内瑞拉/尼日利亚/安哥拉/刚果/加蓬/赤道几内亚无序列。
因此本序列是**部分合计**，且不含 OPEC+，不能与 MOMR 的 OPEC 总产量混用。

月度口径曾由同目录的 opec_momr.py 提供（MOMR 表 5-7，12 国合计）；该脚本 2026-10-11
下线、2026-10-23 移出仓库，现月度口径走 EIA STEO 表 3d（src/fetch/supply/steo_monthly.py），
旧表 5-7 的口径要点留档在 README「已下线口径留档」。
"""
from src.common.http import fetch_fred_csv

# 成员国年度产量序列（原始单位：桶/日）
FRED_SERIES = {
    "SAUNGDPMOMBD": "沙特",
    "IRNNGDPMOMBD": "伊朗",
    "IRQNGDPMOMBD": "伊拉克",
    "KWTNGDPMOMBD": "科威特",
    "ARENGDPMOMBD": "阿联酋",
    "LBYNGDPMOMBD": "利比亚",
    "DZANGDPMOMBD": "阿尔及利亚",
}

START = "2000-01-01"


def fetch(start=START):
    """返回 ``(years, totals_mb_per_day)``：按年跨国求和，换算为百万桶/日。"""
    members = {}
    for series_id, name in FRED_SERIES.items():
        series = fetch_fred_csv(series_id, start)
        if series:
            members[series_id] = series
            print(f"  [supply]  opec {name}({series_id}): {len(series)} pts")
        else:
            print(f"  [supply]  opec {name}({series_id}): empty")

    years = sorted({day[:4] for series in members.values() for day in series})
    out_years, out_values = [], []
    for year in years:
        total, count = 0.0, 0
        for series in members.values():
            # 年度序列通常每月重复同一值，取该年首个非空值即可
            values = [v for day, v in series.items() if day[:4] == year and v is not None]
            if values:
                total += values[0]
                count += 1
        if count > 0:
            out_years.append(year)
            out_values.append(total / 1e6)

    if out_years:
        print(f"  [supply]  OPEC 年度合计: {len(out_years)} 年, "
              f"{out_years[0]}-{out_years[-1]}, 末值 {out_values[-1]:.1f} 百万桶/日")
    return out_years, out_values
