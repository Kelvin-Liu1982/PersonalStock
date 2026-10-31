# -*- coding: utf-8 -*-
"""Alphaliner PublicTop100 → 本地 Excel 同步模块。

数据源：https://alphaliner.axsmarine.com/PublicTop100/
  · 页面用 Ext.Direct  remoting（rooter.php），两个方法：
      top100.getTop100Table   → 100 家运营商全字段（含自有/租入/订单拆分）
      top100.getTextCalculations → Global figures（在运营船舶/TEU/DWT、fully cellular、区域周运力）
  · 纯 HTTP POST 即可取到，无需浏览器/登录。

写入 `数据源/中远海控_行业供需与运价数据.xlsx` 两个 sheet：
  · `Alphaliner-全球运力`      —— 对应官网 Global figures 区块
  · `Alphaliner-中远海控`      —— 对应 COSCO Group 那一行（12 列）

用法：
  python alphaliner_sync.py            # 抓取并写入
  python alphaliner_sync.py --dry-run  # 只抓取打印，不写文件
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
import zipfile
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(HERE, "数据源", "中远海控_行业供需与运价数据.xlsx")

API_URL = "https://alphaliner.axsmarine.com/PublicTop100/rooter.php"
PAGE_URL = "https://alphaliner.axsmarine.com/PublicTop100/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")

SHEET_GLOBAL = "Alphaliner-全球运力"
SHEET_COSCO = "Alphaliner-中远海控"

TARGET_OPERATOR = "COSCO Group"

# ---------------------------------------------------------------- 抓取


def fetch(timeout: int = 45, publish_date: str = None) -> dict:
    """调用 Ext.Direct 接口，返回 {global:{...}, cosco:{...}, fetched_at, source}"""
    payload = json.dumps([
        {"action": "top100", "method": "getTop100Table", "data": None, "type": "rpc", "tid": 1},
        {"action": "top100", "method": "getTextCalculations", "data": None, "type": "rpc", "tid": 2},
    ]).encode("utf-8")
    req = urllib.request.Request(API_URL, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": PAGE_URL,
        "User-Agent": UA,
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("接口返回非 JSON（可能被反爬拦截）：%r" % raw[:200])

    table, calc = None, None
    for it in items:
        if it.get("method") == "getTop100Table":
            table = it.get("result")
        elif it.get("method") == "getTextCalculations":
            calc = it.get("result")
    if not isinstance(table, list) or not table:
        raise RuntimeError("getTop100Table 未返回数据")
    if not isinstance(calc, dict):
        raise RuntimeError("getTextCalculations 未返回数据")

    row = next((r for r in table if str(r.get("operator", "")).strip() == TARGET_OPERATOR), None)
    if row is None:
        row = next((r for r in table if "COSCO" in str(r.get("operator", ""))), None)
    if row is None:
        raise RuntimeError("Top100 表中未找到 %s" % TARGET_OPERATOR)

    def _i(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    act, fully, tot, types = (calc.get("active") or {}), (calc.get("fully") or {}), \
                             (calc.get("total") or {}), (calc.get("types") or {})
    now = datetime.now()
    return {
        "fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "publish_date": publish_date or now.strftime("%Y-%m-%d"),
        "source": PAGE_URL,
        "global": {
            "active_ships": _i(act.get("sum_vessels")),
            "active_teu": _i(act.get("sum_teu")),
            "active_dwt": _i(act.get("sum_dwt")),
            "fully_ships": _i(fully.get("sum_vessels")),
            "fully_teu": _i(fully.get("sum_teu")),
            "total_ships": _i(tot.get("sum_vessels")),
            "total_teu": _i(tot.get("sum_teu")),
            "weekly_transatlantic": _i(types.get("transatlantic")),
            "weekly_transpacific": _i(types.get("transpacific")),
            "weekly_europe": _i(types.get("europe")),
        },
        "cosco": {
            "rank": _i(row.get("rank")),
            "operator": row.get("operator"),
            "share": row.get("percent"),
            "total_teu": _i(row.get("totalTeu")),
            "total_ships": _i(row.get("totalShips")),
            "owned_teu": _i(row.get("ownedTeu")),
            "owned_ships": _i(row.get("ownedShips")),
            "chart_teu": _i(row.get("chartTeu")),
            "chart_ships": _i(row.get("chartShips")),
            "chart_pct": row.get("chartProcent"),
            "order_teu": _i(row.get("orderTeu")),
            "order_ships": _i(row.get("orderShips")),
            "order_pct": row.get("orderProcents"),
            "tooltip": row.get("tooltip"),
        },
    }


# ---------------------------------------------------------------- 写表

HEAD_G = ["发布时间", "全球在运营船舶(艘)", "全球运力(TEU)", "总载重吨(DWT)",
          "其中全集装箱船(艘)", "全集装箱船运力(TEU)",
          "跨大西洋周运力(TEU)", "跨太平洋周运力(TEU)", "远东-欧洲周运力(TEU)", "数据来源"]
HEAD_C = ["发布时间", "排名", "运营商", "全球份额(%)", "总运力(TEU)", "总艘数",
          "自有运力(TEU)", "自有艘数", "租入运力(TEU)", "租入艘数", "租入占比(%)",
          "手持订单(TEU)", "订单艘数", "订单占现有运力(%)", "并表口径说明", "数据来源"]

NOTE_G = ("数据源：Alphaliner PublicTop100 页面 Global figures（接口 top100.getTextCalculations），一手、无需登录；"
          "「全球在运营船舶/运力/DWT」= 页面首行数字，「其中全集装箱船」= fully cellular 口径；"
          "接口 total 字段与 fully 基本一致、已不收录；区域周运力为页面 Regional Trades 区块。"
          "「发布时间」= Alphaliner 页头所显示的数据时点（页面取客户端当日日期，即数据当日），格式 YYYY-MM-DD；同一发布日期只保留一行。")
NOTE_C = ("数据源：Alphaliner PublicTop100（接口 top100.getTop100Table）中 COSCO Group 一行，字段顺序与官网表格一致："
          "总运力/总艘数 → 自有运力/艘数 → 租入(chartered)运力/艘数+占比 → 手持订单运力/艘数+占现有运力比。"
          "「发布时间」= 数据时点（YYYY-MM-DD），同日只保留一行。注意：订单占现有运力比的分母是该公司现有运力（非全球）；全球口径见 `Alphaliner-全球运力` 与月报。")

PCT_G = ()            # 全球表无百分比列
PCT_C = (4, 11, 14)   # 份额 / 租入占比 / 订单占比

THIN = Side(style="thin", color="d0d7de")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HFILL = PatternFill("solid", fgColor="eef2f6")


def _ensure_sheet(wb, name, title, note, head, widths):
    if name in wb.sheetnames:
        return wb[name], False
    ws = wb.create_sheet(name)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(head))
    c = ws.cell(1, 1, title)
    c.font = Font(bold=True, size=13, color="1f2733")
    ws.row_dimensions[1].height = 24
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(head))
    c = ws.cell(2, 1, note)
    c.font = Font(size=9, color="5b6673")
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 58
    for j, h in enumerate(head, start=1):
        c = ws.cell(4, j, h)
        c.font = Font(bold=True, size=10, color="1f2733")
        c.fill = HFILL
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = BORDER
    ws.row_dimensions[4].height = 34
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A5"
    return ws, True


def _as_day(v):
    """把 datetime/date/字符串统一成 'YYYY-MM-DD' 文本，避免 Excel 把日期转成序列值。"""
    if v is None:
        return None
    if isinstance(v, (datetime,)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return s


def _read_rows(ws, ncol):
    out = {}
    for r in range(5, ws.max_row + 1):
        k = ws.cell(r, 1).value
        if k in (None, ""):
            continue
        out[str(k)] = [ws.cell(r, c).value for c in range(1, ncol + 1)]
    return out


def _put_row(ws, date_key, values, ncol, pct_cols=()):
    """按日期写入：同日期覆盖、否则新增，并按日期升序重排（日期键 = 发布时间）。

    pct_cols: 需要固定显示一位小数的列号（份额/百分比），避免 38.0 显示成 38。
    """
    rows = _read_rows(ws, ncol)
    day = str(date_key)[:10]
    # 按「天」匹配已有行（旧键可能是带时分秒的抓取时间），避免重复
    existing = next((k for k in rows if k[:10] == day), None)
    action = "updated" if existing else "appended"
    if existing and existing != str(date_key):
        del rows[existing]
    rows[str(date_key)] = values
    if ws.max_row >= 5:
        ws.delete_rows(5, ws.max_row - 4)
    for k in list(rows):
        rows[k][0] = _as_day(rows[k][0])
    ordered = sorted(rows.items(), key=lambda kv: kv[0])
    for i, (_k, v) in enumerate(ordered, start=5):
        for j in range(1, ncol + 1):
            c = ws.cell(i, j, v[j - 1])
            c.border = BORDER
            c.font = Font(size=10)
            if j == 1:
                c.alignment = Alignment(horizontal="center")
                c.number_format = "@"
            elif j in pct_cols:
                c.number_format = "0.0"
                c.alignment = Alignment(horizontal="right")
            elif isinstance(v[j - 1], (int, float)):
                c.number_format = "#,##0"
                c.alignment = Alignment(horizontal="right")
            elif j == ncol:
                c.alignment = Alignment(wrap_text=True, vertical="top")
                c.font = Font(size=9, color="5b6673")
    row = 5 + [k for k, _ in ordered].index(date_key)
    return row, action


def _canon_restore(path, canon):
    """修复被各种写手（openpyxl/WPS/腾讯文档）改写的等价浮点表示。"""
    with zipfile.ZipFile(path) as zin:
        names = zin.namelist()
        data = {n: zin.read(n) for n in names}
    changed = False
    for (sheetfile, ref), good in canon.items():
        if sheetfile not in data:
            continue
        s = data[sheetfile].decode("utf-8")
        m = re.search(r'(<c r="%s"[^>]*>\s*)<v>([^<]+)</v>' % ref, s)
        if not m:
            continue
        cur = m.group(2)
        try:
            equal = abs(float(cur) - float(good)) <= 1e-15
        except ValueError:
            equal = False
        if cur != good and equal:
            data[sheetfile] = (s[:m.start()] + m.group(1) + "<v>%s</v>" % good
                               + s[m.end():]).encode("utf-8")
            changed = True
    if changed:
        tmp = path + ".tmp"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for n in names:
                zout.writestr(n, data[n])
        os.replace(tmp, path)


CANON = {("xl/worksheets/sheet2.xml", "C8"): "3.0261348005502064E-2"}


def write_sheets(payload: dict) -> dict:
    """把一次抓取结果写入两个 sheet，返回写入位置。"""
    if not os.path.exists(XLSX):
        raise RuntimeError("找不到 %s" % XLSX)
    wb = openpyxl.load_workbook(XLSX)
    created = []

    ws_g, new_g = _ensure_sheet(
        wb, SHEET_GLOBAL,
        "Alphaliner · 全球运力快照（PublicTop100 / Global figures）",
        NOTE_G, HEAD_G,
        [20, 17, 15, 16, 17, 18, 17, 17, 17, 40])
    if new_g:
        created.append(SHEET_GLOBAL)
    g = payload["global"]
    rg, act_g = _put_row(ws_g, payload.get("publish_date") or payload["fetched_at"][:10], [
        payload.get("publish_date") or payload["fetched_at"][:10], g["active_ships"], g["active_teu"], g["active_dwt"],
        g["fully_ships"], g["fully_teu"],
        g["weekly_transatlantic"], g["weekly_transpacific"], g["weekly_europe"],
        payload["source"],
    ], len(HEAD_G), PCT_G)

    ws_c, new_c = _ensure_sheet(
        wb, SHEET_COSCO,
        "Alphaliner · 中远海控（COSCO Group）运力快照",
        NOTE_C, HEAD_C,
        [20, 6, 14, 12, 14, 9, 14, 9, 14, 9, 11, 14, 9, 15, 34, 40])
    if new_c:
        created.append(SHEET_COSCO)
    c = payload["cosco"]
    rc, act_c = _put_row(ws_c, payload.get("publish_date") or payload["fetched_at"][:10], [
        payload.get("publish_date") or payload["fetched_at"][:10], c["rank"], c["operator"], c["share"],
        c["total_teu"], c["total_ships"], c["owned_teu"], c["owned_ships"],
        c["chart_teu"], c["chart_ships"], c["chart_pct"],
        c["order_teu"], c["order_ships"], c["order_pct"],
        c["tooltip"], payload["source"],
    ], len(HEAD_C), PCT_C)

    wb.save(XLSX)
    _canon_restore(XLSX, CANON)
    return {
        "sheets": [SHEET_GLOBAL, SHEET_COSCO],
        "created": created,
        "global_row": rg, "global_action": act_g,
        "cosco_row": rc, "cosco_action": act_c,
        "file": XLSX,
    }


def add_global_row(publish_date: str, **vals) -> dict:
    """补录一条历史快照（数据来自截图/月报等非接口来源）。

    publish_date: YYYY-MM-DD
    可传：ships, teu, dwt, fc_ships, fc_teu, total_ships, total_teu,
          ta, tp, eu（区域周运力）, note（写入来源列）
    """
    wb = openpyxl.load_workbook(XLSX)
    ws, _ = _ensure_sheet(
        wb, SHEET_GLOBAL,
        "Alphaliner · 全球运力快照（PublicTop100 / Global figures）",
        NOTE_G, HEAD_G,
        [20, 17, 15, 16, 17, 18, 17, 17, 17, 40])
    src = vals.get("note") or "Alphaliner PublicTop100 页面（%s）" % publish_date
    values = [
        publish_date, vals.get("ships"), vals.get("teu"), vals.get("dwt"),
        vals.get("fc_ships"), vals.get("fc_teu"),
        vals.get("ta"), vals.get("tp"), vals.get("eu"), src,
    ]
    row, action = _put_row(ws, publish_date, values, len(HEAD_G), PCT_G)
    wb.save(XLSX)
    _canon_restore(XLSX, CANON)
    return {"ok": True, "sheet": SHEET_GLOBAL, "row": row, "action": action,
            "publish_date": publish_date, "file": XLSX}


def add_cosco_row(publish_date: str, **vals) -> dict:
    """补录一条历史快照到 `Alphaliner-中远海控`（数据来自截图/转载文章的 Top30 表）。"""
    wb = openpyxl.load_workbook(XLSX)
    ws, _ = _ensure_sheet(
        wb, SHEET_COSCO,
        "Alphaliner · 中远海控（COSCO Group）运力快照",
        NOTE_C, HEAD_C,
        [20, 6, 14, 12, 14, 9, 14, 9, 14, 9, 11, 14, 9, 15, 34, 40])
    src = vals.get("note") or "Alphaliner TOP 100（%s）" % publish_date
    values = [
        publish_date, vals.get("rank"), vals.get("operator") or TARGET_OPERATOR,
        vals.get("share"), vals.get("total_teu"), vals.get("total_ships"),
        vals.get("owned_teu"), vals.get("owned_ships"),
        vals.get("chart_teu"), vals.get("chart_ships"), vals.get("chart_pct"),
        vals.get("order_teu"), vals.get("order_ships"), vals.get("order_pct"),
        vals.get("tooltip"), src,
    ]
    row, action = _put_row(ws, publish_date, values, len(HEAD_C), PCT_C)
    wb.save(XLSX)
    _canon_restore(XLSX, CANON)
    return {"ok": True, "sheet": SHEET_COSCO, "row": row, "action": action,
            "publish_date": publish_date, "file": XLSX}


def sync() -> dict:
    t0 = time.time()
    payload = fetch()
    info = write_sheets(payload)
    out = {"ok": True, **payload, **info, "elapsed_ms": int((time.time() - t0) * 1000)}
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Alphaliner PublicTop100 → Excel 同步")
    ap.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写文件")
    ap.add_argument("--add-date", help="补录历史快照，格式 YYYY-MM-DD（需配合下面的数值）")
    for k in ("ships", "teu", "dwt", "fc-ships", "fc-teu", "ta", "tp", "eu"):
        ap.add_argument("--" + k, type=int)
    ap.add_argument("--note", help="补录行的来源说明")
    ap.add_argument("--add-cosco", help="补录中远行，格式 YYYY-MM-DD（配合下面的 --c-* 参数）")
    ap.add_argument("--c-rank", type=int)
    ap.add_argument("--c-share", type=float)
    ap.add_argument("--c-total-teu", type=int)
    ap.add_argument("--c-total-ships", type=int)
    ap.add_argument("--c-owned-teu", type=int)
    ap.add_argument("--c-owned-ships", type=int)
    ap.add_argument("--c-chart-teu", type=int)
    ap.add_argument("--c-chart-ships", type=int)
    ap.add_argument("--c-chart-pct", type=float)
    ap.add_argument("--c-order-teu", type=int)
    ap.add_argument("--c-order-ships", type=int)
    ap.add_argument("--c-order-pct", type=float)
    ap.add_argument("--c-tooltip")
    args = ap.parse_args(argv)

    if args.add_date:
        res = add_global_row(
            args.add_date,
            ships=args.ships, teu=args.teu, dwt=args.dwt,
            fc_ships=args.fc_ships, fc_teu=args.fc_teu,
            ta=args.ta, tp=args.tp, eu=args.eu, note=args.note)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    if args.add_cosco:
        res = add_cosco_row(
            args.add_cosco,
            rank=args.c_rank, share=args.c_share,
            total_teu=args.c_total_teu, total_ships=args.c_total_ships,
            owned_teu=args.c_owned_teu, owned_ships=args.c_owned_ships,
            chart_teu=args.c_chart_teu, chart_ships=args.c_chart_ships, chart_pct=args.c_chart_pct,
            order_teu=args.c_order_teu, order_ships=args.c_order_ships, order_pct=args.c_order_pct,
            tooltip=args.c_tooltip, note=args.note)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return 0
    if args.dry_run:
        print(json.dumps(fetch(), ensure_ascii=False, indent=1))
        return 0
    print(json.dumps(sync(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
