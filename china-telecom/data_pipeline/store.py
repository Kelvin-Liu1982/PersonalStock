# -*- coding: utf-8 -*-
"""持久化层：把转换后的表结构写入 XLSX（与中国移动 build_excel.py 同款样式与三 sheet 规范）。

每张表：年报数据 / 季报数据 / 数据来源与口径说明。
依赖 openpyxl（隔离 venv 已安装）。
"""
import os
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

import config as C

HDR_FILL = PatternFill("solid", fgColor="15616D")
HDR_FONT = Font(name="微软雅黑", bold=True, color="FFFFFF", size=11)
TITLE_FONT = Font(name="微软雅黑", bold=True, color="15616D", size=13)
SUB_FONT = Font(name="微软雅黑", color="7A8694", size=10)
METRIC_FONT = Font(name="微软雅黑", size=11)
METRIC_BOLD = Font(name="微软雅黑", bold=True, size=11)
YEAR_FILL = PatternFill("solid", fgColor="F7F9FB")
NOTE_FILL = PatternFill("solid", fgColor="FDF3E3")
THIN = Side(style="thin", color="E3E8EE")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")


def _style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER


def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return round(v, 2)
    return v


def _write_table(ws, start_row, headers, rows):
    ncols = len(headers)
    for j, h in enumerate(headers, 1):
        ws.cell(row=start_row, column=j, value=h)
    _style_header(ws, start_row, ncols)
    r = start_row + 1
    for item in rows:
        name = item[0]
        vals = item[1]
        note = item[2] if len(item) > 2 else ""
        c1 = ws.cell(row=r, column=1, value=name)
        c1.font = METRIC_BOLD
        c1.alignment = LEFT
        c1.border = BORDER
        for k, v in enumerate(vals, 2):
            cell = ws.cell(row=r, column=k, value=_fmt(v))
            cell.font = METRIC_FONT
            cell.alignment = RIGHT if not isinstance(v, str) else CENTER
            cell.border = BORDER
            if isinstance(v, float):
                cell.number_format = "#,##0.00"
        if note:
            nc = ws.cell(row=r, column=ncols, value=note)
            nc.font = SUB_FONT
            nc.alignment = LEFT
            nc.border = BORDER
            nc.fill = NOTE_FILL
        r += 1
    return r


def _autosize(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def build_file(out_dir, file_name, title, annual_headers, annual_rows,
               q_headers, q_rows, source_text, annual_widths=None,
               years_as_rows=False, annual_header_row=4, preserve_quarterly=False):
    # years_as_rows=True：把 metrics-as-rows 的 annual_rows 转置为
    # 「年份为行、指标为列」方向（与 build_s1_svg / 手工在盘文件一致）。
    if years_as_rows:
        periods = annual_headers[1:-1]  # 去掉首尾「指标」「备注」
        indicators = [r[0] for r in annual_rows]
        new_headers = ["年度"] + indicators
        new_rows = []
        for i, p in enumerate(periods):
            vals = [r[1][i] if i < len(r[1]) else None for r in annual_rows]
            new_rows.append((p, vals, ""))
        annual_headers, annual_rows = new_headers, new_rows

    # preserve_quarterly=True：加载已有文件、仅重写「年报数据」sheet，
    # 保留手工补全的「季报数据」「数据来源与口径说明」，避免管道覆盖丢失。
    path = os.path.join(out_dir, file_name)
    if preserve_quarterly and os.path.exists(path):
        wb = openpyxl.load_workbook(path)
        if "年报数据" in wb.sheetnames:
            del wb["年报数据"]
        ws = wb.create_sheet("年报数据", 0)  # 插到最前
        sub_text = "口径：全年累计；年份为行、指标为列；单位见指标名；无法核验年份显示'—'。"
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "年报数据"
        sub_text = ("口径：全年累计；指标为行、年份为列；单位见指标名；无法核验年份显示'—'。"
                    if not years_as_rows else
                    "口径：全年累计；年份为行、指标为列；单位见指标名；无法核验年份显示'—'。")
    ws.cell(row=1, column=1, value=title).font = TITLE_FONT
    ws.cell(row=2, column=1, value=sub_text).font = SUB_FONT
    _write_table(ws, annual_header_row, annual_headers, annual_rows)
    # 年份为行时，标题跨所有指标列合并
    last_col = openpyxl.utils.get_column_letter(max(2, len(annual_headers)))
    if years_as_rows:
        ws.merge_cells("A1:%s1" % last_col)
    if annual_widths is None:
        annual_widths = {"A": 14}
        for i in range(2, len(annual_headers) + 1):
            annual_widths[openpyxl.utils.get_column_letter(i)] = 20
    _autosize(ws, annual_widths)
    ws.freeze_panes = "B%d" % (annual_header_row + 1)
    # Sheet2 季报数据
    if not preserve_quarterly:
        ws2 = wb.create_sheet("季报数据")
        ws2.cell(row=1, column=1, value=title + " · 季报数据").font = TITLE_FONT
        ws2.cell(row=2, column=1, value="口径：单季（由累计利润表推导）。").font = SUB_FONT
        if q_headers and q_rows:
            _write_table(ws2, 4, q_headers, q_rows)
            qw = {"A": 30}
            for i in range(2, len(q_headers)):
                qw[openpyxl.utils.get_column_letter(i)] = 14
            _autosize(ws2, qw)
            ws2.freeze_panes = "B5"
        else:
            ws2.cell(row=4, column=1, value="（暂无单季数据）").font = SUB_FONT
    # Sheet3 数据来源与口径说明
    if "数据来源与口径说明" not in wb.sheetnames:
        ws3 = wb.create_sheet("数据来源与口径说明")
    else:
        ws3 = wb["数据来源与口径说明"]
    ws3.cell(row=1, column=1, value=title + " · 数据来源与口径说明").font = TITLE_FONT
    r = 3
    for line in source_text:
        c = ws3.cell(row=r, column=1, value=line)
        c.font = METRIC_FONT if not line.startswith("·") else SUB_FONT
        c.alignment = LEFT
        ws3.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1
    ws3.cell(row=r + 1, column=1, value="抓取时间：%s" % C.__dict__.get("_FETCH_TS_", "运行时")).font = SUB_FONT
    ws3.column_dimensions["A"].width = 120
    wb.save(path)
    print("  已生成：", file_name)
    return path


def write_dataset(dataset, out_dir=C.OUT_DIR):
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for f in dataset:
        p = build_file(
            out_dir, f["file_name"], f["title"], f["annual_headers"],
            f["annual_rows"], f["q_headers"], f["q_rows"], f["source_text"],
            years_as_rows=f.get("years_as_rows", False),
            annual_header_row=f.get("annual_header_row", 4),
            preserve_quarterly=f.get("preserve_quarterly", False),
        )
        paths.append(p)
    return paths
