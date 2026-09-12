# -*- coding: utf-8 -*-
"""把「2002–2026 年秦皇岛 Q5500 动力煤年均价与周期阶段」SVG
移入 china-coal-dashboard.html 的「长期趋势专区」作为第 7 项，
并删除原先挂在看板末尾的整段「煤炭行业周期」章节。

幂等：靠注释标记 + key 去重，可重复运行。
"""
import json
import re
import os

# ── 路径基准 ───────────────────────────────────────────────────────
# 本脚本位于 <项目根>/src/，统一把工作目录切到项目根，
# 让「数据源/…」「svg/…」「china-coal-dashboard.html」等既有相对路径
# 保持有效——无论从哪个目录执行，结果都一致。
import os as _os
_os.chdir(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

DASH = "china-coal-dashboard.html"
SVG = os.path.join("svg", "煤炭周期复盘.svg")
KEY = "cycle_coal_price"

BEGIN = "<!-- BEGIN 煤炭行业周期（由周期分析框架同步） -->"
END = "<!-- END 煤炭行业周期 -->"

CSS_MARK = "/* ===== 煤炭行业周期章节（由周期分析框架同步附带） ====="
NEW_CSS = (
    "/* ===== 煤炭行业周期图（长期趋势专区 第 7 项） ===== */\n"
    "  .cycle-chart{margin:2px 0 8px;}\n"
    "  .cycle-chart svg{display:block;width:100%;height:auto;"
    "border:1px solid var(--line);border-radius:10px;background:#fff;}\n"
)

DETAILS_MARK = "<!-- 7 煤炭行业周期 -->"

FOOT = (
    "数据口径：秦皇岛港 Q5500 动力煤年均价（元/吨），2002–2026；2026 为 1–8 月均值（虚线，年内未完成）；"
    "年度长协价 =「基准价 + 浮动价」月度挂牌价年均值，2017 年起；"
    "七阶段划分依据产能政策与供需格局；2015 底部采用年均价口径 410（非时点低点 370）；"
    "行业亏损面为萧条期同步确认指标（2015 约 80%、2025 为 53.6%）"
)

SUBH = "2002–2026 年秦皇岛 Q5500 动力煤年均价与周期阶段"


def load_svg():
    """读 SVG，剥掉根标签上的固定 width/height（与看板其它趋势图一致，只留 viewBox 自适应）"""
    s = open(SVG, encoding="utf-8").read().strip()
    m = re.match(r'(<svg\b[^>]*?)\s+width="\d+"\s+height="\d+"([^>]*>)', s)
    if m:
        s = m.group(1) + m.group(2) + s[m.end():]
    return s


def build_details():
    return f"""
  {DETAILS_MARK}
  <details open>
    <summary><span class="idx" style="width:22px;height:22px;font-size:12px;border-radius:6px">7</span> 煤炭行业周期</summary>
    <div class="trend-body">
      <div class="trend-sub-h">{SUBH}</div>
      <div class="cycle-chart" data-img="{KEY}" data-title="{SUBH}"></div>
      <div class="trend-foot">{FOOT}</div>
    </div>
  </details>
"""


def main():
    html = open(DASH, encoding="utf-8").read()
    orig_len = len(html)
    svg = load_svg()

    # ── 1) 删除看板末尾的整段「煤炭行业周期」章节
    if BEGIN in html and END in html:
        i = html.find(BEGIN)
        j = html.find(END) + len(END)
        # 连同其后多余空行一起收掉
        k = j
        while k < len(html) and html[k] in "\r\n":
            k += 1
        html = html[:i].rstrip("\n") + "\n" + html[k:]
        print("1) 已删除末尾「煤炭行业周期」章节")
    else:
        print("1) 末尾章节不存在（已处理过），跳过")

    # ── 2) CSS：换掉旧块，只留 .cycle-chart
    if CSS_MARK in html:
        i = html.find(CSS_MARK)
        j = html.find("</style>", i)
        html = html[:i] + NEW_CSS + html[j:]
        print("2) 已替换为 .cycle-chart 样式")
    elif ".cycle-chart{" not in html:
        j = html.find("</style>")
        html = html[:j] + NEW_CSS + html[j:]
        print("2) 已插入 .cycle-chart 样式")
    else:
        print("2) 样式已存在，跳过")

    # ── 3) __CHARTS__ 增加 key
    # 注意：SVG 内含 \" 转义，正则必须「字符级」处理转义，
    # 否则 [^"]* 会在第一个 \" 处截断，只删掉半个条目、留下孤儿文本（曾导致 JS 语法错误）。
    if f'"{KEY}"' in html:
        pat = re.compile(r'\n  "' + KEY + r'": "(?:[^"\\]|\\.)*",?')
        html, n = pat.subn("", html, count=1)
        print(f"3) __CHARTS__ 已含 {KEY}，移除旧值（{n} 处）后重写")
    entry = '\n  ' + json.dumps(KEY, ensure_ascii=False) + ': ' + json.dumps(svg, ensure_ascii=False)
    anchor = "\n};\nCommonCharts.injectCharts"
    idx = html.find(anchor)
    if idx < 0:
        raise SystemExit("未找到 __CHARTS__ 结束锚点")
    # 上一条目若已带尾逗号就不再补，避免产生 ",,"（JS 对象字面量会直接语法错误）
    head = html[:idx]
    html = head + ("" if head.rstrip().endswith(",") else ",") + entry + html[idx:]
    print(f"3) 已写入 __CHARTS__['{KEY}']（{len(svg)} 字符 SVG）")

    # ── 4) 长期趋势专区插入第 7 项
    if DETAILS_MARK in html:
        print("4) 第 7 项已存在，跳过")
    else:
        anchor2 = "\n\n</div>\n\n<!-- 趋势图模态框 -->"
        k = html.find(anchor2)
        if k < 0:
            raise SystemExit("未找到 .trend-section 结束锚点")
        html = html[:k] + build_details() + html[k:]
        print("4) 已插入「7 煤炭行业周期」")

    open(DASH, "w", encoding="utf-8").write(html)
    print(f"\n写入 {DASH}：{orig_len:,} → {len(html):,} 字符")


if __name__ == "__main__":
    main()
