#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Drewry / Alphaliner / SSE 周报独立展示页生成器
=============================================
数据源（三个文件，互不混用）：
  · 数据源/中远海控_Drewry周报数据.xlsx     —— WCI / IACI / CST / RST 四张表 + 分析要点
  · 数据源/中远海控_Alphaliner周报数据.xlsx —— 全球 / COSCO 两张表 + 分析要点
  · 数据源/中远海控_SSE周报数据.xlsx        —— SCFI&CCFI 综合（2021 起）+ SCFI 分线（仅当年）

产出三个**内容严格隔离**的页面：
  · drewry-weekly.html     —— 四大来源：WCI（运价）/ IACI（亚洲区内）/ CST（停航）/ RST（红海绕航）
  · alphaliner-weekly.html —— 全球船队 / 中远海控 两大模块：运力 + 公司
  · sse-weekly.html        —— SCFI&CCFI 综合 / SCFI 分航线

设计原则：三套数据采样频率、口径与噪声来源不同，不做量价对照、不互为解释变量。

运行：
  python src/build_weekly_pages.py --only alphaliner   # 只重建 Alphaliner 页（每周六快照用）
  python src/build_weekly_pages.py --only drewry      # 只重建 Drewry 页
  python src/build_weekly_pages.py --only sse         # 只重建 SSE 页
  python src/build_weekly_pages.py                   # 不带参数＝三页全量重建（手工维护时用）

各 build_*() 只读自己那个 xlsx，不联网、不写回数据源；--only 用于把「谁的数据更新了」
与「谁的页面被重写」严格对齐，避免 Alphaliner 快照时连带重渲染 Drewry / SSE 页面。
"""
import os
import re
import math
import html
import datetime
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # 项目根 = src/ 的上一级
OUT_DIR = os.path.join(ROOT, "output")
os.makedirs(OUT_DIR, exist_ok=True)
XLSX = os.path.join(ROOT, "数据源", "中远海控_行业供需与运价数据.xlsx")
# 两个周报各自独立成文件（2026-11-13 起，均含 分析要点 表）
DR_XLSX = os.path.join(ROOT, "数据源", "中远海控_Drewry周报数据.xlsx")
AL_XLSX = os.path.join(ROOT, "数据源", "中远海控_Alphaliner周报数据.xlsx")
S_XLSX = os.path.join(ROOT, "数据源", "中远海控_SSE周报数据.xlsx")
OUT_DR = os.path.join(OUT_DIR, "drewry-weekly.html")
OUT_AL = os.path.join(OUT_DIR, "alphaliner-weekly.html")
OUT_SSE = os.path.join(OUT_DIR, "sse-weekly.html")

SHEET_AN = "分析要点"

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
    if hasattr(v, "date"):
        return v.date().isoformat()
    if isinstance(v, datetime.date):
        return v.isoformat()
    s = str(v)[:10] if v is not None else ""
    return s if re.match(r"^20\d\d-\d\d-\d\d$", s) else None


def _num(v):
    """数值化：源表里数字有 int 也有字符串（如 '33688151'），统一转 float。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


AL_G_FIELDS = [
    ("ships", "全球在运营船舶(艘)"), ("fleet", "全球运力(TEU)"), ("dwt", "总载重吨(DWT)"),
    ("fully_ships", "其中全集装箱船(艘)"), ("fully", "全集装箱船运力(TEU)"),
    ("ta", "跨大西洋周运力(TEU)"), ("tp", "跨太平洋周运力(TEU)"),
    ("fe", "远东-欧洲周运力(TEU)"),
]
AL_C_FIELDS = [
    ("rank", "排名"), ("share_raw", "全球份额(%)"), ("cosco", "总运力(TEU)"),
    ("cosco_ships", "总艘数"), ("owned", "自有运力(TEU)"), ("owned_ships", "自有艘数"),
    ("chart", "租入运力(TEU)"), ("chart_ships", "租入艘数"), ("chart_pct", "租入占比(%)"),
    ("order", "手持订单(TEU)"), ("order_ships", "订单艘数"),
    ("order_pct", "订单占现有运力(%)"),
]


def _al_sheet(wb, name, fields):
    """读一张表：{发布时间: {key: 数值}}；表头在第 1 行，表下说明区自动跳过。"""
    if name not in wb.sheetnames:
        raise KeyError("Alphaliner 数据文件缺 sheet「%s」" % name)
    w = wb[name]
    hdr = {str(w.cell(1, c).value).strip(): c
           for c in range(1, w.max_column + 1) if w.cell(1, c).value}
    for _, cn in fields:
        if cn not in hdr:
            raise KeyError("%s 表缺列: %s" % (name, cn))
    out = {}
    for r in range(2, w.max_row + 1):
        d = _d(w.cell(r, 1).value)
        if not d:
            continue
        out[d] = {k: _num(w.cell(r, hdr[cn]).value) for k, cn in fields}
    return out


def read_alphaliner(xlsx=None):
    """`全球` 与 `COSCO` 两表按发布时间合并。

    口径要点：
      · 「全球份额(%)」源表是 `#REF!` 断链，一律按 公司总运力 ÷ 全球运力 重算；
      · 2026-06-17 与 2026-10-02 两期缺自有/租入/订单拆分，留空断线；
      · 快照为**不定期**（间隔 4–28 天），x 轴按真实日期定位，不做等距。
    """
    wb = openpyxl.load_workbook(xlsx or AL_XLSX, data_only=True)
    g = _al_sheet(wb, "全球", AL_G_FIELDS)
    c = _al_sheet(wb, "COSCO", AL_C_FIELDS)
    out = []
    for d in sorted(set(g) | set(c)):
        a, b = g.get(d, {}), c.get(d, {})
        if a.get("fleet") is None and b.get("cosco") is None:
            continue
        rec = dict(d=d)
        rec.update({k: a.get(k) for k, _ in AL_G_FIELDS})
        rec.update({k: b.get(k) for k, _ in AL_C_FIELDS})
        rec["share"] = (rec["cosco"] / rec["fleet"] * 100
                        if rec.get("cosco") and rec.get("fleet") else None)
        rec["per_ship"] = (rec["fleet"] / rec["ships"]
                           if rec.get("fleet") and rec.get("ships") else None)
        # 拆分自洽性：自有 + 租入 与 总运力 对不上（>0.5%）视为串列/缺位，图示断线
        rec["_split_gap"] = (rec["cosco"] - rec["owned"] - rec["chart"]
                             if all(rec.get(k) for k in ("cosco", "owned", "chart"))
                             else None)
        rec["_split_bad"] = bool(rec["_split_gap"] is not None
                                 and abs(rec["_split_gap"]) / rec["cosco"] > 0.005)
        if rec["_split_bad"]:
            rec["chart"] = None
        out.append(rec)
    return out


# IACI 表：综合 + 周环比 + 8 条主要航线（按表头名读取，缺失不报错）
IACI_COLUMNS = [
    ("iaci",     "IACI综合(美元/40ft)"),
    ("iaci_wow", "IACI周环比(%)"),
    ("r_np",     "Shanghai to Nehru Port(美元/40ft)"),
    ("r_tp",     "Shanghai to Tanjung Pelepas(美元/40ft)"),
    ("r_sg",     "Shanghai to Singapore(美元/40ft)"),
    ("r_yk",     "Shanghai to Yokohama(美元/40ft)"),
    ("r_jk",     "Jakarta to Shanghai(美元/40ft)"),
    ("r_bs",     "Busan to Shanghai(美元/40ft)"),
    ("r_hc",     "Ho Chi Minh City to Shanghai(美元/40ft)"),
    ("r_yy",     "Yokohama to Shanghai(美元/40ft)"),
]

WCI_COLUMNS = [
    ("wci", "WCI综合(美元/FEU)"), ("wow", "WCI周环比(%)"),
    ("rtm", "上海-鹿特丹(美元/FEU)"), ("lax", "上海-洛杉矶(美元/FEU)"),
    ("goa", "上海-热那亚(美元/FEU)"), ("nyc", "上海-纽约(美元/FEU)"),
]

CST_COLUMNS = [
    ("planned", "计划航次"), ("blank_n", "停航航次"), ("blank", "停航率(%)"),
    ("blank_tp", "跨太平洋东行取消量(%)"),
    ("blank_ae", "亚洲-北欧/地中海占取消量(%)"),
    ("blank_ta", "跨大西洋占取消量(%)"), ("ontime", "按计划营运率(%)"),
]


def _sheet_dict(wb, name, cols, texts=()):
    """读一张表：{发布日期: {key: value}}，跳过表下的口径说明区。

    texts 中的 key 按字符串读取（如「覆盖周数」W47–W51），其余按数值。
    """
    w = wb[name]
    hdr = {str(w.cell(1, c).value).strip().lstrip("\u3000"): c
           for c in range(1, w.max_column + 1) if w.cell(1, c).value}
    out = {}
    for r in range(2, w.max_row + 1):
        d = _d(w.cell(r, 1).value)
        if not d:
            continue
        rec = {}
        for key, cn in cols:
            if cn not in hdr:
                rec[key] = "" if key in texts else None
            elif key in texts:
                rec[key] = str(w.cell(r, hdr[cn]).value or "")
            else:
                rec[key] = _num(w.cell(r, hdr[cn]).value)
        out[d] = rec
    return out


def _wk(d):
    """ISO 周键 (ISO 年, 周序号)。

    CST 每周五发布、WCI/IACI 每周四发布，同一期在两表里的日期天然相差 1 天，
    因此**按 ISO 周归并**，而不是要求日期字符串相等。
    """
    y, w, _ = datetime.date.fromisoformat(d).isocalendar()
    return (y, w)


def _by_week(dct, name):
    out = {}
    for d, rec in dct.items():
        k = _wk(d)
        if k in out:
            raise RuntimeError(
                "%s 表在同一 ISO 周 %s 出现两行：%s / %s"
                % (name, k, out[k][0], d))
        out[k] = (d, rec)
    return out


def read_drewry():
    """三张表按 ISO 周合并成一条时间序列。

    日期口径：各表保留自己的发布日（WCI/IACI 周四、CST 周五），
    记录里 `d` 为 WCI 侧日期（作跨表统一键），`d_cst` 为 CST 侧日期。
    CST 在新表中按**百分数**存储，此处不再 ×100（旧表为小数比例）。
    """
    wb = openpyxl.load_workbook(DR_XLSX, data_only=True)
    wci = _by_week(_sheet_dict(wb, "WCI", WCI_COLUMNS), "WCI")
    cst = _by_week(_sheet_dict(wb, "CST", CST_COLUMNS + [("_win", "覆盖周数")],
                               texts=("_win",)), "CST")
    iaci = _by_week(_sheet_dict(wb, "IACI", IACI_COLUMNS), "IACI")

    # 周序必须一一对应；两边差几天要落在「周四 vs 周五」的正常范围内
    if set(wci) != set(cst):
        only_w = sorted(k for k in set(wci) - set(cst))[:6]
        only_c = sorted(k for k in set(cst) - set(wci))[:6]
        raise RuntimeError(
            "WCI 与 CST 的周序不匹配（WCI %d 周 / CST %d 周）。"
            "仅 WCI 有：%s；仅 CST 有：%s" % (len(wci), len(cst), only_w, only_c))
    bad = []
    for k in sorted(set(wci) & set(cst)):
        gap = _ord(cst[k][0]) - _ord(wci[k][0])
        if abs(gap) > 3:
            bad.append((wci[k][0], cst[k][0], gap))
    if bad:
        raise RuntimeError(
            "CST 与 WCI 同日期间的日期差超过 3 天，疑似错列或跨期：%s" % bad[:5])
    stray = sorted(set(iaci) - set(wci))
    if stray:
        raise RuntimeError("IACI 存在 WCI 中不存在的周：%s" % stray[:6])

    out = []
    for k in sorted(set(wci) | set(cst)):
        w = wci.get(k, (None, {}))[1]
        c = cst.get(k, (None, {}))[1]
        i = iaci.get(k, (None, {}))[1]
        d = wci.get(k, cst.get(k, (None,)))[0]
        d_cst = cst.get(k, (None,))[0]
        if (w.get("wci") is None and c.get("blank") is None
                and i.get("iaci") is None):
            continue                       # 占位行不参与展示
        rec = dict(d=d, d_cst=d_cst, window=c.get("_win", ""))
        rec.update({kk: w.get(kk) for kk, _ in WCI_COLUMNS})
        rec.update({kk: c.get(kk) for kk, _ in CST_COLUMNS})
        rec.update({kk: i.get(kk) for kk, _ in IACI_COLUMNS})
        out.append(rec)
    return out


def read_rst():
    """Red Sea Diversion Tracker：周度苏伊士/好望角通航艘数。

    返回 [{d, suez, cape, ae_share}]，按周结束日升序；表下说明区自动跳过。
    """
    wb = openpyxl.load_workbook(DR_XLSX, data_only=True)
    if "RST" not in wb.sheetnames:
        return []
    w = wb["RST"]
    hdr = {str(w.cell(1, c).value).strip(): c
           for c in range(1, w.max_column + 1) if w.cell(1, c).value}
    out = []
    for r in range(2, w.max_row + 1):
        d = _d(w.cell(r, 1).value)
        if not d:
            continue
        g = lambda k: _num(w.cell(r, hdr[k]).value) if k in hdr else None
        out.append(dict(d=d, suez=g("经苏伊士(艘/周)"), cape=g("经好望角(艘/周)"),
                        ae_share=g("亚欧运力经苏伊士(%)")))
    return out


def _ord(s):
    return datetime.date.fromisoformat(s).toordinal()


# ---------------------------------------------------------------- 分析要点
def read_analysis(xlsx=None):
    """读 sheet「分析要点」，返回 {来源: {asof, title, points}}（取各来源最新一版）。

    sheet 结构：A 数据截止 | B 来源 | C 标题 | D 要点 | E 序 | F 采集时间
    Drewry 侧由 drewry_ingest.py 写入；Alphaliner 侧由 alphaliner_sync.py 写入。
    缺该 sheet 时返回 {}，页面降级为仅显示自动生成注解。
    """
    wb = openpyxl.load_workbook(xlsx or DR_XLSX, data_only=True)
    if SHEET_AN not in wb.sheetnames:
        return {}
    w = wb[SHEET_AN]
    hdr = {str(w.cell(1, c).value).strip(): c
           for c in range(1, w.max_column + 1) if w.cell(1, c).value}
    need = ["数据截止", "来源", "要点"]
    for k in need:
        if k not in hdr:
            return {}
    groups = {}
    for r in range(2, w.max_row + 1):
        d = _d(w.cell(r, hdr["数据截止"]).value)
        src = str(w.cell(r, hdr["来源"]).value or "").strip().upper()
        pt = str(w.cell(r, hdr["要点"]).value or "").strip()
        if not d or not src or not pt:
            continue
        g = groups.setdefault((src, d), {"asof": d, "title": "", "points": []})
        t = str(w.cell(r, hdr.get("标题", 3)).value or "").strip()
        if t and not g["title"]:
            g["title"] = t
        order = _num(w.cell(r, hdr["序"]).value) if "序" in hdr else None
        g["points"].append((order if order is not None else 999, pt))
    out = {}
    for (src, d), g in groups.items():
        if src in out and out[src]["asof"] >= g["asof"]:
            continue
        g["points"] = [p for _, p in sorted(g["points"], key=lambda x: x[0])]
        out[src] = g
    return out


def pct(a, b):
    """b 相对 a 的百分比变化；任一为空返回 None。"""
    return (b / a - 1) * 100 if (a and b) else None


def stats(rows, key):
    """单个字段的末期/前期/周环比/年内极值。返回 None 表示该字段无数据。"""
    seq = [(r["d"], r[key]) for r in rows if r[key] is not None]
    if not seq:
        return None
    d1, v1 = seq[-1]
    d0, v0 = seq[-2] if len(seq) > 1 else (None, None)
    vals = [v for _, v in seq]
    lo, hi = min(vals), max(vals)
    return dict(d=d1, v=v1, d0=d0, v0=v0, wow=pct(v0, v1), lo=lo, hi=hi,
                lo_d=seq[vals.index(lo)][0], hi_d=seq[vals.index(hi)][0], n=len(vals))


def _streak(vals):
    """末期连续同向的期数（含末期）。"""
    seq = [v for v in vals if v is not None]
    if len(seq) < 2:
        return 0, 0
    sign = 1 if seq[-1] > seq[-2] else (-1 if seq[-1] < seq[-2] else 0)
    if sign == 0:
        return 0, 0
    n = 1
    for i in range(len(seq) - 1, 0, -1):
        d = 1 if seq[i] > seq[i - 1] else (-1 if seq[i] < seq[i - 1] else 0)
        if d != sign:
            break
        n += 1
    return sign, n - 1


def _dir_word(p):
    return "上涨" if p > 0 else ("下跌" if p < 0 else "持平")


# ---------------------------------------------------------------- SVG 绘制
def esc(s):
    return html.escape(str(s), quote=True)


def axis(lo, hi, n=4):
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


def fmt_tick(v):
    a = abs(v)
    if a >= 10000:
        return f"{v:,.0f}"
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:.1f}"
    return f"{v:.1f}" if not float(v).is_integer() else f"{v:.0f}"


def axis_nonneg(vals):
    """计数类指标（艘数、航次）的 y 轴：下限压到 0，避免出现「负的船数」。"""
    lo, hi, ticks = axis(min(vals), max(vals))
    if min(vals) < 0:
        return lo, hi, ticks
    step = (ticks[1] - ticks[0]) if len(ticks) > 1 else max(1.0, hi - lo)
    ticks, v = [], 0.0
    while v <= hi + step * 1e-9 and len(ticks) < 12:
        ticks.append(v)
        v += step
    return 0.0, hi, ticks


def date_ticks(dates, x0, x1, t0, t1, W=780):
    limit = 5 if W < 650 else 7
    multi_year = bool(dates) and dates[0][:4] != dates[-1][:4]
    out, seen = [], set()
    for s in dates:
        m = s[:7]
        if m in seen:
            continue
        seen.add(m)
        x = x0 + (_ord(s) - t0) / max(1, t1 - t0) * (x1 - x0)
        if multi_year:
            lab = "%s年%d月" % (s[2:4], int(s[5:7]))
        else:
            lab = s[:4] + "-01" if m[5:7] == "01" else s[5:7] + "月"
        out.append((x, lab))
    if len(out) > limit:
        out = out[::math.ceil(len(out) / limit)]
    lastx = x0 + (_ord(dates[-1]) - t0) / max(1, t1 - t0) * (x1 - x0)
    gap_min = 50 if multi_year else 38
    lastx_lab = dates[-1][5:]
    if out and abs(out[-1][0] - lastx) <= gap_min:
        # 最后一个月度刻度离末点很近：直接改标为真实日期，避免「11月」让人误读成月末
        out[-1] = (lastx, lastx_lab)
    elif not out or abs(out[-1][0] - lastx) > gap_min:
        out.append((lastx, lastx_lab))
    return out


def _path(dates, vals, t0, t1, x0, x1, y_of):
    seg, segs = [], []
    for s, v in zip(dates, vals):
        if v is None or not isinstance(v, (int, float)):
            if len(seg) > 1:
                segs.append(seg)
            seg = []
            continue
        x = x0 + (_ord(s) - t0) / max(1, t1 - t0) * (x1 - x0)
        seg.append((x, y_of(v)))
    if len(seg) > 1:
        segs.append(seg)
    return " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in g) for g in segs)


def _dots(dates, vals, t0, t1, x0, x1, y_of, color, cid, k, name, vfmt, hl=False):
    out = []
    for i, (s, v) in enumerate(zip(dates, vals)):
        if v is None or not isinstance(v, (int, float)):
            continue
        x = x0 + (_ord(s) - t0) / max(1, t1 - t0) * (x1 - x0)
        y = y_of(v)
        r = 3.6 if i == len(dates) - 1 else 2.4
        out.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" '
            f'stroke="#fff" stroke-width="0.9" data-s="{cid}-{k}">'
            f'<title>{esc(s)} · {esc(name)} {esc(vfmt(v))}</title></circle>')
        # 末点强调环：让"最新一期"在长序列里一眼可辨
        if hl and i == len(dates) - 1:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.6" fill="none" '
                       f'stroke="{C_AMBER}" stroke-width="1.6" opacity=".9"/>')
    return "".join(out)


def _head(cid, title, W, H, unit="", note="", show_title=True):
    p = [f'<svg id="{cid}" viewBox="0 0 {W} {H}" width="100%" role="img" '
         f'xmlns="http://www.w3.org/2000/svg" class="cv">',
         f'<title>{esc(title)}</title>',
         f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fff"/>']
    ty = 24 if show_title else 14
    if show_title and title:
        p.append(f'<text x="14" y="{ty}" font-size="14" font-weight="500" fill="{C_INK}" '
                 f'font-family="-apple-system,PingFang SC,sans-serif">{esc(title)}</text>')
    if unit:
        p.append(f'<text x="{W - 14}" y="{ty}" text-anchor="end" font-size="12" fill="{C_DIM}" '
                 f'font-family="-apple-system,PingFang SC,sans-serif">单位：{esc(unit)}</text>')
    return p


def _foot(p, W, H, X1, note):
    if note:
        p.append(f'<text x="{X1}" y="{H - 8}" text-anchor="end" font-size="11.5" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(note)}</text>')
    p.append("</svg>")
    return "".join(p)


def _foot_text(unit, note, show_title):
    """无内嵌标题时，把单位与脚注合并到右下角一行，避免与图例抢顶部空间。"""
    bits = []
    if unit and not show_title:
        bits.append("单位：" + unit)
    if note:
        bits.append(note)
    return " · ".join(bits)


def multi_svg(cid, title, unit, blocks, colors, vfmt=None, W=780, H=300, note="",
              hl=False, show_title=False, zero=False):
    """blocks: [(name, dates, vals)] 共用一个 y 轴。zero=True 时 y 轴下限压到 0（计数类）。"""
    vfmt = vfmt or (lambda v: f"{v:,.0f}")
    Y0 = 58 if show_title else 40
    X0, X1, Y1 = 62, W - 18, H - 40
    all_dates = sorted({s for _, ds, _ in blocks for s in ds})
    allv = [v for _, _, vs in blocks for v in vs if v is not None]
    if not all_dates or not allv:
        return ""
    t0, t1 = _ord(all_dates[0]), _ord(all_dates[-1])
    lo, hi, ticks = axis_nonneg(allv) if zero else axis(min(allv), max(allv))
    y_of = lambda v: Y1 - (v - lo) / max(1e-9, hi - lo) * (Y1 - Y0)
    p = _head(cid, title, W, H, unit if show_title else "", "", show_title)
    for t in ticks:
        y = y_of(t)
        p.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" '
                 f'stroke="{C_LINE}" stroke-width="0.7"/>')
        p.append(f'<text x="{X0 - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="12" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(fmt_tick(t))}</text>')
    for x, lab in date_ticks(all_dates, X0, X1, t0, t1, W):
        p.append(f'<text x="{x:.1f}" y="{Y1 + 17}" text-anchor="middle" font-size="12" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(lab)}</text>')
    p.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#cfd7e0" stroke-width="0.8"/>')
    lx = X0 + 2
    ly = 34 if show_title else 4
    for k, (name, ds, vs) in enumerate(blocks):
        col = colors[k % len(colors)]
        p.append(f'<path d="{_path(ds, vs, t0, t1, X0, X1, y_of)}" fill="none" '
                 f'stroke="{col}" stroke-width="2" stroke-linejoin="round" '
                 f'stroke-linecap="round" data-s="{cid}-{k}"/>')
        p.append(_dots(ds, vs, t0, t1, X0, X1, y_of, col, cid, k, name, vfmt, hl))
        last = next((v for v in reversed(vs) if v is not None), None)
        lv = vfmt(last) if last is not None else "—"
        est = 30 + len(name) * 12 + len(lv) * 7
        if lx + est > X1 - 4 and lx > X0 + 2:      # 图例自动换行，防溢出卡片
            lx, ly = X0 + 2, ly + 14
        p.append(f'<g class="lg" data-chart="{cid}" data-k="{k}" style="cursor:pointer">'
                 f'<rect x="{lx}" y="{ly}" width="10" height="10" rx="2" fill="{col}"/>'
                 f'<text x="{lx + 15}" y="{ly + 9}" font-size="12" fill="{C_INK}" '
                 f'font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(name)} {esc(lv)}</text></g>')
        lx += est
    return _foot(p, W, H, X1, _foot_text(unit, note, show_title))


def dual_svg(cid, title, a, b, W=780, H=310, note="", hl=False, show_title=False):
    """a/b: (name, unit, dates, vals, color, vfmt)；a 左轴，b 右轴。"""
    na, ua, da, va, ca, fa = a
    nb, ub, db, vb, cb, fb = b
    Y0 = 62 if show_title else 44
    X0, X1, Y1 = 68, W - 62, H - 40
    all_dates = sorted(set(da) | set(db))
    if not all_dates:
        return ""
    t0, t1 = _ord(all_dates[0]), _ord(all_dates[-1])
    va2 = [v for v in va if v is not None]
    vb2 = [v for v in vb if v is not None]
    la, ha, ta = axis(min(va2), max(va2))
    lb, hb, tb = axis(min(vb2), max(vb2))
    ya = lambda v: Y1 - (v - la) / max(1e-9, ha - la) * (Y1 - Y0)
    yb = lambda v: Y1 - (v - lb) / max(1e-9, hb - lb) * (Y1 - Y0)
    p = _head(cid, title, W, H, "", note, show_title)
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
    for x, lab in date_ticks(all_dates, X0, X1, t0, t1, W):
        p.append(f'<text x="{x:.1f}" y="{Y1 + 17}" text-anchor="middle" font-size="12" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(lab)}</text>')
    p.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="#cfd7e0" stroke-width="0.8"/>')
    for k, (name, unit, ds, vs, col, vfmt, y_of) in enumerate([
            (na, ua, da, va, ca, fa, ya), (nb, ub, db, vb, cb, fb, yb)]):
        p.append(f'<path d="{_path(ds, vs, t0, t1, X0, X1, y_of)}" fill="none" '
                 f'stroke="{col}" stroke-width="2.1" stroke-linejoin="round" '
                 f'stroke-linecap="round" data-s="{cid}-{k}"/>')
        p.append(_dots(ds, vs, t0, t1, X0, X1, y_of, col, cid, k, name, vfmt, hl))
        last = next((v for v in reversed(vs) if v is not None), None)
        lv = vfmt(last) if last is not None else "—"
        lx = X0 + 2 if k == 0 else X0 + (250 if W < 650 else 300)
        ly = 36 if show_title else 4
        p.append(f'<g class="lg" data-chart="{cid}" data-k="{k}" style="cursor:pointer">'
                 f'<rect x="{lx}" y="{ly}" width="10" height="10" rx="2" fill="{col}"/>'
                 f'<text x="{lx + 15}" y="{ly + 9}" font-size="12" fill="{C_INK}" '
                 f'font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(name)}（{esc(unit)}）{esc(lv)}</text></g>')
    return _foot(p, W, H, X1, _foot_text("", note, show_title))


def bar_svg(cid, title, unit, dates, vals, W=560, H=290, note="", show_title=False):
    """正负双向柱状图：涨红跌绿。"""
    Y0 = 58 if show_title else 40
    X0, X1, Y1 = 62, W - 18, H - 40
    v = [x for x in vals if x is not None]
    if not v:
        return ""
    lo, hi = min(0, min(v)), max(0, max(v))
    lo, hi, ticks = axis(lo, hi)
    y_of = lambda x: Y1 - (x - lo) / max(1e-9, hi - lo) * (Y1 - Y0)
    t0, t1 = _ord(dates[0]), _ord(dates[-1])
    bw = max(2.0, (X1 - X0) / len(dates) * 0.6)
    p = _head(cid, title, W, H, unit if show_title else "", "", show_title)
    for t in ticks:
        y = y_of(t)
        p.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" '
                 f'stroke="{C_LINE}" stroke-width="0.7"/>')
        p.append(f'<text x="{X0 - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="12" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(fmt_tick(t))}</text>')
    p.append(f'<line x1="{X0}" y1="{y_of(0):.1f}" x2="{X1}" y2="{y_of(0):.1f}" '
             f'stroke="#b8c2cd" stroke-width="0.9"/>')
    for s, x in zip(dates, vals):
        if x is None:
            continue
        px = X0 + (_ord(s) - t0) / max(1, t1 - t0) * (X1 - X0)
        y1, y2 = y_of(0), y_of(x)
        col = C_RED if x >= 0 else C_GREEN
        p.append(f'<rect x="{px - bw / 2:.1f}" y="{min(y1, y2):.1f}" width="{bw:.1f}" '
                 f'height="{max(1.2, abs(y2 - y1)):.1f}" fill="{col}" opacity="0.85" '
                 f'data-s="{cid}-0"><title>{esc(s)} · {x:+.2f}%</title></rect>')
    for x, lab in date_ticks(dates, X0, X1, t0, t1, W):
        p.append(f'<text x="{x:.1f}" y="{Y1 + 17}" text-anchor="middle" font-size="12" '
                 f'fill="{C_DIM}" font-family="-apple-system,PingFang SC,sans-serif">'
                 f'{esc(lab)}</text>')
    return _foot(p, W, H, X1, _foot_text(unit, note, show_title))


def spark(vals, color, W=120, H=34):
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    pts = []
    for i, x in enumerate(vals):
        if x is None:
            continue
        px = 2 + i / max(1, len(vals) - 1) * (W - 4)
        py = H - 3 - (x - lo) / max(1e-9, hi - lo) * (H - 7)
        pts.append(f"{px:.1f},{py:.1f}")
    return (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" aria-hidden="true">'
            f'<path d="M{" L".join(pts)}" fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


# ---------------------------------------------------------------- HTML 骨架
CSS = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>
:root{--bg:#f4f6f8;--card:#fff;--line:#e3e8ee;--ink:#1f2733;--dim:#7a8694;--acc:#c8102e;--acc2:#15616d;--ok:#2e9e6b;--warn:#d98a14;--todo:#9aa6b2;--soft:#f7f9fb}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.6}
header.top{background:var(--card);border-bottom:1px solid var(--line);padding:14px 28px;position:sticky;top:0;z-index:5;box-shadow:0 1px 4px rgba(20,30,50,.04);display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.top h1{font-size:18px;font-weight:700;letter-spacing:.4px}
.top .sub{font-size:11.5px;color:var(--dim)}
nav.tabs{display:flex;gap:6px;margin-left:auto;align-items:center}
nav.tabs a{font-size:11.5px;color:var(--dim);text-decoration:none;border:1px solid var(--line);background:var(--soft);border-radius:10px;padding:4px 11px;white-space:nowrap}
nav.tabs a.on{background:var(--acc2);color:#fff;border-color:var(--acc2);font-weight:600}
nav.tabs a.back{color:var(--acc2)}
.wrap{max-width:1600px;margin:0 auto;padding:22px 28px 80px}
/* Alphaliner 同步按钮：置于顶部分块导航行的最右侧 */
.al-sync-btn{font-size:12px;color:#fff;background:var(--acc2);border:1px solid var(--acc2);border-radius:9px;padding:5px 12px;cursor:pointer;white-space:nowrap;margin-left:auto}
.al-sync-btn:hover{background:#0e4a55}
.al-sync-btn:disabled{background:var(--dim);border-color:var(--dim);cursor:not-allowed}
.al-status{font-size:10.5px;color:var(--dim);line-height:1.45;word-break:break-word;flex:1 1 100%;text-align:right;min-width:0}
.al-status:empty{display:none}
.al-status.ok{color:var(--acc2)}
.al-status.err{color:#c53030}
/* Alphaliner 同步操作条：导航移除后独立成一行，按钮靠右、状态跟后 */
.al-bar{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.al-bar .al-sync-btn{margin-left:auto}
.al-bar .al-status{flex:0 1 auto;margin-left:0;text-align:right}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));gap:12px;margin-bottom:20px}
.kpis.k3{grid-template-columns:repeat(3,1fr)}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 14px 10px;box-shadow:0 1px 3px rgba(20,30,50,.04);position:relative;overflow:hidden}
.kpi-l{font-size:11.5px;color:var(--dim)}
.kpi-v{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.35}
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
/* Drewry 专属：左侧垂直导航 + 右侧全宽内容（Tabler sidebar 风格） */
.vlayout{display:grid;grid-template-columns:212px minmax(0,1fr);gap:18px;align-items:start}
.vside{position:sticky;top:68px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 10px;box-shadow:0 1px 3px rgba(20,30,50,.04)}
.vside h3{font-size:10px;font-weight:700;color:var(--todo);letter-spacing:.9px;margin:2px 10px 10px}
.vside a{display:flex;gap:9px;align-items:center;padding:8px 10px;border-radius:9px;color:var(--dim);text-decoration:none;font-size:12px;margin-bottom:2px;line-height:1.3}
.vside a:hover{background:var(--soft);color:var(--acc2)}
.vside a.on{background:var(--acc2);color:#fff;font-weight:600}
.vside .di{width:22px;height:22px;border-radius:7px;background:var(--soft);color:var(--acc2);display:grid;place-items:center;font-size:10px;font-weight:700;flex:none}
.vside a.on .di{background:rgba(255,255,255,.22);color:#fff}
.vside small{display:block;font-size:10px;color:var(--todo);font-weight:400;margin-top:2px}
.vside a.on small{color:rgba(255,255,255,.82)}
.vside .back{margin-top:9px;border-top:1px dashed var(--line);padding-top:10px;border-radius:0}
.vside .al-sync-btn{width:100%;margin:10px 0 0;text-align:center}
.vside .al-status{flex:none;display:block;margin:6px 0 0;text-align:left;line-height:1.4}
.vmain{min-width:0}
.vmain .chart-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.vmain .blk{margin-top:0;margin-bottom:30px;scroll-margin-top:68px}
@media(max-width:1100px){.vlayout{grid-template-columns:1fr}.vside{position:static}.vmain .blk{margin-bottom:24px}}
@media(max-width:700px){.vmain .chart-grid{grid-template-columns:1fr}}
/* 三张来源分块 */
nav.anchors{display:flex;gap:7px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
nav.anchors span{font-size:10.5px;color:var(--todo)}
nav.anchors a{font-size:11.5px;color:var(--dim);text-decoration:none;border:1px solid var(--line);background:var(--card);border-radius:9px;padding:4px 11px;white-space:nowrap}
nav.anchors a:hover{color:var(--acc2);border-color:var(--acc2)}
nav.anchors a b{color:var(--acc2);margin-right:5px;font-weight:700}
.blk{margin-top:32px;scroll-margin-top:70px}
/* PC 宽屏：四大来源 2×2 卡片并排（仅 .dash 包裹层生效，不影响其它页） */
.dash{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
.dash .blk{margin-top:0;scroll-margin-top:70px}
/* 半宽卡片内 KPI 更紧凑，确保 WCI 5 个能排成一行（每列约143px）；仅 2 列宽屏生效 */
@media(min-width:1201px){
.dash .kpis{grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px}
.dash .kpi{padding:11px 11px 8px}
.dash .kpi-v{font-size:20px}
/* SSE：综合 4 项单行；分线 6 项走 3×2，避免 5+1 孤行 */
.vmain #sseidx .kpis{grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}
.vmain #sseroute .kpis{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
}
/* Tabler 风格卡片：来源块整体成卡，header/body 分层 */
.dash .blk{background:transparent}
.dash .blk-hd{border-left-width:4px}
.blk-hd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc2);border-radius:12px;padding:11px 15px;margin-bottom:12px;box-shadow:0 1px 3px rgba(20,30,50,.04)}
.blk-badge{font-size:10.5px;font-weight:700;letter-spacing:.7px;color:#fff;background:var(--acc2);padding:3px 9px;border-radius:6px;white-space:nowrap}
.blk-hd h2{font-size:15.5px;font-weight:700}
.blk-sub{font-size:11.5px;color:var(--dim)}
.blk-meta{margin-left:auto;font-size:10.5px;color:var(--todo);text-align:right;line-height:1.55}
.blk-meta b{color:var(--acc2);font-weight:600;font-variant-numeric:tabular-nums}
.kps{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:13px;box-shadow:0 1px 3px rgba(20,30,50,.04)}
.kps-h{font-size:11px;font-weight:700;color:var(--acc2);letter-spacing:.4px;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.kps-h em{font-style:normal;font-weight:400;color:var(--todo);letter-spacing:0}
/* 本期要点默认折叠：summary 一行概览，展开后见完整要点 */
details.kps>summary{list-style:none;cursor:pointer;padding:10px 16px;user-select:none}
details.kps>summary::-webkit-details-marker{display:none}
details.kps>summary::before{content:"▸";color:var(--acc2);font-size:12px;margin-right:2px;display:inline-block;transition:transform .15s}
details.kps[open]>summary::before{transform:rotate(90deg)}
details.kps>summary:hover{background:var(--soft);border-radius:12px}
details.kps .kps-body{padding:0 16px 13px;border-top:1px dashed var(--line);margin-top:0;padding-top:9px}
details.kps .kps-h{margin-bottom:6px}
.kps ol{margin:0;padding-left:19px}
.kps li{font-size:12px;line-height:1.75;margin-bottom:5px;color:var(--ink)}
.kps li:last-child{margin-bottom:0}
.kps li b{color:var(--acc);font-weight:600}
.kps-none{font-size:11.5px;color:var(--todo)}
.rtab{width:100%;border-collapse:collapse;font-size:11.5px;font-variant-numeric:tabular-nums}
.rtab th{text-align:right;font-weight:600;color:var(--dim);font-size:10.5px;padding:6px 7px;border-bottom:1px solid var(--line);background:var(--soft);white-space:nowrap}
.rtab th:first-child,.rtab td:first-child{text-align:left}
.rtab td{text-align:right;padding:6px 7px;border-bottom:1px dashed var(--line);white-space:nowrap}
.rtab tr:last-child td{border-bottom:none}
.rtab .up{color:var(--acc);font-weight:600}
.rtab .down{color:var(--ok);font-weight:600}
.rtab .flat{color:var(--dim)}
.rtab.wrap td{white-space:normal;line-height:1.6;text-align:left}
.rtab.wrap th{white-space:normal}
.ann{font-size:11.5px;color:var(--dim);margin-top:6px;line-height:1.68;border-left:2px solid var(--line);padding-left:9px}
.ann b{color:var(--ink);font-weight:600}
.kpi-2{font-size:10.5px;color:var(--todo);font-variant-numeric:tabular-nums;margin-top:1px}
.kpi-2 i{font-style:normal;color:var(--dim);margin-left:3px}
.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:13px;align-items:start}
.chart{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;box-shadow:0 1px 3px rgba(20,30,50,.04);overflow:hidden}
.chart.wide{grid-column:1/-1}
.chart-hd{font-size:12.5px;font-weight:600;margin-bottom:4px;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.chart-hd::before{content:"";display:inline-block;width:3px;height:11px;background:var(--acc2);border-radius:2px}
.chart-tag{font-size:10px;font-weight:400;color:var(--warn);background:#fdf3e3;border-radius:9px;padding:1px 7px}
.chart svg{display:block;width:100%;height:auto;cursor:zoom-in}
.chart .cap{font-size:10.5px;color:var(--dim);margin-top:4px;line-height:1.5}
.note{font-size:12px;background:var(--soft);border-left:3px solid var(--acc2);padding:10px 13px;border-radius:0 8px 8px 0;margin-top:12px;line-height:1.75}
.qtab{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;font-size:12px}
.qtab th{width:112px;text-align:left;background:var(--soft);color:var(--dim);font-weight:600;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top;white-space:nowrap}
.qtab td{padding:9px 12px;border-bottom:1px solid var(--line);line-height:1.7}
.qtab tr:last-child th,.qtab tr:last-child td{border-bottom:none}
.log{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:6px 14px}
.log-item{padding:10px 0;border-bottom:1px dashed var(--line);display:flex;gap:14px;align-items:flex-start}
.log-item:last-child{border-bottom:none}
.log-d{font-size:11.5px;font-weight:600;color:var(--acc2);font-variant-numeric:tabular-nums;white-space:nowrap;min-width:78px}
.log-w{font-size:10.5px;color:var(--todo);white-space:nowrap;min-width:52px}
.log-t{font-size:11.5px;color:var(--ink);line-height:1.65;flex:1}
.log-t b{color:var(--acc)}
details.all-log{margin-top:10px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px}
details.all-log summary{font-size:12px;font-weight:600;cursor:pointer;color:var(--acc2)}
.foot{margin-top:26px;padding-top:12px;border-top:2px solid var(--line);font-size:11px;color:var(--todo);display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap}
#zoom{display:none;position:fixed;inset:0;background:rgba(20,30,50,.55);z-index:99999;padding:24px;overflow:auto}
#zoom.on{display:block}
#zoom .zbox{max-width:1400px;margin:0 auto;background:#fff;border-radius:12px;padding:14px}
#zoom svg{width:100%;height:auto;cursor:zoom-out}
#zoom .zhint{font-size:11px;color:var(--dim);margin-bottom:8px}
/* SVG 悬停读数：黑色竖线 + 数值浮层（三张周报页共用） */
svg.cv{cursor:crosshair}
#chartTip{position:fixed;z-index:99998;display:none;pointer-events:none;background:#fff;
  border:1px solid var(--line);border-radius:8px;box-shadow:0 4px 14px rgba(20,30,50,.16);
  padding:7px 10px;font-size:11.5px;color:var(--ink);line-height:1.65;max-width:240px}
#chartTip .tt-d{font-weight:700;color:var(--acc2);margin-bottom:3px}
#chartTip .tt-r{white-space:nowrap}
#chartTip .tt-c{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;vertical-align:middle}
@media(max-width:1200px){.dash{grid-template-columns:1fr}}
@media(max-width:700px){.chart-grid{grid-template-columns:1fr}.kpis,.kpis.k3{grid-template-columns:repeat(2,1fr)}nav.tabs{margin-left:0}}
</style>
</head>
<body>
<header class="top"><h1>__H1__</h1><span class="sub">__SUB__</span>
<nav class="tabs"><a href="drewry-weekly.html" class="__ON_DR__">Drewry周报</a><a href="alphaliner-weekly.html" class="__ON_AL__">Alphaliner周报</a><a href="sse-weekly.html" class="__ON_SSE__">SSE周报</a><a href="cosco-dashboard.html" class="back">返回主看板</a></nav></header>
<div class="wrap">
"""

TAIL = """</div>
<div id="zoom" onclick="closeZoom(event)"><div class="zbox"><div class="zhint">双击图形放大 · 点击空白处或按 Esc 关闭</div><div id="zbody"></div></div></div>
<script>
document.addEventListener('click',function(e){
  var g=e.target.closest?e.target.closest('.lg'):null;
  if(!g)return;
  var cid=g.getAttribute('data-chart'),k=g.getAttribute('data-k');
  var svg=document.getElementById(cid);if(!svg)return;
  svg.querySelectorAll('[data-s="'+cid+'-'+k+'"]').forEach(function(el){
    el.style.display=(el.style.display==='none')?'':'none';});
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
    document.getElementById('zbody').innerHTML='';}
}
document.addEventListener('keydown',function(e){
  if(e.key==='Escape')document.getElementById('zoom').classList.remove('on');});
/* 左侧垂直菜单：滚动高亮当前来源（三张周报页共用） */
(function(){var as=[].slice.call(document.querySelectorAll(".vside .vlink[href^='#']"));
function upd(){var y=window.scrollY+130,i0=0;
  as.forEach(function(a,i){var el=document.querySelector(a.getAttribute("href"));
    if(el&&el.offsetTop<=y)i0=i;});
  as.forEach(function(a,i){a.classList.toggle("on",i===i0);});}
window.addEventListener("scroll",upd,{passive:true});upd();})();
/* SVG 悬停读数：黑色竖线定位最近数据点，浮层显示该日期各序列数值 */
(function(){
  var tip=document.createElement('div');tip.id='chartTip';document.body.appendChild(tip);
  var cache=new WeakMap(),layer=null,cur=null;
  function pickText(el){
    var txt=el.getAttribute('data-tt');
    if(!txt){
      var t=el.querySelector('title');
      if(!t)return '';
      txt=t.textContent;
      el.setAttribute('data-tt',txt);   /* 转存文本，供放大图克隆后继续读数 */
      t.textContent='';                 /* 清空原生 tooltip 来源 */
    }
    return txt;
  }
  function data(svg){
    if(cache.has(svg))return cache.get(svg);
    var out=[];
    var root=svg.querySelector(':scope > title');
    if(root){svg.setAttribute('aria-label',root.textContent);root.textContent='';}
    svg.querySelectorAll('circle[data-s]').forEach(function(c){
      var txt=pickText(c);if(!txt)return;
      var a=txt.split(' · ');
      out.push({x:parseFloat(c.getAttribute('cx')),d:a[0],lab:a.slice(1).join(' · '),c:c.getAttribute('fill')});
    });
    if(!out.length){
      svg.querySelectorAll('rect[data-s]').forEach(function(r){
        var txt=pickText(r);if(!txt)return;
        var a=txt.split(' · ');
        out.push({x:parseFloat(r.getAttribute('x'))+parseFloat(r.getAttribute('width'))/2,
                  d:a[0],lab:a.slice(1).join(' · '),c:r.getAttribute('fill')});
      });
    }
    cache.set(svg,out);return out;
  }
  document.addEventListener('mousemove',function(ev){
    var svg=ev.target&&ev.target.closest?ev.target.closest('svg.cv'):null;
    if(!svg){if(layer){layer.remove();layer=null;cur=null;}tip.style.display='none';return;}
    var arr=data(svg);if(!arr.length){tip.style.display='none';return;}
    var pt=svg.createSVGPoint();pt.x=ev.clientX;pt.y=ev.clientY;
    var m=svg.getScreenCTM();if(!m)return;
    var x=pt.matrixTransform(m.inverse()).x,best=arr[0],bd=1e9;
    for(var i=0;i<arr.length;i++){var dd=Math.abs(arr[i].x-x);if(dd<bd){bd=dd;best=arr[i];}}
    if(cur!==svg||!layer){
      if(layer)layer.remove();
      layer=document.createElementNS('http://www.w3.org/2000/svg','g');
      layer.setAttribute('pointer-events','none');
      var first=svg.querySelector('path[data-s],rect[data-s]');
      if(first)svg.insertBefore(layer,first);else svg.appendChild(layer);
      cur=svg;
    }
    while(layer.firstChild)layer.removeChild(layer.firstChild);
    var vb=svg.viewBox.baseVal;
    var ln=document.createElementNS('http://www.w3.org/2000/svg','line');
    ln.setAttribute('x1',best.x.toFixed(1));ln.setAttribute('x2',best.x.toFixed(1));
    ln.setAttribute('y1','30');ln.setAttribute('y2',String(vb.height-26));
    ln.setAttribute('stroke','#111');ln.setAttribute('stroke-width','1');
    ln.setAttribute('stroke-dasharray','4 3');ln.setAttribute('opacity','.75');
    layer.appendChild(ln);
    var rows=arr.filter(function(p){return Math.abs(p.x-best.x)<0.7;});
    tip.innerHTML='<div class="tt-d">'+best.d+'</div>'+rows.map(function(p){
      return '<div class="tt-r"><i class="tt-c" style="background:'+p.c+'"></i>'+p.lab+'</div>';
    }).join('');
    tip.style.display='block';
    var L=ev.clientX+14,T=ev.clientY-12;
    if(L+240>window.innerWidth)L=ev.clientX-250;
    if(T+120>window.innerHeight)T=ev.clientY-120;
    tip.style.left=L+'px';tip.style.top=T+'px';
  });
})();
</script>
</body></html>"""


# 同步按钮已并入页面顶部的锚点导航行（最右侧），此处只保留脚本
AL_SYNC_BLOCK = """<script>
const AL_SYNC_URL = (localStorage.getItem('alSyncUrl') || 'http://127.0.0.1:8765/sync');
/* 服务端写的是本机磁盘 html：file:// 或本机静态服务才能 reload 到新页面；
   Cloudflare 线上副本 reload 后仍是旧版本，只能提示需推送后才生效。 */
const AL_IS_LOCAL = (location.protocol === 'file:' ||
                     /^(127\\.0\\.0\\.1|localhost)$/.test(location.hostname));
function alSetStatus(text, cls){
  const el = document.getElementById('al-status'); if(!el) return;
  el.textContent = text || ''; el.className = 'al-status' + (cls ? ' ' + cls : ''); el.title = text || '';
}
/* reload 会清空状态行，用 sessionStorage 把结果带过一次刷新 */
document.addEventListener('DOMContentLoaded', function(){
  try{
    const s = sessionStorage.getItem('alSyncResult');
    if(s){ sessionStorage.removeItem('alSyncResult'); const o = JSON.parse(s); alSetStatus(o.text, o.cls || 'ok'); }
  }catch(e){}
});
async function syncAlphaliner(btn){
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = '同步中…';
  alSetStatus('抓取 Alphaliner PublicTop100 → 写 xlsx → 只重建本页 → 三项校验…');
  try{
    const r = await fetch(AL_SYNC_URL, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const j = await r.json();
    if(!j.ok){
      const err = new Error(j.error || ('HTTP ' + r.status));
      err.stage = j.stage; err.partial = j.partial;
      throw err;
    }
    const g = j.global, c = j.cosco, pd = j.publish_date || (j.fetched_at || '').slice(0, 10);
    const gg = j.global_row || {}, cc = j.cosco_row || {};
    const act = (gg.action === 'appended' || cc.action === 'appended') ? '新增' : '覆盖';
    const ck = j.checks || {};
    const bad = ck.checks ? Object.keys(ck.checks).filter(function(k){ return !ck.checks[k].ok; })
                            .map(function(k){ return ck.checks[k].detail; }) : [];
    const ckTxt = (ck.all_passed === false) ? ('校验未通过：' + (bad.join('；') || '结果缺失'))
                                            : '校验 3/3 通过';
    const rd = j.render || {};
    const pages = (rd.pages || ['alphaliner-weekly.html']).join(',');
    const status = pd + ' · 全球 ' + (g.active_teu/1e4).toFixed(1) + ' 万TEU／中远 ' +
        (c.total_teu/1e4).toFixed(1) + ' 万TEU（订单 ' + c.order_pct + '%）· ' + act +
        '「全球」第 ' + (gg.row || '?') + ' 行、「COSCO」第 ' + (cc.row || '?') + ' 行｜' +
        ckTxt + '｜仅重建 ' + pages +
        (AL_IS_LOCAL ? '，页面即将刷新' : '；当前为线上副本，本机数据与本地页面已更新，线上需推送后才生效');
    const cls = (ck.all_passed === false) ? 'err' : 'ok';
    alSetStatus(status, cls);
    btn.textContent = '已同步 ' + pd.slice(5);
    btn.title = '写入「全球」第 ' + (gg.row || '?') + ' 行、「COSCO」第 ' + (cc.row || '?') + ' 行；' +
        '耗时 ' + j.elapsed_ms + 'ms；备份 ' + (j.backup || '—');
    if(AL_IS_LOCAL){
      try{ sessionStorage.setItem('alSyncResult', JSON.stringify({text: status, cls: cls})); }catch(e){}
      setTimeout(function(){ location.reload(); }, 1400);
    }
  }catch(e){
    let msg;
    if(/Failed to fetch|NetworkError|load failed/i.test(e.message || '')){
      msg = '未连接本地服务：请先运行 python src/alphaliner_server.py（默认 127.0.0.1:8765）';
    }else if(/锁文件/.test(e.message || '')){
      msg = '请先关闭 Excel 中的「中远海控_Alphaliner周报数据.xlsx」，再点同步';
    }else if(e.partial && e.partial.written){
      msg = '数据已写入（' + (e.partial.publish_date || '当日') + '），但「' +
            (e.stage || '后续') + '」阶段失败：' + e.message + '；请检查后重试';
    }else{
      msg = '同步失败' + (e.stage ? '［' + e.stage + '］' : '') + '：' + e.message;
    }
    alSetStatus(msg, 'err'); btn.textContent = '未连接';
    btn.title = '请先在本机启动服务：cd cosco-shipping && python src/alphaliner_server.py';
  }finally{
    btn.disabled = false;
    setTimeout(function(){ btn.textContent = old; }, 9000);
  }
}
</script>
"""


def shell(title, h1, sub, active, body):
    css = (CSS.replace("__TITLE__", esc(title)).replace("__H1__", esc(h1))
           .replace("__SUB__", esc(sub))
           .replace("__ON_DR__", "on" if active == "dr" else "")
           .replace("__ON_AL__", "on" if active == "al" else "")
           .replace("__ON_SSE__", "on" if active == "sse" else ""))
    return css + body + TAIL


def vside(title, items, extra=""):
    """左侧垂直菜单：items = [(href, 徽标字符, 名称, 副标题), ...]。"""
    links = "".join(
        f'<a class="vlink" href="{href}"><span class="di">{ch}</span>'
        f'<span>{name}<small>{sub}</small></span></a>'
        for href, ch, name, sub in items)
    back = ('<a class="vlink back" href="cosco-dashboard.html">'
            '<span class="di">←</span><span>返回主看板</span></a>')
    return f'<aside class="vside"><h3>{esc(title)}</h3>{links}{extra}{back}</aside>'


def vlayout(side, main):
    """左侧粘性菜单 + 右侧全宽内容区。"""
    return '<div class="vlayout">' + side + '<main class="vmain">' + main + '</main></div>'


def kpi_cards(items):
    """items: (name, value, unit, delta, is_pct_point, spark_svg, source, color)"""
    out = []
    for name, val, unit, delta, is_pt, sp, src, col in items:
        dtxt = f"{delta:+.2f}pct" if is_pt else f"{delta:+.2f}%"
        cls = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        out.append(
            f'<div class="kpi"><div class="kpi-l">{esc(name)}</div>'
            f'<div class="kpi-v">{esc(val)}<small>{esc(unit)}</small></div>'
            f'<div class="kpi-c {cls}">{dtxt}<span> 较年初</span></div>'
            f'<div class="kpi-s">{sp}</div><div class="kpi-d">{esc(src)}</div></div>')
    return '<div class="kpis">' + "".join(out) + "</div>"


def section(n, title, sub, inner):
    return (f'<section class="sec"><div class="sec-hd"><span class="sec-n">{n}</span>'
            f'<h2>{esc(title)}</h2><span class="sec-sub">{esc(sub)}</span></div>'
            + inner + "</section>")


def _emph(s):
    """要点文本的轻量排版：**强调** → 加粗；$金额 / 百分比 / 比例自动加粗。"""
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(\$[\d,]+(?:\.\d+)?)", r"<b>\1</b>", s)
    s = re.sub(r"([−+-]?\d+(?:\.\d+)?%)", r"<b>\1</b>", s)
    s = re.sub(r"(\d+/\d+)(?![\d%])", r"<b>\1</b>", s)
    return s


def blk(bid, badge, title, sub, meta, inner):
    """三大来源分块的标题条：徽章 + 中文名 + 英文/口径 + 右侧数据截止。"""
    return (f'<section class="blk" id="{bid}"><div class="blk-hd">'
            f'<span class="blk-badge">{esc(badge)}</span><h2>{esc(title)}</h2>'
            f'<span class="blk-sub">{esc(sub)}</span>'
            f'<div class="blk-meta">{meta}</div></div>{inner}</section>')


def kps_block(heading, an, fallback=""):
    """本期要点卡：标题来自官方原文，要点由 drewry_ingest.py 落库。

    默认折叠为 details（摘要行显示期次+标题），点击展开完整要点，
    以降低每张卡片的纵向占用，适配 2×2 并排布局。
    """
    if not an or not an.get("points"):
        if not fallback:
            return ""
        return (f'<div class="kps"><div class="kps-body" style="border-top:none">'
                f'<div class="kps-h">{esc(heading)}<em>官方要点未录入</em></div>'
                f'<div class="kps-none">{fallback}</div></div></div>')
    t = an.get("title") or ""
    items = "".join(f"<li>{_emph(p)}</li>" for p in an["points"])
    return (f'<details class="kps"><summary>'
            f'<span class="kps-h">{esc(heading)}<em>{esc(t)}</em></span></summary>'
            f'<div class="kps-body"><ol>{items}</ol></div></details>')


def kpi2(items, cls=""):
    """三行式 KPI 卡：值 / 周环比（着色）/ 年内（灰）。items 为 dict 列表。

    cls 可传 "k3" 等，用于局部改变栅格列数（窄卡放 sparkline 会压住第三行文字）。
    """
    out = []
    for it in items:
        out.append(
            f'<div class="kpi"><div class="kpi-l">{esc(it["name"])}</div>'
            f'<div class="kpi-v">{esc(it["v"])}<small>{esc(it["unit"])}</small></div>'
            f'<div class="kpi-c {it.get("cls", "")}">{it.get("d1", "—")}</div>'
            f'<div class="kpi-2">{it.get("d2", "")}</div>'
            f'<div class="kpi-s">{it.get("spark", "")}</div>'
            f'<div class="kpi-d">{esc(it.get("src", ""))}</div></div>')
    return '<div class="kpis%s">' % (" " + cls if cls else "") + "".join(out) + "</div>"


def route_table(title, head, rows, note="", wide=True):
    """分航线当期对照表。rows: (名称, 本期, 上期, 周环比%, 年内低, 年内高)。"""
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    body = []
    for name, cur, prev, wow, lo, hi in rows:
        if wow is None:
            cls, ar, wtxt = "flat", "", "—"
        else:
            cls = "up" if wow > 0 else ("down" if wow < 0 else "flat")
            ar = "▲" if wow > 0 else ("▼" if wow < 0 else "")
            wtxt = f"{wow:+.2f}%"
        body.append(f"<tr><td>{esc(name)}</td><td>{cur}</td><td>{prev}</td>"
                    f'<td class="{cls}">{wtxt}'
                    f'<span style="font-size:9px;margin-left:2px">{ar}</span></td>'
                    f"<td>{lo}</td><td>{hi}</td></tr>")
    n = f'<div class="ann">{note}</div>' if note else ""
    return (f'<div class="chart{" wide" if wide else ""}">'
            f'<div class="chart-hd">{esc(title)}</div>'
            f'<table class="rtab"><tr>{h}</tr>{"".join(body)}</table>{n}</div>')


def grid_table(title, head, rows, note="", wide=True, wrap=False):
    """通用对照表（单元格内容需自行格式化，可含 HTML 着色）。

    wrap=True 时单元格允许折行（长文本列用，如周报正文摘要）。
    """
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    n = f'<div class="ann">{note}</div>' if note else ""
    return (f'<div class="chart{" wide" if wide else ""}">'
            f'<div class="chart-hd">{esc(title)}</div>'
            f'<table class="rtab{" wrap" if wrap else ""}"><tr>{h}</tr>{body}</table>{n}</div>')


def chart(title, svg, cap="", wide=False, tag=""):
    t = f'<span class="chart-tag">{esc(tag)}</span>' if tag else ""
    c = f'<div class="cap">{cap}</div>' if cap else ""
    return (f'<div class="chart{" wide" if wide else ""}">'
            f'<div class="chart-hd">{esc(title)}{t}</div>{svg}{c}</div>')


def chart_ann(title, svg, ann="", cap="", wide=False, tag=""):
    """带数据注解的图卡：cap 为操作提示，ann 为随数据自动生成的解读。"""
    t = f'<span class="chart-tag">{esc(tag)}</span>' if tag else ""
    c = f'<div class="cap">{cap}</div>' if cap else ""
    a = f'<div class="ann">{ann}</div>' if ann else ""
    return (f'<div class="chart{" wide" if wide else ""}">'
            f'<div class="chart-hd">{esc(title)}{t}</div>{svg}{c}{a}</div>')


def quality_table(rows):
    return ('<table class="qtab">' + "".join(
        f'<tr><th>{esc(k)}</th><td>{v}</td></tr>' for k, v in rows) + "</table>")


def chg(seq):
    a = next((v for v in seq if v is not None), None)
    b = next((v for v in reversed(seq) if v is not None), None)
    return (b / a - 1) * 100 if a and b else 0.0


def last(seq):
    return next((v for v in reversed(seq) if v is not None), 0)


def col(rows, k):
    return [r[k] for r in rows]


# ---------------------------------------------------------------- 页面 A
# ---------------------------------------------------------------- 页面 A
# 三大来源 → 三块，严格按 WCI / IACI / CST 从上到下排布
DR_ROUTES = [("rtm", "上海-鹿特丹", C_BLUE),
             ("lax", "上海-洛杉矶", C_RED),
             ("goa", "上海-热那亚", C_AMBER),
             ("nyc", "上海-纽约", C_PURPLE)]
DR_IROUTES = [("r_np", "上海-尼赫鲁港", C_RED),
              ("r_tp", "上海-丹绒帕拉帕斯", C_BLUE),
              ("r_sg", "上海-新加坡", C_TEAL),
              ("r_yk", "上海-横滨", C_AMBER)]
DR_IBACK = [("r_jk", "雅加达-上海", C_RED),
            ("r_bs", "釜山-上海", C_BLUE),
            ("r_hc", "胡志明市-上海", C_TEAL),
            ("r_yy", "横滨-上海", C_AMBER)]
W_USD = lambda v: f"{v:,.0f}"
W_PCT = lambda v: f"{v:.1f}%"
W_N = lambda v: f"{v:,.0f}"

# 图例用短名（4 条序列 + 560 宽卡片，全名会挤到换行），表格与注解仍用全名
DR_SHORT = {"上海-鹿特丹": "上鹿", "上海-洛杉矶": "上洛",
            "上海-热那亚": "上热", "上海-纽约": "上纽",
            "上海-尼赫鲁港": "上尼赫鲁", "上海-丹绒帕拉帕斯": "上丹绒",
            "上海-新加坡": "上新加坡", "上海-横滨": "上横滨",
            "雅加达-上海": "雅-上", "釜山-上海": "釜-上",
            "胡志明市-上海": "胡-上", "横滨-上海": "横-上"}


def sh(n):
    return DR_SHORT.get(n, n)


def _row_at(dr, d):
    return next((r for r in reversed(dr) if r["d"] == d), dr[-1])


def _mark(s, unit=""):
    """KPI 用的周环比文本与配色类。"""
    if s is None or s.get("wow") is None:
        return "—", "flat"
    w = s["wow"]
    cls = "up" if w > 0 else ("down" if w < 0 else "flat")
    return f"周环比 {w:+.2f}%", cls


def build_drewry():
    dr = read_drewry()
    an = read_analysis()
    ds = col(dr, "d")            # WCI/IACI 侧日期（跨表统一键）
    dsc = [r["d_cst"] or r["d"] for r in dr]   # CST 自己的发布日（周五，比 WCI 晚 1 天）
    c = lambda k: col(dr, k)
    n_period = len(dr)

    # ---------------- 统计基元（每块只算自己的字段，互不引用 ----------------
    sw, si, sb = stats(dr, "wci"), stats(dr, "iaci"), stats(dr, "blank")
    so, spl, sbn = stats(dr, "ontime"), stats(dr, "planned"), stats(dr, "blank_n")
    rs = {k: stats(dr, k) for k, _, _ in DR_ROUTES}
    irs = {k: stats(dr, k) for k, _, _ in DR_IROUTES + DR_IBACK}

    # ================================================================ ① WCI
    def kpi_wci():
        items = [dict(name="WCI 综合指数", v=f'{sw["v"]:,.0f}', unit="USD/FEU",
                      d1=f'周环比 {sw["wow"]:+.2f}%',
                      cls="up" if sw["wow"] > 0 else "down",
                      d2=f'<i>年内</i> {chg(c("wci")):+.2f}%',
                      spark=spark(c("wci"), C_RED),
                      src=f'Drewry · {sw["d"]}', color=C_RED)]
        for k, nm, cc in DR_ROUTES[:3] + [("nyc", "上海-纽约", C_PURPLE)]:
            s = rs[k]
            if not s:
                continue
            items.append(dict(name=nm, v=f'{s["v"]:,.0f}', unit="USD/FEU",
                              d1=f'周环比 {s["wow"]:+.2f}%' if s["wow"] is not None else "—",
                              cls="up" if (s["wow"] or 0) > 0 else ("down" if (s["wow"] or 0) < 0 else "flat"),
                              d2=f'<i>年内</i> {chg(c(k)):+.2f}%',
                              spark=spark(c(k), cc),
                              src=f'Drewry · {s["d"]}', color=cc))
        return kpi2(items)

    w1 = multi_svg("w1", "WCI 综合指数", "USD/FEU",
                   [("WCI 综合", ds, c("wci"))], [C_RED], W_USD, W=780, hl=True)
    w2 = multi_svg("w2", "四条上海出口航线", "USD/FEU",
                   [(sh(nm), ds, c(k)) for k, nm, _ in DR_ROUTES],
                   [cc for _, _, cc in DR_ROUTES], W_USD, W=780, hl=True)
    w3 = bar_svg("w3", "WCI 综合周环比", "%", ds, c("wow"), W=560)

    sign, nstr = _streak(c("wci"))
    w1_ann = (f'本期 <b>{sw["v"]:,.0f}</b>（周环比 <b>{sw["wow"]:+.2f}%</b>，官方概述取整 '
              f'<b>{sw["wow"]:.0f}%</b>）' +
              (f'，已连续 <b>{nstr} 周{_dir_word(sign)}</b>' if nstr >= 2 else "") +
              f'；年内高点 <b>{sw["hi"]:,.0f}</b>（{sw["hi_d"]}）、低点 <b>{sw["lo"]:,.0f}</b>'
              f'（{sw["lo_d"]}），当前距高点 <b>{pct(sw["hi"], sw["v"]):+.2f}%</b>。')

    wows = [(nm, rs[k]["wow"]) for k, nm, _ in DR_ROUTES if rs[k] and rs[k]["wow"] is not None]
    downs = [x for x in wows if x[1] < 0]
    ups = [x for x in wows if x[1] > 0]
    flats = [x for x in wows if x[1] == 0]
    worst = min(wows, key=lambda x: x[1]) if wows else None
    best = max(wows, key=lambda x: x[1]) if wows else None
    all_down = bool(wows) and len(downs) == len(wows)
    w2_ann = (f'四条航线 <b>{len(downs)}</b> 跌 / <b>{len(flats)}</b> 平 / <b>{len(ups)}</b> 涨；'
              + (f'跌幅最大 <b>{worst[0]} {worst[1]:+.2f}%</b>，' if worst else "")
              + (f'相对最强 <b>{best[0]} {best[1]:+.2f}%</b>。' if best else "")
              + ("全线同向——" if all_down else "方向分化——")
              + ("综合指数由四条航线加权，单周方向由多数航线决定。" if all_down
                 else "此时综合指数的方向取决于权重，不能由单条航线外推。"))

    bw = [(r["d"], r["wow"]) for r in dr if r["wow"] is not None]
    bmax = max(bw, key=lambda x: x[1]) if bw else None
    bmin = min(bw, key=lambda x: x[1]) if bw else None
    w3_ann = (f'本期 <b>{sw["wow"]:+.2f}%</b>；{n_period} 期中单周最大涨幅 '
              f'<b>{bmax[1]:+.2f}%</b>（{bmax[0]}）、最大跌幅 <b>{bmin[1]:+.2f}%</b>（{bmin[0]}）；'
              f'上涨 <b>{sum(1 for _, v in bw if v > 0)}</b> 周、下跌 '
              f'<b>{sum(1 for _, v in bw if v < 0)}</b> 周。') if bmax and bmin else ""

    wtab = route_table(
        "分航线当期对照（USD/FEU）",
        ["航线", "本期", "上期", "周环比", "年内低", "年内高"],
        [("WCI 综合", f'{sw["v"]:,.0f}', f'{sw["v0"]:,.0f}', sw["wow"],
          f'{sw["lo"]:,.0f}', f'{sw["hi"]:,.0f}')]
        + [(nm, f'{rs[k]["v"]:,.0f}', f'{rs[k]["v0"]:,.0f}', rs[k]["wow"],
            f'{rs[k]["lo"]:,.0f}', f'{rs[k]["hi"]:,.0f}')
           for k, nm, _ in DR_ROUTES if rs[k]],
        note="「周环比」按本表相邻两期实际值计算，与官方取整表述可能有 ±0.5pct 差异；"
             "「年内」区间取本表已录期次的最小/最大值。", wide=True)

    blk_wci = blk("wci", "WCI", "世界集装箱运价指数",
                  "World Container Index · 8 条东西向主干航线加权即期价",
                  f'数据截止 <b>{sw["d"]}</b><br>Drewry 官网 · 每周四',
                  kps_block(f'本期要点 · {sw["d"]}', an.get("WCI"),
                            "本期官方要点尚未录入，下图注解仅由本表数据计算。")
                  + kpi_wci()
                  + '<div class="chart-grid">'
                  + chart_ann("WCI 综合指数", w1, w1_ann,
                              f"{n_period} 期 · 末年橙圈为最新一期 · 点击图例隐藏序列、双击放大",
                              wide=True)
                  + chart_ann("四条上海出口航线", w2, w2_ann,
                              "上鹿/上洛/上热/上纽 · 美线与欧地线量级差 1–2 倍，共用 y 轴",
                              wide=True)
                  + chart_ann("WCI 综合周环比", w3, w3_ann, "正值红、负值绿", wide=True)
                  + wtab
                  + "</div>"
                  + '<div class="note">WCI 是<b>即期运价</b>（USD/FEU，不含长协与码头操作费），'
                    f'每周四发布，覆盖 8 条东西向主干航线；本表只录 4 条上海出口航线，'
                    f'另 4 条回程方向（鹿/洛/热/纽→上海）未录入。'
                    f'<b>WCI 反映的是即期市场，中远海控收入仍有相当比例来自长协，'
                    f'因此它是运价的先行指标而非收入直接映射。</b></div>')

    # ================================================================ ② IACI
    def kpi_iaci():
        items = [dict(name="IACI 综合", v=f'{si["v"]:,.0f}', unit="USD/40ft",
                      d1=f'周环比 {si["wow"]:+.2f}%',
                      cls="up" if si["wow"] > 0 else "down",
                      d2=f'<i>年内</i> {chg(c("iaci")):+.2f}%',
                      spark=spark(c("iaci"), C_RED),
                      src=f'Drewry · {si["d"]}', color=C_RED)]
        for k, nm, cc in [DR_IROUTES[0], DR_IROUTES[2], DR_IBACK[0]]:
            s = irs[k]
            if not s:
                continue
            items.append(dict(name=nm, v=f'{s["v"]:,.0f}', unit="USD/40ft",
                              d1=f'周环比 {s["wow"]:+.2f}%' if s["wow"] is not None else "—",
                              cls="up" if (s["wow"] or 0) > 0 else ("down" if (s["wow"] or 0) < 0 else "flat"),
                              d2=f'<i>年内</i> {chg(c(k)):+.2f}%',
                              spark=spark(c(k), cc),
                              src=f'Drewry · {s["d"]}', color=cc))
        return kpi2(items)

    dr_q = [x for x in dr if x["iaci"] is not None]
    dr_w = [x for x in dr if x["iaci_wow"] is not None]
    dr_ir = [x for x in dr if x["r_np"] is not None]
    qd = [x["d"] for x in dr_q]
    rd = [x["d"] for x in dr_ir]
    i1 = multi_svg("i1", "IACI 综合指数", "USD/40ft",
                   [("IACI 综合", qd, [x["iaci"] for x in dr_q])], [C_RED], W_USD,
                   W=560, hl=True)
    i2 = bar_svg("i2", "IACI 综合周环比", "%",
                 [x["d"] for x in dr_w], [x["iaci_wow"] for x in dr_w], W=560)
    i3 = multi_svg("i3", "上海出发四条航线", "USD/40ft",
                   [(sh(nm), rd, [x[k] for x in dr_ir]) for k, nm, _ in DR_IROUTES],
                   [cc for _, _, cc in DR_IROUTES], W_USD, W=560, hl=True)
    i4 = multi_svg("i4", "回程 / 区域内四条航线", "USD/40ft",
                   [(sh(nm), rd, [x[k] for x in dr_ir]) for k, nm, _ in DR_IBACK],
                   [cc for _, _, cc in DR_IBACK], W_USD, W=560, hl=True)

    iw = [(nm, irs[k]["wow"]) for k, nm, _ in DR_IROUTES + DR_IBACK
          if irs[k] and irs[k]["wow"] is not None]
    iworst = min(iw, key=lambda x: x[1]) if iw else None
    ibest = max(iw, key=lambda x: x[1]) if iw else None
    i1_ann = (f'本期 <b>{si["v"]:,.0f}</b>（{si["v"] - si["v0"]:+,.0f} 美元 / '
              f'<b>{si["wow"]:+.2f}%</b>）；'
              f'年内高点 <b>{si["hi"]:,.0f}</b>（{si["hi_d"]}）、低点 <b>{si["lo"]:,.0f}</b>'
              f'（{si["lo_d"]}），当前距高点 <b>{pct(si["hi"], si["v"]):+.2f}%</b>。')
    i2_ann = (f'本期 <b>{si["wow"]:+.2f}%</b>；{len(dr_w)} 期中上涨 '
              f'<b>{sum(1 for x in dr_w if x["iaci_wow"] > 0)}</b> 期、下跌 '
              f'<b>{sum(1 for x in dr_w if x["iaci_wow"] < 0)}</b> 期；'
              f'单期最大涨幅 <b>{max(x["iaci_wow"] for x in dr_w):+.2f}%</b>、'
              f'最大跌幅 <b>{min(x["iaci_wow"] for x in dr_w):+.2f}%</b>。') if dr_w else ""
    i3_ann = (f'上海出发四条中 <b>{sum(1 for k, _, _ in DR_IROUTES if irs[k]["wow"] < 0)}</b> 条下跌；'
              + (f'跌幅最大 <b>{iworst[0]} {iworst[1]:+.2f}%</b>。' if iworst else "")
              + f'该组量级 {min(irs[k]["lo"] for k, _, _ in DR_IROUTES):,.0f}–'
                f'{max(irs[k]["hi"] for k, _, _ in DR_IROUTES):,.0f} 美元/40ft，是中国出口方向的报价中枢。')
    i4_ann = (f'回程线绝对量级仅 <b>{min(irs[k]["lo"] for k, _, _ in DR_IBACK):,.0f}–'
              f'{max(irs[k]["hi"] for k, _, _ in DR_IBACK):,.0f}</b> 美元/40ft；'
              + (f'本期 <b>{ibest[0]} {ibest[1]:+.2f}%</b> 涨幅看似最大，' if ibest and ibest[1] > 5 else "")
              + '<b>但基数只有百美元级，单周波动可轻易超过 ±15%，方向意义远弱于上海出口航线，'
                '不可用作运价趋势判断。</b>')

    itab = route_table(
        "8 条分航线当期对照（USD/40ft）",
        ["航线", "本期", "上期", "周环比", "年内低", "年内高"],
        [(nm, f'{irs[k]["v"]:,.0f}', f'{irs[k]["v0"]:,.0f}', irs[k]["wow"],
          f'{irs[k]["lo"]:,.0f}', f'{irs[k]["hi"]:,.0f}')
         for k, nm, _ in DR_IROUTES + DR_IBACK if irs[k]],
        note="上海出发组按本期运价降序，回程组单列（量级相差一个数量级以上，混排会压平回程）。")

    blk_iaci = blk("iaci", "IACI", "亚洲区内集装箱运价指数",
                   "Intra-Asia Container Index · 18 条航线专属指数 + 综合",
                   f'数据截止 <b>{si["d"]}</b><br>Drewry 官网 · 每周四',
                   kps_block(f'本期要点 · {si["d"]}', an.get("IACI"),
                             "本期官方要点尚未录入，下图注解仅由本表数据计算。")
                   + kpi_iaci()
                  + '<div class="chart-grid">'
                  + chart_ann("IACI 综合指数", i1, i1_ann,
                              f"{len(dr_q)} 期 · 官方 2026-01-02 起周更 · 末年橙圈为最新一期")
                  + chart_ann("IACI 综合周环比", i2, i2_ann, "正值红、负值绿")
                  + chart_ann("上海出发四条航线", i3, i3_ann, "中国出口方向")
                  + chart_ann("回程 / 区域内四条航线", i4, i4_ann, "回程方向 · 与左图分列因量级相差一个数量级")
                  + itab
                  + "</div>"
                   + '<div class="note">IACI 由 <b>18 条航线专属指数 + 1 个综合指数</b>构成，'
                     '单位美元/40ft，不含起运港与目的港码头操作费（THC），2026-01-02 起由双周改为周更。'
                     f'本表录综合 {len(dr_q)} 期、分航线 {len(dr_ir)} 期（8 条），'
                     '<b>并非 18 条全覆盖，因此不可由这 8 条反算综合指数</b>。'
                     'IACI 只覆盖亚洲区内航线，与 WCI 的东西向干线是两套独立市场，'
                     '不构成同一运价的短长期关系。</div>')

    # ================================================================ ③ CST
    cst_row = _row_at(dr, sb["d"]) if sb else dr[-1]
    win = cst_row.get("window") or ""
    # CST 每周五发布，比 WCI/IACI（周四）晚一天；表内按周四日期归并，页面须显示真实截止日
    cst_asof = ((an.get("CST") or {}).get("asof")
                or next((x for x in reversed(dsc) if x), ds[-1]))

    def kpi_cst():
        items = []
        if sb:
            items.append(dict(name="未来五周停航率", v=f'{sb["v"]:.0f}', unit="%",
                              d1=f'较上期 {(sb["v"] - sb["v0"]):+.1f}pct' if sb["v0"] is not None else "—",
                              cls="up" if sb["v"] > sb["v0"] else "down",
                              d2=f'<i>年内</i> {sb["lo"]:.0f}–{sb["hi"]:.0f}%',
                              spark=spark(c("blank"), C_TEAL),
                              src=f'Drewry CST · {cst_asof}', color=C_TEAL))
        if spl:
            items.append(dict(name="计划航次", v=f'{spl["v"]:,.0f}', unit="班",
                              d1=f'较上期 {spl["v"] - spl["v0"]:+,.0f} 班' if spl["v0"] else "—",
                              cls="up" if spl["v"] > spl["v0"] else "down",
                              d2=f'<i>覆盖</i> {esc(win)}',
                              spark=spark(c("planned"), C_GRAY),
                              src=f'Drewry CST · {cst_asof}', color=C_GRAY))
        if sbn:
            items.append(dict(name="停航航次", v=f'{sbn["v"]:,.0f}', unit="班",
                              d1=f'较上期 {sbn["v"] - sbn["v0"]:+,.0f} 班' if sbn["v0"] else "—",
                              cls="up" if sbn["v"] > sbn["v0"] else "down",
                              d2=f'<i>实际比值</i> {sbn["v"] / spl["v"] * 100:.2f}%' if spl else "",
                              spark=spark(c("blank_n"), C_AMBER),
                              src=f'Drewry CST · {cst_asof}', color=C_AMBER))
        if so:
            items.append(dict(name="按计划营运率", v=f'{so["v"]:.0f}', unit="%",
                              d1=f'较上期 {(so["v"] - so["v0"]):+.1f}pct' if so["v0"] is not None else "—",
                              cls="up" if so["v"] > so["v0"] else "down",
                              d2=f'<i>年内</i> {so["lo"]:.0f}–{so["hi"]:.0f}%',
                              spark=spark(c("ontime"), C_BLUE),
                              src=f'Drewry CST · {cst_asof}', color=C_BLUE))
        return kpi2(items)

    c1 = multi_svg("c1", "未来五周停航率", "%",
                   [("停航率", dsc, c("blank"))], [C_RED], W_PCT, W=560, hl=True)
    c2 = multi_svg("c2", "未来五周停航航次", "班",
                   [("停航航次", dsc, c("blank_n"))], [C_AMBER], W_N, W=560, hl=True,
                   zero=True)
    c3 = multi_svg("c3", "分航线取消量占比", "%",
                   [("跨太平洋东行", dsc, c("blank_tp")),
                    ("亚洲-北欧/地中海", dsc, c("blank_ae")),
                    ("跨大西洋", dsc, c("blank_ta"))],
                   [C_RED, C_TEAL, C_AMBER], W_PCT, W=780, hl=True)

    s_tp, s_ae, s_ta = stats(dr, "blank_tp"), stats(dr, "blank_ae"), stats(dr, "blank_ta")
    d_blank = (sb["v"] - sb["v0"]) if (sb and sb["v0"] is not None) else 0
    c1_ann = (f'未来五周停航率 <b>{sb["v"]:.0f}%</b>（上期 {sb["v0"]:.0f}%，'
              f'<b>{d_blank:+.0f}pct</b>）；年内区间 <b>{sb["lo"]:.0f}–{sb["hi"]:.0f}%</b>，'
              f'高点在 {sb["hi_d"]}。对应按计划营运率 <b>{so["v"]:.0f}%</b>'
              f'（上期 {so["v0"]:.0f}%）——两者互为补数，'
              + ("停航率上升说明船司在主动收紧运力托价。" if d_blank > 0 else
                 ("停航率持平，运力投放节奏未变。" if d_blank == 0 else
                  "停航率下降说明运力在回归航线。"))
              ) if sb and so else ""
    c2_ann = (f'计划 <b>{spl["v"]:,.0f}</b> 班、停航 <b>{sbn["v"]:,.0f}</b> 班，'
              f'实际比值 <b>{sbn["v"] / spl["v"] * 100:.2f}%</b>（表内取整 {sb["v"]:.0f}%）；'
              f'停航航次年内 <b>{sbn["lo"]:,.0f}–{sbn["hi"]:,.0f}</b> 班，而计划航次稳定在 '
              f'<b>{spl["lo"]:,.0f}–{spl["hi"]:,.0f}</b> 班——'
              f'<b>计划航次几乎不动，停航航次才是波动来源，故只画停航航次</b>。') if spl and sbn and sb else ""
    c3_ann = (f'本期结构：亚欧 <b>{s_ae["v"]:.0f}%</b>（上期 {s_ae["v0"]:.0f}%）、'
              f'跨太 <b>{s_tp["v"]:.0f}%</b>（上期 {s_tp["v0"]:.0f}%）、'
              f'跨大西洋 <b>{s_ta["v"]:.0f}%</b>（上期 {s_ta["v0"]:.0f}%）；'
              f'跨大西洋占比年内区间 <b>{s_ta["lo"]:.0f}–{s_ta["hi"]:.0f}%</b>。') if s_tp and s_ae and s_ta else ""

    blk_cst = blk("cst", "CST", "取消航次追踪",
                  "Cancelled Sailings Tracker · 未来五周东西向主干航线",
                  f'覆盖周 <b>{esc(win)}</b> · 数据截止 <b>{cst_asof}</b>'
                  f'<br>Drewry 官网 · 每周五（比 WCI/IACI 晚 1 天）',
                  kps_block(f'本期要点 · {cst_asof}', an.get("CST"),
                            "本期官方要点尚未录入，下图注解仅由本表数据计算。")
                  + kpi_cst()
                  + '<div class="chart-grid">'
                  + chart_ann("未来五周停航率", c1, c1_ann,
                              f"覆盖 {win} · 停航率＝停航÷计划，为前瞻值")
                  + chart_ann("未来五周停航航次", c2, c2_ann, "停航航次为波动来源")
                  + chart_ann("分航线取消量占比", c3, c3_ann, "三项合计约 100%", wide=True)
                  + "</div>"
                  + '<div class="note">口径三条必须记住：'
                    '<b>① 停航率统计的是「未来五周」的公告值</b>（本周发布的期次覆盖下一周起的 5 个周次），'
                    '不是当周实际执行率，属<b>前瞻</b>指标；'
                    '② 只统计东西向三大干线（跨太平洋东行、亚欧含地中海、跨大西洋），不含区域内；'
                    '③ L–N 三列是「占取消总量的比例」，不是各航线自身停航率。'
                    '本页已按上期结论复核：停航率与 WCI 周环比在本表样本内一阶差分相关仅 '
                    '<b>r≈−0.13</b>，<b>停航是需求走弱后的结果，而非运价上涨的原因</b>。</div>')

    # ================================================================ ④ RST
    # Red Sea Diversion Tracker：唯一的「绕航退潮」周度定量来源，双周更新
    rst = read_rst()
    if rst:
        rs = []
        for x in rst:
            tot = (x["suez"] or 0) + (x["cape"] or 0)
            rs.append(dict(d=x["d"], suez=x["suez"], cape=x["cape"],
                           total=tot or None,
                           share=(x["suez"] / tot * 100) if tot else None,
                           ae_share=x["ae_share"]))
        rd = [x["d"] for x in rs]
        ss, sc = stats(rs, "suez"), stats(rs, "cape")
        st, ssh = stats(rs, "total"), stats(rs, "share")
        sa = next((x for x in reversed(rs) if x["ae_share"] is not None), None)
        r_asof = (an.get("RST") or {}).get("asof") or ss["d"]

        def kpi_rst():
            return kpi2([
                dict(name="经苏伊士", v=f'{ss["v"]:,.0f}', unit="艘/周",
                     d1=f'较上周 {ss["v"] - ss["v0"]:+.0f} 艘',
                     cls="up" if ss["v"] > ss["v0"] else "down",
                     d2=f'<i>年内</i> {ss["lo"]:,.0f}–{ss["hi"]:,.0f}',
                     spark=spark([x["suez"] for x in rs], C_RED),
                     src=f'Drewry RST · {r_asof}', color=C_RED),
                dict(name="经好望角", v=f'{sc["v"]:,.0f}', unit="艘/周",
                     d1=f'较上周 {sc["v"] - sc["v0"]:+.0f} 艘',
                     cls="up" if sc["v"] > sc["v0"] else "down",
                     d2=f'<i>年内</i> {sc["lo"]:,.0f}–{sc["hi"]:,.0f}',
                     spark=spark([x["cape"] for x in rs], C_BLUE),
                     src=f'Drewry RST · {r_asof}', color=C_BLUE),
                dict(name="苏伊士通行占比", v=f'{ssh["v"]:.1f}', unit="%",
                     d1=f'较上周 {ssh["v"] - ssh["v0"]:+.1f}pct',
                     cls="up" if ssh["v"] > ssh["v0"] else "down",
                     d2=f'<i>年内</i> {ssh["lo"]:.1f}–{ssh["hi"]:.1f}%',
                     spark=spark([x["share"] for x in rs], C_TEAL),
                     src="苏伊士÷（苏伊士+好望角）· 按艘数", color=C_TEAL),
                dict(name="亚欧运力经苏伊士", v=f'{sa["ae_share"]:.0f}' if sa else "—",
                     unit="%",
                     d1="官方仅给出当期值", cls="flat",
                     d2="<i>口径</i> 运力份额，非艘数",
                     spark="", src=f'Drewry RST · {sa["d"] if sa else r_asof}',
                     color=C_PURPLE),
            ])

        r1 = multi_svg("r1", "经苏伊士 vs 经好望角（周度通航艘数）", "艘/周",
                       [("经苏伊士", rd, [x["suez"] for x in rs]),
                        ("经好望角", rd, [x["cape"] for x in rs])],
                       [C_RED, C_BLUE], W_N, W=780, hl=True, zero=True)
        r2 = multi_svg("r2", "苏伊士通行占比", "%",
                       [("苏伊士占比", rd, [x["share"] for x in rs])],
                       [C_TEAL], W_PCT, W=560, hl=True)
        r3 = multi_svg("r3", "两线合计通行艘数", "艘/周",
                       [("合计", rd, [x["total"] for x in rs])],
                       [C_GRAY], W_N, W=560, hl=True, zero=True)

        dip = min(rs, key=lambda x: x["total"] or 9e9)
        r1_ann = (f'本期经苏伊士 <b>{ss["v"]:,.0f}</b> 艘、经好望角 <b>{sc["v"]:,.0f}</b> 艘，'
                  f'合计 <b>{st["v"]:,.0f}</b> 艘；苏伊士较上周 '
                  f'<b>{ss["v"] - ss["v0"]:+.0f}</b> 艘，占两线合计 '
                  f'<b>{ssh["v"]:.1f}%</b>。官方另称同比 <b>+130%</b>。')
        r2_ann = (f'苏伊士通行占比 <b>{ssh["v"]:.1f}%</b>（上周 {ssh["v0"]:.1f}%，'
                  f'<b>{ssh["v"] - ssh["v0"]:+.1f}pct</b>）；年内区间 '
                  f'<b>{ssh["lo"]:.1f}–{ssh["hi"]:.1f}%</b>，低点 {ssh["lo_d"]}、高点 {ssh["hi_d"]}。'
                  + (f'占比已从低点回升 <b>{ssh["v"] - ssh["lo"]:.1f}pct</b>，'
                     '即绕航退潮在数量层面已经发生。' if ssh["v"] > ssh["lo"] else ""))
        r3_ann = (f'两线合计 <b>{st["v"]:,.0f}</b> 艘/周，年内区间 <b>{st["lo"]:,.0f}–{st["hi"]:,.0f}</b>。'
                  f'该值的<b>稳定性</b>决定前两张图的可比性：合计应大致恒定，'
                  f'只是货量在两线之间重新分配。'
                  f'异常周 <b>{dip["d"]}</b> 合计仅 <b>{dip["total"]:,.0f}</b> 艘（下一周即回补），'
                  f'疑节假日短周或数据缺报，<b>勿读作航线切换</b>。')

        # 最近 9 周逐周对照
        def _d_cell(p):
            if p is None:
                return '<span class="flat">—</span>'
            cls = "up" if p > 0 else ("down" if p < 0 else "flat")
            ar = "▲" if p > 0 else ("▼" if p < 0 else "")
            return f'<span class="{cls}">{p:+.1f}%{ar}</span>'

        tail = rs[-9:]
        rows_t = []
        for i, x in enumerate(tail):
            prev = tail[i - 1]["suez"] if i > 0 else None
            wow = (x["suez"] / prev - 1) * 100 if prev else None
            rows_t.append([esc(x["d"]), f'{x["suez"]:,.0f}', f'{x["cape"]:,.0f}',
                           f'{x["total"]:,.0f}', f'{x["share"]:.1f}%', _d_cell(wow)])
        rtab = grid_table("最近 9 周逐周对照",
                          ["周结束日", "经苏伊士", "经好望角", "合计", "苏伊士占比", "苏伊士周环比"],
                          rows_t, wide=True,
                          note="「经苏伊士周环比」按本表相邻两周计算；官方仅公布当期艘数与同比，不逐期给出周环比。")

        blk_rst = blk("rst", "RST", "红海绕航追踪",
                      "Red Sea Diversion Tracker · 苏伊士 vs 好望角 集装箱船通行",
                      f'数据截止 <b>{r_asof}</b>（周结束）<br>Drewry 官网 · 每两周周二',
                      kps_block(f'本期要点 · {r_asof}', an.get("RST"),
                                "本期官方要点尚未录入，下图注解仅由本表数据计算。")
                      + kpi_rst()
                      + '<div class="chart-grid">'
                      + chart_ann("经苏伊士 vs 经好望角", r1, r1_ann,
                                  "同年 57 周 · 末年橙圈为最新一期 · 两线均按艘数，同一 y 轴可比",
                                  wide=True)
                      + chart_ann("苏伊士通行占比", r2, r2_ann, "按艘数计算，非运力口径")
                      + chart_ann("两线合计通行艘数", r3, r3_ann, "稳定性校验：合计应大致恒定")
                      + rtab
                      + "</div>"
                      + '<div class="note">三条口径必须分清：'
                        '<b>① 本块的艘数是「全集装箱船每周通行量」</b>（苏伊士双向 / 绕好望角），'
                        '由官网图表数字化得到，精度约 ±3 艘，非官方数值；'
                        '<b>②「苏伊士通行占比」= 苏伊士 ÷（苏伊士＋好望角），按艘数</b>，'
                        f'本期为 <b>{ssh["v"]:.0f}%</b>；'
                        '<b>③ 官方「亚欧运力经苏伊士 60%」是运力份额口径</b>，'
                        '与 ② 的分母不同，<b>不可用 ② 反推 ③</b>。'
                        '研究含义：绕航等于把有效运力锁在长航线上，复航则是把运力还给市场——'
                        '这是运价中枢的供给侧变量，<b>与停航率（船司主动调控）是两套独立机制</b>。</div>')

    # ================================================================ 组装
    side = vside("四大追踪来源", [
        ("#wci", "W", "WCI", "世界集装箱运价"),
        ("#iaci", "I", "IACI", "亚洲区内运价"),
        ("#cst", "C", "CST", "取消航次追踪"),
        ("#rst", "R", "RST", "红海绕航追踪"),
    ])

    foot = (f'<div class="foot"><span>数据来源：Drewry World Container Index / Intra-Asia Container '
            f'Index / Cancelled Sailings Tracker / Red Sea Diversion Tracker 官网；'
            f'本期要点为官方原文提炼，RST 艘数为图表数字化。</span>'
            f'<span>更新：WCI 与 IACI 每周四、CST 每周五、RST 每两周周二；'
            f'本页由 build_weekly_pages.py 从 xlsx 重建，非实时。</span></div>')
    body = vlayout(side, blk_wci + blk_iaci + blk_cst + blk_rst + foot)
    doc = shell("Drewry 周报 · 运价与停航", "Drewry 周报 · 运价与停航",
                f"WCI / IACI / CST / RST 四大来源分块 · 2026 年内 {n_period} 期 · 单一 xlsx 数据源",
                "dr", body)
    open(OUT_DR, "w", encoding="utf-8").write(doc)
    return OUT_DR, doc, n_period, sum(len((an.get(k) or {}).get("points") or [])
                                     for k in ("WCI", "IACI", "CST", "RST"))

# ---------------------------------------------------------------- 页面 B
# ---------------------------------------------------------------- 页面 B
def _chg_txt(s, unit="%", what="较上期"):
    """stats() → (文案, 配色类)。"""
    if not s or s.get("wow") is None:
        return "—", "flat"
    w = s["wow"]
    cls = "up" if w > 0 else ("down" if w < 0 else "flat")
    return f"{what} {w:+.2f}{unit}", cls


def al_points_global(al):
    """全球运力块的「本期要点」。

    Alphaliner 官网只给数字、**没有任何文字洞察**，因此这一块的分析全部由本表数据生成，
    每期自动刷新，不依赖人工撰写。返回 (标题, [要点])。
    """
    g = [r for r in al if r["fleet"]]
    if len(g) < 3:
        return "", []
    c, p = g[-1], g[0]
    ytd = pct(p["fleet"], c["fleet"])
    tp = [(r["d"], r["tp"]) for r in g if r["tp"]]
    fe = [(r["d"], r["fe"]) for r in g if r["fe"]]
    ta = [(r["d"], r["ta"]) for r in g if r["ta"]]
    tp_max = max(tp, key=lambda x: x[1]) if tp else None
    fe_max = max(fe, key=lambda x: x[1]) if fe else None
    ta_max = max(ta, key=lambda x: x[1]) if ta else None
    per = p["per_ship"] or 0
    ratio = (c["fully"] / c["fleet"] * 100) if c.get("fully") else None
    gap = (c["fleet"] - c["fully"]) if c.get("fully") else None
    gaps = [(_ord(g[i + 1]["d"]) - _ord(g[i]["d"])) for i in range(len(g) - 1)]
    med = sorted(gaps)[len(gaps) // 2]

    title = ("全球运力 %.1f 万TEU 创年内新高，三大干线仅跨大西洋收缩" % (c["fleet"] / 1e4))
    pts = [
        "全球在运营运力 %.1f 万TEU（年初至今 %+.2f%%），本期即年内峰值；在运营船舶 %s 艘（%+.2f%%）。"
        % (c["fleet"] / 1e4, ytd, f"{c['ships']:,.0f}", pct(p["ships"], c["ships"])),
        "单船平均 %.0f TEU/艘（年初 %.0f）：运力增速快于艘数增速，增量主要来自大型化而非单纯加船。"
        % (c["fleet"] / c["ships"], per),
        "全集装箱船 %.1f 万TEU（%+.2f%%），占全部在运营运力的 %.1f%%；差额 %.1f 万TEU 为非全集装箱船。"
        % (c["fully"] / 1e4, pct(p["fully"], c["fully"]), ratio, gap / 1e4),
        "干线投放分化：跨太平洋 %.1f 万TEU/周（%+.1f%%，峰 %.1f @%s）、远东-欧洲 %.1f 万（%+.1f%%，峰 %.1f @%s）、"
        "跨大西洋 %.1f 万（%+.1f%%，峰值即年初 %.1f）——亚欧与跨太在加投，跨大西洋在撤线。"
        % (c["tp"] / 1e4, pct(p["tp"], c["tp"]), tp_max[1] / 1e4, tp_max[0],
           c["fe"] / 1e4, pct(p["fe"], c["fe"]), fe_max[1] / 1e4, fe_max[0],
           c["ta"] / 1e4, pct(p["ta"], c["ta"]), ta_max[1] / 1e4),
        "快照为**不定期**更新（间隔 %d–%d 天，中位 %d 天），x 轴按真实日期定位；"
        "不宜把它当等距周序列做差分或求周环比均值。" % (min(gaps), max(gaps), med),
    ]
    return title, pts


def al_points_cosco(al):
    """COSCO 块的「本期要点」——同样由数据生成，重点落在份额与订单这两个前瞻量上。"""
    g = [r for r in al if r["cosco"] and r["fleet"]]
    if len(g) < 3:
        return "", []
    c, p = g[-1], g[0]
    sh = [(r["d"], r["share"]) for r in g if r["share"] is not None]
    sh_lo, sh_hi = min(sh, key=lambda x: x[1]), max(sh, key=lambda x: x[1])
    orders = [(r["d"], r["order_pct"]) for r in g if r["order_pct"] is not None]
    op_hi = max(orders, key=lambda x: x[1]) if orders else None
    g_ytd = pct(p["fleet"], c["fleet"])
    c_ytd = pct(p["cosco"], c["cosco"])

    title = ("份额稳在 %.2f%%，订单占现有运力 %.1f%%——2027 年后运力增速大概率反超行业"
             % (c["share"], c["order_pct"] or 0))
    pts = [
        "中远运力 %.1f 万TEU（%+.2f%%）、%s 艘，全球排名第 %d；增速慢于行业的 %+.2f%%，"
        "份额由 %.2f%% 微降至 %.2f%%。"
        % (c["cosco"] / 1e4, c_ytd, f"{c['cosco_ships']:,.0f}", c["rank"] or 0,
           g_ytd, p["share"], c["share"]),
        "份额年内区间 %.2f%%（%s）～%.2f%%（%s），振幅不足 %.2f 个百分点——"
        "相对位置基本锁定，行业扩张主要由头部与他司推动，而非中远。"
        % (sh_lo[1], sh_lo[0], sh_hi[1], sh_hi[0], sh_hi[1] - sh_lo[1]),
        "自有 %.1f 万 + 租入 %.1f 万TEU，租入占比 %.1f%%（年初 %.1f%%），运力结构一年未变。"
        % (c["owned"] / 1e4, (c["chart"] or 0) / 1e4, c["chart_pct"] or 0, p["chart_pct"] or 0),
        "手持订单 %.1f 万TEU／%s 艘，占现有运力 %.1f%%（年内峰值 %.1f%% @%s），"
        "在头部承运人里属高位。"
        % ((c["order"] or 0) / 1e4, f"{c['order_ships']:,.0f}", c["order_pct"] or 0,
           op_hi[1] if op_hi else 0, op_hi[0] if op_hi else "—"),
        "含义：若订单按期交付，运力两年内将增长约 %.0f%%，远高于行业 %.1f%% 的年增速——"
        "份额大概率上行，但同时压低行业运价中枢。**这是本页唯一具前瞻性的信号。**"
        % (c["order_pct"] or 0, g_ytd),
    ]
    return title, pts


def build_alphaliner():
    al = read_alphaliner()
    an = read_analysis(AL_XLSX)
    ds = col(al, "d")
    c = lambda k: col(al, k)
    W_TEU = lambda v: f"{v:,.1f}"
    W_PCT = lambda v: f"{v:.2f}%"
    W_N = lambda v: f"{v:,.0f}"
    wan = lambda seq: [v / 10000 if v is not None else None for v in seq]

    fleet_w, fully_w = wan(c("fleet")), wan(c("fully"))
    cosco_w, owned_w, chart_w, order_w = (wan(c("cosco")), wan(c("owned")),
                                          wan(c("chart")), wan(c("order")))
    ta_w, tp_w, fe_w = wan(c("ta")), wan(c("tp")), wan(c("fe"))
    idx_fleet = [v / fleet_w[0] * 100 if v else None for v in fleet_w]
    idx_cosco = [v / cosco_w[0] * 100 if v else None for v in cosco_w]

    sg = stats(al, "fleet")
    ss = stats(al, "ships")
    sf = stats(al, "fully")
    sp = stats(al, "per_ship")
    sta, stp, sfe = stats(al, "ta"), stats(al, "tp"), stats(al, "fe")
    sc = stats(al, "cosco")
    ssh, sord, sop = stats(al, "share"), stats(al, "order"), stats(al, "order_pct")
    scop = stats(al, "chart_pct")
    cp0 = c("chart_pct")[0]        # 年初租入占比

    # 本期要点：优先用 xlsx 里同期的官方/人工版本，否则用数据生成版
    def _kps(src):
        a = an.get(src)
        gen = al_points_global(al) if src == "全球" else al_points_cosco(al)
        if a and a.get("asof") == ds[-1] and a.get("points"):
            return a
        return dict(asof=ds[-1], title=gen[0], points=gen[1])

    # ============================================================ ① 全球
    def kpi_g():
        items = [
            dict(name="全球在运营运力", v=f'{sg["v"] / 1e4:,.1f}', unit="万TEU",
                 d1=_chg_txt(sg)[0], cls=_chg_txt(sg)[1],
                 d2=f'<i>年内</i> {chg(c("fleet")):+.2f}%',
                 spark=spark(fleet_w, C_TEAL), src=f'Alphaliner · {sg["d"]}', color=C_TEAL),
            dict(name="全集装箱船运力", v=f'{sf["v"] / 1e4:,.1f}', unit="万TEU",
                 d1=_chg_txt(sf)[0], cls=_chg_txt(sf)[1],
                 d2=f'<i>年内</i> {chg(c("fully")):+.2f}%',
                 spark=spark(fully_w, C_BLUE), src=f'Alphaliner · {sf["d"]}', color=C_BLUE),
            dict(name="全球在运营船舶", v=f'{ss["v"]:,.0f}', unit="艘",
                 d1=_chg_txt(ss)[0], cls=_chg_txt(ss)[1],
                 d2=f'<i>年内</i> {chg(c("ships")):+.2f}%',
                 spark=spark(c("ships"), C_GRAY), src=f'Alphaliner · {ss["d"]}', color=C_GRAY),
            dict(name="单船平均运力", v=f'{sp["v"]:,.0f}', unit="TEU/艘",
                 d1=_chg_txt(sp)[0], cls=_chg_txt(sp)[1],
                 d2=f'<i>年内</i> {chg(c("per_ship")):+.2f}%',
                 spark=spark(c("per_ship"), C_AMBER), src=f'Alphaliner · {sp["d"]}', color=C_AMBER),
        ]
        return kpi2(items)

    g1 = multi_svg("g1", "全球船队运力", "万TEU",
                   [("全部在运营", ds, fleet_w), ("全集装箱船", ds, fully_w)],
                   [C_TEAL, C_BLUE], W_TEU, W=560, hl=True)
    g2 = multi_svg("g2", "三大干线周运力投放", "万TEU",
                   [("跨太平洋", ds, tp_w), ("远东-欧洲", ds, fe_w), ("跨大西洋", ds, ta_w)],
                   [C_RED, C_BLUE, C_GRAY], W_TEU, W=560, hl=True)
    g3 = multi_svg("g3", "单船平均运力（大型化）", "TEU/艘",
                   [("单船平均", ds, c("per_ship"))], [C_AMBER], W_N, W=560, hl=True)
    g4 = multi_svg("g4", "在运营船舶数与全集装箱船", "艘",
                   [("在运营船舶", ds, c("ships")), ("其中全集装箱船", ds, c("fully_ships"))],
                   [C_GRAY, C_BLUE], W_N, W=560, hl=True)

    share_gap = (sf["v"] / sg["v"] * 100) if sg["v"] else 0
    g1_ann = (f'本期全部在运营 <b>{sg["v"] / 1e4:,.1f}</b> 万TEU、全集装箱船 '
              f'<b>{sf["v"] / 1e4:,.1f}</b> 万TEU，后者占比 <b>{share_gap:.1f}%</b>，'
              f'差额 <b>{(sg["v"] - sf["v"]) / 1e4:,.1f}</b> 万TEU 为非全集装箱船。'
              f'两条线几乎平行，说明运力增长几乎全部来自集装箱船本身。')
    g2_ann = (f'跨太平洋 <b>{stp["v"] / 1e4:,.1f}</b> 万TEU/周（{_chg_txt(stp)[0]}）、'
              f'远东-欧洲 <b>{sfe["v"] / 1e4:,.1f}</b> 万（{_chg_txt(sfe)[0]}）、'
              f'跨大西洋 <b>{sta["v"] / 1e4:,.1f}</b> 万（{_chg_txt(sta)[0]}）。'
              f'年内跨太 <b>{pct(c("tp")[0], stp["v"]):+.1f}%</b>、欧线 '
              f'<b>{pct(c("fe")[0], sfe["v"]):+.1f}%</b>、大西洋 '
              f'<b>{pct(c("ta")[0], sta["v"]):+.1f}%</b>——'
              f'唯一在撤线的是跨大西洋。')
    g3_ann = (f'单船平均由 <b>{c("per_ship")[0]:,.0f}</b> 升至 <b>{sp["v"]:,.0f}</b> TEU/艘'
              f'（<b>{chg(c("per_ship")):+.2f}%</b>），同期运力 <b>{chg(c("fleet")):+.2f}%</b>、'
              f'艘数 <b>{chg(c("ships")):+.2f}%</b>；'
              f'运力增速高于艘数增速约 '
              f'<b>{chg(c("fleet")) - chg(c("ships")):+.2f}pct</b>，'
              f'这部分差额就是大型化的贡献。<b>判断供给压力要看运力而非艘数。</b>')
    sfs = stats(al, "fully_ships")
    g4_ann = (f'本期在运营船舶 <b>{ss["v"]:,.0f}</b> 艘，其中全集装箱船 <b>{sfs["v"]:,.0f}</b> 艘、'
              f'占 <b>{sfs["v"] / ss["v"] * 100:.1f}%</b>，其余 <b>{ss["v"] - sfs["v"]:,.0f}</b> 艘'
              f'为非全集装箱船。年内艘数 '
              f'<b>{chg(c("ships")):+.2f}%</b>、全集装箱船 '
              f'<b>{chg(c("fully_ships")):+.2f}%</b>——'
              f'集装箱船的增长略快于总体，说明新增运力集中在集装箱板块。')

    tab_g = grid_table(
        "最近 9 期快照",
        ["发布时间", "在运营运力(万TEU)", "在运营船舶(艘)", "单船平均(TEU)",
         "跨太平洋(万TEU/周)", "远东-欧洲", "跨大西洋"],
        [[esc(r["d"]),
          f'{r["fleet"] / 1e4:,.1f}' if r["fleet"] else "—",
          f'{r["ships"]:,.0f}' if r["ships"] else "—",
          f'{r["per_ship"]:,.0f}' if r["per_ship"] else "—",
          f'{r["tp"] / 1e4:,.1f}' if r["tp"] else "—",
          f'{r["fe"] / 1e4:,.1f}' if r["fe"] else "—",
          f'{r["ta"] / 1e4:,.1f}' if r["ta"] else "—"]
         for r in al[-9:]],
        note="快照不定期，行间间隔 4–28 天，相邻行不可直接当作「一周」比较。")

    blk_g = blk("global", "GLOBAL", "全球船队",
                "Alphaliner PublicTop100 · Global figures + Regional Trades",
                f'数据截止 <b>{sg["d"]}</b><br>官网每日更新 · 本页每周六取一次快照',
                kps_block(f'本期要点 · {sg["d"]}', _kps("全球"),
                          "本期要点生成失败，下图注解仍可用。")
                + kpi_g()
                + '<div class="chart-grid">'
                + chart_ann("全球船队运力", g1, g1_ann,
                            f'{len(al)} 期不定期快照 · 末年橙圈为最新一期')
                + chart_ann("三大干线周运力", g2, g2_ann,
                            "同一 y 轴；跨大西洋量级仅为另两条的 1/4")
                + chart_ann("单船平均运力", g3, g3_ann, "全球运力 ÷ 在运营船舶艘数")
                + chart_ann("在运营船舶数 / 全集装箱船", g4, g4_ann,
                            "艘数口径；两线差额＝非全集装箱船")
                + tab_g
                + "</div>")

    # ============================================================ ② COSCO
    def kpi_c():
        return kpi2([
            dict(name="中远海控运力", v=f'{sc["v"] / 1e4:,.1f}', unit="万TEU",
                 d1=_chg_txt(sc)[0], cls=_chg_txt(sc)[1],
                 d2=f'<i>年内</i> {chg(c("cosco")):+.2f}%',
                 spark=spark(cosco_w, C_RED), src=f'Alphaliner · {sc["d"]}', color=C_RED),
            dict(name="全球份额", v=f'{ssh["v"]:.2f}', unit="%",
                 d1=f'较上期 {ssh["v"] - ssh["v0"]:+.2f}pct',
                 cls="up" if ssh["v"] > ssh["v0"] else "down",
                 d2=f'<i>年内</i> {ssh["lo"]:.2f}–{ssh["hi"]:.2f}%',
                 spark=spark(c("share"), C_PURPLE), src="公司运力 ÷ 全球运力", color=C_PURPLE),
            dict(name="手持订单 / 现有运力", v=f'{sop["v"]:.1f}', unit="%",
                 d1=f'较上期 {sop["v"] - sop["v0"]:+.1f}pct',
                 cls="up" if sop["v"] > sop["v0"] else "down",
                 d2=f'<i>年内峰</i> {sop["hi"]:.1f}%',
                 spark=spark(c("order_pct"), C_GREEN),
                 src=f'Alphaliner · {sop["d"]}', color=C_GREEN),
            dict(name="租入运力占比", v=f'{scop["v"]:.1f}', unit="%",
                 d1=f'较上期 {scop["v"] - scop["v0"]:+.1f}pct',
                 cls="up" if scop["v"] > scop["v0"] else "down",
                 d2=f'<i>年内</i> {scop["lo"]:.1f}–{scop["hi"]:.1f}%',
                 spark=spark(c("chart_pct"), C_TEAL), src="运力结构", color=C_TEAL),
        ])

    s1 = multi_svg("s1", "中远 vs 全球（年初 = 100）", "指数",
                   [("全球运力", ds, idx_fleet), ("中远海控", ds, idx_cosco)],
                   [C_GRAY, C_RED], lambda v: f"{v:.1f}", W=780, hl=True)
    s2 = multi_svg("s2", "中远全球运力份额", "%",
                   [("全球份额", ds, c("share"))], [C_PURPLE], W_PCT, W=560, hl=True)
    # 手持订单绝对量与「订单/现有运力」本质是同一序列的两种标度（分母仅缓慢变化），
    # 双轴画出来会完全重合，故只画绝对量；比例放在 KPI 与注解里。
    s3 = multi_svg("s3", "手持订单（未交付运力）", "万TEU",
                   [("手持订单", ds, order_w)], [C_GREEN], W_TEU, W=560, hl=True)
    # 自有与租入拆成两张图：两者量级差 1.5 倍，合画时租入的波动会被压平
    s4 = multi_svg("s4", "自有运力", "万TEU",
                   [("自有运力", ds, owned_w)], [C_TEAL], W_TEU, W=560, hl=True)
    s5 = multi_svg("s5", "租入运力", "万TEU",
                   [("租入运力", ds, chart_w)], [C_AMBER], W_TEU, W=560, hl=True)

    s1_ann = (f'年初至今全球 <b>{chg(c("fleet")):+.2f}%</b>、中远 '
              f'<b>{chg(c("cosco")):+.2f}%</b>，公司落后行业 '
              f'<b>{abs(chg(c("cosco")) - chg(c("fleet"))):.2f}pct</b>。'
              f'月末两条线间距即累计跑输幅度：<b>中远这一年是在被行业稀释，而不是扩张。</b>')
    s2_ann = (f'份额 <b>{ssh["v"]:.2f}%</b>（上期 {ssh["v0"]:.2f}%），年内 '
              f'<b>{ssh["lo"]:.2f}–{ssh["hi"]:.2f}%</b>，'
              f'低点 {ssh["lo_d"]}、高点 {ssh["hi_d"]}，振幅仅 '
              f'<b>{ssh["hi"] - ssh["lo"]:.2f}pct</b>。'
              f'<b>份额的稳定性说明公司没有份额战意图，运力投放按自身节奏走。</b>')
    s3_ann = (f'手持订单 <b>{sord["v"] / 1e4:,.1f}</b> 万TEU，占现有运力 '
              f'<b>{sop["v"]:.1f}%</b>（上期 {sop["v0"]:.1f}%，年内峰 {sop["hi"]:.1f}% @{sop["hi_d"]}）。'
              f'两个数字是同一件事的两种标度——分母（现有运力）变化很慢，'
              f'所以绝对量与比例走势一致，<b>图上只画绝对量</b>。'
              f'订单/运力是全球航运最可靠的运力前瞻指标：'
              f'<b>{sop["v"]:.0f}% 意味着交付完成后船队规模接近翻半倍</b>，'
              f'这个量级会同时压低行业运价中枢。')
    sown, scht = stats(al, "owned"), stats(al, "chart")
    s4_ann = (f'自有运力 <b>{sown["v"] / 1e4:,.1f}</b> 万TEU（{_chg_txt(sown)[0]}），'
              f'占公司总运力 <b>{sown["v"] / sc["v"] * 100:.1f}%</b>；年内 '
              f'<b>{chg(c("owned")):+.2f}%</b>，区间 '
              f'<b>{sown["lo"] / 1e4:,.1f}–{sown["hi"] / 1e4:,.1f}</b> 万TEU。'
              f'自有运力是刚性成本端，变化极慢，一年只挪了约 '
              f'<b>{(sown["hi"] - sown["lo"]) / 1e4:,.1f}</b> 万TEU。')
    s5_ann = (f'租入运力 <b>{scht["v"] / 1e4:,.1f}</b> 万TEU（{_chg_txt(scht)[0]}），'
              f'占 <b>{scht["v"] / sc["v"] * 100:.1f}%</b>；年内 '
              f'<b>{chg(c("chart")):+.2f}%</b>，快于自有的 '
              f'<b>{chg(c("owned")):+.2f}%</b>，'
              f'租入占比因此由 <b>{cp0:.1f}%</b> 升到 <b>{scop["v"]:.1f}%</b>。'
              f'<b>租入是弹性成本：运价上行时放大利润，下行时也是最先被退掉的那部分。</b>')

    tab_c = grid_table(
        "最近 9 期快照",
        ["发布时间", "总运力(万TEU)", "艘数", "全球份额", "自有(万TEU)",
         "租入(万TEU)", "租入占比", "订单(万TEU)", "订单/现有"],
        [[esc(r["d"]),
          f'{r["cosco"] / 1e4:,.1f}' if r["cosco"] else "—",
          f'{r["cosco_ships"]:,.0f}' if r["cosco_ships"] else "—",
          f'{r["share"]:.2f}%' if r["share"] else "—",
          f'{r["owned"] / 1e4:,.1f}' if r["owned"] else "—",
          f'{r["chart"] / 1e4:,.1f}' if r["chart"] else "—",
          f'{r["chart_pct"]:.1f}%' if r["chart_pct"] else "—",
          f'{r["order"] / 1e4:,.1f}' if r["order"] else "—",
          f'{r["order_pct"]:.1f}%' if r["order_pct"] else "—"]
         for r in al[-9:]],
        note="「—」为源表该期缺列或串列（2026-06-17、2026-10-02 整段缺拆分；"
             "2026-06-25 租入列少一位数，已按拆分不自洽剔除）。")

    blk_c = blk("cosco", "COSCO", "中远海控",
                "Alphaliner TOP100 · COSCO Group 一行",
                f'数据截止 <b>{sc["d"]}</b><br>全球排名第 {int(al[-1]["rank"] or 0)} · 官网每日更新',
                kps_block(f'本期要点 · {sc["d"]}', _kps("COSCO"),
                          "本期要点生成失败，下图注解仍可用。")
                + kpi_c()
                + '<div class="chart-grid">'
                + chart_ann("中远 vs 全球（年初=100）", s1, s1_ann,
                            "两条线间距＝累计相对强弱", wide=True)
                + chart_ann("全球运力份额", s2, s2_ann, "公司运力 ÷ 全球运力，非源表 #REF! 列")
                + chart_ann("手持订单（未交付运力）", s3, s3_ann,
                            "单轴绝对量；比例见 KPI 卡「手持订单 / 现有运力」")
                + chart_ann("自有运力", s4, s4_ann, "刚性成本端，一年仅微调")
                + chart_ann("租入运力", s5, s5_ann,
                            "弹性成本端 · 2026-06-25 租入列少一位数，该点断线")
                + tab_c
                + "</div>")

    # ============================================================ 组装
    sync_extra = ('<button class="al-sync-btn" id="al-btn" onclick="syncAlphaliner(this)">'
                  '同步 Alphaliner TOP100</button>'
                  '<span class="al-status" id="al-status"></span>')
    side = vside("两大模块", [
        ("#global", "G", "GLOBAL", "全球船队"),
        ("#cosco", "C", "COSCO", "中远海控"),
    ], extra=sync_extra)

    n_gap = sum(1 for r in al if r["owned"] is None)
    foot = (f'<div class="foot"><span>数据来源：Alphaliner PublicTop100（Global figures / '
            f'Regional Trades / TOP100 第 4 行 COSCO Group），官网每日更新，本页每周六取一次快照。</span>'
            f'<span>本页 {len(al)} 期不定期快照；分析要点与图表注解由本表数据生成（官网无文字洞察）。</span></div>')
    body = AL_SYNC_BLOCK + vlayout(side, blk_g + blk_c + foot)
    doc = shell("Alphaliner 周报 · 运力与公司", "Alphaliner 周报 · 运力与公司",
                f"全球船队 / 中远海控 两大模块 · {len(al)} 期快照 · 单一 xlsx 数据源",
                "al", body)
    open(OUT_AL, "w", encoding="utf-8").write(doc)
    return OUT_AL, doc, len(al), (len(_kps("全球")["points"]) + len(_kps("COSCO")["points"]))


# ---------------------------------------------------------------- 页面 C
# SSE（上海航运交易所）：SCFI & CCFI 综合指数（长序列）+ SCFI 分航线（仅当年）
SSE_ROUTES = [("eu",  "欧洲航线",   C_BLUE,   "USD/TEU", "欧线"),
              ("med", "地中海航线", C_TEAL,   "USD/TEU", "地中"),
              ("usw", "美西航线",   C_RED,    "USD/FEU", "美西"),
              ("use", "美东航线",   C_PURPLE, "USD/FEU", "美东"),
              ("pw",  "波斯湾航线", C_AMBER,  "USD/TEU", "波斯")]
SSE_UNIT = {k: u for k, _, _, u, _ in SSE_ROUTES}
SSE_SHORT = {k: s for k, _, _, _, s in SSE_ROUTES}
CCFI_START = "2022-01-01"     # CCFI 2021 年缺 19 期，统一从 2022 年起用


def _pctp(v):
    """源表周环比按小数比例存（0.0051 = 0.51%），统一转百分数。"""
    x = _num(v)
    return None if x is None else x * 100


def _sse_col(h, prefix):
    """列定位：兼容表头里的全/半角括号与空格差异。"""
    def norm(s):
        return s.replace("（", "(").replace("）", ")").replace(" ", "")
    for k, c in h.items():
        if norm(k).startswith(norm(prefix)):
            return c
    raise KeyError("SSE 表缺少列：%s" % prefix)


def read_sse():
    """读 SSE 两张表 → (综合指数序列, 分航线序列)。

    综合表 2021-01-08 起 290 期；分线表只有当年 43 期（2026 年内）。
    两表日期在 2026 段完全对齐，但分线没有历史 → 两块各自成图，不做跨表相减。
    """
    wb = openpyxl.load_workbook(S_XLSX, data_only=True)

    def hdr(ws):
        return {str(ws.cell(1, c).value).strip(): c
                for c in range(1, ws.max_column + 1) if ws.cell(1, c).value}

    w = wb["SCFI&CCFI"]
    h = hdr(w)
    ci = {k: _sse_col(h, k) for k in
          ("SCFI综合指数", "SCFI周环比", "CCFI综合指数", "CCFI周环比", "SCFI/CCFI")}
    idx = []
    for r in range(2, w.max_row + 1):
        d = _d(w.cell(r, 1).value)
        if not d:
            continue
        idx.append(dict(
            d=d,
            scfi=_num(w.cell(r, ci["SCFI综合指数"]).value),
            scfi_wow=_pctp(w.cell(r, ci["SCFI周环比"]).value),
            ccfi=_num(w.cell(r, ci["CCFI综合指数"]).value),
            ccfi_wow=_pctp(w.cell(r, ci["CCFI周环比"]).value),
            ratio=_num(w.cell(r, ci["SCFI/CCFI"]).value)))

    w = wb["SCFI 分线"]
    h = hdr(w)
    ku, kn = _sse_col(h, "舱位利用率"), _sse_col(h, "市场行情简评")
    fl = []
    for r in range(2, w.max_row + 1):
        d = _d(w.cell(r, 1).value)
        if not d:
            continue
        rec = dict(d=d,
                   util=str(w.cell(r, ku).value or "").strip(),
                   note=str(w.cell(r, kn).value or "").strip())
        for k, cn, _, _, _ in SSE_ROUTES:
            rec[k] = _num(w.cell(r, _sse_col(h, cn)).value)
        fl.append(rec)
    return idx, fl


def sse_points_index(idx, cc, i26):
    """综合指数块的本期要点（全部由本表数据生成，每期自动刷新）。"""
    ss, sc = stats(idx, "scfi"), stats(cc, "ccfi")
    rr = [r for r in idx if r["d"] >= CCFI_START and r["ratio"] is not None]
    sr = stats(rr, "ratio")
    if not ss or not sc:
        return "", []
    sign, ns = _streak(col(idx, "scfi"))
    ytd = pct(i26[0]["scfi"], i26[-1]["scfi"])
    c_ytd = pct(next(r["ccfi"] for r in cc if r["d"][:4] == "2026"),
                next(r["ccfi"] for r in reversed(cc) if r["d"][:4] == "2026"))
    gaps = [(_ord(idx[i + 1]["d"]) - _ord(idx[i]["d"])) for i in range(len(idx) - 1)]
    med = sorted(gaps)[len(gaps) // 2]
    diverge = (ss["wow"] or 0) * (sc["wow"] or 0) < 0

    # 本期官方周报未发布 CCFI 时，不得把上期 CCFI / 溢价倍数当作本期结论展示。
    ccfi_missing = idx[-1]["ccfi"] is None
    last_d = idx[-1]["d"]
    title = (("SCFI %.0f 点（%+.2f%%）——本期 CCFI 未发布，长协端数据停留在 %s"
              % (ss["v"], ss["wow"] or 0, sc["d"])) if ccfi_missing else
             ("SCFI %.0f 点（%+.2f%%），即期溢价 %.2f 倍——%s"
              % (ss["v"], ss["wow"] or 0, sr["v"],
                 "即期强于长协" if sr["v"] > 1.5 else "长协托底")))
    pt_ccfi = (
        "**本期（%s）官方周报未发布 CCFI 综合指数**：本表该期 CCFI 综合、CCFI 周环比、"
        "SCFI/CCFI 即期溢价倍数均留空，不以上期值代填。最近一期可用 CCFI 为 "
        "**%s 的 %.2f 点**（%+.2f%%），2026 年内 %+.1f%%；下方 CCFI 图表与 KPI 显示的是"
        "该期数值，不代表本期长协走势。"
        % (last_d, sc["d"], sc["v"], sc["wow"] or 0, c_ytd)
    ) if ccfi_missing else (
        "CCFI 综合 **%.2f 点**（%+.2f%%），2026 年内 **%+.1f%%**；"
        "%s——即期与长协**方向相反**，说明船司在长协端仍在提价/顺延，"
        "而现货端已先行回落，两者价差是利润弹性的来源。"
        % (sc["v"], sc["wow"] or 0, c_ytd, "与 SCFI 背离" if diverge else "与 SCFI 同向")
        if diverge else
        "CCFI 综合 **%.2f 点**（%+.2f%%），2026 年内 **%+.1f%%**；"
        "与 SCFI **同向**，即期与长协同步移动，价差未走阔。"
        % (sc["v"], sc["wow"] or 0, c_ytd)
    )
    pt_ratio = (
        "**SCFI/CCFI 即期溢价本期不计算**（CCFI 缺失）；最近可用值为 %s 的 %.2f 倍"
        "（年内区间 %.2f–%.2f）。>1 表示即期高于长协加权中枢，船司当期收入弹性放大；"
        "<1 则长协托底、即期下行对收入的拖累被削弱。"
        % (sr["d"], sr["v"], sr["lo"], sr["hi"])
    ) if ccfi_missing else (
        "**SCFI/CCFI 即期溢价 %.2f 倍**（年内区间 %.2f–%.2f，均值附近 %.2f）："
        ">1 表示即期高于长协加权中枢，船司当期收入弹性放大；"
        "<1 则长协托底、即期下行对收入的拖累被削弱。"
        % (sr["v"], sr["lo"], sr["hi"], sr["v"])
    )
    pts = [
        "SCFI 综合 **%.2f 点**（周环比 **%+.2f%%**）%s；2026 年内 **%+.1f%%**，"
        "距 2021 年峰值 %.2f 点仍有 **%.1f%%** 空间。"
        % (ss["v"], ss["wow"] or 0,
           "，已连续 %d 周%s" % (ns, _dir_word(sign)) if ns >= 2 else "",
           ytd, ss["hi"], pct(ss["hi"], ss["v"])),
        pt_ccfi,
        pt_ratio,
        "2026 年内 SCFI 高点 **%.0f**（%s）、低点 **%.0f**（%s），当前位于年内区间 "
        "**%.0f%%** 分位——%s。"
        % (max(r["scfi"] for r in i26), max(i26, key=lambda r: r["scfi"])["d"],
           min(r["scfi"] for r in i26), min(i26, key=lambda r: r["scfi"])["d"],
           (ss["v"] - min(r["scfi"] for r in i26))
           / max(1e-9, max(r["scfi"] for r in i26) - min(r["scfi"] for r in i26)) * 100,
           "运价仍处年内高位区" if (ss["v"] - min(r["scfi"] for r in i26))
           / max(1e-9, max(r["scfi"] for r in i26) - min(r["scfi"] for r in i26)) > 0.6
           else "已从年内高位回落"),
        "口径：SCFI 为**即期价**、CCFI 为**长协加权**，两者不可直接比大小；"
        "本表周序列**非严格等距**（春节等假期造成 %d–%d 天间隔，中位 %d 天），"
        "故 x 轴按真实日期定位，且不宜对周环比直接取算术均值。"
        ""
        % (min(gaps), max(gaps), med),
    ]
    return title, pts


def sse_points_routes(fl):
    """分航线块的本期要点：涨跌分布、量级差、舱位利用率分档。"""
    if len(fl) < 3:
        return "", []
    cur, first = fl[-1], fl[0]
    rs = {k: stats(fl, k) for k, _, _, _, _ in SSE_ROUTES}
    wows = [(cn, rs[k]["wow"]) for k, cn, _, _, _ in SSE_ROUTES
            if rs[k] and rs[k]["wow"] is not None]
    downs = [x for x in wows if x[1] < 0]
    ups = [x for x in wows if x[1] > 0]
    best = max(wows, key=lambda x: x[1]) if wows else None
    worst = min(wows, key=lambda x: x[1]) if wows else None
    ytd = {cn: pct(first[k], cur[k]) for k, cn, _, _, _ in SSE_ROUTES}
    util = [r["util"] for r in fl if r["util"]]
    n_t = sum(1 for u in util if u == "紧张")

    title = ("美线年内 +%.0f%% 领涨、欧线仅 +%.0f%%，%d 条航线中 %d 条本周回落"
             % (ytd["美西航线"], ytd["欧洲航线"], len(wows), len(downs)))
    pts = [
        "本周 **%d 涨 / %d 跌**；最强 **%s %+.2f%%**、最弱 **%s %+.2f%%**。"
        % (len(ups), len(downs),
           best[0] if best else "—", best[1] if best else 0,
           worst[0] if worst else "—", worst[1] if worst else 0),
        "年初至今分化极大：**美西 %+.0f%%、美东 %+.0f%%、波斯湾 %+.0f%%**，"
        "而**欧洲仅 %+.0f%%、地中海 %+.0f%%**——增量几乎全部集中在跨太平洋与中东，"
        "欧地线只是小幅修复。"
        % (ytd["美西航线"], ytd["美东航线"], ytd["波斯湾航线"],
           ytd["欧洲航线"], ytd["地中海航线"]),
        "绝对量级：美东 **%.0f** > 美西 **%.0f** > 波斯湾 **%.0f** > 地中海 **%.0f** > "
        "欧洲 **%.0f**（美元/箱）——美线与欧线差 %.1f 倍，"
        "**同一张图共用 y 轴会把欧线压平，故本页按单位分两组**。"
        % (cur["use"], cur["usw"], cur["pw"], cur["med"], cur["eu"],
           cur["use"] / max(1e-9, cur["eu"])),
        "舱位利用率定性分档：**紧张 %d 期 / 平衡 %d 期 / 宽松 %d 期**"
        "（共 %d 期，紧张占 %.0f%%）——供给端偏紧与美线运价高位互相印证。"
        % (n_t, sum(1 for u in util if u == "平衡"), sum(1 for u in util if u == "宽松"),
           len(util), n_t / max(1, len(util)) * 100),
        "口径：欧洲/地中海/波斯湾为 **USD/TEU**，美西/美东为 **USD/FEU**，"
        "两者**不可直接比大小**；分航线数据只有**当年**（%s 起 %d 期），"
        "更长历史需从上海航交所周报逐期补录。" % (fl[0]["d"], len(fl)),
    ]
    return title, pts


def build_sse():
    idx, fl = read_sse()
    di = col(idx, "d")
    c = lambda k: col(idx, k)
    i26 = [r for r in idx if r["d"] >= "2026-01-01"]
    cc = [r for r in idx if r["d"] >= CCFI_START and r["ccfi"] is not None]
    dc = col(cc, "d")
    rr = [r for r in idx if r["d"] >= CCFI_START and r["ratio"] is not None]
    drr = col(rr, "d")
    ww = [r for r in idx if r["scfi_wow"] is not None][-104:]
    dw = col(ww, "d")

    ss, sc, sr = stats(idx, "scfi"), stats(cc, "ccfi"), stats(rr, "ratio")
    rs = {k: stats(fl, k) for k, _, _, _, _ in SSE_ROUTES}
    cur, first = fl[-1], fl[0]
    n_period = len(idx)

    # ================================================================ ① 综合
    def kpi_idx():
        items = [
            dict(name="SCFI 综合指数", v=f'{ss["v"]:,.2f}', unit="点",
                 d1=f'周环比 {ss["wow"]:+.2f}%' if ss["wow"] is not None else "—",
                 cls="up" if (ss["wow"] or 0) > 0 else ("down" if (ss["wow"] or 0) < 0 else "flat"),
                 d2=f'<i>年内</i> {pct(i26[0]["scfi"], i26[-1]["scfi"]):+.1f}%',
                 spark=spark(c("scfi")[-104:], C_RED), src=f'SSE · {ss["d"]}'),
            dict(name="CCFI 综合指数" + ("（上期）" if idx[-1]["ccfi"] is None else ""),
                 v=f'{sc["v"]:,.2f}', unit="点",
                 d1=f'周环比 {sc["wow"]:+.2f}%' if sc["wow"] is not None else "—",
                 cls="up" if (sc["wow"] or 0) > 0 else ("down" if (sc["wow"] or 0) < 0 else "flat"),
                 d2=f'<i>年内</i> '
                    f'{pct(next(r["ccfi"] for r in cc if r["d"][:4] == "2026"), sc["v"]):+.1f}%',
                 spark=spark(col(cc, "ccfi")[-104:], C_BLUE), src=f'SSE · {sc["d"]}'),
            dict(name="SCFI / CCFI 即期溢价" + ("（上期）" if idx[-1]["ccfi"] is None else ""),
                 v=f'{sr["v"]:.2f}', unit="倍",
                 d1=f'较上期 {pct(rr[-2]["ratio"], sr["v"]):+.2f}%',
                 cls="flat",
                 d2=f'<i>年内区间</i> {sr["lo"]:.2f}–{sr["hi"]:.2f}',
                 spark=spark(col(rr, "ratio")[-104:], C_AMBER), src=f'SSE · {sr["d"]}'),
            dict(name="SCFI 距 2021 峰值", v=f'{pct(ss["hi"], ss["v"]):+.1f}%', unit="",
                 d1=f'峰值 {ss["hi"]:,.0f} 点',
                 cls="down" if ss["v"] < ss["hi"] else "up",
                 d2=f'<i>峰值日期</i> {ss["hi_d"]}',
                 spark="", src=f'2021-01 起 {n_period} 期最高'),
        ]
        return kpi2(items)

    s1 = multi_svg("s1", "SCFI 综合指数", "点",
                   [("SCFI 综合", di, c("scfi"))], [C_RED], W=560, hl=True)
    s2 = multi_svg("s2", "CCFI 综合指数", "点",
                   [("CCFI 综合", dc, col(cc, "ccfi"))], [C_BLUE], W=560, hl=True)
    s3 = multi_svg("s3", "SCFI / CCFI 即期溢价倍数", "倍",
                   [("即期溢价", drr, col(rr, "ratio"))], [C_AMBER], W=560, hl=True)
    s4 = bar_svg("s4", "SCFI 综合周环比", "%", dw, col(ww, "scfi_wow"), W=560, H=300)

    sign, nstr = _streak(c("scfi"))
    s1_ann = (f'本期 <b>{ss["v"]:,.2f}</b> 点（周环比 <b>{ss["wow"]:+.2f}%</b>'
              + (f'，已连续 <b>{nstr} 周{_dir_word(sign)}</b>' if nstr >= 2 else "")
              + f'）；2021 年以来峰值 <b>{ss["hi"]:,.0f}</b>（{ss["hi_d"]}）、'
                f'谷值 <b>{ss["lo"]:,.0f}</b>（{ss["lo_d"]}），当前距峰值 '
                f'<b>{pct(ss["hi"], ss["v"]):+.1f}%</b>。长序列按<b>真实日期</b>定位，'
                f'春节等长假造成的 14 天间隔会显示为横向拉宽，不是缺数据。')
    gap_now = pct(sc["v"], ss["v"])
    s2_ann = (f'本期 <b>{sc["v"]:,.2f}</b> 点（周环比 <b>{sc["wow"]:+.2f}%</b>）；'
              f'SCFI 当前比 CCFI <b>{gap_now:+.1f}%</b>，'
              + ('即期显著高于长协中枢——船司当期收入弹性放大，'
                 '但长协占比高意味着报表收入的上行幅度会小于 SCFI 涨幅。'
                 if gap_now > 20 else
                 '即期与长协接近，SCFI 波动对报表收入的传导更直接。'))
    s3_ann = (f'本期 <b>{sr["v"]:.2f}</b> 倍；本年区间 <b>{sr["lo"]:.2f}–{sr["hi"]:.2f}</b>，'
              f'当前处于区间 <b>{(sr["v"] - sr["lo"]) / max(1e-9, sr["hi"] - sr["lo"]) * 100:.0f}%</b> 分位。'
              f'含义：<b>&gt;1 即期高于长协</b>，船司短期盈利弹性大；'
              f'<b>回落至 1 附近</b>说明长协价已追上现货，运价下行对收入的冲击被合同价缓冲。')
    bw = [r["scfi_wow"] for r in idx if r["scfi_wow"] is not None]
    bmax, bmin = max(bw), min(bw)
    s4_ann = (f'近 {len(ww)} 期：上涨 <b>{sum(1 for v in bw if v > 0)}</b> 期、'
              f'下跌 <b>{sum(1 for v in bw if v < 0)}</b> 期；全样本单期最大 '
              f'<b>{bmax:+.2f}%</b>、最小 <b>{bmin:+.2f}%</b>。'
              f'柱状按<b>真实日期</b>落位，长短不一的间隔说明发布节奏受假期影响。')

    dtab = grid_table(
        "最近 9 期综合指数（点）",
        ["日期", "SCFI", "周环比", "CCFI", "周环比", "即期倍数"],
        [[r["d"],
          f'{r["scfi"]:,.2f}' if r["scfi"] is not None else "—",
          f'<span class="{_cls(r["scfi_wow"])}">{r["scfi_wow"]:+.2f}%</span>'
          if r["scfi_wow"] is not None else "—",
          f'{r["ccfi"]:,.2f}' if r["ccfi"] is not None else "—",
          f'<span class="{_cls(r["ccfi_wow"])}">{r["ccfi_wow"]:+.2f}%</span>'
          if r["ccfi_wow"] is not None else "—",
          f'{r["ratio"]:.2f}' if r["ratio"] is not None else "—"]
         for r in idx[-9:]],
        note="周环比取源表字段（小数比例 ×100），已与相邻两期实际值逐期核对一致。",
        wide=True)

    t1, p1 = sse_points_index(idx, cc, i26)
    blk_idx = blk("sseidx", "SCFI·CCFI", "上海出口集装箱运价指数 / 中国出口集装箱运价指数",
                  "即期 | 长协加权",
                  f'数据截止 <b>{ss["d"]}</b><br>上海航运交易所 · 每周五',
                  kps_block(f'本期要点 · {ss["d"]}', dict(title=t1, points=p1))
                  + kpi_idx()
                  + '<div class="chart-grid">'
                  + chart_ann("SCFI 综合指数（2021-01 起）", s1, s1_ann,
                              f"{n_period} 期 · 末年橙圈为最新一期 · 点击图例隐藏、双击放大")
                  + chart_ann("CCFI 综合指数", s2, s2_ann,
                              f"{len(cc)} 期 · 末年橙圈为最新一期 · 点击图例隐藏、双击放大")
                  + chart_ann("SCFI 综合周环比（近 104 期）", s4, s4_ann,
                              "正值红、负值绿 · 全样本极值见注解")
                  + chart_ann("SCFI / CCFI 即期溢价倍数", s3, s3_ann,
                              "= SCFI ÷ CCFI，>1 即期高于长协")
                  + dtab
                  + "</div>")

    # ================================================================ ② 分航线
    def kpi_routes():
        items = []
        for k, cn, cc_, un, _ in SSE_ROUTES:
            s = rs[k]
            if not s:
                continue
            items.append(dict(
                name=cn, v=f'{s["v"]:,.0f}', unit=un,
                d1=f'周环比 {s["wow"]:+.2f}%' if s["wow"] is not None else "—",
                cls=_cls(s["wow"]),
                d2=f'<i>年内</i> {pct(first[k], s["v"]):+.0f}%',
                spark=spark(col(fl, k), cc_), src=f'SSE · {s["d"]}'))
        items.append(dict(
            name="舱位利用率", v=cur["util"] or "—", unit="",
            d1="定性分档 · 非数值",
            cls="flat",
            d2=f'<i>紧张</i> {sum(1 for r in fl if r["util"] == "紧张")} 期 / {len(fl)} 期',
            spark="", src=f'SSE 周报正文 · {cur["d"]}'))
        return kpi2(items, cls="k3")

    eu = [r for r in fl if r["eu"] is not None]
    us = [r for r in fl if r["usw"] is not None]
    pw = [r for r in fl if r["pw"] is not None]
    r1 = multi_svg("r1", "欧地线（USD/TEU）", "USD/TEU",
                   [(SSE_SHORT["eu"], col(eu, "d"), col(eu, "eu")),
                    (SSE_SHORT["med"], col(eu, "d"), col(eu, "med"))],
                   [C_BLUE, C_TEAL], W=560, hl=True)
    r2 = multi_svg("r2", "美线（USD/FEU）", "USD/FEU",
                   [(SSE_SHORT["usw"], col(us, "d"), col(us, "usw")),
                    (SSE_SHORT["use"], col(us, "d"), col(us, "use"))],
                   [C_RED, C_PURPLE], W=560, hl=True)
    r3 = multi_svg("r3", "波斯湾线（USD/TEU）", "USD/TEU",
                   [(SSE_SHORT["pw"], col(pw, "d"), col(pw, "pw"))],
                   [C_AMBER], W=560, hl=True)

    w = {cn: rs[k]["wow"] for k, cn, _, _, _ in SSE_ROUTES if rs[k]}
    eu_hi = max(eu, key=lambda r: r["med"])
    us_hi = max(us, key=lambda r: r["use"])
    r1_ann = (f'欧洲 <b>{cur["eu"]:,.0f}</b>（{w.get("欧洲航线", 0):+.2f}%）、'
              f'地中海 <b>{cur["med"]:,.0f}</b>（{w.get("地中海航线", 0):+.2f}%）；'
              f'两线年内低点分别在 {min(eu, key=lambda r: r["eu"])["d"]} 与 '
              f'{min(eu, key=lambda r: r["med"])["d"]}，'
              f'当前距年内高点 '
              f'<b>{pct(eu_hi["med"], cur["med"]):+.1f}%</b>（地中海）。'
              f'欧地线弹性明显小于美线，是长协占比最高的一组。')
    r2_ann = (f'美西 <b>{cur["usw"]:,.0f}</b>（{w.get("美西航线", 0):+.2f}%）、'
              f'美东 <b>{cur["use"]:,.0f}</b>（{w.get("美东航线", 0):+.2f}%）；'
              f'年内自 {first["usw"]:,.0f} / {first["use"]:,.0f} 起涨，'
              f'当前 <b>{pct(first["usw"], cur["usw"]):+.0f}% / '
              f'{pct(first["use"], cur["use"]):+.0f}%</b>，'
              f'距高点仅 <b>{pct(us_hi["use"], cur["use"]):+.1f}%</b>（美东）。'
              f'<b>跨太平洋是本轮运价上行的主引擎</b>，与 WCI 洛杉矶/纽约的走势同向。')
    r3_ann = (f'波斯湾 <b>{cur["pw"]:,.0f}</b>（{w.get("波斯湾航线", 0):+.2f}%）；'
              f'年内自 {min(pw, key=lambda r: r["pw"])["pw"]:,.0f} 涨至 '
              f'{max(pw, key=lambda r: r["pw"])["pw"]:,.0f}，'
              f'振幅 <b>{pct(min(pw, key=lambda r: r["pw"])["pw"], max(pw, key=lambda r: r["pw"])["pw"]):+.0f}%</b>。'
              f'该航线对<b>中东地缘与霍尔木兹通行风险</b>最敏感，'
              f'单周波动可轻易超过 ±5%，方向参考价值强于幅度。')

    rtab = grid_table(
        "最近 9 期分航线运价",
        ["日期", "欧洲", "地中海", "美西", "美东", "波斯湾", "舱位"],
        [[r["d"],
          f'{r["eu"]:,.0f}', f'{r["med"]:,.0f}', f'{r["usw"]:,.0f}',
          f'{r["use"]:,.0f}', f'{r["pw"]:,.0f}', r["util"] or "—"]
         for r in fl[-9:]],
        note="欧洲/地中海/波斯湾为 USD/TEU，美西/美东为 USD/FEU；"
             "「舱位」为周报正文的定性分档，非数值。",
        wide=False)

    t2, p2 = sse_points_routes(fl)
    blk_rt = blk("sseroute", "SCFI 分线", "上海出口集装箱分航线运价",
                 "5 条主干航线 · 单位 USD/TEU 与 USD/FEU 并存",
                 f'数据截止 <b>{cur["d"]}</b><br>上海航运交易所 · {len(fl)} 期',
                 kps_block(f'本期要点 · {cur["d"]}', dict(title=t2, points=p2))
                 + kpi_routes()
                 + '<div class="chart-grid">'
                 + chart_ann("欧地线（USD/TEU）", r1, r1_ann, "欧洲 / 地中海 · 末年橙圈为最新")
                 + chart_ann("美线（USD/FEU）", r2, r2_ann, "美西 / 美东 · 末年橙圈为最新")
                 + chart_ann("波斯湾线（USD/TEU）", r3, r3_ann, "地缘溢价最敏感的一条")
                 + rtab
                 + "</div>")

    # ================================================================ 组装
    side = vside("两大板块", [
        ("#sseidx", "S", "SCFI·CCFI", "综合运价指数"),
        ("#sseroute", "R", "分线", "五条主干航线"),
    ])
    foot = (f'<div class="foot"><span>数据来源：上海航运交易所（sse.net.cn）SCFI / CCFI 周度指数、'
            f'SCFI 分航线运价与周报正文；综合指数 2021-01 起 {n_period} 期，'
            f'分航线为 2026 年内 {len(fl)} 期。</span>'
            f'<span>更新：每周五发布；本页由 build_weekly_pages.py 从 '
            f'中远海控_SSE周报数据.xlsx 重建，非实时。</span></div>')
    body = vlayout(side, blk_idx + blk_rt + foot)
    doc = shell("SSE 周报 · 上海航运交易所运价指数", "SSE 周报 · 上海航运交易所运价指数",
                f"SCFI / CCFI 综合指数 · SCFI 五条分航线 · "
                f"综合 {n_period} 期 / 分线 {len(fl)} 期 · 单一 xlsx 数据源",
                "sse", body)
    open(OUT_SSE, "w", encoding="utf-8").write(doc)
    return OUT_SSE, doc, n_period, len(p1) + len(p2)


def _cls(v):
    """涨红跌绿配色类。"""
    if v is None:
        return "flat"
    return "up" if v > 0 else ("down" if v < 0 else "flat")


BUILDERS = {
    "drewry": build_drewry,
    "alphaliner": build_alphaliner,
    "sse": build_sse,
}


def main(argv=None):
    """按 --only 重建指定周报页；默认 all（三页全量，保持原有行为）。"""
    import argparse
    ap = argparse.ArgumentParser(description="Drewry / Alphaliner / SSE 周报页生成器")
    ap.add_argument("--only", choices=(*BUILDERS, "all"), default="all",
                    help="只重建指定页面；默认 all（三页全量重建）")
    args = ap.parse_args(argv)

    targets = list(BUILDERS) if args.only == "all" else [args.only]
    results = []
    for name in targets:
        path, doc, n, extra = BUILDERS[name]()
        size = len(doc.encode("utf-8"))
        results.append({"page": name, "path": path, "bytes": size,
                        "periods": n, "svg": doc.count("<svg "), "points": extra})
        print(f"生成 {os.path.basename(path):26s} {size:>7,} B  "
              f"SVG {doc.count('<svg '):>2d} 张  数据 {n} 期" +
              (f"  官方要点 {extra} 条" if extra else ""))
    skipped = [n for n in BUILDERS if n not in targets]
    if skipped:
        print("未渲染（数据未更新）: " + ", ".join(skipped))
    return results


if __name__ == "__main__":
    main()
