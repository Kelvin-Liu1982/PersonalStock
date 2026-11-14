#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【已废弃 · 2026-11-13】本脚本与产物 volume-price.html 均不再使用，仅留档。
  废弃原因：①「运价与运力做量价对照」的设计已被否决（两者采样频率与噪声来源不同，
  见 build_weekly_pages.py 顶部设计原则）；②其数据源 `Drewry周报(WCI&停航)` sheet
  已拆分为 数据源/中远海控_Drewry周报数据.xlsx 的 WCI / IACI / CST 三张表，
  本脚本按单表列位读取，运行会直接报错。
  现行入口：drewry-weekly.html（build_weekly_pages.py）、alphaliner-weekly.html。

中远海控 · 运力 × 运价 双周报监测页生成器
=========================================
单一数据源：数据源/中远海控_行业供需与运价数据.xlsx
  · Alphaliner周报（全球&中远）  -> 量（运力 / 投放 / 订单 / 份额）
  · Drewry周报(WCI&停航)         -> 价（WCI / 分航线 / 停航）

产出：volume-price.html（单文件自包含，内联 SVG，零外部依赖）
不改动 cosco-dashboard.html / build_tracker.py / render_html.py / xlsx。
运行：python src/build_volume_price.py
"""
import os
import re
import math
import html
import datetime
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
XLSX = os.path.join(ROOT, "数据源", "中远海控_行业供需与运价数据.xlsx")
OUT = os.path.join(ROOT, "output", "volume-price.html")
os.makedirs(os.path.join(ROOT, "output"), exist_ok=True)

SHEET_AL = "Alphaliner周报（全球&中远）"
SHEET_DR = "Drewry周报(WCI&停航)"
PAIR_WINDOW = 3          # 量价配对容差（天），不插值

C_TEAL = "#15616d"
C_BLUE = "#185FA5"
C_GREEN = "#2e9e6b"
C_GRAY = "#7a8694"
C_RED = "#c8102e"
C_AMBER = "#d98a14"
C_PURPLE = "#6b5ca5"
C_INK = "#1f2733"
C_DIM = "#7a8694"
C_LINE = "#e3e8ee"

# ---------------------------------------------------------------- 数据读取
def _d(v):
    """单元格 -> ISO 日期字符串；非日期返回 None。"""
    if hasattr(v, "date"):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    s = str(v)[:10] if v is not None else ""
    return s if re.match(r"^20\d\d-\d\d-\d\d$", s) else None


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def read_alphaliner():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    w = wb[SHEET_AL]
    hdr = {str(w.cell(3, c).value).strip(): c
           for c in range(1, w.max_column + 1) if w.cell(3, c).value}
    need = ["发布时间", "全球运力(TEU)", "其中全集装箱船(艘)", "全集装箱船运力(TEU)",
            "跨大西洋周运力(TEU)", "跨太平洋周运力(TEU)", "远东-欧洲周运力(TEU)",
            "总运力(TEU)", "全球份额(%)", "手持订单(TEU)", "订单占现有运力(%)",
            "自有运力(TEU)", "租入运力(TEU)", "总艘数", "全球在运营船舶(艘)", "总载重吨(DWT)"]
    for k in need:
        if k not in hdr:
            raise KeyError("Alphaliner 表缺列: " + k)
    out = []
    for r in range(4, w.max_row + 1):
        d = _d(w.cell(r, hdr["发布时间"]).value)
        if not d:
            continue
        g = lambda k: _num(w.cell(r, hdr[k]).value)
        rec = dict(
            d=d,
            fleet=g("全球运力(TEU)"),
            fully=g("全集装箱船运力(TEU)"),
            ships=g("全球在运营船舶(艘)"),
            dwt=g("总载重吨(DWT)"),
            ta=g("跨大西洋周运力(TEU)"),
            tp=g("跨太平洋周运力(TEU)"),
            fe=g("远东-欧洲周运力(TEU)"),
            cosco=g("总运力(TEU)"),
            cosco_ships=g("总艘数"),
            share=g("全球份额(%)"),          # 原表为小数比例，后面统一 ×100
            order=g("手持订单(TEU)"),
            order_pct=g("订单占现有运力(%)"),  # 原表已是百分数
            owned=g("自有运力(TEU)"),
            chart=g("租入运力(TEU)"),
        )
        # 口径统一：份额一律由 公司运力÷全球运力 重算，避免原表小数/百分数混用
        rec["share"] = (rec["cosco"] / rec["fleet"] * 100
                        if rec["cosco"] and rec["fleet"] else None)
        out.append(rec)
    return out, hdr


def read_drewry():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    w = wb[SHEET_DR]
    hdr = {str(w.cell(1, c).value).strip().lstrip("\u3000"): c
           for c in range(1, w.max_column + 1) if w.cell(1, c).value}
    need = ["发布日期", "WCI综合(美元/FEU)", "上海-鹿特丹(美元/FEU)",
            "上海-洛杉矶(美元/FEU)", "上海-热那亚(美元/FEU)", "上海-纽约(美元/FEU)",
            "停航率(%)", "跨太平洋东行航线取消量(%)",
            "亚洲-北欧/地中海占取消量(%)", "跨大西洋占取消量(%)", "按计划营运率(%)"]
    for k in need:
        if k not in hdr:
            raise KeyError("Drewry 表缺列: " + k)
    out = []
    for r in range(2, w.max_row + 1):
        d = _d(w.cell(r, hdr["发布日期"]).value)
        if not d:
            continue
        g = lambda k: _num(w.cell(r, hdr[k]).value)
        # 停航率 / 取消量占比 / 营运率 原表均为小数比例 -> 统一为百分数
        out.append(dict(
            d=d,
            wci=g("WCI综合(美元/FEU)"),
            rtm=g("上海-鹿特丹(美元/FEU)"),
            lax=g("上海-洛杉矶(美元/FEU)"),
            goa=g("上海-热那亚(美元/FEU)"),
            nyc=g("上海-纽约(美元/FEU)"),
            blank=(g("停航率(%)") or 0) * 100,
            blank_tp=(g("跨太平洋东行航线取消量(%)") or 0) * 100,
            blank_ae=(g("亚洲-北欧/地中海占取消量(%)") or 0) * 100,
            blank_ta=(g("跨大西洋占取消量(%)") or 0) * 100,
            ontime=(g("按计划营运率(%)") or 0) * 100,
        ))
    return out


def _ord(s):
    return datetime.date.fromisoformat(s).toordinal()


def pair(al, dr, key_a, key_d, win=PAIR_WINDOW):
    """按最近发布日期把量数据点配到价数据点；超窗返回 None。"""
    xs, ys, used = [], [], []
    for a in al:
        best, gap = None, 10 ** 9
        for b in dr:
            g = abs(_ord(a["d"]) - _ord(b["d"]))
            if g < gap:
                best, gap = b, g
        ok = best is not None and gap <= win
        xs.append(a[key_a] if ok else None)
        ys.append(best[key_d] if ok else None)
        used.append((best["d"], gap) if ok else None)
    return xs, ys, used


def corr(xs, ys):
    p = [(x, y) for x, y in zip(xs, ys)
         if isinstance(x, (int, float)) and isinstance(y, (int, float))]
    if len(p) < 5:
        return float("nan"), len(p)
    X = [a for a, b in p]
    Y = [b for a, b in p]
    mx, my = sum(X) / len(X), sum(Y) / len(Y)
    num = sum((a - mx) * (b - my) for a, b in p)
    den = math.sqrt(sum((a - mx) ** 2 for a in X) * sum((b - my) ** 2 for b in Y))
    return (num / den if den else float("nan")), len(p)


def diff_corr(xs, ys):
    dx, dy = [], []
    for i in range(1, len(xs)):
        a, b, c, d = xs[i], ys[i], xs[i - 1], ys[i - 1]
        dx.append(a - c if None not in (a, c) else None)
        dy.append(b - d if None not in (b, d) else None)
    return corr(dx, dy)


# ---------------------------------------------------------------- SVG 绘制
def esc(s):
    return html.escape(str(s), quote=True)


def axis(lo, hi, n=4):
    vals = [v for v in (lo, hi) if isinstance(v, (int, float))]
    if not vals:
        return 0, 1, [0, 1]
    lo, hi = min(vals), max(vals)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.10
    lo, hi = lo - pad, hi + pad
    step = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(step)) if step > 0 else 1
    chosen = step
    for m in (1, 2, 2.5, 5, 10):
        if step / mag <= m:
            chosen = m * mag
            break
    lo = math.floor(lo / chosen) * chosen
    hi = math.ceil(hi / chosen) * chosen
    ticks, v = [], lo
    while v <= hi + chosen * 1e-6 and len(ticks) < 12:
        ticks.append(v)
        v += chosen
    return lo, hi, ticks


def fmt_tick(v, unit=""):
    a = abs(v)
    if a >= 10000:
        return f"{v / 10000:,.0f}万"
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:.1f}"
    return f"{v:.1f}" if not float(v).is_integer() else f"{v:.0f}"


def date_ticks(dates, x0, x1, t0, t1, limit=7, W=780):
    limit = 5 if W < 650 else limit
    """按月取刻度，并保证末点。返回 [(x, label)]。"""
    out, seen = [], set()
    for s in dates:
        m = s[:7]
        if m in seen:
            continue
        seen.add(m)
        x = x0 + (_ord(s) - t0) / max(1, t1 - t0) * (x1 - x0)
        out.append((x, s[5:7] + "月" if m[5:7] != "01" else s[:4] + "-01"))
    if len(out) > limit:
        k = math.ceil(len(out) / limit)
        out = out[::k]
    lastx = x0 + (_ord(dates[-1]) - t0) / max(1, t1 - t0) * (x1 - x0)
    if not out or abs(out[-1][0] - lastx) > 26:
        out.append((lastx, dates[-1][5:]))
    return out


def _path(dates, vals, t0, t1, x0, x1, y_of):
    """None 断线的折线 path。"""
    seg, segs, last = [], [], False
    for s, v in zip(dates, vals):
        if v is None or not isinstance(v, (int, float)):
            if len(seg) > 1:
                segs.append(seg)
            seg, last = [], False
            continue
        x = x0 + (_ord(s) - t0) / max(1, t1 - t0) * (x1 - x0)
        y = y_of(v)
        if not last and seg:
            seg = []
        seg.append((x, y))
        last = True
    if len(seg) > 1:
        segs.append(seg)
    return " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in g) for g in segs)


def _dots(dates, vals, t0, t1, x0, x1, y_of, color, cid, k, name, vfmt, show_all=False):
    out = []
    for i, (s, v) in enumerate(zip(dates, vals)):
        if v is None or not isinstance(v, (int, float)):
            continue
        x = x0 + (_ord(s) - t0) / max(1, t1 - t0) * (x1 - x0)
        y = y_of(v)
        show = show_all or i == len(dates) - 1
        r = 2.6 if show_all else 3.6
        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" '
            f'stroke="#fff" stroke-width="1" data-s="{cid}-{k}">'
            f'<title>{esc(s)} · {esc(name)} {esc(vfmt(v))}</title></circle>')
    return "".join(out)


def multi_svg(cid, title, unit, blocks, colors, vfmt=None, W=780, H=300,
              show_all_dots=False, note=""):
    """blocks: [(name, dates, vals)]，共用一个 y 轴。"""
    vfmt = vfmt or (lambda v: f"{v:,.0f}")
    X0, X1, Y0, Y1 = 62, W - 18, 58, H - 40
    all_dates = sorted({s for _, ds, _ in blocks for s in ds})
    allv = [v for _, _, vs in blocks for v in vs if v is not None]
    if not all_dates or not allv:
        return ""
    t0, t1 = _ord(all_dates[0]), _ord(all_dates[-1])
    lo, hi, ticks = axis(min(allv), max(allv))
    y_of = lambda v: Y1 - (v - lo) / max(1e-9, hi - lo) * (Y1 - Y0)
    p = [f'<svg id="{cid}" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'xmlns="http://www.w3.org/2000/svg" class="cv">',
         f'<title>{esc(title)}</title><desc>{esc(note or title)}</desc>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fff"/>',
         f'<text x="14" y="24" font-size="14" font-weight="500" fill="{C_INK}" '
         f'font-family="-apple-system,PingFang SC,sans-serif">{esc(title)}</text>',
         f'<text x="{W - 14}" y="24" text-anchor="end" font-size="12" fill="{C_DIM}" '
         f'font-family="-apple-system,PingFang SC,sans-serif">单位：{esc(unit)}</text>']
    for t in ticks:
        y = y_of(t)
        p.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" '
                 f'stroke="{C_LINE}" stroke-width="0.7"/>')
        p.append(f'<text x="{X0 - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="12" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(fmt_tick(t))}</text>')
    for x, lab in date_ticks(all_dates, X0, X1, t0, t1, W=W):
        p.append(f'<text x="{x:.1f}" y="{Y1 + 17}" text-anchor="middle" font-size="12" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(lab)}</text>')
    p.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#cfd7e0" stroke-width="0.8"/>')
    lx = X0 + 2
    for k, (name, ds, vs) in enumerate(blocks):
        col = colors[k % len(colors)]
        d = _path(ds, vs, t0, t1, X0, X1, y_of)
        last = next((v for v in reversed(vs) if v is not None), None)
        p.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2" '
                 f'stroke-linejoin="round" stroke-linecap="round" data-s="{cid}-{k}"/>')
        p.append(_dots(ds, vs, t0, t1, X0, X1, y_of, col, cid, k, name, vfmt, show_all_dots))
        lv = vfmt(last) if last is not None else "—"
        p.append(f'<g class="lg" data-chart="{cid}" data-k="{k}" style="cursor:pointer">'
                 f'<rect x="{lx}" y="34" width="10" height="10" rx="2" fill="{col}"/>'
                 f'<text x="{lx + 15}" y="43" font-size="12" fill="{C_INK}" '
                 f'font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(name)} {esc(lv)}</text></g>')
        lx += 22 + len(name) * 11 + len(lv) * 7
    if note:
        p.append(f'<text x="{X1}" y="{H - 8}" text-anchor="end" font-size="11.5" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(note)}</text>')
    p.append("</svg>")
    return "".join(p)


def dual_svg(cid, title, a, b, W=780, H=320, note=""):
    """a/b: (name, unit, dates, vals, color, vfmt) —— a 左轴，b 右轴。"""
    na, ua, da, va, ca, fa = a
    nb, ub, db, vb, cb, fb = b
    X0, X1, Y0, Y1 = 68, W - 62, 62, H - 40
    all_dates = sorted(set(da) | set(db))
    if not all_dates:
        return ""
    t0, t1 = _ord(all_dates[0]), _ord(all_dates[-1])
    la, ha, ta = axis(min(v for v in va if v is not None),
                      max(v for v in va if v is not None))
    lb, hb, tb = axis(min(v for v in vb if v is not None),
                      max(v for v in vb if v is not None))
    ya = lambda v: Y1 - (v - la) / max(1e-9, ha - la) * (Y1 - Y0)
    yb = lambda v: Y1 - (v - lb) / max(1e-9, hb - lb) * (Y1 - Y0)
    p = [f'<svg id="{cid}" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'xmlns="http://www.w3.org/2000/svg" class="cv">',
         f'<title>{esc(title)}</title>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fff"/>',
         f'<text x="14" y="24" font-size="14" font-weight="500" fill="{C_INK}" '
         f'font-family="-apple-system,PingFang SC,sans-serif">{esc(title)}</text>']
    for t in ta:
        y = ya(t)
        p.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" '
                 f'stroke="{C_LINE}" stroke-width="0.7"/>')
        p.append(f'<text x="{X0 - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="12" '
                 f'fill="{ca}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(fmt_tick(t))}</text>')
    for t in tb:
        y = yb(t)
        p.append(f'<text x="{X1 + 7}" y="{y + 3.5:.1f}" font-size="12" '
                 f'fill="{cb}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(fmt_tick(t))}</text>')
    for x, lab in date_ticks(all_dates, X0, X1, t0, t1, W=W):
        p.append(f'<text x="{x:.1f}" y="{Y1 + 17}" text-anchor="middle" font-size="12" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(lab)}</text>')
    p.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#cfd7e0" stroke-width="0.8"/>')
    for k, (name, unit, ds, vs, col, vfmt, y_of, u) in enumerate([
            (na, ua, da, va, ca, fa, ya, 0), (nb, ub, db, vb, cb, fb, yb, 1)]):
        d = _path(ds, vs, t0, t1, X0, X1, y_of)
        p.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.1" '
                 f'stroke-linejoin="round" stroke-linecap="round" data-s="{cid}-{k}"/>')
        p.append(_dots(ds, vs, t0, t1, X0, X1, y_of, col, cid, k, name, vfmt))
        last = next((v for v in reversed(vs) if v is not None), None)
        lv = vfmt(last) if last is not None else "—"
        lx = X0 + 2 if k == 0 else X0 + 300
        p.append(f'<g class="lg" data-chart="{cid}" data-k="{k}" style="cursor:pointer">'
                 f'<rect x="{lx}" y="36" width="10" height="10" rx="2" fill="{col}"/>'
                 f'<text x="{lx + 15}" y="45" font-size="12" fill="{C_INK}" '
                 f'font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(name)}（{esc(unit)}）{esc(lv)}</text></g>')
    if note:
        p.append(f'<text x="{X1}" y="{H - 8}" text-anchor="end" font-size="11.5" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(note)}</text>')
    p.append("</svg>")
    return "".join(p)


def spark(vals, color, W=120, H=34):
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    n = len(vals)
    pts = []
    for i, x in enumerate(vals):
        if x is None:
            continue
        px = 2 + i / max(1, n - 1) * (W - 4)
        py = H - 3 - (x - lo) / max(1e-9, hi - lo) * (H - 7)
        pts.append(f"{px:.1f},{py:.1f}")
    d = "M" + " L".join(pts) if pts else ""
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" aria-hidden="true">'
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


# ---------------------------------------------------------------- 组装
def main():
    al, al_hdr = read_alphaliner()
    dr = read_drewry()
    assert al and dr

    al_dates = [x["d"] for x in al]
    dr_dates = [x["d"] for x in dr]
    gaps = [(_ord(al_dates[i + 1]) - _ord(al_dates[i])) for i in range(len(al_dates) - 1)]
    max_gap_i = gaps.index(max(gaps))

    # 量价配对（用于统计结论，不插值、不入图）
    _, wci_p, pairs = pair(al, dr, "fleet", "wci")
    n_pair = sum(1 for p in pairs if p)
    st = {}
    for key_a, key_d, label in [
            ("fleet", "wci", "global"),
            ("tp", "lax", "tp"),
            ("fe", "rtm", "fe"),
            ("ta", "nyc", "ta")]:
        xs = [a[key_a] for a in al]
        ys = [b[key_d] for b in dr]
        xa, ya, _ = pair(al, dr, key_a, key_d)
        st[label] = dict(level=corr(xa, ya), diff=diff_corr(xa, ya))

    # 派生序列
    g = lambda k: [x[k] for x in al]
    fleet_w = [v / 10000 if v else None for v in g("fleet")]
    cosco_w = [v / 10000 if v else None for v in g("cosco")]
    order_w = [v / 10000 if v else None for v in g("order")]
    ta_w = [v / 10000 if v else None for v in g("ta")]
    tp_w = [v / 10000 if v else None for v in g("tp")]
    fe_w = [v / 10000 if v else None for v in g("fe")]
    share = g("share")
    order_pct = g("order_pct")
    idx_fleet = [v / fleet_w[0] * 100 if v else None for v in fleet_w]
    idx_cosco = [v / cosco_w[0] * 100 if v else None for v in cosco_w]
    h = lambda k: [x[k] for x in dr]
    W_TEU = lambda v: f"{v:,.1f}万TEU"
    W_USD = lambda v: f"{v:,.0f}"
    W_PCT = lambda v: f"{v:.1f}%"
    W_TEU0 = lambda v: f"{v:,.0f}TEU"

    def chg(seq, pct=True):
        a = next((v for v in seq if v is not None), None)
        b = next((v for v in reversed(seq) if v is not None), None)
        return ((b / a - 1) * 100) if (a and b and pct) else (b - a if a and b else 0)

    kpis = [
        ("全球在运营运力", f"{fleet_w[-1]:,.1f}", "万TEU", chg(fleet_w),
         spark(fleet_w, C_TEAL), "Alphaliner · " + al_dates[-1], C_TEAL),
        ("WCI 综合指数", f"{h('wci')[-1]:,.0f}", "USD/FEU", chg(h("wci")),
         spark(h("wci"), C_RED), "Drewry · " + dr_dates[-1], C_RED),
        ("东西向停航率", f"{h('blank')[-1]:.1f}", "%", h("blank")[-1] - h("blank")[0],
         spark(h("blank"), C_AMBER), "Drewry · " + dr_dates[-1], C_AMBER),
        ("中远海控运力", f"{cosco_w[-1]:,.1f}", "万TEU", chg(cosco_w),
         spark(cosco_w, C_BLUE), "Alphaliner · " + al_dates[-1], C_BLUE),
        ("中远全球份额", f"{share[-1]:.2f}", "%", share[-1] - share[0],
         spark(share, C_PURPLE), "Alphaliner · " + al_dates[-1], C_PURPLE),
        ("手持订单 / 现有运力", f"{order_pct[-1]:.1f}", "%", order_pct[-1] - order_pct[0],
         spark(order_pct, C_GREEN), "Alphaliner · " + al_dates[-1], C_GREEN),
    ]
    kpi_html = []
    for name, val, unit, delta, sp, src, col in kpis:
        is_pct_point = name in ("东西向停航率", "中远全球份额", "手持订单 / 现有运力")
        dtxt = (f"{delta:+.2f}pct" if is_pct_point else f"{delta:+.2f}%")
        cls = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        kpi_html.append(
            f'<div class="kpi"><div class="kpi-l">{esc(name)}</div>'
            f'<div class="kpi-v">{esc(val)}<small>{esc(unit)}</small></div>'
            f'<div class="kpi-c {cls}">{dtxt}<span> 年内</span></div>'
            f'<div class="kpi-s">{sp}</div><div class="kpi-d">{esc(src)}</div></div>')
    kpi_html = "".join(kpi_html)

    # --- 图 1：量价总览（双轴，真实日历 x）
    c1 = dual_svg("c1", "全球运力（量） vs WCI 综合（价）",
                  ("全球运力", "万TEU", al_dates, fleet_w, C_TEAL, W_TEU),
                  ("WCI 综合", "USD/FEU", dr_dates, h("wci"), C_RED, W_USD),
                  note=f"按真实日期定位 · 量 {len(al)} 期 / 价 {len(dr)} 期 · 点击图例隐藏序列")

    # --- 图 2：区域量价三组（双轴小图）
    def regional(cid, title, key_a, key_d, name_a, name_d, col_a, col_d, caveat, w=560):
        xa, ya, _ = pair(al, dr, key_a, key_d)
        av = [v / 10000 if v else None for v in g(key_a)]
        lv = corr(xa, ya)[0]
        dv = diff_corr(xa, ya)[0]
        s = dual_svg(cid, title,
                     (name_a, "万TEU", al_dates, av, col_a, W_TEU),
                     (name_d, "USD/FEU", dr_dates, h(key_d), col_d, W_USD),
                     W=w, H=290,
                     note=f"同期配对 r={lv:+.2f} · Δr={dv:+.2f}")
        return s, lv, dv, caveat

    c2, r2, d2, _ = regional("c2", "跨太平洋投放 vs 上海-洛杉矶 WCI",
                             "tp", "lax", "跨太平洋周运力", "上海-洛杉矶", C_TEAL, C_RED, "", w=560)
    c3, r3, d3, _ = regional("c3", "远东-欧洲投放 vs 上海-鹿特丹 WCI",
                             "fe", "rtm", "远东-欧洲周运力", "上海-鹿特丹", C_BLUE, C_RED, "", w=560)
    c4, r4, d4, _ = regional("c4", "跨大西洋投放 vs 上海-纽约 WCI",
                             "ta", "nyc", "跨大西洋周运力", "上海-纽约", C_GRAY, C_AMBER,
                             "口径不对等：跨大西洋指欧美之间，上海-纽约属跨太航线；仅作方向参考", w=780)

    # --- 图 3：三大干线投放（单轴多序列）
    c5 = multi_svg("c5", "三大主干航线周运力投放", "万TEU",
                   [("跨太平洋", al_dates, tp_w), ("远东-欧洲", al_dates, fe_w),
                    ("跨大西洋", al_dates, ta_w)],
                   [C_RED, C_BLUE, C_GRAY], W_TEU, W=560,
                   note="Alphaliner Global figures · 真实日历定位")

    # --- 图 4：WCI 四条上海出口航线
    c6 = multi_svg("c6", "上海出口四条航线 WCI", "USD/FEU",
                   [("上鹿", dr_dates, h("rtm")), ("上洛", dr_dates, h("lax")),
                    ("上热", dr_dates, h("goa")), ("上纽", dr_dates, h("nyc"))],
                   [C_BLUE, C_RED, C_AMBER, C_GRAY], W_USD, W=560,
                   note="Drewry WCI · 45 期")

    # --- 图 5：停航率与结构
    c7 = multi_svg("c7", "停航率与分航线取消量占比", "%",
                   [("停航率", dr_dates, h("blank")),
                    ("跨太", dr_dates, h("blank_tp")),
                    ("亚地", dr_dates, h("blank_ae")),
                    ("跨大", dr_dates, h("blank_ta"))],
                   [C_RED, C_TEAL, C_AMBER, C_GRAY], W_PCT,
                   note="停航率 = 停航航次÷计划航次；取消量占比三项合计约 100%")

    # --- 图 6：公司 vs 行业（指数化）
    c8 = multi_svg("c8", "中远海控运力 vs 全球运力（年初=100）", "指数",
                   [("全球运力", al_dates, idx_fleet), ("中远海控", al_dates, idx_cosco)],
                   [C_GRAY, C_RED], lambda v: f"{v:.1f}", W=560,
                   note=f"年内全球 {chg(fleet_w):+.2f}% / 中远 {chg(cosco_w):+.2f}%")

    # --- 图 7：订单
    c9 = dual_svg("c9", "中远海控手持订单：绝对量 vs 占现有运力",
                  ("手持订单", "万TEU", al_dates, order_w, C_GREEN, W_TEU),
                  ("订单/运力", "%", al_dates, order_pct, C_RED, W_PCT),
                  W=560, H=290, note="Alphaliner TOP100 · 5 月与 9 月两轮订单上修")

    # --- 数据质量面板
    bad_q = []
    for x in al:
        if x["owned"] and x["chart"] and x["cosco"] and abs(x["owned"] + x["chart"] - x["cosco"]) > 2:
            bad_q.append((x["d"], f"自有+租入 与 总运力 差 {x['cosco'] - x['owned'] - x['chart']:+,.0f} TEU"))
    bad_f = [x["d"] for x in al if x["fully"] == x["fleet"]]
    miss_rows = []
    for x in al:
        m = [k for k in ("order", "order_pct", "owned", "chart", "cosco_ships") if x[k] is None]
        if m:
            miss_rows.append((x["d"], "、".join(m)))

    quality = [
        ("样本", f"Alphaliner {len(al)} 期（{al_dates[0]} ~ {al_dates[-1]}）；Drewry {len(dr)} 期（{dr_dates[0]} ~ {dr_dates[-1]}）"),
        ("时间粒度", f"Alphaliner 间隔 最小 {min(gaps)} 天 / 中位 {sorted(gaps)[len(gaps)//2]} 天 / 最大 {max(gaps)} 天；"
                 f"最大断档 {al_dates[max_gap_i]} → {al_dates[max_gap_i+1]}。属 TOP100 快照，非严格周度，图中按真实日期定位"),
        ("量价配对", f"以 ±{PAIR_WINDOW} 天最近发布日期配对，{n_pair}/{len(al)} 期可配；未插值、未前向填充"),
        ("单位口径", "Alphaliner 原表「全球份额(%)」实为小数比例（0.1057），本页统一重算为 M÷C×100；"
                 "Drewry 停航率/取消量占比/营运率为小数比例，本页统一 ×100；"
                 "WCI周环比、订单占比、租入占比原表已是百分数，不再换算"),
        ("已知脏数据", f"F 全集装箱船运力 2 行与 C 串列（{('、'.join(bad_f)) or '无'}）；"
                   f"Q 租入运力 {len(bad_q)} 行与 M−O 不符（" + "；".join(f"{d} {m}" for d, m in bad_q) + "）；"
                   f"{len(miss_rows)} 行整段缺列（" + "；".join(f"{d} 缺 {m}" for d, m in miss_rows) + "）"),
        ("口径限制", "跨大西洋周运力（欧美之间）与「上海-纽约」WCI 并非同一航线口径，图 4 仅作方向参考；"
                 "量价水平值相关含共同趋势，不能作因果解读"),
        ("数据修复", "本页为只读展示，不回写 xlsx；上述脏数据保留在台账中，待确认后单独修正"),
    ]
    q_html = "".join(
        f'<tr><th>{esc(k)}</th><td>{v}</td></tr>' for k, v in quality)

    # --- 结论文字
    conclusion = (
        f"<b>一阶差分是本页最重要的结论。</b>"
        f"水平值上全球运力与 WCI 综合相关 r={st['global']['level'][0]:+.3f}，"
        f"但两条序列 2026 年同向上行，属共同趋势造成的伪相关；"
        f"一阶差分后 Δ运力 vs ΔWCI 仅 r={st['global']['diff'][0]:+.3f}（n={st['global']['diff'][1]}）。"
        f"分航线同样：跨太 Δr={st['tp']['diff'][0]:+.3f}、远东-欧洲 Δr={st['fe']['diff'][0]:+.3f}、"
        f"跨大西洋 Δr={st['ta']['diff'][0]:+.3f}。"
        f"这与停航率与运价无稳定正相关的既有结论一致——<b>运力投放与停航是慢变量/结果变量，"
        f"短期价格方向仍应以 WCI 与分航线运价本身为准</b>。"
        f"本页的价值在于把「量」与「价」并列观测、识别背离，而不是用运力去预测运价。"
    )

    HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>中远海控 · 运力 × 运价 双周报监测</title>
<style>
:root{--bg:#f4f6f8;--card:#fff;--line:#e3e8ee;--ink:#1f2733;--dim:#7a8694;--acc:#c8102e;--acc2:#15616d;--ok:#2e9e6b;--warn:#d98a14;--todo:#9aa6b2;--soft:#f7f9fb}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.6}
header.top{background:var(--card);border-bottom:1px solid var(--line);padding:16px 28px;position:sticky;top:0;z-index:5;box-shadow:0 1px 4px rgba(20,30,50,.04);display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.top h1{font-size:19px;font-weight:700;letter-spacing:.5px}
.top .sub{color:var(--dim);font-size:12px}
.top a{margin-left:auto;font-size:12px;color:var(--acc2);text-decoration:none;border:1px solid var(--line);background:var(--soft);border-radius:10px;padding:4px 10px;white-space:nowrap}
.top a:hover{background:#eef2f6}
.wrap{max-width:1200px;margin:0 auto;padding:22px 22px 80px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:12px;margin-bottom:24px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 14px 10px;box-shadow:0 1px 3px rgba(20,30,50,.04);position:relative;overflow:hidden}
.kpi-l{font-size:11.5px;color:var(--dim)}
.kpi-v{font-size:23px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.35;color:var(--ink)}
.kpi-v small{font-size:11px;font-weight:400;color:var(--dim);margin-left:4px}
.kpi-c{font-size:11.5px;font-weight:600;font-variant-numeric:tabular-nums}
.kpi-c span{font-weight:400;color:var(--todo)}
.kpi-c.up{color:var(--acc)}.kpi-c.down{color:var(--ok)}.kpi-c.flat{color:var(--dim)}
.kpi-s{position:absolute;right:8px;bottom:26px;opacity:.85}
.kpi-d{font-size:10px;color:var(--todo);border-top:1px dashed var(--line);padding-top:6px;margin-top:4px}
.sec{margin-top:26px}
.sec-hd{display:flex;align-items:baseline;gap:10px;margin-bottom:11px;flex-wrap:wrap}
.sec-n{width:24px;height:24px;border-radius:7px;background:var(--acc2);color:#fff;display:inline-grid;place-items:center;font-size:12px;font-weight:700;flex:none}
.sec h2{font-size:16px;font-weight:700}
.sec-sub{font-size:11.5px;color:var(--dim);margin-left:4px}
.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:13px;align-items:start}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;box-shadow:0 1px 3px rgba(20,30,50,.04);overflow:hidden}
.chart.wide{grid-column:1/-1}
.chart-hd{font-size:12.5px;font-weight:600;color:var(--ink);margin-bottom:4px;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.chart-hd::before{content:"";display:inline-block;width:3px;height:11px;background:var(--acc2);border-radius:2px}
.chart-tag{font-size:10px;font-weight:400;color:var(--warn);background:#fdf3e3;border-radius:9px;padding:1px 7px}
.chart svg{display:block;width:100%;height:auto;cursor:zoom-in}
.chart .cap{font-size:10.5px;color:var(--dim);margin-top:4px;line-height:1.5}
.note{font-size:12px;color:var(--ink);background:var(--soft);border-left:3px solid var(--acc2);padding:10px 13px;border-radius:0 8px 8px 0;margin-top:12px;line-height:1.75}
.qtab{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:12px}
.qtab th{width:110px;text-align:left;background:var(--soft);color:var(--dim);font-weight:600;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top;white-space:nowrap}
.qtab td{padding:9px 12px;border-bottom:1px solid var(--line);line-height:1.7}
.qtab tr:last-child th,.qtab tr:last-child td{border-bottom:none}
.foot{margin-top:26px;padding-top:12px;border-top:2px solid var(--line);font-size:11px;color:var(--todo);display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap}
#zoom{display:none;position:fixed;inset:0;background:rgba(20,30,50,.55);z-index:99999;padding:24px;overflow:auto}
#zoom.on{display:block}
#zoom .zbox{max-width:1400px;margin:0 auto;background:#fff;border-radius:12px;padding:14px}
#zoom svg{width:100%;height:auto;cursor:zoom-out}
#zoom .zhint{font-size:11px;color:var(--dim);margin-bottom:8px}
@media(max-width:700px){.chart-grid{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}.top a{margin-left:0}}
</style>
</head>
<body>
<header class="top"><h1>中远海控 · 运力 × 运价 双周报监测</h1>
<span class="sub">Alphaliner（量） / Drewry（价） · 2026 年内同期对照 · 单一 xlsx 数据源</span>
<a href="cosco-dashboard.html">返回主看板</a></header>
<div class="wrap">
<div class="kpis">"""

    MID1 = """</div>
<section class="sec">
<div class="sec-hd"><span class="sec-n">01</span><h2>量价总览</h2><span class="sec-sub">同一日历轴上的慢变量与快变量</span></div>
<div class="chart-grid"><div class="chart wide">
<div class="chart-hd">全球运力 vs WCI 综合 <span class="chart-tag">双轴 · 勿作因果解读</span></div>"""

    MID2 = """<div class="cap">左轴为全球在运营运力（万TEU），右轴为 WCI 综合（USD/FEU）。点击图例可隐藏序列；双击图形可放大。</div>
</div></div>
<div class="note">"""

    MID3 = """</div>
</section>
<section class="sec">
<div class="sec-hd"><span class="sec-n">02</span><h2>区域量价对照</h2><span class="sec-sub">投放量与对应航线运价并列观测</span></div>
<div class="chart-grid">
<div class="chart"><div class="chart-hd">跨太平洋 / 上海-洛杉矶</div>"""

    MID4 = """<div class="cap">该组航线口径对应，是三组中最可比的一组。</div></div>
<div class="chart"><div class="chart-hd">远东-欧洲 / 上海-鹿特丹</div>"""

    MID5 = """<div class="cap">该组航线口径对应。</div></div>
<div class="chart wide"><div class="chart-hd">跨大西洋 / 上海-纽约 <span class="chart-tag">口径不对等</span></div>"""

    MID6 = """<div class="cap">跨大西洋周运力指欧美之间航线，而「上海-纽约」属跨太平洋（经巴拿马）航线，二者并非同一口径；此处仅作方向性参考，不用于相关性结论。</div></div>
</div>
</section>
<section class="sec">
<div class="sec-hd"><span class="sec-n">03</span><h2>供给结构与价格分化</h2><span class="sec-sub">投放 → 停航 → 运价，三条并列</span></div>
<div class="chart-grid">
<div class="chart"><div class="chart-hd">三大主干航线周运力投放</div>"""

    MID7 = """</div>
<div class="chart"><div class="chart-hd">上海出口四条航线 WCI</div>"""

    MID8 = """</div>
<div class="chart wide"><div class="chart-hd">停航率与分航线取消量占比</div>"""

    MID9 = """</div>
</div>
<div class="note">年内结构变化：跨太平洋周运力 +11.9%、远东-欧洲 +10.9%、跨大西洋 −13.3%；同期上海-洛杉矶 WCI 由 2,481 升至 7,539 USD/FEU、上海-纽约由 3,302 升至 9,303，而上鹿与上热在 7 月见顶后回落。<b>运价分化幅度显著大于运力投放分化幅度</b>，说明区域价差主要由需求、绕航与船司定价策略驱动，而非运力存量本身。</div>
</section>
<section class="sec">
<div class="sec-hd"><span class="sec-n">04</span><h2>公司相对位置</h2><span class="sec-sub">中远海控 vs 行业</span></div>
<div class="chart-grid">
<div class="chart"><div class="chart-hd">运力增速对照（年初=100）</div>"""

    MID10 = """</div>
<div class="chart"><div class="chart-hd">手持订单与订单占现有运力</div>"""

    MID11 = """</div>
</div>
<div class="note">中远海控年内运力增速慢于全球约 0.7pct，份额由 10.65% 微降至 10.57%；但手持订单占现有运力由 38.1% 升至 50.6%（9 月峰值 52.4%），意味着后续运力增速大概率反超行业。这是双周报里<b>唯一具有前瞻性的公司层信号</b>。</div>
</section>
<section class="sec">
<div class="sec-hd"><span class="sec-n">05</span><h2>数据口径与质量</h2><span class="sec-sub">已知问题全部明示，不静默修补</span></div>
<table class="qtab">"""

    TAIL = """</table>
</section>
<div class="foot"><span>数据来源：Alphaliner PublicTop100（Global figures / TOP100 第 4 行 COSCO Group）；Drewry《Cancelled Sailings Tracker》与 WCI 周报（公众号转载整理）。</span>
<span>更新频率：Alphaliner 快照约 4–28 天不定期、Drewry 周度；本页由 build_volume_price.py 从 xlsx 重建，非实时。</span></div>
</div>
<div id="zoom" onclick="closeZoom(event)"><div class="zbox"><div class="zhint">双击图形放大 · 点击空白处关闭</div><div id="zbody"></div></div></div>
<script>
document.addEventListener('click',function(e){
  var g=e.target.closest?e.target.closest('.lg'):null;
  if(!g)return;
  var cid=g.getAttribute('data-chart'),k=g.getAttribute('data-k');
  var svg=document.getElementById(cid);if(!svg)return;
  var key=cid+'-'+k;
  svg.querySelectorAll('[data-s="'+key+'"]').forEach(function(el){
    el.style.display=(el.style.display==='none')?'':'none';
  });
  g.style.opacity=(g.style.opacity==='0.4')?'':'0.4';
});
document.addEventListener('dblclick',function(e){
  var svg=e.target.closest?e.target.closest('svg.cv'):null;
  if(!svg)return;
  document.getElementById('zbody').innerHTML=svg.outerHTML;
  document.getElementById('zoom').classList.add('on');
});
function closeZoom(e){
  if(e.target.id==='zoom'||e.target.closest('svg.cv')){
    document.getElementById('zoom').classList.remove('on');
    document.getElementById('zbody').innerHTML='';
  }
}
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){document.getElementById('zoom').classList.remove('on');}
});
</script>
</body></html>"""

    doc = (HEAD + kpi_html + MID1 + c1 + MID2 + conclusion + MID3 + c2 + MID4 + c3
           + MID5 + c4 + MID6 + c5 + MID7 + c6 + MID8 + c7 + MID9 + c8 + MID10
           + c9 + MID11 + q_html + TAIL)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print("生成:", OUT)
    print("字节:", len(doc.encode("utf-8")))
    print("SVG 数:", doc.count('<svg '))
    print(f"Alphaliner {len(al)} 期 / Drewry {len(dr)} 期 / ±{PAIR_WINDOW}天可配 {n_pair} 期")
    print(f"Δ相关: global={st['global']['diff'][0]:+.3f} tp={st['tp']['diff'][0]:+.3f} "
          f"fe={st['fe']['diff'][0]:+.3f} ta={st['ta']['diff'][0]:+.3f}")


if __name__ == "__main__":
    main()
