#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_light_theme.py —— 把 output/gold-terminal.html 从暗色终端改为白底浅色主题。

方案 2：变量 + 硬编码 hex 按语义映射 + 暗色专用效果改写。
只改 CSS/JS 的**颜色字面量**，绝不碰：
  - /*GOLD_DATA_START/END*/ 与 /*GOLD_PANEL_DATA_START/END*/ 两个数据块
  - HTML 结构、data-field / data-macro 绑定、交互逻辑、SVG 绘制逻辑

默认值（用户 2026-11-15 确认「按方案 2、默认设置来」）：
  - 范围：仅 gold-terminal.html
  - 涨跌色：沿用现有约定（涨绿 / 跌红），只加深以适配白底
  - 金色：#E0B84C → #9A6B00（白底对比度 4.69:1，满足 WCAG AA 正文 4.5）；
    --up 绿 #4fb477 → #1f7a4d（5.32:1）
  - 不保留暗色主题

用法：
  python3 tools/apply_light_theme.py --dry-run   # 只打印替换统计
  python3 tools/apply_light_theme.py             # 写入（先备份到 ~/.Trash/）
"""
import argparse
import datetime
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, 'output', 'gold-terminal.html')

# ---------- 阶段 C：:root 变量（必须最先做，避免被全局映射误伤） ----------
VARS = [
    ('--bg:#0a0d12;', '--bg:#ffffff;'),
    ('--bg-2:#0d1118;', '--bg-2:#f7f8fa;'),
    ('--panel:#0c1118;', '--panel:#ffffff;'),
    ('--line:#1b222c;', '--line:#e3e7ed;'),
    ('--line-2:#262f3b;', '--line-2:#cbd3dd;'),
    ('--txt:#c7d0db;', '--txt:#1f2933;'),
    ('--txt-dim:#76828f;', '--txt-dim:#5b6672;'),
    ('--txt-faint:#4a5562;', '--txt-faint:#8a94a1;'),
    ('--gold:#E0B84C;', '--gold:#9A6B00;'),
    ('--gold-2:#C9A227;', '--gold-2:#8A6508;'),
    ('--gold-dim:#8a7223;', '--gold-dim:#E8D9A8;'),
    ('--up:#4fb477;', '--up:#1f7a4d;'),
    ('--down:#d65745;', '--down:#c0392b;'),
    ('--accent-cool:#5a8db5;', '--accent-cool:#2E6D9E;'),
]

# ---------- 阶段 A：需要按上下文单独处理的特殊点 ----------
CONTEXT = [
    # 反白文字 / 反白圆点：暗底挖空 → 白底挖空
    ('::selection{background:var(--gold-2);color:#0a0d12}',
     '::selection{background:var(--gold-2);color:#ffffff}'),
    (".eventbar .evtag{font-family:var(--mono);font-size:11px;letter-spacing:1px;color:#0a0d12;",
     ".eventbar .evtag{font-family:var(--mono);font-size:11px;letter-spacing:1px;color:#ffffff;"),
    (".hnow{fill:#0a0d12;stroke:#E0B84C;", ".hnow{fill:#ffffff;stroke:#9A6B00;"),
    (".hpeak{fill:#0a0d12;stroke:#E0B84C;", ".hpeak{fill:#ffffff;stroke:#9A6B00;"),
    (".hlow{fill:#0a0d12;stroke:#5a8db5;", ".hlow{fill:#ffffff;stroke:#2E6D9E;"),
    (".macro-spark .ms-dot{fill:#0a0d12;stroke:#E0B84C;",
     ".macro-spark .ms-dot{fill:#ffffff;stroke:#9A6B00;"),
    # JS：条内数值标签（彩色柱上）改白字；负值柱下标签改主文字色
    ("{anchor:pos?'end':'start', fill:'#0a0d12', size:'12', weight:'700'}",
     "{anchor:pos?'end':'start', fill:'#ffffff', size:'12', weight:'700'}"),
    ("{anchor:'middle', fill:'#fff', size:'12.5', weight:'600'}",
     "{anchor:'middle', fill:'var(--txt)', size:'12.5', weight:'600'}"),
    # 暗色渐变：顶栏 / 数据条 / 模块头 hover
    ('background:linear-gradient(180deg,#0e131b,#0a0d12);',
     'background:linear-gradient(180deg,#ffffff,#f4f6f9);'),
    ('background:linear-gradient(180deg,#0c1119,#0a0d12);',
     'background:linear-gradient(180deg,#ffffff,#f4f6f9);'),
    ('background:linear-gradient(180deg,#0f141d,#0b0f16);',
     'background:linear-gradient(180deg,#fafbfc,#f1f4f8);'),
    ('.tpl-ph:hover{background:linear-gradient(180deg,#131a24,#0b0f16)}',
     '.tpl-ph:hover{background:linear-gradient(180deg,#ffffff,#f4f6f9)}'),
    # 事件条斜纹
    ('background:repeating-linear-gradient(45deg,#0c1118,#0c1118 10px,#0b1017 10px,#0b1017 20px);',
     'background:repeating-linear-gradient(45deg,#f7f8fa,#f7f8fa 10px,#eef2f7 10px,#eef2f7 20px);'),
    # 阴影 / hover 高亮
    ('box-shadow:0 10px 28px rgba(0,0,0,.55);', 'box-shadow:0 10px 28px rgba(15,23,42,.16);'),
    ('box-shadow:0 0 6px var(--up);', 'box-shadow:0 0 0 3px rgba(31,122,77,.18);'),
    ('box-shadow:0 0 7px var(--up);', 'box-shadow:0 0 0 3px rgba(31,122,77,.18);'),
    ('.gdt-hit:hover{fill:rgba(255,255,255,.035)}', '.gdt-hit:hover{fill:rgba(15,23,42,.05)}'),
    # 输入框：白底（区别于图表容器的浅灰底）
    ('width:100%;background:#080b10;border:1px solid var(--line);color:var(--gold);',
     'width:100%;background:#ffffff;border:1px solid var(--line);color:var(--gold);'),
    # 金色半透明面积 / 阶段色带：白底上需略加深
    ('.harea{fill:rgba(224,184,76,.10)}', '.harea{fill:rgba(154,107,0,.12)}'),
    ('.macro-spark .ms-area{fill:rgba(224,184,76,.10)}',
     '.macro-spark .ms-area{fill:rgba(154,107,0,.12)}'),
    ("var col = b[2]==='up' ? 'rgba(224,184,76,.07)' : (b[2]==='down' ? 'rgba(214,87,69,.07)' : 'rgba(90,141,181,.06)');",
     "var col = b[2]==='up' ? 'rgba(154,107,0,.09)' : (b[2]==='down' ? 'rgba(192,57,43,.09)' : 'rgba(46,109,158,.08)');"),
    # 力矩阵浅色文字 → 深色
    ('.push .fcell .fname{color:#cfe6d8}', '.push .fcell .fname{color:#1f7a4d}'),
    ('.pull .fcell .fname{color:#e6cfca}', '.pull .fcell .fname{color:#b5462f}'),
    # ⚠️ --gold-dim 改为浅金后只能用于 border / 渐变；
    #    以下 6 处原本把它当文字色 / SVG fill，白底上会看不见，必须改用深金 --gold-2。
    ('font-family:var(--mono);font-size:11px;color:var(--gold-dim);line-height:1.5;',
     'font-family:var(--mono);font-size:11px;color:var(--gold-2);line-height:1.5;'),
    ('.lblock li::before{content:"▸";position:absolute;left:0;color:var(--gold-dim)}',
     '.lblock li::before{content:"▸";position:absolute;left:0;color:var(--gold-2)}'),
    ('.foot b{color:var(--gold-dim)}', '.foot b{color:var(--gold-2)}'),
    ('.cb-foot b{color:var(--gold-dim)}', '.cb-foot b{color:var(--gold-2)}'),
    ("fill:'var(--gold-dim)'", "fill:'var(--gold-2)'"),
]

# ---------- 阶段 B：剩余硬编码 hex 按语义全局映射 ----------
HEXMAP = {
    '#0c1118': '#f4f6f9',   # 卡片 hover / stage hover
    '#11161f': '#f2f5f9',   # 列表分隔 / 卡片 hover
    '#0b1017': '#f7f8fa',   # tpl-head / 图表容器
    '#14202c': '#f7f8fa',   # 按钮底
    '#1b2a38': '#eef2f7',   # 按钮 hover
    '#0a0e14': '#eef1f5',   # 权重条底
    '#141922': '#ffffff',   # tooltip 底
    '#101821': '#ffffff',   # 图表切换按钮
    '#17202b': '#fdf5e3',   # 图表切换按钮选中（浅金）
    '#080b10': '#f7f8fa',   # 图表容器 / mini 图底
    '#1a222c': '#e5e9ef',   # JS 图表网格线
    '#1b222c': '#e5e9ef',   # CSS 图表网格线（变量行已被阶段 C 替换）
    '#4a5562': '#6b7684',   # 轴标签
    '#6b7785': '#5b6672',   # JS 轴标签
    '#7d8a98': '#5b6672',   # 图表注释 / mini 图标签
    '#3a4653': '#9aa4b1',   # placeholder
    '#E0B84C': '#9A6B00',   # 金色主线 / 渐变 stop / 债务面板
    '#C9A227': '#8A6508',   # 深金 / GDT 回收金
    '#8a7223': '#E8D9A8',   # 浅金边框
    '#4fb477': '#1f7a4d',   # 涨 绿
    '#d65745': '#c0392b',   # 跌 红
    '#5a8db5': '#2E6D9E',   # 冷蓝
    '#8B5CF6': '#7C3AED',   # GDT 金饰制造
    '#C026D3': '#A21CAF',   # GDT 央行及其他
    '#7FA8C9': '#4A7FA5',   # GDT 生产商套保
}

# 替换后不应再出现的暗色 / 低对比色
BLACKLIST = [
    '#0a0d12', '#0d1118', '#0c1118', '#1b222c', '#262f3b', '#c7d0db', '#76828f',
    '#0e131b', '#0c1119', '#0f141d', '#0b0f16', '#0b1017', '#14202c', '#1b2a38',
    '#11161f', '#0a0e14', '#141922', '#101821', '#17202b', '#080b10', '#1a222c',
    '#7d8a98', '#3a4653', '#131a24', '#4a5562', '#6b7785',
    '#E0B84C', '#C9A227', '#8a7223', '#4fb477', '#d65745', '#5a8db5',
    '#8B5CF6', '#C026D3', '#7FA8C9',
]


def apply(s, log):
    # 阶段 C：变量定义
    for old, new in VARS:
        n = s.count(old)
        assert n == 1, f'变量定义应命中 1 次，实际 {n}: {old}'
        s = s.replace(old, new, 1)
        log.append(('var', old, new, 1))
    # 阶段 A：特殊上下文
    for old, new in CONTEXT:
        n = s.count(old)
        assert n >= 1, f'上下文未命中: {old[:70]}'
        s = s.replace(old, new)
        log.append(('ctx', old[:46], new[:46], n))
    # 阶段 B：剩余 hex 全局映射
    for old, new in HEXMAP.items():
        n = len(re.findall(re.escape(old) + r'(?![0-9a-fA-F])', s))
        if n:
            s = re.sub(re.escape(old) + r'(?![0-9a-fA-F])', new, s)
            log.append(('hex', old, new, n))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    s = open(HTML, encoding='utf-8').read()
    n0 = len(s)
    # 数据块必须原样保留
    for mark in ('/*GOLD_DATA_START*/', '/*GOLD_DATA_END*/',
                 '/*GOLD_PANEL_DATA_START*/', '/*GOLD_PANEL_DATA_END*/'):
        assert s.count(mark) == 1, f'数据标记异常: {mark}'
    data_before = re.findall(r'/\*GOLD_DATA_START\*/[\s\S]*?/\*GOLD_DATA_END\*/', s)[0]
    panel_before = re.findall(r'/\*GOLD_PANEL_DATA_START\*/[\s\S]*?/\*GOLD_PANEL_DATA_END\*/', s)[0]

    log = []
    out = apply(s, log)

    # 残留检查
    resid = []
    for c in BLACKLIST:
        n = len(re.findall(re.escape(c) + r'(?![0-9a-fA-F])', out, flags=re.I))
        if n:
            resid.append((c, n))
    print(f'替换统计：共 {len(log)} 条规则 / {sum(x[3] for x in log)} 处命中')
    for typ in ('var', 'ctx', 'hex'):
        sub = [x for x in log if x[0] == typ]
        print(f'  {typ}: {len(sub)} 条规则 / {sum(x[3] for x in sub)} 处')
    print('暗色残留:', resid if resid else '无 ✓')
    assert not resid, f'仍有暗色残留: {resid}'

    # 数据块逐字节未变
    assert re.findall(r'/\*GOLD_DATA_START\*/[\s\S]*?/\*GOLD_DATA_END\*/', out)[0] == data_before
    assert re.findall(r'/\*GOLD_PANEL_DATA_START\*/[\s\S]*?/\*GOLD_PANEL_DATA_END\*/', out)[0] == panel_before
    print('数据块逐字节未变 ✓')
    # 结构锚点仍在
    for k in ('class="macro-badge"', 'class="macro-spark"', 'id="evBtn"', 'id="tplArea"'):
        assert out.count(k) == s.count(k), f'结构被改动: {k}'
    print('结构/绑定锚点未变 ✓')

    if args.dry_run:
        print('\n[dry-run] 未写入文件')
        return 0

    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    trash = os.path.expanduser(f'~/.Trash/gold-terminal-dark-{stamp}.html')
    shutil.copy2(HTML, trash)
    print(f'\n备份 -> {trash}')
    with open(HTML, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'✓ 已写入 {HTML}（{n0:,} → {len(out):,} 字符）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
