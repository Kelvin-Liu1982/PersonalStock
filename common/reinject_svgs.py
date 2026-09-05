# -*- coding: utf-8 -*-
"""重新注入：把 build 脚本重新生成的 .svg 文件内容，按 key(=文件名去扩展名) 写回
HTML 的 var __CHARTS__ = {...} 对象。用于「改生成器样式后」刷新内联图表，而无需
重跑整条 HTML 生成管线（coal/mobile/telecom 的 SVG 在 Phase 3 已内联进 HTML）。

用法：
  python common/reinject_svgs.py <html> <svg_dir1> [<svg_dir2> ...]
可选：--dry  只报告差异不写盘
"""
import os, re, sys, json, argparse

SVG_RE = re.compile(r'var __CHARTS__\s*=\s*(\{.*?\})\s*;', re.S)


def sanitize(s):
    # 避免 </script 提前闭合（SVG 内不应含，但防御性处理）
    return s.replace("</script", "<\\/script")


def collect_svgs(dirs):
    m = {}
    for d in dirs:
        for root, _, files in os.walk(d):
            for fn in files:
                if fn.endswith(".svg"):
                    key = fn[:-4]
                    with open(os.path.join(root, fn), encoding="utf-8") as f:
                        m[key] = f.read()
    return m


def reinject(html_path, svg_dirs, dry=False):
    html = open(html_path, encoding="utf-8").read()
    mt = SVG_RE.search(html)
    if not mt:
        print(f"[FAIL] {html_path}: 未找到 var __CHARTS__ 块"); return 1
    obj = json.loads(mt.group(1))
    svgs = collect_svgs(svg_dirs)

    replaced, missing, orphan = [], [], []
    for k in obj:
        if k in svgs:
            old = obj[k]
            new = sanitize(svgs[k])
            if old != new:
                replaced.append(k)
            obj[k] = new
        else:
            missing.append(k)
    for k in svgs:
        if k not in obj:
            orphan.append(k)

    print(f"[INFO] __CHARTS__ 共 {len(obj)} 键；svg 文件 {len(svgs)} 个")
    print(f"       已替换 {len(replaced)} 个；HTML 缺 svg(保留原值) {len(missing)} 个；svg 孤儿 {len(orphan)} 个")
    if missing: print("       缺 svg 键:", missing)
    if orphan: print("       孤儿 svg:", orphan)
    if dry:
        return 0
    new_block = "var __CHARTS__ = " + json.dumps(obj, ensure_ascii=False, indent=2) + ";"
    new_html = html[:mt.start()] + new_block + html[mt.end():]
    # 防御：确认替换后仍能解析
    assert SVG_RE.search(new_html), "替换后 __CHARTS__ 块不可解析"
    open(html_path, "w", encoding="utf-8").write(new_html)
    print(f"[OK] 已写回 {html_path}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("svg_dirs", nargs="+")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    sys.exit(reinject(a.html, a.svg_dirs, a.dry))
