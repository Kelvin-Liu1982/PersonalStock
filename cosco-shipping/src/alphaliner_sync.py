# -*- coding: utf-8 -*-
"""Alphaliner PublicTop100 → 本地 Excel 同步模块。

数据源：https://alphaliner.axsmarine.com/PublicTop100/
  · 页面用 Ext.Direct  remoting（rooter.php），两个方法：
      top100.getTop100Table   → 100 家运营商全字段（含自有/租入/订单拆分）
      top100.getTextCalculations → Global figures（在运营船舶/TEU/DWT、fully cellular、区域周运力）
  · 纯 HTTP POST 即可取到，无需浏览器/登录。

写入 `数据源/中远海控_行业供需与运价数据.xlsx` 的**单张合并表**：
  · `Alphaliner周报（全球&中远）` —— 表头第 3 行、数据自第 4 行起，23 列
    （A–I 官网 Global figures；J–V COSCO Group 一行；W 数据来源）
  · 同一「发布时间」只保留一行：再次点击覆盖该行，不重复追加。
  · 不再创建已废弃的 `Alphaliner-全球运力` / `Alphaliner-中远海控` 两张表。

用法：
  python src/alphaliner_sync.py            # 抓取并写入
  python src/alphaliner_sync.py --dry-run  # 只抓取打印，不写文件
  python src/alphaliner_sync.py --verify   # 只读校验最新一期（自动化第 3 步）
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from copy import copy
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # 项目根 = src/ 的上一级
AL_XLSX = os.path.join(ROOT, "数据源", "中远海控_Alphaliner周报数据.xlsx")

API_URL = "https://alphaliner.axsmarine.com/PublicTop100/rooter.php"
PAGE_URL = "https://alphaliner.axsmarine.com/PublicTop100/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")

DATA_START = 2          # 表头第 1 行，数据自第 2 行
HEAD_G = ["发布时间", "全球在运营船舶(艘)", "全球运力(TEU)", "总载重吨(DWT)",
          "其中全集装箱船(艘)", "全集装箱船运力(TEU)",
          "跨大西洋周运力(TEU)", "跨太平洋周运力(TEU)", "远东-欧洲周运力(TEU)"]
HEAD_C = ["发布时间", "运营商", "排名", "全球份额(%)", "总运力(TEU)", "总艘数",
          "自有运力(TEU)", "自有艘数", "租入运力(TEU)", "租入艘数", "租入占比(%)",
          "手持订单(TEU)", "订单艘数", "订单占现有运力(%)"]

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

# ---------------------------------------------------------------- 写表


def _as_day(v):
    """单元格 → 'YYYY-MM-DD'；非日期返回 None（跳过表下说明区）。"""
    if hasattr(v, "date"):
        return v.date().isoformat()
    s = str(v)[:10] if v is not None else ""
    return s if re.match(r"^20\d\d-\d\d-\d\d$", s) else None


def check_lock(xlsx=None):
    """写入前预检：Excel 锁文件存在时直接拒绝，避免破坏用户正在编辑的表格。"""
    path = xlsx or AL_XLSX
    lock = os.path.join(os.path.dirname(path), "~$" + os.path.basename(path))
    if os.path.exists(lock):
        raise RuntimeError("检测到 Excel 锁文件 ~$%s，请先关闭表格再运行"
                           % os.path.basename(path))
    if not os.path.exists(path):
        raise RuntimeError("找不到 %s；本脚本只写不建，请先确认文件存在" % path)


def _last_data_row(ws):
    """返回最后一行有效日期数据所在行号；无数据则回到表头行。"""
    last = DATA_START - 1
    for r in range(DATA_START, ws.max_row + 1):
        if _as_day(ws.cell(r, 1).value):
            last = r
    return last


def verify(xlsx=None, expected_date=None, points_per_source=5):
    """只读校验最新一期快照 —— 周六自动化第 3 步，CLI 与「同步」按钮共用。

    ① 「全球」「COSCO」末行发布时间均为期望日期（默认当天）
    ② 两表数据行数相等
    ③ 「分析要点」中「全球」「COSCO」两组要点的数据截止 == 最新日期，且每组恰好 N 条

    不抛异常：任何失败都以 checks 里的 False + detail 返回，便于调用方照实展示。
    """
    path = xlsx or AL_XLSX
    day = expected_date or datetime.now().strftime("%Y-%m-%d")
    out = {"ok": False, "expected_date": day, "asof": None, "checks": {},
           "all_passed": False, "rows": {}, "points": {}, "error": None}
    if not os.path.exists(path):
        out["error"] = "找不到 %s" % path
        return out
    try:
        wb = openpyxl.load_workbook(path, data_only=True)
        missing = [s for s in ("全球", "COSCO", "分析要点") if s not in wb.sheetnames]
        if missing:
            out["error"] = "缺少 sheet：%s" % "、".join(missing)
            return out

        g, c = wb["全球"], wb["COSCO"]
        gr, cr = _last_data_row(g), _last_data_row(c)
        gd = _as_day(g.cell(gr, 1).value) if gr >= DATA_START else None
        cd = _as_day(c.cell(cr, 1).value) if cr >= DATA_START else None
        out["asof"] = gd
        out["rows"] = {"全球": gr - DATA_START + 1, "COSCO": cr - DATA_START + 1}
        out["checks"]["dates_match"] = {
            "ok": gd == day and cd == day,
            "detail": "全球末行 %s / COSCO 末行 %s（期望 %s）" % (gd, cd, day)}
        out["checks"]["rows_equal"] = {
            "ok": gr == cr,
            "detail": "全球 %d 期 / COSCO %d 期" % (out["rows"]["全球"], out["rows"]["COSCO"])}

        a = wb["分析要点"]
        cnt, asofs = {"全球": 0, "COSCO": 0}, set()
        for r in range(2, a.max_row + 1):
            src = str(a.cell(r, 2).value or "").strip()
            d = _as_day(a.cell(r, 1).value)
            if src in cnt and d == day:
                cnt[src] += 1
                asofs.add(d)
        out["points"] = cnt
        out["checks"]["analysis_points"] = {
            "ok": (all(v == points_per_source for v in cnt.values())
                   and asofs == {day}),
            "detail": "全球 %d 条 / COSCO %d 条，数据截止 %s（期望各 %d 条、截止 %s）"
                      % (cnt["全球"], cnt["COSCO"], "/".join(sorted(asofs)) or "—",
                         points_per_source, day)}

        out["all_passed"] = all(v["ok"] for v in out["checks"].values())
        out["ok"] = out["all_passed"]
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, e)
    return out


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


def _upsert(sheet, day, cells, head):
    """按发布时间在某张表 upsert 一行；cells={列名: 值}，未给出的列保留原值。"""
    check_lock()
    bak = os.path.join(tempfile.gettempdir(),
                       "bak_alphaliner_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(AL_XLSX, bak)

    wb = openpyxl.load_workbook(AL_XLSX)
    if sheet not in wb.sheetnames:
        raise RuntimeError("找不到 sheet「%s」；已停止，不会新建" % sheet)
    ws = wb[sheet]
    head_now = [str(ws.cell(1, c).value or "").strip() for c in range(1, len(head) + 1)]
    if head_now != head:
        raise RuntimeError("「%s」表头与预期不符：%r" % (sheet, head_now))

    target, last = None, DATA_START - 1
    for r in range(DATA_START, ws.max_row + 1):
        k = _as_day(ws.cell(r, 1).value)
        if k and re.match(r"^\d{4}-\d{2}-\d{2}$", str(k)):
            last = r
            if str(k) == day:
                target = r
    action = "updated" if target else "appended"
    if target is None:
        target = last + 1
    style_row = max(DATA_START, target - 1)
    for i2, h in enumerate(head, 1):
        cell = ws.cell(target, i2)
        if i2 == 1:
            cell.value = day
        elif h in cells:
            cell.value = cells[h]
        elif target > last:
            cell.value = None
        if target > last:
            cell._style = copy(ws.cell(style_row, i2)._style)
    wb.save(AL_XLSX)
    _fix_empty_fills(AL_XLSX)
    return {"sheet": sheet, "row": target, "action": action,
            "publish_date": day, "backup": bak}


def write(payload):
    """把一次 PublicTop100 抓取结果分别写入 `全球` 与 `COSCO` 两张表。"""
    g, c = payload["global"], payload["cosco"]
    day = payload.get("publish_date") or payload["fetched_at"][:10]
    gc = {
        "全球在运营船舶(艘)": g.get("active_ships"),
        "全球运力(TEU)": g.get("active_teu"),
        "总载重吨(DWT)": g.get("active_dwt"),
        "其中全集装箱船(艘)": g.get("fully_ships"),
        "全集装箱船运力(TEU)": g.get("fully_teu"),
        "跨大西洋周运力(TEU)": g.get("weekly_transatlantic"),
        "跨太平洋周运力(TEU)": g.get("weekly_transpacific"),
        "远东-欧洲周运力(TEU)": g.get("weekly_europe"),
    }
    # 「全球份额(%)」源表是 #REF! 断链，这里按 公司总运力 ÷ 全球运力 直接算百分数
    share = None
    if c.get("total_teu") and g.get("active_teu"):
        share = round(c["total_teu"] / g["active_teu"] * 100, 4)
    cc = {
        "运营商": c.get("operator") or TARGET_OPERATOR,
        "排名": c.get("rank"), "全球份额(%)": share,
        "总运力(TEU)": c.get("total_teu"), "总艘数": c.get("total_ships"),
        "自有运力(TEU)": c.get("owned_teu"), "自有艘数": c.get("owned_ships"),
        "租入运力(TEU)": c.get("chart_teu"), "租入艘数": c.get("chart_ships"),
        "租入占比(%)": c.get("chart_pct"),
        "手持订单(TEU)": c.get("order_teu"), "订单艘数": c.get("order_ships"),
        "订单占现有运力(%)": c.get("order_pct"),
    }
    r1 = _upsert("全球", day, {k: v for k, v in gc.items() if v is not None}, HEAD_G)
    r2 = _upsert("COSCO", day, {k: v for k, v in cc.items() if v is not None}, HEAD_C)
    # 注意：键名必须避开 global / cosco —— sync() 里 payload 的这两键是抓取的原始数据
    return {"ok": True, "publish_date": day,
            "global_row": r1, "cosco_row": r2,
            "backup": r1["backup"], "file": AL_XLSX}


def write_analysis():
    """用最新快照重新生成「分析要点」，写入 `分析要点` 表。

    Alphaliner 官网不给任何文字洞察，所以这一块的分析全部由本表数据生成
    （生成函数在 build_weekly_pages.py，保证页面与表内文字同源）。
    """
    from build_weekly_pages import al_points_global, al_points_cosco, read_alphaliner
    from drewry_ingest import _ensure_analysis_sheet, _upsert_analysis

    al = read_alphaliner(AL_XLSX)
    if not al:
        return {}
    asof = al[-1]["d"]
    wb = openpyxl.load_workbook(AL_XLSX)
    ws, created = _ensure_analysis_sheet(wb)
    out = {"asof": asof, "sheet_created": created, "sources": {}}
    for src, fn in (("全球", al_points_global), ("COSCO", al_points_cosco)):
        title, pts = fn(al)
        if not pts:
            continue
        n, dropped = _upsert_analysis(ws, asof, src, title, pts)
        out["sources"][src] = {"written": n, "replaced": dropped}
    wb.save(AL_XLSX)
    _fix_empty_fills(AL_XLSX)
    return out


def add_global_row(publish_date, **vals):
    """补录一条历史快照到 `全球` 表。可传 ships/teu/dwt/fc_ships/fc_teu/ta/tp/eu。"""
    cells = {
        "全球在运营船舶(艘)": vals.get("ships"), "全球运力(TEU)": vals.get("teu"),
        "总载重吨(DWT)": vals.get("dwt"),
        "其中全集装箱船(艘)": vals.get("fc_ships"),
        "全集装箱船运力(TEU)": vals.get("fc_teu"),
        "跨大西洋周运力(TEU)": vals.get("ta"),
        "跨太平洋周运力(TEU)": vals.get("tp"),
        "远东-欧洲周运力(TEU)": vals.get("eu"),
    }
    return _upsert("全球", publish_date,
                   {k: v for k, v in cells.items() if v is not None}, HEAD_G)


def add_cosco_row(publish_date, **vals):
    """补录中远字段到 `COSCO` 表（只填给出的列，其余保留原值）。"""
    cells = {
        "运营商": vals.get("operator") or TARGET_OPERATOR,
        "排名": vals.get("rank"), "全球份额(%)": vals.get("share"),
        "总运力(TEU)": vals.get("total_teu"), "总艘数": vals.get("total_ships"),
        "自有运力(TEU)": vals.get("owned_teu"), "自有艘数": vals.get("owned_ships"),
        "租入运力(TEU)": vals.get("chart_teu"), "租入艘数": vals.get("chart_ships"),
        "租入占比(%)": vals.get("chart_pct"),
        "手持订单(TEU)": vals.get("order_teu"), "订单艘数": vals.get("order_ships"),
        "订单占现有运力(%)": vals.get("order_pct"),
    }
    return _upsert("COSCO", publish_date,
                   {k: v for k, v in cells.items() if v is not None}, HEAD_C)


def sync() -> dict:
    """抓取当日 PublicTop100 → 写入 `全球`/`COSCO` → 重新生成 `分析要点`。

    只负责数据落库；页面渲染与校验由调用方（自动化 CLI / 同步按钮服务）串联。
    """
    t0 = time.time()
    check_lock()                      # 抓取前预检，避免锁表时白抓一次
    payload = fetch()
    info = write(payload)
    info["analysis"] = write_analysis()
    out = {"ok": True, **payload, **info, "elapsed_ms": int((time.time() - t0) * 1000)}
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Alphaliner PublicTop100 → Excel 同步")
    ap.add_argument("--dry-run", action="store_true", help="只抓取并打印，不写文件")
    ap.add_argument("--verify", action="store_true",
                    help="只读校验最新一期（不抓取、不写文件），供自动化与按钮共用")
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

    if args.verify:
        print(json.dumps(verify(), ensure_ascii=False, indent=1))
        return 0
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
