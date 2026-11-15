# -*- coding: utf-8 -*-
"""地缘政治维度：OVX 恐慌指数 + 已实现波动率。

- OVX 是 CBOE 编制的原油版 VIX，直接从期权隐含波动率刻画“恐慌溢价”，
  对地缘冲突与供给中断最敏感，是本维度的核心观测。
- 已实现波动率（Brent 20 日年化）与单日跳变用于把“已发生的冲击”计入压力分。

数据源：Yahoo Finance ^OVX，query2 为主端点、query1 兜底。
"""
import datetime

from src import config
from src.common.http import fetch_json_curl
from src.common.series import align

ENDPOINTS = [
    "https://query2.finance.yahoo.com/v8/finance/chart/%5EOVX?interval=1d&range=3y",
    "https://query1.finance.yahoo.com/v8/finance/chart/%5EOVX?interval=1d&range=3y",
]

# Yahoo 的 chart 接口对 User-Agent 挑剔：裸 Mozilla/5.0 会被 403、默认 curl 会被 429，
# 必须用接近真实浏览器的 UA 才能拿到数据（2026-09 起实测）。
_BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def fetch(tries=3):
    """抓取 Yahoo ^OVX 日度序列，返回 ``{YYYY-MM-DD: float}``。失败返回 {}。"""
    for attempt in range(tries):
        for url in ENDPOINTS:
            payload = fetch_json_curl(url, tries=1, timeout=40, user_agent=_BROWSER_UA)
            try:
                result = payload["chart"]["result"][0]
                timestamps = result["timestamp"]
                closes = result["indicators"]["quote"][0]["close"]
            except (KeyError, IndexError, TypeError):
                continue

            out = {}
            for ts, close in zip(timestamps, closes):
                if close is None:
                    continue
                day = datetime.datetime.fromtimestamp(
                    ts, datetime.timezone.utc).strftime("%Y-%m-%d")
                out[day] = float(close)
            if out:
                return out
        print(f"  [geo]     OVX 第 {attempt + 1} 轮抓取失败，重试")
    return {}


def derive(dates, ovx_raw, vol20):
    """派生对齐后的 OVX 与地缘预警（压力分由 src/score/dims.py 与 src/score/geo.py 计算）。

    参数
        dates:   统一日度日期轴
        ovx_raw: fetch() 的原始 ``{date: value}``
        vol20:   Brent 20 日年化波动率（%）
    """
    ovx = align(ovx_raw, dates)
    print(f"  [geo]     ovx: {len(ovx_raw)} raw pts, "
          f"{sum(1 for v in ovx if v is not None)} aligned")

    alerts = []
    for i in range(1, len(dates)):
        if vol20[i] is not None and vol20[i] >= config.ALERT_VOL_THRESHOLD:
            alerts.append({
                "date": dates[i],
                "dim": "地缘政治",
                "level": "high",
                "msg": f"20日年化波动率升至 {vol20[i]:.0f}%（地缘/供给冲击信号）",
            })

    print(f"  [geo]     波动率触发预警 {len(alerts)} 条")
    return {"ovx": ovx, "alerts": alerts}
