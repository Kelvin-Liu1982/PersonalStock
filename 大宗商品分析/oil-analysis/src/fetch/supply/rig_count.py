#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Baker Hughes 官网自动抓取「Worldwide Rig Count（全球旋转钻井平台数）」历史月度序列。
- 官网 rigcount.bakerhughes.com 提供可下载的 Excel（Worldwide Rig Count Report / Worldwide Rig Count Jan2007_xxx.xlsx）。
- 这些静态文件的 UUID 会随每月更新变化，所以本脚本每次从页面实时发现链接，无需硬编码。
- 解析两类结构：
  * 月度报告（含 "WW Monthly" 表）：国家级明细按 (年,月) 求和得到 Worldwide 合计（最权威，与 WW Summary 核对一致）。
  * 长历史文件（含 "Worldwide_Rigcount" 表）：按年份分块，取 "Total World" 列。
- 合并：月度报告（更新、更准）覆盖长历史的重叠月份。
输出：data/processed/rig_world.json -> {months, world, unit, source, retrieved, latest_month}
"""
import datetime
import os, re, json, sys, io
import urllib.request
from src.common.deps import require_openpyxl
from src.common.months import ABBR as MONTHS
from collections import defaultdict

from src.paths import DATA_PROCESSED, DATA_RAW_RIG

# 官网静态文件的 UUID 每月变化，下载到的 Excel 落在 data/raw/rig_count 作为缓存，
# live 发现失败时会回退解析该目录下已存在的文件。
CACHE = DATA_RAW_RIG
os.makedirs(CACHE, exist_ok=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
# 注意：官网 overview 页的 static-files 链接不稳定（常只返回 PDF），
# 而 intl-rig-count 页稳定列出所有 Worldwide Rig Count 的 Excel 下载链接。
OVERVIEW = "https://rigcount.bakerhughes.com/intl-rig-count"


def http_get(url, binary=False, head=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if head:
        req.get_method = lambda: "HEAD"
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read() if not head else b""
        cdisp = r.headers.get("Content-Disposition", "")
        ctype = r.headers.get("Content-Type", "")
        return data, cdisp, ctype


def discover_xlsx():
    """从官网发现所有 static-files 链接，筛选名称含 Worldwide 的 Excel。"""
    html, _, _ = http_get(OVERVIEW)
    txt = html.decode("utf-8", "ignore")
    uuids = re.findall(r"/static-files/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", txt)
    uuids = list(dict.fromkeys(uuids))  # 去重保序
    out = []
    for uid in uuids:
        url = f"https://rigcount.bakerhughes.com/static-files/{uid}"
        try:
            _, cdisp, ctype = http_get(url, head=True)
        except Exception as e:
            print("  HEAD 失败", uid, e)
            continue
        fname = ""
        m = re.search(r'filename="([^"]+)"', cdisp)
        if m:
            fname = m.group(1)
        is_xlsx = "spreadsheetml" in ctype or fname.lower().endswith(".xlsx")
        if is_xlsx and re.search(r"world\s*wide", fname, re.I):
            out.append((uid, fname))
            print("  命中:", fname)
    return out


def load_workbook_from_bytes(data):
    return require_openpyxl().load_workbook(io.BytesIO(data), data_only=True, read_only=True)


def _norm(cell):
    """表头文本归一化：小写 + 只保留字母数字，便于跨版本匹配（'Rig Count Value' -> 'rigcountvalue'）。"""
    if not isinstance(cell, str):
        return ""
    return re.sub(r"[^a-z0-9]", "", cell.strip().lower())


# Year / Month / Rig Count 三列的候选表头名（归一化后比较）。
# ⚠️ 不能写死列索引：Baker Hughes 改版时明细列整体左移了 4 列
# （旧版 Year@5 / Month@6 / RigCountValue@7 → 新版 Year@4 / Month@5 / RigCountValue@6），
# 固定索引会让解析**静默返回空 dict**，表现为「数据源挂了」而不是「表结构变了」，
# 极难排查。改版记录见 data/raw/rig_count/README.md（该文件同时登记各期 xlsx 的
# 覆盖区间与「哪些期次参与合并」，改名或移动前先来这里确认缓存键与合并口径）。
_ALIASES = {
    "year": {"year"},
    "month": {"month"},
    "value": {"rigcountvalue", "rigcount", "rigcountvalues"},
}


def _find_header(rows):
    """按表头文本定位三列，返回 ``(行号, year列, month列, value列)``；找不到返回 None。"""
    for i, r in enumerate(rows):
        if not r:
            continue
        found = {}
        for j, cell in enumerate(r):
            key = _norm(cell)
            if not key:
                continue
            for field, names in _ALIASES.items():
                if field not in found and key in names:
                    found[field] = j
        if len(found) == 3:
            return i, found["year"], found["month"], found["value"]
    return None


def parse_ww_monthly(wb):
    """月度报告：WW Monthly 表国家级明细按 (年,月) 求和 -> Worldwide 合计。"""
    if "WW Monthly" not in wb.sheetnames:
        return {}
    ws = wb["WW Monthly"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = _find_header(rows)
    if hdr is None:
        print("  [rig]    WW Monthly 未找到 Year/Month/Rig Count 表头"
              "（表结构可能再次改版，请检查列位移）")
        return {}
    hidx, iy, im, iv = hdr
    width = max(iy, im, iv)
    agg = defaultdict(float)
    for r in rows[hidx + 1:]:
        if not r or len(r) <= width:
            continue
        if not isinstance(r[iy], int) or not isinstance(r[im], int) or r[iv] is None:
            continue
        agg[(int(r[iy]), int(r[im]))] += float(r[iv])
    print(f"  [rig]    WW Monthly 表头行 {hidx}：Year@{iy} / Month@{im} / RigCount@{iv}")
    return dict(agg)


def _total_world_col(rows):
    """按文本定位 Worldwide_Rigcount 表的 'Total World' 列；找不到返回 None。"""
    for r in rows:
        if not r:
            continue
        for j, cell in enumerate(r):
            key = _norm(cell)
            if key in ("totalworld", "worldtotal", "total"):
                return j
    return None


def parse_worldwide_rigcount(wb):
    """长历史文件：Worldwide_Rigcount 表，按年份分块，取 'Total World' 列。"""
    name = "Worldwide_Rigcount"
    if name not in wb.sheetnames:
        return {}
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    # 旧版固定取 idx 10；改版后按文本定位，两者不一致时以文本定位为准并提示。
    tcol = _total_world_col(rows)
    if tcol is None:
        tcol = 10
        print("  [rig]    Worldwide_Rigcount 未找到 'Total World' 表头，回落旧列位 10")
    elif tcol != 10:
        print(f"  [rig]    Worldwide_Rigcount 'Total World' 列位 {tcol}（旧版为 10）")
    cur_year = None
    result = {}
    for r in rows:
        if not r or len(r) <= tcol:
            continue
        b = r[1]
        # 年份块头：列B 为年份(int)，列C 为地区名(字符串)
        if isinstance(b, int) and isinstance(r[2], str):
            cur_year = b
            continue
        # 数据行：列B 为月份缩写，Total World 列为数值
        if cur_year is not None and b in MONTHS and isinstance(r[tcol], (int, float)):
            result[(cur_year, MONTHS[b])] = float(r[tcol])
    return result


def main():
    print("== 发现 Worldwide Rig Count Excel ==")
    # ⚠️ 官网对脚本与无头浏览器返回 403（Akamai 边缘拦截，2026-10 实测 urllib / curl /
    # playwright 全被挡）。此时 discover_xlsx 直接抛 HTTPError，若不接住，本步骤会崩在
    # 发现阶段、根本走不到下面的「解析本地已下载 xlsx」兜底 —— 序列默默停在旧月份。
    try:
        found = discover_xlsx()
    except Exception as exc:
        print(f"  官网链接发现失败（{type(exc).__name__}: {exc}）→ 改用本地已下载文件")
        found = []
    if not found:
        print("  未从官网发现任何 Worldwide Rig Count Excel，转本地解析。")

    merged = {}
    sources = []
    monthly_buckets = []  # 月度报告（较新，后合并以覆盖重叠月份）
    backbone_buckets = []  # 长历史文件（先合并）
    for uid, fname in found:
        url = f"https://rigcount.bakerhughes.com/static-files/{uid}"
        path = os.path.join(CACHE, uid + ".xlsx")
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            data, _, _ = http_get(url, binary=True)
            with open(path, "wb") as f:
                f.write(data)
        else:
            with open(path, "rb") as f:
                data = f.read()
        wb = load_workbook_from_bytes(data)
        d_m = parse_ww_monthly(wb)
        d = d_m if d_m else parse_worldwide_rigcount(wb)
        wb.close()
        if not d:
            print("  解析为空，跳过:", fname)
            continue
        if d_m:
            monthly_buckets.append((fname, d))
        else:
            backbone_buckets.append((fname, d))
        sources.append((fname, len(d), min(d), max(d)))
        print(f"  解析 {fname}: {len(d)} 个月, {min(d)}~{max(d)}")

    # 合并顺序：先长历史，后月度报告（较新、更准，覆盖重叠月份）
    for fname, d in backbone_buckets:
        merged.update(d)
    for fname, d in monthly_buckets:
        merged.update(d)

    # 兜底：live 发现为空/被拦截时，直接解析本地已下载的 xlsx（两种结构均可）。
    # ⚠️ 必须复刻上面的「先长历史、后月度报告」合并顺序：local 分支若只按文件名排序
    # update，backbone（1975–2024-03）会反过来盖掉月度报告在 2024-01~03 的重叠月份。
    if not merged:
        print(f"  live 未发现，回退解析本地 {DATA_RAW_RIG}/*.xlsx ...")
        local_monthly, local_backbone = [], []
        for fn in sorted(os.listdir(DATA_RAW_RIG)):
            if fn.endswith(".xlsx") and fn not in ("rig_world.xlsx",):
                with open(os.path.join(DATA_RAW_RIG, fn), "rb") as f:
                    data = f.read()
                wb = load_workbook_from_bytes(data)
                d_m = parse_ww_monthly(wb)
                d = d_m if d_m else parse_worldwide_rigcount(wb)
                wb.close()
                if not d:
                    print("  解析为空，跳过:", fn)
                    continue
                (local_monthly if d_m else local_backbone).append((fn, d))
                sources.append((fn, len(d), min(d), max(d)))
                print(f"  解析 {fn}: {len(d)} 个月, {min(d)}~{max(d)}")
        # ⚠️ 只取「期次最新的一份月度报告」合并，不能把所有月度报告都叠加：
        #   目录里可能同时存在多份不同期次的月度报告（当前有 2024-06 / 2025-07 / 2026-09 三期），
        #   它们覆盖范围大量重叠但细项口径随期次变动；若逐份按序 update，旧期次（2025-07）
        #   会回写 2013-01~2025-07 共 116 个月的历史（实测个别月份偏差达 47.6 台）。
        #   主干的 "Total World" 是官方公布的合计列，除最新期次覆盖不到的区间外应予保留。
        # 判据用「自身最新月份」而非文件名：目录里既有 uuid 名又有人工名，字典序与期次无关。
        if local_monthly:
            local_monthly.sort(key=lambda it: max(it[1]))
            newest = local_monthly[-1]
            print(f"  月度报告取最新期次：{newest[0]}（覆盖至 {max(newest[1])}），"
                  f"其余 {len(local_monthly) - 1} 份旧期次不参与合并")
            local_monthly = [newest]
        for _fn, d in local_backbone:
            merged.update(d)
        for _fn, d in local_monthly:
            merged.update(d)

    if not merged:
        print("所有文件解析为空，退出。")
        sys.exit(1)

    keys = sorted(merged)
    months = [f"{y}-{m:02d}" for (y, m) in keys]
    world = [round(merged[k], 1) for k in keys]

    out = {
        "months": months,
        "world": world,
        "unit": "rig count (台)",
        "scope": "Worldwide = 美国 + 加拿大 + 国际（Baker Hughes 全球旋转钻井平台数）",
        "source": "Baker Hughes Worldwide Rig Count (rigcount.bakerhughes.com)",
        "retrieved": datetime.date.today().isoformat(),
        "latest_month": months[-1],
        "files": [s[0] for s in sources],
    }
    out_path = os.path.join(DATA_PROCESSED, "rig_world.json")
    os.makedirs(DATA_PROCESSED, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n完成：{len(months)} 个月, {months[0]} ~ {months[-1]}, 最新={world[-1]}")
    print("输出 ->", out_path)


if __name__ == "__main__":
    main()
