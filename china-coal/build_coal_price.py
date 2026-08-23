# -*- coding: utf-8 -*-
"""
构建「秦皇岛港5500大卡动力煤现货价」2026年以来周度序列的趋势图与火花线。

【数据口径 · 重要变更】
- 价格数据由人工维护在  数据源/中煤能源_价格和成本.xlsx（原「秦皇岛5500现货价_周度.xlsx」改名）的「秦皇岛5500周度」sheet  （仅 CCTD 口径）。
- 本脚本【只读】该 xlsx，【不再联网抓取】 CCTD，也【不再改写】该 xlsx 文件。
- 脚本仅据此生成两张 SVG 图表（供 china-coal-dashboard.html 引用）：
      trend_qhd5500_weekly.svg   (模态框趋势图)
      spark_qhd5500.svg          (卡片内 mini sparkline)
- 若需更新价格，请直接编辑 xlsx，再运行本脚本刷新图表即可。
"""
import os
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_XLSX = os.path.join(HERE, "数据源", "中煤能源_价格和成本.xlsx")
OUT_SVG = os.path.join(HERE, "trend_qhd5500_weekly.svg")
OUT_SPARK = os.path.join(HERE, "spark_qhd5500.svg")


def load_series(path):
    """读取 xlsx，返回 (dates, vals)。
    - 跳过表头行与底部汇总行（这些行价格列为 None 或非数值）；
    - 价格列缺失/非数值 → 跳过；
    - 价格 = 0 的行（文件中 1 月无 CCTD 披露的周）保留为 0 占位，绘图时跳过，
      以保证 x 轴按真实周序连续。
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["秦皇岛5500周度"]
    # 定位表头（周结束日）
    hdr_row = None
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=1).value == "周结束日":
            hdr_row = r
            break
    if hdr_row is None:
        raise RuntimeError("未在 xlsx 中找到表头行（周结束日）")

    dates, vals = [], []
    for r in range(hdr_row + 1, ws.max_row + 1):
        d = ws.cell(row=r, column=1).value
        v = ws.cell(row=r, column=3).value
        # 汇总行 / 空行：价格列为 None 或非数值 → 跳过
        if v is None:
            continue
        try:
            vf = float(v)
        except (TypeError, ValueError):
            continue
        if not isinstance(d, str):
            continue
        dates.append(str(d)[:10])
        vals.append(vf)
    return dates, vals


def build_trend_svg(dates, vals, fname, W=1000, H=420, title=None):
    ml, mr, mt, mb = 60, 24, 42, 56
    pw, ph = W - ml - mr, H - mt - mb
    n = len(vals)
    # 仅用有效点绘制（跳过无数据周的 0，1月段留空）
    valid_idx = [i for i in range(n) if isinstance(vals[i], (int, float)) and vals[i] != 0]
    if not valid_idx:
        raise RuntimeError("无有效价格数据，无法绘制趋势图")
    xs_all = [ml + pw * i / (n - 1) for i in range(n)]
    vmin = min(vals[i] for i in valid_idx)
    vmax = max(vals[i] for i in valid_idx)
    pad = (vmax - vmin) * 0.12 or 10
    vmin, vmax = vmin - pad, vmax + pad

    def yp(v):
        return mt + ph - (v - vmin) / (vmax - vmin) * ph

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">']
    svg.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    ttl = title or "秦皇岛港5500动力煤现货价（2026·周度·元/吨）"
    svg.append(f'<text x="{ml}" y="26" font-size="16" font-weight="700" fill="#1e3a5f">{ttl}</text>')
    # y 网格
    for k in range(5):
        yv = vmin + (vmax - vmin) * k / 4
        yy = yp(yv)
        svg.append(f'<line x1="{ml}" y1="{yy:.1f}" x2="{ml+pw}" y2="{yy:.1f}" stroke="#eef1f5"/>')
        svg.append(f'<text x="{ml-8}" y="{yy+4:.1f}" font-size="11" fill="#9ca3af" text-anchor="end">{yv:.0f}</text>')
    # 轴
    svg.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#d1d5db"/>')
    svg.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#d1d5db"/>')
    # 折线（仅有效点，按真实周序 x 坐标定位）
    pts = [f"{xs_all[i]:.1f} {yp(vals[i]):.1f}" for i in valid_idx]
    svg.append(f'<path d="M{" L".join(pts)}" fill="none" stroke="#c53030" stroke-width="2.5"/>')
    for i in valid_idx:
        svg.append(f'<circle cx="{xs_all[i]:.1f}" cy="{yp(vals[i]):.1f}" r="2.6" fill="#c53030" stroke="#fff" stroke-width="1"/>')
    # x 标签（每月标一次）
    step = max(1, n // 12)
    for i in range(n):
        if i % step == 0 or i == n - 1:
            lab = dates[i][5:7] + "/" + dates[i][8:10]
            svg.append(f'<text x="{xs_all[i]:.1f}" y="{mt+ph+18:.1f}" font-size="10.5" fill="#6b7280" text-anchor="middle">{lab}</text>')
    # 图例
    svg.append(f'<rect x="{ml+4}" y="{H-20}" width="12" height="12" rx="2" fill="#c53030"/>')
    svg.append(f'<text x="{ml+21}" y="{H-10}" font-size="11.5" fill="#374151">秦皇岛5500现货价</text>')
    svg.append(f'<text x="{ml+pw}" y="{H-10}" font-size="10.5" fill="#9ca3af" text-anchor="end">单位:元/吨（仅CCTD口径，缺测段不画）</text>')
    svg.append('</svg>')
    with open(fname, "w", encoding="utf-8") as f:
        f.write("".join(svg))
    print(f"✅ 生成趋势图：{fname}")


def build_spark(vals, fname, color="#c53030", W=62, H=28):
    # 仅用有效点（跳过无数据周的 0），否则 min/max 取到 0 会让火花线比例失真
    vseq = [v for v in vals if isinstance(v, (int, float)) and v != 0]
    if not vseq:
        raise RuntimeError("无有效价格数据，无法绘制火花线")
    n = len(vseq)
    xs = [2 + (W - 4) * i / (n - 1) for i in range(n)]
    vmin, vmax = min(vseq), max(vseq)
    pad = (vmax - vmin) * 0.15 or 1

    def yp(v):
        return 4 + (H - 8) - (v - (vmin - pad)) / ((vmax + pad) - (vmin - pad)) * (H - 8)

    pts = [f"{xs[i]:.1f} {yp(vseq[i]):.1f}" for i in range(n)]
    svg = [f'<svg class="spark" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'<path d="M{" L".join(pts)}" fill="none" stroke="{color}" stroke-width="2"/>')
    svg.append('</svg>')
    with open(fname, "w", encoding="utf-8") as f:
        f.write("".join(svg))
    print(f"✅ 生成 sparkline：{fname}")


def main():
    dates, vals = load_series(OUT_XLSX)
    print(f"📊 从 xlsx 读取 {len(dates)} 个周度观测点（价格=0 为无数据占位，不绘制）")
    build_trend_svg(dates, vals, OUT_SVG,
                    title="秦皇岛港5500动力煤现货价（2026·周度·仅CCTD口径）")
    build_spark(vals, OUT_SPARK)


if __name__ == "__main__":
    main()
