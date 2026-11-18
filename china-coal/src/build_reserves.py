# -*- coding: utf-8 -*-
"""
构建「煤矿资源与储备（2025年报）」板块：只读 数据源/中煤能源_资源储备.xlsx，
生成 ①区域资源对比 SVG（横向分组条形图，写 svg/ 供 reinject 注入 __CHARTS__）
②板块 HTML（KPI 徽章 + 3 张明细表 + 页脚），幂等 patch 回 china-coal-dashboard.html。

三个 sheet：
  按区域资源储备分布   区域/资源量/可采储量/证实储量/主要煤种（含合计行）
  重点煤矿资源储备     煤矿/所属区域/资源量/可采储量或设计可采储量/产能及权益/当前情况
  其他主要煤矿和矿区   区域/主要煤矿或矿区/主要煤种/资源情况

用法（任意目录）：python src/build_reserves.py
依赖：openpyxl（只读）。本脚本不改 xlsx。
"""
import os
import re
import html as _html
import openpyxl

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(HERE)
XLSX = "数据源/中煤能源_资源储备.xlsx"
SVG_OUT = "svg/reserve_region.svg"
HTML = "china-coal-dashboard.html"

C_RES, C_REC, C_PRO = "#c8102e", "#d98a14", "#2e9e6b"  # 资源量红 / 可采琥珀 / 证实绿


def _num(v):
    """数字 → 保留两位并带千分位；非数字原样转义。"""
    if isinstance(v, (int, float)):
        return f"{v:,.2f}"
    return _html.escape(str(v)) if v is not None else "—"


def _cell(v):
    return _html.escape(str(v)) if v is not None else "—"


def _mine_val(v):
    """重点煤矿储量格：数字保留两位并右对齐用；文本（如'未披露'）灰色显示。"""
    if isinstance(v, (int, float)):
        return f"{v:,.2f}"
    t = _html.escape(str(v)) if v is not None else "—"
    return f'<span style="color:var(--todo);font-size:11px">{t}</span>'


def _equity(v):
    """权益：小数→百分比，保留最多 4 位小数去尾零（1→100%、0.51→51%、0.50224→50.224%）。"""
    if isinstance(v, (int, float)):
        pct = v * 100
        return f"{pct:.4f}".rstrip("0").rstrip(".") + "%"
    return _cell(v)


def _capacity(v):
    """产能/权益产能：整数带千分位，小数保留两位（如 263.5、120.54）。"""
    if isinstance(v, (int, float)):
        return f"{v:,.2f}" if v != int(v) else f"{int(v):,}"
    return _cell(v)


def load_data():
    wb = openpyxl.load_workbook(XLSX, data_only=True)

    # 总览 sheet：KPI 直接取前 5 个指标（表头在第 4 行，数据从第 5 行起）
    ws = wb["总览"]
    overview = []
    for r in range(5, ws.max_row + 1):
        name = ws.cell(row=r, column=1).value
        val = ws.cell(row=r, column=2).value
        unit = ws.cell(row=r, column=3).value
        if name is None or val is None:
            continue
        overview.append((str(name), val, str(unit) if unit else ""))

    ws = wb["按区域资源储备分布"]
    region = []
    for r in range(2, ws.max_row + 1):
        row = [ws.cell(row=r, column=c).value for c in range(1, 6)]
        if row[0] is None:
            continue
        region.append(row)

    ws = wb["重点煤矿资源储备"]
    mines = []
    for r in range(2, ws.max_row + 1):
        row = [ws.cell(row=r, column=c).value for c in range(1, 8)]
        if row[0] is None:
            continue
        mines.append(row)

    ws = wb["其他主要煤矿和矿区"]
    # 该 sheet 前几行是标题/说明/空行，真正表头在第 4 行（首格='序号'）
    hdr = None
    for r in range(1, ws.max_row + 1):
        if str(ws.cell(row=r, column=1).value).strip() == "序号":
            hdr = r
            break
    if hdr is None:
        raise RuntimeError("未在『其他主要煤矿和矿区』中找到表头行（首格=序号）")
    others = []
    for r in range(hdr + 1, ws.max_row + 1):
        row = [ws.cell(row=r, column=c).value for c in range(1, 13)]
        name = row[1]
        first = str(row[0]).strip() if row[0] is not None else ""
        is_total = first.startswith("合计")  # 合计行：矿井名为空、首格写'合计…'
        if name is None and not is_total:
            continue
        others.append(row)
    return overview, region, mines, others


def build_region_svg(region):
    """横向分组条形图：每区域 3 根条（资源量/可采储量/证实储量）。末行为合计，不入图。"""
    items = [r for r in region if str(r[0]).strip() != "合计"]
    W, H = 1000, 150 + len(items) * 50
    ml, mr, mt, mb = 96, 56, 48, 40
    pw, ph = W - ml - mr, H - mt - mb
    vmax = max(float(r[1]) for r in items)
    vmax = (int(vmax / 20) + 1) * 20  # 上限取 20 的整数倍
    grp = ph / len(items)
    bar_h = 11

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'font-family="-apple-system,Segoe UI,PingFang SC,sans-serif">',
         f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
         f'<text x="{ml}" y="22" fill="#1f2733" font-size="14" font-weight="700">'
         f'各区域煤矿资源储量对比（单位：亿吨）</text>']
    # 图例
    lx = ml + pw
    for lab, col in [("证实储量", C_PRO), ("可采储量", C_REC), ("资源量", C_RES)]:
        s.append(f'<text x="{lx}" y="24" font-size="11" fill="#64748b" text-anchor="end">{lab}</text>')
        s.append(f'<rect x="{lx-52}" y="15" width="10" height="10" rx="2" fill="{col}"/>')
        lx -= 78
    # x 轴网格（0 / vmax/4 ... vmax）
    for k in range(5):
        gx = ml + pw * k / 4
        gv = vmax * k / 4
        s.append(f'<line x1="{gx:.1f}" y1="{mt}" x2="{gx:.1f}" y2="{mt+ph}" stroke="#eef1f5"/>')
        s.append(f'<text x="{gx:.1f}" y="{mt+ph+18}" font-size="11" fill="#9ca3af" text-anchor="middle">{gv:.0f}</text>')
    s.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#d1d5db"/>')

    for i, r in enumerate(items):
        name = str(r[0])
        cy = mt + grp * i + grp / 2
        s.append(f'<text x="{ml-10}" y="{cy+4:.1f}" font-size="12" fill="#374151" text-anchor="end">{_html.escape(name)}</text>')
        # 三根条：资源量(上) / 可采(中) / 证实(下)
        for j, (idx, col) in enumerate([(1, C_RES), (2, C_REC), (3, C_PRO)]):
            v = float(r[idx]) if isinstance(r[idx], (int, float)) else 0
            y = cy - bar_h * 1.5 + j * bar_h + (j - 1) * 1
            w = pw * v / vmax
            s.append(f'<rect x="{ml}" y="{y:.1f}" width="{w:.1f}" height="{bar_h-1}" rx="2" fill="{col}"/>')
            s.append(f'<text x="{ml+w+5:.1f}" y="{y+bar_h-3:.1f}" font-size="10" fill="#64748b">{_num(v)}</text>')
    s.append("</svg>")
    os.makedirs("svg", exist_ok=True)
    with open(SVG_OUT, "w", encoding="utf-8") as f:
        f.write("".join(s))
    print(f"✅ 区域资源对比 SVG：{SVG_OUT}（{len(items)} 区域）")


CSS = """/* RES_STYLE:BEGIN */
.res-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:6px 0 16px}
.res-kpi{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.res-kpi .k{font-size:12px;color:var(--dim)}
.res-kpi .v{font-size:23px;font-weight:700;color:var(--acc);font-variant-numeric:tabular-nums;margin-top:3px;line-height:1.2}
.res-kpi .u{font-size:12px;color:var(--dim);font-weight:400;margin-left:3px}
.res-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(16,24,40,.04)}
.res-card h4{font-size:14px;font-weight:700;margin-bottom:10px;color:var(--navy);display:flex;align-items:center;gap:8px}
.res-card h4::before{content:"";width:4px;height:15px;background:var(--acc2);border-radius:2px}
.res-chart svg{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:8px;background:#fff;margin-bottom:12px}
.res-tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.res-tbl th,.res-tbl td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;line-height:1.5}
.res-tbl th{background:var(--soft);color:var(--dim);font-weight:600;font-size:11.5px;white-space:nowrap}
.res-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.res-tbl tr.total td{font-weight:700;color:var(--acc);background:#fff5f6;border-top:2px solid var(--acc)}
.res-tbl tbody tr:hover{background:#fafbfc}
.res-badge{display:inline-block;padding:1px 8px;border-radius:9px;font-size:11px;font-weight:600;white-space:nowrap}
.res-badge.prod{background:#e7f6ee;color:#047857}
.res-badge.build{background:#fff4e5;color:#b45309}
.res-badge.na{background:#f1f3f5;color:#9aa6b2}
.res-foot{font-size:11px;color:var(--dim);margin-top:2px;line-height:1.7}
/* RES_STYLE:END */"""


def _badge(txt):
    t = (txt or "").strip()
    cls = "prod" if t == "在产" else ("build" if "在建" in t else "na")
    return f'<span class="res-badge {cls}">{_cell(t) if t else "—"}</span>'


def build_section(overview, region, mines, others):
    # KPI 直接来自总览 sheet 前 5 个指标（数值/单位均取总览，保留其对整数千分位）
    kpi_labels = {
        "2025年末煤炭资源量": "资源量合计",
        "2025年末可采储量": "可采储量合计",
        "2025年末证实储量": "证实储量合计",
        "重点并表在产矿核定产能": "核定产能",
        "重点并表在产矿权益产能": "权益产能",
    }
    kpi_html = []
    for name, val, unit in overview[:5]:
        label = kpi_labels.get(name, name)
        kpi_html.append(f'<div class="res-kpi"><div class="k">{_cell(label)}</div>'
                        f'<div class="v">{_capacity(val)}<span class="u">{_cell(unit)}</span></div></div>')

    # 区域表
    rh = ['<table class="res-tbl"><thead><tr><th>区域</th><th style="text-align:right">资源量（亿吨）</th>'
          '<th style="text-align:right">可采储量（亿吨）</th><th style="text-align:right">证实储量（亿吨）</th>'
          '<th>主要煤种</th></tr></thead><tbody>']
    for r in region:
        is_total = str(r[0]).strip() == "合计"
        rh.append('<tr class="total">' if is_total else "<tr>")
        rh.append(f'<td>{_cell(r[0])}</td><td class="num">{_num(r[1])}</td>'
                  f'<td class="num">{_num(r[2])}</td><td class="num">{_num(r[3])}</td>'
                  f'<td>{_cell(r[4])}</td></tr>')
    rh.append("</tbody></table>")

    # 重点煤矿表（7 列：产能与权益已拆开；权益小数→百分比）
    mh = ['<table class="res-tbl"><thead><tr><th>煤矿</th><th>所属区域</th>'
          '<th style="text-align:right">资源量（亿吨）</th><th style="text-align:right">可采/设计可采（亿吨）</th>'
          '<th>产能</th><th style="text-align:right">权益</th><th>当前情况</th></tr></thead><tbody>']
    for r in mines:
        mh.append(f'<tr><td><b>{_cell(r[0])}</b></td><td>{_cell(r[1])}</td>'
                  f'<td class="num">{_mine_val(r[2])}</td><td class="num">{_mine_val(r[3])}</td>'
                  f'<td>{_cell(r[4])}</td><td class="num">{_equity(r[5])}</td>'
                  f'<td>{_badge(r[6])}</td></tr>')
    mh.append("</tbody></table>")

    # 其他主要煤矿和矿区表（12 列中按用户要求排除：序号/资产口径/说明·数据质量/主要来源URL）
    # 保留：矿井(1) 省区(2) 煤种(3) 运营主体(4) 状态(6) 产能(7) 权益比例(8) 权益产能(9)
    oh = ['<table class="res-tbl"><thead><tr><th>矿井/项目</th><th>省区</th><th>煤种/用途</th>'
          '<th>运营主体</th><th>状态</th>'
          '<th style="text-align:right">核定/设计产能<br>(万吨/年)</th>'
          '<th style="text-align:right">中煤权益</th>'
          '<th style="text-align:right">权益产能<br>(万吨/年)</th></tr></thead><tbody>']
    for r in others:
        first = str(r[0]).strip() if r[0] is not None else ""
        is_total = first.startswith("合计")
        if is_total:
            oh.append(f'<tr class="total"><td colspan="5">{_cell(r[0])}</td>'
                      f'<td class="num">{_capacity(r[7])}</td><td class="num">—</td>'
                      f'<td class="num">{_capacity(r[9])}</td></tr>')
            continue
        # 状态：含'在建'→琥珀 badge；否则在产→绿 badge
        st = str(r[6]) if r[6] is not None else ""
        st_badge = _badge("在建" if "在建" in st else ("在产" if "在产" in st else st))
        oh.append(f'<tr><td><b>{_cell(r[1])}</b></td><td>{_cell(r[2])}</td>'
                  f'<td>{_cell(r[3])}</td><td>{_cell(r[4])}</td><td>{st_badge}</td>'
                  f'<td class="num">{_capacity(r[7])}</td>'
                  f'<td class="num">{_equity(r[8])}</td>'
                  f'<td class="num">{_capacity(r[9])}</td></tr>')
    oh.append("</tbody></table>")

    return f"""<!-- RES_SECTION:BEGIN -->
<h2 class="sec-title">煤矿资源与储备（2025年报口径）</h2>

<div class="res-kpis">
  {''.join(kpi_html)}
</div>

<div class="res-card">
  <h4>按区域资源储备分布</h4>
  <div class="res-chart"><div data-img="reserve_region"></div></div>
  {''.join(rh)}
</div>

<div class="res-card">
  <h4>重点煤矿资源储备（单矿口径）</h4>
  {''.join(mh)}
  <div class="res-foot">注：权益为对公司持股比例（苇子沟 49.94% 为穿透权益）；储量「未披露」表示未见可核实的单矿储量公开数据，仅列产能与权益；苇子沟为一期在建项目；大海则、王家岭为在产主力矿。</div>
</div>

<div class="res-card">
  <h4>重点并表煤矿及在建项目资产主表（24 处矿井/项目）</h4>
  {''.join(oh)}
  <div class="res-foot">注：产能单位万吨/年，权益产能＝核定/设计产能×中煤权益比例；合计为 22 处在产并表矿（不含苇子沟、里必两处在建项目），逐矿求和可能因比例取整与研究报告合计 14,388 存在小幅差异。状态按最新披露：苇子沟首采面预计 2027 年底、里必预计 2028 年底。逐矿实际产量与最新剩余可采储量多未单独披露，项目设计可采储量≠当前剩余储量。表中省略序号、资产口径、数据质量说明及来源 URL，完整出处见「中煤能源_资源储备.xlsx」。</div>
</div>

<div class="res-foot">数据来源：中煤能源 2025 年年度报告，整理自「中煤能源_资源储备.xlsx」；资源量／可采储量／证实储量为年报披露的合并口径（亿吨），按省份及重点矿区拆分。证实储量 ⊂ 可采储量 ⊂ 资源量，三者为包含关系而非并列可加总。里必单矿储量、部分参股项目单矿数据未单独披露，按年报原文注明。数据频率：年度（2025年报），后续随年报更新。</div>
<!-- RES_SECTION:END -->"""


def register_chart(svg_raw):
    """把区域 SVG 注册进 HTML 的 __CHARTS__（新增 key 或更新，幂等）。
    reinject_svgs.py 只更新已存在的 key，新图需在此先注册。"""
    h = open(HTML, encoding="utf-8").read()
    marker = "var __CHARTS__ = {"
    i = h.index(marker)
    j = h.index("};", i)   # __CHARTS__ 对象闭合处（SVG 内无花括号）
    head, tail = h[:j], h[j:]

    esc = svg_raw.replace("\\", "\\\\").replace('"', '\\"')
    pat = re.compile(r'\n  "reserve_region": "(?:[^"\\]|\\.)*"', re.S)
    if pat.search(head):
        head = pat.sub(lambda m: '\n  "reserve_region": "' + esc + '"', head, count=1)
        print("✅ __CHARTS__ 已更新 key 'reserve_region'")
    else:
        # 在对象末尾（最后一个条目后、}; 前）插入；无尾逗号则补一个
        stripped = head.rstrip()
        comma = "" if stripped.endswith(",") else ","
        head = stripped + comma + '\n  "reserve_region": "' + esc + '"\n'
        print("✅ __CHARTS__ 已新增 key 'reserve_region'")
    open(HTML, "w", encoding="utf-8").write(head + tail)


def patch_html(section):
    h = open(HTML, encoding="utf-8").read()
    # 1) 注入 CSS（幂等）
    css_block = re.compile(r"/\* RES_STYLE:BEGIN \*/.*?/\* RES_STYLE:END \*/", re.S)
    if css_block.search(h):
        h = css_block.sub(CSS, h, count=1)
    else:
        h = h.replace("</style>", CSS + "\n</style>", 1)

    # 2) 注入 section（幂等）：插在趋势专区收尾后、趋势图模态框注释前
    sec_block = re.compile(r"<!-- RES_SECTION:BEGIN -->.*?<!-- RES_SECTION:END -->", re.S)
    if sec_block.search(h):
        h = sec_block.sub(section, h, count=1)
    else:
        anchor = "<!-- 趋势图模态框 -->"
        if anchor in h:
            h = h.replace(anchor, section + "\n\n" + anchor, 1)
        else:
            raise RuntimeError("未找到插入锚点：<!-- 趋势图模态框 -->")
    open(HTML, "w", encoding="utf-8").write(h)
    print(f"✅ 板块已写入 {HTML}（CSS + 3 表 + KPI + 页脚，幂等）")


def main():
    overview, region, mines, others = load_data()
    print(f"📊 读取 xlsx：总览 {len(overview)} 指标 / 区域 {len(region)} 行 / "
          f"重点煤矿 {len(mines)} 行 / 资产主表 {len(others)} 行")
    build_region_svg(region)
    patch_html(build_section(overview, region, mines, others))
    register_chart(open(SVG_OUT, encoding="utf-8").read().strip())


if __name__ == "__main__":
    main()
