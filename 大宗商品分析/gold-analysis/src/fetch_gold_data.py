#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_gold_data.py —— 抓取实时/周期数据，写回 data/gold_data.xlsx。

用法（在 gold-analysis/ 下运行）:
  python3 src/fetch_gold_data.py            抓取全部可自动化字段
  python3 src/fetch_gold_data.py --spot     只抓现货金价
  python3 src/fetch_gold_data.py --fred     只抓 FRED 序列
  python3 src/fetch_gold_data.py --dry-run  只打印将写入的值，不落盘

抓取后需再跑 build_html.py 才会写进 HTML：
  python3 src/fetch_gold_data.py && python3 src/build_html.py

口径说明（重要，避免用错量级的数据覆盖页面）:
  tickerUst  ← FRED DGS10（10Y 美债收益率），口径一致，直接覆盖。
  tickerDxy  ← ICE DXY。FRED **没有** ICE DXY；其 DTWEXBGS 是「广义美元指数」
               （量级 ~120），与 ICE DXY（量级 ~98）不同量级，直接覆盖会让页面
               数值跳变。故 FRED 只写入参考字段 dxyBroad，tickerDxy 保持人工维护；
               如需自动覆盖，请在 src/config.py 的 DXY_API 填第三方接口。
  worldDebt  ← TICKER 标签为「WORLD DEBT/GDP」即**全球**口径，FRED 无全球序列，
               人工维护（不覆盖）。
  usDebtGdp  ← FRED GFDGDPA188S（**美国**联邦债务/GDP），与债务面板 2025 的
               121.5 同口径，自动抓取。
  央行购金 / 中国持金 / 机构目标价 —— 无公开 API，人工填 Excel（见 config.MANUAL_ONLY）。
"""
import argparse
import datetime
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import excelio
import paths


def http_get_json(url):
    """GET 一个 JSON 接口；全部重试失败后返回 None 并打印原因（不抛异常）。

    FRED 会对新建连接偶发 SSL 握手重置（UNEXPECTED_EOF_WHILE_READING），
    表现为「每个新序列第一次请求必失败、重试即成功」，故内置重试。
    """
    last = ""
    for attempt in range(config.HTTP_RETRIES):
        if attempt:
            time.sleep(config.HTTP_RETRY_DELAY * attempt)  # 0.6s, 1.2s, 1.8s ...
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(
                req, timeout=config.REQUEST_TIMEOUT, context=ssl.create_default_context()
            ) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # HTTP 层已收到响应，属确定性错误（如 400 api_key 缺失），不重试
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            print(f"  ! HTTP {e.code}: {body[:160]}")
            return None
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:160]}"
    print(f"  ! 请求失败（已重试 {config.HTTP_RETRIES} 次）{last}")
    return None


def money(v):
    """4456.399902 -> '$4,456'"""
    return "$" + format(int(round(float(v))), ",d")


def fetch_daily_hl(sym=None, rng="2y"):
    """Yahoo 日线（含日内 high/low）→ [{date, high, low, close}]，升序。

    专供区间高点/回撤计算（ath / athDate / lowValue / lowDrop / reboundFromLow）。
    与 fetch_event.fetch_daily 的区别：后者只取收盘价（算 eventPct 用），
    此函数保留日内 high/low，才能匹配「盘中历史高点」的口径。
    """
    sym = sym or config.YAHOO_GOLD_SYM
    url = config.YAHOO_CHART.format(sym=sym, rng=rng)
    j = http_get_json(url)
    if not j or not j.get("chart", {}).get("result"):
        print("  ! 日线(high/low) 抓取失败，ath/low 沿用原值")
        return []
    res = j["chart"]["result"][0]
    stamps = res.get("timestamp") or []
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    highs, lows, closes = q.get("high") or [], q.get("low") or [], q.get("close") or []
    out = []
    for t, h, l, c in zip(stamps, highs, lows, closes):
        c = c if c is not None else (l if l is not None else h)
        if c is None:
            continue
        out.append({
            "date": datetime.datetime.fromtimestamp(
                t, datetime.timezone.utc).strftime("%Y-%m-%d"),
            "high": float(h) if h is not None else float(c),
            "low": float(l) if l is not None else float(c),
            "close": float(c),
        })
    return out


def fetch_spot():
    """现货金价 -> 格式化字符串；失败返回 None。"""
    j = http_get_json(config.GOLD_API)
    if not j:
        return None
    p = j.get("price")
    if p is None:
        print("  ! 返回中没有 price 字段")
        return None
    return money(p)


def fetch_fred(series_id, limit=2):
    """取 FRED 序列最近 limit 个观测值（最新在前）；无 key 或失败返回 None。"""
    if not config.FRED_API_KEY:
        return None
    url = (
        f"{config.FRED_BASE}?series_id={series_id}"
        f"&api_key={config.FRED_API_KEY}&file_type=json"
        f"&sort_order=desc&limit={limit}"
    )
    j = http_get_json(url)
    if not j or "observations" not in j:
        return None
    vals = []
    for obs in j["observations"]:
        try:
            vals.append(float(obs["value"]))
        except (TypeError, ValueError):
            vals.append(None)
    return vals


def fetch_dxy_thirdparty():
    """可选的第三方 ICE DXY 接口；未配置返回 None。"""
    if not config.DXY_API:
        return None
    j = http_get_json(config.DXY_API)
    if not j:
        return None
    for k in ("price", "dxy", "value", "close"):
        if isinstance(j.get(k), (int, float)):
            return float(j[k])
    return None


def main():
    ap = argparse.ArgumentParser(description="抓取黄金看板数据 -> data/gold_data.xlsx")
    ap.add_argument("--spot", action="store_true", help="只抓现货金价")
    ap.add_argument("--fred", action="store_true", help="只抓 FRED 序列")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写 Excel")
    args = ap.parse_args()
    do_all = not (args.spot or args.fred)

    excelio.ensure_workbook()
    updates = {}

    # ---------- 1) 现货金价 ----------
    if do_all or args.spot:
        print("[1] 现货金价 · gold-api.com")
        s = fetch_spot()
        if s:
            updates["spot"] = s
            updates["tickerXau"] = s
            # 同步「当前报盘」月份标签，避免出现「2026-08 的标签 + 11 月的价格」
            updates["spotAsOf"] = datetime.date.today().strftime("%Y-%m")
            print(f"  ✓ spot / tickerXau = {s}（报盘月份 {updates['spotAsOf']}）")
        else:
            print("  - 获取失败，保留 Excel 中的快照值")

    # ---------- 2) FRED 序列 ----------
    if do_all or args.fred:
        print("[2] FRED 序列")
        if not config.FRED_API_KEY:
            print("  - 未配置 api_key，跳过。获取方式：")
            print("      export FRED_API_KEY=你的key")
            print("      或填入 src/config.py 的 FRED_API_KEY")
            print("      申请：https://fred.stlouisfed.org/docs/api/api_key.html")
        else:
            # 10Y 美债收益率（口径一致，直接覆盖）
            v = fetch_fred(config.FRED_SERIES["tickerUst"])
            if v and v[0] is not None:
                updates["tickerUst"] = f"{v[0]:.2f}%"
                if len(v) > 1 and v[1] is not None:
                    updates["tickerUstChg"] = f"{v[0] - v[1]:+.2f}"
                print(f"  ✓ tickerUst = {updates['tickerUst']}"
                      + (f"（日变动 {updates['tickerUstChg']}）" if "tickerUstChg" in updates else ""))
            else:
                print("  - DGS10 获取失败，保留快照")

            # 广义美元指数（仅参考，不覆盖 ICE DXY）
            v = fetch_fred(config.FRED_SERIES["tickerDxy"])
            if v and v[0] is not None:
                updates["dxyBroad"] = f"{v[0]:.1f}"
                print(f"  ✓ dxyBroad = {updates['dxyBroad']}（广义指数，仅供参考，不覆盖 tickerDxy）")

            # 美国联邦债务 / GDP
            v = fetch_fred(config.FRED_SERIES["worldDebt"])
            if v and v[0] is not None:
                updates["usDebtGdp"] = f"{v[0]:.1f}%"
                print(f"  ✓ usDebtGdp = {updates['usDebtGdp']}")

            # 净利息 / GDP（供债务面板人工核对）
            v = fetch_fred(config.FRED_SERIES["interestGdp"])
            if v and v[0] is not None:
                print(f"  ✓ interestGdp = {v[0]:.2f}%（债务面板用；跨年值请人工并入「美债数据」sheet）")

    # ---------- 3) 第三方 ICE DXY（可选） ----------
    if config.DXY_API and (do_all or args.spot):
        print("[3] 第三方 ICE DXY · config.DXY_API")
        d = fetch_dxy_thirdparty()
        if d:
            updates["tickerDxy"] = f"{d:.1f}"
            print(f"  ✓ tickerDxy = {updates['tickerDxy']}")
        else:
            print("  - 获取失败，保留快照")

    # ---------- 4) 区间高点 / 回撤（ath · athDate · lowValue · lowDrop · reboundFromLow）----------
    # 力矩阵「压制④实际利率上行」的例证依赖这组字段，此前只有 schema 种子值、无人更新。
    if do_all or args.spot:
        print("[4] 区间高点与回撤 · Yahoo " + config.YAHOO_GOLD_SYM + "（2y 日线 high/low）")
        hl = fetch_daily_hl(config.YAHOO_GOLD_SYM, "2y")
        if hl:
            peak = max(hl, key=lambda r: r["high"])
            after = [r for r in hl if r["date"] >= peak["date"]]
            trough = min(after, key=lambda r: r["low"]) if after else peak
            ath, lowv = peak["high"], trough["low"]
            drop = (ath - lowv) / ath * 100.0 if ath else 0.0
            latest = hl[-1]["close"]
            rebound = (latest - lowv) / lowv * 100.0 if lowv else 0.0
            updates["ath"] = money(ath)
            updates["athDate"] = peak["date"]
            updates["lowValue"] = money(lowv)
            updates["lowDate"] = trough["date"]
            updates["lowDrop"] = f"{drop:.0f}%"
            updates["reboundFromLow"] = f"{rebound:+.1f}%"
            print(f"  ✓ 高点 {updates['ath']}（{peak['date']}）→ 低点 {updates['lowValue']}"
                  f"（{trough['date']}，回撤 {updates['lowDrop']}）；"
                  f"最新收盘 {latest:,.0f}（{hl[-1]['date']}），自低点 {updates['reboundFromLow']}")
        else:
            print("  - 抓取失败，ath/low 沿用原值")

    # ---------- 5) 力矩阵例证数据（③美元走弱单日冲击 / ④实利率 4 周变化）----------
    # 让两处例证不再写死过期月份，改为由最近行情自动生成。
    if do_all or args.spot:
        print("[5] 力矩阵例证 · 美元单日冲击 + 实利率 4 周变化")
        dxy = fetch_daily_hl("DX-Y.NYB", "1y")
        gold_d = fetch_daily_hl(config.YAHOO_GOLD_SYM, "1y")
        gpct = {}
        for i in range(1, len(gold_d)):
            p, c = gold_d[i - 1]["close"], gold_d[i]["close"]
            if p:
                gpct[gold_d[i]["date"]] = (c - p) / p * 100.0
        # ③ 近 120 个交易日内 DXY 单日跌幅最大的一天（约半年）
        if len(dxy) > 2:
            dp = []
            for i in range(1, len(dxy)):
                p, c = dxy[i - 1]["close"], dxy[i]["close"]
                if p:
                    dp.append((dxy[i]["date"], (c - p) / p * 100.0))
            if dp:
                recent = dp[-120:] if len(dp) > 120 else dp
                day, chg = min(recent, key=lambda x: x[1])
                updates["egUsdDate"] = day
                updates["egUsdDxyChg"] = f"{chg:+.2f}%"
                updates["egUsdGoldChg"] = f"{gpct.get(day, 0.0):+.1f}%"
                print(f"  ✓ ③ 美元单日最大跌幅 {day}：DXY {updates['egUsdDxyChg']}，"
                      f"金价 {updates['egUsdGoldChg']}")
        # ④ 近 20 个交易日 DFII10 变化 + 同期金价
        tips = fetch_fred(config.FRED_SERIES_MACRO.get("A2", "DFII10"), limit=21)
        if tips and len(tips) >= 2 and tips[0] is not None and tips[-1] is not None:
            updates["egRealTipsChg"] = f"{tips[0] - tips[-1]:+.2f}pct"
            if len(gold_d) >= 21:
                g0, g1 = gold_d[-21]["close"], gold_d[-1]["close"]
                updates["egRealGoldChg"] = f"{(g1 - g0) / g0 * 100:+.1f}%"
            print(f"  ✓ ④ 近 20 交易日 TIPS {updates['egRealTipsChg']}，"
                  f"金价 {updates.get('egRealGoldChg', '—')}")

    # ---------- 6) 落盘 ----------
    print()
    if args.dry_run:
        print("[dry-run] 将写入：")
        for k, v in updates.items():
            print(f"  {k} = {v}")
        return 0

    if updates:
        n = excelio.update_snapshot(updates)
        excelio.touch_meta()
        print(f"✓ 已写入 {n} 个字段 -> {paths.DATA_XLSX}")
        print("  下一步：python3 src/build_html.py   # 把 Excel 注入 output/gold-terminal.html")
    else:
        print("- 没有可写入的字段（抓取失败或未配置 key），Excel 保持原样")
    return 0


if __name__ == "__main__":
    sys.exit(main())
