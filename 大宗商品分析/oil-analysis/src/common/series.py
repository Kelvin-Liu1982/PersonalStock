# -*- coding: utf-8 -*-
"""序列运算公共层：对齐、收益率、滚动波动率、z-score、相关系数。

看板的“五维度压力分”全部由这里的算子派生而来，集中放置可保证
供给侧 / 需求侧 / 地缘 / 宏观 / 突发 五个维度用的是同一套口径。
"""
import math
import statistics


def align(source, dates):
    """把 ``{date: value}`` 前向填充到统一日期轴上（轴首端的未知区间保留 None）。"""
    out, last = [], None
    for day in dates:
        if day in source:
            last = source[day]
        out.append(last)
    return out


def pct(current, previous):
    """环比变动（百分比）。基准为 0 或存在空值时返回 None。"""
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous - 1) * 100


def rolling_std(values, window=20, min_periods=5):
    """滚动总体标准差；有效样本不足 min_periods 时置 None。"""
    out = []
    for i in range(len(values)):
        win = [x for x in values[max(0, i - window + 1):i + 1] if x is not None]
        out.append(statistics.pstdev(win) if len(win) >= min_periods else None)
    return out


def annualize_vol(rolling_values, periods=252):
    """把日频滚动标准差年化为百分比波动率。"""
    return [None if v is None else v * math.sqrt(periods) * 100 for v in rolling_values]


def zscore(values):
    """z-score 标准化，返回 ``(标准化序列, 均值, 总体标准差)``。"""
    xs = [v for v in values if v is not None]
    mean = statistics.mean(xs) if xs else 0
    stdev = statistics.pstdev(xs) if xs else 1
    return [None if v is None else (v - mean) / stdev for v in values], mean, stdev


def rolling_zscore(values, window=252, min_periods=60):
    """按位置滚动 z-score 标准化。

    第 i 个值的 z-score 相对其前 ``window`` 个有效样本（含自身）计算，
    使归一化基线 = 最近 window 个观测，与看板展示窗口（RANGE=252 交易日）对齐。
    这样综合压力分不再受 START_DATE 回溯长度影响——无论抓取多少历史，
    评分永远只看“屏幕上那 1 年”的同口径区间。

    有效样本不足 min_periods 时返回 None（压力分回落中性 50）。
    """
    out = []
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        win = [v for v in values[lo:i + 1] if v is not None]
        if len(win) < min_periods:
            out.append(None)
            continue
        mean = statistics.mean(win)
        stdev = statistics.pstdev(win)
        v = values[i]
        if v is None:
            out.append(None)
        elif stdev == 0:
            out.append(0.0)
        else:
            out.append((v - mean) / stdev)
    return out


def stress(z_values, sensitivity):
    """把 z-score 映射成 0–100 的压力分（50 为中性）。"""
    return [clip(50 + sensitivity * (z if z is not None else 0)) for z in z_values]


def pearson(a, b):
    """皮尔逊相关系数，有效配对少于 5 组时返回 None。"""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 5:
        return None
    xa = [p[0] for p in pairs]
    ya = [p[1] for p in pairs]
    ma, mb = statistics.mean(xa), statistics.mean(ya)
    num = sum((x - ma) * (y - mb) for x, y in zip(xa, ya))
    da = math.sqrt(sum((x - ma) ** 2 for x in xa))
    db = math.sqrt(sum((y - mb) ** 2 for y in ya))
    return num / (da * db) if da and db else None


def clip(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def last_value(arr):
    """取序列最后一个非空值（末尾存在空洞时向前回溯）。"""
    if not arr:
        return None
    if arr[-1] is not None:
        return arr[-1]
    return next((x for x in reversed(arr) if x is not None), None)
