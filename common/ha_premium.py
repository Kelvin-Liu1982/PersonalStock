# -*- coding: utf-8 -*-
"""跨看板通用「H/A 溢价率（日频）」数据层 + 图表层（/业绩追踪看板/common）。

用途：任意 A+H 双重上市标的，一条命令产出「H/A 溢价率日频序列」与配套 SVG，
供各看板内联到 __CHARTS__（与 common/svg_charts.py 的 canonical 780×300 风格一致）。

口径（与 worker/index.js 的 decorate() 完全一致）：
    premium = H股收盘价(港元) × HKD/CNY ÷ A股收盘价 − 1
    → 负值 = H 股相对 A 股折价；**不是** A/H 溢价（后者方向相反）。
    → 必须用【未复权】收盘价：前复权会按 A 股分红调整历史价，使历史溢价率失真。

数据源（均免费、无需 key）：
    1) A/H 日线：腾讯 gtimg  web.ifzq.gtimg.cn/appstock/app/fqkline/get
       单次最多约 800 根（≈3.3 年），不传 fq 参数即为未复权。
    2) HKD/CNY 日汇率：优先 frankfurter.dev（ECB 日参考价 JSON）；
       失败回退 ECB 官方 eurofxref-hist.zip（用 CNY/HKD 交叉汇率，权威且可回溯至 1999）。
       注意：ECB 参考价截至前一日 16:00 CET，当日盘中值仍以 Worker 实时汇率为准。

可复现性：默认同时写 CSV 快照（含 a/h 收盘、汇率、溢价率），
    --offline 时完全不联网、仅从快照重绘，保证 SVG 逐字节可重建。

用法（命令行）：
    python common/ha_premium.py --a sh601898 --h hk01898 --title "中煤能源 H/A 溢价率" \\
        --csv 数据源/ha_premium_601898.csv \\
        --trend svg/trend_ha_premium.svg --spark svg/spark_ha_premium.svg

    python common/ha_premium.py --a 601898 --h 01898 --bars 400          # 代码可省略市场前缀
    python common/ha_premium.py --offline --csv 数据源/ha_premium_601898.csv \\
        --trend svg/trend_ha_premium.svg                                 # 只重绘，不联网

用法（作为库）：
    from common.ha_premium import build_series, render_trend_svg, render_spark_svg
    rows = build_series("sh601898", "hk01898", bars=400)   # [{date,a,h,fx,pct}, ...]
    svg  = render_trend_svg(rows, "中煤能源 H/A 溢价率")
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import re
import sys
import time
import urllib.request
import zipfile

# ── 常量 ────────────────────────────────────────────────────────────────
TENCENT_KLINE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{bars},"
FRANKFURTER = "https://api.frankfurter.dev/v1/{start}..{end}?base=HKD&symbols=CNY"
ECB_HIST_ZIP = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
UA = "Mozilla/5.0 (compatible; workbuddy-ha-premium/1.0)"
TIMEOUT = 25

# 图表默认配色（浅色主题）；溢价率本身不是「涨跌」，故线色取中性蓝而非红/绿
LINE_COLOR = "#185FA5"
ACCENT_COLOR = "#c53030"
GRID_COLOR = "#eef2f6"
TICK_COLOR = "#7a8694"
TITLE_COLOR = "#1f2733"

CSV_HEADER = ["date", "a_close", "h_close", "hkd_cny", "premium_pct"]


# ── 基础设施 ────────────────────────────────────────────────────────────
def _http_get(url, timeout=TIMEOUT, retries=2):
    """带 UA / 超时 / 重试的 GET，返回 bytes。"""
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:          # noqa: BLE001 - 统一重试后抛出原始错误
            last = e
            if i < retries:
                time.sleep(0.8 * (i + 1))
    raise RuntimeError(f"请求失败: {url} -> {last}")


def normalize_code(code, market="a"):
    """把 '601898' / 'sh601898' / '01898' / 'hk01898' 归一化为腾讯代码。

    market='a'：纯数字 6 位按首位推断 sh/sz；market='h'：纯数字补零到 5 位加 hk。
    """
    c = str(code).strip().lower()
    if market == "h":
        if re.fullmatch(r"hk\d{5}", c):
            return c
        digits = re.sub(r"\D", "", c)
        if not digits:
            raise ValueError(f"H 股代码非法: {code!r}")
        return "hk" + digits.zfill(5)
    if re.fullmatch(r"(sh|sz)\d{6}", c):
        return c
    digits = re.sub(r"\D", "", c)
    if len(digits) != 6:
        raise ValueError(f"A 股代码非法: {code!r}（需 6 位数字）")
    return ("sh" if digits[0] in "56" else "sz") + digits


# ── 数据层：日线 ────────────────────────────────────────────────────────
def fetch_daily_close(code, bars=400):
    """取未复权日收盘价，返回 {'YYYY-MM-DD': close}（升序无关，取用方自行排序）。"""
    raw = _http_get(TENCENT_KLINE.format(code=code, bars=int(bars)))
    try:
        payload = json.loads(raw.decode("utf-8", "ignore"))
        node = payload["data"][code]
    except Exception as e:                                  # noqa: BLE001
        raise RuntimeError(f"腾讯日线解析失败 {code}: {e}") from e
    # 未传 fq 时返回 'day'；若上游仍给了复权键，优先取未复权的 'day'
    arr = node.get("day") or node.get("qfqday")
    if not arr:
        raise RuntimeError(f"腾讯日线为空 {code}")
    out = {}
    for r in arr:
        try:
            out[str(r[0])[:10]] = float(r[2])               # [日期, 开, 收, 高, 低, 量]
        except (IndexError, TypeError, ValueError):
            continue
    if not out:
        raise RuntimeError(f"腾讯日线无有效记录 {code}")
    return out


# ── 数据层：汇率 ────────────────────────────────────────────────────────
def fetch_fx_frankfurter(start, end):
    """ECB 日参考价（经 frankfurter.dev），返回 {'YYYY-MM-DD': HKD/CNY}。"""
    raw = _http_get(FRANKFURTER.format(start=start, end=end))
    payload = json.loads(raw.decode("utf-8", "ignore"))
    out = {}
    for d, kv in (payload.get("rates") or {}).items():
        v = kv.get("CNY") if isinstance(kv, dict) else None
        if v:
            out[str(d)[:10]] = float(v)
    return out


def fetch_fx_ecb(start, end):
    """ECB 官方 eurofxref-hist.zip → HKD/CNY = CNY_per_EUR ÷ HKD_per_EUR。"""
    raw = _http_get(ECB_HIST_ZIP, timeout=40)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        rows = csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8"))
        out = {}
        for r in rows:
            d = r.get("Date")
            if not d or d < start or d > end:
                continue
            try:
                hkd, cny = float(r["HKD"]), float(r["CNY"])
            except (KeyError, TypeError, ValueError):
                continue
            if hkd > 0 and cny > 0:
                out[d] = cny / hkd
    return out


def fetch_fx_hkd_cny(start, end, source="auto"):
    """按 auto → frankfurter → ECB 顺序取汇率；全部失败则抛错（不静默编造）。"""
    order = {"auto": ["frankfurter", "ecb"], "frankfurter": ["frankfurter"],
             "ecb": ["ecb"]}.get(source, ["frankfurter", "ecb"])
    errs = []
    for name in order:
        try:
            fx = fetch_fx_frankfurter(start, end) if name == "frankfurter" else fetch_fx_ecb(start, end)
            if fx:
                return fx, name
            errs.append(f"{name}: 返回空")
        except Exception as e:                              # noqa: BLE001
            errs.append(f"{name}: {e}")
    raise RuntimeError("汇率获取失败（" + "；".join(errs) + "）")


def _fill_fx(dates, fx):
    """把日频汇率对齐到交易日：取 ≤ 该日的最近值（前向填充）。

    返回 (filled, skipped)：skipped 为早于汇率覆盖起点、无法填充的日期。
    """
    keys = sorted(fx)
    if not keys:
        return {}, list(dates)
    filled, skipped = {}, []
    j = -1
    for d in sorted(dates):
        while j + 1 < len(keys) and keys[j + 1] <= d:
            j += 1
        if j < 0:
            skipped.append(d)
        else:
            filled[d] = fx[keys[j]]
    return filled, skipped


# ── 序列合成 ────────────────────────────────────────────────────────────
def build_series(a_code, h_code, bars=400, start=None, end=None, fx_source="auto",
                 today=None):
    """合成 H/A 溢价率日频序列。

    返回 (rows, meta)：
      rows = [{'date','a','h','fx','pct'}, ...] 按日期升序
      meta = {'a_code','h_code','fx_source','fetched_at','bars','skipped'}
    """
    a_code, h_code = normalize_code(a_code, "a"), normalize_code(h_code, "h")
    a = fetch_daily_close(a_code, bars)
    h = fetch_daily_close(h_code, bars)

    lo = min(min(a), min(h)) if start is None else max(min(a), min(h), start)
    hi = max(max(a), max(h)) if end is None else min(max(a), max(h), end)
    fx, fx_name = fetch_fx_hkd_cny(lo, hi, source=fx_source)

    common_dates = sorted(d for d in (set(a) & set(h)) if lo <= d <= hi)
    filled, skipped = _fill_fx(common_dates, fx)

    rows = []
    for d in common_dates:
        r = filled.get(d)
        if not r:
            continue
        pa, ph = a[d], h[d]
        if pa <= 0 or ph <= 0:
            continue
        rows.append({
            "date": d,
            "a": round(pa, 4),
            "h": round(ph, 4),
            "fx": round(r, 6),
            "pct": round((ph * r / pa - 1) * 100, 2),
        })
    if not rows:
        raise RuntimeError("无重叠交易日或汇率，序列为空")
    meta = {
        "a_code": a_code,
        "h_code": h_code,
        "fx_source": fx_name,
        "fetched_at": today or dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "bars": int(bars),
        "skipped": skipped,
    }
    return rows, meta


# ── 快照层（CSV，离线可重建） ───────────────────────────────────────────
def save_csv(path, rows, meta=None):
    """写 CSV 快照；meta 以 '#' 注释行置于表头之前（load_csv 会自动跳过）。"""
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        if meta:
            for k in ("a_code", "h_code", "fx_source", "fetched_at", "bars"):
                if k in meta:
                    f.write(f"# {k}: {meta[k]}\n")
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for r in rows:
            w.writerow([r["date"], r["a"], r["h"], r["fx"], r["pct"]])
    return path


def load_csv(path):
    """读 CSV 快照，返回 (rows, meta)。"""
    rows, meta = [], {}
    with open(path, encoding="utf-8") as f:
        lines = []
        for line in f:
            if line.startswith("#"):
                k, _, v = line[1:].partition(":")
                meta[k.strip()] = v.strip()
            else:
                lines.append(line)
    for r in csv.DictReader(io.StringIO("".join(lines))):
        try:
            rows.append({
                "date": r["date"],
                "a": float(r["a_close"]),
                "h": float(r["h_close"]),
                "fx": float(r["hkd_cny"]),
                "pct": float(r["premium_pct"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda x: x["date"])
    return rows, meta


def embed_html(html_path, key, rows, meta, tag_id="haPremiumData"):
    """把序列写入看板 HTML 的 <script id="haPremiumData" type="application/json">。

    - 幂等：已存在同 key 则整体替换；其它 key 原样保留（一个看板可挂多只标的）；
    - 不存在该 script 标签时，插到 </body> 之前；
    - 输出为紧凑 JSON（省体积），并把 '</' 转义为 '<\\/' 以免提前闭合 script。
    """
    payload = {
        "a": meta.get("a_code", ""),
        "h": meta.get("h_code", ""),
        "unit": "%",
        "updated": rows[-1]["date"],
        "series": [[r["date"], r["pct"]] for r in rows],
    }
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    pat = re.compile(r'(<script[^>]*id="%s"[^>]*>)(.*?)(</script>)' % re.escape(tag_id), re.S)
    m = pat.search(html)
    if m:
        try:
            obj = json.loads(m.group(2) or "{}")
        except ValueError:
            obj = {}
        obj[key] = payload
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        html = html[:m.start(2)] + body + html[m.end(2):]
        action = "更新"
    else:
        block = (f'<script id="{tag_id}" type="application/json">'
                 + json.dumps({key: payload}, ensure_ascii=False,
                              separators=(",", ":")).replace("</", "<\\/")
                 + "</script>\n</body>")
        if "</body>" not in html:
            raise RuntimeError(f"{html_path} 缺少 </body>，无法插入数据块")
        html = html.replace("</body>", block, 1)
        action = "新增"

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return action, len(rows)


# ── 图表层 ──────────────────────────────────────────────────────────────
def _nice_axis(vmin, vmax, ticks=5):
    """把 [vmin,vmax] 收敛到「整刻度」区间，返回 (lo, hi, step)。

    百分比序列最忌讳 -19/-24/-30 这类随机刻度；按 1/2/2.5/5/10 量级取步长并外扩。
    """
    span = (vmax - vmin) or (abs(vmax) * 0.1 or 1)
    raw = span / max(1, ticks)
    mag = 10 ** math.floor(math.log10(raw))
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    lo = math.floor((vmin - span * 0.05) / step) * step
    hi = math.ceil((vmax + span * 0.05) / step) * step
    if hi - lo < step:
        hi = lo + step
    return lo, hi, step


def _path_d(xs, ys, base_y=None):
    """由点列拼 SVG path；base_y 不为 None 时闭合成面积路径。

    注意：不能用 "x y x y".replace(" "," L") 之类的替换——首点的 x/y 之间也会被替换。
    """
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in zip(xs, ys))
    if base_y is not None:
        d += f" L{xs[-1]:.1f} {base_y:.1f} L{xs[0]:.1f} {base_y:.1f} Z"
    return d


def _fmt_pct(v, dec=0):
    """百分比刻度/标签：正值补 '+'、0 不补，便于与折价区分。"""
    if abs(v) < 10 ** (-(dec + 2)):
        return "0" + ("." + "0" * dec if dec else "") + "%"
    return f"{v:+.{dec}f}%"


def render_trend_svg(rows, title, color=LINE_COLOR, accent=ACCENT_COLOR,
                     W=780, H=300, fill=True, months_every=2, subtitle=None,
                     vfmt=None, label_fmt=None):
    """日频溢价率趋势图（canonical 780×300：白底、#eef2f6 网格、#7a8694 刻度）。

    - x 轴按索引等距（与各看板趋势图一致），每 months_every 个月标一次 + 首末点必标；
    - 仅末点画强调圆点与数值标签，避免 300+ 点密集遮挡；
    - 区间跨 0 时画一条虚线零轴（H 股由折价转溢价的临界线）。
    """
    if not rows:
        raise RuntimeError("render_trend_svg: rows 为空")
    padL, padR, padT, padB = 54, 18, 40, 44
    plotW, plotH = W - padL - padR, H - padT - padB
    n = len(rows)
    vals = [r["pct"] for r in rows]
    ylo, yhi, step = _nice_axis(min(vals), max(vals))
    if vfmt is None:
        dec = 0 if abs(step - round(step)) < 1e-9 else 1
        vfmt = lambda v: _fmt_pct(v, dec)
    if label_fmt is None:
        label_fmt = lambda v: _fmt_pct(v, 2)

    def X(i):
        return padL + (plotW * i / (n - 1) if n > 1 else plotW / 2)

    def Y(v):
        return padT + plotH * (1 - (v - ylo) / (yhi - ylo))

    xs = [X(i) for i in range(n)]
    ys = [Y(v) for v in vals]

    o = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
         f'font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">']
    o.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')
    o.append(f'<text x="{padL}" y="22" fill="{TITLE_COLOR}" font-size="14" '
             f'font-weight="700">{_esc(title)}</text>')
    if subtitle:
        o.append(f'<text x="{padL}" y="36" fill="#9aa6b2" font-size="10">{_esc(subtitle)}</text>')

    # 横向网格 + y 刻度（按整步长）
    val = ylo
    while val <= yhi + step * 1e-6:
        gy = Y(val)
        o.append(f'<line x1="{padL}" y1="{gy:.1f}" x2="{W - padR}" y2="{gy:.1f}" '
                 f'stroke="{GRID_COLOR}" stroke-width="1"/>')
        o.append(f'<text x="{padL - 6}" y="{gy + 3.5:.1f}" fill="{TICK_COLOR}" '
                 f'font-size="10" text-anchor="end">{vfmt(val)}</text>')
        val += step

    # 零轴（跨 0 时）
    if ylo < 0 < yhi:
        zy = Y(0)
        o.append(f'<line x1="{padL}" y1="{zy:.1f}" x2="{W - padR}" y2="{zy:.1f}" '
                 f'stroke="#cbd5e1" stroke-width="1" stroke-dasharray="4 3"/>')

    # 面积 + 折线
    if fill:
        o.append(f'<path d="{_path_d(xs, ys, base_y=Y(ylo))}" fill="{color}" fill-opacity="0.07"/>')
    o.append(f'<path d="{_path_d(xs, ys)}" fill="none" stroke="{color}" '
             f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')

    # 末点强调 + 数值
    o.append(f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="3.2" '
             f'fill="{accent}" stroke="#ffffff" stroke-width="1.4"/>')
    o.append(f'<text x="{xs[-1] - 6:.1f}" y="{ys[-1] - 9:.1f}" fill="{accent}" '
             f'font-size="10.5" font-weight="700" text-anchor="end">{label_fmt(vals[-1])}</text>')

    # x 轴月份标签
    base = padT + plotH
    last_label_x = None
    for i, r in enumerate(rows):
        m = r["date"][:7]
        prev = rows[i - 1]["date"][:7] if i else None
        if m == prev:
            continue
        mi = int(m[5:7])
        if not (i == 0 or (mi - 1) % max(1, months_every) == 0):
            continue
        anchor = "start" if i == 0 else ("end" if i >= n - 1 else "middle")
        lx = xs[i] + (2 if i == 0 else (-2 if i >= n - 1 else 0))
        o.append(f'<text x="{lx:.1f}" y="{base + 18:.1f}" fill="{TICK_COLOR}" '
                 f'font-size="9" text-anchor="{anchor}">{m}</text>')
        last_label_x = xs[i]

    # 末点日期标签（与上一个月份标签过近则省略）
    if last_label_x is None or xs[-1] - last_label_x > 46:
        o.append(f'<text x="{xs[-1]:.1f}" y="{base + 18:.1f}" fill="{TICK_COLOR}" '
                 f'font-size="9" text-anchor="end">{rows[-1]["date"][5:]}</text>')

    o.append(f'<line x1="{padL}" y1="{base:.1f}" x2="{W - padR}" y2="{base:.1f}" '
             f'stroke="#c3ccd6" stroke-width="1"/>')
    o.append('</svg>')
    return "".join(o)


def render_spark_svg(rows, color=LINE_COLOR, W=62, H=28):
    """卡片内 mini sparkline（与各看板 spark_*.svg 同规格 62×28）。"""
    vals = [r["pct"] for r in rows]
    if not vals:
        raise RuntimeError("render_spark_svg: rows 为空")
    n = len(vals)
    vmin, vmax = min(vals), max(vals)
    pad = (vmax - vmin) * 0.15 or 0.5
    lo, hi = vmin - pad, vmax + pad
    xs = [2 + (W - 4) * i / (n - 1) for i in range(n)] if n > 1 else [W / 2]
    ys = [4 + (H - 8) * (1 - (v - lo) / (hi - lo)) for v in vals]
    return (f'<svg class="spark" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="{_path_d(xs, ys)}" fill="none" stroke="{color}" stroke-width="2"/>'
            f'</svg>')


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ── CLI ────────────────────────────────────────────────────────────────
def _stats(rows):
    vals = [r["pct"] for r in rows]
    mn = min(rows, key=lambda r: r["pct"])
    mx = max(rows, key=lambda r: r["pct"])
    return {
        "n": len(rows),
        "start": rows[0]["date"],
        "end": rows[-1]["date"],
        "latest": rows[-1]["pct"],
        "avg": round(sum(vals) / len(vals), 2),
        "min": mn["pct"], "min_date": mn["date"],
        "max": mx["pct"], "max_date": mx["date"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="H/A 溢价率（日频）序列与 SVG 生成器 —— 通用模块，供任意 A+H 标的复用")
    ap.add_argument("--a", help="A 股代码，如 sh601898 / 601898")
    ap.add_argument("--h", help="H 股代码，如 hk01898 / 01898")
    ap.add_argument("--title", help="图表标题，默认「{A代码} H/A 溢价率（日频）」")
    ap.add_argument("--bars", type=int, default=400, help="日线根数（上限约 800），默认 400")
    ap.add_argument("--start", help="起始日期 YYYY-MM-DD（可选）")
    ap.add_argument("--end", help="截止日期 YYYY-MM-DD（可选）")
    ap.add_argument("--fx", default="auto", choices=["auto", "frankfurter", "ecb"],
                    help="汇率源，默认 auto（frankfurter → ECB 依次回退）")
    ap.add_argument("--csv", help="CSV 快照路径（联网时写入；--offline 时读取）")
    ap.add_argument("--offline", action="store_true", help="不联网，仅用 --csv 快照重绘")
    ap.add_argument("--trend", help="趋势图 SVG 输出路径")
    ap.add_argument("--spark", help="sparkline SVG 输出路径")
    ap.add_argument("--json", dest="json_out", help="序列 JSON 输出路径（供前端交互图用）")
    ap.add_argument("--embed-html", help="把序列写入该看板 HTML 的 script#haPremiumData（供卡片内嵌图）")
    ap.add_argument("--embed-key", help="写入 HTML 时使用的键，默认取 A 代码的 6 位数字")
    ap.add_argument("--color", default=LINE_COLOR, help=f"折线颜色，默认 {LINE_COLOR}")
    ap.add_argument("--months-every", type=int, default=2, help="x 轴每几个月标一次，默认 2")
    ap.add_argument("--no-fill", action="store_true", help="不画面积填充")
    args = ap.parse_args(argv)

    if args.offline:
        if not args.csv:
            ap.error("--offline 需配合 --csv 指定快照")
        rows, meta = load_csv(args.csv)
        a_code, h_code = meta.get("a_code", ""), meta.get("h_code", "")
        print(f"📦 离线读取快照：{args.csv}（{len(rows)} 点，{rows[0]['date']} ~ {rows[-1]['date']}）")
    else:
        if not (args.a and args.h):
            ap.error("联网模式需同时提供 --a 与 --h（或改用 --offline --csv）")
        bars = max(30, min(int(args.bars), 800))
        if args.bars > 800:
            print("⚠️  腾讯日线上限约 800 根，已截断为 800")
        try:
            rows, meta = build_series(args.a, args.h, bars=bars, start=args.start,
                                      end=args.end, fx_source=args.fx)
        except Exception as e:                              # noqa: BLE001
            print(f"✗ 取数失败：{e}", file=sys.stderr)
            return 2
        a_code, h_code = meta["a_code"], meta["h_code"]
        print(f"🌐 已获取 {a_code}/{h_code}：{len(rows)} 个共同交易日"
              f"（{rows[0]['date']} ~ {rows[-1]['date']}），汇率源 {meta['fx_source']}")
        if meta["skipped"]:
            print(f"⚠️  {len(meta['skipped'])} 个交易日早于汇率覆盖范围已跳过")
        if args.csv:
            save_csv(args.csv, rows, meta)
            print(f"💾 快照已写入：{args.csv}")

    st = _stats(rows)
    print(f"📊 H/A 溢价率：最新 {st['latest']:+.2f}%（{st['end']}），均值 {st['avg']:+.2f}%，"
          f"区间 {st['min']:+.2f}%（{st['min_date']}）~ {st['max']:+.2f}%（{st['max_date']}）")

    title = args.title or f"{a_code.upper()} H/A 溢价率（日频）"
    if args.embed_html:
        key = args.embed_key or re.sub(r"\D", "", a_code)
        if not key:
            print("✗ --embed-html 无法推导键名，请显式传 --embed-key", file=sys.stderr)
            return 2
        act, cnt = embed_html(args.embed_html, key, rows,
                              {"a_code": a_code, "h_code": h_code})
        print(f"🧩 数据块已{act}：{args.embed_html}（key={key}，{cnt} 点）")
    if args.trend:
        svg = render_trend_svg(rows, title, color=args.color, months_every=args.months_every,
                               fill=not args.no_fill)
        _write(args.trend, svg)
        print(f"✅ 趋势图：{args.trend}")
    if args.spark:
        _write(args.spark, render_spark_svg(rows, color=args.color))
        print(f"✅ sparkline：{args.spark}")
    if args.json_out:
        _write(args.json_out, json.dumps(
            {"meta": {"a": a_code, "h": h_code, "unit": "%", "caliber": "H*fx/A-1"},
             "series": [{"date": r["date"], "pct": r["pct"]} for r in rows]},
            ensure_ascii=False, separators=(",", ":")))
        print(f"✅ JSON：{args.json_out}")
    return 0


def _write(path, text):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    sys.exit(main())
