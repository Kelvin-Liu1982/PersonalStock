#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""需求侧 · 中游炼厂高频指标（美国开工率 + 中国加工量/进口量）。

产出 data/processed/refinery.json，注入 data/dataset/ 由
src/pipeline/build_dataset.py 统一负责（本模块不写域数据）。

- usUtilMonths / usUtil : 美国炼厂开工率月均（2024-01 .. 最新），来自 EIA 周度
                          PET.WPULEUS3.W，按自然月对周度值取平均。
- cnProcMonths / cnProc : 中国原油加工量（国家统计局，万吨/月）。用户依据统计局
                          月度数据手动录入，现改由 data/raw/cn_crude_import and processing.xlsx
                          （sheet「中国原油加工量」）维护（2024-01 起，1/2 月为非官方均分估算）。
- cnImportMonths / cnImport : 中国原油进口量（海关总署，万吨/月）。用户依据海关
                          月度进出口快讯手动录入，现改由 data/raw/cn_crude_import and processing.xlsx
                          （sheet「中国原油进口量」）维护（2024-01 起）。

运行：在仓库根目录执行 `python -m src.fetch.demand.refinery`
"""
import datetime, json, os

from src import config
from src.common.deps import require_openpyxl
from src.common.http import fetch_json_urlopen
from src.paths import DATA_PROCESSED, DATA_RAW

SID = "PET.WPULEUS3.W"
START_MONTH = "2024-01"  # 与原油加工量(中国) xlsx 窗口对齐，展示更多历史

# 中国原油进口量 / 加工量手动数据源（xlsx，已合并为单一工作簿，按 sheet 分别读取）。
# 缺失时回退到内置硬编码 fallback。
CN_IMPORT_XLSX = os.path.join(DATA_RAW, "cn_crude_import and processing.xlsx")

# 中国原油加工量手动数据源（同一合并工作簿，sheet「中国原油加工量」）。
# 缺失时回退到内置硬编码 fallback。
CN_PROC_XLSX = os.path.join(DATA_RAW, "cn_crude_import and processing.xlsx")


def fetch_eia(sid=SID):
    """抓取 EIA 周度序列，返回 ``{period: value}``；失败返回 {}（不抛错）。"""
    url = f"https://api.eia.gov/v2/seriesid/{sid}?api_key={config.EIA_KEY}"
    payload = fetch_json_urlopen(url, timeout=30)
    if not payload or "error" in payload:
        print(f"  [demand]  {sid} 抓取失败: {payload.get('error') if payload else 'empty'}")
        return {}
    rows = payload.get("response", {}).get("data", [])
    # period 形如 "2026-07-24"（周截止周五），value 为浮点数
    return {x["period"]: float(x["value"]) for x in rows if x.get("value") is not None}


def month_avg(pmap):
    """average weekly values per YYYY-MM, return sorted (months, vals)."""
    by = {}
    for p, v in pmap.items():
        m = p[:7]
        by.setdefault(m, []).append(v)
    months = sorted(m for m in by if m >= START_MONTH)
    vals = [round(sum(by[m]) / len(by[m]), 2) for m in months]
    return months, vals


def load_cn_import_xlsx(path=CN_IMPORT_XLSX):
    """读取 data/raw/cn_crude_import and processing.xlsx 的「中国原油进口量」工作表。

    预期表头：年月 | 年份 | 月份 | 当月进口量（万吨） | 累计进口量（万吨） | ...
    返回 [("YYYY-MM", value), ...]，按年月排序；失败返回空列表。
    """
    if not os.path.exists(path):
        print(f"  [demand]  {path} 不存在，中国进口量回退到内置数据")
        return []
    try:
        wb = require_openpyxl().load_workbook(path, data_only=True)
        ws = wb["中国原油进口量"]
    except Exception as e:
        print(f"  [demand]  读取 {path} 失败: {e}，回退到内置数据")
        return []

    # 找表头行（默认第一行）
    headers = [c.value for c in ws[1]]
    try:
        col_month = headers.index("年月")
        col_value = headers.index("当月进口量（万吨）")
    except ValueError:
        # 兼容：按位置读取（A=年月, D=当月进口量）
        col_month, col_value = 0, 3

    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[col_month] is None:
            continue
        mraw = row[col_month]
        if isinstance(mraw, (datetime.datetime, datetime.date)):
            month = mraw.strftime("%Y-%m")
        else:
            month = str(mraw).strip()
            # 兼容「2026-08-01 00:00:00」这类字符串形态（xlsx 年月列混用日期类型）
            if len(month) >= 10 and month[4] == "-" and month[7] == "-":
                month = month[:7]
        val = row[col_value]
        if val is None:
            continue
        try:
            out.append((month, float(val)))
        except (ValueError, TypeError):
            continue

    wb.close()
    out.sort(key=lambda x: x[0])
    print(f"  [demand]  中国原油进口量 xlsx：读取 {len(out)} 个月，{out[0][0]} ~ {out[-1][0]}")
    return out


def load_cn_proc_xlsx(path=CN_PROC_XLSX):
    """读取 data/raw/cn_crude_import and processing.xlsx 的「中国原油加工量」工作表。

    支持两种表头：
      - 旧式：年月 | ... | 当月加工量（万吨）（年月列可能是日期类型，需归一化）
      - 新式：年份 | 月份 | 当月加工量（万吨） | 同比 | 备注
    返回 [("YYYY-MM", value), ...]，按年月排序；失败返回空列表。
    """
    if not os.path.exists(path):
        print(f"  [demand]  {path} 不存在，中国加工量回退到内置数据")
        return []
    try:
        wb = require_openpyxl().load_workbook(path, data_only=True)
        ws = wb["中国原油加工量"]
    except Exception as e:
        print(f"  [demand]  读取 {path} 失败: {e}，回退到内置数据")
        return []

    headers = [c.value for c in ws[1]]

    def _idx(name):
        try:
            return headers.index(name)
        except ValueError:
            return None

    i_ym = _idx("年月")
    i_year = _idx("年份")
    i_month = _idx("月份")
    i_val = _idx("当月加工量（万吨）")
    has_split = (i_year is not None and i_month is not None)
    # 取值列：优先按表头，其次 新式(2) / 旧式(3) 兜底
    col_value = i_val if i_val is not None else (2 if has_split else 3)

    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row:
            continue
        # ---- 解析月份键 YYYY-MM ----
        if i_ym is not None:
            mraw = row[i_ym]
            if mraw is None:
                continue
            if isinstance(mraw, (datetime.datetime, datetime.date)):
                month = mraw.strftime("%Y-%m")
            else:
                month = str(mraw).strip()
                if len(month) >= 10 and month[4] == "-" and month[7] == "-":
                    month = month[:7]
        elif has_split:
            yv, mv = row[i_year], row[i_month]
            if yv is None or mv is None:
                continue
            try:
                month = f"{int(yv):04d}-{int(mv):02d}"
            except (ValueError, TypeError):
                continue
        else:
            continue
        # ---- 取值 ----
        val = row[col_value] if col_value < len(row) else None
        if val is None:
            continue
        try:
            out.append((month, float(val)))
        except (ValueError, TypeError):
            continue

    wb.close()
    out.sort(key=lambda x: x[0])
    print(f"  [demand]  中国原油加工量 xlsx：读取 {len(out)} 个月，"
          f"{out[0][0] if out else '—'} ~ {out[-1][0] if out else '—'}")
    return out


def _missing_months(months):
    """返回 months（YYYY-MM 升序）首尾区间内缺失的月份列表；无缺失返回 []。"""
    if not months:
        return []
    parts = [tuple(int(x) for x in m.split("-")) for m in months]
    y, mo = parts[0]
    end_y, end_mo = parts[-1]
    gap = []
    while (y, mo) <= (end_y, end_mo):
        key = f"{y:04d}-{mo:02d}"
        if key not in months:
            gap.append(key)
        mo += 1
        if mo > 12:
            mo = 1
            y += 1
    return gap


def build(pmap):
    """组装 refinery.json 的内容。pmap 为空时美国开工率段留空。"""
    months, vals = month_avg(pmap) if pmap else ([], [])
    if months:
        print("US util monthly:", months[0], "->", months[-1], "n=", len(months))
        print("latest 3 monthly util:", list(zip(months[-3:], vals[-3:])))
    else:
        print("  [demand]  美国开工率无数据，该段留空")

    us_util_meta = (
        "美国炼厂开工率：EIA 周度 PET.WPULEUS3.W（炼油厂开工率，%），"
        "按自然月对周度值取平均。最新月 " + (months[-1] if months else "—") + "。"
    )

    # ---- China crude processing (国家统计局 原油加工量, 万吨/月) ----
    # 用户依据国家统计局月度数据手动录入，现改由 xlsx 维护。
    # 口径：国家统计局「能源主要产品产量 → 原油加工量」，单位 万吨/月。
    cn_proc = load_cn_proc_xlsx()
    if not cn_proc:
        # fallback hardcode（与旧版本一致，保证 xlsx 缺失时仍可 build）
        cn_proc = [
            ("2025-07", 6306.4), ("2025-08", 6346.5), ("2025-09", 6268.7),
            ("2025-10", 6342.8), ("2025-11", 6082.6), ("2025-12", 6245.9),
            ("2026-03", 6167.3), ("2026-04", 5464.5), ("2026-05", 5372.5),
            ("2026-06", 5123.8),
        ]
        print("  [demand]  中国原油加工量使用内置 fallback 数据")
    cn_months = [m for m, _ in cn_proc]
    cn_vals = [v for _, v in cn_proc]
    missing = _missing_months(cn_months)
    gap_note = ("（缺 " + "、".join(missing) + "）") if missing else ""
    cn_meta = (
        "中国原油加工量（国家统计局，万吨/月）：由 data/raw/cn_crude_import and processing.xlsx 维护，"
        f"覆盖 {cn_months[0]}~{cn_months[-1]}{gap_note}，单位 万吨。"
    )

    # ---- China crude oil imports (海关总署 原油进口量, 万吨/月) ----
    # 用户依据海关总署月度进出口快讯手动录入，现改由 xlsx 维护。
    # 口径：海关总署「原油进口量（货量）」，单位 万吨/月（当月值，非累计）。
    cn_import = load_cn_import_xlsx()
    if not cn_import:
        # fallback hardcode（与旧版本一致，保证 xlsx 缺失时仍可 build）
        cn_import = [
            ("2025-06", 4987.8), ("2025-07", 4719.0), ("2025-08", 4918.6),
            ("2025-09", 4690.2), ("2025-10", 4833.6), ("2025-11", 5078.0),
            ("2025-12", 5596.4), ("2026-01", 4888.9), ("2026-02", 4804.5),
            ("2026-03", 4998.2), ("2026-04", 3847.1), ("2026-05", 3308.1),
        ]
        print("  [demand]  中国原油进口量使用内置 fallback 数据")

    ci_months = [m for m, _ in cn_import]
    ci_vals = [v for _, v in cn_import]
    latest_month = ci_months[-1] if ci_months else "—"
    has_estimate = any(m in ("2026-03", "2026-04", "2026-05") for m in ci_months)
    ci_meta = (
        "中国原油进口量（海关总署，万吨/月）：由 data/raw/cn_crude_import and processing.xlsx 维护，"
        f"覆盖 {ci_months[0] if ci_months else '—'}~{latest_month}。"
        "2026 年初中美贸易摩擦叠加油价高位，进口明显回落；"
        f"{latest_month} 约 {ci_vals[-1]:.0f} 万吨。"
        f"{'2026-03/04/05 为预估值。' if has_estimate else ''}单位 万吨。"
    )

    return {
        "usUtilMonths": months, "usUtil": vals, "usUtilMeta": us_util_meta,
        "cnProcMonths": cn_months, "cnProc": cn_vals, "cnProcMeta": cn_meta,
        "cnImportMonths": ci_months, "cnImport": ci_vals, "cnImportMeta": ci_meta,
    }


def main():
    pmap = fetch_eia()
    ref = build(pmap)
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    path = os.path.join(DATA_PROCESSED, "refinery.json")
    with open(path, "w") as f:
        json.dump(ref, f, ensure_ascii=False, indent=2)
    print("已写出", path)


if __name__ == "__main__":
    main()
