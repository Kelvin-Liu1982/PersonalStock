#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 3 静态校验：确认内联注入完整且无悬空引用。"""
import os, re, json, sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = {
    "coal": "china-coal/china-coal-dashboard.html",
    "mobile": "china-mobile/china-mobile-dashboard.html",
    "telecom": "china-telecom/china-telecom-dashboard.html",
}

ok = True
for name, rel in DASH.items():
    p = os.path.join(WS, rel)
    html = open(p, encoding="utf-8").read()
    print("== %s ==" % name)

    # 1) 无外链 svg <img>
    ext = re.findall(r'<img src="([^"]*?\.svg)"', html)
    if ext:
        ok = False
        print("  [FAIL] 仍存在外链 svg <img>:", ext[:5], "...")
    else:
        print("  [OK] 无外链 svg <img>")

    # 2) __CHARTS__ 可解析
    m = re.search(r"var __CHARTS__ = (\{.*?\});\nCommonCharts", html, re.S)
    if not m:
        ok = False
        print("  [FAIL] 未找到 __CHARTS__ 块")
        continue
    try:
        charts = json.loads(m.group(1))
        print("  [OK] __CHARTS__ 解析成功, 共 %d 个图表" % len(charts))
    except Exception as e:
        ok = False
        print("  [FAIL] __CHARTS__ JSON 解析错误:", e)
        continue

    # 3) 占位键全部可解析
    keys = set(re.findall(r'data-img="([^"]+)"', html))
    keys |= set(re.findall(r'data-svg="([^"]+)"', html))
    missing = [k for k in keys if k not in charts]
    if missing:
        ok = False
        print("  [FAIL] 占位键在 __CHARTS__ 中缺失:", missing)
    else:
        print("  [OK] 全部 %d 个占位键均可解析" % len(keys))

    # 4) 不应残留 svg/ 路径（coal CHART_MAP 等）
    leftover = re.findall(r'"svg/[^"]*?\.svg"', html)
    if leftover:
        ok = False
        print("  [FAIL] 残留 svg/ 路径:", leftover[:5])
    else:
        print("  [OK] 无残留 svg/ 路径")

    # 5) injectCharts 调用存在
    if "CommonCharts.injectCharts" not in html:
        ok = False
        print("  [FAIL] 缺少 injectCharts 调用")
    else:
        print("  [OK] injectCharts 调用存在")

print("\n结果:", "全部通过 ✅" if ok else "存在失败 ❌")
sys.exit(0 if ok else 1)
