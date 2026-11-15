# -*- coding: utf-8 -*-
"""全项目唯一的路径定义。

历史上每个脚本各写一份 ``HERE = dirname(__file__)`` / ``ROOT = dirname(dirname(HERE))``，
一旦移动脚本就会错位。这里集中定义，所有模块统一从本文件取路径。

目录语义：
    data/raw/        抓取到的原始文件（OPEC MOMR PDF、Baker Hughes Excel）—— 不可再生，需保留
    data/processed/  各抓取器解析原始数据后的中间产物 —— 可由 data/raw 完全重算
    data/dataset/    合并后的域数据，按主题分文件 —— build_html 的唯一输入
    assets/vendor/   第三方前端库原件（Chart.js / ECharts），构建时复制到 output/vendor/
    output/          可直接发布的站点（单文件 HTML + 本地 vendor）—— 全部可重建
"""
import os

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 原始数据 ----
DATA_RAW = os.path.join(WORKSPACE, "data", "raw")
DATA_RAW_OPEC = os.path.join(DATA_RAW, "opec_momr")
DATA_RAW_OPEC_WOO = os.path.join(DATA_RAW, "opec_woo")
DATA_RAW_IEA_OIL = os.path.join(DATA_RAW, "iea_oil")
DATA_RAW_EIA_AEO = os.path.join(DATA_RAW, "eia_aeo")
DATA_RAW_STEO = os.path.join(DATA_RAW, "eia_steo")   # 短期能源展望，表 3a/3d 世界产量
DATA_RAW_RIG = os.path.join(DATA_RAW, "rig_count")

# ---- 抓取产物 ----
DATA_PROCESSED = os.path.join(WORKSPACE, "data", "processed")

# ---- 域数据（渲染输入）----
DATASET_DIR = os.path.join(WORKSPACE, "data", "dataset")

# ---- 静态原件 ----
ASSETS_DIR = os.path.join(WORKSPACE, "assets")
ASSETS_VENDOR = os.path.join(ASSETS_DIR, "vendor")
CHART_VENDOR_SRC = os.path.join(ASSETS_VENDOR, "chart.umd.min.js")
ECHARTS_VENDOR_SRC = os.path.join(ASSETS_VENDOR, "echarts.min.js")

# ---- 发布产物 ----
OUTPUT_DIR = os.path.join(WORKSPACE, "output")
VENDOR_DIR = os.path.join(OUTPUT_DIR, "vendor")
DASHBOARD_HTML = os.path.join(OUTPUT_DIR, "crude_oil_dashboard.html")
CHART_VENDOR = os.path.join(VENDOR_DIR, "chart.umd.min.js")
ECHARTS_VENDOR = os.path.join(VENDOR_DIR, "echarts.min.js")

# ---- 前端模板（dashboard 的骨架 / 样式 / 脚本，构建时组装成单文件产物）----
# 拆成三个文件后，JS 可被 node --check / eslint 直接校验，CSS 与 HTML 也可独立编辑，
# 不再塞在一个 Python 原始字符串里（那样 JS 没有任何语法检查手段）。
TEMPLATES_DIR = os.path.join(WORKSPACE, "src", "pipeline", "templates")
DASHBOARD_HTML_TPL = os.path.join(TEMPLATES_DIR, "dashboard.html")
DASHBOARD_CSS_TPL = os.path.join(TEMPLATES_DIR, "dashboard.css")
DASHBOARD_JS_TPL = os.path.join(TEMPLATES_DIR, "dashboard.js")
