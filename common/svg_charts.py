# -*- coding: utf-8 -*-
"""跨看板通用 SVG 图表生成库（/业绩追踪看板/common）。

本模块是从各看板「本地副本」抽出来的**泛型**工具，不含任何项目数据/品牌：
- 原 china-mobile/gen_line_svg.py 与 china-telecom/gen_line_svg.py 逐字节相同，
  于 2026-09-05 合并到此（Phase 0 重构）；
- cosco-shipping/build_tracker.py 的 make_stacked_bar_svg / make_pct_stacked_bar_svg
  与宽幅折线图 make_line_svg_wide 于 2026-09-05 收进本模块（Phase 2 重构）。
  说明：make_line_svg（移动端紧凑版）与 make_line_svg_wide（cosco 宽幅副标题版）
  渲染风格不同，二者并存而非强行合并——强行统一会改变任一侧既有图表像素，
  违背「重构不改变输出」的硬约束。make_stacked_bar_svg / make_pct_stacked_bar_svg
  为 cosco 独有，直接整体迁入（含其默认 src_note 文案，与调用处显式传参一致）。

设计原则：本库只负责「给定 labels/values/color → 返回 SVG 字符串」，
具体指标语义、品牌配色、卡片结构由各看板本地决定（保持项目间严格隔离）。

用法（看板构建脚本顶部）：
    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from common.svg_charts import make_line_svg, make_placeholder, nice_ceil, nice_floor

    svg = make_line_svg("营业收入", "亿元", [2020, 2021], [7680.7, 7890.1], "#c8102e")
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


def make_line_svg(title, unit, labels, values, color, W=780, H=300, quarterly=False,
                  vfmt=None, src_note=None, ptype="年"):
    """单序列折线图 SVG（canonical 统一风格：780×300 宽版、无副标题、浅色主题）。

    与 make_line_svg_wide 共享同一渲染逻辑，是全看板「简单趋势图」的唯一入口。
    - 年度(quarterly=False)：x 轴逐点标年份，逐点标数值。
    - 季度(quarterly=True)：仅每年 Q1 标年份 + 画年分隔竖线，数值标签仅标 Q1 点。
    - y 轴 band 缩放（留白 12%），#eef2f6 网格，#7a8694 刻度。
    - 固定 780×300（忽略调用方传入的 W/H，显示由 CSS 自适应缩放）；src_note/ptype 不再输出。
    """
    W, H = 780, 300  # 统一画布，忽略调用方旧参数
    if vfmt is None:
        vfmt = (lambda v: fmt_val(v, unit)) if unit else (lambda v: f"{v:,.0f}")
    padL, padR, padT, padB = 54, 18, 40, 44
    plotW = W - padL - padR
    plotH = H - padT - padB
    xs, xf = padL, W - padR
    ys, yf = padT, H - padB
    vs = [v for v in values if isinstance(v, (int, float))]
    if not vs:
        return make_placeholder(title, W, H)
    n = len(values)
    vmax, vmin = max(vs), min(vs)
    span = (vmax - vmin) or 1
    ylo = vmin - span * 0.12
    yhi = vmax + span * 0.12
    if ylo == yhi:
        ylo = yhi - 1
        yhi = yhi + 1

    def X(i):
        return xs + (plotW * (i / (n - 1)) if n > 1 else plotW / 2)

    def Y(v):
        return ys + plotH * (1 - (v - ylo) / (yhi - ylo))

    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    # 仅标题，无副标题（数据源说明已移除）
    o.append('<text x="%d" y="22" fill="#1f2733" font-size="14" font-weight="700">%s</text>' % (padL, title))
    T = 5
    for g in range(T + 1):
        val = ylo + (yhi - ylo) * g / T
        gy = Y(val)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (xs, gy, xf, gy))
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="10" text-anchor="end">%s</text>' % (xs - 6, gy + 3.5, vfmt(val)))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (xs, yf, xf, yf))
    for i, lb in enumerate(labels):
        q = None
        if quarterly:
            try:
                q = int(str(lb).split("Q")[1])
            except Exception:
                q = 1
        if q == 1:
            o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef2f6" stroke-width="1"/>' % (X(i), ys, X(i), yf))
        anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
        if quarterly:
            txt = str(lb).split("Q")[0] if q == 1 else ""
        else:
            txt = str(lb)
        lx = X(i) + (4 if i == 0 else (-4 if i == n - 1 else 0))
        if txt:
            o.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="8.5" text-anchor="%s">%s</text>' % (lx, H - 16, anchor, txt))
    d = ""
    for i, v in enumerate(values):
        if v is None:
            continue
        d += ("L" if d else "M") + "%.1f %.1f " % (X(i), Y(v))
    if d:
        o.append('<path d="%s" fill="none" stroke="%s" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' % (d, color))
    for i, v in enumerate(values):
        if v is None:
            continue
        o.append('<circle cx="%.1f" cy="%.1f" r="2.8" fill="%s"/>' % (X(i), Y(v), color))
        # 数值标签：年度逐点；季度仅 Q1
        if quarterly:
            q = int(str(labels[i]).split("Q")[1]) if "Q" in str(labels[i]) else 1
            if q != 1:
                continue
        o.append('<text x="%.1f" y="%.1f" fill="%s" font-size="9" text-anchor="middle">%s</text>' % (X(i), Y(v) - 7, color, vfmt(v)))
    o.append('</svg>')
    return "".join(o)


def make_placeholder(title, W=780, H=300):
    """年度-only 指标的季度占位图。固定 780×300 以与 canonical 趋势图一致。"""
    W, H = 780, 300
    return (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">'
        f'<rect x="0" y="0" width="{W}" height="{H}" fill="#f7f9fb" stroke="#e3e8ee" stroke-dasharray="5 4"/>'
        f'<text x="{W/2}" y="{H/2-6}" fill="#7a8694" font-size="14" font-weight="700" text-anchor="middle">{title}</text>'
        f'<text x="{W/2}" y="{H/2+18}" fill="#9aa6b2" font-size="12" text-anchor="middle">该指标仅披露年度数据（季报数据表未含相应列）</text>'
        f'</svg>'
    )


def make_line_svg_wide(title, unit, labels, values, color, vfmt=None, W=780, H=300, src_note=None, ptype="季"):
    """cosco-shipping 宽幅折线图入口 —— 现已统一为 canonical 单序列折线渲染
    （780×300、无副标题）。仅保留旧签名以兼容 build_tracker.py 调用；
    src_note/ptype 不再输出（数据源说明已移除）。"""
    return make_line_svg(title, unit, labels, values, color, W=W, H=H,
                         quarterly=any("Q" in str(lb) for lb in labels), vfmt=vfmt)


def make_stacked_bar_svg(title, unit, labels, series, colors, vfmt=None, W=780, H=330, src_note=None, ptype="年"):
    """年度堆叠柱 SVG（浅色主题，顶部图例，水平网格，柱顶总值标签）。
    series=[(name, values), ...] 从底到顶；colors 等长；vfmt 默认 .0f。"""
    if vfmt is None: vfmt=lambda v:f"{v:.0f}"
    if src_note is None: src_note = "中远海控_财报核心数据.xlsx · 成本结构(集装箱航运业务)"
    padL, padR, padT, padB = 54, 18, 58, 44
    plotW = W - padL - padR
    plotH = H - padT - padB
    n = len(labels)
    totals = [sum(v[i] for _, v in series) for i in range(n)]
    vmax = max(totals) if totals else 1
    yhi = float(nice_ceil(vmax * 1.08)) if vmax > 0 else 1
    ylo = 0.0
    if yhi == ylo: yhi = ylo + 1
    def Y(v): return padT + plotH * (1 - (v - ylo) / (yhi - ylo))
    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('<text x="%d" y="20" fill="#1f2733" font-size="14" font-weight="700">%s</text>' % (padL, title))
    o.append('<text x="%d" y="36" fill="#9aa6b2" font-size="10">单位：%s · 样本 %d %s · %s ~ %s · 数据源：%s</text>' % (padL, unit, n, ptype, labels[0], labels[-1], src_note))
    # 图例（顶部一行，右对齐）
    legW = sum(len(nm)*10 + 26 for nm, _ in series)
    lx = W - padR - legW
    for idx, (nm, _) in enumerate(series):
        o.append('<rect x="%.1f" y="12" width="10" height="10" rx="2" fill="%s"/>' % (lx, colors[idx]))
        o.append('<text x="%.1f" y="21" fill="#1f2733" font-size="10.5">%s</text>' % (lx + 14, nm))
        lx += len(nm) * 10 + 26
    # 横向网格 + y 刻度
    T = 5
    for g in range(T + 1):
        val = ylo + (yhi - ylo) * g / T; gy = Y(val)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (padL, gy, W - padR, gy))
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="10" text-anchor="end">%s</text>' % (padL - 6, gy + 3.5, vfmt(val)))
    # x 轴线
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (padL, Y(ylo), W - padR, Y(ylo)))
    # 堆叠柱
    gap = plotW / (n + 1)
    bw = gap * 0.55
    for i in range(n):
        x = padL + gap * (i + 1) - bw / 2
        bottom = 0.0
        y_bot = Y(ylo)
        for (nm, vals), col in zip(series, colors):
            v = vals[i]
            y_top = Y(bottom + v)
            h = y_bot - y_top
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="2"/>' % (x, y_top, bw, h, col))
            # 段内占比百分数：标注该分段占当年总值的百分比；段过矮则跳过避免拥挤
            if totals[i] > 0 and h >= 10:
                pct = round(v / totals[i] * 100)
                o.append('<text x="%.1f" y="%.1f" fill="#ffffff" font-size="9" text-anchor="middle" font-weight="700">%d%%</text>' % (x + bw / 2, y_top + h / 2 + 3.0, pct))
            bottom += v
            y_bot = y_top
        # 柱顶总值标签
        o.append('<text x="%.1f" y="%.1f" fill="#1f2733" font-size="9.5" text-anchor="middle" font-weight="600">%s</text>' % (x + bw / 2, Y(totals[i]) - 5, vfmt(totals[i])))
    # x 轴年份标签
    for i, lb in enumerate(labels):
        cx = padL + gap * (i + 1)
        o.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="10" text-anchor="middle">%s</text>' % (cx, H - 16, lb))
    o.append('</svg>')
    return "".join(o)


def make_pct_stacked_bar_svg(title, labels, routes, shares, colors, W=780, H=330, src_note=None, ptype="年"):
    """100% 堆叠柱 SVG：每根柱各段份额之和=100%。顶部图例、水平网格、段内占比标签。
    shares: {route: [pct,...]} 每根柱之和应为 100；colors 与 routes 顺序一致。"""
    if src_note is None:
        src_note = "中远海控_货运量与航线结构数据.xlsx · 分航线箱量与收入明细"
    padL, padR, padT, padB = 54, 18, 58, 44
    plotW = W - padL - padR
    plotH = H - padT - padB
    n = len(labels)
    yhi, ylo = 100.0, 0.0
    def Y(v): return padT + plotH * (1 - (v - ylo) / (yhi - ylo))
    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('<text x="%d" y="20" fill="#1f2733" font-size="14" font-weight="700">%s</text>' % (padL, title))
    o.append('<text x="%d" y="36" fill="#9aa6b2" font-size="10">单位：%% · 100%% 堆叠 · 样本 %d %s · %s ~ %s · 数据源：%s</text>' % (padL, n, ptype, labels[0], labels[-1], src_note))
    # 图例（顶部一行，右对齐）
    legW = sum(len(nm) * 10 + 26 for nm in routes)
    lx = W - padR - legW
    for idx, nm in enumerate(routes):
        o.append('<rect x="%.1f" y="12" width="10" height="10" rx="2" fill="%s"/>' % (lx, colors[idx]))
        o.append('<text x="%.1f" y="21" fill="#1f2733" font-size="10.5">%s</text>' % (lx + 14, nm))
        lx += len(nm) * 10 + 26
    # 横向网格 + y 刻度（0–100）
    T = 5
    for g in range(T + 1):
        val = ylo + (yhi - ylo) * g / T; gy = Y(val)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (padL, gy, W - padR, gy))
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="10" text-anchor="end">%d%%</text>' % (padL - 6, gy + 3.5, int(val)))
    # x 轴线
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (padL, Y(ylo), W - padR, Y(ylo)))
    # 100% 堆叠柱（每段之和=100，无需柱顶总值标签）
    gap = plotW / (n + 1)
    bw = gap * 0.55
    for i in range(n):
        x = padL + gap * (i + 1) - bw / 2
        bottom = 0.0
        y_bot = Y(ylo)
        for nm, col in zip(routes, colors):
            v = shares[nm][i]
            y_top = Y(bottom + v)
            h = y_bot - y_top
            o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" rx="2"/>' % (x, y_top, bw, h, col))
            if h >= 10:
                pct = round(v)
                o.append('<text x="%.1f" y="%.1f" fill="#ffffff" font-size="9" text-anchor="middle" font-weight="700">%d%%</text>' % (x + bw / 2, y_top + h / 2 + 3.0, pct))
            bottom += v
            y_bot = y_top
    # x 轴年份标签
    for i, lb in enumerate(labels):
        cx = padL + gap * (i + 1)
        o.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="10" text-anchor="middle">%s</text>' % (cx, H - 16, lb))
    o.append('</svg>')
    return "".join(o)
