#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求侧 · 宏观先行指标：制造业 PMI（中美欧）与全球 GDP 增速预期。

产出 data/processed/pmi_data.json、gdp_expectation.json、imf_woe.json 与 imf_woe_oil.json。
注入 data/dataset/ 由 src/pipeline/build_dataset.py 统一负责，本模块不写域数据。

数据来源（见各 meta 字段）：
  - 制造业 PMI（中美欧）：data/raw/pmi_manufacturing.xlsx —— 手工维护的唯一事实来源。
      美国   = ISM 制造业 PMI（ISM Report On Business，季调）
      中国   = 国家统计局官方制造业 PMI（stats.gov.cn）
      欧元区 = HCOB 制造业 PMI（S&P Global / Hamburg Commercial Bank，终值）
      xlsx 缺失或读取失败时，回退到本文件内置的 FALLBACK_* 硬编码序列。
  - 全球 GDP 增速预期 / 油价基准假设：IMF《世界经济展望》（WEO，一年四期：1/4/7/10 月）。
      **唯一事实源是 WOE_VINTAGES 期次矩阵**（见下方），三份产物均由它派生：
        gdp_expectation.json = 最新期次那一行 + 历年实际值（KPI 芯片用）
        imf_woe.json         = GDP 期次面板（「逐期修正」图用）+ 页尾文案所需的最新期次标签
        imf_woe_oil.json     = 油价期次面板（「IMF 油价基准预测」图用，共用同一套期次轴/标签）
      新增一期 → 只在 WOE_VINTAGES 末尾追加一行即可，数值 / 页尾 / 修正图全部随之更新，
      不要再在别处（如 dashboard.js 的 source 文案）另写一遍期次。

维护方式：往 data/raw/pmi_manufacturing.xlsx 的「制造业PMI」表追加/修改行即可，
表头为 月份 | 美国 ISM | 中国 PMI | 欧元区 HCOB，月份格式 YYYY-MM。

运行：在仓库根目录执行 `python -m src.fetch.demand.pmi_gdp`
"""
import json, os

from src.common.deps import require_openpyxl
from src.paths import DATA_PROCESSED, DATA_RAW

# ---- 手工维护的 PMI 数据源（xlsx）----
PMI_XLSX = os.path.join(DATA_RAW, "pmi_manufacturing.xlsx")
PMI_SHEET = "制造业PMI"

# ---- 统一月份轴兜底：2024-07 .. 2026-09（27 个月）----
def mrange(start="2024-07", end="2026-09"):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1; y += 1
    return out

MONTHS = mrange()

# ---- 以下三段为兜底硬编码：仅当 xlsx 缺失/读取失败时使用 ----
# ⚠️ 2026-10-23 同步：与 data/raw/pmi_manufacturing.xlsx 保持一致。
#    美国 ISM 会在每年 1 月修订季调因子，2025-09/10/11 三期由首发值 49.1/48.7/48.2
#    修订为 48.9/48.8/48.0（Haver 2026-09 述评与 ISM 2026-09 报告「LAST 12 MONTHS」
#    表同源）。改任何一期都要同时改 xlsx 与这里，两处不一致时以 xlsx 为准。
# 美国 ISM 制造业 PMI
FALLBACK_US = {
 "2024-07":46.8,"2024-08":47.2,"2024-09":47.2,"2024-10":46.5,"2024-11":48.4,"2024-12":49.2,
 "2025-01":50.9,"2025-02":50.3,"2025-03":49.0,"2025-04":48.7,"2025-05":48.5,"2025-06":49.0,
 "2025-07":48.0,"2025-08":48.7,"2025-09":48.9,"2025-10":48.8,"2025-11":48.0,"2025-12":47.9,
 "2026-01":52.6,"2026-02":52.4,"2026-03":52.7,"2026-04":52.7, "2026-05":54.0,"2026-06":53.3,
 "2026-07":55.6,"2026-08":54.6,"2026-09":54.5,
}
# 中国 官方制造业 PMI
FALLBACK_CN = {
 "2025-01":49.1,"2025-02":50.2,"2025-03":50.5,"2025-04":49.0,"2025-05":49.5,"2025-06":49.7,
 "2025-07":49.3,"2025-08":49.4,"2025-09":49.8,"2025-10":49.0,"2025-11":49.2,"2025-12":50.1,
 "2026-01":49.3,"2026-02":49.0,"2026-03":50.4,"2026-04":50.3, "2026-05":50.0,"2026-06":50.3,
 "2026-07":49.2,"2026-08":49.8,"2026-09":50.1,
}
# 欧元区 HCOB 制造业 PMI
FALLBACK_EU = {
 "2025-01":45.1,"2025-02":46.6,"2025-03":47.6,"2025-04":48.6,"2025-05":49.0,"2025-06":49.4,
 "2025-07":49.5,"2025-08":49.8,"2025-09":50.7,"2025-10":49.8,"2025-11":50.0,"2025-12":49.6,
 "2026-01":48.8,"2026-02":49.5,"2026-03":50.8,"2026-04":52.2, "2026-05":51.6,"2026-06":51.4,
 "2026-07":52.0,"2026-08":52.7,"2026-09":52.9,
}


def load_pmi_xlsx(path=PMI_XLSX):
    """读取 data/raw/pmi_manufacturing.xlsx 的「制造业PMI」工作表。

    预期表头：月份 | 美国 ISM | 中国 PMI | 欧元区 HCOB（月份形如 2024-01）。
    返回 (months, us_map, cn_map, eu_map)，months 升序；失败返回 None。
    """
    if not os.path.exists(path):
        print(f"  [demand]  {path} 不存在，PMI 回退到内置数据")
        return None
    try:
        wb = require_openpyxl().load_workbook(path, data_only=True)
        ws = wb[PMI_SHEET]
    except Exception as e:
        print(f"  [demand]  读取 {path} 失败: {e}，PMI 回退到内置数据")
        return None

    headers = [c.value for c in ws[1]]

    def _idx(name, default):
        try:
            return headers.index(name)
        except ValueError:
            return default

    i_m = _idx("月份", 0)
    i_us = _idx("美国 ISM", 1)
    i_cn = _idx("中国 PMI", 2)
    i_eu = _idx("欧元区 HCOB", 3)

    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        raw = row[i_m] if i_m < len(row) else None
        if raw is None:
            continue
        if isinstance(raw, str):
            month = raw.strip()
        else:
            month = str(raw).strip()
        if len(month) >= 7 and month[4] == "-":
            month = month[:7]
        else:
            continue

        def _v(i):
            if i >= len(row):
                return None
            x = row[i]
            if x is None or x == "":
                return None
            try:
                return float(x)
            except (ValueError, TypeError):
                return None

        out[month] = (_v(i_us), _v(i_cn), _v(i_eu))

    wb.close()
    if not out:
        print(f"  [demand]  {path} 无有效数据行，PMI 回退到内置数据")
        return None
    months = sorted(out)
    print(f"  [demand]  制造业 PMI xlsx：读取 {len(months)} 个月，{months[0]} ~ {months[-1]}")
    return (
        months,
        {m: out[m][0] for m in months},
        {m: out[m][1] for m in months},
        {m: out[m][2] for m in months},
    )


def build_pmi():
    """优先取 xlsx，否则回退内置硬编码；返回 pmi 字典。"""
    got = load_pmi_xlsx()
    if got:
        months, um, cm, em = got
        source = "data/raw/pmi_manufacturing.xlsx（手工维护）"
    else:
        months, um, cm, em = MONTHS, FALLBACK_US, FALLBACK_CN, FALLBACK_EU
        source = "内置硬编码兜底（xlsx 不可用）"
        print("  [demand]  制造业 PMI 使用内置 fallback 数据")

    us_v = [um.get(m) for m in months]
    cn_v = [cm.get(m) for m in months]
    eu_v = [em.get(m) for m in months]

    last = months[-1]
    tail = []
    for name, arr in (("美国", us_v), ("中国", cn_v), ("欧元区", eu_v)):
        if arr[-1] is not None:
            tail.append(f"{name} {arr[-1]}")
    latest_note = f"最新 {last}：" + "、".join(tail) + "。" if tail else ""

    meta = (
        "制造业 PMI（月度，%）。美国=ISM 制造业 PMI（ISM Report On Business，季调）；"
        "中国=国家统计局官方制造业 PMI（stats.gov.cn）；欧元区=HCOB 制造业 PMI"
        "（S&P Global / Hamburg Commercial Bank，终值）。50 为荣枯线：>50 扩张，<50 收缩。"
        f"数据覆盖 {months[0]}~{months[-1]}（{len(months)} 个月），来源 {source}。"
        f"{latest_note}"
    )
    return {
        "months": months,
        "us": us_v,
        "china": cn_v,
        "euro": eu_v,
        "meta": meta,
        "retrieved": "2026-10-04",
    }


# ---- 全球 GDP 增速预期 & 油价基准假设（IMF《世界经济展望》，一年四期：1/4/7/10 月）----
# ⚠️ 2026-10-13 重构为「**期次矩阵**单一事实源」。此前只存最新一期，导致三处各写一遍、
#    改期次必漏改（实测：数值已换 10 月期、页尾文案仍写 7 月）。现在一切由本表派生：
#      gdp_expectation.json  = 最新期次那一行 + 历年实际值（KPI 芯片 / 图表用）
#      imf_woe.json          = GDP 期次面板（「逐期修正」图用）+ 页尾文案所需的期次标签
#      imf_woe_oil.json      = 油价期次面板（「IMF 油价基准预测」图用，同一套期次标签）
#    2026-10-14 增油价列：WEO 不做供需平衡预测，但在「全球假设」里按期货曲线给出
#    **油价基准假设**（口径 = Brent / Dubai Fateh / WTI 三者简单平均，美元/桶）。
#    GDP 与油价共用同一份期次轴，因此放在同一张矩阵里，绝不会各写一遍导致错期。
#    WEO 一年四期：1 月 / 7 月为 Update（更新），4 月 / 10 月为正刊。
#
# 期次矩阵：每行 5 项 ——
#   0 期次键（YYYY-MM）
#   1 期次中文标签
#   2 {目标年: 该期次对这一年的全球增速预测 %}
#   3 {目标年: 该期次对这一年的油价基准假设 美元/桶}（口径见 OIL_BASIS）
#   4 该期次假设所依据的期货曲线截止日（原文标注才有；10 月期未见标注故留空）
# 新增一期只需在末尾追加一行，其余全部自动派生。
# ---- 期次矩阵：每行 5 项 ——
#   0 期次键（YYYY-MM）
#   1 期次中文标签
#   2 {目标年: 该期次对这一年的全球增速预测 %}（GDP 面板用）
#   3 {目标年: 该期次对这一年的油价基准假设 美元/桶}（口径见 OIL_BASIS，油价面板用）
#   4 该期次假设所依据的期货曲线截止日（原文标注才有；10 月期未见标注故留空）
# 新增一期只需在对应列表末尾追加一行，数值 / 页尾 / 修正图全部随之更新。
#
# ⚠️ 2026-10-14 重构：GDP 面板与油价面板**期次范围不同**，拆成两张矩阵：
#   WOE_VINTAGES       —— GDP 面板源（imf_woe / gdp_expectation）：仅 2026 辑四期（不变）。
#   WOE_OIL_VINTAGES   —— 油价面板源（imf_woe_oil）：含 2025 辑四期 + 2026 辑四期，
#                          目标年 = 2025 / 2026 / 2027，其中 2026 同时作为 2025 辑「次年」
#                          与 2026 辑「当年」出现，渲染层自动拼接成一条连续修订路径
#                          （即用户提出的「同目标年跨辑」问题，不再有两条 2026 曲线）。
_W26 = [
    ("2026-01", "2026 年 1 月更新（WEO Update, January 2026）",  {2026: 3.3, 2027: 3.2},
     {2026: 62.13, 2027: 62.17}, "2025-11-20"),
    ("2026-04", "2026 年 4 月（WEO April 2026）",                {2026: 3.1, 2027: 3.2},
     {2026: 82.22, 2027: 75.97}, "2026-03-10"),
    ("2026-07", "2026 年 7 月更新（WEO Update, July 2026）",     {2026: 3.0, 2027: 3.4},
     {2026: 89.27, 2027: 78.70}, "2026-06-10"),
    ("2026-10", "2026 年 10 月 13 日更新（WEO October 2026）",   {2026: 3.1, 2027: 3.4},
     {2026: 95.74, 2027: 87.39}, ""),
]
# 2025 辑 WEO 四期油价基准假设（Brent / 迪拜法塔赫 / WTI 三品种简单平均，官方数字）：
#   2025-01 futures as of 2024-11-20 → 2025 = 69.76 / 2026 = 67.96
#   2025-04                        → 2025 = 66.94 / 2026 = 62.38
#   2025-07 futures as of 2025-06-26 → 2025 = 68.18 / 2026 = 64.33
#   2025-10                        → 2025 = 68.92 / 2026 = 65.84
# 来源：IMF《WEO》2025 年四期官方「全球假设」（Jan/Apr/Jul/Oct 2025 WEO 的期次附录/脚注）。
# ⚠️ GDP 列（第 3 元组元素）留空 {}：油价面板期次范围与 GDP 面板不同，此处 GDP 值不参与
#   任何图表；若日后 GDP 面板也要回溯 2025 辑，再按官方四期 GDP 预测回填即可。
_W25_OIL = [
    ("2025-01", "2025 年 1 月更新（WEO Update, January 2025）", {},
     {2025: 69.76, 2026: 67.96}, "2024-11-20"),
    ("2025-04", "2025 年 4 月（WEO April 2025）",                {},
     {2025: 66.94, 2026: 62.38}, "2025-03-10"),
    ("2025-07", "2025 年 7 月更新（WEO Update, July 2025）",     {},
     {2025: 68.18, 2026: 64.33}, "2025-06-26"),
    ("2025-10", "2025 年 10 月（WEO October 2025）",            {},
     {2025: 68.92, 2026: 65.84}, "2025-08-29"),
]
WOE_VINTAGES = _W26                       # GDP 面板源（不变）
WOE_OIL_VINTAGES = _W25_OIL + _W26        # 油价面板源（含 2025 辑）
# 已实现年份的实际值（不随期次滚动；2025 取 10 月期正文披露的 3.5）
GDP_ACTUAL = {2024: 3.3, 2025: 3.5}
# 已实现年份的油价实际值（同样不随期次滚动）。67.74 是 WEO 原文（2026 年 4 月期脚注 8 /
# 10 月期报道）明确披露的 2025 年「石油现货价格指数」年均值。
OIL_ACTUAL = {2025: 67.74}
# 油价口径说明（写进 meta，前端页尾直接引用，避免各图各写一套措辞）
OIL_BASIS = "英国布伦特、迪拜法塔赫和西得克萨斯中质原油价格的简单平均值（美元/桶）"
# GDP「逐期修正」图展示的目标年（= 当年与次年，与 IEA OMR / OPEC MOMR / EIA STEO 三张修正图同一口径）。
# 油价面板的目标年由 WOE_OIL_VINTAGES 动态收集，不在此硬编码（见 _derive_woe_oil）。
TARGET_YEARS = [2026, 2027]


def _derive_gdp():
    """由期次矩阵派生「最新期次快照」：历年实际值 + 最新期次对目标年的预测。"""
    latest = WOE_VINTAGES[-1][2]
    years = sorted(list(GDP_ACTUAL.keys()) + TARGET_YEARS)
    values, actual = [], []
    for y in years:
        if y in GDP_ACTUAL:
            values.append(GDP_ACTUAL[y]); actual.append(True)
        else:
            values.append(latest.get(y)); actual.append(False)
    vk, vlabel, _, _, _ = WOE_VINTAGES[-1]
    return {
        "years": [str(y) for y in years],
        "values": values,
        "actual": actual,
        "meta": ("全球GDP增速预期（年度，%）。来源：IMF《世界经济展望》"
                 + vlabel + "：全球经济增长 "
                 + "、".join("%d=%.1f%%" % (y, latest[y]) for y in TARGET_YEARS)
                 + "（最新期次值，由 src/fetch/demand/pmi_gdp.py 的 WOE_VINTAGES 期次矩阵自动派生，"
                   "改期次只需改矩阵）。"
                 + "2024/2025 为实际值，2026/2027 为基金组织最新预期。"
                 + "注：WEO 一年四期（1/4/7/10 月），非月度频率；各期次对同一目标年的预测见「逐期修正」图。"),
        "retrieved": vk,   # 最新期次键（YYYY-MM），供下游取用
    }


def _derive_woe():
    """由期次矩阵派生「逐期修正」面板：期次序列 × 每个目标年一条线。"""
    months = [v[0] for v in WOE_VINTAGES]
    series = {}
    for y in TARGET_YEARS:
        series[y] = [v[2].get(y) for v in WOE_VINTAGES]
    vk, vlabel, _, _, _ = WOE_VINTAGES[-1]
    return {
        "months": months,
        "growth": {str(y): series[y] for y in TARGET_YEARS},   # {"2026": [...], "2027": [...]}
        "vintages": [{"key": v[0], "label": v[1]} for v in WOE_VINTAGES],
        "latestKey": vk,
        "latestLabel": vlabel,
        "meta": {
            "woeSrc": ("数据：取自 IMF《世界经济展望》各期次对全球增速的预测值 —— "
                       "1 月 / 7 月为 Update、4 月 / 10 月为正刊，一年四期；"
                       "本图展示各期次对 %d / %d 年预测的滚动修订路径"
                       "（源文件：手工维护于 src/fetch/demand/pmi_gdp.py 的 WOE_VINTAGES）。"
                       % (TARGET_YEARS[0], TARGET_YEARS[1])),
        },
        "retrieved": vk,
    }


def _derive_woe_oil():
    """由油价期次矩阵派生「IMF 油价基准预测」面板，**按 WEO 辑（edition）分组**。

    每一辑（2025 辑 / 2026 辑）= 一个独立视图：含该辑的 4 个期次与其预测的目标年
    （当年 + 次年）。前端在卡片右上角用年份按钮在「2025 辑 / 2026 辑」之间切换，
    各辑互不叠加 → 彻底规避「同目标年跨辑出现两次」的撞键 / 双线问题
    （2026 同时作为 2025 辑次年与 2026 辑当年，在两辑里各自成线，但分属不同页面，
     不会出现在同一张图上）。未来 WEO 出 2027 辑，只须在 WOE_OIL_VINTAGES 追加该行、
     按钮自动多出「2027」一项。

    ⚠️ 与 _derive_woe（GDP 面板）同源于 pmi_gdp.py，但 GDP 面板仍按单矩阵 WOE_VINTAGES
    （仅 2026 四期）渲染；此处用 WOE_OIL_VINTAGES（2025 四期 + 2026 四期），两套矩阵
    共用同一套期次轴，只是范围不同。
    """
    # 按发布年（期次键前 4 位）把期次行归到各辑
    editions_rows = {}
    for v in WOE_OIL_VINTAGES:
        yr = v[0][:4]
        editions_rows.setdefault(yr, []).append(v)
    editions = sorted(editions_rows.keys())  # ["2025", "2026"]，升序

    by_edition = {}
    for yr in editions:
        rows = editions_rows[yr]
        months = [r[0] for r in rows]
        oil_years = set()
        for r in rows:
            oil_years.update(r[3].keys())
        oil_years = sorted(oil_years)            # 该辑预测的目标年（当年 + 次年）
        price = {y: [r[3].get(y) for r in rows] for y in oil_years}
        vk, vlabel, _, _, _ = rows[-1]
        # 参考线①= **本辑当年**的实际值（口径同预测线），用于「WEO 逐期修订 vs 该年真实落点」。
        # ⚠️ 2026-10-15 订正：此前取「全局最新已实年份」，导致 2026 辑也画 2025 实际 67.74
        #    —— 与该辑主题（2026 / 2027 假设）无关，属跨年串味。现按辑取当年：
        #      2025 辑 → 2025 实际 67.74（OIL_ACTUAL 有）
        #      2026 辑 → 需 2026 官方全年实际，而 2026 年尚未走完、OIL_ACTUAL 未收录
        #                → actual 为空，该辑**不画**参考线。
        #    ⚠️ 绝不拿「年内迄今均值」冒充全年实际（口径不同且未走完，会误导）。
        #    待 WEO 披露 2026 全年实际后，只需往 OIL_ACTUAL 加一行，2026 辑自动出现该线。
        actual = {}
        ay = int(yr)
        if ay in OIL_ACTUAL:
            actual = {yr: OIL_ACTUAL[ay]}
        by_edition[yr] = {
            "months": months,
            # {"2025":[...4], "2026":[...4]}（2025 辑）/ {"2026":[...4], "2027":[...4]}（2026 辑）
            "price": {str(y): price[y] for y in oil_years},
            # 已实现年份的实际值（不随期次滚动）：{"2025": 67.74}
            "actual": actual,
            "meta": {
                "edition": yr,
                "oilSrc": (
                    "数据：取自 IMF《世界经济展望》每年各期次（1/4/7/10 月 Update / 正刊）"
                    "「全球假设」中的石油价格基准值 —— 口径为Brent/Dubai/WTI 的简单平均值，"
                    "由期货市场推导，（源文件：手工维护于 src/fetch/demand/pmi_gdp.py 的 WOE_OIL_VINTAGES）。"
                ),
                # 最新一期对全部目标年的假设值，供 KPI / 页尾直接引用
                "latest": {str(y): rows[-1][3].get(y) for y in oil_years},
                "futuresAsOf": rows[-1][4],
                "vintages": [{"key": r[0], "label": r[1], "futuresAsOf": r[4]} for r in rows],
                "boundary": None,   # 分辑展示后无需跨辑边界标注
            },
        }
    return {
        "editions": editions,
        "byEdition": by_edition,
        "retrieved": WOE_OIL_VINTAGES[-1][0],
    }


gdp = _derive_gdp()
woe = _derive_woe()
woe_oil = _derive_woe_oil()


def main():
    """写出中间产物到 data/processed/（pmi_data / gdp_expectation / imf_woe）。"""
    pmi = build_pmi()
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    with open(os.path.join(DATA_PROCESSED, "pmi_data.json"), "w") as f:
        json.dump(pmi, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_PROCESSED, "gdp_expectation.json"), "w") as f:
        json.dump(gdp, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_PROCESSED, "imf_woe.json"), "w") as f:
        json.dump(woe, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_PROCESSED, "imf_woe_oil.json"), "w") as f:
        json.dump(woe_oil, f, ensure_ascii=False, indent=2)

    print("PMI months:", len(pmi["months"]), pmi["months"][0], "->", pmi["months"][-1])
    print("US non-null :", sum(1 for x in pmi["us"] if x is not None))
    print("CN non-null :", sum(1 for x in pmi["china"] if x is not None))
    print("EU non-null :", sum(1 for x in pmi["euro"] if x is not None))
    print("GDP years  :", gdp["years"], gdp["values"], "(派生自期次", gdp["retrieved"], ")")
    print("WEO 期次    :", woe["months"])
    for y in TARGET_YEARS:
        print("  %d 增速路径:" % y, woe["growth"][str(y)])
    print("WEO 油价辑   :", woe_oil["editions"])
    for yr in woe_oil["editions"]:
        ed = woe_oil["byEdition"][yr]
        print("  %s 辑期次:" % yr, ed["months"], "目标年:", sorted(int(k) for k in ed["price"]))
        for y in ed["price"]:
            print("    %s 油价假设路径:" % y, ed["price"][y])
    print("已写出 data/processed/{pmi_data,gdp_expectation,imf_woe,imf_woe_oil}.json")


if __name__ == "__main__":
    main()
