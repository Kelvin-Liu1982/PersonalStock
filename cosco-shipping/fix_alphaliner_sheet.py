# -*- coding: utf-8 -*-
"""新增 sheet「供给端-Alphaliner周报(摘要)」：2025 年以来 Alphaliner 免费周报摘要指标，
仅收录有公开记录的时点（不逐周连续、不插值、不做交叉验证）。
"""
import os, sys, zipfile, re
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

XLSX = "数据源/中远海控_行业供需与运价数据.xlsx"
SHEET = "供给端-Alphaliner周报(摘要)"
assert os.path.exists(XLSX), XLSX

# ---------- 数据（仅 Alphaliner，按数据截止日排序） ----------
# 列: 截止日 | 在运营艘数 | 船队运力万TEU | 口径 | 订单艘数 | 订单万TEU | 订单占船队% | 闲置艘数 | 闲置万TEU | 闲置% | 转载来源 | 备注
ROWS = [
    ("2025-01-02", 6371, 3143.0, "全集装箱船(fully cellular)", None, None, None, None, None, None,
     "工商时报/永丰金引Alphaliner", "「营运船舶6371艘、总运力逾3143万TEU」；艘数与1月中旬口径不同，判为 fully cellular 口径"),
    ("2025-01-10", 7176, 3150.14, "全部在运营", None, None, None, None, None, None,
     "网易·航运榜", "31,501,412 TEU；较2024-01-11 +2,870,411 TEU"),
    ("2025-01-14", 7211, 3156.04, "全部在运营", None, None, None, None, None, None,
     "中国船东协会", "Alphaliner 百强榜；前三合计占46.33%"),
    ("2025-03-12", 7265, 3186.3, "全部在运营", None, 910.0, 28.6, None, None, None,
     "现代物流报", "手持订单910万TEU，为当时历史新高"),
    ("2025-04-04", 7282, 3203.05, "全部在运营", None, None, None, None, None, None,
     "国际船舶网", None),
    ("2025-04-16", 7286, 3207.93, "全部在运营", None, None, None, None, None, None,
     "辽宁省国际货运代理协会", None),
    ("2025-04-25", 7299, 3177.90, "全集装箱船(fully cellular)", None, None, None, None, None, None,
     "河北浩华/ horwa.net", "fully cellular 首破6500艘，总运力31,779,002 TEU；7299艘为运营中船队总数"),
    ("2025-06初", 6526, 3200.0, "全部在运营(SSE 转引)", None, None, None, None, 16.0, 0.6,
     "上海航运交易所《2025(年中)水运形势报告》", "闲置16万TEU占总运力0.6%，与年初持平、同比降0.1pp；10000TEU以上占45.6%"),
    ("2025-06-02", 7307, 3239.0, "全部在运营", None, None, None, None, None, None,
     "国际船舶网", None),
    ("2025-06-19", 7321, 3254.89, "全部在运营", None, None, None, None, None, None,
     "网易·6月运力榜", "32,548,889 TEU；较上期(4-11) +501,729 TEU"),
    ("2025-07-13", 7352, 3270.28, "全部在运营", None, None, None, None, None, None,
     "《世界海运》2025年第8期", "AXS-Alphaliner 统计；约3.88亿载重吨"),
    ("2025-08-03", 7360, 3278.1, "全部在运营", None, None, None, None, None, None,
     "国际船舶网", None),
    ("2025-08中", None, 3250.0, "全集装箱船(fully cellular)", None, 995.0, None, None, None, 0.5,
     "AXSMarine 官方博客(public.axsmarine.com)", "「approached 32.5 MTEU」为约数；订单9.95 MTEU 创历史新高(≈30.6% of fleet)；闲置率0.5%，双周仅+2.8万TEU"),
    ("2025-09-03", 7384, 3297.2, "全部在运营", None, None, None, None, None, None,
     "航运界", None),
    ("2025-09-07", 7388, 3298.99, "全部在运营", None, None, None, None, None, None,
     "国际船舶网", None),
    ("2025-10-31", None, None, "未公布船队总量", 1104, 1053.0, 32.36, None, None, None,
     "Yahoo奇摩/台媒引Alphaliner", "10月底：手持订单1104艘、1053万TEU，占现有船队32.36%"),
    ("2025-11-27", 7473, 3349.2, "全部在运营", 1109, 1125.0, 34.0, None, None, None,
     "国际船舶网", "订单1109艘1125万+TEU≈船队34%；991艘将于2028年底前交付"),
    ("2025-12-10", 7477, 3352.2, "全部在运营", None, None, None, None, None, None,
     "国际船舶网", None),
    ("2025-12-13", 7481, 3353.0, "全部在运营", None, None, None, None, None, None,
     "物流巴士/5684.com", "33,530,009 TEU，环比+156,212 TEU"),
    ("2025-12-15", None, 3310.0, "全部在运营(西语媒体口径)", None, None, None, 98, 25.73, 0.8,
     "MundoMarítimo 引Alphaliner", "98艘、257,272 TEU 商业闲置=0.8%；船队33.1 MTEU；厂内/ yard 运力环比降约10万TEU"),
    ("2025-12-28", 7492, 3365.73, "全部在运营", None, None, None, None, None, None,
     "大数跨境·本周运力报告(20251229)", "统计时段12-22~12-28；环比+4.41万TEU；前十合计占84.7%"),
    ("2025-12底", None, 3700.0, "接近3700万TEU(AXSMarine 口径)", None, None, None, 83, 21.23, 0.6,
     "AXSMarine 官方博客 / Ship&Bunker / LoadStar", "83艘、212,327 TEU 商业闲置=0.6%；2025全年平均闲置率0.7%"),
    ("2026-01-03", 7498, 3369.0, "全部在运营", None, None, None, None, None, None,
     "光大期货《航运策略月报》引Alphaliner", "前三占47.16%"),
    ("2026-01月报", None, 3325.7, "全集装箱船(cellular)，月报口径", None, 1134.1, 34.1, None, None, None,
     "Alphaliner Monthly Monitor, January 2026（截图）", "原表写作 33,257 Mteu / 11,341 Mteu，实际为千TEU(kTEU)口径：33,257 千TEU＝3,325.7万TEU、11,341 千TEU＝1,134.1万TEU；若按字面百万TEU 解读会放大到 332.6亿TEU（约为实际船队950倍），显系单位标注错误。同比 +7.17% → 隐含 2025-01 为 3,103.2万TEU，一年净增 222.5万TEU（月均 18.5万）。与 2026-01-03 百强榜「全部在运营 3,369万」差 43.3万TEU＝非格栅兼营箱位，口径自洽"),
    ("2026-02-11", 7515, 3384.0, "全部在运营", None, None, None, None, None, None,
     "国际船舶网", None),
    ("2026-02-13", 7518, 3384.9, "全部在运营", None, None, None, None, None, None,
     "航运界", "MSC 破720万TEU、份额21.4%"),
    ("2026-02-14", 7517, 3384.89, "全部在运营", None, None, None, None, None, None,
     "华光源海·2月运力榜", "33,848,891 TEU；环比+150,944 TEU"),
    ("2026-03-19", 7516, 3389.6, "全部在运营", None, None, None, None, None, None,
     "航运界", None),
    ("2026-03底", 7518, 3400.0, "全部在运营(约)", None, None, None, None, None, None,
     "El Estrecho / 海事服务网(cnss)", "fully cellular 首破6700艘=3360万TEU；全部在运营7518艘≈3400万TEU；远东-欧洲周运力破53万TEU"),
    ("2026-04-05", 7522, 3399.66, "全部在运营", None, None, None, None, None, None,
     "国际船舶网", None),
    ("2026-04-20", None, None, "未公布船队总量", None, None, None, 81, 23.57, 0.7,
     "The Loadstar 引Alphaliner", "81艘、235,705 TEU 商业闲置=0.7%；另坞修141艘65.67万TEU，闲置+在坞合计2.7%；因中东冲突改道/避风58艘约31万TEU(不计入商业闲置)"),
    ("2026-05-11", 7537, 3409.7, "全部在运营", None, None, None, None, None, None,
     "航运界", None),
    ("2026-06-15", None, None, "未公布船队总量", None, None, None, 74, 20.13, 0.6,
     "信德海事网", "500TEU以上商业闲置74艘、20.13万TEU=0.6%；18000TEU以上零闲置"),
    ("2026-06-25", 7554, 3431.7, "全部在运营", 1592, 1298.0, 38.3, None, None, None,
     "航运界 / 信德海事网", "订单1592艘1298万TEU=船队38.3%；2025全年新增订单737艘505万TEU"),
    ("2026-06-29", None, None, "未公布船队总量", None, None, None, 84, 24.1, 0.70,
     "Alphaliner Weekly Newsletter No.27/2026（PDF 原件）", "商业闲置84艘、约241,000 TEU（双周净增10艘），原文为约数；闲置占比0.70%系按241,000÷34,317,000(6-25船队)计算、非原文给出；另'in yard'约504,000 TEU（双周降约64,000）；因中东改道/避风41艘约215,000 TEU，按 Alphaliner 定义不计入商业闲置"),
    ("2026-07-10", 7592, 3442.8, "全部在运营", None, None, None, None, None, None,
     "华光源海·7月运力榜 / 浙江沛洋", "34,427,972 TEU，环比+185,227 TEU；MSC 734.3万TEU(21.5%)"),
    ("2026-08中", None, 3416.0, "现役船队(订单占比分母)", 1724, 1397.0, 40.9, None, None, None,
     "信德海事网(Alphaliner 第33期周报)", "订单1724艘1397万TEU，Alphaliner 表述为40%，按其两组数据算≈40.9%，2009年以来最高；较6月+132艘/99万TEU"),
    ("2026-08-24", None, 3440.0, "全部在运营(约)", None, None, None, 95, 20.0, 0.6,
     "网易/航运界引Alphaliner", "「约3440万TEU」；商业闲置95艘、不足20万TEU=0.6%，'fully employed'"),
    ("2026-10-20", 7670, 3493.41, "全部在运营(Top100 Global figures, consolidated)", None, None, None, None, None, None,
     "Alphaliner 官网 PublicTop100 页面（免费）", "34,934,139 TEU；其中 fully cellular 34,520,733 TEU / 6,862艘；415,468,213 DWT。TOP100 各公司手持订单合计 1,304.5万TEU＝全球船队 37.3%（公司口径、不含独立船东订单，故低于 Alphaliner 官方 40.9%）；区域周运力：跨大西洋 154,747 / 跨太平洋 621,487 / 远东-欧洲 561,784 TEU"),
]

TITLE = "供给端 · Alphaliner 周报摘要指标（2025 年以来，按数据截止日）"
NOTE = ("数据源：Alphaliner（法国 AXSMarine）免费周报/双周报摘要指标，经中文及外文媒体转载获取；"
        "口径：仅收录有公开记录的时点，非逐周连续序列、不做任何插值；按要求未与 Clarksons / ISL / BIMCO 交叉验证。"
        "注意：①「全部在运营」与「全集装箱船(fully cellular)」是两种口径，混用会失真，已在 D 列标明；"
        "②订单占船队比例为 Alphaliner 原文表述或按其公布的订单/船队两组数据计算；"
        "③商业闲置船(commercial idle)不含等泊、坞修及因改道/避风的运力。"
        "整理日期 2026-10-20；下次更新建议：每月初补上月各时点。")
HEAD = ["数据截止日", "全球在运营集装箱船(艘)", "全球船队总运力(万TEU)", "运力口径",
        "手持订单(艘)", "手持订单(万TEU)", "订单占船队比例(%)",
        "商业闲置船(艘)", "闲置运力(万TEU)", "闲置占比(%)", "转载来源", "备注"]

def snapshot(wb):
    """值 + 解析后样式（数字格式/字体/填充/边框/对齐）一起快照，确保旧 sheet 逐格不变。"""
    def sig(c):
        return (c.number_format, c.font.b, c.font.sz,
                c.font.color.rgb if c.font.color else None,
                c.fill.fgColor.rgb if c.fill and c.fill.fgColor else None, c.fill.patternType,
                c.alignment.horizontal, c.alignment.vertical, c.alignment.wrapText,
                tuple((getattr(c.border, s).style if getattr(c.border, s) is not None else None)
                      for s in ("left", "right", "top", "bottom")))
    return {ws.title: [[(c.value, sig(c)) for c in row] for row in ws.iter_rows()] for ws in wb.worksheets}

def fill_count(path):
    with zipfile.ZipFile(path) as z:
        s = z.read("xl/styles.xml").decode("utf-8")
    return s.count("<fill/>"), s.count("<fill>")

wb = openpyxl.load_workbook(XLSX)
before = snapshot(wb)
before_fill = fill_count(XLSX)
if SHEET in wb.sheetnames:
    del wb[SHEET]
ws = wb.create_sheet(SHEET)

thin = Side(style="thin", color="d0d7de")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
head_fill = PatternFill("solid", fgColor="eef2f6")

ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(HEAD))
c = ws.cell(1, 1, TITLE)
c.font = Font(bold=True, size=13, color="1f2733")
c.alignment = Alignment(vertical="center")
ws.row_dimensions[1].height = 24

ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(HEAD))
c = ws.cell(2, 1, NOTE)
c.font = Font(size=9, color="5b6673")
c.alignment = Alignment(wrap_text=True, vertical="top")
ws.row_dimensions[2].height = 62

for j, h in enumerate(HEAD, start=1):
    c = ws.cell(4, j, h)
    c.font = Font(bold=True, size=10, color="1f2733")
    c.fill = head_fill
    c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    c.border = border
ws.row_dimensions[4].height = 32

for i, r in enumerate(ROWS, start=5):
    for j, v in enumerate(r, start=1):
        c = ws.cell(i, j, v)
        c.font = Font(size=10)
        c.border = border
        if j in (2, 5, 8):
            c.alignment = Alignment(horizontal="right")
            c.number_format = "#,##0"
        elif j in (3, 6, 9):
            c.alignment = Alignment(horizontal="right")
            c.number_format = "#,##0.0"
        elif j in (7, 10):
            c.alignment = Alignment(horizontal="right")
            c.number_format = "0.00"
        elif j == 12:
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.font = Font(size=9, color="5b6673")
        else:
            c.alignment = Alignment(horizontal="left")

widths = [13, 15, 15, 24, 11, 13, 13, 12, 13, 10, 30, 52]
for j, w in enumerate(widths, start=1):
    ws.column_dimensions[get_column_letter(j)].width = w
ws.freeze_panes = "A5"
ws.sheet_view.showGridLines = True

wb.save(XLSX)
print("saved. rows:", len(ROWS), "sheets:", wb.sheetnames)

# ---------- 修补 openpyxl %.16g 截断的浮点（恢复 17 位有效数字） ----------
# openpyxl 保存时用 %.16g 格式化浮点，会把个别单元格的第 17 位有效数字截断，需按原始 XML 还原。
def _cell_v(path, sheetfile, ref):
    with zipfile.ZipFile(path) as z:
        s = z.read(sheetfile).decode("utf-8")
    m = re.search(r'<c r="%s"[^>]*>\s*<v>([^<]+)</v>' % ref, s)
    return m.group(1) if m else None

# 这些单元格在原文件中使用 17 位有效数字；任何写入方（openpyxl %.16g / WPS / 腾讯文档）
# 都可能把末位改写成等价浮点，这里按"数值等价即归位"的原则还原为规范写法。
CANON = {("xl/worksheets/sheet2.xml", "C8"): "3.0261348005502064E-2"}
with zipfile.ZipFile(XLSX) as zin:
    names = zin.namelist()
    data = {n: zin.read(n) for n in names}
for (sheetfile, ref), good in CANON.items():
    s = data[sheetfile].decode("utf-8")
    m = re.search(r'(<c r="%s"[^>]*>\s*)<v>([^<]+)</v>' % ref, s)
    if not m:
        print("warn: %s!%s 未找到" % (sheetfile, ref)); continue
    cur = m.group(2)
    if cur != good and abs(float(cur) - float(good)) <= 1e-15:
        s = s[:m.start()] + m.group(1) + "<v>%s</v>" % good + s[m.end():]
        data[sheetfile] = s.encode("utf-8")
        print("restored %s!%s: %s -> %s" % (sheetfile, ref, cur, good))
    else:
        print("ok %s!%s = %s" % (sheetfile, ref, cur))
tmp = XLSX + ".tmp"
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for n in names:
        zout.writestr(n, data[n])
os.replace(tmp, XLSX)

# ---------- 校验 ----------
wb2 = openpyxl.load_workbook(XLSX)
after = snapshot(wb2)
after_fill = fill_count(XLSX)
assert wb2.sheetnames == wb.sheetnames, wb2.sheetnames
# 其他 4 个 sheet 必须逐格不变
def _same(a, b):
    """值：数值按 1e-15 相对容差比较（允许末位表示漂移）；其余精确比较。样式必须完全一致。"""
    (va, sa), (vb, sb) = a, b
    if sa != sb:
        return False
    if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
        return abs(va - vb) <= 1e-15 * max(1.0, abs(va), abs(vb))
    return va == vb

changed = []
for name in before:
    if name == SHEET:
        continue
    ra, rb = before[name], after.get(name) or []
    if len(ra) != len(rb):
        changed.append((name, "行数 %d -> %d" % (len(ra), len(rb)))); continue
    for i, (rowa, rowb) in enumerate(zip(ra, rb)):
        if len(rowa) != len(rowb):
            changed.append((name, "第%d行列数" % (i + 1))); break
        bad = [j for j, (ca, cb) in enumerate(zip(rowa, rowb)) if not _same(ca, cb)]
        if bad:
            changed.append((name, "第%d行 列%s 值或样式不同" % (i + 1, bad[:3]))); break
assert not changed, "其他 sheet 被改动: %s" % changed
ws2 = wb2[SHEET]
assert ws2.max_row == 4 + len(ROWS), ws2.max_row
def _dkey(d):
    """2025-06初 / 2026-08中 / 2025-12底 这类非数字尾缀映射为月内排序位。"""
    last = d[-1]
    tail = {"初": "01", "中": "15", "底": "28"}.get(last, d[-2:])
    return (d[:4], d[5:7], tail)
dates = [ws2.cell(r, 1).value for r in range(5, ws2.max_row + 1)]
assert dates == sorted(dates, key=_dkey), "未按截止日排序"
# 抽查 5 个关键值
spot = {ws2.cell(r, 1).value: [ws2.cell(r, c).value for c in range(2, 11)] for r in range(5, ws2.max_row + 1)}
checks = [
    ("2025-03-12", 7265, 3186.3, None, 910.0, 28.6),
    ("2025-12-28", 7492, 3365.73, None, None, None),
    ("2026-06-25", 7554, 3431.7, 1592, 1298.0, 38.3),
    ("2026-08中", None, 3416.0, 1724, 1397.0, 40.9),
    ("2026-08-24", None, 3440.0, None, None, None),
]
for d, n, f, on, ot, op in checks:
    v = spot[d]
    assert v[0] == n and v[1] == f and v[3] == on and v[4] == ot and v[5] == op, (d, v)
print("styles.xml <fill/> : before=%d after=%d  (必须相等且为0)" % (before_fill[0], after_fill[0]))
print("OK: 其他 %d 个 sheet 逐格未变；新 sheet %d 行数据；抽查 5 项通过" % (len(before) - 1, len(ROWS)))
