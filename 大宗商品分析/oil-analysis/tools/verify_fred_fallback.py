#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验：FRED 取不到时，批处理侧「沿用上次已提交值」的回落逻辑。

背景（2026-10-22 实测）：FRED 维护期 HTTP 200 返回的是维护页 HTML，
``fetch_fred_csv`` 把它当 CSV 解析后**静默返回 {}**。宏观三条（dxy/dff/dgs10）
与汽油价（gas）会落成全 None —— 图变空是轻的，重的是把「拉取实时」的回落底稿洗掉。

本校验直接驱动 ``src.pipeline.build_dataset._fallback_fred``：
  · FRED 返回空 → 用上一次已提交的 prices.json 填回同名键；
  · **只填旧日期上的旧值**，绝不向新日期前向填充（前向填充 = 凭空造观测，
    会污染 dxy_chg5 预警 / z 分数 / 相关系数矩阵）。

用法（仓库根目录）：python tools/verify_fred_fallback.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import dataio                                    # noqa: E402
from src.pipeline.build_dataset import _fallback_fred     # noqa: E402

CHK = []


def chk(name, ok, detail=""):
    CHK.append((name, bool(ok), detail))
    print(("  ✅ " if ok else "  ❌ ") + name + ("  " + detail if detail else ""))


def main():
    prev = dataio.load_data()
    dates = prev.get("dates") or []
    chk("已有数据集可读（回落底稿存在）", len(dates) > 0, f"dates={len(dates)}")

    # 用真实的 FRED 键名（宏观三条 + 汽油价）跑回落
    series_map = {"dxy": "DTWEXBGS", "dff": "DFF", "dgs10": "DGS10", "gas": "GASREGW"}
    raw = {k: {} for k in series_map}          # 模拟 FRED 全挂

    out = _fallback_fred(dict(raw), series_map, "test")

    for k in series_map:
        rebuilt = out.get(k) or {}
        # 期望：与上一次已提交值逐点一致（日期是 prev 的真子集里的非空点）
        arr = prev.get(k) or []
        expected = {d: arr[i] for i, d in enumerate(dates)
                    if i < len(arr) and arr[i] is not None}
        ok_n = len(rebuilt) == len(expected)
        ok_v = all(rebuilt.get(d) == v for d, v in expected.items())
        chk(f"{k} 沿用旧值", ok_n and ok_v,
            f"{len(rebuilt)} pts，末值 {max(rebuilt) if rebuilt else '-'}"
            f"={rebuilt[max(rebuilt)] if rebuilt else '-'}")
        # 关键断言：不得出现 prev 之外的日期（即没有前向填充到新日期）
        extra = [d for d in rebuilt if d not in set(dates)]
        chk(f"{k} 未向新日期前向填充", not extra, f"越界日期 {len(extra)} 个")

    # FRED 正常时不应改动任何东西
    healthy = {"dxy": {"2026-01-02": 100.0}}
    same = _fallback_fred(dict(healthy), {"dxy": "DTWEXBGS"}, "test")
    chk("FRED 正常时不改写（保持原值）",
        same.get("dxy") == {"2026-01-02": 100.0}, "dxy 原样返回")

    bad = [c for c in CHK if not c[1]]
    print(f"\n{len(CHK) - len(bad)}/{len(CHK)} OK" + ("" if not bad else "  ❌ 存在失败项"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
