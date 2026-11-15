# -*- coding: utf-8 -*-
"""Excel 数据仓读写层。

data/gold_data.xlsx 是单一数据源。本模块负责：
    ensure_workbook()  首次运行时按 schema 的种子值建库
    read_*()           读出各 sheet，供 build_html 生成数据块
    update_snapshot()  fetch 抓到的值写回「行情快照」
    touch_meta()       更新「元数据」里的最后更新时间

依赖：openpyxl（见 gold-analysis/requirements.txt）
"""
import datetime
import os
import sys

# 允许从任意工作目录直接运行本文件（把 src/ 加入模块搜索路径）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openpyxl import Workbook, load_workbook

import paths
import schema


def _fill(ws, header, rows):
    ws.append(list(header))
    for r in rows:
        ws.append(list(r))
    # 表头加粗 + 冻结首行，便于人工维护
    for c in ws[1]:
        c.font = c.font.copy(bold=True)
    ws.freeze_panes = "A2"


def ensure_workbook(force=False):
    """若 Excel 不存在则按种子值创建；force=True 时重建（会清空人工填写的数据）。

    已存在但缺 sheet（向前兼容旧库）时，只补齐缺失的 sheet，不覆盖人工数据。
    """
    path = paths.DATA_XLSX

    # 首次：从零建库
    if not os.path.exists(path):
        os.makedirs(paths.DATA_DIR, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = schema.SHEET_SNAPSHOT
        _fill(ws, schema.HEAD_SNAPSHOT, schema.SEED_SNAPSHOT)
        for name, header, rows in (
            (schema.SHEET_CB_COUNTRY, schema.HEAD_CB_COUNTRY, schema.SEED_CB_COUNTRY),
            (schema.SHEET_CB_MONTHLY, schema.HEAD_CB_MONTHLY, schema.SEED_CB_MONTHLY),
            (schema.SHEET_CB_ANNUAL, schema.HEAD_CB_ANNUAL, schema.SEED_CB_ANNUAL),
            (schema.SHEET_GDT, schema.HEAD_GDT, schema.SEED_GDT),
            (schema.SHEET_CN_CB_MONTHLY, schema.HEAD_CN_CB_MONTHLY, schema.SEED_CN_CB_MONTHLY),
            (schema.SHEET_US_DEBT, schema.HEAD_US_DEBT, schema.SEED_US_DEBT),
            (schema.SHEET_META, schema.HEAD_META, schema.SEED_META),
            (schema.SHEET_EVENTS, schema.HEAD_EVENTS, schema.SEED_EVENTS),
            (schema.SHEET_MACRO_LATEST, schema.HEAD_MACRO_LATEST, schema.SEED_MACRO_LATEST),
            (schema.SHEET_MACRO_SERIES, schema.HEAD_MACRO_SERIES, schema.SEED_MACRO_SERIES),
        (schema.SHEET_GOLD_MONTHLY, schema.HEAD_GOLD_MONTHLY, schema.SEED_GOLD_MONTHLY),
            (schema.SHEET_GOLD_MONTHLY, schema.HEAD_GOLD_MONTHLY, schema.SEED_GOLD_MONTHLY),
        ):
            ws = wb.create_sheet(name)
            _fill(ws, header, rows)
        wb.save(path)
        return path, True

    # force：删后重建
    if force:
        os.remove(path)
        return ensure_workbook(force=False)

    # 已存在：补齐缺失 sheet（迁移旧库），不碰已有数据
    wb = load_workbook(path)
    added = []
    for name, header, rows in (
        (schema.SHEET_CB_COUNTRY, schema.HEAD_CB_COUNTRY, schema.SEED_CB_COUNTRY),
        (schema.SHEET_CB_MONTHLY, schema.HEAD_CB_MONTHLY, schema.SEED_CB_MONTHLY),
        (schema.SHEET_CN_CB_MONTHLY, schema.HEAD_CN_CB_MONTHLY, schema.SEED_CN_CB_MONTHLY),
        (schema.SHEET_US_DEBT, schema.HEAD_US_DEBT, schema.SEED_US_DEBT),
        (schema.SHEET_META, schema.HEAD_META, schema.SEED_META),
        (schema.SHEET_EVENTS, schema.HEAD_EVENTS, schema.SEED_EVENTS),
        (schema.SHEET_CB_ANNUAL, schema.HEAD_CB_ANNUAL, schema.SEED_CB_ANNUAL),
        (schema.SHEET_GDT, schema.HEAD_GDT, schema.SEED_GDT),
        (schema.SHEET_MACRO_LATEST, schema.HEAD_MACRO_LATEST, schema.SEED_MACRO_LATEST),
        (schema.SHEET_MACRO_SERIES, schema.HEAD_MACRO_SERIES, schema.SEED_MACRO_SERIES),
    ):
        if name not in wb.sheetnames:
            ws = wb.create_sheet(name)
            _fill(ws, header, rows)
            added.append(name)
    if added:
        wb.save(path)
    return path, bool(added)


def _sheet_rows(wb, name, min_cols):
    """按 sheet 名取数据行（跳过表头），每行返回 list；空行跳过。"""
    if name not in wb.sheetnames:
        return []
    out = []
    for row in wb[name].iter_rows(min_row=2, values_only=True):
        if row is None or all(v is None for v in row):
            continue
        cells = list(row) + [None] * (min_cols - len(row))
        out.append(cells[:min_cols])
    return out


def read_snapshot():
    """返回 {field: value}（字符串），供 GOLD_DATA 使用。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    d = {}
    for field, value, _n, _s, _f in _sheet_rows(wb, schema.SHEET_SNAPSHOT, 5):
        if field is None:
            continue
        d[str(field)] = "" if value is None else str(value)
    return d


def read_cb_country():
    """图1：返回 [{'name','value','source','note'}]，按净购金量降序（买家在上）。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    rows = []
    for name, value, source, note in _sheet_rows(wb, schema.SHEET_CB_COUNTRY, 4):
        if name is None or value is None:
            continue
        rows.append({
            "name": str(name),
            "value": float(value),
            "source": "" if source is None else str(source),
            "note": "" if note is None else str(note),
        })
    rows.sort(key=lambda x: -x["value"])
    return rows


def read_cb_monthly():
    """图2：返回 [{'month','value'}]，保持 Excel 中的月份顺序。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    rows = []
    for month, value in _sheet_rows(wb, schema.SHEET_CB_MONTHLY, 2):
        if month is None or value is None:
            continue
        rows.append({"month": str(month), "value": float(value)})
    return rows


def read_cn_cb_monthly():
    """中国央行购金月度：返回 [{'month','reserve','add','streak'}]，保持月份顺序。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    rows = []
    for month, reserve, add, streak in _sheet_rows(wb, schema.SHEET_CN_CB_MONTHLY, 4):
        if month is None:
            continue
        rows.append({
            "month": str(month),
            "reserve": _f(reserve),
            "add": _f(add),
            "streak": _f(streak),
        })
    return rows


def read_cb_annual():
    """图3：返回 [{'year','value','note'}]，2002–当年（当年为 YTD）。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    rows = []
    for year, value, note in _sheet_rows(wb, schema.SHEET_CB_ANNUAL, 3):
        if year is None or value is None:
            continue
        rows.append({"year": int(year), "value": float(value), "note": str(note or "")})
    rows.sort(key=lambda r: r["year"])
    return rows


def read_gdt_quarterly():
    """全球黄金供需季度（WGC GDT Gold Balance）：返回 [{'quarter','demand','supply','series'}]。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    out = []
    for row in _sheet_rows(wb, schema.SHEET_GDT, len(schema.HEAD_GDT)):
        q = row[0]
        if q is None:
            continue
        vals = [float(v) if isinstance(v, (int, float)) else 0.0 for v in row[1:11]]
        out.append({
            "quarter": str(q),
            "jewellery": vals[0], "technology": vals[1], "investment": vals[2], "cb": vals[3],
            "demand": vals[4],
            "mine": vals[5], "hedging": vals[6], "mineTotal": vals[7], "recycled": vals[8],
            "supply": vals[9],
        })
    return out


def read_us_debt():
    """债务面板：返回 {'years','debt','r','n','interest','rn'}（等长数组）。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    out = {"years": [], "debt": [], "r": [], "n": [], "interest": [], "rn": []}
    for year, debt, r, n, interest, rn in _sheet_rows(wb, schema.SHEET_US_DEBT, 6):
        if year is None:
            continue
        out["years"].append(int(year))
        out["debt"].append(_f(debt))
        out["r"].append(_f(r))
        out["n"].append(_f(n))
        out["interest"].append(_f(interest))
        out["rn"].append(_f(rn))
    return out


def read_events():
    """黄金事件流：返回 [{'date','title','source','pct','link'}]，**保持 sheet 原序**。

    ⚠️ 不要在这里重排：fetch_event.py 刻意把「本次选中、页面正在显示」的那条放在第 1 行，
    其余按日期倒序。一旦按日期重排，第 1 行会变成更新的候选，与 event 条显示的不一致。
    """
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    rows = []
    for date, title, source, pct, link in _sheet_rows(wb, schema.SHEET_EVENTS, 5):
        if date is None or title is None:
            continue
        rows.append({
            "date": str(date),
            "title": str(title),
            "source": "" if source is None else str(source),
            "pct": "" if pct is None else str(pct),
            "link": "" if link is None else str(link),
        })
    return rows


def write_events(rows):
    """整表覆盖写「黄金事件流」。rows 同 read_events 的结构，按日期倒序。

    只重写这一个 sheet，不动其它 sheet（含人工填写的口径说明）。
    """
    wb = load_workbook(paths.DATA_XLSX)
    if schema.SHEET_EVENTS in wb.sheetnames:
        del wb[schema.SHEET_EVENTS]
    # 插到「元数据」之前，保持与其它数据 sheet 相邻
    idx = wb.sheetnames.index(schema.SHEET_META) if schema.SHEET_META in wb.sheetnames else None
    ws = wb.create_sheet(schema.SHEET_EVENTS, idx)
    _fill(ws, schema.HEAD_EVENTS,
          [(r["date"], r["title"], r["source"], r["pct"], r["link"]) for r in rows])
    wb.save(paths.DATA_XLSX)
    return len(rows)


def read_macro_latest():
    """宏观因子现值：返回 [{key,name,value,date,unit,source,note}]，保持 sheet 顺序。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    out = []
    for row in _sheet_rows(wb, schema.SHEET_MACRO_LATEST, 7):
        if row[0] is None:
            continue
        out.append({
            "key": str(row[0]),
            "name": "" if row[1] is None else str(row[1]),
            "value": "" if row[2] is None else str(row[2]),
            "date": "" if row[3] is None else str(row[3]),
            "unit": "" if row[4] is None else str(row[4]),
            "source": "" if row[5] is None else str(row[5]),
            "note": "" if row[6] is None else str(row[6]),
        })
    return out


def read_macro_series():
    """宏观因子时序：返回 {A2: [{d,v}, ...], ...}，各因子按日期升序。

    长表存储（因子|日期|数值），避免日/季频率不同被强行对齐到同一行。
    """
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    out = {}
    for key, date, value in _sheet_rows(wb, schema.SHEET_MACRO_SERIES, 3):
        if key is None or date is None or value is None:
            continue
        out.setdefault(str(key), []).append({"d": str(date), "v": _f(value)})
    for k in out:
        out[k].sort(key=lambda r: r["d"])
    return out


def write_macro(latest, series):
    """整表覆盖写两个宏观 sheet（不动其它 sheet 的人工数据）。

    latest: 同 read_macro_latest；series: {key: [{d,v}]}
    """
    wb = load_workbook(paths.DATA_XLSX)
    for name, header, rows in (
        (schema.SHEET_MACRO_LATEST, schema.HEAD_MACRO_LATEST,
         [(r["key"], r["name"], r["value"], r["date"], r["unit"], r["source"], r["note"])
          for r in latest]),
        (schema.SHEET_MACRO_SERIES, schema.HEAD_MACRO_SERIES,
         [(k, p["d"], p["v"]) for k in sorted(series) for p in series[k]]),
    ):
        if name in wb.sheetnames:
            del wb[name]
        ws = wb.create_sheet(name)
        _fill(ws, header, rows)
    wb.save(paths.DATA_XLSX)
    return len(latest), sum(len(v) for v in series.values())


def read_gold_monthly():
    """当年月度金价：返回 [{'month','price','note'}]，按月份升序。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    out = []
    for month, price, note in _sheet_rows(wb, schema.SHEET_GOLD_MONTHLY, 3):
        if month is None or price is None:
            continue
        out.append({"month": str(month), "price": _f(price),
                    "note": "" if note is None else str(note)})
    out.sort(key=lambda r: r["month"])
    return out


def write_gold_monthly(rows):
    """整表覆盖写「黄金月度均价」（不动其它 sheet）。"""
    wb = load_workbook(paths.DATA_XLSX)
    if schema.SHEET_GOLD_MONTHLY in wb.sheetnames:
        del wb[schema.SHEET_GOLD_MONTHLY]
    ws = wb.create_sheet(schema.SHEET_GOLD_MONTHLY)
    _fill(ws, schema.HEAD_GOLD_MONTHLY,
          [(r["month"], r["price"], r.get("note", "")) for r in rows])
    wb.save(paths.DATA_XLSX)
    return len(rows)


def read_meta():
    """返回 {key: value}。"""
    wb = load_workbook(paths.DATA_XLSX, data_only=True)
    d = {}
    for key, value, _note in _sheet_rows(wb, schema.SHEET_META, 3):
        if key is None:
            continue
        d[str(key)] = "" if value is None else str(value)
    return d


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def update_snapshot(updates):
    """把 fetch 到的值写回「行情快照」sheet。updates: {field: value}。

    只改 value 列；field 不存在时追加新行（数据源标 fetch）。
    """
    if not updates:
        return 0
    wb = load_workbook(paths.DATA_XLSX)
    ws = wb[schema.SHEET_SNAPSHOT]
    if ws.max_row < 1 or ws.cell(row=1, column=1).value != "field":
        raise RuntimeError("「行情快照」sheet 结构异常，首列应为 field")

    existing = {}
    for r in range(2, ws.max_row + 1):
        k = ws.cell(row=r, column=1).value
        if k is not None:
            existing[str(k)] = r

    n = 0
    for field, value in updates.items():
        row = existing.get(str(field))
        if row is None:
            ws.append([str(field), str(value), "fetch 自动写入", "fetch", "自动"])
        else:
            ws.cell(row=row, column=2).value = str(value)
        n += 1

    wb.save(paths.DATA_XLSX)
    return n


def touch_meta(updates=None):
    """更新「元数据」：默认写入最后更新时间。"""
    payload = {"lastUpdated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if updates:
        payload.update(updates)

    wb = load_workbook(paths.DATA_XLSX)
    if schema.SHEET_META not in wb.sheetnames:
        wb.create_sheet(schema.SHEET_META).append(list(schema.HEAD_META))
    ws = wb[schema.SHEET_META]

    existing = {}
    for r in range(2, ws.max_row + 1):
        k = ws.cell(row=r, column=1).value
        if k is not None:
            existing[str(k)] = r

    for key, value in payload.items():
        row = existing.get(str(key))
        if row is None:
            ws.append([str(key), str(value), ""])
        else:
            ws.cell(row=row, column=2).value = str(value)

    wb.save(paths.DATA_XLSX)
    return payload
