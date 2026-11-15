# -*- coding: utf-8 -*-
"""地缘维度 · ICE 布伦特 投机净持仓（CFTC 持仓报告）。

数据口径
--------
CFTC 每周五发布截至当周二的持仓报告（COT）。Brent 原油期货在 CFTC 的
合约代码为 06765T（"BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE"）。
采用 disaggregated（持仓报告·期货仅）中的 **Managed Money（管理基金）净头寸**
= 管理基金多头 − 管理基金空头，作为"非商业 / 投机"持仓的现代口径代理
（传统 legacy 报告的 Non-Commercial 与之高度一致，且几乎所有现代原油情绪
分析均看 Managed Money）。

数据源：CFTC Public Reporting Environment（Socrata API，公开、无需 token、
列式 CSV，无脆弱的固定宽度解析），含完整历史周度序列。

返回 ``{YYYY-MM-DD: float}``（周度净头寸，按报告日即周二），由 build_dataset
经 align() 前向填充到统一日度轴。任何一步失败返回空 dict（管线降级）。
"""
import csv
import io
import urllib.parse
import urllib.request

API_BASE = "https://publicreporting.cftc.gov/resource/72hh-3qpy.csv"
CONTRACT_CODE = "06765T"          # BRENT LAST DAY - NYMEX
START_DATE = "2024-01-01"         # 抓取起点（geo 主窗口 RANGE=252，多备无妨）


def _build_url():
    where = (f"cftc_contract_market_code='{CONTRACT_CODE}' "
             f"and report_date_as_yyyy_mm_dd >= '{START_DATE}'")
    params = {
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": "5000",
    }
    return API_BASE + "?" + urllib.parse.urlencode(params)


def fetch(start=None):
    """抓取 Brent 投机净持仓，返回 ``{date: net_managed_money}``（周度，按报告日）。"""
    try:
        url = _build_url()
        req = urllib.request.Request(url, headers={"User-Agent": "oil-analysis/1.0"})
        with urllib.request.urlopen(req, timeout=40) as resp:
            text = resp.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        out = {}
        for row in reader:
            rd = (row.get("report_date_as_yyyy_mm_dd") or "").split("T")[0]
            if not rd:
                continue
            try:
                long_all = float(row.get("m_money_positions_long_all") or 0)
                short_all = float(row.get("m_money_positions_short_all") or 0)
            except (TypeError, ValueError):
                continue
            out[rd] = round(long_all - short_all, 1)
        if out:
            last_k = list(out)[-1]
            print(f"  [cot]    ICE 布伦特 投机净持仓(Managed Money)：{len(out)} 周，"
                  f"最新 {last_k} -> {out[last_k]:+.0f} 手")
        else:
            print("  [cot]    无数据，跳过")
        return out
    except Exception as exc:  # 任何失败都降级为空，不阻断管线
        print(f"  [cot]    抓取失败（降级为空）: {exc!r}")
        return {}
