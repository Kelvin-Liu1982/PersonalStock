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
from src.common.http import fetch_json_curl, fetch_json_urlopen, fetch_text_curl
from src.common.series import align
import re

# ⚠️ 2026-11-27：`api.eia.gov/v2/seriesid` 端点会**滞后官网 WPSR 一期**（实测 API 的
#    prod/gasSupplied/total/cushing/gasinv 只到 11-13，而官网 WPSR 已发 11-20 期、
#    11-25 发布）。官网提供当期 CSV（ir.eia.gov/wpsr/table{1,4}.csv），故用 CSV 补
#    「比 API 更晚的那一期」，历史仍由 API 提供（CSV 只有最近两期+去年同期）。
_WPSR_TABLES = {
    "table1": "https://ir.eia.gov/wpsr/table1.csv",   # U.S. Petroleum Balance Sheet
    "table4": "https://ir.eia.gov/wpsr/table4.csv",   # Stocks of Crude Oil by PAD / 汽油库存
}
# key → (表, 分组关键词|None, 行标签关键词, 单位换算系数到 API 口径)
#   table1 库存单位=百万桶 → ×1000 得千桶；产/供为千桶/日 → ×1。
_WPSR_MAP = {
    "total":       ("table1", None,                  "commercial (excluding spr)", 1000.0),
    "spr":         ("table1", None,                  "strategic petroleum reserve", 1000.0),
    "prod":        ("table1", "crude oil supply",    "domestic production", 1.0),
    "gasSupplied": ("table1", "products supplied",   "finished motor gasoline", 1.0),
    "cushing":     ("table4", None,                  "cushing", 1000.0),
    "gasinv":      ("table4", None,                  "total motor gasoline", 1000.0),
}


def _num(s):
    """CSV 数值（含千分位逗号）→ float；占位符返回 None。"""
    if s is None:
        return None
    t = str(s).strip().replace(",", "")
    if not t or t in ("--", "NA", "N/A", "W"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _mdy_to_iso(s):
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", (s or "").strip())
    if not m:
        return None
    mo, dy, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yr < 100:
        yr += 2000
    return f"{yr:04d}-{mo:02d}-{dy:02d}"


def _parse_wpsr(text):
    """解析 WPSR CSV → (header_dates: [(col_idx, iso)], rows)。

    ⚠️ CSV 有两种行结构：单级行（r[0]=标签, r[1]=最新值）与两级行
    （r[0]=分组, r[1]=子项标签, r[2]=最新值）。故取「值列」时要按行加 0/1 偏移，
    与表头日期列对齐（表头形如 STUB_1, 11/20/26, 11/13/26, …）。
    """
    import csv, io
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    header = rows[0]
    hdates = []
    for i, cell in enumerate(header):
        iso = _mdy_to_iso(cell)
        if iso:
            hdates.append((i, iso))
    return hdates, rows[1:]


def _match_row(r, grp, lab):
    c0 = (r[0] if r else "").strip().lower()
    c1 = (r[1] if len(r) > 1 else "").strip().lower()
    if grp:
        return grp in c0 and lab in c1
    # 单级行：r[0] 命中标签，且 r[1] 是数值（不是子标签文字）
    return lab in c0 and _num(c1) is not None


def _wpsr_points():
    """返回 {key: {iso_date: value(API 单位)}}，只用比 API 更新的那几期（调用方再判断）。"""
    cache, out = {}, {}
    for key, (tbl, grp, lab, mult) in _WPSR_MAP.items():
        if tbl not in cache:
            txt = fetch_text_curl(_WPSR_TABLES[tbl], timeout=40, tries=2)
            cache[tbl] = _parse_wpsr(txt)
        hdates, rows = cache[tbl]
        if not hdates:
            continue
        for r in rows:
            if not _match_row(r, grp, lab):
                continue
            two_level = (grp is not None) or (_num(r[1] if len(r) > 1 else None) is None)
            offset = 1 if two_level else 0
            pts = {}
            for col, iso in hdates:
                j = col + offset
                v = _num(r[j]) if j < len(r) else None
                if v is not None:
                    pts[iso] = v * mult
            if pts:
                out[key] = pts
            break   # 每个 key 只取第一条命中行
    return out


def _supplement_with_wpsr(raw):
    """用 WPSR 官网 CSV 补齐 API 滞后的最新期（只补比 API max 更新的日期）。"""
    wpsr = _wpsr_points()
    if not wpsr:
        return
    added = []
    for key, pts in wpsr.items():
        series = raw.get(key)
        if series is None:
            continue
        api_max = max(series) if series else None
        for iso, v in pts.items():
            if api_max is None or iso > api_max:
                series[iso] = v
                added.append(f"{key}@{iso}")
    if added:
        print(f"  [supply]  EIA API 滞后，已用 WPSR 官网 CSV 补最新期：{', '.join(sorted(set(added)))}")

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

# EIA API 每序列请求次数（取并集以弥合副本不同步；util 无 CSV 兜底、主要靠这个）。
_API_TRIES = 2

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
    """抓取全部周度序列，返回 ``{key: {period: float}}``。单个序列失败不影响其它。

    ⚠️ 2026-11-27：EIA API 的 seriesid 端点有两类不稳定 ——
    (1) **副本不同步**：同一序列两次请求可能返回不同末日（实测 util 一次到 10-30、
        一次到 11-20），故每序列取 ``_API_TRIES`` 次并**合并并集**，弥合副本差异；
    (2) **滞后官网一期**：prod/gasSupplied/total/cushing/gasinv 常比官网 WPSR 少一周，
        由 :func:`_supplement_with_wpsr` 用官网 CSV 补（util 无 CSV 兜底，靠上面的重试）。
    """
    raw = {}
    for key, series_id in EIA_SERIES.items():
        url = f"https://api.eia.gov/v2/seriesid/{series_id}?api_key={config.EIA_KEY}"
        series = {}
        for _attempt in range(_API_TRIES):
            payload = fetch_json_curl(url, timeout=40)
            for point in payload.get("response", {}).get("data", []):
                try:
                    series[point["period"]] = float(point["value"])
                except (KeyError, TypeError, ValueError):
                    pass
        raw[key] = series
    # API 常滞后官网一期：用 WPSR CSV 补最新（只补比 API max 更新的日期）。
    _supplement_with_wpsr(raw)
    for key in EIA_SERIES:
        s = raw.get(key) or {}
        lp = max(s) if s else None
        print(f"  [supply]  eia {key}: {len(s)} pts, "
              f"last={s.get(lp) if lp else None} ({lp})")
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
