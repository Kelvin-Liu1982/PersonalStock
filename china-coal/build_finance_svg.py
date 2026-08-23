# -*- coding: utf-8 -*-
"""
卡片4「财务表现」SVG 趋势图生成（只读数据源版）
-----------------------------------------------------------------
- 数据来源：`数据源/中煤能源_业务追踪数据.xlsx`
  - `财务指标(季度)` sheet（单季还原后的真实单季值，报告日 YYYYQn，2020Q1-2026Q1）
  - `财务指标(年度)` sheet（年报全年值，年份 2020-2025）
- 生成：
  - `trend_{key}_y.svg` 年度趋势图（来自 财务指标(年度)）
  - `trend_{key}_q.svg` 季度趋势图（来自 财务指标(季度)）
  - `spark_{key}.svg`    卡片内 mini sparkline（来自 财务指标(季度)）
  注：长期趋势专区财务表现原为两张组合图（trend_revenue_profit / trend_ratios），
  已于 2026-08-23 改为 10 张单独图（5 指标 × 年度_y + 季度_q），组合图不再生成。
- 视觉风格与 build_finance_card.py 的 build_svg_base / build_sparkline 完全一致。
- 本脚本**只读 xlsx，绝不写回 Excel**。
"""
import openpyxl
from openpyxl.utils import get_column_letter

EXCEL = "数据源/中煤能源_业务追踪数据.xlsx"
Q_SHEET = "财务指标(季度)"
Y_SHEET = "财务指标(年度)"

# 指标定义：key, 标题, 列名, 单位, 颜色
METRICS = [
    ("revenue", "营业收入",         "营业收入(亿元)",       "亿元", "#c53030"),
    ("profit",  "归母净利润",       "归母净利润(亿元)",     "亿元", "#1e3a5f"),
    ("cash",    "经营现金流净额",   "经营现金流净额(亿元)", "亿元", "#d97706"),
    ("debt",    "资产负债率",       "资产负债率(%)",        "%",   "#047857"),
    ("roe",     "ROE累计",          "ROE累计(%)",           "%",   "#b45309"),
    ("bps",     "每股净资产",       "每股净资产(元)",       "元",   "#2563eb"),
]

# ---------- 读取 sheet -> 列字典 ----------
def load_sheet(sheet_name):
    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    ws = wb[sheet_name]
    hdr = [c.value for c in ws[3]]
    rows = {}
    labels = []
    for r in range(4, ws.max_row + 1):
        key = ws.cell(row=r, column=1).value
        if key is None:
            continue
        row = {hdr[i]: ws.cell(row=r, column=i + 1).value for i in range(len(hdr))}
        rows[str(key)] = row
        labels.append(str(key))
    return hdr, rows, labels

q_hdr, q_rows, q_labels = load_sheet(Q_SHEET)   # 季度：YYYYQn
y_hdr, y_rows, y_labels = load_sheet(Y_SHEET)   # 年度：年份(2020-2025)

def col_vals(rows, labels, col):
    return [rows[l].get(col) for l in labels]

# ---------- 绘图函数（与 build_finance_card.py 视觉一致） ----------
def build_svg_base(series_list, title, yunit, fname, W=1000, H=420, xlabels=None, label_step=None):
    ml, mr, mt, mb = 58, 24, 42, 44
    pw, ph = W - ml - mr, H - mt - mb
    n = len(series_list[0][1]) if series_list else 1
    xs = [ml + (pw * i / (n - 1)) for i in range(n)]
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">'.format(W=W, H=H)]
    svg.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    svg.append(f'<text x="{ml}" y="26" font-size="16" font-weight="700" fill="#1e3a5f">{title}</text>')
    allv = [v for _, vals, _ in series_list for v in vals if v is not None]
    ymin, ymax = min(allv), max(allv)
    pad = (ymax - ymin) * 0.15 or 1
    ymin, ymax = ymin - pad, ymax + pad
    def ypos(v):
        return mt + ph - (v - ymin) / (ymax - ymin) * ph
    for k in range(5):
        yv = ymin + (ymax - ymin) * k / 4
        yy = ypos(yv)
        svg.append(f'<line x1="{ml}" y1="{yy:.1f}" x2="{ml+pw}" y2="{yy:.1f}" stroke="#eef1f5"/>')
        svg.append(f'<text x="{ml-8}" y="{yy+4:.1f}" font-size="11" fill="#9ca3af" text-anchor="end">{yv:.1f}</text>')
    svg.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#d1d5db"/>')
    svg.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#d1d5db"/>')
    step = label_step if label_step else max(1, n // 10)
    for i in range(n):
        if i % step == 0 or i == n - 1:
            _lab = (xlabels[i] if xlabels else str(i))
            svg.append(f'<text x="{xs[i]:.1f}" y="{mt+ph+18:.1f}" font-size="10.5" fill="#6b7280" text-anchor="middle">{_lab}</text>')
    for name, vals, color in series_list:
        pts = [(xs[i], ypos(vals[i])) for i in range(n) if vals[i] is not None]
        if len(pts) > 1:
            d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
            svg.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for x, y in pts:
            svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}" stroke="#fff" stroke-width="1"/>')
    lx = ml + 4
    for name, _, color in series_list:
        svg.append(f'<rect x="{lx}" y="{H-22}" width="12" height="12" rx="2" fill="{color}"/>')
        svg.append(f'<text x="{lx+17}" y="{H-12}" font-size="11.5" fill="#374151">{name}</text>')
        lx += 18 + len(name) * 12
    svg.append(f'<text x="{ml+pw}" y="{H-12}" font-size="10.5" fill="#9ca3af" text-anchor="end">单位:{yunit}</text>')
    svg.append('</svg>')
    s = "".join(svg)
    with open(fname, "w", encoding="utf-8") as f:
        f.write(s)
    print(f"✅ 生成图表：{fname}")
    return s

def build_sparkline(vals, color, fname):
    W, H = 62, 28
    n = len(vals)
    if n < 2:
        d = f"M2 {H/2:.1f} L{W-2} {H/2:.1f}"
    else:
        clean = [v for v in vals if v is not None]
        ymin, ymax = min(clean), max(clean)
        pad = (ymax - ymin) * 0.1 or 1
        ymin, ymax = ymin - pad, ymax + pad
        pts = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            x = 2 + (W - 4) * i / (n - 1)
            y = H - 2 - (v - ymin) / (ymax - ymin) * (H - 4)
            pts.append(f"{x:.1f} {y:.1f}")
        d = "M" + " L".join(pts)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" class="spark">'
           f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    with open(fname, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"✅ 生成 sparkline：{fname}")
    return svg

# 智能 x 标签：同年仅首季显年份
def quarter_label_smart(labels):
    out = []
    prev_year = None
    for lab in labels:
        y = lab[:4]
        if y != prev_year:
            out.append(lab)          # 如 2020Q1
            prev_year = y
        else:
            out.append(lab[4:])       # 如 Q2
    return out

# ---------- 1) 单指标 年度图 + 季度图 + sparkline ----------
for key, title, col, unit, color in METRICS:
    # 年度（财务指标(年度)，标签 2020-2025）
    y_vals = col_vals(y_rows, y_labels, col)
    build_svg_base([(title, y_vals, color)],
                   f"{title}趋势（年度）", unit,
                   f"trend_{key}_y.svg", W=1000, H=420,
                   xlabels=y_labels)
    # 季度（财务指标(季度)，标签 2020Q1-2026Q1）
    q_vals = col_vals(q_rows, q_labels, col)
    build_svg_base([(title, q_vals, color)],
                   f"{title}趋势（季度·单季）", unit,
                   f"trend_{key}_q.svg", W=1000, H=420,
                   xlabels=quarter_label_smart(q_labels), label_step=1)
    # sparkline（年度序列，与趋势按钮口径统一）
    build_sparkline(y_vals, color, f"spark_{key}.svg")

# =====================================================================
# 注：长期趋势专区财务表现原为两张组合图（trend_revenue_profit /
# trend_ratios），已于 2026-08-23 改为 10 张单独图（5 指标 × 年度_y
# + 季度_q），相关组合图生成逻辑已移除，仅保留下方说明。
# 已生成的 10 张图：
#   年度：trend_revenue_y / trend_profit_y / trend_debt_y / trend_roe_y / trend_bps_y
#   季度：trend_revenue_q / trend_profit_q / trend_debt_q / trend_roe_q / trend_bps_q
# =====================================================================


print("\n🎉 全部财务 SVG 已重新生成（年度图/trend 年度/sparkline 均来自 财务指标(年度)；季度图来自 财务指标(季度)）")
