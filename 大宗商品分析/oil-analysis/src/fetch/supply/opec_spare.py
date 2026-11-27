# -*- coding: utf-8 -*-
"""供给侧 · OPEC 有效剩余产能（EIA STEO，COPS_OPEC_R05，月度）。

剩余产能是油市的“缓冲垫”：越低说明市场吸收供给冲击的能力越弱、溢价越高。
经验上 1–2 Mb/d 以下常对应紧平衡；2020 年需求崩塌时一度冲高至近 6 Mb/d。

口径说明：中东（沙特/阿联酋/科威特等）几乎囊括 OPEC 全部剩余产能，
非洲与南美为 0，故该序列可直接当作 OPEC 总量使用。

展示口径（2026-09-09 修订，2026-10-06 确认）：
序列尾部按 EIA STEO 最新 vintage 分三段：
    真实估算段      2026-02 (2.195) 及之前
    真实低值段      2026-03 起剩余产能实际降至 0（霍尔木兹海峡扰动致有效剩余产能骤降）
    预测段          2027-04 起为 2.35（STEO 预测）

2026-09-09 起**取消截断**：此前用「精确 0 = 未观测占位」判定并在首个 0 处 break，
导致 2026-03 之后的全部数据（含 2027 预测段）被丢弃、图只画到 2026-02。
该判定是错的——0 是真实读数（中东产能受限导致的实际归零），不是数据缺口。
现按「EIA 返回多少就展示多少」处理，不做任何截断。
（历史背景：2020 年需求崩塌时该序列一度冲高至近 6 Mb/d。）
"""
import urllib.parse
import json
import os
import datetime

from src import config
from src.common.http import fetch_json_curl
from src.paths import DATA_PROCESSED

SERIES_ID = "COPS_OPEC_R05"

# 最近一次成功抓取的缓存（抓取失败时回退，避免整图空白）。
_CACHE_PATH = os.path.join(DATA_PROCESSED, "opec_spare.json")


def fetch(start=None, display_from=None, tries=5):
    """抓取 STEO 月度序列。

    返回 ``(months, values)``；失败时返回两个空列表。
    """
    start = start or config.STEO_START
    display_from = display_from or config.SPARE_FROM

    params = {
        "frequency": "monthly",
        "data[0]": "value",
        "facets[seriesId][]": SERIES_ID,
        "start": start,
    }
    url = "https://api.eia.gov/v2/steo/data/?" + urllib.parse.urlencode(params) + \
          f"&api_key={config.EIA_KEY}"

    payload = fetch_json_curl(url, tries=tries, pause=2, timeout=40, curl_retry=3)
    raw = {}
    for row in payload.get("response", {}).get("data", []):
        if row.get("value") is None:
            continue
        try:
            raw[row["period"]] = float(row["value"])
        except (KeyError, TypeError, ValueError):
            pass

    # 不做任何截断：EIA 返回多少就展示多少（含 0 值段与 2027 预测段）。
    # 唯一的过滤是 display_from —— 它只控制左端起点，不切断尾部。
    months, values = [], []
    for period in sorted(raw):
        if period < display_from:
            continue
        months.append(period)
        values.append(raw[period])

    # ⚠️ 2026-11-27：STEO 端点（v2/steo/data + 方括号参数）在 build 的密集请求下常超时，
    #    单独跑却能成功（实测 21s 通）。为避免一次抖动就让图整张空白，成功后写缓存，
    #    失败时回退**上次成功值**（数值口径不变，仅日期可能略旧，脚注可见）。
    if months:
        _write_cache(months, values)
        print(f"  [supply]  opecSpare: {len(months)} pts, "
              f"{months[0]} - {months[-1]}, last={values[-1]}")
    else:
        cm, cv = _read_cache()
        if cm:
            months, values = cm, cv
            print(f"  [supply]  ⚠ opecSpare 抓取失败，回退上次成功缓存：{len(cm)} pts, "
                  f"{cm[0]} - {cm[-1]}, last={cv[-1]}")
        else:
            print("  [supply]  opecSpare: 无有效数据（且无缓存可回退）")

    return months, values


def _write_cache(months, values):
    """保存最近一次成功结果，供后续抓取失败时回退。"""
    try:
        os.makedirs(DATA_PROCESSED, exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump({"months": months, "values": values,
                       "retrieved": datetime.date.today().isoformat()},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _read_cache():
    """读取上次成功缓存；不存在/损坏返回两个空列表。"""
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("months") or [], d.get("values") or []
    except Exception:
        return [], []
