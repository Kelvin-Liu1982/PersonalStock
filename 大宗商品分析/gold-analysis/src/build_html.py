#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_html.py —— 读 data/gold_data.xlsx，把数据注入 output/gold-terminal.html。

用法（在 gold-analysis/ 下运行）:
  python3 src/build_html.py                 注入数据块（常用）
  python3 src/build_html.py --check         只校验并预览，不写文件
  python3 src/build_html.py --strip-node-ids  顺带清掉 data-page-node-id（部署前用）

典型流程:
  python3 src/fetch_gold_data.py && python3 src/build_html.py

只替换这两组标记之间的内容，绝不碰布局 / CSS / 其它 JS:
  /*GOLD_DATA_START*/       ... /*GOLD_DATA_END*/        -> 标量字段（TICKER / HERO / stat 卡）
  /*GOLD_PANEL_DATA_START*/ ... /*GOLD_PANEL_DATA_END*/  -> 央行购金图1图2 + 价格时间轴 + 美债面板 + 推演参数

页面上的死 SVG 已全部改为数据驱动：改数据请改 Excel 后跑本脚本，
不要手改 HTML 里这两个标记之间的内容（下次构建会被覆盖）。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import excelio
import paths

MARK_GOLD = re.compile(r"/\*GOLD_DATA_START\*/[\s\S]*?/\*GOLD_DATA_END\*/")
MARK_PANEL = re.compile(r"/\*GOLD_PANEL_DATA_START\*/[\s\S]*?/\*GOLD_PANEL_DATA_END\*/")
# 「上涨驱动权重」脚注（央行购金最新季度）的静态占位，构建时同步，避免首屏闪现旧季度
MARK_WFOOT = re.compile(r'(<div class="wfoot" id="wfootCb"[^>]*>)[\s\S]*?(</div>)')

# 可视化编辑器会给每个节点注入 data-page-node-id（本文件 471 个，约 +2 万字符）。
# 它是编辑器的节点追踪标记，对渲染无用，部署前可清掉。
# 注意只清这一个属性：data-field（数据绑定）与 data-w（权重条原始属性）必须保留。
NODE_ID_ATTR = re.compile(r'\s+data-page-node-id=("[^"]*"|\'[^\']*\')')


def strip_node_ids(html):
    """移除 data-page-node-id，返回 (新 html, 移除个数)。"""
    return NODE_ID_ATTR.subn("", html)


def to_json(obj):
    """序列化为可安全内嵌 <script> 的 JSON。"""
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    return s.replace("</", "<\\/")  # 防止数据里出现 </script> 提前闭合标签


def build_forces(macro_latest, macro_series, gold):
    """力矩阵状态灯：当前值 + 近 4 周变化 + 指标方向 + 对金价信号。

    同源指标镜像处理：A3(DXY) 同时驱动「推涨③美元走弱」与「压制①美元走强」，
    A2(TIPS 实际利率) 同时驱动「推涨④实利率下行」与「压制④实利率上行」，
    两列取相反语义，避免同一指标出现自相矛盾的显示。
    指标方向（dir）始终表示指标自身变化方向；tone 表示该卡身份下对金价的净信号。
    """
    latest = {m["key"]: m for m in (macro_latest or []) if isinstance(m, dict)}

    def _num(s):
        try:
            return float(str(s).replace(",", "").replace("%", "").strip())
        except (TypeError, ValueError):
            return None

    def _chg(key, weeks=4):
        ser = (macro_series or {}).get(key) or []
        if len(ser) < weeks + 1:
            return None
        try:
            return float(ser[-1]["v"]) - float(ser[-1 - weeks]["v"])
        except (TypeError, ValueError, KeyError):
            return None

    def _dir(c):
        if c is None or abs(c) < 1e-9:
            return "flat"
        return "up" if c > 0 else "down"

    out = []

    # 推涨① 避险需求 ← A5 地缘政治风险指数 GPR（上升 = 避险升温，利多）
    a5 = latest.get("A5")
    if a5:
        v, c = _num(a5.get("value")), _chg("A5")
        out.append({
            "id": "fsig_bullSafe", "name": "GPR 地缘风险",
            "val": f"{v:.1f}" if v is not None else "—",
            "unit": a5.get("unit") or "", "chg": f"{c:+.1f}" if c is not None else "—",
            "dir": _dir(c),
            "tag": "避险升温" if (c or 0) > 0 else "避险降温",
            "tone": "bull" if (c or 0) > 0 else "neutral",
            "src": "Caldara-Iacoviello",
        })

    # 推涨③ 美元走弱 / 压制① 美元走强 ← A3 ICE DXY（同源镜像）
    a3 = latest.get("A3")
    if a3:
        v, c = _num(a3.get("value")), _chg("A3")
        vtxt = f"{v:.2f}" if v is not None else "—"
        ctxt = f"{c:+.2f}" if c is not None else "—"
        out.append({
            "id": "fsig_bullUsd", "name": "DXY 美元指数",
            "val": vtxt, "unit": "", "chg": ctxt, "dir": _dir(c),
            "tag": "美元走弱 · 推涨生效" if (c or 0) < 0 else "美元偏强 · 未生效",
            "tone": "bull" if (c or 0) < 0 else "neutral",
            "src": "ICE DXY",
        })
        out.append({
            "id": "fsig_bearUsd", "name": "DXY 美元指数",
            "val": vtxt, "unit": "", "chg": ctxt, "dir": _dir(c),
            "tag": "美元走强 · 压制生效" if (c or 0) > 0 else "美元走弱 · 压制减弱",
            "tone": "bear" if (c or 0) > 0 else "neutral",
            "src": "ICE DXY",
        })

    # 推涨④ 实际利率下行 / 压制④ 实际利率上行 ← A2 10Y TIPS（同源镜像）
    a2 = latest.get("A2")
    if a2:
        v, c = _num(a2.get("value")), _chg("A2")
        vtxt = f"{v:.2f}%" if v is not None else "—"
        ctxt = f"{c:+.2f}" if c is not None else "—"
        out.append({
            "id": "fsig_bullReal", "name": "10Y TIPS 实利率",
            "val": vtxt, "unit": "", "chg": ctxt, "dir": _dir(c),
            "tag": "实利率下行 · 推涨生效" if (c or 0) < 0 else "实利率上行 · 未生效",
            "tone": "bull" if (c or 0) < 0 else "neutral",
            "src": "FRED DFII10",
        })
        out.append({
            "id": "fsig_bearReal", "name": "10Y TIPS 实利率",
            "val": vtxt, "unit": "", "chg": ctxt, "dir": _dir(c),
            "tag": "实利率上行 · 压制生效" if (c or 0) > 0 else "实利率下行 · 压制减弱",
            "tone": "bear" if (c or 0) > 0 else "neutral",
            "src": "FRED DFII10",
        })

    # 压制③ 加息预期 ← 10Y 名义利率（行情快照 tickerUst，无周序列，取最新变动）
    uv, uc = _num((gold or {}).get("tickerUst")), _num((gold or {}).get("tickerUstChg"))
    if uv is not None:
        out.append({
            "id": "fsig_bearHike", "name": "10Y 名义利率",
            "val": f"{uv:.2f}%", "unit": "", "chg": f"{uc:+.2f}" if uc is not None else "—",
            "dir": _dir(uc),
            "tag": "加息压力升" if (uc or 0) > 0 else "加息压力缓和",
            "tone": "bear" if (uc or 0) > 0 else "neutral",
            "src": "10Y UST",
        })

    # 推涨② 通胀预期 ← A7 10Y 盈亏平衡通胀率（通胀预期上升 = 保值需求增，利多）
    a7 = latest.get("A7")
    if a7:
        v, c = _num(a7.get("value")), _chg("A7")
        out.append({
            "id": "fsig_bullInfl", "name": "10Y 通胀预期",
            "val": f"{v:.2f}%" if v is not None else "—",
            "unit": "", "chg": f"{c:+.2f}" if c is not None else "—",
            "dir": _dir(c),
            "tag": "通胀预期升温" if (c or 0) > 0 else "通胀预期回落",
            "tone": "bull" if (c or 0) > 0 else "neutral",
            "src": "FRED T10YIE",
        })

    # 压制② 风险偏好回升 ← A8 VIX（VIX 下行 = 风险偏好回升，压制生效）
    a8 = latest.get("A8")
    if a8:
        v, c = _num(a8.get("value")), _chg("A8")
        out.append({
            "id": "fsig_bearRisk", "name": "VIX 波动率",
            "val": f"{v:.1f}" if v is not None else "—",
            "unit": "", "chg": f"{c:+.1f}" if c is not None else "—",
            "dir": _dir(c),
            "tag": "风险偏好回升 · 压制生效" if (c or 0) < 0 else "避险升温 · 压制减弱",
            "tone": "bear" if (c or 0) < 0 else "neutral",
            "src": "CBOE ^VIX",
        })

    return out


def build_payload():
    """从 Excel 组装两个数据块。"""
    gold = excelio.read_snapshot()

    country = excelio.read_cb_country()
    monthly = excelio.read_cb_monthly()
    annual = excelio.read_cb_annual()
    gdt = excelio.read_gdt_quarterly()
    cn_monthly = excelio.read_cn_cb_monthly()
    debt = excelio.read_us_debt()
    meta = excelio.read_meta()
    events = excelio.read_events()
    macro_latest = excelio.read_macro_latest()
    macro_series = excelio.read_macro_series()
    gold_monthly = excelio.read_gold_monthly()

    panel = {
        "cbCountry": [{"name": r["name"], "value": r["value"]} for r in country],
        "cbMonthly": [{"month": r["month"], "value": r["value"]} for r in monthly],
        "cnMonthly": [
            {"month": r["month"], "reserve": r["reserve"],
             "add": r["add"], "streak": r["streak"]}
            for r in cn_monthly
        ],
        "cbAnnual": [
            {"year": r["year"], "value": r["value"], "note": r["note"]}
            for r in annual
        ],
        "gdtQuarter": [
            {"quarter": r["quarter"], "jewellery": r["jewellery"], "technology": r["technology"],
             "investment": r["investment"], "cb": r["cb"], "demand": r["demand"],
             "mine": r["mine"], "hedging": r["hedging"], "mineTotal": r["mineTotal"],
             "recycled": r["recycled"], "supply": r["supply"]}
            for r in gdt
        ],
        "debt": {
            "years": debt["years"],
            "debt": debt["debt"],
            "r": debt["r"],
            "n": debt["n"],
            "interest": debt["interest"],
            "rn": debt["rn"],
        },
        "meta": meta,
        # A 模块 A2–A6 宏观因子（fetch_macro.py 抓取）：现值徽章 + mini sparkline
        "macroLatest": macro_latest,
        "macroSeries": macro_series,
        "goldMonthly": gold_monthly,
        # 黄金事件流（fetch_event.py 抓取）：页面 event 条显示第 0 条
        "events": [{"date": r["date"], "title": r["title"], "source": r["source"],
                    "pct": r["pct"], "link": r["link"]} for r in events],
    }
    # 力矩阵状态灯（方案 B 第一步）：由 A2/A3/A5 + 10Y 名义利率派生，随数据自动刷新
    panel["forces"] = build_forces(macro_latest, macro_series, gold)
    # cbH1Summary：与图 3 全球央行年度净购金（cbAnnual 最新年份 YTD）同源，
    # 弃用旧的 "1–7 月 / H1 综合" 静态口径，避免注入写死的季度值。
    if annual:
        _a = annual[-1]
        gold["cbH1Summary"] = f"{_a['year']} 年至今 +{_a['value']:.0f}t"

    return gold, panel, country, monthly, debt, cn_monthly, events, gold_monthly


def main():
    ap = argparse.ArgumentParser(description="Excel -> output/gold-terminal.html")
    ap.add_argument("--check", action="store_true", help="只校验并预览，不写文件")
    ap.add_argument(
        "--strip-node-ids", action="store_true",
        help="清掉可视化编辑器注入的 data-page-node-id（减小体积，部署前用）。"
             "会破坏编辑器的节点追踪，且本脚本无法还原。",
    )
    args = ap.parse_args()

    excelio.ensure_workbook()

    if not os.path.exists(paths.TERMINAL_HTML):
        print(f"  ✗ 未找到终稿：{paths.TERMINAL_HTML}")
        return 1

    with open(paths.TERMINAL_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    missing = []
    if not MARK_GOLD.search(html):
        missing.append("GOLD_DATA_START/END")
    if not MARK_PANEL.search(html):
        missing.append("GOLD_PANEL_DATA_START/END")
    if missing:
        print("  ✗ HTML 中未找到标记：" + "、".join(missing))
        print("    请确认终稿文件完整（标记可能被误删）。")
        return 1

    gold, panel, country, monthly, debt, cn_monthly, events, gold_monthly = build_payload()

    # 预览
    print("待注入数据：")
    print(f"  行情快照字段：{len(gold)} 个")
    for k in ("spot", "tickerXau", "tickerUst", "tickerDxy", "cbChinaOwn",
              "worldDebt", "cbNet2025", "cnImportH1"):
        if k in gold:
            print(f"      {k:14s} = {gold[k]}")
    print(f"  央行购金国别：{len(country)} 个"
          + (f"（{country[0]['name']} {country[0]['value']:+g}t … {country[-1]['name']} {country[-1]['value']:+g}t）"
             if country else ""))
    print(f"  央行购金月度：{len(monthly)} 个月")
    _gd = panel.get("gdtQuarter", [])
    print(f"  全球黄金供需季度：{len(_gd)} 个季度"
          + (f"（{_gd[0]['quarter']} {_gd[0]['demand']:.1f}t … {_gd[-1]['quarter']} {_gd[-1]['demand']:.1f}t）"
             if _gd else ""))
    _ann = panel.get("cbAnnual", [])
    print(f"  央行购金年度：{len(_ann)} 年"
          + (f"（{_ann[0]['year']} {_ann[0]['value']:+g}t … {_ann[-1]['year']} {_ann[-1]['value']:+g}t）"
             if _ann else ""))
    print(f"  中国央行购金月度：{len(cn_monthly)} 个月"
          + (f"（{cn_monthly[0]['month']} {cn_monthly[0]['add']:+g} → {cn_monthly[-1]['month']} {cn_monthly[-1]['add']:+g} 万盎司）"
             if cn_monthly else ""))
    print(f"  美债数据：{len(debt['years'])} 年 {debt['years'][0] if debt['years'] else '—'}"
          f"–{debt['years'][-1] if debt['years'] else '—'}")
    print(f"  当年月度金价：{len(gold_monthly)} 个月"
          + (f"（{gold_monthly[0]['month']} ${gold_monthly[0]['price']:,.0f} → "
             f"{gold_monthly[-1]['month']} ${gold_monthly[-1]['price']:,.0f}）" if gold_monthly else ""))
    _ml = panel.get("macroLatest", [])
    _ms = panel.get("macroSeries", {})
    print(f"  宏观因子：{len(_ml)} 项 / 时序 {sum(len(v) for v in _ms.values())} 点"
          + ("（" + " · ".join(f"{r['key']} {r['value']}{r['unit']}" for r in _ml) + "）" if _ml else ""))
    print(f"  黄金事件流：{len(events)} 条"
          + (f"（最新 {events[0]['date']} {events[0]['pct'] or '—'} · {events[0]['source']}"
             f" · {events[0]['title'][:24]}）" if events else ""))
    for k in ("eventDate", "eventPct", "eventSource", "eventText"):
        if k in gold:
            print(f"      {k:14s} = {gold[k]}")

    # 编辑器节点标记统计（无论是否清理都报一下，方便判断要不要清）
    n_ids = len(NODE_ID_ATTR.findall(html))
    if n_ids:
        # 属性值是 ASCII，按实际编码计字节，不要按中文 3 字节估算
        saved_chars = sum(len(m.group(0)) for m in NODE_ID_ATTR.finditer(html))
        saved_bytes = sum(len(m.group(0).encode("utf-8")) for m in NODE_ID_ATTR.finditer(html))
        action = "本次将清理" if args.strip_node_ids else "保留（加 --strip-node-ids 可清理）"
        print(f"  编辑器节点标记：data-page-node-id × {n_ids} —— {action}，"
              f"可省 {saved_chars:,} 字符 / {saved_bytes:,} 字节")
    else:
        print("  编辑器节点标记：无（已是干净文件）")

    if args.check:
        print("\n[--check] 校验通过，未写入文件。")
        return 0

    new_html = MARK_GOLD.sub(
        "/*GOLD_DATA_START*/\nwindow.GOLD_DATA = " + to_json(gold) + ";\n/*GOLD_DATA_END*/",
        html, count=1,
    )
    new_html = MARK_PANEL.sub(
        "/*GOLD_PANEL_DATA_START*/\nwindow.GOLD_PANEL_DATA = " + to_json(panel) + ";\n/*GOLD_PANEL_DATA_END*/",
        new_html, count=1,
    )

    # 「上涨驱动权重」脚注的静态占位同步为最新季度（运行时 applyData 仍会再刷一次，
    # 此处只求首屏与数据一致，消除旧季度闪现）。
    _a4 = next((m for m in panel.get("macroLatest", []) if m.get("key") == "A4"), None)
    if _a4:
        try:
            _a4v = f"{float(_a4['value']):.1f}"
        except (TypeError, ValueError):
            _a4v = str(_a4["value"])
        _wf = ("央行购金：2022–24 每年净买 &gt;1000t，2025 约 863t，最新 "
               + str(_a4.get("date", "")) + " 净买 " + _a4v
               + "t（WGC 口径）；黄金占全球央行储备比重自 1996 年来首超美债。")
        new_html = MARK_WFOOT.sub(lambda m: m.group(1) + _wf + m.group(2), new_html, count=1)

    if args.strip_node_ids:
        new_html, removed = strip_node_ids(new_html)
        if removed:
            print(f"\n  ✓ 已清理 data-page-node-id × {removed}"
                  f"（页面编辑器节点追踪已失效，本脚本无法还原）")

    with open(paths.TERMINAL_HTML, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"\n✓ 已注入 -> {paths.TERMINAL_HTML}")
    # 注意：len() 是字符数，中文在 UTF-8 下占 3 字节，与磁盘字节数不同，需分别给出
    nchars, nbytes = len(new_html), len(new_html.encode("utf-8"))
    print(f"  大小 {nchars:,} 字符 / {nbytes:,} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
