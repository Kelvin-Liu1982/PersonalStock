# -*- coding: utf-8 -*-
"""
把 svg/ 目录下重生成的 *.svg 按文件名（去扩展名即 key）写回看板 HTML 的
var __CHARTS__ = {...} 对象中。

设计要点：
  - __CHARTS__ 是单行 JS 对象，每条目形如：
        \n  "key": "<svg ... 内部引号转义为 \\">",
    SVG 内容里的双引号被转义成 \\"，因此「旧值清除」正则必须用
    (?:[^"\\]|\\.)* 而非 [^"]*，否则会在第一个 \\" 处截断留下孤儿文本，
    导致 SyntaxError。
  - 只替换 __CHARTS__ 中【已存在】的 key（文件名去扩展名 == key）。
    文件名与 key 不匹配的 svg（如中文名 煤炭周期复盘.svg 对应 key=cycle_coal_price）
    会被跳过并提示——这类由 move_cycle_to_trend.py 单独处理，不要在此覆盖。
  - 幂等：重跑读当前 __CHARTS__ 再按 svg/ 重写，结果稳定。
  - 仅写 HTML，绝不回写 xlsx。

用法（在 china-coal/ 目录下）：
    python3 src/reinject_svgs.py china-coal-dashboard.html svg
依赖：无第三方库（仅标准库）。
"""
import sys
import os
import re


def main():
    if len(sys.argv) < 3:
        print("用法: python3 reinject_svgs.py <dashboard.html> <svg_dir>")
        sys.exit(1)
    html_path = sys.argv[1]
    svg_dir = sys.argv[2]
    html = open(html_path, encoding="utf-8").read()

    marker = "var __CHARTS__ = {"
    i = html.index(marker)
    j = html.index("</script>", i)
    head = html[:i]            # marker 之前
    block = html[i + len(marker):j]   # 对象主体
    tail = html[j:]            # '</script>' 及其之后

    n_replaced = 0
    n_skipped = 0
    for fn in sorted(os.listdir(svg_dir)):
        if not fn.endswith(".svg"):
            continue
        key = fn[:-4]
        raw = open(os.path.join(svg_dir, fn), encoding="utf-8").read().strip()
        # 转义：先反斜杠，再双引号（与 JS 字符串字面量一致）
        esc = raw.replace("\\", "\\\\").replace('"', '\\"')
        # 转义感知条目匹配：捕获前缀、可选尾部逗号
        pat = re.compile(r'(\n  "' + re.escape(key) + r'": )"(?:[^"\\]|\\.)*"(,?)')
        m = pat.search(block)
        if not m:
            print(f"⚠️  跳过（__CHARTS__ 中无 key '{key}'）：{fn}")
            n_skipped += 1
            continue
        block = pat.sub(
            lambda mm: mm.group(1) + '"' + esc + '"' + mm.group(2),
            block,
            count=1,
        )
        n_replaced += 1

    new_html = head + marker + block + tail
    open(html_path, "w", encoding="utf-8").write(new_html)
    print(f"✅ 写回 {n_replaced} 个 svg 到 __CHARTS__（跳过 {n_skipped} 个不匹配 key）")


if __name__ == "__main__":
    main()
