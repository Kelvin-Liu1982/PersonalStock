# -*- coding: utf-8 -*-
"""校验中国移动看板：sparkline / SVG / 卡片数值一致性（只读，不写 HTML）。"""
import os, re
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
HTML = ROOT / "china-mobile-dashboard.html"

html = HTML.read_text(encoding="utf-8")

# 1. 解析 sparkMini 数据数组
spark_data = {}
for m in re.finditer(r"sparkMini\('([^']+)',\s*\[([^\]]*)\]", html):
    sid, arr = m.group(1), m.group(2)
    vals = []
    for token in arr.split(","):
        token = token.strip()
        if token in ("", "null", "None"):
            vals.append(None)
        else:
            vals.append(float(token))
    spark_data[sid] = vals

# 2. 提取所有 spark-mini 与 trend-btn 的 data-jump
sparks = re.findall(r'<span class="spark-mini" id="([^"]+)" data-jump="([^"]+)"></span>', html)
btns = re.findall(r'<button class="trend-btn" data-jump="([^"]+)">趋势</button>', html)
ids = set(re.findall(r'\bid="([^"]+)"', html))

print(f"sparkline 数量：{len(sparks)}")
print(f"趋势按钮数量：{len(btns)}")
print(f"按钮/sparkline 数量是否一致：{len(btns) == len(sparks)}")

missing_targets = [t for _, t in sparks if t not in ids]
print(f"data-jump 目标缺失：{missing_targets}")

# 3. SVG 数值标签解析
def parse_svg_vals(svg_path):
    if not svg_path.exists():
        return []
    txt = svg_path.read_text(encoding="utf-8")
    vals = []
    for m in re.finditer(r'<text[^>]*font-weight="600"[^>]*>([^<]+)</text>', txt):
        s = m.group(1).strip().replace("+", "").replace(",", "")
        try:
            vals.append(float(s))
        except ValueError:
            pass
    return vals


def parse_display(v_text):
    t = v_text.strip()
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None, None
    val = float(m.group())
    if "万亿" in t:
        val *= 10000
        unit = "万亿"
    elif "亿户" in t:
        unit = "亿户"
    elif "亿" in t:
        unit = "亿"
    elif "pp" in t:
        unit = "pp"
    elif "%" in t:
        unit = "%"
    elif "港元" in t:
        unit = "港元"
    elif "万站" in t:
        unit = "万站"
    elif "万家" in t:
        unit = "万家"
    elif "EFLOPS" in t:
        unit = "EFLOPS"
    elif "元" in t:
        unit = "元"
    else:
        unit = ""
    return val, unit


print("\n" + "=" * 70)
print("一致性校验")
print("=" * 70)

svg_mismatches = []
disp_mismatches = []
ok_count = 0

for sid, target in sparks:
    vals = spark_data.get(sid, [])
    svg_path = ROOT / "svg 图" / target.split("_")[0] / f"{target}.svg"
    svg_vals = parse_svg_vals(svg_path)
    spark_nonnull = [v for v in vals if v is not None]

    # SVG 与 sparkline 比较
    svg_ok = len(spark_nonnull) == len(svg_vals) and all(
        abs(a - b) < 0.05 or (max(abs(a), abs(b)) > 0 and abs(a - b) / max(abs(a), abs(b)) < 0.005)
        for a, b in zip(spark_nonnull, svg_vals)
    )
    if not svg_ok:
        svg_mismatches.append(f"{sid}: sparkline={spark_nonnull} SVG={svg_vals}")

    # 最新数据点
    last_val = None
    for v in reversed(vals):
        if v is not None:
            last_val = v
            break
    if last_val is None:
        continue

    # 解析 .v：正确定位该 spark-mini 所在的 .metric div
    id_pos = html.find(f'id="{sid}"')
    if id_pos == -1:
        continue
    # 向前找最后一个 <div class="metric">
    start = html.rfind('<div class="metric">', 0, id_pos)
    if start == -1:
        continue
    # 向后找第一个 </div>
    end = html.find('</div>', id_pos)
    if end == -1:
        continue
    metric_block = html[start:end+6]
    v_match = re.search(r'<span class="v[^"]*"[^>]*>(.*?)</span>', metric_block)
    if not v_match:
        continue
    v_text = v_match.group(1)
    cur_val, unit = parse_display(v_text)
    if cur_val is None:
        continue

    tol = max(0.05, abs(last_val) * 0.005)
    match = abs(cur_val - last_val) <= tol
    status = "OK" if match else "不匹配"
    if match:
        ok_count += 1
    else:
        disp_mismatches.append(f"{sid}: 显示值 {v_text} != 最新 {last_val}")
    print(f"{sid}: {v_text:>22} -> 最新 {last_val:>10} [{status}]")

print("\n" + "=" * 70)
print(f"通过：{ok_count}/{len(sparks)}")
if svg_mismatches:
    print("\n【SVG / sparkline 不匹配】")
    for x in svg_mismatches:
        print(x)
else:
    print("【SVG / sparkline 全部一致】")
if disp_mismatches:
    print("\n【显示值 / 最新数据 不匹配】")
    for x in disp_mismatches:
        print(x)
else:
    print("【显示值均为 sparkline 最新数据】")

# 4. 基础标签/引用校验
print("\n" + "=" * 70)
print("标签与引用校验")
print("=" * 70)
for tag in ["div", "span", "figure", "table", "details", "script", "style", "button"]:
    o = len(re.findall(r'<%s[\s>]' % tag, html))
    c = len(re.findall(r'</%s>' % tag, html))
    print(f"<{tag}> open={o} close={c}{'  <-- MISMATCH' if o != c else ''}")
print(f"ch_payout 残留：{html.count('ch_payout')} | ch_capex：{html.count('ch_capex')} | ch_arpu：{html.count('ch_arpu')}")
