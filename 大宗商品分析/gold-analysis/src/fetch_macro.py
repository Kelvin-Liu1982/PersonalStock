#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_macro.py —— 抓取 A 模块 A2–A8 七个宏观定价因子，写回 data/gold_data.xlsx。

方案 2：每个因子提供「现值（只读徽章）+ 时序（mini sparkline）」。
数据源均免费；FRED key 复用 config.FRED_API_KEY，Yahoo 日线复用 fetch_event.fetch_daily()。

    A2 实际利率   FRED DFII10（10Y TIPS 收益率）              日
    A3 美元指数   Yahoo DX-Y.NYB（ICE DXY）                   日
    A4 央行购金   复用「黄金供需季度」央行及其他机构列（WGC）   季
    A5 地缘政治   Caldara-Iacoviello GPR 指数 GPRD_MA30        日
    A6 金油比     Yahoo GC=F ÷ FRED DCOILWTICO(WTI)            日
    A7 通胀预期   FRED T10YIE（10Y 盈亏平衡通胀率）            日
    A8 风险偏好   Yahoo ^VIX（CBOE 波动率指数）                日

⚠️ 口径（务必保持，勿混用）：
  - DFII10 ≠ DGS10 − T10YIE，两者都是"实际利率"但构造不同，本表只用 DFII10。
  - ICE DXY(≈101) ≠ FRED 广义美元 DTWEXBGS(≈121)，量级不同。
  - A4 用 WGC GDT 季度口径，与 IFS「央行购金年度」不是同一口径，勿混。
  - GPR 是报纸词频代理指标，非价格；用 MA30 平滑。
  - GC=F 是 COMEX 期货、WTI 是现货，金油比只作趋势观察，单位为桶/盎司。
  - 日频统一降采样为周频（每周最后一个有效值），A4 保留 12 个季度；各因子独立绘图，不共轴。

用法（在 gold-analysis/ 下运行）：
  python3 src/fetch_macro.py                 抓取并写入
  python3 src/fetch_macro.py --dry-run       只打印，不落盘
  python3 src/fetch_macro.py --force-gpr     强制重下 GPR xls（默认用 data/ 缓存）
  python3 src/fetch_macro.py --no-gpr        跳过 GPR（离线时用缓存现值兜底）

抓取后需再跑 build_html.py 才会写进 HTML。
"""
import argparse
import datetime
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import excelio
import fetch_event
import fetch_gold_data
import paths


def months_ago_str(n):
    """今天往前 n 个月的 YYYY-MM-DD（日固定取 28，避开大小月问题）。"""
    d = datetime.date.today()
    y, m = d.year, d.month - n
    while m <= 0:
        m += 12
        y -= 1
    return datetime.date(y, m, 28).isoformat()


def fred_series(series_id, start):
    """FRED 序列 → [(date, float)] 升序；缺失值 '.' 跳过；失败返回 []。"""
    url = (f"{config.FRED_BASE}?series_id={series_id}&api_key={config.FRED_API_KEY}"
           f"&file_type=json&sort_order=asc&limit={config.FRED_MACRO_LIMIT}"
           f"&observation_start={start}")
    j = fetch_gold_data.http_get_json(url)
    if not j or "observations" not in j:
        print(f"  ! FRED {series_id} 获取失败")
        return []
    out = []
    for o in j["observations"]:
        v = o.get("value")
        if v in (None, "", "."):
            continue
        try:
            out.append((o["date"], float(v)))
        except (TypeError, ValueError):
            continue
    return out


def yahoo_series(sym, rng=None):
    """Yahoo chart 日线 → [(date, close)]；复用 fetch_event.fetch_daily。"""
    rows = fetch_event.fetch_daily(sym=sym, rng=rng or config.YAHOO_RANGE_MACRO)
    return [(r["date"], r["close"]) for r in rows]


def ensure_gpr(force=False):
    """GPR 日频 xls：有缓存则复用，否则下载到 data/。返回路径或 None。"""
    p = config.GPR_CACHE
    if os.path.exists(p) and not force:
        print(f"  ✓ GPR 使用缓存 {os.path.basename(p)}（--force-gpr 可重下）")
        return p
    try:
        req = urllib.request.Request(config.GPR_XLS_URL,
                                     headers={"User-Agent": config.USER_AGENT})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        with open(p, "wb") as f:
            f.write(raw)
        print(f"  ✓ GPR 已下载 {len(raw):,} 字节 -> {p}")
        return p
    except Exception as e:
        print(f"  ! GPR 下载失败：{type(e).__name__}: {str(e)[:100]}")
        return p if os.path.exists(p) else None


def gpr_series(path):
    """读 GPRD_MA30 列 → [(date, ma30)]；xlrd 2.x 可读 CDFV2 xls。"""
    if not path or not os.path.exists(path):
        return []
    try:
        import xlrd
        sh = xlrd.open_workbook(path).sheet_by_index(0)
        head = [str(x).strip() for x in sh.row_values(0)]
        i_day, i_ma = head.index("DAY"), head.index("GPRD_MA30")
        out = []
        for r in range(1, sh.nrows):
            day, ma = sh.cell_value(r, i_day), sh.cell_value(r, i_ma)
            try:
                s = str(int(float(day))).zfill(8)
                d = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
                v = float(ma)
            except (TypeError, ValueError):
                continue
            out.append((d, v))
        out.sort()
        return out[-config.GPR_DAYS:]
    except Exception as e:
        print(f"  ! GPR 解析失败：{type(e).__name__}: {str(e)[:100]}")
        return []


def weekly(points, weeks=None):
    """日频 → 周频：按 ISO 周分组取每周最后一个有效值，保留最近 weeks 周。"""
    weeks = weeks or config.MACRO_SERIES_WEEKS
    bucket = {}
    for d, v in sorted(points):
        try:
            iso = datetime.date.fromisoformat(d).isocalendar()
        except ValueError:
            continue  # 季度标签等非法日期不参与降采样
        bucket[(iso[0], iso[1])] = (d, v)
    return [bucket[k] for k in sorted(bucket)][-weeks:]


def main():
    ap = argparse.ArgumentParser(description="抓取 A2–A6 宏观因子 -> data/gold_data.xlsx")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写 Excel")
    ap.add_argument("--force-gpr", action="store_true", help="强制重下 GPR xls")
    ap.add_argument("--no-gpr", action="store_true", help="跳过 GPR 抓取，沿用已有现值")
    args = ap.parse_args()

    excelio.ensure_workbook()
    start = months_ago_str(config.FRED_MACRO_START_MONTHS)
    print(f"[宏观因子抓取] 起始 {start} · 目标窗口 {config.MACRO_SERIES_WEEKS} 周")

    # ---------- A2 实际利率 ----------
    print("[1] A2 实际利率 · FRED DFII10")
    a2_all = fred_series(config.FRED_SERIES_MACRO["A2"], start)
    a7_all = fred_series(config.FRED_SERIES_MACRO["A7"], start)
    print(f"  ✓ DFII10 {len(a2_all)} 个观测；T10YIE(A7 通胀预期) {len(a7_all)} 个")

    # ---------- A3 美元指数 ----------
    print("[2] A3 美元指数 · Yahoo " + config.YAHOO_SYM["dxy"])
    a3_all = yahoo_series(config.YAHOO_SYM["dxy"])
    print(f"  ✓ ICE DXY {len(a3_all)} 个交易日")

    # ---------- A4 央行购金（复用现有 GDT 季度 sheet）----------
    print("[3] A4 央行购金 · 复用「黄金供需季度」（WGC 口径）")
    gdt = excelio.read_gdt_quarterly()
    a4_all = [(r["quarter"], float(r["cb"])) for r in gdt][-config.MACRO_A4_QUARTERS:]
    print(f"  ✓ 最近 {len(a4_all)} 个季度，最新 {a4_all[-1] if a4_all else '—'}")

    # ---------- A5 地缘风险 ----------
    print("[4] A5 地缘风险 · GPR 指数 GPRD_MA30")
    if args.no_gpr:
        a5_all, gpr_path = [], None
        print("  - 已跳过（--no-gpr）")
    else:
        gpr_path = ensure_gpr(args.force_gpr)
        a5_all = gpr_series(gpr_path)
        print(f"  ✓ {len(a5_all)} 天，最新 {a5_all[-1] if a5_all else '—'}")

    # ---------- A6 金油比 ----------
    print("[5] A6 金油比 · Yahoo GC=F ÷ FRED DCOILWTICO")
    gold_all = yahoo_series(config.YAHOO_SYM["gold"])
    wti_all = fred_series(config.FRED_SERIES_MACRO["oil"], start)
    wti = dict(wti_all)
    gold = dict(gold_all)
    a6_all = [(d, gold[d] / wti[d]) for d in sorted(set(gold) & set(wti)) if wti[d] > 0]
    print(f"  ✓ 金价 {len(gold_all)} / WTI {len(wti_all)} / 可比日 {len(a6_all)}；"
          f"最新 {a6_all[-1] if a6_all else '—'}")

    # ---------- A7 通胀预期 ----------
    print("[6] A7 通胀预期 · FRED T10YIE")
    print(f"  ✓ {len(a7_all)} 个观测，最新 {a7_all[-1] if a7_all else '—'}")

    # ---------- A8 风险偏好 ----------
    print("[7] A8 风险偏好 · Yahoo " + config.YAHOO_SYM["vix"])
    a8_all = yahoo_series(config.YAHOO_SYM["vix"])
    print(f"  ✓ VIX {len(a8_all)} 个交易日，最新 {a8_all[-1] if a8_all else '—'}")

    # ---------- 组装 ----------
    spec = [
        ("A2", "实际利率 TIPS", a2_all, "%", "FRED DFII10",
         "10Y TIPS 收益率（市场口径实际利率）；非 DGS10−T10YIE 构造值", lambda v: f"{v:.2f}"),
        ("A3", "美元指数", a3_all, "", "Yahoo DX-Y.NYB (ICE DXY)",
         "ICE DXY；与 FRED 广义美元 DTWEXBGS 量级不同，不可混用", lambda v: f"{v:.2f}"),
        ("A4", "央行及其他机构净购金", [], "吨/季", "WGC GDT 季度（复用本地 sheet）",
         "WGC 口径季度值；与 IFS 年度净购金非同一口径", lambda v: f"{v:.1f}"),
        ("A5", "地缘政治风险指数", a5_all, "MA30", "Caldara-Iacoviello GPR",
         "报纸词频代理指标，30 日均；非价格、非直接避险溢价", lambda v: f"{v:.1f}"),
        ("A6", "金油比", a6_all, "桶/盎司", "Yahoo GC=F ÷ FRED DCOILWTICO",
         "COMEX 期货金价 ÷ WTI 现货；仅作趋势观察", lambda v: f"{v:.1f}"),
        ("A7", "通胀预期", a7_all, "%", "FRED T10YIE",
         "10Y 盈亏平衡通胀率；通胀预期上行为黄金保值需求提供支撑", lambda v: f"{v:.2f}"),
        ("A8", "风险偏好 VIX", a8_all, "", "Yahoo ^VIX",
         "CBOE 波动率指数；VIX 下行=风险偏好回升（压制黄金），上行=避险升温", lambda v: f"{v:.1f}"),
    ]

    series, latest = {}, []
    prev = {r["key"]: r for r in excelio.read_macro_latest()}
    for key, name, raw, unit, source, note, fmt in spec:
        if key == "A4":
            pts = [{"d": str(d), "v": float(v)} for d, v in a4_all]
        else:
            pts = [{"d": d, "v": float(v)} for d, v in weekly(raw)]
        if not pts and key in prev:  # 抓取失败时保留上次现值，不写空
            print(f"  ! {key} 无新数据，沿用上次现值")
            latest.append(prev[key])
            continue
        series[key] = pts
        last = pts[-1]
        latest.append({
            "key": key, "name": name, "value": fmt(last["v"]), "date": last["d"],
            "unit": unit, "source": source, "note": note,
        })

    print("\n现值汇总：")
    for r in latest:
        print(f"  {r['key']} {r['name']:<14s} {r['value']:>9s} {r['unit']:<8s} "
              f"({r['date']}) · {r['source']}")
    print("\n时序点数：" + " ".join(f"{k}={len(v)}" for k, v in sorted(series.items())))

    if args.dry_run:
        print("\n[dry-run] 未写入文件")
        return 0

    n1, n2 = excelio.write_macro(latest, series)
    excelio.touch_meta()
    print(f"\n✓ 已写入 {n1} 行现值 / {n2} 行时序 -> {paths.DATA_XLSX}")
    print("  下一步：python3 src/build_html.py   # 注入 output/gold-terminal.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
