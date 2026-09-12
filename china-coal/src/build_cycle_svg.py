# -*- coding: utf-8 -*-
"""只读「数据源/煤炭行业周期历史煤价.xlsx」→ 生成「2002年以来煤炭周期复盘」综合趋势 SVG。

一张图承载四层信息（单一系列 + 标注层，不引入第二数据轴）：
  1) 价格长周期：秦皇岛 Q5500 年均价折线 + 七个阶段分区
  2) 行业状态：峰谷拐点标注；谷点附「行业亏损面」——萧条确认的同步指标
  3) 领先关系：资本开支时滞规则示意（价格顶 → 资本开支顶 → 价格底）
  4) 拐点识别：大 / 中 / 小三级拐点分类

2015 底部统一采用年均价口径 410（非时点低点 370）。绝不写回 xlsx。
"""
import os
from openpyxl import load_workbook

# ── 路径基准 ───────────────────────────────────────────────────────
# 本脚本位于 <项目根>/src/，统一把工作目录切到项目根，
# 让「数据源/…」「svg/…」「china-coal-dashboard.html」等既有相对路径
# 保持有效——无论从哪个目录执行，结果都一致。
import os as _os
_os.chdir(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

XLSX = os.path.join("数据源", "煤炭行业周期历史煤价.xlsx")
OUT = os.path.join("svg", "煤炭周期复盘.svg")

# ── 画布与布局（压缩版：与看板内 1000×420 SVG 同量级，避免在 dashboard 视口中撑高被切）
W, H = 1240, 460
ML, MR, MT, PH = 64, 48, 84, 220
PW = W - ML - MR                 # 1128
AXIS_Y = MT + PH                 # 304
XLAB_Y = AXIS_Y + 18             # 322
RY0, RY1 = 36, 60                # 顶部阶段色带（h=24）
BA_Y, BA_H = 340, 42             # 资本开支时滞规则带
BB_Y, BB_H = 390, 42             # 三级拐点分类带

YMIN, YMAX, YSTEP = 0, 1400, 200

INK, SUB, GRID = "#1f2733", "#5b6573", "#e6ebf1"
RED, GREEN, PURPLE = "#c53030", "#047857", "#7c3aed"
BLUE, GRAY = "#2563eb", "#64748b"
LTPRICE = "#1d4ed8"             # 年度长协价曲线

# ── 关键拐点：年份 → (数值, 说明, peak/trough)
ANN = {
    2011: ("820", "黄金十年顶", "peak"),
    2015: ("410", "供给侧前底", "trough"),
    2022: ("1280", "周期峰值", "peak"),
    2025: ("697", "近年低点", "trough"),
    2026: ("786", "1-8月·回升", "peak"),
}

# ── 大周期拐点（产业政策转向）：竖虚线 + 菱形标记
POLICY_TURN = (2016, 2025)

# ── 三级拐点分类
TIERS = [
    (PURPLE, "大周期拐点 · 产业政策转向", "2016 供给侧改革　2025 反内卷控产"),
    (BLUE, "中周期拐点 · 宏观冲击", "2008 金融危机　2020 疫情"),
    (GRAY, "小周期拐点 · 季节性需求", "迎峰度夏　冬季供暖"),
]


def load_data():
    wb = load_workbook(XLSX, data_only=True)
    ws = wb["年度均价"]
    years, vals, loss, lt = [], [], {}, {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        if row[0] is None or row[1] is None:
            continue
        y = int(row[0])
        years.append(y)
        vals.append(float(row[1]))
        if row[2] not in (None, ""):
            lt[y] = float(row[2])
        if row[3]:
            loss[y] = str(row[3]).strip()

    ws2 = wb["周期阶段"]
    phases = []
    for row in ws2.iter_rows(min_row=3, values_only=True):
        if row[0] is None or row[1] is None:
            continue
        phases.append((int(row[0]), int(row[1]), str(row[2]), str(row[3]), str(row[4] or "")))
    return years, vals, loss, lt, phases


def h_arrow(x1, x2, y, color):
    """水平箭头：线 + 三角头"""
    return (
        f'<line x1="{x1}" y1="{y}" x2="{x2 - 7}" y2="{y}" stroke="{color}" stroke-width="1.4"/>'
        f'<path d="M{x2 - 9} {y - 4} L{x2} {y} L{x2 - 9} {y + 4} Z" fill="{color}"/>'
    )


def build(years, vals, loss, lt, phases):
    n = len(years)
    y0 = years[0]
    step = PW / (n - 1)
    sx = lambda yr: ML + (yr - y0) * step
    yv = lambda v: MT + PH * (1 - (v - YMIN) / (YMAX - YMIN))

    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
             f'width="{W}" height="{H}" font-family="'
             '-apple-system,BlinkMacSystemFont,\'Segoe UI\',\'PingFang SC\',\'Microsoft YaHei\',sans-serif">')

    # 标题
    s.append(f'<text x="{ML}" y="22" fill="{INK}" font-size="14" font-weight="700">'
             '2002–2026 年秦皇岛 Q5500 动力煤年均价与周期阶段</text>')

    # ── 顶部阶段色带
    for i, (p0, p1, name, color, _d) in enumerate(phases):
        x1 = max(ML, sx(p0) - step / 2)
        x2 = min(ML + PW, sx(p1) + step / 2)
        s.append(f'<rect x="{x1:.1f}" y="{RY0}" width="{x2 - x1:.1f}" height="{RY1 - RY0}" '
                 f'fill="{color}" opacity="0.88"/>')
        if i > 0:
            s.append(f'<line x1="{x1:.1f}" y1="{RY0}" x2="{x1:.1f}" y2="{RY1}" '
                     f'stroke="#ffffff" stroke-width="1.5"/>')
        cx, cy = (x1 + x2) / 2, (RY0 + RY1) / 2
        s.append(f'<text x="{cx:.1f}" y="{cy + 3.6:.1f}" font-size="10" font-weight="700" fill="#ffffff" '
                 f'text-anchor="middle" paint-order="stroke" stroke="{color}" '
                 f'stroke-width="3" stroke-linejoin="round">{name}</text>')

    # ── 绘图区阶段底色
    for p0, p1, _n, color, _d in phases:
        x1 = max(ML, sx(p0) - step / 2)
        x2 = min(ML + PW, sx(p1) + step / 2)
        s.append(f'<rect x="{x1:.1f}" y="{MT}" width="{x2 - x1:.1f}" height="{PH}" '
                 f'fill="{color}" opacity="0.10"/>')

    # ── 网格 + y 轴
    v = YMIN
    while v <= YMAX:
        yy = yv(v)
        s.append(f'<line x1="{ML}" y1="{yy:.1f}" x2="{ML + PW}" y2="{yy:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{ML - 8}" y="{yy + 3.5:.1f}" font-size="10" fill="{SUB}" '
                 f'text-anchor="end">{v}</text>')
        v += YSTEP
    s.append(f'<text x="{ML - 8}" y="{MT - 9}" font-size="10" fill="{SUB}" text-anchor="end">元/吨</text>')

    # ── 阶段分界竖虚线
    for p0, p1, _n, _c, _d in phases[:-1]:
        bx = sx(p1) + step / 2
        if ML < bx < ML + PW:
            s.append(f'<line x1="{bx:.1f}" y1="{MT}" x2="{bx:.1f}" y2="{AXIS_Y}" '
                     f'stroke="#94a3b8" stroke-width="1" stroke-dasharray="3 3" opacity="0.65"/>')

    # ── 大周期拐点：竖虚线 + 菱形
    for yr in POLICY_TURN:
        if yr not in years:
            continue
        idx = years.index(yr)
        x, y = sx(yr), yv(vals[idx])
        s.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{AXIS_Y}" '
                 f'stroke="{PURPLE}" stroke-width="1.4" stroke-dasharray="4 3" opacity="0.9"/>')
        if yr in ANN:                      # 2025：空心菱形套在谷点上
            s.append(f'<path d="M{x:.1f} {y - 8:.1f} L{x + 8:.1f} {y:.1f} '
                     f'L{x:.1f} {y + 8:.1f} L{x - 8:.1f} {y:.1f} Z" fill="none" '
                     f'stroke="{PURPLE}" stroke-width="1.8"/>')
        else:                              # 2016：实心菱形
            s.append(f'<path d="M{x:.1f} {y - 5.5:.1f} L{x + 5.5:.1f} {y:.1f} '
                     f'L{x:.1f} {y + 5.5:.1f} L{x - 5.5:.1f} {y:.1f} Z" fill="{PURPLE}"/>')

    # ── 年度长协价曲线（2017 年起，与现货共用左轴）
    lt_yrs = sorted(lt)
    if lt_yrs:
        lpts = [(sx(y), yv(lt[y])) for y in lt_yrs]
        s.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in lpts) + '" '
                 f'fill="none" stroke="{LTPRICE}" stroke-width="2.2" '
                 'stroke-linejoin="round" stroke-linecap="round"/>')
        for (mx, my) in lpts:
            s.append(f'<rect x="{mx - 3.2:.1f}" y="{my - 3.2:.1f}" width="6.4" height="6.4" '
                     f'rx="1.2" fill="{LTPRICE}" stroke="#ffffff" stroke-width="1.2"/>')
        ex, ey = lpts[-1]
        s.append(f'<text x="{ex:.1f}" y="{ey + 17:.1f}" font-size="10.5" font-weight="700" '
                 f'fill="{LTPRICE}" text-anchor="end" paint-order="stroke" stroke="#ffffff" '
                 f'stroke-width="2.5" stroke-linejoin="round">{lt[lt_yrs[-1]]:g}</text>')

    # ── 折线（主体实线，末段虚线）
    pts = [(sx(y), yv(val)) for y, val in zip(years, vals)]
    s.append('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts[:-1]) + '" '
             f'fill="none" stroke="{INK}" stroke-width="2.4" '
             'stroke-linejoin="round" stroke-linecap="round"/>')
    s.append(f'<line x1="{pts[-2][0]:.1f}" y1="{pts[-2][1]:.1f}" x2="{pts[-1][0]:.1f}" '
             f'y2="{pts[-1][1]:.1f}" stroke="{INK}" stroke-width="2.4" stroke-dasharray="6 4"/>')

    # ── 数据点与标注
    for yr, val in zip(years, vals):
        x, y = sx(yr), yv(val)
        if yr in ANN:
            label, desc, kind = ANN[yr]
            col = RED if kind == "peak" else GREEN
            if yr == years[-1]:
                s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#ffffff" '
                         f'stroke="{col}" stroke-width="2.2"/>')
            else:
                s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.6" fill="{col}" '
                         f'stroke="#ffffff" stroke-width="1.6"/>')
            if kind == "peak":
                vy, dy, ly = y - 11, y - 21.5, y - 32.5
            else:
                vy, dy, ly = y + 18, y + 28.5, y + 39.5
            s.append(f'<text x="{x:.1f}" y="{vy:.1f}" font-size="11" font-weight="700" '
                     f'fill="{col}" text-anchor="middle">{label}</text>')
            s.append(f'<text x="{x:.1f}" y="{dy:.1f}" font-size="9" fill="{SUB}" '
                     f'text-anchor="middle" paint-order="stroke" stroke="#ffffff" '
                     f'stroke-width="2.5" stroke-linejoin="round">{desc}</text>')
            if yr in loss:
                s.append(f'<text x="{x:.1f}" y="{ly:.1f}" font-size="9.5" font-weight="700" '
                         f'fill="{col}" text-anchor="middle" paint-order="stroke" stroke="#ffffff" '
                         f'stroke-width="2.5" stroke-linejoin="round">{loss[yr]}</text>')
        else:
            s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="#ffffff" '
                     f'stroke="{INK}" stroke-width="1.5"/>')

    # ── x 轴
    s.append(f'<line x1="{ML}" y1="{AXIS_Y}" x2="{ML + PW}" y2="{AXIS_Y}" '
             f'stroke="#cbd5e1" stroke-width="1"/>')
    for yr in years:
        s.append(f'<text x="{sx(yr):.1f}" y="{XLAB_Y}" font-size="9.5" fill="{SUB}" '
                 f'text-anchor="middle">{yr}</text>')

    # ── 图例（绘图区左上空白处）
    lg_x, lg_y, lg_w, lg_h = 80, 108, 252, 56
    s.append(f'<rect x="{lg_x}" y="{lg_y}" width="{lg_w}" height="{lg_h}" rx="8" '
             f'fill="#ffffff" stroke="#dbe2ea" stroke-width="0.8" opacity="0.96"/>')
    s.append(f'<line x1="{lg_x + 14}" y1="{lg_y + 20}" x2="{lg_x + 38}" y2="{lg_y + 20}" '
             f'stroke="{INK}" stroke-width="2.4"/>')
    s.append(f'<text x="{lg_x + 46}" y="{lg_y + 24}" font-size="11.5" fill="{INK}">'
             'Q5500 现货年均价</text>')
    s.append(f'<line x1="{lg_x + 14}" y1="{lg_y + 39}" x2="{lg_x + 38}" y2="{lg_y + 39}" '
             f'stroke="{LTPRICE}" stroke-width="2.2"/>')
    s.append(f'<rect x="{lg_x + 22.8:.1f}" y="{lg_y + 35.8}" width="6.4" height="6.4" rx="1.2" '
             f'fill="{LTPRICE}" stroke="#ffffff" stroke-width="1"/>')
    s.append(f'<text x="{lg_x + 46}" y="{lg_y + 43}" font-size="11.5" fill="{INK}">'
             '年度长协价（2017 起）</text>')

    # ── 带 A：资本开支时滞规则
    s.append(f'<rect x="{ML}" y="{BA_Y}" width="{PW}" height="{BA_H}" rx="8" '
             f'fill="#faf7fe" stroke="{PURPLE}" stroke-width="0.8" opacity="0.95"/>')
    s.append(f'<text x="{ML + 14}" y="{BA_Y + 26}" font-size="10" font-weight="700" '
             f'fill="{PURPLE}">资本开支时滞规则</text>')
    s.append(f'<text x="{ML + 14}" y="{BA_Y + 38}" font-size="8.5" fill="{SUB}">领先指标量化</text>')

    fx, ny = ML + 180, BA_Y + 16
    nodes = [("价格顶 2011", 104), ("资本开支顶 2012", 128), ("价格底 2015", 104)]
    xs, cur = [], fx
    for txt, w in nodes:
        xs.append((cur, w, txt))
        cur += w + 52
    for (nx, nw, txt) in xs:
        s.append(f'<rect x="{nx}" y="{ny}" width="{nw}" height="20" rx="6" fill="#ffffff" '
                 f'stroke="{PURPLE}" stroke-width="0.8"/>')
        s.append(f'<text x="{nx + nw / 2:.1f}" y="{ny + 10}" font-size="10" fill="{PURPLE}" '
                 f'text-anchor="middle" dominant-baseline="central">{txt}</text>')
    s.append(h_arrow(xs[0][0] + xs[0][1] + 4, xs[1][0] - 4, ny + 10, PURPLE))
    s.append(f'<text x="{(xs[0][0] + xs[0][1] + xs[1][0]) / 2:.1f}" y="{ny - 2}" font-size="8.5" '
             f'fill="{PURPLE}" text-anchor="middle">1~2年</text>')
    s.append(h_arrow(xs[1][0] + xs[1][1] + 4, xs[2][0] - 4, ny + 10, PURPLE))
    s.append(f'<text x="{(xs[1][0] + xs[1][1] + xs[2][0]) / 2:.1f}" y="{ny - 2}" font-size="8.5" '
             f'fill="{PURPLE}" text-anchor="middle">3~4年</text>')
    tipx = xs[2][0] + xs[2][1] + 24
    s.append(f'<text x="{tipx}" y="{ny + 11}" font-size="10" fill="{SUB}">'
             '本轮：价格顶 2022 → 资本开支顶 2023 → 理论底 2026，被「反内卷」政策提前至 2025-07</text>')

    # ── 带 B：三级拐点分类
    s.append(f'<rect x="{ML}" y="{BB_Y}" width="{PW}" height="{BB_H}" rx="8" '
             f'fill="#f8fafc" stroke="#cbd5e1" stroke-width="0.8"/>')
    cw = PW / 3
    for i, (col, title, ex) in enumerate(TIERS):
        cx0 = ML + i * cw + 18
        if i > 0:
            s.append(f'<line x1="{ML + i * cw:.1f}" y1="{BB_Y + 8}" x2="{ML + i * cw:.1f}" '
                     f'y2="{BB_Y + BB_H - 8}" stroke="#e2e8f0" stroke-width="1"/>')
        s.append(f'<rect x="{cx0}" y="{BB_Y + 10}" width="9" height="9" rx="2" fill="{col}"/>')
        s.append(f'<text x="{cx0 + 15}" y="{BB_Y + 18}" font-size="11" font-weight="700" '
                 f'fill="{INK}">{title}</text>')
        s.append(f'<text x="{cx0}" y="{BB_Y + 38}" font-size="10" fill="{SUB}">{ex}</text>')

    s.append('</svg>')
    return "\n".join(s)


def main():
    years, vals, loss, lt, phases = load_data()
    svg = build(years, vals, loss, lt, phases)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print("written:", OUT)
    print("years:", years[0], "-", years[-1], "| n =", len(years))
    print("亏损面标注:", loss)
    if lt:
        lo, hi = min(lt.values()), max(lt.values())
        print(f"长协价 {min(lt)}-{max(lt)}: {lo:g}–{hi:g} 元/吨，振幅 {(hi/lo-1)*100:.0f}%")
        sw = [v for y, v in zip(years, vals) if y in lt]      # 同期现货（同窗口才可比）
        slo, shi = min(sw), max(sw)
        print(f"同期现货 {slo:g}–{shi:g} 元/吨，振幅 {(shi/slo-1)*100:.0f}%"
              f"（长协机制压缩波动约 {(shi/slo-1)/(hi/lo-1):.1f} 倍）")


if __name__ == "__main__":
    main()
