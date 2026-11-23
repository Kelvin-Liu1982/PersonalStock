# -*- coding: utf-8 -*-
"""运行配置：API 凭据与时间窗常量。

凭据优先读环境变量（``EIA_KEY`` / ``FRED_KEY``），取不到才回落到内置默认值，
这样既能在本地零配置重跑，也允许用环境变量覆盖成自己的 key。
注意：默认 key 会随渲染一起注入 HTML，仅适合本地/内网看板，不要用于公开部署。
"""
import os

EIA_KEY = os.environ.get("EIA_KEY") or "de8q5z7QnC66e71u7it6VBUYrTP8sJi1rMAOfZLc"
FRED_KEY = os.environ.get("FRED_KEY") or "fb21897ac02e392cce06b3f9209a3e1f"

# ---- 时间窗 ----
START_DATE = "2024-01-01"   # FRED / EIA 日度序列起点（2024 起，供裂解价差等派生序列回溯到 2024）
                            # 注：图表展示窗口默认由 build_html.py 的 RANGE(252≈1年) 控制，
                            #     拉长抓取起点只增加底层历史，不改变其它日度图的可见区间；
                            #     例外：宏观金融两张图配置 from:"2024-01" 全窗口展示。
STEO_START = "2010-01"      # EIA STEO 接口请求起点
SPARE_FROM = "2015-01"      # OPEC 剩余产能展示段起点（更早年份不呈现）
BRENT_MONTHLY_START = "2015-01-01"   # Brent 月均序列（FRED DCOILBRENTEU）请求起点
# ⚠️ 故意比 START_DATE 更早：Brent 月均只用于「OPEC 剩余产能」长周期图（x 轴 2015-01→2027-12）
#    上叠加的右轴价格线，必须同那段历史对齐。
#    ⚠️ 但它**绝不能并进 raw_prices 参与日度日期轴** —— src/fetch/prices.py::fetch_brent_monthly
#    单独返回，build_dataset 只把它写进 opec.json 的 brentMonthly，否则整屏日度图
#    的横轴会从 2024 一路拉到 2015（2026-10-07 加这条序列时的坑）。

# ---- 其它突发：跳变阈值 ----
JUMP_THRESHOLD = 2.5        # 单日涨跌超过该百分比记为一次跳变事件
ALERT_RET_THRESHOLD = 3.0   # 单日变动超过该值触发预警
ALERT_RET_HIGH = 5.0        # 单日变动超过该值升级为 high 级预警
ALERT_VOL_THRESHOLD = 45.0  # 20 日年化波动率超过该值触发地缘预警
ALERT_DXY_THRESHOLD = 2.0   # 美元指数 5 日变动超过该值触发宏观预警

# ---- 供给侧：库欣（Cushing, OK）库存周变动预警阈值（百万桶）----
# ⚠️ 这两个阈值是**按真实库欣序列实测分布校准**的，别凭感觉改（2026-10-07 修正口径后重算）：
#    库欣周变动（2004 年至今 1172 周，样本）：中位 0.72、p75 1.29、p90 1.92、p95 2.50、p99 3.68 Mbbl。
#    旧值 4 / 8 是按此前**误用全美商业库存**（427 Mbbl 量级）时定的：
#    换回真库欣后 ≥8 Mbbl 全历史 0 次命中（死分支），≥4 Mbbl 只有 0.8%（约一年一次）。
#    取「中 = p90（约 9% 的周，一年 4–5 次）／高 = p99 以上（约 0.8%，一年一次）」：
CUSHING_ALERT_THRESHOLD = 2    # mid：值得看的周度异动
CUSHING_HIGH_THRESHOLD = 4     # high：异常周度累库/去库

# ---- 派生序列的口径参数（Python 与页面 computeDerived 共用）----
DXY_CHG_WINDOW = 5              # 美元指数 N 日变动的窗口（交易日）
GAL_PER_BBL = 42                # 每桶折合加仑数，用于裂解价差 = 汽油价($/gal)×42 − WTI

# ---- 序列算子参数（供 src/common/series.py 与 src/fetch/shocks/events.py 使用）----
VOL_WINDOW = 20             # 已实现波动率的滚动窗口（交易日）
VOL_MIN_PERIODS = 5         # 滚动标准差的有效样本下限，不足置 None
ANNUALIZE_PERIODS = 252     # 年化用的年交易日数

# ---- 汇总 ----
MAX_ALERTS = 60             # 预警列表最终保留条数（看板预警流只展示最近 N 条）

# 注意：以上常量是**评分与预警模型的唯一事实来源**。
# 页面内的实时重算（build_html.py 的 computeDerived）不再硬编码这些数值，
# 而是由 build_html.py 序列化成 JS 的 CONST 对象注入（见 _score_const）。
# 调整阈值只需改这里，Python 产线与页面实时模式自动保持一致。
