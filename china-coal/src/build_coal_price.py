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
import re
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

# 项目根（本脚本位于 <项目根>/src/）：所有输入/输出路径以项目根为基准
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_XLSX = os.path.join(HERE, "数据源", "中煤能源_价格和成本.xlsx")
OUT_SVG = os.path.join(HERE, "svg/trend_qhd5500_weekly.svg")
OUT_SPARK = os.path.join(HERE, "svg/spark_qhd5500.svg")


def _fmt_date(d):
    """把日期单元格统一成 'YYYY-MM-DD' 字符串；同时支持 str 与 datetime。"""
    if isinstance(d, datetime.datetime):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        return d[:10]
    return None


def load_series(path):
    """读取 xlsx，返回 (dates, vals)。
    - 跳过表头行与底部汇总行（这些行价格列为 None 或非数值）；
    - 价格列缺失/非数值 → 跳过；
    - 价格 = 0 的行（文件中 1 月无 CCTD 披露的周）保留为 0 占位，绘图时跳过，
      以保证 x 轴按真实周序连续。
    - 日期列可为 str('YYYY-MM-DD') 或 datetime（周结束日），两种都接受。
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
        ds = _fmt_date(d)
        if ds is None:
            continue
        dates.append(ds)
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
    # 顶部标题：双击放大时仍可见，弹窗内与 modal 标题视觉重复但可接受
    svg.append(f'<text x="{ml}" y="22" fill="#1f2733" font-size="14" font-weight="700">{title}</text>')
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
    # x 标签：仅标注「每月第一个日期」（数据中出现的最早日），格式 YYYY/MM/DD
    last_month = None
    for i in range(n):
        cur_month = dates[i][:7]  # 'YYYY-MM'
        if cur_month != last_month:
            lab = dates[i].replace("-", "/")  # 'YYYY/MM/DD'
            svg.append(f'<text x="{xs_all[i]:.1f}" y="{mt+ph+18:.1f}" font-size="10.5" fill="#6b7280" text-anchor="middle">{lab}</text>')
            last_month = cur_month
    # 底部图例（色块 + 指标名）已按用户要求移除，保持全看板下方无图例
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


def band_of(avg):
    """按当年截止目前均价分三档着色：>750 高景气(红) / 550–750 中性(琥珀) / <550 承压(绿)。"""
    if avg > 750:
        return "#c53030", "高景气(>750)"
    if avg >= 550:
        return "#d97706", "中性(550–750)"
    return "#047857", "承压(<550)"


def patch_dashboard(latest, ytd_avg, color, band_label):
    """把秦皇岛5500现货价的『名称着色 + 最新周度值 + 年内均价』写回看板 HTML。
    幂等：每次都按稳定 data-page-node-id 重建对应 span，重复运行不产生重复注释。
    """
    HTML = "china-coal-dashboard.html"
    html = open(HTML, encoding="utf-8").read()
    k_node = 'data-page-node-id="KQMTlv6vlERIB7IqHlCpSQ"'   # 指标名称 span
    v_node = 'data-page-node-id="vcBbOmHQ33kvGp9jGkTBov"'  # 数值 span
    # 1) 指标名称按分档着色
    html = re.sub(
        r'<span class="k" ' + re.escape(k_node) + r'>秦皇岛5500现货价</span>',
        f'<span class="k" {k_node} style="color:{color}">秦皇岛5500现货价</span>',
        html, count=1)
    # 2) 数值更新为最新周度价
    html = re.sub(
        r'<span class="v" ' + re.escape(v_node) + r'>[^<]*</span>',
        f'<span class="v" {v_node}>{latest:.0f} 元/吨</span>',
        html, count=1)
    # 3) 年内均注释（先删旧，再插到数值后）
    html = re.sub(r'<span class="ytdavg" data-ytd="1"[^>]*>[^<]*</span>', "", html)
    ann = (f'<span class="ytdavg" data-ytd="1" '
           f'style="color:#6b7280;font-size:11px;margin-left:6px;">年内均 {ytd_avg:.0f}</span>')
    html = re.sub(
        r'(<span class="v" ' + re.escape(v_node) + r'>[^<]*</span>)',
        lambda m: m.group(1) + ann, html, count=1)
    open(HTML, "w", encoding="utf-8").write(html)
    print(f"✅ 看板已更新：秦皇岛5500现货价 名称着色[{band_label}]、最新 {latest:.0f}、年内均 {ytd_avg:.0f}")


def main():
    dates, vals = load_series(OUT_XLSX)
    print(f"📊 从 xlsx 读取 {len(dates)} 个周度观测点（价格=0 为无数据占位，不绘制）")
    build_trend_svg(dates, vals, OUT_SVG,
                    title="秦皇岛港5500动力煤现货价（2026·周度·仅CCTD口径）")
    build_spark(vals, OUT_SPARK)
    # 当年截止目前均价 + 最新周度 → 名称分档着色（替代原「情景假设框架」）
    ytd = [(d, v) for d, v in zip(dates, vals)
           if d.startswith("2026") and isinstance(v, (int, float)) and v != 0]
    if ytd:
        latest_d, latest_v = ytd[-1]
        ytd_avg = sum(v for _, v in ytd) / len(ytd)
        color, band_label = band_of(ytd_avg)
        patch_dashboard(latest_v, ytd_avg, color, band_label)
        print(f"📈 2026 年内 {len(ytd)} 个有效周：最新 {latest_v:.0f}（{latest_d}），均价 {ytd_avg:.1f} → 分档 {band_label}")
    else:
        print("⚠️ 无 2026 年有效价格数据，跳过名称着色")


if __name__ == "__main__":
    main()
