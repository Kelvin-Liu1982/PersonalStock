#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Drewry 四大追踪器 → 本地 Excel 落库
===================================
把每期 Drewry 免费追踪器的**数据 + 官方分析要点**写入独立数据文件
`数据源/中远海控_Drewry周报数据.xlsx`，作为 drewry-weekly.html 的唯一数据源。

表结构（一源一表）
------------------
  WCI   World Container Index        → sheet `WCI`   发布日期 / 综合 / 周环比 / 4 条上海出口航线
  IACI  Intra-Asia Container Index   → sheet `IACI`  发布日期 / 综合 / 周环比 / 8 条航线
  CST   Cancelled Sailings Tracker   → sheet `CST`   发布日期 / 覆盖周数 / 计划 / 停航 / 停航率 / 结构 / 营运率
  RST   Red Sea Diversion Tracker    → sheet `RST`   周结束日 / 苏伊士 / 好望角 / 亚欧运力占比 / 备注

各表按**自己的发布日**入库（取 payload 里的 asof；缺省时 CST 兜底 edition_date+1 天）：
  WCI/IACI 周四、CST 周五，同一期在两张表里天然差 1 天，合并时按 ISO 周对齐（见 build_weekly_pages.py）。

分析要点写入 sheet `分析要点`（A–F 列），键 = (数据截止, 来源)：
  A 数据截止 | B 来源 | C 标题 | D 要点 | E 序 | F 采集时间
  同一 (数据截止, 来源) 再次写入会先删除该组旧要点再整组重写，不会重复累加。

单位约定（与旧版单表不同，务必注意）
------------------------------------
  CST 的停航率 / 取消量占比 / 营运率在本文件按 **百分数** 存储（6.0 表示 6%），
  不再是小数比例（0.06）；下游读取端在各脚本边界处自行归一，不依赖本文件。

用法
----
  python src/drewry_ingest.py 数据源/drewry_2026-11-13.json          # 写入
  python src/drewry_ingest.py 数据源/drewry_2026-11-13.json --dry-run # 只打印
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import zipfile
from copy import copy
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DR_XLSX = os.path.join(ROOT, "数据源", "中远海控_Drewry周报数据.xlsx")

SHEET_AN = "分析要点"
AN_HEAD = ["数据截止", "来源", "标题", "要点", "序", "采集时间"]
AN_WIDTH = [13, 8, 52, 96, 6, 18]

# 每个 sheet 的列映射（1-based，与表头一致）。键名与 payload 一致。
COL = {
    "WCI": {"发布日期": 1, "wci": 2, "wow": 3, "rtm": 4, "lax": 5, "goa": 6, "nyc": 7},
    "IACI": {"发布日期": 1, "iaci": 2, "iaci_wow": 3,
             "r_np": 4, "r_tp": 5, "r_sg": 6, "r_yk": 7,
             "r_jk": 8, "r_bs": 9, "r_hc": 10, "r_yy": 11},
    "CST": {"发布日期": 1, "覆盖周数": 2, "planned": 3, "blank_n": 4,
            "blank": 5, "tp": 6, "ae": 7, "ta": 8, "ontime": 9},
    "RST": {"周结束日": 1, "suez": 2, "cape": 3, "ae_share": 4, "备注": 5},
}
DATE_HEAD = {"WCI": "发布日期", "IACI": "发布日期", "CST": "发布日期", "RST": "周结束日"}


# ---------------------------------------------------------------- 工具
def _fix_empty_fills(path):
    """openpyxl 保存后偶发空 <fill/>，修复以免 Excel 报样式错误。"""
    with zipfile.ZipFile(path) as zin:
        names = zin.namelist()
        data = {n: zin.read(n) for n in names}
    key = "xl/styles.xml"
    if key not in data:
        return 0
    s = data[key].decode("utf-8")
    n = s.count("<fill/>")
    if not n:
        return 0
    data[key] = s.replace(
        "<fill/>", '<fill><patternFill patternType="none"/></fill>').encode("utf-8")
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, data[name])
    os.replace(tmp, path)
    return n


def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if hasattr(v, "year") and hasattr(v, "month") and hasattr(v, "day"):
        return v if not hasattr(v, "hour") else v.date()
    if v is None:
        return None
    s = str(v).strip()[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------- 数据表写入
def _find_row(ws, day):
    for r in range(2, ws.max_row + 1):
        if _as_date(ws.cell(r, 1).value) == day:
            return r
    return None


def _last_data_row(ws):
    last = 1
    for r in range(2, ws.max_row + 1):
        if _as_date(ws.cell(r, 1).value):
            last = r
        elif last > 1:
            break                    # 已进入表下口径说明区
    return last


def _upsert_row(ws, day, cells, colmap):
    """按日期写入：已存在则覆盖该行；不存在则在数据区末尾插入新行（说明区随之下移）。"""
    r = _find_row(ws, day)
    action = "update"
    if r is None:
        r = _last_data_row(ws) + 1
        ws.insert_rows(r)
        if r > 2:                    # 沿用上一数据行的样式
            for c in range(1, ws.max_column + 1):
                ws.cell(r, c)._style = copy(ws.cell(r - 1, c)._style)
        action = "append"
    c0 = ws.cell(r, 1)
    c0.value = datetime.combine(day, datetime.min.time())
    c0.number_format = "yyyy-mm-dd"
    c0.alignment = Alignment(horizontal="center")
    for k, v in cells.items():
        if v is None:
            continue
        ws.cell(r, colmap[k], v)
    return r, action


# ---------------------------------------------------------------- 分析要点
def _write_an_header(ws):
    for i, h in enumerate(AN_HEAD, 1):
        c = ws.cell(1, i, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="15616D")
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = AN_WIDTH[i - 1]
    ws.freeze_panes = "A2"


def _ensure_analysis_sheet(wb):
    if SHEET_AN in wb.sheetnames:
        ws = wb[SHEET_AN]
        head = [str(ws.cell(1, c).value or "").strip() for c in range(1, len(AN_HEAD) + 1)]
        if not any(head):            # 空表（用户在 Excel 里手工新建的）→ 补表头
            _write_an_header(ws)
            return ws, True
        if head[:2] != AN_HEAD[:2]:
            raise RuntimeError(
                "sheet「%s」表头与预期不符：%s；已停止，请人工确认后再运行" % (SHEET_AN, head))
        return ws, False
    ws = wb.create_sheet(SHEET_AN)
    _write_an_header(ws)
    return ws, True


def _upsert_analysis(ws, asof, source, title, points):
    """删除同一 (数据截止, 来源) 的旧要点后整组重写，保证幂等。"""
    asof_d = _as_date(asof)
    drop = []
    for r in range(2, ws.max_row + 1):
        d = _as_date(ws.cell(r, 1).value)
        s = str(ws.cell(r, 2).value or "").strip()
        if d and d == asof_d and s == source:
            drop.append(r)
    for r in reversed(drop):
        ws.delete_rows(r, 1)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    # 插在数据区末尾（表下还有「口径与来源说明」区块，不能简单 append）
    row = _last_data_row(ws) + 1
    ws.insert_rows(row, amount=len(points))
    for i, p in enumerate(points):
        r = row + i
        if r > 2:                    # 沿用上一数据行的样式
            for c in range(1, 7):
                ws.cell(r, c)._style = copy(ws.cell(r - 1, c)._style)
    for i, p in enumerate(points, 1):
        vals = [asof_d, source, title if i == 1 else None, p, i, now if i == 1 else None]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row + i - 1, c, v)
            cell.alignment = Alignment(vertical="top", wrap_text=(c == 4))
            if c in (1, 5, 6):
                cell.alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row + i - 1, 1).number_format = "yyyy-mm-dd"
    return len(points), len(drop)


# ---------------------------------------------------------------- 主流程
def ingest(payload: dict, dry_run: bool = False) -> dict:
    ed = _as_date(payload.get("edition_date"))
    if not ed:
        raise ValueError("payload 缺少 edition_date(YYYY-MM-DD)")

    wci = payload.get("wci") or {}
    iaci = payload.get("iaci") or {}
    cst = payload.get("cst") or {}
    rst = payload.get("rst") or {}

    # 每个 sheet 的待写单元格
    plan_cells = {"WCI": {}, "IACI": {}, "CST": {}, "RST": {}}
    for k in ("wci", "wow", "rtm", "lax", "goa", "nyc"):
        if wci.get(k) is not None:
            plan_cells["WCI"][k] = float(wci[k])
    for k in ("iaci", "iaci_wow"):
        if iaci.get(k) is not None:
            plan_cells["IACI"][k] = float(iaci[k])
    for k, v in (iaci.get("routes") or {}).items():
        if k in COL["IACI"] and v is not None:
            plan_cells["IACI"][k] = float(v)
    if cst.get("window"):
        plan_cells["CST"]["覆盖周数"] = str(cst["window"])
    for k in ("planned", "blank_n", "blank", "tp", "ae", "ta", "ontime"):
        if cst.get(k) is not None:
            plan_cells["CST"][k] = float(cst[k])   # 已是百分数，不再 ÷100

    rst_rows = []
    for row in (rst.get("rows") or []):
        d = _as_date(row.get("week_end"))
        if not d:
            continue
        rst_rows.append((d, {k: row[k] for k in ("suez", "cape", "ae_share", "备注")
                             if row.get(k) is not None}))

    plan = {"edition": ed.isoformat(),
            "cells": {s: plan_cells[s] for s in plan_cells if plan_cells[s]},
            "rst_rows": len(rst_rows), "analysis": {}}
    for src, blk in (("WCI", wci), ("IACI", iaci), ("CST", cst), ("RST", rst)):
        pts = blk.get("points") or []
        if pts:
            plan["analysis"][src] = {"asof": blk.get("asof") or ed.isoformat(),
                                     "title": blk.get("title", ""),
                                     "points": pts}

    if dry_run:
        plan["dry_run"] = True
        return plan

    if os.path.exists(os.path.join(os.path.dirname(DR_XLSX),
                                   "~$" + os.path.basename(DR_XLSX))):
        raise RuntimeError("检测到 Excel 锁文件 ~$%s，请先关闭表格再运行"
                           % os.path.basename(DR_XLSX))
    if not os.path.exists(DR_XLSX):
        raise RuntimeError("找不到数据文件 %s；本脚本只写不建，请先确认文件存在" % DR_XLSX)

    bak = os.path.join(tempfile.gettempdir(),
                       "bak_drewry_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(DR_XLSX, bak)

    wb = openpyxl.load_workbook(DR_XLSX)
    written = {}
    for src in ("WCI", "IACI", "CST"):
        cells = plan_cells[src]
        if not cells:
            continue
        if src not in wb.sheetnames:
            raise RuntimeError("找不到 sheet「%s」；已停止，不会新建" % src)
        # 各表按自己的发布日入库：WCI/IACI 周四，CST 周五（晚一天）。
        # 缺 asof 时退回 edition_date；CST 再兜底 +1 天。
        blk = {"WCI": wci, "IACI": iaci, "CST": cst}[src]
        day = _as_date(blk.get("asof")) or ed
        if src == "CST" and not _as_date(blk.get("asof")):
            day = ed + datetime.timedelta(days=1)
        r, act = _upsert_row(wb[src], day, cells, COL[src])
        written[src] = {"row": r, "action": act, "cols": len(cells),
                        "date": day.isoformat()}

    if rst_rows:
        ws = wb["RST"]
        for d, cells in rst_rows:
            r, act = _upsert_row(ws, d, cells, COL["RST"])
            written.setdefault("RST", {"rows": []})["rows"].append(
                {"date": d.isoformat(), "row": r, "action": act})

    ws_an, created = _ensure_analysis_sheet(wb)
    for src, an in plan["analysis"].items():
        n, dropped = _upsert_analysis(ws_an, an["asof"], src, an["title"], an["points"])
        an["written"] = n
        an["replaced"] = dropped

    wb.save(DR_XLSX)
    fixed = _fix_empty_fills(DR_XLSX)
    plan.update({"written": written, "file": DR_XLSX, "backup": bak,
                 "analysis_sheet": SHEET_AN, "analysis_sheet_created": created,
                 "fills_fixed": fixed})

    # 写后自检：WCI（周四）与 CST（周五）应属同一批 ISO 周，逐周一一对应
    chk = openpyxl.load_workbook(DR_XLSX, data_only=True)

    def _weeks(sn):
        ws = chk[sn]
        out = []
        for r in range(2, ws.max_row + 1):
            d = _as_date(ws.cell(r, 1).value)
            if not d:
                break
            out.append(tuple(d.isocalendar()[:2]))
        return out

    ww, cc = _weeks("WCI"), _weeks("CST")
    plan["week_check"] = {"WCI": len(ww), "CST": len(cc), "aligned": ww == cc}
    if ww != cc:
        plan["week_check"]["warn"] = ("WCI 与 CST 的 ISO 周序列不一致；"
                                      "build_weekly_pages.py 会拒绝建页，请先核对两表日期")
    return plan


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if not args:
        print("用法: python src/drewry_ingest.py <payload.json> [--dry-run]")
        return 2
    with open(args[0], encoding="utf-8") as f:
        payload = json.load(f)
    plan = ingest(payload, dry_run=dry)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
