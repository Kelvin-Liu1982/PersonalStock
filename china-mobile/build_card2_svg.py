# -*- coding: utf-8 -*-
"""读取 数据源/中国移动_核心业务运营与结构转型.xlsx 年报数据 sheet，
为卡片2（核心业务运营与结构转型）的五个指标生成年度 SVG 折线图，
输出到 svg 图/s2/。

五个指标（与看板卡片2 sparkline 一一对应）：
  csr    通信服务收入（亿元）       2020-2025: 6957,7514,8121,8635,8895,7149
  ratio  算力+智能占主营比（%）     2020-2025: —,—,—,—,18.8,20.2
  5g     5G网络客户（亿户）         2020-2025: (2020口径不同未纳入),2.07,3.27,4.65,5.52,6.42
  marpu  移动ARPU（元）             2020-2025: 47.4,49,49.2,49.3,48.5,47
  harpu  家庭综合ARPU（元）          2020-2025: 37.7,40,42,43,43.8,44.5

仅年度（本卡片指标均为年度披露，无季度序列需求）。
生成器只读 XLSX，绝不写回。
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/Users/sto1/.workbuddy/skills/finance-xlsx-svg-charts/scripts")
sys.path.insert(0, HERE)
import openpyxl
from gen_line_svg import make_line_svg

SRC = os.path.join(HERE, "数据源", "中国移动_核心业务运营与结构转型.xlsx")
OUT_DIR = os.path.join(HERE, "svg 图", "s2")
os.makedirs(OUT_DIR, exist_ok=True)

YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

wb = openpyxl.load_workbook(SRC, data_only=True)
ws = wb["年报数据"]


def get_row(name):
    for r in range(5, 40):
        if ws.cell(r, 1).value == name:
            return r
    raise KeyError("未找到指标: " + name)


def col(name):
    row = get_row(name)
    return [ws.cell(row, c).value for c in range(2, 8)]  # 2020-2025


def clean(v):
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "—", "-", "－", "未单独披露", "约"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


csr = [clean(v) for v in col("通信服务收入（亿元）")]
ratio = [clean(v) for v in col("算力+智能占主营比（%）")]
g5 = [clean(v) for v in col("5G网络客户（亿户）")]
# 2020 年"5G套餐客户"1.65 亿与"5G网络客户"口径不同，未纳入 → None
if len(g5) == 6:
    g5[0] = None
marpu = [clean(v) for v in col("移动ARPU（元）")]
harpu = [clean(v) for v in col("家庭综合ARPU（元）")]

# (key, 显示名, 单位, 序列, 颜色) —— 颜色与卡片2 sparkline 一致
IND = [
    ("csr", "通信服务收入", "亿元", csr, "#15616d"),
    ("ratio", "算力+智能占主营比", "%", ratio, "#c8102e"),
    ("5g", "5G网络客户", "亿户", g5, "#d98a14"),
    ("marpu", "移动ARPU", "元", marpu, "#c8102e"),
    ("harpu", "家庭综合ARPU", "元", harpu, "#2e9e6b"),
]

written = []
for key, name, unit, vals, color in IND:
    svg = make_line_svg(name, unit, YEARS, vals, color, W=480, H=260, quarterly=False)
    fn = os.path.join(OUT_DIR, f"s2_{key}_annual.svg")
    with open(fn, "w", encoding="utf-8") as f:
        f.write(svg)
    written.append(fn)

print("生成 %d 个年度 SVG（输出至 %s）：" % (len(written), os.path.relpath(OUT_DIR, HERE)))
for w in written:
    print("  ", os.path.basename(w))

print("\n数值核对：")
for key, name, unit, vals, color in IND:
    print(f"  {name}: {vals}")
