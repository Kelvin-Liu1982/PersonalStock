#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原油看板数据层：按数据域分文件存储域数据。

- ``load_data()``  读取 data/dataset/*.json 并合并成单一 dict（供渲染与增量注入使用）。
- ``save_data(d)`` 按 GROUPS 把 dict 拆写回各域文件。

合并后的 dict 与单文件存储在内容上完全等价；拆分只是磁盘组织方式，
不影响渲染出的 HTML（SNAPSHOT 仍是同一个合并对象）。

注意：GROUPS 的键顺序决定了合并后 dict 的键顺序，也就决定了注入 HTML 的
SNAPSHOT 字段顺序。调整顺序会改变产物字节，修改前请确认是否必要。
"""
import json, os

from src.paths import DATASET_DIR as DATA_DIR

# 顶级 key -> 域文件名（每个 key 仅归属一个文件）
GROUPS = {
    "meta.json":    ["meta"],
    "prices.json":  ["dates", "brent", "wti", "dxy", "dff", "dgs10", "gas", "gasSupplied",
                     "ovx", "crack", "spread_bw", "brentCot", "brentTerm", "brentTermMeta",
                     "ret", "vol20", "dxy_chg5",
                     "composite", "corr"],
    "eia.json":     ["eiaWeekly", "eiaDates", "eia"],
    # brentMonthly = Brent 月均价（{YYYY-MM: v}），2026-10-07 起叠加在剩余产能图上做右轴，
    # 归在 opec.json 域是因为它只服务那一张图（刻意不进 prices.json，免得被误当价格基准）。
    # 2026-10-11「OPEC 原油产量」与「Non-OPEC DoC 原油产量」双图换源（MOMR → STEO 表 3d）后，
    # 旧键 opecMonthly/opecMonthlyCountries/opecMonths/opecMonthlyMeta 与
    # nonOpecDoCMonths/nonOpecDoCTotal/nonOpecDoCCountries/nonOpecDoCMeta 已随 build_dataset 移除；
    # opec.json 域现只承载：剩余产能（EIA）+ OPEC 年度序列 + Brent 月均价。
    "opec.json":    ["opecSpare", "opecSpareMonths", "opec", "opecYears",
                     "brentMonthly"],
    # 全球视角（EIA STEO 官方 API COPR_* **月度**口径）：世界 / OPEC / 非 OPEC 三条原油线。
    # 刻意单开一域：它们 Frequency=月度、口径=原油，与 opec.json 的月度二手来源不是一回事。
    # ⚠️ 2026-10-10 由季度改月度（数据源换成 STEO base tables Excel 的 3atab），
    #    旧季度键 steoQuarters/steoWorld/steoOpec/steoNonOpec/nonOpecDoCQuarter/othersQuarter
    #    已随 build_dataset 一并移除。
    # ⚠️ 2026-10-16 再换源：xlsx 手工下载 → **EIA STEO 实时 API**（数据集随 dataset 步骤刷新），
    #    预测边界 forecastStart/Index 由 API 分国行最后非空月推导（不再依赖 Dates 表）。
    "world.json":   ["steoMonths", "steoWorldMonthly", "steoOpecMonthly", "steoNonOpecMonthly",
                     "steoWorldMeta", "steoForecastStart", "steoForecastIndex",
                     "steoLastHistorical",
                     # OPEC 11 国分项（STEO API COPR_*，2026-10-11 起供「OPEC 原油产量」图）
                     "steoOpecMembers", "steoOpecMembersMeta",
                     # OPEC+ 非 OPEC 参与国（DoC）10 国分项 + 合计（COPR_OPECPLUS_OTHER，
                     # 2026-10-11 起供「Non-OPEC DoC 原油产量」图）
                     "steoDocMembers", "steoDoCTotal", "steoDoCMeta"],
    "stocks.json":  ["usSpr", "usSprMonths", "usSprMeta",
                     "oecdCrude", "oecdMonths", "oecdProducts", "oecdTotal", "oecdMeta"],
    "rig.json":     ["rigWorld", "rigMonths", "rigMonthlyMeta"],
    "macro.json":   ["pmiMonths", "pmiUS", "pmiChina", "pmiEuro", "pmiMeta",
                     "gdpYears", "gdpValues", "gdpActual", "gdpMeta",
                     # IMF《WEO》期次面板（与 GDP 快照同源于 pmi_gdp.py 的 WOE_VINTAGES 矩阵）
                     "imfWoeMonths", "imfWoe2026Growth", "imfWoe2027Growth", "imfWoeMeta",
                     "usUtilMonths", "usUtil", "usUtilMeta"],
    "china.json":   ["cnProcMonths", "cnProc", "cnProcMeta",
                     "cnImportMonths", "cnImport", "cnImportMeta"],
    # IEA 预测体系（OMR 月度滚动修正 +《Oil 20XX》中期展望），2026-09 新增「未来展望」看板
    "iea_forecast.json": ["ieaOmrMonths", "ieaOmr2026Demand", "ieaOmr2027Demand",
                         "ieaOmrWarOnset", "ieaOutlookYears", "ieaOutlook2023",
                         "ieaOutlook2024", "ieaOutlook2025", "ieaOutlookMeta"],
    # OPEC 预测体系（MOMR 月度滚动修正 + WOO 2026 长期展望），与 IEA 侧并列
    "opec_forecast.json": ["opecMomrMonths", "opecMomr2026Demand", "opecMomr2027Demand",
                          "opecMomrWarOnset", "opecWooYears", "opecWooDemand",
                          "opecWoo2025", "opecWoo2024", "opecWoo2023",
                          "opecForecastMeta"],
    # EIA 预测体系（STEO 月度滚动 + AEO 美国长期展望）；注意 IEO 已停滞，无全球长期对等品
    "eia_forecast.json": ["eiaSteoMonths", "eiaSteo2026Demand", "eiaSteo2027Demand",
                         "eiaSteoWarOnset", "eiaAeoYears", "eiaAeoConsHigh",
                         "eiaAeoConsLow", "eiaAeoCaseHigh", "eiaAeoCaseLow",
                         "eiaAeoConsBase", "eiaAeoCaseBase",
                         # EIA STEO 表 2 油价基准预测（outlook8，2026-10-14 新增；
                         # 与 imf_forecast.json 的 imfOil* 并列成「原油价格预测」组）
                         "eiaSteoPriceMonths", "eiaSteoBrent2026", "eiaSteoBrent2027",
                         "eiaSteoBrentActual2025", "eiaSteoPriceMeta",
                         "eiaForecastMeta"],
    # IMF 预测体系（WEO「全球假设」中的油价基准值，按 WEO 辑分组逐期修正，2026-10-14 新增）。
    # 与 macro.json 里的 imfWoe*（GDP）同源于 pmi_gdp.py 的 WOE_VINTAGES 矩阵，但服务对象
    # 是「未来展望」模块的油价图，故单开一域、命名 imfOil*。
    # ⚠️ 2026-10-14（续）重构：由「按目标年写死键名」改为「按 WEO 辑分组」
    # （imfOilEditions = 按钮顺序 + imfOilByEdition[辑年] = 该辑视图数据），
    # 前端右上角年份按钮在 2025 / 2026 辑之间切换，各辑独立成图（解决跨辑重复目标年）。
    "imf_forecast.json": ["imfOilEditions", "imfOilByEdition"],
    # igeo / igeoBreak 自 2026-09-27 起随 dims 一起落库：地缘维度已在 ETL 期由
    # score/geo.py 计算（此前只在渲染期算，save_data 会因未知 key 抛错）。
    "risk.json":    ["dims", "igeo", "igeoBreak", "alerts", "events", "kpis"],
    # 原油快讯（2026-10-15 新增，取代原「各维度风险贡献（当前）」卡位）。
    # ⚠️ **纯手工维护域**：Argus 站点有反爬（curl 一律 HTTP 202 + 0 字节），
    #    `src/fetch/` 抓不到，也没有 extract 脚本；数据由 Argus 原油页
    #    （/en/commodities/crude）人工摘录后写在这里，改完跑 `run.py html` 即可。
    #    仅存 title / url / date / source 四项，前端只渲染「标题 + 超链接」。
    "news.json":    ["crudeNews", "crudeNewsMeta"],
}

# 反向映射：key -> 文件名
KEY_TO_FILE = {k: fn for fn, keys in GROUPS.items() for k in keys}


def load_data():
    """读取所有域文件并合并为单一 dict（按 GROUPS 顺序，便于稳定排序）。"""
    data = {}
    for fn in GROUPS:
        p = os.path.join(DATA_DIR, fn)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as handle:
                data.update(json.load(handle))
    return data


def save_data(data):
    """按 GROUPS 把 data 拆写回各域文件。未知 key 会抛错（防静默丢数据）；
    某域文件中属于该域的 key 全缺时跳过写（保留磁盘上已有内容，避免误清空）。

    ⚠️ 2026-10-14 修：按域**合并**写，不再整域覆盖。
    背景：iea / opec / eia 三个预测体系的域文件是**手工维护**的（README 数据表注明
    「手工维护于 data/dataset/*.json」），build_dataset 不产出它们的键。此前只要
    某个域有**任何一个** key 由 build_dataset 产出（如 10-14 新增的 eiaSteoPrice*），
    整域就会被只含新键的内容覆盖，手工维护的旧键全部丢失 —— 当天 eia_forecast.json
    的 eiaSteoMonths / eiaAeo* / eiaForecastMeta 就是这么没的（从事会话记录恢复）。
    现改为：先读磁盘上该域现有内容，再用 data 里的新值覆盖同名键，
    属于该域但两边都没有的键依然不写。已退役的源要清键，需显式删文件或改 GROUPS。
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    unknown = [k for k in data if k not in KEY_TO_FILE]
    if unknown:
        raise KeyError("未归入任何域文件的 key: " + ", ".join(unknown))
    written = 0
    for fn, keys in GROUPS.items():
        fresh = {k: data[k] for k in keys if k in data}
        if not fresh:  # 该域本次无任何新数据，整域不动
            continue
        path = os.path.join(DATA_DIR, fn)
        merged = dict(fresh)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as handle:
                    old = json.load(handle)
            except (ValueError, OSError):
                old = {}
            # 磁盘上属于该域、且未被本次数据覆盖的键原样保留（手工维护内容）
            for k in keys:
                if k in old and k not in fresh:
                    merged[k] = old[k]
        _write_json(path, merged)
        written += 1
    return written


def _write_json(path, obj):
    """写 JSON（显式 with 关闭句柄；不加 encoding 会跟随系统 locale，产物不可复现）。"""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2)


def split_existing(path):
    """一次性迁移：把旧的单文件拆成域文件（不删除原文件）。"""
    with open(path, encoding="utf-8") as handle:
        d = json.load(handle)
    n = save_data(d)
    return d, n
