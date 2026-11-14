#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Red Sea Diversion Tracker 图表数字化
====================================
Drewry 的 RST 页面只给一张 PNG 双线图（无数据列、无 Canva 原生数据），
本脚本按像素反算两条周度序列，供 `中远海控_Drewry周报数据.xlsx` 的 `RST` 表使用。

原理
----
  1. 金色 = 经苏伊士，深蓝 = 经好望角（RGB 阈值分离，排除图例圆点）；
  2. 用图上两条已知网格线定标（默认 200 → y=330px、150 → y=478.5px，2.97 px/单位）；
  3. 横轴 57 个等距周点，x 从 91px 到 1040px，对应 2025-10-05 ~ 2026-11-01。

精度与校准（每次换图都要重跑 --calibrate 复核）
----------------------------------------------
  官方正文会给出当期苏伊士艘数（如 53），数字化末点应与之相差 ≤2 艘；
  末 3 周均值、连续 >50 周数也应与正文表述一致。三条都过才可入库。

用法
----
  python src/redsea_digitize.py ~/Downloads/rst.png                 # 打印 57 行 CSV
  python src/redsea_digitize.py ~/Downloads/rst.png --json          # 输出 ingest 可用片段
  python src/redsea_digitize.py ~/Downloads/rst.png --calibrate 53  # 与官方值比对
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys

import numpy as np
from PIL import Image

# 图上网格线的像素行 → 数值（2026-11 版 PNG 实测；换图后需重新标定）
Y200, Y150 = 330.0, 478.5
X0, X1 = 91.0, 1040.0          # 首末周点的像素 x
N = 57                          # 周点数
D0 = datetime.date(2025, 10, 5)  # 首周结束日


def _series(mask, x0=85, x1=1045, y_min=195):
    xs, ys = [], []
    for x in range(x0, x1):
        col = np.nonzero(mask[:, x])[0]
        col = col[col > y_min]          # 排除顶部图例圆点
        if len(col) == 0:
            continue
        xs.append(x)
        ys.append(float(np.median(col)))
    return np.array(xs), np.array(ys)


def digitize(png):
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    sat = a.max(2) - a.min(2)
    gold = (r > 140) & (r < 215) & (g > 95) & (g < 170) & (b < 80) & (sat > 55)
    navy = (b > 45) & (b < 115) & (r < 70) & (g < 85) & (sat > 20)
    per_unit = (Y150 - Y200) / 50.0
    val = lambda y: 200.0 - (y - Y200) / per_unit

    gx, gy = _series(gold)
    nx, ny = _series(navy)
    if len(gx) < N // 2 or len(nx) < N // 2:
        raise RuntimeError("未能识别到足够的线像素，请检查配色阈值或图是否换版")
    step = (X1 - X0) / (N - 1)
    rows = []
    for i in range(N):
        x = X0 + i * step
        suez = int(round(val(gy[np.argmin(abs(gx - x))])))
        cape = int(round(val(ny[np.argmin(abs(nx - x))])))
        rows.append((D0 + datetime.timedelta(days=7 * i), suez, cape))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("png")
    ap.add_argument("--json", action="store_true", help="输出 ingest 用 JSON 片段")
    ap.add_argument("--calibrate", type=float, default=None,
                    help="官方公布的当期苏伊士艘数，用于校准比对")
    a = ap.parse_args()

    rows = digitize(a.png)
    if a.json:
        out = {"rows": [{"week_end": d.isoformat(), "suez": s, "cape": c}
                        for d, s, c in rows[-2:]]}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if a.calibrate is not None:
        last = rows[-1][1]
        tail = [s for _, s, _ in rows[-3:]]
        run = 0
        for _, s, _ in reversed(rows):
            if s > 50:
                run += 1
            else:
                break
        print("末点数字化 %d / 官方 %.0f → 差 %+.0f" % (last, a.calibrate, last - a.calibrate))
        print("末 3 周均值 %.1f；末尾连续 >50 周数 %d" % (sum(tail) / 3.0, run))
        ok = abs(last - a.calibrate) <= 2
        print("校准结论：", "通过（≤2 艘）" if ok else "偏差过大，需重新标定网格线")
        return 0 if ok else 3

    print("week_end,suez,cape")
    for d, s, c in rows:
        print("%s,%d,%d" % (d.isoformat(), s, c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
