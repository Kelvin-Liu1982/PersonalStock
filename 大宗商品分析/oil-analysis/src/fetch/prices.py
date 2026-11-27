# -*- coding: utf-8 -*-
"""价格基准（多维度共用）。

Brent / WTI / 美国常规汽油价（GASREGW）有双重身份：
1. 它们与宏观金融序列一起决定看板的**日度日期轴**；
2. Brent/WTI 被供给、地缘、宏观、突发多个维度反复引用（价差、收益率、波动率）。

因此价格不属于任何单一维度，单独成模块，由 pipeline 最先拉取。

2026-10-08 换源：Brent / WTI 改走 **EIA 日度现货**
------------------------------------------------
FRED 的 ``DCOILBRENTEU`` / ``DCOILWTICO`` 是 EIA 这两条序列的**转载** —— 抽样 12/12 个
交易日的值**完全相同（差 0.00）**，所以换源是零口径风险的平移，不是换口径。
换的理由是**更新速度**：

    · FRED 平台「每周批量补更一次」：2026-10-07 22:36 时只到 09-29，
      次日 07:33 才补齐到 10-06（一夜补 5 个交易日），日常最长滞后 7 个自然日；
    · EIA 直连是 T+1（同一时刻已含 10-06）。

代价实例：2026-10-02 Brent 从 114.82 跳到 135.51（+18.9%），而快照停在 09-29 的 113.96 ——
整根暴涨在跳变事件流、20 日波动率与压力分里全部缺失。换源后滞后从 ~7 天缩到 1 天。

⚠️ 换源不换值，但**会影响所有派生指标**：日度轴尾部不再是一段平坦的前向填充区，
vol20 / ret / 跳变事件 / z-score 压力分 / composite 都会重算，属预期变化（不是 bug）。
"""
from src import config
from src.common.http import fetch_fred_csv, fetch_fred_group, fetch_json_curl

# Brent / WTI 现货：**日度**，直连 EIA（与 FRED 那两条同值，仅更新更快，见模块 docstring）
EIA_PRICE_SERIES = {
    "brent": "PET.RBRTE.D",   # Europe Brent Spot Price FOB（美元/桶，日度）
    "wti": "PET.RWTC.D",      # WTI Spot Price，Cushing OK（美元/桶，日度）
}

# EIA 拿不到时的兜底源（值相同，只是滞后约一周）。
# ⚠️ 必须有兜底：价格是日度轴与其它派生序列的基准，一旦整条为空会「静默」让全屏
#    日度图与压力分失真 —— 正是 B47 那类「优雅降级伪装成空图」的故障模式。
FRED_PRICE_FALLBACK = {
    "brent": "DCOILBRENTEU",
    "wti": "DCOILWTICO",
}

# 其余价格仍走 FRED：零售汽油价（GASREGW）是**周度**序列，FRED 是唯一源。
# ⚠️ 因此裂解价差 crack 仍是周度台阶 —— 彻底日度化要换日度汽油现货/期货，
#    属另一轮口径决策，这轮不动。
FRED_SERIES = {
    "gas": "GASREGW",         # 美国常规汽油零售价（美元/加仑），用于裂解价差
}

# EIA v2 单次请求的观测数上限是 5000。
# ⚠️ 日度价只按 START_DATE(2024-01) 起取，1500 个观测足够（实测 699 点）且留约 2 年余量 ——
#    别无脑用 5000：多拉三千多个用不上的点会让「拉取实时」明显变慢
#    （2026-10-08 实测：默认 5000 时整条实时链路 43s，服务端还是单线程串行）。
#    brentMonthly 要回溯到 2015，才需要用满 5000。
EIA_DAILY_LENGTH = 1500
EIA_HISTORY_LENGTH = 5000


def _fetch_eia_daily(ids, start, length=EIA_DAILY_LENGTH):
    """抓 EIA 日度序列，返回 ``{key: {YYYY-MM-DD: float}}``。

    ⚠️ 两个坑：

    1. **必须本地按 ``start`` 过滤**：EIA v2 的 ``seriesid`` 接口实测不认 ``start``/``end``
       （传了仍从 2006 年起返回）。不过滤的话，价格序列会把 ``_build_date_axis`` 的并集
       从 2024 一路拉回 2006，全屏日度图横轴被拉长 20 年 —— 与
       ``config.BRENT_MONTHLY_START`` 注释警告的是同一类问题。
       所以只能靠 ``length`` 限流 + 本地过滤，两者缺一不可。
    2. 接口默认按 period **降序**返回，别照抄 ``list(...)[-1]`` 取「最新」（会拿到最早期）。
    """
    out = {}
    for key, series_id in ids.items():
        # ⚠️ 2026-11-27 实测：**不带 ``length``，也不带 ``sort[]``/``data[]`` 方括号参数**。
        #    - ``length=1500`` → 返回陈旧分页（末日停在 11-17、耗时 ~22s）；无 length 返回
        #      全量 5000 条、2s 到位且末日最新（11-24）—— 更快更正确。
        #    - 方括号参数（sort[0][column]/data[0]）会让请求挂起超时。
        #    故只发 ``?api_key=``，靠下方本地 ``period < start`` 过滤（本就有）。
        #    ``length`` 形参保留仅为兼容 fetch_brent_monthly 的调用，不再拼入 URL。
        url = f"https://api.eia.gov/v2/seriesid/{series_id}?api_key={config.EIA_KEY}"
        payload = fetch_json_curl(url, timeout=40) or {}
        rows = payload.get("response", {}).get("data", [])
        series = {}
        for point in rows:
            period, value = point.get("period"), point.get("value")
            if not period or value is None:
                continue
            if period < start:          # ISO 日期可直接字符串比较
                continue
            try:
                series[period] = float(value)
            except (TypeError, ValueError):
                pass
        out[key] = series
    return out


def fetch(start=None):
    """抓取价格序列，返回 ``{key: {YYYY-MM-DD: float}}``。

    Brent / WTI 优先 EIA 日度；任一条拿不到就**两条一起**回落 FRED ——
    两条同源，只回落一条会让 BW 价差变成「新 vs 旧」的假价差。

    ⚠️ 2026-11-27「较新者优先」：EIA 的 seriesid 接口有**发布节奏差异**（实测 Brent
    到 11-24 而 WTI 停在 11-17），也可能偶发返回陈旧副本。故两条源都取，用**两序列
    最小末日**（min(brent_last, wti_last)）作判据：FRED 的最小末日更新时，整体改用
    FRED（DCOILBRENTEU/DCOILWTICO 与 EIA 同值、仅转载渠道，切换不引入口径差）。
    用 min 而非只看 brent，可避免「一新一旧」在末尾几日算出失真的 BW 价差。
    """
    start = start or config.START_DATE
    out = {}

    eia = _fetch_eia_daily(EIA_PRICE_SERIES, start)
    for key in EIA_PRICE_SERIES:
        out[key] = eia.get(key) or {}

    missing = [k for k in EIA_PRICE_SERIES if not out.get(k)]
    # 判据用**两序列最小末日**：EIA 的 WTI（RWTC）发布常比 Brent 晚（实测 Brent 到 11-24
    # 而 WTI 停在 11-17）。若只看 brent 会误判「EIA 已最新」而保留一侧陈旧的 WTI，
    # 导致末尾几日 BW 价差用旧 WTI 失真。用 min 保证两条都新才认新。
    def _pair_edge(d):
        a = max((d or {}).get("brent") or {}, default=None)
        b = max((d or {}).get("wti") or {}, default=None)
        return min(a, b) if (a and b) else None

    eia_edge = _pair_edge(out)
    # EIA 缺失 → 必须回落；EIA 非空但任一条陈旧 → 也比对 FRED 取新
    fred = {}
    if missing or eia_edge is None:
        print(f"  [prices]  ⚠ EIA 日度价缺 {missing}，Brent/WTI 整体回落 FRED（同值，滞后约一周）")
        fred = fetch_fred_group(FRED_PRICE_FALLBACK, start, "prices-fb")
    else:
        fred = fetch_fred_group(FRED_PRICE_FALLBACK, start, "prices-fb")
        fred_edge = _pair_edge(fred)
        if fred_edge and eia_edge and fred_edge > eia_edge:
            print(f"  [prices]  ⚠ EIA 副本较旧（两序列最小末日 {eia_edge} < FRED {fred_edge}），"
                  f"整体改用 FRED（较新者优先，同值同源）")
            missing = list(EIA_PRICE_SERIES)
        else:
            fred = {}   # FRED 不比 EIA 新，保留 EIA
    for key in ("brent", "wti"):
        if fred.get(key):
            out[key] = fred[key]

    for key in EIA_PRICE_SERIES:
        ks = sorted(out[key])
        src = "FRED回落" if key in missing else "EIA日度"
        print(f"  [prices]  {key}（{src}）: {len(ks)} pts, "
              f"last={out[key][ks[-1]] if ks else None} ({ks[-1] if ks else '-'})")

    for key, series in fetch_fred_group(FRED_SERIES, start, "prices").items():
        out[key] = series
    return out


def fetch_brent_monthly(start=None):
    """Brent **月度均价**（美元/桶），返回 ``{YYYY-MM: v}``。

    与 :func:`fetch` 是两套东西，别混用：

    - :func:`fetch` 走 ``config.START_DATE``（2024-01），产物进日度日期轴，供派生序列用；
    - 本函数回溯到 ``config.BRENT_MONTHLY_START``（2015-01），产物**只给「OPEC 有效剩余产能」
      那张长周期图叠加的右轴价格线**（x 轴 2015-01 → 2027-12），故单独返回、不并入日期轴。

    2026-10-08：底层从 FRED 换成 **EIA 日度** ``PET.RBRTE.D``，与日度价同源
    （避免「同一事实抄两处」）；EIA 拿不到时回落 FRED。
    聚合口径仍是日度价的**自然月算术平均**（两边都没有现成的月频序列：
    FRED 的 ``frequency=monthly`` 参数实测返回 400 Invalid value）。
    """
    start = start or config.BRENT_MONTHLY_START
    # 回溯到 2015（约 2900 个交易日）→ 需要接近上限的 length，别用日度那个 1500
    daily = _fetch_eia_daily({"brent": EIA_PRICE_SERIES["brent"]}, start,
                             length=EIA_HISTORY_LENGTH).get("brent") or {}
    if not daily:
        print(f"  [prices]  ⚠ EIA 日度价为空，brentMonthly 回落 FRED")
        daily = fetch_fred_csv(FRED_PRICE_FALLBACK["brent"], start)

    buckets = {}
    for day, value in daily.items():
        if value is None:
            continue
        buckets.setdefault(day[:7], []).append(value)
    out = {}
    for month, values in buckets.items():
        out[month] = round(sum(values) / len(values), 2)
    print(f"  [prices]  brentMonthly: {len(out)} 个月 "
          f"{min(out) if out else '-'} → {max(out) if out else '-'}")
    return out
