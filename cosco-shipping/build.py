# -*- coding: utf-8 -*-
"""
一键重建中远海控追踪看板（方向C + 趋势增强）。

用法:
    python build.py
    # 或先建虚拟环境: python -m venv .venv && .venv/bin/pip install -r requirements.txt

步骤:
    1) build_financials.py  重新生成 数据源/中远海控_财报核心数据.xlsx
                           （联网抓取东方财富业绩报表；失败则回退到本地 财报原始数据_缓存.json）
    2) build_buyback.py     重新生成 数据源/中远海控_回购明细.xlsx（内置已核对数据）
    3) build_tracker.py     读取 数据源/ 下全部 xlsx，生成时序数据 + 趋势图(base64)，写入 _data_js.txt
    4) render_html.py       读取 _data_js.txt，合成单文件 HTML（cosco-dashboard.html）

说明: 步骤 1) 依赖网络与 财报原始数据_缓存.json；若只想用已提交的 数据源/ 重生成看板，
      可直接运行 build_tracker.py + render_html.py（跳过 1)/2)）。
依赖: openpyxl, matplotlib（见 requirements.txt）
"""
import sys, subprocess, os

HERE = os.path.dirname(os.path.abspath(__file__))
# 使用当前 Python 解释器；如需隔离依赖请自建 venv 并安装 requirements.txt
PY = sys.executable

# 全部脚本均位于本仓库（数据源生成 + 看板构建）
for script in ("build_financials.py", "build_buyback.py", "build_tracker.py", "render_html.py"):
    path = os.path.join(HERE, script)
    print(f"\n=== running {script} ===")
    subprocess.run([PY, path], check=True)

print("\n=== DONE: cosco-dashboard.html 已更新 ===")
