# -*- coding: utf-8 -*-
"""
只读 数据源/中煤能源_月度经营数据.xlsx，生成「月度经营数据追踪」卡片（原卡片6）的 5 张 svg：
  - trend_m_prod.svg        商品煤产量（万吨）          sheet1 B 列
  - trend_m_sales.svg       商品煤销量（万吨）          sheet1 C 列
  - trend_m_selfsales.svg   自产商品煤销量（万吨）      sheet1 D 列
  - trend_m_equip.svg       煤矿装备产值（亿元）        sheet2 G 列
  - trend_m_chem.svg        煤化工业务（万吨）          sheet2 B-F 列合并（5 条线）
并为每张图生成对应的 sparkline（spark_m_*.svg）。

x 轴：2026年1月…7月（共 7 个月度点）。
注意 sheet2 的 F 列（尿素）2月、4月为空（单月未披露）→ 该点断点不连线。

重要：本脚本只读取 xlsx、只写出 SVG，绝不写回 xlsx。
用法（在 china-coal/ 目录下）：
    python3 build_monthly_svg.py
依赖：openpyxl（仅读取）
"""
import openpyxl

FID = "数据源/中煤能源_月度经营数据.xlsx"

MONTH_LABELS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月"]


def load_monthly_col(ws, col_letter):
    """读取某列（跳过表头与『累计』行），返回 [(label, value), ...]；空值返回 None。"""
    col = openpyxl.utils.column_index_from_string(col_letter)
    rows = []
    for r in range(2, ws.max_row + 1):
        m = ws.cell(row=r, column=1).value
        if m is None:
            continue
        if "累计" in str(m):
            continue
        v = ws.cell(row=r, column=col).value
        val = float(v) if isinstance(v, (int, float)) else None
        rows.append((str(m), val))
    return rows


def load_monthly_multi(ws, col_letters):
    """读取多列，返回 {col_letter: [(label, value_or_None), ...]}；仅取月份行（与单列同序）。"""
    base = load_monthly_col(ws, col_letters[0])
    labels = [lab for lab, _ in base]
    out = {}
    for cl in col_letters:
        col = openpyxl.utils.column_index_from_string(cl)
        series = []
        for r in range(2, ws.max_row + 1):
            m = ws.cell(row=r, column=1).value
            if m is None or "累计" in str(m):
                continue
            v = ws.cell(row=r, column=col).value
            series.append((str(m), float(v) if isinstance(v, (int, float)) else None))
        out[cl] = series
    return labels, out


# ---------- 单序列月度趋势图 ----------
def build_trend_m(series, fname, title, color="#c53030", unit="万吨"):
    W, H = 1000, 420
    ml, mr, mt, mb = 60, 24, 42, 56
    plot_bottom = H - mb
    ph = plot_bottom - mt
    pw = W - ml - mr
    labels = [lab for lab, _ in series]
    vals = [v for _, v in series if v is not None]
    n = len(series)
    # x 均匀分布（含空值点占位，但仅画有效点）
    xs = [ml + pw * i / (n - 1) for i in range(n)]
    vmin, vmax = min(vals), max(vals)
    pad = (vmax - vmin) * 0.18 or 10
    vmin, vmax = vmin - pad, vmax + pad
    def yp(v):
        return mt + ph - (v - vmin) / (vmax - vmin) * ph
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">']
    svg.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    svg.append(f'<text x="{ml}" y="26" font-size="16" font-weight="700" fill="#1e3a5f">{title}</text>')
    for k in range(5):
        yv = vmin + (vmax - vmin) * k / 4
        yy = yp(yv)
        svg.append(f'<line x1="{ml}" y1="{yy:.1f}" x2="{ml+pw}" y2="{yy:.1f}" stroke="#eef1f5"/>')
        svg.append(f'<text x="{ml-8}" y="{yy+4:.1f}" font-size="11" fill="#9ca3af" text-anchor="end">{yv:.0f}</text>')
    svg.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{plot_bottom}" stroke="#d1d5db"/>')
    svg.append(f'<line x1="{ml}" y1="{plot_bottom}" x2="{ml+pw}" y2="{plot_bottom}" stroke="#d1d5db"/>')
    # 折线（断点处理：None 处断开）
    seg = []
    for i, (lab, v) in enumerate(series):
        if v is None:
            if seg:
                svg.append(f'<path d="M{" L".join(seg)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
                seg = []
            continue
        seg.append(f"{xs[i]:.1f} {yp(v):.1f}")
    if seg:
        svg.append(f'<path d="M{" L".join(seg)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
    for i, (lab, v) in enumerate(series):
        if v is None:
            continue
        cx, cy = xs[i], yp(v)
        svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.6" fill="{color}" stroke="#fff" stroke-width="1"/>')
        svg.append(f'<text x="{cx:.1f}" y="{cy-12:.1f}" font-size="12" fill="#374151" text-anchor="middle">{v:.0f}</text>')
        svg.append(f'<text x="{cx:.1f}" y="{plot_bottom+18:.1f}" font-size="11" fill="#6b7280" text-anchor="middle">{MONTH_LABELS[i]}</text>')
    svg.append(f'<text x="{ml+pw}" y="{H-10}" font-size="10.5" fill="#9ca3af" text-anchor="end">单位:{unit}</text>')
    svg.append('</svg>')
    with open(fname, "w", encoding="utf-8") as f:
        f.write("".join(svg))
    print(f"✅ 生成月度趋势图：{fname}（{n} 个月度点，有效 {len(vals)}）")


# ---------- 多序列月度趋势图（煤化工 B-F 五线） ----------
def build_trend_m_multi(labels, data, fname, title, series_meta, unit="万吨"):
    W, H = 1000, 460
    ml, mr, mt, mb = 60, 24, 42, 92
    plot_bottom = H - mb
    ph = plot_bottom - mt
    pw = W - ml - mr
    n = len(labels)
    xs = [ml + pw * i / (n - 1) for i in range(n)]
    allvals = [v for cl in data for _, v in data[cl] if v is not None]
    vmin, vmax = min(allvals), max(allvals)
    pad = (vmax - vmin) * 0.18 or 10
    vmin, vmax = vmin - pad, vmax + pad
    def yp(v):
        return mt + ph - (v - vmin) / (vmax - vmin) * ph
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">']
    svg.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    svg.append(f'<text x="{ml}" y="26" font-size="16" font-weight="700" fill="#1e3a5f">{title}</text>')
    for k in range(5):
        yv = vmin + (vmax - vmin) * k / 4
        yy = yp(yv)
        svg.append(f'<line x1="{ml}" y1="{yy:.1f}" x2="{ml+pw}" y2="{yy:.1f}" stroke="#eef1f5"/>')
        svg.append(f'<text x="{ml-8}" y="{yy+4:.1f}" font-size="11" fill="#9ca3af" text-anchor="end">{yv:.0f}</text>')
    svg.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{plot_bottom}" stroke="#d1d5db"/>')
    svg.append(f'<line x1="{ml}" y1="{plot_bottom}" x2="{ml+pw}" y2="{plot_bottom}" stroke="#d1d5db"/>')
    # 每条线
    for cl, (lab, color) in series_meta.items():
        s = data[cl]
        seg = []
        for i, (m, v) in enumerate(s):
            if v is None:
                if seg:
                    svg.append(f'<path d="M{" L".join(seg)}" fill="none" stroke="{color}" stroke-width="2.2"/>')
                    seg = []
                continue
            seg.append(f"{xs[i]:.1f} {yp(v):.1f}")
        if seg:
            svg.append(f'<path d="M{" L".join(seg)}" fill="none" stroke="{color}" stroke-width="2.2"/>')
        for i, (m, v) in enumerate(s):
            if v is None:
                continue
            cx, cy = xs[i], yp(v)
            svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.8" fill="{color}" stroke="#fff" stroke-width="1"/>')
    # x 轴月份
    for i in range(n):
        svg.append(f'<text x="{xs[i]:.1f}" y="{plot_bottom+18:.1f}" font-size="11" fill="#6b7280" text-anchor="middle">{MONTH_LABELS[i]}</text>')
    # 图例
    lx = ml
    ly = H - 30
    for cl, (lab, color) in series_meta.items():
        svg.append(f'<rect x="{lx}" y="{ly-10}" width="12" height="12" rx="2" fill="{color}"/>')
        svg.append(f'<text x="{lx+16}" y="{ly}" font-size="11" fill="#374151">{lab}</text>')
        lx += 16 + len(lab) * 13 + 18
    svg.append(f'<text x="{ml+pw}" y="{H-10}" font-size="10.5" fill="#9ca3af" text-anchor="end">单位:{unit}</text>')
    svg.append('</svg>')
    with open(fname, "w", encoding="utf-8") as f:
        f.write("".join(svg))
    print(f"✅ 生成月度多线趋势图：{fname}（{len(series_meta)} 条线 × {n} 月）")


# ---------- sparkline（取月度序列，断点跳过） ----------
def build_spark(vals, fname, color="#c53030"):
    W, H = 62, 28
    pts_v = [v for v in vals if v is not None]
    n = len(pts_v)
    if n < 2:
        # 单点或不连续：画平线
        svg = [f'<svg class="spark" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">']
        svg.append(f'<path d="M2 {H/2} L{W-2} {H/2}" fill="none" stroke="{color}" stroke-width="2"/>')
        svg.append('</svg>')
        with open(fname, "w", encoding="utf-8") as f:
            f.write("".join(svg))
        print(f"✅ 生成 sparkline（平线）：{fname}")
        return
    xs = [2 + (W - 4) * i / (n - 1) for i in range(n)]
    vmin, vmax = min(pts_v), max(pts_v)
    pad = (vmax - vmin) * 0.15 or 1
    def yp(v):
        return 4 + (H - 8) - (v - (vmin - pad)) / ((vmax + pad) - (vmin - pad)) * (H - 8)
    pts = [f"{xs[i]:.1f} {yp(pts_v[i]):.1f}" for i in range(n)]
    svg = [f'<svg class="spark" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<path d="M{" L".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>')
    svg.append('</svg>')
    with open(fname, "w", encoding="utf-8") as f:
        f.write("".join(svg))
    print(f"✅ 生成 sparkline：{fname}（{n} 点）")


if __name__ == "__main__":
    wb = openpyxl.load_workbook(FID, data_only=True)
    ws1 = wb["煤炭业务月度数据"]
    ws2 = wb["煤化工与煤矿装备月度数据"]

    # 4 个单线指标
    prod = load_monthly_col(ws1, "B")   # 商品煤产量
    sales = load_monthly_col(ws1, "C")  # 商品煤销量
    selfs = load_monthly_col(ws1, "D")  # 自产商品煤销量
    equip = load_monthly_col(ws2, "G")  # 煤矿装备产值

    build_trend_m(prod, "trend_m_prod.svg", "中煤能源 商品煤产量（2026年1-7月·万吨）", "#c53030", "万吨")
    build_trend_m(sales, "trend_m_sales.svg", "中煤能源 商品煤销量（2026年1-7月·万吨）", "#15616d", "万吨")
    build_trend_m(selfs, "trend_m_selfsales.svg", "中煤能源 自产商品煤销量（2026年1-7月·万吨）", "#2e9e6b", "万吨")
    build_trend_m(equip, "trend_m_equip.svg", "中煤能源 煤矿装备产值（2026年1-7月·亿元）", "#d98a14", "亿元")

    build_spark([v for _, v in prod], "spark_m_prod.svg", "#c53030")
    build_spark([v for _, v in sales], "spark_m_sales.svg", "#15616d")
    build_spark([v for _, v in selfs], "spark_m_selfsales.svg", "#2e9e6b")
    build_spark([v for _, v in equip], "spark_m_equip.svg", "#d98a14")

    # 煤化工业务（B-F 五线合并）
    labels, chem = load_monthly_multi(ws2, ["B", "C", "D", "E", "F"])
    chem_meta = {
        "B": ("聚乙烯", "#c53030"),
        "C": ("聚丙烯", "#15616d"),
        "D": ("甲醇", "#2e9e6b"),
        "E": ("硝铵", "#d98a14"),
        "F": ("尿素", "#7a5cc8"),
    }
    build_trend_m_multi(labels, chem, "trend_m_chem.svg", "中煤能源 煤化工主要产品产量（2026年1-7月·万吨）", chem_meta, "万吨")
    build_spark([v for _, v in chem["D"]], "spark_m_chem.svg", "#2e9e6b")  # 以甲醇为主序列

    print("✅ 完成（未写回 xlsx）")
