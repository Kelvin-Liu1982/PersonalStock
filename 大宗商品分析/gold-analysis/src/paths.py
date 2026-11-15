# -*- coding: utf-8 -*-
"""全项目唯一的路径定义。

历史上脚本各自写 ``HERE = dirname(__file__)``，一旦移动脚本就会错位。
这里集中定义，所有模块统一从本文件取路径（与 oil-analysis 保持同一约定）。

目录语义：
    data/       Excel 数据仓（gold_data.xlsx）—— fetch 落盘 + build 的唯一输入
    src/        全部代码
    output/     全部 HTML 页面归档目录；gold-terminal.html 为可完全重建的终稿，
                另有独立可视化页（央行购金 / 债务复利模型 / 债务真实数据校准）。
                ⚠️ 不要再往项目根目录放 HTML；历史 _bak 已清理。
"""
import os

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---- 数据仓 ----
DATA_DIR = os.path.join(WORKSPACE, "data")
DATA_XLSX = os.path.join(DATA_DIR, "gold_data.xlsx")

# ---- 代码 ----
SRC_DIR = os.path.join(WORKSPACE, "src")

# ---- 发布产物 ----
OUTPUT_DIR = os.path.join(WORKSPACE, "output")
TERMINAL_HTML = os.path.join(OUTPUT_DIR, "gold-terminal.html")
