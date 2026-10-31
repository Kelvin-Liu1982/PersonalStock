#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按海关总署官方表修正 需求端-港口吞吐量&出口 sheet 的出口四列，并补 2026-09 行。
数据来源（均可复现，脚本幂等可重复跑）：
  URL1 进出口商品总值表(美元值)B月度表(2026-10-18) -> 出口总额(绝对,百万美元/100=亿) + 2026 出口同比
  URL3 进出口商品总值表(美元值)B月度表(2026-01-18) -> 2025 出口同比（当年表带上年同期同比行；已用绝对/2024-1 逐月交叉验证）
  URL2 2026年9月国别(地区)总值表 + 海关数据点评 -> 2026-09 对东盟/欧盟/美国 单月同比
说明：2025 出口总额绝对值 URL1 与 URL3 有 ~0.1% 差异（改订），此处 col D 取 URL1；col E(同比) 取 URL3 官方同比行。
"""
import openpyxl, zipfile, re, os, sys

XLSX = "数据源/中远海控_行业供需与运价数据.xlsx"
SHEET = "需求端-港口吞吐量&出口"

# 出口总额(亿美元)：URL1 绝对值 ÷100
EXP = {
    "2025-01": 3242.62, "2025-02": 2147.72, "2025-03": 3130.44, "2025-04": 3151.16,
    "2025-05": 3156.31, "2025-06": 3246.17, "2025-07": 3212.16, "2025-08": 3212.81,
    "2025-09": 3281.49, "2025-10": 3049.16, "2025-11": 3299.90, "2025-12": 3572.38,
    "2026-01": 3565.34, "2026-02": 2997.56, "2026-03": 3209.86, "2026-04": 3589.73,
    "2026-05": 3762.66, "2026-06": 4117.55, "2026-07": 3978.60, "2026-08": 4013.82,
    "2026-09": 4471.84,
}
# 出口同比：2025 取 URL3 当年表同比行；2026 取 URL1 同比行
EXP_YOY = {
    "2025-01": 0.059, "2025-02": -0.031, "2025-03": 0.122, "2025-04": 0.080,
    "2025-05": 0.046, "2025-06": 0.058, "2025-07": 0.071, "2025-08": 0.043,
    "2025-09": 0.082, "2025-10": -0.012, "2025-11": 0.059, "2025-12": 0.066,
    "2026-01": 0.100, "2026-02": 0.396, "2026-03": 0.025, "2026-04": 0.139,
    "2026-05": 0.192, "2026-06": 0.268, "2026-07": 0.239, "2026-08": 0.249,
    "2026-09": 0.363,
}
# 2026-09 新行（吞吐量两列留空待 MOT 发布；分区域为 9 月单月同比）
NEW_0926 = ["2026-09", None, None, 4471.84, 0.363, 0.523, 0.253, 0.396]

def empty_fill_count(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("xl/styles.xml").decode("utf-8")
    return len(re.findall(r"<fill\s*/>", xml)) + len(re.findall(r"<fill></fill>", xml))

wb = openpyxl.load_workbook(XLSX)
ws = wb[SHEET]

# 清理尾部空行（年月列为空），避免 append 落到空行之后
last_data = 1
for r in range(2, ws.max_row + 1):
    if ws.cell(r, 1).value not in (None, ""):
        last_data = r
if ws.max_row > last_data:
    ws.delete_rows(last_data + 1, ws.max_row - last_data)
    print(f"[clean] 删除尾部空行（保留至第 {last_data} 行）")

changes = []
for r in range(2, ws.max_row + 1):
    key = str(ws.cell(r, 1).value)
    if key in EXP:
        old = ws.cell(r, 4).value
        if old != EXP[key]:
            ws.cell(r, 4).value = EXP[key]
            changes.append((key, "出口总额", old, EXP[key]))
    if key in EXP_YOY:
        old = ws.cell(r, 5).value
        if old != EXP_YOY[key]:
            ws.cell(r, 5).value = EXP_YOY[key]
            changes.append((key, "出口同比", old, EXP_YOY[key]))

# 仅在缺 2026-09 行时追加（幂等）
if str(ws.cell(ws.max_row, 1).value) != "2026-09":
    ws.append(NEW_0926)
    changes.append(("2026-09", "新增行", "-", "出口4471.84/同比+36.3%/东盟+52.3%/欧盟+25.3%/美国+39.6%"))
else:
    print("[skip] 2026-09 行已存在")

if not changes:
    print("[ok] 无需变更（数据已是最新）"); sys.exit(0)

before = empty_fill_count(XLSX)
tmp = XLSX + ".tmp"
wb.save(tmp)
after = empty_fill_count(tmp)
if after > before:
    os.remove(tmp); raise SystemExit(f"[FATAL] 样式损坏：空 <fill/> {before}->{after}")
os.replace(tmp, XLSX)

print(f"[ok] 已保存（行数={ws.max_row}，空<fill/> {before}->{after}）")
print(f"\n共 {len(changes)} 处变更：")
print(f"{'月份':<9}{'列':<8}{'旧值':<12}{'新值':<12}")
for k, col, o, n in changes:
    print(f"{k:<9}{col:<8}{str(o):<12}{str(n):<12}")
