#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 3: 把各看板外链 <img src="...svg"> 大图改为内联 data-img + __CHARTS__ 统一注入
（cosco 同款 common/charts.js 的 injectCharts 机制）。

- 一次迁移（migrate）：扫描 <img src="...svg"> / <figure><img> / data-svg="...svg">，
  替换为 <div data-img="KEY"> / <figure data-img="KEY"> / data-svg="KEY"，
  生成 var __CHARTS__ = {...} 并调用 CommonCharts.injectCharts。
- 可重复（rebuild）：迁移后 HTML 已无 <img src="...svg">，此时扫描 data-img / data-svg
  占位键，重新读取磁盘 svg 文件生成 __CHARTS__（用于数据更新后重跑）。

用法:
  python3 common/embed_svgs_phase3.py            # 迁移 coal / mobile / telecom
  python3 common/embed_svgs_phase3.py --only mobile   # 只跑某个看板
  python3 common/embed_svgs_phase3.py --dry       # 不改写，只打印将要做的事

依赖: 各看板需在 <head>/<body> 已引入 ../common/charts.js（coal/mobile/telecom 均已引入）。
"""
import os
import re
import sys
import json

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DASHBOARDS = {
    "coal": {
        "html": "china-coal/china-coal-dashboard.html",
        "svg_dir": "china-coal/svg",
        "kind": "coal",
    },
    "mobile": {
        "html": "china-mobile/china-mobile-dashboard.html",
        "svg_dir": "china-mobile/svg 图",
        "kind": "figure",
    },
    "telecom": {
        "html": "china-telecom/china-telecom-dashboard.html",
        "svg_dir": "china-telecom/svg",
        "kind": "figure",
    },
}

MARKER_RE = re.compile(r"<!--\s*Phase 3.*?</script>\s*", re.S | re.I)


def sanitize(svg: str) -> str:
    """防止内联 SVG 中出现字面量 </script> 提前闭合外层 <script> 块。"""
    return re.sub(r"</script", r"<\\/script", svg, flags=re.I)


def read_svg_by_key(svg_dir: str, key: str):
    cand = os.path.join(svg_dir, key + ".svg")
    if os.path.exists(cand):
        with open(cand, encoding="utf-8") as f:
            return f.read()
    for root, _, files in os.walk(svg_dir):
        if (key + ".svg") in files:
            with open(os.path.join(root, key + ".svg"), encoding="utf-8") as f:
                return f.read()
    return None


def collect_keys_from_svg_dir(svg_dir: str):
    keys = []
    for root, _, files in os.walk(svg_dir):
        for fn in files:
            if fn.endswith(".svg"):
                keys.append(fn[:-4])
    return sorted(set(keys))


def migrate_coal(html: str):
    # 1) sparkline: <span class="spark" ...><img src="svg/spark_X.svg" ...></span>
    #    -> <span class="spark" data-img="spark_X"></span>
    html = re.sub(
        r'<span class="spark"[^>]*>\s*<img src="svg/([^"]+?)\.svg"[^>]*>\s*</span>',
        r'<span class="spark" data-img="\1"></span>',
        html,
    )
    # 2) 趋势大图: 独立 <img src="svg/trend_X.svg" ...> -> <div data-img="trend_X"></div>
    html = re.sub(
        r'<img src="svg/([^"]+?)\.svg"[^>]*>',
        r'<div data-img="\1"></div>',
        html,
    )
    # 3) CHART_MAP 的 q/y 路径 -> KEY
    html = re.sub(
        r'([qy]):\s*"svg/([^"]+?)\.svg"',
        r'\1: "\2"',
        html,
    )
    # 4) 模态框: <img id="trendModalImg"> -> <div class="trend-body" id="trendModalBody">
    html = re.sub(
        r'<img id="trendModalImg"[^>]*>',
        r'<div class="trend-body" id="trendModalBody"></div>',
        html,
    )
    # 5) createTrendModal 配置: img -> body，render 改为读 __CHARTS__
    html = re.sub(
        r"title:\s*'#trendModalTitle',\s*img:\s*'#trendModalImg',",
        r"title: '#trendModalTitle', body: '#trendModalBody',",
        html,
    )
    html = re.sub(
        r"render:\s*function\s*\(ctx,\s*m,\s*period\)\s*\{\s*"
        r"ctx\.img\.src\s*=\s*m\[period\];",
        r"render: function (ctx, m, period) {\n"
        r"      var payload = __CHARTS__[m[period]];\n"
        r"      if (ctx.body) ctx.body.innerHTML = payload || '';",
        html,
    )
    return html


def migrate_figure(html: str):
    # 1) <figure class="svgi" id="ID"><img src="PATH.svg" alt="..."></figure>
    #    -> <figure class="svgi" id="ID" data-img="KEY"></figure>
    def fig_repl(m):
        attrs = m.group(1) or ""
        path = m.group(2)
        key = os.path.basename(path)
        return '<figure class="svgi"%s data-img="%s"></figure>' % (attrs, key)

    html = re.sub(
        r'<figure class="svgi"( id="[^"]*")?>\s*<img src="([^"]+?)\.svg" alt="[^"]*">\s*</figure>',
        fig_repl,
        html,
    )
    # 2) 按钮 data-svg="PATH.svg" -> data-svg="KEY"
    html = re.sub(
        r'data-svg="([^"]+?)\.svg"',
        lambda m: 'data-svg="%s"' % os.path.basename(m.group(1)),
        html,
    )
    # 3) 弹窗委托: var src=b.getAttribute('data-svg'); -> 改从 __CHARTS__ 取内联 SVG
    html = re.sub(
        r"var src=b\.getAttribute\('data-svg'\);",
        r"var key=b.getAttribute('data-svg');\n    var src=__CHARTS__[key];",
        html,
    )
    return html


def collect_referenced_keys(html: str, kind: str):
    keys = set(re.findall(r'data-img="([^"]+)"', html))
    keys |= set(re.findall(r'data-svg="([^"]+)"', html))
    if kind == "coal":
        # CHART_MAP 里的 q/y 键
        for k in re.findall(r'(?:q|y):\s*"([^"]+)"', html):
            # 仅收集看起来像 svg key 的（无扩展名、无路径斜杠）
            if "/" not in k and not k.endswith(".svg"):
                keys.add(k)
    return keys


def make_marker(charts: dict) -> str:
    js = json.dumps(charts, ensure_ascii=False, indent=2)
    return (
        "\n<!-- Phase 3: 内联 SVG 统一注入（由 common/embed_svgs_phase3.py 生成，勿手改） -->\n"
        '<script>var __CHARTS__ = ' + js + ";\n"
        'CommonCharts.injectCharts("[data-img]", __CHARTS__);</script>\n'
    )


def process(name, cfg, dry=False):
    html_path = os.path.join(WS, cfg["html"])
    svg_dir = os.path.join(WS, cfg["svg_dir"])
    kind = cfg["kind"]
    with open(html_path, encoding="utf-8") as f:
        html = f.read()

    # 判断是否已经迁移（不存在外链 svg 的 <img>，但存在 data-img 占位）
    has_img_ref = bool(re.search(r'<img src="[^"]*?\.svg"', html))
    has_data_img = 'data-img="' in html

    if has_img_ref or not has_data_img:
        mode = "migrate"
        if kind == "coal":
            html = migrate_coal(html)
        else:
            html = migrate_figure(html)
    else:
        mode = "rebuild"

    # 收集键并读取 svg
    keys = collect_referenced_keys(html, kind)
    charts = {}
    missing = []
    for k in sorted(keys):
        svg = read_svg_by_key(svg_dir, k)
        if svg is None:
            missing.append(k)
        else:
            charts[k] = sanitize(svg)

    # 若 rebuild 且 charts 为空（svg 已被删），用 svg 目录全量兜底
    if not charts and os.path.isdir(svg_dir):
        for k in collect_keys_from_svg_dir(svg_dir):
            svg = read_svg_by_key(svg_dir, k)
            if svg:
                charts[k] = sanitize(svg)

    if missing:
        print("  [WARN] %s: 以下键在 %s 找不到对应 svg 文件: %s"
              % (name, svg_dir, ", ".join(missing)))

    # 注入 / 更新 __CHARTS__ 脚本块
    marker = make_marker(charts)
    if MARKER_RE.search(html):
        html = MARKER_RE.sub(marker, html, count=1)
        injected = "updated"
    else:
        html = html.replace("</body>", marker + "</body>", 1)
        injected = "inserted"

    if dry:
        print("  [DRY] %s: mode=%s, 占位键=%d, 内联图表=%d, 注入=%s"
              % (name, mode, len(keys), len(charts), injected))
        return

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("  [OK] %s: mode=%s, 占位键=%d, 内联图表=%d, 注入=%s, 文件=%s"
          % (name, mode, len(keys), len(charts), injected, cfg["html"]))


def main():
    only = None
    dry = False
    args = sys.argv[1:]
    if "--dry" in args:
        dry = True
        args.remove("--dry")
    if "--only" in args:
        i = args.index("--only")
        only = args[i + 1]
    if only:
        if only not in DASHBOARDS:
            print("未知看板: %s (可选: %s)" % (only, ", ".join(DASHBOARDS)))
            sys.exit(1)
        targets = {only: DASHBOARDS[only]}
    else:
        targets = DASHBOARDS

    for name, cfg in targets.items():
        print("处理 %s ..." % name)
        process(name, cfg, dry=dry)


if __name__ == "__main__":
    main()
