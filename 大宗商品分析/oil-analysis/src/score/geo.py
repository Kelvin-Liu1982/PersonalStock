# -*- coding: utf-8 -*-
"""地缘与情绪恐慌指数 I_geo（0–4）。

由三个分项相加，任一分项走高都意味着市场在给“供给中断”更高的定价：

    OVX（0–2）     原油版 VIX：>45 记 2 分，35–45 记 1 分
    BW 价差（0–1） Brent−WTI > 7 美元记 1 分（跨区套利紧张）
    剩余产能（0–1） OPEC 有效剩余产能 < 200 万桶/日记 1 分（缓冲垫变薄）

注意：本指数**在数据集组装期**由 src/pipeline/build_dataset.py 调用一次，
落库的 dims.geo / composite 即最终口径；src/pipeline/build_html.py 会再调用
一次作为幂等兜底（旧 dataset 也能被修正），重复调用结果相同。

本函数是地缘维度与综合分的**唯一权威口径**：src/score/dims.py 只产出
supply / demand / macro / other 四个 z-score 维度，geo 与 composite 都在这里补齐。
"""
import bisect

from src.common.series import clip, last_value

MAX_SCORE = 4  # 2 + 1 + 1，用于把 0–4 归一化到 0–100

# 各分项的判定阈值（原先散落在各 score_* 函数里的字面量）。
# 提升为常量的原因：页面实时重算（build_html.py 的 computeDerived）需要同一套数值，
# 由 build_html.py 序列化注入 JS，避免 Python / JS 两份硬编码漂移。
OVX_HIGH = 45.0        # OVX > 45 记 2 分
OVX_MID = 35.0         # OVX 35–45 记 1 分；< 35 记 0（30–35 缺口按 0）
SPREAD_HIGH = 7.0      # Brent−WTI > 7 美元记 1 分
SPARE_LOW = 2.0        # OPEC 有效剩余产能 < 2.0 百万桶/日记 1 分


def score_ovx(value):
    """OVX 恐慌指数分项（0–2）。"""
    if value is None:
        return 0
    if value > OVX_HIGH:
        return 2
    if value >= OVX_MID:
        return 1
    return 0  # <35 记 0（30–35 区间按 0 处理）


def score_spread(spread):
    """Brent−WTI 价差分项（0–1）。"""
    if spread is None:
        return 0
    if spread > SPREAD_HIGH:
        return 1
    return 0


def score_spare(spare_capacity):
    """OPEC 有效剩余产能分项（0–1），单位百万桶/日。"""
    if spare_capacity is None:
        return 0
    if spare_capacity < SPARE_LOW:
        return 1
    return 0


def apply(data):
    """就地计算 I_geo 并回填 data（幂等，可重复调用）。

    回填六个字段：
        data["igeo"]              0–4 的综合指数序列
        data["igeoBreak"]         逐日分项 {"ovx","bw","spare"}
        data["dims"]["geo"]       归一化到 0–100 的地缘压力分
        data["composite"]         综合分：geo 与 other 先合并为「地缘·波动」块，再与供给/需求/宏观四通道等权
        data["kpis"]["composite"] 同步刷新，避免 KPI 与 composite 序列末值打架

    ⚠️ 最后一项是历史 bug 的修复点：kpis.composite 曾在 build_dataset 里用
    另一套（已删除的波动率）口径落库，导致页面仪表盘显示 67 而综合风险曲线
    末值是 78。kpis 必须由本函数统一刷新，否则离线快照会与 dims 自相矛盾。
    """
    dates = data.get("dates", [])
    brent = data.get("brent", [])
    wti = data.get("wti", [])
    ovx = data.get("ovx") or []

    spread = [
        (b - w) if (b is not None and w is not None) else None
        for b, w in zip(brent, wti)
    ]

    spare_months = data.get("opecSpareMonths", [])
    spare_values = data.get("opecSpare", [])
    # 先按月份排序一次，之后用二分查找：
    # ① 旧实现对每个交易日线性扫描全部月份，997 天 × 156 月 ≈ 15.5 万次比较；
    # ② 旧实现还**依赖 opecSpareMonths 已升序**（用 earlier[-1] 取最后一项），
    #    源数据一旦乱序就会取错月份且毫无提示。排序 + bisect 两个问题一起解决。
    # 语义保持等价：取「月份 <= 当日月份」的最新一条（含当日月份本身）。
    pairs = sorted(zip(spare_months, spare_values))
    spare_keys = [m for m, _ in pairs]
    spare_vals = [v for _, v in pairs]

    def spare_at(day):
        """按月份取剩余产能；该月无数据时沿用最近一个更早的月份。"""
        idx = bisect.bisect_right(spare_keys, day[:7]) - 1
        return spare_vals[idx] if idx >= 0 else None

    igeo_break, igeo = [], []
    for i, day in enumerate(dates):
        ovx_part = score_ovx(ovx[i] if i < len(ovx) else None)
        spread_part = score_spread(spread[i] if i < len(spread) else None)
        spare_part = score_spare(spare_at(day))
        igeo_break.append({"ovx": ovx_part, "bw": spread_part, "spare": spare_part})
        igeo.append(ovx_part + spread_part + spare_part)

    data["igeo"] = igeo
    data["igeoBreak"] = igeo_break

    need = ("supply", "demand", "macro", "other")
    if "dims" in data and all(k in data["dims"] for k in need):
        geo_dim = [clip(v / MAX_SCORE * 100) for v in igeo]
        data["dims"]["geo"] = geo_dim

        dims = data["dims"]
        # 综合分：地缘(geo)与其他突发(other)实测全样本相关系数 0.74，二者都主要由
        # OVX 波动率驱动（同源）。若简单等权会把「地缘·波动」压力双计（占 2/5）。
        # 故先将 geo 与 other 合并为「地缘·波动」块（各占半），再与供给/需求/宏观
        # 做四通道等权均值，消除双计。
        composite = []
        for i in range(len(dates)):
            gv = (geo_dim[i] + dims["other"][i]) / 2 if (
                geo_dim[i] is not None and dims["other"][i] is not None
            ) else None
            values = [dims["supply"][i], dims["demand"][i], dims["macro"][i], gv]
            if all(v is not None for v in values):
                composite.append(clip(sum(values) / 4))
            else:
                composite.append(None)
        data["composite"] = composite
        if isinstance(data.get("kpis"), dict):
            data["kpis"]["composite"] = last_value(composite)

    return data
