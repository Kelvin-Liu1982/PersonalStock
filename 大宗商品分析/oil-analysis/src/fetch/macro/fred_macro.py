# -*- coding: utf-8 -*-
"""宏观金融维度（FRED 日度）。

看板口径：油价以美元计价，美元走强通常压制油价（负相关）；
联邦基金利率与 10 年期国债收益率刻画利率与政策预期，是宏观金融环境的核心观测。
"""
from src import config
from src.common.http import fetch_fred_group
from src.common.series import pct

FRED_SERIES = {
    "dxy": "DTWEXBGS",   # 名义广义美元指数
    "dff": "DFF",        # 联邦基金有效利率
    "dgs10": "DGS10",    # 10 年期国债到期收益率
}


def fetch(start=None):
    """抓取宏观金融三条序列，返回 ``{key: {YYYY-MM-DD: float}}``。"""
    start = start or config.START_DATE
    return fetch_fred_group(FRED_SERIES, start, "macro")


def derive(dates, dxy):
    """派生美元 5 日变动与宏观预警（压力分由 src/score/dims.py 与 src/score/geo.py 计算）。

    参数
        dates: 统一日度日期轴
        dxy:   对齐后的美元指数序列

    返回
        {"dxy_chg5": [...], "alerts": [...]}
    """
    w = config.DXY_CHG_WINDOW
    dxy_chg5 = [
        pct(dxy[i], dxy[i - w]) if (i >= w and dxy[i] and dxy[i - w]) else None
        for i in range(len(dxy))
    ]

    # 预警：美元指数 5 日变动超阈值（走强压制油价 / 走弱支撑油价）
    alerts = []
    for i in range(1, len(dates)):
        change = dxy_chg5[i]
        if change is not None and abs(change) >= config.ALERT_DXY_THRESHOLD:
            direction = "走强压制油价" if change > 0 else "走弱支撑油价"
            alerts.append({
                "date": dates[i],
                "dim": "宏观金融",
                "level": "mid",
                "msg": f"美元指数 5 日变动 {change:+.1f}%（{direction}）",
            })

    print(f"  [macro]   dxy_chg5 触发预警 {len(alerts)} 条")
    return {"dxy_chg5": dxy_chg5, "alerts": alerts}
