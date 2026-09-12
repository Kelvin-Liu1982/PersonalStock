# -*- coding: utf-8 -*-
"""
只读 数据源/中煤能源_月度经营数据.xlsx，生成「月度经营数据追踪」卡片（原卡片6）的 5 张 svg：
  - trend_m_prod.svg        商品煤产量（万吨）          sheet1 B 列
  - trend_m_sales.svg       商品煤销量（万吨）          sheet1 C 列
  - trend_m_selfsales.svg   自产商品煤销量（万吨）      sheet1 D 列
  - trend_m_equip.svg       煤矿装备产值（亿元）        sheet2 G 列
  - trend_m_chem.svg        煤化工业务（万吨）          sheet2 B-F 列合并（5 条线）
并为每张图生成对应的 sparkline（spark_m_*.svg，取 2026 当年序列）。

x 轴：1月…8月（共 8 个月度点）。
双折线：每个指标图同时画 2026 实际（实线 + 数值标签）与 2025 同期（虚线 + 数值标签），便于同比对照。
注意 sheet2 的 F 列（尿素）2025/2026 个别月份为空（单月未披露）→ 该点断点不连线。

数据源结构：
  - 2026 月度块在行 2-8（月份为字符串 '2026年N月'），行 9 为 '1-7月累计'（跳过）。
  - 2025 月度块紧随其后（月份为 datetime 2025 年），末行为 '1-7月累计'（跳过）。
  - 2025 与 2026 同列（如 B 列既含 2026 产量也含 2025 产量），靠行块区分年份。

重要：本脚本只读取 xlsx、只写出 SVG，绝不写回 xlsx。
用法（在 china-coal/ 目录下）：
    python3 build_monthly_svg.py
依赖：openpyxl（仅读取）
"""
import os
import datetime
import openpyxl

# ── 路径基准 ───────────────────────────────────────────────────────
# 本脚本位于 <项目根>/src/，统一把工作目录切到项目根，
# 让「数据源/…」「svg/…」「china-coal-dashboard.html」等既有相对路径
# 保持有效——无论从哪个目录执行，结果都一致。
import os as _os
_os.chdir(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

SVG_DIR = "svg"   # 图表统一输出到 svg/ 子目录
os.makedirs(SVG_DIR, exist_ok=True)

FID = "数据源/中煤能源_月度经营数据.xlsx"

MONTH_LABELS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月"]


def _year_of(m):
    """从月份单元格判断年份：字符串 'YYYY年N月' 或 datetime。"""
    if isinstance(m, datetime.datetime):
        return m.year
    if isinstance(m, str):
        for y in (2026, 2025, 2024, 2023):
            if m.startswith(str(y) + "年"):
                return y
    return None


def _label_of(m):
    """月份单元格 → 'N月' 短标签（与 MONTH_LABELS 对齐）。"""
    if isinstance(m, datetime.datetime):
        return f"{m.month}月"
    if isinstance(m, str) and "年" in m:
        return m.split("年", 1)[1]
    return str(m) if m is not None else ""


def load_monthly_col(ws, col_letter, year=2026):
    """读取某列某年的月度块（跳过表头/空行/'累计'行），返回 [(label, value), ...]；空值 None。"""
    col = openpyxl.utils.column_index_from_string(col_letter)
    rows = []
    for r in range(2, ws.max_row + 1):
        m = ws.cell(row=r, column=1).value
        if m is None:
            continue
        if isinstance(m, str) and "累计" in m:
            continue
        if _year_of(m) != year:
            continue
        v = ws.cell(row=r, column=col).value
        val = float(v) if isinstance(v, (int, float)) else None
        rows.append((_label_of(m), val))
    return rows


def load_monthly_multi(ws, col_letters, year=2026):
    """读取多列某年的月度块，返回 (labels, {col_letter: [(label, value_or_None), ...]})。"""
    base = load_monthly_col(ws, col_letters[0], year)
    labels = [lab for lab, _ in base]
    out = {}
    for cl in col_letters:
        col = openpyxl.utils.column_index_from_string(cl)
        series = []
        for r in range(2, ws.max_row + 1):
            m = ws.cell(row=r, column=1).value
            if m is None or isinstance(m, str) and "累计" in m:
                continue
            if _year_of(m) != year:
                continue
            v = ws.cell(row=r, column=col).value
            series.append((_label_of(m), float(v) if isinstance(v, (int, float)) else None))
        out[cl] = series
    return labels, out


# ---------- 单序列月度趋势图（支持第二序列：2025 同期虚线） ----------
def build_trend_m(series, fname, title, color="#c53030", unit="万吨", series2=None):
    W, H = 1000, 440
    ml, mr, mt, mb = 60, 24, 42, 56
    plot_bottom = H - mb
    ph = plot_bottom - mt
    pw = W - ml - mr
    n = len(series)
    xs = [ml + pw * i / (n - 1) for i in range(n)]
    # y 范围需同时容纳两条线
    vals = [v for _, v in series if v is not None]
    if series2:
        vals += [v for _, v in series2 if v is not None]
    vmin, vmax = min(vals), max(vals)
    pad = (vmax - vmin) * 0.20 or 10
    vmin, vmax = vmin - pad, vmax + pad
    def yp(v):
        return mt + ph - (v - vmin) / (vmax - vmin) * ph
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">']
    svg.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    # 顶部标题：双击放大时仍可见，弹窗内与 modal 标题视觉重复但可接受
    svg.append(f'<text x="{ml}" y="22" fill="#1f2733" font-size="14" font-weight="700">{title}</text>')
    # 年份图例（右上角）
    xr = ml + pw
    svg.append(f'<text x="{xr}" y="24" font-size="11" fill="#64748b" text-anchor="end">2025同期</text>')
    svg.append(f'<line x1="{xr-66}" y1="20" x2="{xr-46}" y2="20" stroke="#64748b" stroke-width="2" stroke-dasharray="5 3"/>')
    xr2 = xr - 92
    svg.append(f'<text x="{xr2}" y="24" font-size="11" fill="{color}" text-anchor="end">2026</text>')
    svg.append(f'<line x1="{xr2-54}" y1="20" x2="{xr2-34}" y2="20" stroke="{color}" stroke-width="2.5"/>')
    # 网格 + y 轴刻度
    for k in range(5):
        yv = vmin + (vmax - vmin) * k / 4
        yy = yp(yv)
        svg.append(f'<line x1="{ml}" y1="{yy:.1f}" x2="{ml+pw}" y2="{yy:.1f}" stroke="#eef1f5"/>')
        svg.append(f'<text x="{ml-8}" y="{yy+4:.1f}" font-size="11" fill="#9ca3af" text-anchor="end">{yv:.0f}</text>')
    svg.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{plot_bottom}" stroke="#d1d5db"/>')
    svg.append(f'<line x1="{ml}" y1="{plot_bottom}" x2="{ml+pw}" y2="{plot_bottom}" stroke="#d1d5db"/>')
    # --- 2025 同期：虚线（先画，置于底层） ---
    if series2:
        seg = []
        for i, (lab, v) in enumerate(series2):
            if v is None:
                if seg:
                    svg.append(f'<path d="M{" L".join(seg)}" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5 3"/>')
                    seg = []
                continue
            seg.append(f"{xs[i]:.1f} {yp(v):.1f}")
        if seg:
            svg.append(f'<path d="M{" L".join(seg)}" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5 3"/>')
        for i, (lab, v) in enumerate(series2):
            if v is None:
                continue
            cx, cy = xs[i], yp(v)
            svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#94a3b8" stroke="#fff" stroke-width="1"/>')
            svg.append(f'<text x="{cx:.1f}" y="{cy+16:.1f}" font-size="10" fill="#64748b" text-anchor="middle">{v:.0f}</text>')
    # --- 2026 实际：实线（后画，置于上层） ---
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
        svg.append(f'<text x="{cx:.1f}" y="{cy-12:.1f}" font-size="12" font-weight="600" fill="#374151" text-anchor="middle">{v:.0f}</text>')
        svg.append(f'<text x="{cx:.1f}" y="{plot_bottom+18:.1f}" font-size="11" fill="#6b7280" text-anchor="middle">{MONTH_LABELS[i]}</text>')
    svg.append('</svg>')
    with open(fname, "w", encoding="utf-8") as f:
        f.write("".join(svg))
    print(f"✅ 生成月度趋势图（双线）：{fname}（{n} 月；2026+2025同期）")


# ---------- 多序列月度趋势图（煤化工 B-F 五线，每条含 2025 虚线） ----------
def build_trend_m_multi(labels, data, fname, title, series_meta, unit="万吨", data2=None):
    W, H = 1000, 470
    # mt 由 42 提到 62：为右上角「产品图例」腾出第二行；
    # mb 由 96 收到 56：原底部空间是给图例留的，图例移除后收回，避免下方大片空白
    ml, mr, mt, mb = 60, 24, 62, 56
    plot_bottom = H - mb
    ph = plot_bottom - mt
    pw = W - ml - mr
    n = len(labels)
    xs = [ml + pw * i / (n - 1) for i in range(n)]
    allvals = [v for cl in data for _, v in data[cl] if v is not None]
    if data2:
        allvals += [v for cl in data2 for _, v in data2[cl] if v is not None]
    vmin, vmax = min(allvals), max(allvals)
    pad = (vmax - vmin) * 0.18 or 10
    vmin, vmax = vmin - pad, vmax + pad
    def yp(v):
        return mt + ph - (v - vmin) / (vmax - vmin) * ph
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">']
    svg.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    # 顶部标题：双击放大时仍可见，弹窗内与 modal 标题视觉重复但可接受
    svg.append(f'<text x="{ml}" y="22" fill="#1f2733" font-size="14" font-weight="700">{title}</text>')
    # 年份图例（右上角，颜色仅作示意）
    xr = ml + pw
    svg.append(f'<text x="{xr}" y="24" font-size="11" fill="#64748b" text-anchor="end">2025同期（虚线）</text>')
    svg.append(f'<line x1="{xr-118}" y1="20" x2="{xr-98}" y2="20" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5 3"/>')
    xr2 = xr - 134
    svg.append(f'<text x="{xr2}" y="24" font-size="11" fill="#374151" text-anchor="end">2026（实线）</text>')
    svg.append(f'<line x1="{xr2-104}" y1="20" x2="{xr2-84}" y2="20" stroke="#475569" stroke-width="2.5"/>')
    # 产品图例（右上角第二行·右对齐；原底部图例已按用户要求移除，保持全看板下方无图例）
    _items = list(series_meta.items())

    def _w(lab):
        return 15 + len(lab) * 11 + 14

    _total = sum(_w(lab) for _, (lab, _c) in _items)
    lx = (ml + pw) - _total
    ly = 44
    for cl, (lab, color) in _items:
        svg.append(f'<rect x="{lx}" y="{ly-9}" width="11" height="11" rx="2" fill="{color}"/>')
        svg.append(f'<text x="{lx+15}" y="{ly}" font-size="10.5" fill="#374151">{lab}</text>')
        lx += _w(lab)
    # 网格 + y 轴刻度
    for k in range(5):
        yv = vmin + (vmax - vmin) * k / 4
        yy = yp(yv)
        svg.append(f'<line x1="{ml}" y1="{yy:.1f}" x2="{ml+pw}" y2="{yy:.1f}" stroke="#eef1f5"/>')
        svg.append(f'<text x="{ml-8}" y="{yy+4:.1f}" font-size="11" fill="#9ca3af" text-anchor="end">{yv:.0f}</text>')
    svg.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{plot_bottom}" stroke="#d1d5db"/>')
    svg.append(f'<line x1="{ml}" y1="{plot_bottom}" x2="{ml+pw}" y2="{plot_bottom}" stroke="#d1d5db"/>')
    # 每条线：先画 2025 虚线（底层），再画 2026 实线（上层）
    for cl, (lab, color) in series_meta.items():
        if data2:
            s2 = data2[cl]
            seg = []
            for i, (m, v) in enumerate(s2):
                if v is None:
                    if seg:
                        svg.append(f'<path d="M{" L".join(seg)}" fill="none" stroke="{color}" stroke-width="1.8" stroke-dasharray="5 3" opacity="0.7"/>')
                        seg = []
                    continue
                seg.append(f"{xs[i]:.1f} {yp(v):.1f}")
            if seg:
                svg.append(f'<path d="M{" L".join(seg)}" fill="none" stroke="{color}" stroke-width="1.8" stroke-dasharray="5 3" opacity="0.7"/>')
            for i, (m, v) in enumerate(s2):
                if v is None:
                    continue
                svg.append(f'<circle cx="{xs[i]:.1f}" cy="{yp(v):.1f}" r="2.4" fill="{color}" opacity="0.7" stroke="#fff" stroke-width="0.8"/>')
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
            svg.append(f'<circle cx="{xs[i]:.1f}" cy="{yp(v):.1f}" r="2.8" fill="{color}" stroke="#fff" stroke-width="1"/>')
    # x 轴月份
    for i in range(n):
        svg.append(f'<text x="{xs[i]:.1f}" y="{plot_bottom+18:.1f}" font-size="11" fill="#6b7280" text-anchor="middle">{MONTH_LABELS[i]}</text>')
    # 底部产品图例已移除（改置于右上角第二行）
    svg.append('</svg>')
    with open(fname, "w", encoding="utf-8") as f:
        f.write("".join(svg))
    print(f"✅ 生成月度多线趋势图（双线）：{fname}（{len(series_meta)} 产品 × {n} 月 × 2 年）")


# ---------- sparkline（取 2026 当月序列，断点跳过） ----------
def build_spark(vals, fname, color="#c53030"):
    W, H = 62, 28
    pts_v = [v for v in vals if v is not None]
    n = len(pts_v)
    if n < 2:
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

    # 4 个单线指标（2026 当年 + 2025 同期）
    prod = load_monthly_col(ws1, "B", 2026)    # 商品煤产量
    sales = load_monthly_col(ws1, "C", 2026)   # 商品煤销量
    selfs = load_monthly_col(ws1, "D", 2026)   # 自产商品煤销量
    equip = load_monthly_col(ws2, "G", 2026)   # 煤矿装备产值
    prod25 = load_monthly_col(ws1, "B", 2025)
    sales25 = load_monthly_col(ws1, "C", 2025)
    selfs25 = load_monthly_col(ws1, "D", 2025)
    equip25 = load_monthly_col(ws2, "G", 2025)

    build_trend_m(prod, "svg/trend_m_prod.svg", "商品煤产量（2026 vs 2025同期·万吨）", "#c53030", "万吨", prod25)
    build_trend_m(sales, "svg/trend_m_sales.svg", "商品煤销量（2026 vs 2025同期·万吨）", "#15616d", "万吨", sales25)
    build_trend_m(selfs, "svg/trend_m_selfsales.svg", "自产商品煤销量（2026 vs 2025同期·万吨）", "#2e9e6b", "万吨", selfs25)
    build_trend_m(equip, "svg/trend_m_equip.svg", "煤矿装备产值（2026 vs 2025同期·亿元）", "#d98a14", "亿元", equip25)

    build_spark([v for _, v in prod], "svg/spark_m_prod.svg", "#c53030")
    build_spark([v for _, v in sales], "svg/spark_m_sales.svg", "#15616d")
    build_spark([v for _, v in selfs], "svg/spark_m_selfsales.svg", "#2e9e6b")
    build_spark([v for _, v in equip], "svg/spark_m_equip.svg", "#d98a14")

    # 煤化工业务（B-F 五线合并，2026 + 2025 同期）
    labels, chem = load_monthly_multi(ws2, ["B", "C", "D", "E", "F"], 2026)
    labels25, chem25 = load_monthly_multi(ws2, ["B", "C", "D", "E", "F"], 2025)
    chem_meta = {
        "B": ("聚乙烯", "#c53030"),
        "C": ("聚丙烯", "#15616d"),
        "D": ("甲醇", "#2e9e6b"),
        "E": ("硝铵", "#d98a14"),
        "F": ("尿素", "#7a5cc8"),
    }
    build_trend_m_multi(labels, chem, "svg/trend_m_chem.svg", "煤化工主要产品产量（2026 vs 2025同期·万吨）", chem_meta, "万吨", chem25)
    build_spark([v for _, v in chem["D"]], "svg/spark_m_chem.svg", "#2e9e6b")  # 以甲醇为主序列

    print("✅ 完成（未写回 xlsx）")
