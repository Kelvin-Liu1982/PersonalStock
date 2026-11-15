# -*- coding: utf-8 -*-
"""压力分模型：四个 z-score 维度。

把原始指标统一映射成 0–100 的压力分（50 为中性）：

    供给侧 supply  裂解价差的 z-score（炼厂利润越高 → 供给越紧）
    需求侧 demand  汽油价的 z-score（终端价格越高 → 需求越旺）
    宏观金融 macro 美元指数的 z-score（美元越强 → 对油价压制越大）
    其他突发 other 近 20 日跳变次数（非常态事件密度）

地缘政治 geo 与综合分 composite **不在本文件计算**，见 src/score/geo.py::apply。

历史遗留说明（勿回退）：这里曾用「已实现波动率占比 × 78 + 跳变加分 × 4」
算过一版 geo，已移除，原因有三：
  1. 它只用了 vol20 与单日跳变，与 other 维度（跳变计数）重复计数；
  2. 前端 computeDerived 只实现 I_geo 口径（ovx + BW 价差 + 剩余产能），
     保留旧口径会让落库快照与页面实时重算分叉；
  3. I_geo 是离散可解释的 0–4 且能拆出分项（ovx / bw / spare），
     旧口径是连续量，无法对应页面上的 I_geo 图表。

集中在本文件的好处是：这几个维度的口径可以并排对照审阅，
而各 fetch 模块只负责取数与产出该维度的预警。
"""
from src import config
from src.common.series import clip, stress, rolling_zscore

# 各维度 z-score -> 压力分的敏感度
SENSITIVITY = {
    "supply": 16,
    "demand": 13,
    "macro": 17,
}

# 评分归一化基线窗口（与看板展示窗口 RANGE=252 交易日对齐）。
# 用滚动窗口而非整段抓取历史，使 composite 不受 START_DATE 回溯长度影响：
# 无论抓取多少历史，评分永远只看“最近 SCORE_WINDOW 个观测”的同口径区间。
SCORE_WINDOW = 252
# 滚动窗口有效样本下限；不足时该点回落中性 50（仅影响屏外极早期历史）。
SCORE_MIN_PERIODS = 60

# 突发维度：近 20 日每个跳变事件折算 26 分
PER_JUMP_SCORE = 26

JUMP_WINDOW = 20


def compute(crack, gas, dxy, ret):
    """返回 ``{"supply","demand","macro","other"}`` 四个等长序列。

    z-score 归一化基线 = 最近 SCORE_WINDOW 个观测（滚动窗口），与展示窗口对齐，
    因此压力分不随 START_DATE 回溯长度漂移。

    不含 geo 与 composite：这两项由 src/score/geo.py::apply 在数据组装完成后
    统一回填（I_geo 口径），本文件不重复定义地缘判定。
    """
    zcrack = rolling_zscore(crack, SCORE_WINDOW, SCORE_MIN_PERIODS)
    zgas = rolling_zscore(gas, SCORE_WINDOW, SCORE_MIN_PERIODS)
    zdxy = rolling_zscore(dxy, SCORE_WINDOW, SCORE_MIN_PERIODS)

    print(f"  [score]   四维压力分已生成（样本 {len(zcrack)} 天，"
          f"z-score 基线=滚动 {SCORE_WINDOW} 日）；"
          f"geo / composite 交由 score/geo.py 回填")
    return {
        "supply": stress(zcrack, SENSITIVITY["supply"]),
        "demand": stress(zgas, SENSITIVITY["demand"]),
        "macro": stress(zdxy, SENSITIVITY["macro"]),
        "other": _other_stress(ret),
    }


def _other_stress(ret, window=JUMP_WINDOW):
    """突发压力分 = 近 20 个交易日内的跳变次数 × 26。"""
    return [
        clip(sum(
            1 for r in ret[max(0, i - window + 1):i + 1]
            if r is not None and abs(r) > config.JUMP_THRESHOLD
        ) * PER_JUMP_SCORE)
        for i in range(len(ret))
    ]
