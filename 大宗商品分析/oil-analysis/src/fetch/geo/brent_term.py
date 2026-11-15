# -*- coding: utf-8 -*-
"""地缘维度 · 期货期限结构（Brent 近月 − 远月价差）。

数据口径
--------
原油期货曲线形状（backwardation / contango）是地缘与供给冲击最直接的
"近端稀缺"信号：近端升水（backwardation，价差 > 0）通常意味着即期供给偏紧、
地缘风险溢价高；近端贴水（contango，价差 < 0）意味着即期宽松、库存充裕。

实现：用 yfinance 拉取 Brent 近月连续（BZ=F）与各远月合约（BZ{mc}{yy}.NYM）
的日度收盘价，对每一个交易日取"到期月 = 当日 + 12 个月"的远月合约，
计算 近月 − 远月 价差（美元/桶）。价差为正=backwardation，为负=contango。
与项目既有的 OVX（Yahoo ^OVX）同源，均为 Yahoo 行情，属可接受的一手行情源。

返回 ``{YYYY-MM-DD: float}``（日度价差），由 build_dataset 对齐到统一日度轴。

⚠️ **失败不得静默**：本模块历史上用裸 ``except Exception → return {}`` 兜底，
2026-10-06 的构建里 Yahoo 批量抓取失败被整个吞掉，落库成 1006 个 null，
页面上只表现为"一张空图"、没有任何提示。现在改为：

    * ``fetch_with_status()`` 返回 ``(data, status)``，status 带 ok / points /
      last / error / contracts / missing，由 build_dataset 落进 ``brentTermMeta``，
      前端据此在卡内显示可操作的说明；
    * 失败时打印醒目的 ⚠️ 告警行。

⚠️ **pandas / yfinance 必须延迟导入**：本模块被 build_dataset 顶层 import，
若在模块顶层 `import pandas/yfinance`，缺依赖时 ImportError 会直接炸掉整条流水线，
违反「任何单一数据源失败都不能中断流水线」的约定。故二者只在 fetch() 内按需导入，
导入失败按降级处理（打印可操作提示 + 返回空）。numpy 历史遗留但从未使用，已删除。

⚠️ **两个已修的老坑（勿回退）**：
1. 远月合约列表**必须按近月合约的实际交易日推导**，不能硬编码年份区间。
   旧实现写死 ``_YEARS=[2025..2029]``，一次请求 60 个合约，其中 40 个已摘牌
   （2025 全部 + 2026 除 BZZ26），每次构建都发 40 个必败 404，极易触发 Yahoo 限流
   —— 这正是 2026-10-06 那次"整批返回空"的诱因。现在只请求真正需要的 ~25 个。
2. **Yahoo 对已到期年份的合约没有历史**是结构性事实：它只给未到期年份的合约
   留 2 年历史。日期 t 的远月 = t+12 个月，所以本序列天然只有约 10–11 个月
   （2025-12 起），不可能填满 2 年回溯窗口。看板 RANGE=252 的窗口起点
   （2026-10 时为 2026-01-25）刚好被完整覆盖，属可接受。
"""

import time

# Brent 期货月份代码（F=1月 … Z=12月）
_MONTH_CODES = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}
_CODE_OF_MONTH = {m: c for c, m in _MONTH_CODES.items()}

# 期限结构目标跨度（月）
_SPAN_MONTHS = 12

# 近月 / 远月统一回溯窗口（Yahoo period 取值；与近月连续合约能拿到的历史一致）
_PERIOD = "2y"

# 批量下载尝试次数（Yahoo 偶发限流，重试一次基本能过）
_BATCH_TRIES = 2

# 近月连续合约尝试次数（它是全序列的基准，失败等于整图失效，多给一次机会）
_FRONT_TRIES = 3


def _symbol(year, month):
    """合约代码：BZ + 月份码 + 两位年 + .NYM，如 2027-10 -> BZV27.NYM。"""
    return f"BZ{_CODE_OF_MONTH[month]}{str(year % 100).zfill(2)}.NYM"


def _target_forward_month(date_str):
    y, m, _ = (int(x) for x in date_str.split("-"))
    total = (y * 12 + (m - 1)) + _SPAN_MONTHS
    return total // 12, (total % 12) + 1


def _needed_months(date_keys):
    """按近月合约的实际交易日推导所需远月到期月（去重、升序）。

    旧实现硬编码年份区间 → 60 个合约里有 40 个已摘牌。这里只保留真正会被用到的
    月份（2 年日度序列 → 约 25 个），既去掉必败请求，也让年份随当前日期自动滚动。
    """
    return sorted({_target_forward_month(d) for d in date_keys})


def _ser_to_map(ser, index, pd):
    return {
        index[i].strftime("%Y-%m-%d"): float(ser.iloc[i])
        for i in range(len(ser))
        if not pd.isna(ser.iloc[i])
    }


def _bundle_closes(bundle, tickers, pd):
    """从 yfinance 批量下载结果里取每个合约的 {date: close}。"""
    closes = {}
    if bundle is None or len(bundle) == 0:
        return closes
    cols = bundle.columns
    # 多合约：列为多级 (field, symbol)；单合约：列可能是 (symbol, field) 或普通
    if isinstance(cols, pd.MultiIndex):
        # 两种常见排列都兼容
        lvl0 = cols.get_level_values(0)
        if "Close" in lvl0:
            for sym in tickers:
                try:
                    ser = bundle[("Close", sym)]
                    closes[sym] = _ser_to_map(ser, bundle.index, pd)
                except Exception:
                    continue
        else:
            for sym in tickers:
                try:
                    ser = bundle.loc[:, (sym, "Close")]
                    closes[sym] = _ser_to_map(ser, bundle.index, pd)
                except Exception:
                    continue
    else:
        for sym in tickers:
            if sym in bundle.columns:
                closes[sym] = _ser_to_map(bundle[sym], bundle.index, pd)
    return closes


def _require_deps():
    """按需导入 (pandas, yfinance)；缺依赖时返回 None 并由调用方降级。"""
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError as exc:
        print(f"  [term]   缺少依赖 yfinance/pandas（降级为空）: {exc!r}")
        print("        安装：python3.13 -m pip install -r requirements.txt")
        print("        期限结构只是地缘维度的一张图，缺失不影响其余数据源。")
        return None
    return pd, yf


def _front_closes(yf, pd):
    """近月连续合约 BZ=F 的 {date: close}，带重试。"""
    for attempt in range(_FRONT_TRIES):
        try:
            hist = yf.Ticker("BZ=F").history(period=_PERIOD)
            if hist is None or len(hist) == 0:
                raise ValueError("空结果")
            out = _ser_to_map(hist["Close"], hist.index, pd)
            if out:
                return out
        except Exception as exc:
            print(f"  [term]   BZ=F 第 {attempt + 1}/{_FRONT_TRIES} 次抓取失败: {exc!r}")
        time.sleep(2)
    return {}


def _download_closes(yf, pd, syms):
    """批量下载远月合约收盘价，返回 {symbol: {date: close}}，带一次重试。"""
    closes = {}
    for attempt in range(_BATCH_TRIES):
        try:
            bundle = yf.download(syms, period=_PERIOD, progress=False)
            closes = _bundle_closes(bundle, syms, pd)
        except Exception as exc:
            print(f"  [term]   远月合约批量下载第 {attempt + 1}/{_BATCH_TRIES} 次失败: {exc!r}")
            closes = {}
        if any(closes.values()):
            return closes
        time.sleep(3)
    return closes


def _fallback_closes(yf, pd, syms):
    """批量下载整体返回空（多为 Yahoo 限流）时的逐合约兜底。"""
    out = {}
    for sym in syms:
        try:
            hist = yf.Ticker(sym).history(period=_PERIOD)
            if hist is None or len(hist) == 0:
                continue
            m = _ser_to_map(hist["Close"], hist.index, pd)
            if m:
                out[sym] = m
        except Exception:
            continue
    return out


def _resolve(target, by_month):
    """取目标到期月的收盘价表；缺失时在 ±1 个月内就近替代。

    跨月替代会引入约 1 个月的期限误差，故只在目标月合约无数据时兜底，
    不做更大范围搜索（旧实现在全部 60 个合约里取最近，误差不可控）。
    """
    y, m = target
    for dm in (0, -1, 1):
        ty, tm = y, m + dm
        if tm < 1:
            ty, tm = ty - 1, 12
        elif tm > 12:
            ty, tm = ty + 1, 1
        got = by_month.get((ty, tm))
        if got:
            return got
    return None


def _warn(status):
    """失败时的醒目告警：让"整图空白"在构建日志里可追溯。"""
    print("  ⚠️ [term] Brent 期限结构抓取失败：地缘 tab「Brent 12个月期限结构（近月−远月）」"
          f"将显示为空白（{status.get('error')}）。重跑 `python run.py dataset` 即可恢复；"
          "该图缺失不影响其余数据源。")


def fetch_with_status(start=None):
    """抓取 Brent 12 个月期限结构价差。

    返回 ``(data, status)``：

    * ``data``   —— ``{YYYY-MM-DD: spread}``，失败为空 dict；
    * ``status`` —— ``{ok, points, last, error, contracts, missing, source}``，
      由 build_dataset 落进 ``brentTermMeta``，供前端在数据缺失时给出说明。
    """
    status = {
        "ok": False, "points": 0, "last": None, "error": None,
        "contracts": 0, "missing": 0,
        "source": "Yahoo Finance：BZ=F（近月连续）与 BZ{mc}{yy}.NYM（远月合约）日度收盘价",
    }
    deps = _require_deps()
    if deps is None:
        status["error"] = "缺少依赖 yfinance/pandas"
        _warn(status)
        return {}, status
    pd, yf = deps

    try:
        front_close = _front_closes(yf, pd)
        if not front_close:
            status["error"] = "近月连续合约 BZ=F 无数据"
            _warn(status)
            return {}, status

        months = _needed_months(front_close.keys())
        syms = [_symbol(y, m) for y, m in months]
        status["contracts"] = len(syms)

        deferred = _download_closes(yf, pd, syms)
        missing = [s for s in syms if not deferred.get(s)]
        if not deferred and missing:
            print(f"  [term]   批量下载为空，改用逐合约兜底（{len(missing)} 个）...")
            deferred = _fallback_closes(yf, pd, missing)
            missing = [s for s in syms if not deferred.get(s)]
        status["missing"] = len(missing)

        by_month = {}
        for (y, m), sym in zip(months, syms):
            if deferred.get(sym):
                by_month[(y, m)] = deferred[sym]

        out = {}
        for date_str, fpx in front_close.items():
            dpx = _resolve(_target_forward_month(date_str), by_month)
            if not dpx or date_str not in dpx:
                continue
            out[date_str] = round(fpx - dpx[date_str], 3)

        if out:
            last_k = list(out)[-1]
            status.update(ok=True, points=len(out), last=last_k)
            print(f"  [term]   Brent 12M 期限结构：{len(out)} 个交易日，"
                  f"最新 {last_k} -> {out[last_k]:+.2f} $/bbl"
                  f"（远月合约命中 {len(syms) - len(missing)}/{len(syms)}）")
        else:
            status["error"] = "远月合约无可用行情"
            _warn(status)
        return out, status
    except Exception as exc:  # 任何失败都降级为空，不阻断管线
        status["error"] = f"抓取异常：{type(exc).__name__}"
        print(f"  [term]   抓取失败（降级为空）: {exc!r}")
        _warn(status)
        return {}, status


def fetch(start=None):
    """抓取 Brent 12 个月期限结构价差，返回日度 ``{date: spread}``。"""
    data, _ = fetch_with_status(start)
    return data
