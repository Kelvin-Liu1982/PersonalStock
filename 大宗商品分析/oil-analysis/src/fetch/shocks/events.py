# -*- coding: utf-8 -*-
"""其他突发的维度：价格跳变与异常事件。

承接无法归入供给/需求/地缘/宏观四类的冲击——由 Brent 单日收益率及其滚动
波动率派生：
- ``ret`` / ``vol20`` 是本模块的产物，但同时被地缘维度引用，因此放在最前计算；
- ``events`` 为时间线上的跳变事件（供看板事件流使用）；
- 压力分取“近 20 个交易日内的跳变次数”映射，次数越多说明非常态冲击越密集。
"""
from src import config
from src.common.series import annualize_vol, pct, rolling_std


def returns(brent):
    """Brent 单日收益率序列（%）。首日为 None。"""
    return [
        pct(brent[i], brent[i - 1]) if (i > 0 and brent[i] and brent[i - 1]) else None
        for i in range(len(brent))
    ]


def realized_vol(ret, window=None):
    """Brent 已实现波动率（%，年化）。窗口与年化口径统一取 config。"""
    window = window or config.VOL_WINDOW
    return annualize_vol(
        rolling_std([None if r is None else r / 100 for r in ret], window,
                    min_periods=config.VOL_MIN_PERIODS),
        periods=config.ANNUALIZE_PERIODS)


def derive(dates, brent, ret):
    """派生跳变事件与突发预警（压力分由 src/score/dims.py 与 src/score/geo.py 计算）。"""
    events = [
        {
            "date": dates[i],
            "ret": round(ret[i], 2),
            "level": "high" if abs(ret[i]) >= config.ALERT_RET_HIGH else "mid",
        }
        for i in range(len(ret))
        if ret[i] is not None and abs(ret[i]) > config.JUMP_THRESHOLD
    ]
    events.sort(key=lambda x: x["date"], reverse=True)

    alerts = []
    for i in range(1, len(brent)):
        change = ret[i]
        if change is not None and abs(change) >= config.ALERT_RET_THRESHOLD:
            alerts.append({
                "date": dates[i],
                "dim": "其他突发",
                "level": "high" if abs(change) >= config.ALERT_RET_HIGH else "mid",
                "msg": f"Brent 单日变动 {change:+.1f}%（{'大涨' if change > 0 else '大跌'}）",
            })

    print(f"  [shocks]  跳变事件 {len(events)} 条，预警 {len(alerts)} 条")
    return {"events": events, "alerts": alerts}
