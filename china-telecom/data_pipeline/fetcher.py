# -*- coding: utf-8 -*-
"""真实数据抓取层：调用东方财富 Eastmoney 公开接口，抓取中国电信 H 股/A 股财报与行情。

所有函数均发起真实 HTTP 请求；原始响应缓存到 cache/ 便于复核与离线重放。
若网络不可用，fallback 到缓存（cache 命中时）。抓取结果未经硬编码，全部来自接口返回。
"""
import json
import os
import urllib.parse
import urllib.request
import requests

import config as C

os.makedirs(C.CACHE_DIR, exist_ok=True)


def _get_json(url, params, timeout=30):
    """GET 并返回 JSON（requests）。"""
    r = requests.get(url, params=params, headers=C.UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _cache(name, data):
    path = os.path.join(C.CACHE_DIR, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _load_cache(name):
    path = os.path.join(C.CACHE_DIR, name + ".json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _em_rows(report_name, sec_code, pagesize=120):
    """Eastmoney datacenter 通用取数；返回 result.data 列表。"""
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "filter": '(SECURITY_CODE="%s")' % sec_code,
        "pageSize": str(pagesize),
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "source": "HSF10",
        "client": "PC",
    }
    j = _get_json(C.EMAPI_BASE, params)
    if not j.get("success"):
        raise RuntimeError("Eastmoney API error: %s | %s" % (j.get("message"), j.get("code")))
    res = j.get("result") or {}
    return res.get("data") or []


# ---------------------------------------------------------------------------
# H 股 F10 长表：每行一个科目（ITEM_NAME + AMOUNT），按报告期分组
# ---------------------------------------------------------------------------
def fetch_hk_income(use_cache=True):
    name = "hk_income"
    if use_cache:
        c = _load_cache(name)
        if c:
            return c
    rows = _em_rows(C.RPT_HK_INCOME, C.H_SHARE_CODE)
    _cache(name, rows)
    return rows


def fetch_hk_balance(use_cache=True):
    name = "hk_balance"
    if use_cache:
        c = _load_cache(name)
        if c:
            return c
    rows = _em_rows(C.RPT_HK_BALANCE, C.H_SHARE_CODE)
    _cache(name, rows)
    return rows


def _hk_by_period(rows, item_name, date_type=C.DATE_TYPE_ANNUAL):
    """长表 -> {report_date: amount}，仅取某报告期类型（默认年报）。"""
    out = {}
    for r in rows:
        if r.get("ITEM_NAME") == item_name and r.get("DATE_TYPE_CODE") == date_type:
            out[r.get("REPORT_DATE")] = r.get("AMOUNT")
    return out


def hk_income_annual_series(item_name):
    """返回 {年份: 金额(元)} 的年报序列（H 股 F10 通常仅含最新年份）。"""
    rows = fetch_hk_income()
    d = _hk_by_period(rows, item_name)
    return {int(k[:4]): v for k, v in d.items() if k and len(k) >= 4}


def hk_balance_annual_series(item_name):
    rows = fetch_hk_balance()
    d = _hk_by_period(rows, item_name)
    return {int(k[:4]): v for k, v in d.items() if k and len(k) >= 4}


# ---------------------------------------------------------------------------
# A 股宽表：每行一个报告期，列即指标（2020-2025 全历史）
# ---------------------------------------------------------------------------
def fetch_a_income(use_cache=True):
    name = "a_income"
    if use_cache:
        c = _load_cache(name)
        if c:
            return c
    rows = _em_rows(C.RPT_A_INCOME, C.A_SHARE_CODE)
    _cache(name, rows)
    return rows


def fetch_a_cashflow(use_cache=True):
    name = "a_cashflow"
    if use_cache:
        c = _load_cache(name)
        if c:
            return c
    rows = _em_rows(C.RPT_A_CASHFLOW, C.A_SHARE_CODE)
    _cache(name, rows)
    return rows


def a_income_annual_series(col):
    """返回 {年份: 值} 的年报序列（A 股宽表，金额单位元）。"""
    rows = fetch_a_income()
    out = {}
    for r in rows:
        if r.get("DATE_TYPE_CODE") == C.DATE_TYPE_ANNUAL and r.get("REPORT_DATE"):
            y = int(r["REPORT_DATE"][:4])
            out[y] = r.get(col)
    return out


# ---------------------------------------------------------------------------
# 行情快照
# ---------------------------------------------------------------------------
def fetch_quote(use_cache=False):
    """返回 00762.HK 实时行情 dict（f43=最新价*100 等）。"""
    name = "hk_quote"
    if use_cache:
        c = _load_cache(name)
        if c:
            return c
    params = {
        "secid": C.H_SHARE_SECID,
        "fields": "f43,f44,f45,f46,f57,f58,f60,f168,f116,f117",
    }
    q = urllib.parse.urlencode(params)
    url = C.QUOTE_BASE + "?" + q
    req = urllib.request.Request(url, headers=C.UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        j = json.loads(resp.read().decode("utf-8"))
    data = j.get("data") or {}
    _cache(name, data)
    return data


# ---------------------------------------------------------------------------
# 便捷汇总：把抓取结果整理为"看板可直接用"的字典（金额转为亿元）
# ---------------------------------------------------------------------------
def build_fetched_snapshot():
    """抓取并整理最新年度真实财报摘要（单位：亿元 / 元）。"""
    snap = {}
    inc = fetch_hk_income()
    bal = fetch_hk_balance()

    income_map = {
        "rev": _hk_by_period(inc, "营业额"),
        "np": _hk_by_period(inc, "股东应占溢利"),
        "eps": _hk_by_period(inc, "每股基本盈利"),
        "gp": _hk_by_period(inc, "毛利"),
        "da": _hk_by_period(inc, "折旧与摊销"),
        "opt": _hk_by_period(inc, "经营溢利"),
        "tax": _hk_by_period(inc, "税项"),
        "finance": _hk_by_period(inc, "融资成本"),
    }
    bal_map = {
        "total_assets": _hk_by_period(bal, "总资产"),
        "total_liab": _hk_by_period(bal, "总负债"),
        "equity": _hk_by_period(bal, "股东权益"),
        "ar": _hk_by_period(bal, "应收帐款"),
    }

    def to_yi(series, metric):
        # 金额类(元)转亿元；每股指标(eps, 单位元/股)保持原值不除。
        # 注意：series 的键是完整报告期时间戳，需提取年份作为整数键，便于下游按年索引。
        out = {}
        for k, v in series.items():
            y = int(str(k)[:4])
            if metric == "eps":
                out[y] = v
            elif isinstance(v, (int, float)):
                out[y] = round(v / 1e8, 2)
            else:
                out[y] = v
        return out

    snap["income_yi"] = {m: to_yi(s, m) for m, s in income_map.items()}
    snap["balance_yi"] = {m: to_yi(s, m) for m, s in bal_map.items()}
    return snap


if __name__ == "__main__":
    s = build_fetched_snapshot()
    print("== 抓取的 H 股最新年度真实财报摘要（亿元）==")
    print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
    print("== A 股 2020-2025 营收（亿元，与 H 股合并营收一致）==")
    rev = a_income_annual_series("TOTAL_OPERATE_INCOME")
    print({y: round(v / 1e8, 2) if v else None for y, v in sorted(rev.items())})
    q = fetch_quote()
    print("== 行情 ==", q)
