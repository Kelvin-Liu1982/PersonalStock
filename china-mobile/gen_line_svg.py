# -*- coding: utf-8 -*-
"""中国移动看板本地版「财报 XLSX → 静态 SVG 折线图」生成库。

基于 finance-xlsx-svg-charts skill 的 gen_line_svg 定制：
- 更小边距，让折线区域更贴近画布边缘（填满画布）
- 数据点数值标签更大、更醒目
- 被 china-mobile 下各 build_card*_svg.py 本地调用，避免影响其他项目

用法：
    from gen_line_svg import make_line_svg, make_placeholder, nice_ceil, nice_floor
    svg = make_line_svg("营业收入", "亿元", [2020,2021,...], [7680.7,...], "#c8102e")
"""
import math


def nice_ceil(v):
    if v <= 0:
        return 1
    p = 10 ** math.floor(math.log10(v))
    for s in [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]:
        if v <= s * p:
            return s * p
    return 10 * p


def nice_floor(v):
    if v >= 0:
        return 0
    p = 10 ** math.floor(math.log10(-v))
    for s in [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]:
        if -v <= s * p:
            return -(s * p)
    return -10 * p


def fmt_axis(v):
    if v == 0:
        return "0"
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:.0f}"
    return f"{v:.1f}"


def fmt_val(v, unit):
    if v is None:
        return ""
    if unit in ("%", "pp"):
        return ("+" if v > 0 else "") + f"{v:.1f}"
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:.0f}"
    return f"{v:.1f}"


def make_line_svg(title, unit, labels, values, color, W=480, H=260, quarterly=False):
    """生成单序列折线图 SVG 字符串（浅色主题，紧凑边距版）。

    labels: x 轴标签序列（年度用年份整数，季度用 '2020Q1' 字符串）
    values: 与 labels 等长的数值序列，None 表示缺测
    quarterly: True 时 x 轴仅在每年 Q1 标年份、季度点标数值标签、画年分隔竖线
    """
    # 紧凑边距：让折线区域占满画布
    padL, padR, padT, padB = 34, 22, 24, 20
    plotW = W - padL - padR
    plotH = H - padT - padB
    xs, xf = padL, W - padR
    ys, yf = padT, H - padB

    vs = [v for v in values if isinstance(v, (int, float))]
    if not vs:
        return make_placeholder(title, W, H)
    vmax, vmin = max(vs), min(vs)
    ylo = 0 if vmin >= 0 else nice_floor(vmin)
    yhi = nice_ceil(vmax)
    if yhi == ylo:
        yhi = ylo + 1

    n = len(values)

    def X(i):
        return xs + (plotW * (i / (n - 1)) if n > 1 else plotW / 2)

    def Y(v):
        return ys + plotH * (1 - (v - ylo) / (yhi - ylo))

    out = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">']
    out.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')
    out.append(f'<text x="{padL}" y="16" fill="#1f2733" font-size="13" font-weight="700">{title}（{unit}）</text>')
    for g in range(5):
        val = ylo + (yhi - ylo) * g / 4
        gy = Y(val)
        out.append(f'<line x1="{xs}" y1="{gy:.1f}" x2="{xf}" y2="{gy:.1f}" stroke="#e3e8ee" stroke-width="1"/>')
        out.append(f'<text x="{xs-6}" y="{gy+3.5:.1f}" fill="#7a8694" font-size="10" text-anchor="end">{fmt_axis(val)}</text>')
    out.append(f'<line x1="{xs}" y1="{yf:.1f}" x2="{xf}" y2="{yf:.1f}" stroke="#c3ccd6" stroke-width="1"/>')

    if quarterly:
        for i, lb in enumerate(labels):
            try:
                q = int(str(lb).split("Q")[1])
            except Exception:
                q = 1
            if q == 1:
                out.append(f'<line x1="{X(i):.1f}" y1="{ys}" x2="{X(i):.1f}" y2="{yf:.1f}" stroke="#eef2f6" stroke-width="1"/>')

    d = ""
    for i, v in enumerate(values):
        if v is None:
            continue
        d += ("L" if d else "M") + f"{X(i):.1f} {Y(v):.1f} "
    if d:
        out.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
    for i, v in enumerate(values):
        if v is None:
            continue
        out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3" fill="{color}"/>')

    for i, lb in enumerate(labels):
        if quarterly:
            try:
                yr = int(str(lb).split("Q")[0]); q = int(str(lb).split("Q")[1])
            except Exception:
                yr, q = lb, 1
            txt = str(yr) if q == 1 else ""
            if txt:
                out.append(f'<text x="{X(i):.1f}" y="{H-8}" fill="#7a8694" font-size="10" text-anchor="middle">{txt}</text>')
        elif lb is not None:
            out.append(f'<text x="{X(i):.1f}" y="{H-8}" fill="#7a8694" font-size="10" text-anchor="middle">{lb}</text>')

    # 数值标签：字号加大、与数据点间距加大，提升可读性
    for i, v in enumerate(values):
        if v is None:
            continue
        if quarterly:
            try:
                q = int(str(labels[i]).split("Q")[1]) if "Q" in str(labels[i]) else 1
            except Exception:
                q = 1
            if q != 1:
                continue
        out.append(f'<text x="{X(i):.1f}" y="{Y(v)-9:.1f}" fill="#1f2733" font-size="11" font-weight="600" text-anchor="middle">{fmt_val(v, unit)}</text>')

    out.append("</svg>")
    return "".join(out)


def make_placeholder(title, W=720, H=280):
    """年度-only 指标的季度占位图。"""
    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">'
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#f7f9fb" stroke="#e3e8ee" stroke-dasharray="5 4"/>'
        f'<text x="{W/2}" y="{H/2-6}" fill="#7a8694" font-size="14" font-weight="700" text-anchor="middle">{title}</text>'
        f'<text x="{W/2}" y="{H/2+18}" fill="#9aa6b2" font-size="12" text-anchor="middle">该指标仅披露年度数据（季报数据表未含相应列）</text>'
        f'</svg>'
    )
