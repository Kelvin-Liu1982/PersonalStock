# -*- coding: utf-8 -*-
"""中国联通数据本地化管道 —— 入口。

流程：实时抓取 Eastmoney(00762.HK 利润表/资产负债表、600050.SH 营收历史、行情)
      → 与已核验年报指标合并(实时抓取覆盖 2025) → 持久化为 5 个 XLSX
      （年报数据/季报数据/数据来源与口径说明，遵循中国移动本地存储规范）。

用法：在 china-unicom/ 目录下执行
      python data_pipeline/run.py
依赖：python -m venv 隔离环境已装 openpyxl、requests
"""
import os
import datetime

import config as C
import transform as T
import store as S
import fetcher as F

C.__dict__["_FETCH_TS_"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    print("=" * 64)
    print("中国联通(00762.HK) 数据本地化管道")
    print("输出目录：", C.OUT_DIR)
    print("=" * 64)

    print("\n[1/3] 实时抓取 Eastmoney 真实财报与行情 ...")
    try:
        q = F.fetch_quote()
        px = q.get("f43")
        print("  行情快照 00762.HK 最新价(分):", px, "名称:", q.get("f58"))
    except Exception as e:
        print("  行情抓取失败（不影响财报）：", e)

    print("\n[2/3] 组装数据集（实时抓取覆盖 2025 单元格）...")
    dataset = T.build_dataset()

    print("\n[3/3] 持久化 XLSX（年报/季报/来源说明 三 sheet）...")
    paths = S.write_dataset(dataset, C.OUT_DIR)

    print("\n完成。生成文件：")
    for p in paths:
        print("  -", os.path.relpath(p, C.OUT_DIR))
    print("\n说明：无法核验的年份显示为'—'，待补历年年报；股息率/利差需刷新行情后回填。")


if __name__ == "__main__":
    main()
