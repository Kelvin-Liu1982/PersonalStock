# -*- coding: utf-8 -*-
"""把 data/dataset/*.json 渲染成单文件仪表盘 output/crude_oil_dashboard.html。

数据层：data/dataset/ 按域分文件（src/dataio.py 负责合并/拆分）。
地缘恐慌指数 I_geo 在渲染期计算（src/score/geo.py），结果只注入 SNAPSHOT、不落库。
Chart.js 走本地 vendor（assets/vendor/ 复制而来），避免依赖 CDN。

运行：在仓库根目录执行 `python -m src.pipeline.build_html`

前端模板不再内联在本文件里，而是拆到 src/pipeline/templates/：

    dashboard.html   HTML 骨架（含 __CSS__ / __JS__ 两个占位符）
    dashboard.css    样式
    dashboard.js     脚本（含 __DATA__ / __CONST__ / __EIA_SERIES__ / STATE_CORR_PLACEHOLDER / __START_DATE__）

占位符用**裸标识符**（如 ``const SNAPSHOT = __DATA__;``）而不是被注释包裹的形式，
这样 dashboard.js 本身就是合法 JS，可以直接 `node --check` / eslint，
不必先替换再校验。构建时的组装顺序见 ``build()``。
"""
import json
import os
import shutil
import subprocess

from src import config, dataio
from src.paths import (CHART_VENDOR, CHART_VENDOR_SRC, DASHBOARD_CSS_TPL,
                       DASHBOARD_HTML, DASHBOARD_HTML_TPL, DASHBOARD_JS_TPL,
                       ECHARTS_VENDOR, ECHARTS_VENDOR_SRC, OUTPUT_DIR,
                       VENDOR_DIR)
from src.score import dims as score_dims
from src.score import geo as geo_score

# 本地内置 Chart.js（避免依赖 jsdelivr CDN，国内浏览器常因墙无法加载）
CHART_CDN = ("https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js",
             "https://unpkg.com/chart.js@4.5.1/dist/chart.umd.min.js")


def _ensure_chart_vendor():
    """保证 output/vendor/chart.umd.min.js 存在：先复制 assets 原件，再退化为下载。"""
    if os.path.exists(CHART_VENDOR):
        return
    os.makedirs(VENDOR_DIR, exist_ok=True)
    if os.path.exists(CHART_VENDOR_SRC):
        shutil.copyfile(CHART_VENDOR_SRC, CHART_VENDOR)
        return
    for url in CHART_CDN:
        if subprocess.run(["curl", "-sSL", url, "-o", CHART_VENDOR]).returncode == 0 \
                and os.path.getsize(CHART_VENDOR) > 1000:
            break


# ECharts 5.5.1：仅用于「制造业 PMI 中/美/欧」单图实验（markPoint / markArea / visualMap /
# dataZoom 等组件 Chart.js 无原生能力）。同样走本地 vendor，缺失时下载。
ECHARTS_CDN = ("https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
               "https://unpkg.com/echarts@5.5.1/dist/echarts.min.js")


def _ensure_echarts_vendor():
    """保证 output/vendor/echarts.min.js 存在：先复制 assets 原件，再退化为下载。"""
    if os.path.exists(ECHARTS_VENDOR):
        return
    os.makedirs(VENDOR_DIR, exist_ok=True)
    if os.path.exists(ECHARTS_VENDOR_SRC):
        shutil.copyfile(ECHARTS_VENDOR_SRC, ECHARTS_VENDOR)
        return
    for url in ECHARTS_CDN:
        if subprocess.run(["curl", "-sSL", url, "-o", ECHARTS_VENDOR]).returncode == 0 \
                and os.path.getsize(ECHARTS_VENDOR) > 100000:
            break


# ---- 前端模板 ----
# dashboard 的 HTML 骨架 / CSS / JS 分别放在 src/pipeline/templates/ 下，
# 构建时读进来组装成单文件产物（占位符与组装顺序见 build()）。
# 拆开的好处：JS 可被 node --check / eslint 直接校验，CSS 与 HTML 也能独立编辑，
# 不必再从产物 HTML 里手工抽取脚本片段来做语法检查。


def _read_asset(path):
    """读取一个模板文件（UTF-8）。"""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _score_const():
    """评分 / 预警模型的常量表 —— 序列化后注入页面的 ``CONST``。

    ``computeDerived``（页面实时重算）必须复用与 Python 产线完全相同的数值，
    否则同一份数据在「离线快照」与「实时拉取」两种模式下会给出不同分数。
    因此这里统一从 config / score 模块取值，而不是在 JS 里再写一份字面量。
    """
    return {
        "scoreWindow": score_dims.SCORE_WINDOW,
        "scoreMinPeriods": score_dims.SCORE_MIN_PERIODS,
        "sensSupply": score_dims.SENSITIVITY["supply"],
        "sensDemand": score_dims.SENSITIVITY["demand"],
        "sensMacro": score_dims.SENSITIVITY["macro"],
        "perJumpScore": score_dims.PER_JUMP_SCORE,
        "jumpWindow": score_dims.JUMP_WINDOW,
        "geoMaxScore": geo_score.MAX_SCORE,
        "ovxHigh": geo_score.OVX_HIGH,
        "ovxMid": geo_score.OVX_MID,
        "spreadHigh": geo_score.SPREAD_HIGH,
        "spareLow": geo_score.SPARE_LOW,
        "jumpThreshold": config.JUMP_THRESHOLD,
        "alertRet": config.ALERT_RET_THRESHOLD,
        "alertRetHigh": config.ALERT_RET_HIGH,
        "alertVol": config.ALERT_VOL_THRESHOLD,
        "alertDxy": config.ALERT_DXY_THRESHOLD,
        "cushingAlert": config.CUSHING_ALERT_THRESHOLD,
        "cushingHigh": config.CUSHING_HIGH_THRESHOLD,
        "volWindow": config.VOL_WINDOW,
        "volMinPeriods": config.VOL_MIN_PERIODS,
        "annualizePeriods": config.ANNUALIZE_PERIODS,
        "dxyChgWindow": config.DXY_CHG_WINDOW,
        "galPerBbl": config.GAL_PER_BBL,
        "maxAlerts": config.MAX_ALERTS,
    }


def _eia_series_const():
    """把 EIA 周度序列的 id 表注入前端，让**抓取侧只有一份 id 表**。

    ``src/fetch/supply/eia_weekly.py::EIA_SERIES`` 是唯一事实源（python 抓取、快照、
    实时拉取三条路径都从它出发）。此前前端 ``dashboard.js::fetchEIA()`` 手抄了第二份
    id 表，2026-10-07 加 ``spr`` 时只改了 python 侧 —— 结果首屏（读快照）正常，
    点「拉取实时」后 ``STATE.eia.spr`` / ``STATE.eiaWeekly.spr`` 直接不存在，
    该图渲染成空画布「图没了」（工单：图重新绘制一行后消失）。
    现在前端从构建注入拿 id，加序列只需改 python 一处，静态校验
    ``tools/check_eia_series.js`` 会兜住两边不同步的情况。

    返回 ``{ids:{name:series_id}, million:[name,...], derived:[name,...]}``：
    ``million`` 里的序列原始单位为千桶，实时拉取要 /1000（与 python 的 MILLION_UNITS 同口径）；
    ``derived`` 里的序列**没有自己的 seriesid**（如含SPR总库存 gross = total + spr），
    由 python ``build_axes`` 与前端 ``fetchEIA`` 各自按恒等算出，实时与快照两边都要有。
    """
    from src.fetch.supply import eia_weekly
    return {
        "ids": dict(eia_weekly.EIA_SERIES),
        "million": list(eia_weekly.MILLION_UNITS),
        "derived": list(eia_weekly.DERIVED),
    }


def _eia_price_const():
    """把 **EIA 日度油价**的 id 表注入前端（2026-10-08 新增）。

    ⚠️ 刻意与 :func:`_eia_series_const`（周度石油周报）**分成两张表**：
    前端 ``fetchEIA()`` 用 ``EIA_SERIES.ids`` 的 period 并集生成「周轴」，
    把日度价格混进去会让周轴从约 2296 个周点膨胀到几千个日点，周度图 x 轴整片塌掉。
    所以日度油价走独立的 ``EIA_PRICE_IDS``，只做日轴对齐、绝不进周轴并集。

    返回 ``{ids:{name:series_id}, fallback:{name:series_id}}``：
    ``fallback`` 是 EIA 不可用时回落的 FRED 序列（与 EIA 同值，仅滞后约一周）。
    """
    from src.fetch import prices
    # len = 日度价的请求限流值（跟着 python 的 EIA_DAILY_LENGTH 走，不另抄一份常量）：
    # EIA seriesid 默认返回 5000 个观测（2006 年至今），看板只要 2024 起那一段。
    return {
        "ids": dict(prices.EIA_PRICE_SERIES),
        "fallback": dict(prices.FRED_PRICE_FALLBACK),
        "len": prices.EIA_DAILY_LENGTH,
    }


def build():
    """渲染出单文件仪表盘的 HTML 字符串（只读数据 + 拼字符串，不写盘）。

    所有副作用（vendor 准备、I_geo 回填）都收在本函数内，不再放在模块顶层——
    这样 ``import build_html`` 不会触发任何文件写入或网络下载。
    """
    data = dataio.load_data()
    # 地缘与情绪恐慌指数 I_geo（0–4）：构建期预计算并注入 SNAPSHOT。
    # dataset 里通常已由 build_dataset 落库过同一口径，这里是幂等兜底
    # （旧 dataset / 手工编辑过的 risk.json 也能被修正到 I_geo 口径）。
    geo_score.apply(data)

    _ensure_chart_vendor()
    _ensure_echarts_vendor()

    # 组装顺序有讲究：先把 CSS / JS 两个大块填进骨架（它们内部还带着
    # __DATA__ / __CONST__ / __START_DATE__ 等占位符），再逐个替换这些占位符。
    html = _read_asset(DASHBOARD_HTML_TPL)
    html = html.replace("__CSS__", _read_asset(DASHBOARD_CSS_TPL))
    html = html.replace("__JS__", _read_asset(DASHBOARD_JS_TPL))
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    html = html.replace("__CONST__", json.dumps(_score_const(), ensure_ascii=False))
    # EIA 序列 id 表（唯一事实源 = src/fetch/supply/eia_weekly.py），前端 fetchEIA 直接读
    html = html.replace("__EIA_SERIES__", json.dumps(_eia_series_const(), ensure_ascii=False))
    # EIA 日度油价 id 表（唯一事实源 = src/fetch/prices.py），与上面周度表**分开注入**：
    # 日度价格绝不能进 EIA_SERIES，否则前端周轴并集会从周点膨胀成日点（周度图 x 轴塌掉）。
    html = html.replace("__EIA_PRICE_IDS__", json.dumps(_eia_price_const(), ensure_ascii=False))
    # 相关系数矩阵不再需要占位符：computeDerived 用 corrMatrix 实时重算，
    # 此前恒用快照矩阵，导致「拉取实时」后矩阵还是旧数据的。
    # API Key 注入到 dashboard.js 的 API_KEYS 常量（界面上不再显示输入框）。
    # ⚠️ 默认**不注入**：产物会进公开仓库并对外发布，view-source 即可拿到 Key。
    # 仅本地/内网调试需要页面内实时刷新时，显式设置 EMBED_KEYS=1 再构建。
    _embed_keys = os.environ.get("EMBED_KEYS", "").strip().lower() in ("1", "true", "yes")
    html = (html.replace("__FRED_KEY__", config.FRED_KEY if _embed_keys else "")
                .replace("__EIA_KEY__", config.EIA_KEY if _embed_keys else "")
                .replace("__START_DATE__", config.START_DATE))
    return html


def main():
    html = build()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(DASHBOARD_HTML, "w") as handle:
        handle.write(html)
    print("dashboard written, bytes:", len(html), "->", DASHBOARD_HTML)


if __name__ == "__main__":
    main()
