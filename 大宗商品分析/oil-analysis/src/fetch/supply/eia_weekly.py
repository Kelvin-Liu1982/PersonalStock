# -*- coding: utf-8 -*-
"""供给侧 · EIA 周度石油周报。

看板里所有“周度真实数据”都来自这里：原油产量、库欣与全美商业库存、汽油库存、
炼厂开工率、成品油供应量、美国 SPR 原油库存（2026-10-07 换源，原走 OPEC MOMR 表 9-2）。
周度库存意外是短线油价最重要的扰动之一。

两套坐标轴：
    eia        对齐到日度轴（前向填充），供跨维度对比与压力分计算
    eiaWeekly  原生周度网格（不做填充），图表周轴使用，避免出现假的每日台阶
"""
from src import config
from src.common.http import fetch_json_curl, fetch_json_urlopen
from src.common.series import align

# ⚠️ 2026-10-07 口径订正（此前「库欣 / 全美商业」两张图序列用反了）：
#    库欣（Cushing, OK）≈ 22–30 百万桶，全美商业原油 ≈ 425–430 百万桶，两者差一个数量级。
#    · PET.WCESTUS1.W  = "U.S. Ending Stocks excluding SPR of Crude Oil"  → 全美商业（ex-SPR）
#    · PET.WCRSTUS1.W  = "U.S. Ending Stocks of Crude Oil"                → 含 SPR 总原油（= total + spr）
#    · PET.WCSSTUS1.W  = "U.S. Ending Stocks of Crude Oil in SPR"         → SPR
#    旧的 cushing 错用了 WCESTUS1（427 被当库欣）、total 错用了 WCRSTUS1（711 被当全美商业）。
#    真正的库欣序列 id 不是 PET.WC*（WCUSTUS1 / WCESTUS2 / WCSSTUS2 全是 404），
#    而是站点表格列代码形式：PET.W_EPC0_SAX_YCUOK_MBBL.W（ duoarea=YCUOK ）。
EIA_SERIES = {
    "cushing": "PET.W_EPC0_SAX_YCUOK_MBBL.W",  # 库欣（Cushing, OK）原油期末库存·不含SPR（千桶）
    "total": "PET.WCESTUS1.W",                 # 全美商业原油期末库存·不含SPR（千桶）
    "prod": "PET.WCRFPUS2.W",                  # 美国原油产量（千桶/日）
    "gasinv": "PET.WGTSTUS1.W",                # 汽油库存（千桶）
    "util": "PET.WPULEUS3.W",                  # 炼厂开工率（%）
    "gasSupplied": "PET.WGFUPUS2.W",           # 成品油供应量（千桶/日）
    # 美国 SPR 原油期末库存（千桶）：EIA 周报自带序列，2026-10-07 起上图读这里的原生周度值。
    # ⚠️ id 里的 SST 不是 "stocks" 而是 SPR 口径；WSPR* / WCESTUS2 等猜测 id 在 API 里全是 404。
    "spr": "PET.WCSSTUS1.W",
}

# 这些序列原始单位为千桶，需换算成百万桶
MILLION_UNITS = ("cushing", "total", "prod", "gasinv", "gasSupplied", "spr")

# 派生序列：没有自己的 seriesid，由已有序列算出。
# 恒等（逐周精确成立，2026-09-25 实测 711,087 = 427,320 + 283,767）：
#    含SPR原油总库存 = 全美商业原油(ex-SPR) + SPR
# 只抓一份 total+spr 即可表达这个事实；再单独 fetch 一份 WCRSTUS1 属于「同一事实抄两处」，
# 正是 2026-10-07「首屏正常、开页拉取后图没了」那类静默失效的根源。
DERIVED = ("gross",)

# 库欣（Cushing, OK）库存周变动触发供给侧预警的阈值（百万桶）。
# 单一来源在 src/config.py（那里的注释记录了实测分布与旧阈值失效的原因），
# 这里保留同名别名仅为本模块可读性；页面实时重算（computeDerived）经 CONST
# 注入的是同一组数值，勿在此改字面量。
CUSHING_ALERT_THRESHOLD = config.CUSHING_ALERT_THRESHOLD
CUSHING_HIGH_THRESHOLD = config.CUSHING_HIGH_THRESHOLD


def fetch():
    """抓取全部周度序列，返回 ``{key: {period: float}}``。单个序列失败不影响其它。"""
    raw = {}
    for key, series_id in EIA_SERIES.items():
        url = f"https://api.eia.gov/v2/seriesid/{series_id}?api_key={config.EIA_KEY}"
        payload = fetch_json_curl(url, timeout=40)
        points = payload.get("response", {}).get("data", [])
        series = {}
        for point in points:
            try:
                series[point["period"]] = float(point["value"])
            except (KeyError, TypeError, ValueError):
                pass
        raw[key] = series
        # ⚠️ EIA v2 的 seriesid 接口默认按 period **降序**（最新在最前）返回，
        #    直接取 ``list(series.values())[-1]`` 拿到的是 **最早** 那期 —— 实测会打印出
        #    「prod last=8634 / util last=84 / spr last=270455」这种 1982 年的数，
        #    看起来像「数据源串了」实则只是日志误导（2026-10-07 排查发现）。
        #    这里显式按 max(period) 取最新一期，并连日期一起打印。
        last_period = max(series) if series else None
        last = series[last_period] if last_period else None
        print(f"  [supply]  eia {key}: {len(series)} pts, "
              f"last={last} ({last_period})")
    return raw


def build_axes(raw, all_dates):
    """产出日度对齐版 ``eia``、原生周度轴 ``eia_dates`` 与周度值 ``eia_weekly``。"""
    if not raw:
        return None, [], {}

    eia_dates = sorted(set().union(*(set(m.keys()) for m in raw.values())))

    eia, eia_weekly = {}, {}
    for key, series in raw.items():
        aligned = align(series, all_dates)
        if key in MILLION_UNITS:
            aligned = [None if v is None else v / 1000.0 for v in aligned]
        eia[key] = aligned

        # 周度原生值：仅真实观测点，缺失周留空（图表中自然断开）
        eia_weekly[key] = [
            None if period not in series
            else (series[period] / 1000.0 if key in MILLION_UNITS else series[period])
            for period in eia_dates
        ]

    # 派生序列（见 DERIVED）：含SPR原油总库存 gross = 全美商业 total + SPR spr。
    # ⚠️ 必须在**换算成百万桶之后**相加（与前端 fetchEIA 同口径）：
    #    gross 不在 MILLION_UNITS 名单里，若在换算前相加，结果会是 711087 这种千桶数。
    if "total" in eia and "spr" in eia:
        eia["gross"] = [None if (t is None or s is None) else t + s
                        for t, s in zip(eia["total"], eia["spr"])]
    if "total" in eia_weekly and "spr" in eia_weekly:
        eia_weekly["gross"] = [None if (t is None or s is None) else t + s
                               for t, s in zip(eia_weekly["total"], eia_weekly["spr"])]

    # 恒等自校验：EIA 官方口径下这个等式逐周精确成立，任何一份序列取错口径/错位都会报出来。
    if "gross" in eia:
        bad = [i for i, tri in enumerate(zip(eia["gross"], eia["total"], eia["spr"]))
               if None not in tri and abs(tri[0] - (tri[1] + tri[2])) > 0.02]
        if bad:
            print(f"  [supply]  ⚠ gross ≠ total+spr 的周次 {len(bad)} 个（{bad[:3]}），"
                  f"恒等是 EIA 官方口径，多半是某序列取错或错位")

    return eia, eia_dates, eia_weekly


def fetch_gas_supplied(eia, all_dates):
    """成品油供应量（百万桶/日）。优先取 eia 结果，缺失时用 urllib 直接兜底。

    ⚠️ 判定"缺失"必须看**有没有非空值**，不能只判 ``is not None``：
    ``align()`` 在序列全空时返回的是**等长的全 None 列表**（不是 None），
    旧写法 ``if gas_supplied is not None: return`` 会把这条空列表当成有效结果直接返回，
    导致下面的 urllib 兜底分支永远不可达。
    """
    gas_supplied = (eia or {}).get("gasSupplied") or []
    if any(v is not None for v in gas_supplied):
        return gas_supplied

    url = f"https://api.eia.gov/v2/seriesid/{EIA_SERIES['gasSupplied']}?api_key={config.EIA_KEY}"
    payload = fetch_json_urlopen(url, timeout=40)
    try:
        series = {
            p["period"]: float(p["value"])
            for p in payload["response"]["data"]
            if p.get("value") is not None
        }
    except (KeyError, TypeError, ValueError):
        print("  [supply]  gasSupplied 兜底拉取失败")
        return None

    gas_supplied = [series[d] / 1000.0 if d in series else None for d in all_dates]
    print(f"  [supply]  gasSupplied（urllib 兜底）: "
          f"{sum(1 for v in gas_supplied if v is not None)} pts")
    return gas_supplied


def alerts(dates, cushing):
    """库欣（Cushing, OK）库存周变动超阈值的供给侧预警。

    ⚠️ 输入 ``cushing`` 必须是**库欣**序列（PET.W_EPC0_SAX_YCUOK_MBBL.W，22–30 Mbbl 量级），
    不是全美商业库存。2026-10-07 之前这里传的是 WCESTUS1（427 Mbbl），阈值按那个口径定，
    换回真库欣后 >=8 Mbbl 全历史 0 次命中；阈值已按实测分布重新校准（见 config.py 注释）。
    """
    out = []
    if not cushing:
        return out

    for i in range(1, len(cushing)):
        current, previous = cushing[i], cushing[i - 1]
        if current is None or previous is None:
            continue
        change = current - previous
        if abs(change) >= CUSHING_ALERT_THRESHOLD:
            out.append({
                "date": dates[i],
                "dim": "供给侧",
                "level": "high" if abs(change) >= CUSHING_HIGH_THRESHOLD else "mid",
                "msg": f"库欣原油库存周变动 {change:+.1f} 百万桶",
            })

    print(f"  [supply]  库欣库存触发预警 {len(out)} 条"
          f"（阈值 mid>={CUSHING_ALERT_THRESHOLD} / high>={CUSHING_HIGH_THRESHOLD} 百万桶）")
    return out
