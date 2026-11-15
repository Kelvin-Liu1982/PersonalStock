# -*- coding: utf-8 -*-
"""供给侧 · 世界 / OPEC / 非 OPEC 的**月度**原油产量 —— EIA STEO 官方 API。

2026-10-16 换源：由「STEO base tables Excel（3atab / 3dtab）**手工下载** + openpyxl 解析」
改为 **EIA STEO 官方 API**（`/v2/steo/data/`，月度，与周度 WPSR 同为 EIA v2、同一把 key）。
⚠️ 只换**取数方式**，输出契约（data/processed/steo_world_monthly.json 的键）保持不变，
   故 build_dataset.py 无需改动即可继续消费。

序列口径（**COPR_* = Crude Oil Production，仅原油，百万桶/日**）：
    世界      COPR_WORLD
    OPEC      COPR_OPEC
    非 OPEC   COPR_NONOPEC
    OPEC 11 国分项（脚注 c，**不含阿联酋**）  COPR_SA/IZ/IR/KU/VE/NI/LY/AG/CF/EK/GB
    DoC 10 国分项（OPEC+ 非 OPEC 参与国）    COPR_RS/KZ/MX/MU/AJ/MY/OD/BX/BA/SU
    DoC 合计                                COPR_OPECPLUS_OTHER
⚠️ 勿混用 COPC_*（产能）与 PAPR_*（液体总量，含凝析油）—— 本图标题是「**原油**产量」。

与换源前 xlsx 口径一致、已实测复刻（2026-10-16 @2026-09 逐项数值吻合，4 合计 + 21 分国）：
  ① 分国行**只有历史段有值**（预测月 API 返回空），合计行才有预测段；
  ② 因此**预测边界可由「任一分国行最后一个非空月」反推**（= lastHistorical，次月即
     forecastStart），不再依赖 xlsx 的 Dates 表；
  ③ API 起点是 1993-01，而看板窗口自 **2022-01** 起，故按 WINDOW_START 截断，
     否则图会被拉长到 30 余年。
  ④ API 只给**最新一期** STEO（无历史 vintage）—— 本图只需「最新一期的历史+预测」，
     故无影响（与 outlook8 的逐期修订图不同，那张必须继续用 PDF）。

恒等式：OPEC + 非 OPEC == 世界（原油），容差 0.05，脚本内自验。
预测守卫：若 API 未给出预测数据（无边界或预测段全空），按需求**直接删除预测段**。

运行：仓库根目录 `python -m src.fetch.supply.steo_monthly`（抓 API 并写 processed json）。
"""
import json
import os
import urllib.parse

from src import config
from src.common.http import fetch_json_curl
from src.paths import DATA_PROCESSED

# 看板窗口起点：与换源前 xlsx 的 72 月窗口左端一致。API 实际从 1993-01 起，必须截断。
WINDOW_START = "2022-01"

# 三组合计（原油）
GROUPS = [("world", "世界合计"), ("opec", "OPEC"), ("nonOpec", "非 OPEC")]
SERIES = {"world": "COPR_WORLD", "opec": "COPR_OPEC", "nonOpec": "COPR_NONOPEC"}

# OPEC 11 国分项（脚注 c：阿尔及利亚/刚果/赤道几内亚/加蓬/伊朗/伊拉克/科威特/利比亚/
# 尼日利亚/沙特/委内瑞拉，**不含阿联酋**，≠ MOMR 表 5-7 的 12 国口径）。
# ⚠️ 中文名既是 json 的键、也是前端图例文本（「刚果」2026-10-11 按用户要求简写），
#    改这里必须同步 dashboard.js 的 major 与校验脚本的 EXPECT 键。
OPEC_MEMBERS = [
    ("COPR_SA", "沙特"), ("COPR_IZ", "伊拉克"), ("COPR_IR", "伊朗"), ("COPR_KU", "科威特"),
    ("COPR_VE", "委内瑞拉"), ("COPR_NI", "尼日利亚"), ("COPR_LY", "利比亚"),
    ("COPR_AG", "阿尔及利亚"), ("COPR_CF", "刚果"), ("COPR_EK", "赤道几内亚"),
    ("COPR_GB", "加蓬"),
]

# OPEC+ 里的**非 OPEC** 参与国（DoC，10 国，脚注 b 的 other participants）
DOC_MEMBERS = [
    ("COPR_RS", "俄罗斯"), ("COPR_KZ", "哈萨克斯坦"), ("COPR_MX", "墨西哥"), ("COPR_MU", "阿曼"),
    ("COPR_AJ", "阿塞拜疆"), ("COPR_MY", "马来西亚"), ("COPR_OD", "南苏丹"),
    ("COPR_BX", "文莱"), ("COPR_BA", "巴林"), ("COPR_SU", "苏丹"),
]
DOC_TOTAL = "COPR_OPECPLUS_OTHER"

# 预测边界探针：任一分国行即可（分国行只有历史段有值，其最后非空月 = lastHistorical）
BOUNDARY_PROBE = "COPR_SA"

# 单次请求批量取的序列（合计 3 + OPEC 11 + DoC 10 + DoC 合计 1 = 25）
_ALL_IDS = [SERIES[k] for k in ("world", "opec", "nonOpec")] \
    + [sid for sid, _ in OPEC_MEMBERS] \
    + [sid for sid, _ in DOC_MEMBERS] + [DOC_TOTAL]


def _next_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    m += 1
    if m > 12:
        y, m = y + 1, 1
    return "%04d-%02d" % (y, m)


def _month_range(start, end):
    """闭区间 [start, end] 的 YYYY-MM 列表。"""
    out, cur = [], start
    while cur <= end:
        out.append(cur)
        cur = _next_month(cur)
        if len(out) > 1200:      # 安全阀，防死循环
            break
    return out


def _fetch_all():
    """一次请求抓全部序列，返回 ``{seriesId: {period: float}}``。失败返回 {}。"""
    params = [("frequency", "monthly"), ("data[0]", "value"),
              ("sort[0][column]", "period"), ("sort[0][direction]", "asc"),
              ("length", "5000"), ("start", WINDOW_START)]
    for sid in _ALL_IDS:
        params.append(("facets[seriesId][]", sid))
    url = ("https://api.eia.gov/v2/steo/data/?" + urllib.parse.urlencode(params)
           + "&api_key=" + config.EIA_KEY)
    payload = fetch_json_curl(url, timeout=60, curl_retry=3)
    out = {}
    for row in (payload or {}).get("response", {}).get("data", []):
        sid, period, value = row.get("seriesId"), row.get("period"), row.get("value")
        if not sid or not period or value is None:
            continue
        try:
            out.setdefault(sid, {})[period] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def fetch():
    """抓 API 并组装成 processed json 的结构（dict）。失败/空返回 None。"""
    raw = _fetch_all()
    world_raw = raw.get(SERIES["world"]) or {}
    if not world_raw:
        print("  [supply]  steo monthly: 世界序列为空（API 失败？），放弃")
        return None

    # 窗口：WINDOW_START → 世界合计最后一个有值的月
    end = max(world_raw)
    months = _month_range(WINDOW_START, end)
    print("  [supply]  steo monthly: %d 序列, 窗口 %s ~ %s (%d 月)"
          % (len(raw), months[0], months[-1], len(months)))

    # 预测边界：分国探针的最后一个非空月 = 末个历史月，次月即预测起点
    probe = raw.get(BOUNDARY_PROBE) or {}
    last_hist = max(probe) if probe else None
    fc = _next_month(last_hist) if last_hist else None
    fc_i = months.index(fc) if (fc and fc in months) else None
    if fc_i is None:
        # 预测起点不在窗口内 ⇒ 本期窗口里根本没有预测段（如 EIA 只给到历史月）
        fc = None

    def aligned(sid):
        s = raw.get(sid) or {}
        return [s.get(m) for m in months]

    world = aligned(SERIES["world"])
    opec = aligned(SERIES["opec"])
    non_opec = aligned(SERIES["nonOpec"])
    members = {zh: aligned(sid) for sid, zh in OPEC_MEMBERS}
    doc_members = {zh: aligned(sid) for sid, zh in DOC_MEMBERS}
    doc_total = aligned(DOC_TOTAL)

    # ---- 预测守卫：API 若无预测数据（无边界 / 预测段全空），按需求直接删除预测段 ----
    if fc_i is not None and not any(v is not None for v in world[fc_i:]):
        # fc_i 有值但预测段全空 —— 同样是「没有预测」，一并清掉（避免 forecastStart
        # 指向一个不存在的预测段，前端会把它当边界画虚线）
        print("  [supply]  steo monthly: API 未提供预测数据 → 删除预测段")
        fc, fc_i = None, None
    if fc_i is None and last_hist and last_hist in months:
        cut = months.index(last_hist) + 1
        months = months[:cut]
        world, opec, non_opec = world[:cut], opec[:cut], non_opec[:cut]
        members = {k: v[:cut] for k, v in members.items()}
        doc_members = {k: v[:cut] for k, v in doc_members.items()}
        doc_total = doc_total[:cut]
        print("  [supply]  steo monthly: 窗口截断至 %s（仅历史段，共 %d 月）"
              % (months[-1], len(months)))

    out = {
        "unit": "mb/d",
        "frequency": "月度",
        "months": months,
        "lastHistorical": last_hist,
        "forecastStart": fc,
        "forecastIndex": fc_i,
        "source": "EIA 短期能源展望（STEO）API /v2/steo/data/（月度，最新一期）",
        "meta": ("世界 / OPEC / 非 OPEC 的**月度原油**产量，来自 EIA STEO 官方 API 的 "
                 "COPR_* 序列（Crude Oil Production，仅原油、不含 NGL），单位百万桶/日 "
                 "(mb/d) 日均速率，**不做任何月度加总/平均换算**。OPEC 为 11 国口径"
                 "（不含阿联酋）。"
                 + (("%s~%s 为历史实际值、%s 起为 STEO 预测值。" % (months[0], last_hist, fc))
                    if (last_hist and fc) else
                    ("%s~%s 为历史实际值（EIA 本期未提供预测段）。" % (months[0], last_hist)
                     if last_hist else ""))),
    }
    for key, zh in GROUPS:
        out[key] = {"label": zh, "crude": {"world": world, "opec": opec, "nonOpec": non_opec}[key]}

    out["opecMembers"] = members
    out["opecMembersMeta"] = (
        "EIA STEO API 的 OPEC 11 国分项（脚注 c 口径：沙特/伊拉克/伊朗/科威特/委内瑞拉/"
        "尼日利亚/利比亚/阿尔及利亚/刚果/赤道几内亚/加蓬，不含阿联酋）。原油 COPR_*，mb/d；"
        "分国行仅历史段（至 %s）有值，STEO 不提供分国预测。"
        % (last_hist or "—"))
    out["docMembers"] = doc_members
    out["docTotal"] = doc_total
    out["docMembersMeta"] = (
        "EIA STEO API 的 OPEC+ 非 OPEC 参与国（DoC）10 国分项与合计（脚注 b 的 other "
        "participants：俄罗斯/哈萨克斯坦/墨西哥/阿曼/阿塞拜疆/马来西亚/南苏丹/文莱/巴林/苏丹）。"
        "原油 COPR_*，mb/d；分国行仅历史段（至 %s）有值，合计行%s。"
        % (last_hist or "—", "含 STEO 预测段" if fc else "本期也无预测段"))

    # ---- 恒等校验：OPEC + 非 OPEC == 世界（原油），容差 0.05 ----
    bad = []
    for i, m in enumerate(months):
        w, o, n = world[i], opec[i], non_opec[i]
        if w is None or o is None or n is None:
            continue
        if abs(o + n - w) > 0.05:
            bad.append("%s:%.3fvs%.3f" % (m, o + n, w))
    print("  [supply]  恒等校验（OPEC + 非OPEC = 世界，原油）：",
          "通过" if not bad else "偏差 " + ",".join(bad[:5]))

    return out


def main():
    data = fetch()
    if not data:
        print("!! STEO 月度产量抓取失败，未写出文件")
        return
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    p = os.path.join(DATA_PROCESSED, "steo_world_monthly.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    months = data["months"]
    print("\n%-9s%10s%10s%11s" % ("月份", "世界", "OPEC", "非OPEC"))
    fc_i = data["forecastIndex"]
    for i, m in enumerate(months):
        mark = "  <- 预测起点" if i == fc_i else ""
        print("%-9s%10.2f%10.2f%11.2f%s" % (m, data["world"]["crude"][i],
              data["opec"]["crude"][i], data["nonOpec"]["crude"][i], mark))
    print("\n共 %d 个月 %s ~ %s，来源 %s，预测起点 %s（index %s）"
          % (len(months), months[0], months[-1], data["source"],
             data["forecastStart"], fc_i))
    print("已写出:", p)


if __name__ == "__main__":
    main()
