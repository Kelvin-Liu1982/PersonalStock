# -*- coding: utf-8 -*-
"""ETL 编排器：把五维度抓取结果合并成 data/dataset/*.json。

流水线（六步，顺序不可随意调整）：

    [1/6] 价格基准   src.fetch.prices          Brent / WTI / 汽油价 —— 决定日度日期轴
    [2/6] 跨维派生   收益率、波动率、裂解价差、BW 价差 —— 其余四维度都要引用
    [3/6] 各维度抓取 供给侧 / 地缘 / 宏观金融 / 其他突发，各自产出序列与该维度预警
    [4/6] 压力分     src.score.dims         供给/需求/宏观/其他 四维 0–100
    [5/6] 汇总       地缘 I_geo + 综合分（src.score.geo）、预警、相关系数、KPI
    [6/6] 离线注入   OPEC 预测(MOMR) / SPR(EIA 周报 API) / OECD 库存(MOMR) / 钻井 / PMI / 炼厂

运行：仓库根目录执行 `python -m src.pipeline.build_dataset`

设计约定
--------
1. **抓取模块只取数，不打分。** 各 fetch 模块返回原始序列并附带该维度预警，
   供给/需求/宏观/其他四维的压力分由 src/score/dims.py 计算（z-score 口径），
   地缘维度与综合分由 src/score/geo.py::apply 计算（I_geo 口径），
   后者同时负责把 kpis.composite 刷新到同一口径 —— 三者口径必须保持可并排审阅，
   且**任何一处口径变更都要同步前端 computeDerived**。
2. **geo 与 composite 只在 geo.apply 里产出一次。** 历史上 dims.compute 也算过
   一版（波动率口径），被 apply 覆盖后成为死代码，且把 kpis.composite 留在旧口径上，
   导致落库 KPI 与 composite 序列末值差 10.66 分。现已移除，勿回退。
3. **预警合并顺序固定。** 见下方 merge 处的注释：合并顺序 + 按日期倒序排序 +
   截断前 60 条，三者共同决定最终顺序，改动会直接改变页面渲染结果。
4. **任何单一数据源失败都不能中断流水线。** fetch 公共层失败返回空，
   本文件对空结果做降级处理（对应区块留空而不是抛错）。
   ⚠️ 唯一例外是**价格基准**（Brent/WTI）：它是日度轴与所有派生序列的地基，
      两条都为空时继续跑只会把 prices.json 洗成全 null，故直接终止且不写盘。
5. **FRED 系列取不到时沿用上次已提交值**（见 `_fallback_fred`）。
   FRED 维护/不可达时 HTTP 200 返回的是维护页 HTML，`fetch_fred_csv` 会把它当 CSV
   解析并**静默返回 {}**（2026-10-22 实测）。宏观三条与汽油价因此会落成全 None，
   除了让图变空，还会把「拉取实时」的回落底稿一并洗掉。
   沿用规则：**只在旧日期上沿用旧值，绝不向新日期前向填充** —— 填充等于凭空造观测，
   会污染 dxy_chg5 预警、z 分数与相关系数矩阵。
"""
import datetime
import json
import os

from src import config, dataio
from src.common.series import align, last_value, pearson
from src.fetch import prices
from src.fetch.geo import ovx as geo_ovx
from src.fetch.geo import cftc_cot, brent_term
from src.fetch.macro import fred_macro
from src.fetch.shocks import events as shock_events
from src.fetch.supply import eia_weekly, opec_annual, opec_spare, steo_monthly
from src.paths import DATA_PROCESSED
from src.score import dims as score_dims
from src.score import geo as geo_score

# 预警列表最终保留条数（看板预警流只展示最近 N 条）。
# 常量单一来源在 src/config.py（MAX_ALERTS），页面实时重算经 CONST 注入同一数值。
# 2026-10-08：Brent/WTI 改直连 EIA 日度现货。FRED 的 DCOILBRENTEU / DCOILWTICO
# 是这两条的**转载**（抽样 12/12 个交易日同值），但 FRED 平台每周才批量补更一次，
# 最长滞后 7 天；EIA 直连是 T+1。宏观金融三条与汽油零售价仍走 FRED。
META_SOURCE = ("价格：EIA 日度现货（PET.RBRTE.D / PET.RWTC.D，直连；"
               "FRED 的 DCOILBRENTEU/DCOILWTICO 为同源转载，每周补更、滞后约一周）"
               " · 宏观金融与汽油零售价：FRED（美国圣路易斯联储）公开序列")


# 相关系数矩阵的 5 条序列（顺序即矩阵行列顺序）
CORR_LABELS = ["Brent", "裂解价差", "波动率", "广义美元指数（DTWEXBGS）", "BW价差"]


def load_processed(name):
    """读取 data/processed/<name>.json；缺失返回 {}。"""
    path = os.path.join(DATA_PROCESSED, name)
    if not os.path.exists(path):
        print(f"  [offline]  {name} 缺失，该区块留空")
        return {}
    with open(path) as handle:
        return json.load(handle)


def _build_date_axis(raw_price_map):
    """日度日期轴 = 所有价格序列日期的并集（升序）。"""
    return sorted(set().union(*(set(m) for m in raw_price_map.values())))


def _fallback_fred(raw, series_map, label):
    """FRED 取不到时，用**上次已提交数据集**里的同名序列填回空键（沿用旧值）。

    触发场景：FRED 维护/不可达（2026-10-22 实测）时 ``fetch_fred_csv`` 会把维护页
    当 CSV 解析并**静默返回 {}**。照原样 align 会把这些键写成全 None，后果有两层：
      ① 宏观金融两图（DFF + 10Y 美债、广义美元指数）与裂解价差图变「本图暂无数据」；
      ② 更严重 —— 会把实时态的回落底稿洗掉（loadLive 在 FRED 失败时回落 SNAPSHOT）。

    与 STEO 的既有先例同思路（无数据回落上次快照，见下方 [6/6]）。
    ⚠️ 本函数只填回**旧日期上的真实历史值**，不为新日期编造观测；新日期上的取值
       由下游 ``align`` 的前向填充负责，与周度序列（GASREGW）既有的日轴处理同口径
       —— 末端是一段持平段，dxy_chg5 因此变动为 0、不会触发假预警。
    """
    missing = [k for k in series_map if not raw.get(k)]
    if not missing:
        return raw
    prev = dataio.load_data()
    prev_dates = prev.get("dates") or []
    for k in missing:
        arr = prev.get(k) or []
        rebuilt = {}
        for i, d in enumerate(prev_dates):
            if i < len(arr) and arr[i] is not None:
                rebuilt[d] = arr[i]
        if rebuilt:
            raw[k] = rebuilt
            last_d = sorted(rebuilt)[-1]
            print(f"  [{label}]  ⚠ FRED 无 {k}（{series_map[k]}），沿用上次已提交值 "
                  f"{len(rebuilt)} pts（末值 {last_d}={rebuilt[last_d]}）")
        else:
            print(f"  [{label}]  ⚠ FRED 无 {k}（{series_map[k]}），且无历史值可沿用（本次为空）")
    return raw


def _build_correlation(series_list):
    """对给定的多条序列两两求皮尔逊相关系数，返回对称方阵。

    相关系数满足 corr(a,b) == corr(b,a)，旧实现 ``n×n`` 全量调用 pearson，
    5 条序列时 25 次里有 15 次是重复计算。这里只算上三角（含对角线）再镜像，
    pearson 调用降到 n(n+1)/2 = 15 次；结果逐格等价（pearson 本身对称）。
    """
    n = len(series_list)
    matrix = [[None] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            value = pearson(series_list[i], series_list[j])
            matrix[i][j] = value
            matrix[j][i] = value
    return matrix


def build():
    # ---------------- [1/6] 价格基准 + 日度日期轴 ----------------
    print("[1/6] 抓取价格基准（Brent / WTI / 汽油价）...")
    raw_prices = prices.fetch()
    # 汽油零售价（GASREGW）是 FRED 唯一源，FRED 故障时会静默为空 → 沿用上次已提交值。
    # ⚠️ brent / wti 不在这里兜：它们的主源是 EIA，只有 EIA 挂了才回落 FRED。
    #    两条同时为空说明价格基准本身没了，继续跑只会把 prices.json 洗成全 null，
    #    故直接终止（不写盘）—— 宁可保留上一次数据集，也不留一份看着正常其实是空的。
    raw_prices = _fallback_fred(raw_prices, prices.FRED_SERIES, "prices")
    if not raw_prices.get("brent") and not raw_prices.get("wti"):
        print("[1/6] ❌ Brent / WTI 均为空（EIA 直连与 FRED 兜底同时不可用），终止构建且不写盘")
        return None

    # Brent 月均（2015 起）—— 只给「OPEC 有效剩余产能」图的右轴价格线用。
    # ⚠️ 刻意与 raw_prices 分开取：一旦并进日期轴，全屏日度图的横轴都会被拉到 2015。
    brent_monthly = prices.fetch_brent_monthly()

    print("[1/6] 抓取宏观金融序列（美元 / 联邦基金利率 / 10Y）...")
    raw_macro = _fallback_fred(fred_macro.fetch(), fred_macro.FRED_SERIES, "macro")

    dates = _build_date_axis({**raw_prices, **raw_macro})
    if not dates:
        print("日期轴为空，终止构建（数据源全部不可用）")
        return None

    aligned = {key: align(raw, dates) for key, raw in {**raw_prices, **raw_macro}.items()}
    brent = aligned["brent"]
    wti = aligned["wti"]
    gas = aligned["gas"]
    dxy = aligned["dxy"]

    # ---------------- [2/6] 跨维度派生 ----------------
    print("[2/6] 派生收益率 / 波动率 / 裂解价差 / BW 价差...")
    ret = shock_events.returns(brent)
    vol20 = shock_events.realized_vol(ret)
    crack = [
        None if (gas[i] is None or wti[i] is None) else gas[i] * config.GAL_PER_BBL - wti[i]
        for i in range(len(gas))
    ]
    spread_bw = [
        None if (brent[i] is None or wti[i] is None) else brent[i] - wti[i]
        for i in range(len(brent))
    ]

    # ---------------- [3/6] 各维度抓取 ----------------
    print("[3/6] 供给侧 · EIA 周报 / OPEC 剩余产能 / OPEC 年度产量...")
    eia_raw = eia_weekly.fetch()
    eia, eia_dates, eia_weekly_map = eia_weekly.build_axes(eia_raw, dates)
    gas_supplied = eia_weekly.fetch_gas_supplied(eia, dates)
    opec_spare_months, opec_spare_values = opec_spare.fetch()
    opec_years, opec_annual_values = opec_annual.fetch()
    supply_alerts = eia_weekly.alerts(dates, (eia or {}).get("cushing"))

    print("[3/6] 地缘政治 · OVX（Yahoo ^OVX）...")
    geo = geo_ovx.derive(dates, geo_ovx.fetch(), vol20)

    print("[3/6] 地缘政治 · CFTC 布伦特投机净持仓（Managed Money）/ Brent 12M 期限结构...")
    brent_cot_raw = cftc_cot.fetch()
    # 期限结构额外回传状态：抓取失败时整条序列会落成 null，页面只表现为"一张空图"。
    # 状态落进 brentTermMeta，前端据此在卡内显示可操作说明（见 dashboard.js renderTermChart）。
    brent_term_raw, brent_term_status = brent_term.fetch_with_status()
    if not brent_term_status.get("ok"):
        print("  ⚠️ [term] Brent 期限结构本次未取到数据（{}），地缘 tab 该图将显示说明文案，"
              "重跑本脚本即可恢复。".format(brent_term_status.get("error")))

    print("[3/6] 宏观金融 · 美元 5 日变动...")
    macro = fred_macro.derive(dates, dxy)

    print("[3/6] 其他突发 · 跳变事件...")
    shocks = shock_events.derive(dates, brent, ret)

    # ---------------- [4/6] 压力分（供给/需求/宏观/其他） ----------------
    print("[4/6] 计算四维压力分（geo / composite 在下一步由 score/geo.py 回填）...")
    scores = score_dims.compute(crack, gas, dxy, ret)

    # ---------------- [5/6] 汇总：预警 / 相关系数 / KPI ----------------
    print("[5/6] 汇总预警、相关系数与 KPI...")
    # 合并顺序 = 其他突发 → 地缘 → 宏观 → 供给侧。
    # Python 的 sort 是稳定排序，因此同一天的预警会保持上面的维度先后，
    # 随后统一按日期倒序并截断到 MAX_ALERTS 条。改动此顺序会改变页面渲染。
    alerts = shocks["alerts"] + geo["alerts"] + macro["alerts"] + supply_alerts
    alerts.sort(key=lambda x: x["date"], reverse=True)
    alerts = alerts[:config.MAX_ALERTS]

    corr = {
        "labels": CORR_LABELS,
        "matrix": _build_correlation([brent, crack, vol20, dxy, spread_bw]),
    }

    # 「数据截至」口径必须与前端 loadLive 一致：取 Brent 最后一个**真实**观测日，
    # 不能取日期轴的末日。日期轴是 Brent/WTI/GAS/DGS10/DFF 各序列的并集，而 10Y
    # 美债（DGS10）常比油价晚 1–3 个交易日发布 —— 轴尾会留下几个只有 DGS10 有数、
    # Brent/WTI 只是前向填充重复的"补尾日"（2026-09-30 ~ 10-05）。原写法
    # `latest = len(brent)-1` 直接取 `dates[-1]`，把"截至"虚报成 2026-10-05，
    # 而实时拉取路径（loadLive 会裁掉尾部 Brent 为空的日子）显示 2026-09-29，
    # 两条路径同一张图却两个"截至"（2026-10-07 修）。
    # raw_prices["brent"] 是 {date: value} 的未对齐原始字典，max 即最后真实观测日。
    _brent_dates = sorted((raw_prices.get("brent") or {}).keys())
    latest_date = _brent_dates[-1] if _brent_dates else dates[-1]
    kpis = {
        "latest_date": latest_date,
        "brent": last_value(brent), "wti": last_value(wti), "dxy": last_value(dxy),
        "spread_bw": last_value(spread_bw), "crack": last_value(crack),
        "vol20": last_value(vol20),
        # composite 由下方 geo_score.apply 回填（I_geo 口径），这里仅占位保键序
        "composite": None,
        "n": len(brent),
    }

    data = {
        "meta": {
            "source": META_SOURCE,
            "built": datetime.date.today().isoformat(),
        },
        "dates": dates,
        "brent": brent, "wti": wti, "dxy": dxy,
        "dff": aligned["dff"], "dgs10": aligned["dgs10"], "gas": gas,
        "gasSupplied": gas_supplied,
        "ret": ret, "vol20": vol20, "crack": crack,
        "spread_bw": spread_bw, "dxy_chg5": macro["dxy_chg5"],
        "ovx": geo["ovx"],
        "brentCot": align(brent_cot_raw, dates),
        "brentTerm": align(brent_term_raw, dates),
        "brentTermMeta": brent_term_status,
        "opecSpareMonths": opec_spare_months, "opecSpare": opec_spare_values,
        # Brent 月均价（{YYYY-MM: v}）：叠加在剩余产能图上做双轴对照，只服务这一张图
        "brentMonthly": brent_monthly,
        "eia": eia, "eiaDates": eia_dates, "eiaWeekly": eia_weekly_map,
        "opecYears": opec_years, "opec": opec_annual_values,
        "dims": {
            "supply": scores["supply"], "demand": scores["demand"],
            # geo 占位保键序，真实值由 geo_score.apply 回填
            "geo": [], "macro": scores["macro"], "other": scores["other"],
        },
        "composite": [],
        "alerts": alerts, "events": shocks["events"],
        "corr": corr, "kpis": kpis,
    }

    # 地缘维度（I_geo 口径）与综合分统一在这里产出一次，并同步刷新
    # kpis.composite —— 落库值即最终口径，离线快照与页面实时重算天然一致。
    geo_score.apply(data)

    # ---------------- [6/6] 离线产物注入 ----------------
    # 这些数据源没有可用 API（PDF 月报 / Excel 报表 / 手动录入），
    # 解析脚本各自产出 data/processed/*.json，这里只负责读进来拼装。
    print("[6/6] 注入离线解析产物...")
    data.update(_offline_supply())
    data.update(_offline_demand())

    written = dataio.save_data(data)
    print(f"已写入 data/dataset/ 共 {written} 个域文件")
    print(f"数据集构建完成：{len(dates)} 天，预警 {len(alerts)} 条，"
          f"跳变事件 {len(shocks['events'])} 条")
    print("kpis:", json.dumps(kpis, ensure_ascii=False))
    return data


def _offline_supply():
    """供给侧离线产物：OPEC 月度产量 / 美国 SPR / OECD 库存 / 全球钻井数。"""
    out = {}

    # ⚠️ 2026-10-11「OPEC 原油产量」图换源（MOMR 表 5-7 12 国 → STEO 表 3d 11 国）+
    #    「Non-OPEC DoC 原油产量」图同步换源（MOMR 10 国 → STEO 表 3d 10 国）后，
    #    旧键 opecMonths / opecMonthly / opecMonthlyCountries / opecMonthlyMeta /
    #    nonOpecDoCMonths / nonOpecDoCTotal / nonOpecDoCCountries / nonOpecDoCMeta
    #    全部随之下线；原 `opec_momr.py` 脚本与其存档 opec_monthly.json 已于
    #    2026-10-23 移出仓库（口径要点留档在 README「已下线口径留档」）。
    #    两张图现都走下方 STEO 表 3d 分项键（见 swm 块）。

    spr = load_processed("us_spr.json")
    out["usSprMonths"] = spr.get("months", [])
    out["usSpr"] = spr.get("spr", [])
    out["usSprMeta"] = spr.get("source", "")

    oecd = load_processed("oecd_stocks.json")
    out["oecdMonths"] = oecd.get("months", [])
    out["oecdCrude"] = oecd.get("crude", [])
    # products = 成品油/石化产品等非原油商业库存（IEA 口径）；与 oecdTotal（=crude+products）不同口径
    out["oecdProducts"] = oecd.get("products", [])
    out["oecdTotal"] = oecd.get("total", [])
    out["oecdMeta"] = oecd.get("source", "")

    rig = load_processed("rig_world.json")
    out["rigMonths"] = rig.get("months", [])
    out["rigWorld"] = rig.get("world", [])
    out["rigMonthlyMeta"] = " | ".join(
        part for part in (rig.get("source", ""), rig.get("scope", "")) if part)

    # 全球视角：EIA STEO 官方 API 的**月度**原油产量（世界 / OPEC / 非 OPEC）。
    # ⚠️ 2026-10-10 起由**季度**改**月度**：用户提供 STEO base tables Excel
    #    （data/raw/eia_steo/oct26_base.xlsx / 3atab），里面有 2022-01~2027-12 共 72 个月的
    #    月度列，分辨率远高于季度。旧季度口径脚本 `steo_world.py` 已废弃不用，
    #    其键 steoQuarters / steoWorld / steoOpec / steoNonOpec / nonOpecDoCQuarter /
    #    othersQuarter 随之移除（DoC/Others 那两条拆分线本就依赖 MOMR，与月度口径不同源）。
    #    值是 mb/d 日均速率（月值即该月日均），**不得做任何月度加总/平均换算**。
    # 2026-10-16 换源：STEO 月度产量由「手工下载 base tables xlsx + 解析」改为
    # **EIA STEO 官方 API**（src/fetch/supply/steo_monthly.py），并随本步骤实时抓取，
    # 使 `python run.py build` 每月自动拿到最新一期（此前挂在 extract 步骤，build 不刷新）。
    # ⚠️ API 失败/返回空时回落 processed json（上次成功快照），保证流水线不中断。
    swm = None
    try:
        swm = steo_monthly.fetch()
    except Exception as exc:                      # 任何异常都不阻断流水线
        print(f"  [offline]  STEO 月度 API 抓取异常：{exc}")
    if not swm:
        print("  [offline]  STEO 月度 API 无数据，回落上次快照 steo_world_monthly.json")
        swm = load_processed("steo_world_monthly.json")
    out["steoMonths"] = swm.get("months", [])
    out["steoForecastStart"] = swm.get("forecastStart")
    out["steoForecastIndex"] = swm.get("forecastIndex")
    out["steoLastHistorical"] = swm.get("lastHistorical")
    out["steoWorldMonthly"] = (swm.get("world") or {}).get("crude", [])
    out["steoOpecMonthly"] = (swm.get("opec") or {}).get("crude", [])
    out["steoNonOpecMonthly"] = (swm.get("nonOpec") or {}).get("crude", [])
    out["steoWorldMeta"] = " | ".join(
        part for part in (swm.get("meta", ""), swm.get("source", "")) if part)
    # OPEC 11 国分项（EIA STEO API COPR_*，脚注 c 口径、不含阿联酋）。
    # ⚠️ 2026-10-11「OPEC 原油产量」图换源：MOMR 表 5-7 12 国 → 本键 11 国。
    #    72 月轴与 steoMonths 对齐；分国行仅历史段有值（预测月为 null），合计的
    #    预测段仍由 steoOpecMonthly 承载（徽章经 steoHistCut 标到末个历史月）。
    out["steoOpecMembers"] = swm.get("opecMembers", {})
    out["steoOpecMembersMeta"] = swm.get("opecMembersMeta", "")
    # OPEC+ 非 OPEC 参与国（DoC）10 国分项 + 合计（EIA STEO API COPR_*，脚注 b 的
    # other participants 段）。⚠️ 2026-10-11「Non-OPEC DoC 原油产量」图换源：
    # MOMR 表 5-7（31 月，2024-02 起）→ 本键（57 月历史段 2022-01 起，与全球图同轴）。
    # 分国行仅历史段有值（预测月为 null）；合计行含预测段，徽章经 steoHistCut 标到末个历史月。
    out["steoDocMembers"] = swm.get("docMembers", {})
    out["steoDoCTotal"] = swm.get("docTotal", [])
    out["steoDoCMeta"] = swm.get("docMembersMeta", "")

    return out


def _offline_demand():
    """需求侧离线产物：制造业 PMI / GDP 增速预期 / 中美炼厂高频指标。"""
    out = {}

    pmi = load_processed("pmi_data.json")
    out["pmiMonths"] = pmi.get("months", [])
    out["pmiUS"] = pmi.get("us", [])
    out["pmiChina"] = pmi.get("china", [])
    out["pmiEuro"] = pmi.get("euro", [])
    out["pmiMeta"] = pmi.get("meta", "")

    gdp = load_processed("gdp_expectation.json")
    out["gdpYears"] = gdp.get("years", [])
    out["gdpValues"] = gdp.get("values", [])
    out["gdpActual"] = gdp.get("actual", [])
    out["gdpMeta"] = gdp.get("meta", "")

    # IMF《WEO》期次面板（「逐期修正」图）。与上面的 GDP 快照同源 —— 都由
    # pmi_gdp.py 的 WOE_VINTAGES 期次矩阵派生，不在这里做任何二次计算。
    # growth 是按目标年分组的 {年份: [各期次值]}，前端按年取数组，故展开成扁平键。
    woe = load_processed("imf_woe.json")
    out["imfWoeMonths"] = woe.get("months", [])
    growth = woe.get("growth") or {}
    for year, seq in growth.items():
        out["imfWoe%sGrowth" % year] = seq
    out["imfWoeMeta"] = {
        "woeSrc": (woe.get("meta") or {}).get("woeSrc", ""),
        "latestKey": woe.get("latestKey", ""),
        # 页尾「IMF《世界经济展望》X 更新」中的 X 由这里派生，不再在 dashboard.js 里另写一遍
        "latestLabel": woe.get("latestLabel", ""),
        "vintages": woe.get("vintages", []),
    }

    # IMF 油价基准假设期次面板（「IMF 油价基准预测」图，挂在「未来展望」模块）。
    # 与上面 GDP 面板同源 —— 都由 pmi_gdp.py 的 WOE_OIL_VINTAGES 矩阵派生（同一套期次轴），
    # 这里只做扁平化展开，不做任何二次计算。
    # ⚠️ 按 WEO 辑（edition）分组：imfOilEditions = 按钮顺序（["2025","2026"]），
    # imfOilByEdition[辑年] = {months, price:{目标年:[各期次值]}, actual, meta}。
    # 前端卡片右上角用年份按钮在「2025 辑 / 2026 辑」间切换，各辑独立成图，
    # 不再把 2025 辑的「次年」与 2026 辑的「当年」拼到一张图（消除跨辑撞键 / 双线问题）。
    oil = load_processed("imf_woe_oil.json")
    out["imfOilEditions"] = oil.get("editions", [])
    out["imfOilByEdition"] = oil.get("byEdition", {})

    # EIA STEO 表 2 油价基准预测期次面板（「EIA 油价基准预测」图，outlook8）。
    # 与上面的 IMF 油价面板并列成「原油价格预测」组：全球只有这两家发布油价预测，
    # IEA / OPEC 只做需求预测。EIA 逐月发布（本地 10 期 PDF），频率比 IMF 的季度更细。
    # 由 src/extract/eia_steo_price.py 从各期 STEO PDF 表 2 提取，这里只扁平化展开，
    # 不做任何二次计算。⚠️ EIA 是 Brent 现货单一品种，IMF 是三品种简单平均，
    # 两者绝对值差 1~14 美元，横向对照只比修订路径（meta.口径 已写明）。
    steo = load_processed("eia_steo_price.json")
    steo_brent = steo.get("brent") or {}
    steo_vintages = steo.get("vintages", [])
    out["eiaSteoPriceMonths"] = steo_vintages
    out["eiaSteoBrent2026"] = [steo_brent.get(v, {}).get("Y2026") for v in steo_vintages]
    out["eiaSteoBrent2027"] = [steo_brent.get(v, {}).get("Y2027") for v in steo_vintages]
    # 已实现年份实际值：各期 PDF 表 2 的 2025 年度 Brent 均价（历史段，各期一致），
    # 取最新期那份；与 EIA 预测线同口径（Brent 现货），可直接比。
    latest_v = (steo.get("meta") or {}).get("latest", "") or (steo_vintages[-1] if steo_vintages else "")
    y2025 = steo_brent.get(latest_v, {}).get("Y2025")
    out["eiaSteoBrentActual2025"] = {"2025": y2025} if y2025 is not None else {}
    out["eiaSteoPriceMeta"] = {
        "steoSrc": steo.get("source", ""),
        "latest": latest_v,
        "frequency": (steo.get("meta") or {}).get("frequency", ""),
        "vintages": steo_vintages,
        "口径": (steo.get("meta") or {}).get("口径", ""),
    }

    ref = load_processed("refinery.json")
    for key in ("usUtilMonths", "usUtil", "usUtilMeta",
                "cnProcMonths", "cnProc", "cnProcMeta",
                "cnImportMonths", "cnImport", "cnImportMeta"):
        out[key] = ref.get(key, [])

    return out


if __name__ == "__main__":
    build()
