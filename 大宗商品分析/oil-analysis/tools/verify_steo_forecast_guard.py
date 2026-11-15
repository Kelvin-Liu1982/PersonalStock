# -*- coding: utf-8 -*-
"""校验 STEO 月度抓取的两个边界分支（**离线**，不联网、不改数据集）。

背景：2026-10-16 供给侧三张图（全球 / Non-OPEC DoC / OPEC 原油产量）由「手工下载
STEO base tables xlsx」换成 **EIA STEO 官方 API**（src/fetch/supply/steo_monthly.py）。
真实 API 目前带预测段（2026-10 起），所以「无预测 → 删除预测段」这条守卫分支在
日常抓取里**永远走不到**，必须造数据单独验，否则哪天 EIA 停发预测就静默出错。

用例：
  case A  造一份「合计行到 2027-12、分国行只到 2026-09」的数据 —— 复刻线上形态，
          断言 forecastStart=2026-10 / forecastIndex=57 / 72 个月。
  case B  造一份「合计行也只到 2026-09（完全没有预测月）」的数据 —— 断言
          forecastStart/forecastIndex 均为 None、月份轴截断到 2026-09（57 月）、
          四条合计与 21 国分项长度同步截断、且末尾月份就是 lastHistorical。

用法：oil-analysis 目录下 `PYTHONPATH=. .venv/bin/python tools/verify_steo_forecast_guard.py`
      （要带 PYTHONPATH=. 才能 import src.*；其它 tools/*.js 走浏览器，无需此步）
"""
import sys

from src.fetch.supply import steo_monthly as sm


def _mk(periods_world, periods_country):
    """造 raw：{seriesId: {period: value}}。合计行给足月份，分国行给历史段。"""
    raw = {}
    all_ids = ([sm.SERIES[k] for k in ("world", "opec", "nonOpec")]
               + [sid for sid, _ in sm.OPEC_MEMBERS]
               + [sid for sid, _ in sm.DOC_MEMBERS] + [sm.DOC_TOTAL])
    for sid in all_ids:
        per = periods_world if sid in (sm.SERIES["world"], sm.SERIES["opec"],
                                       sm.SERIES["nonOpec"], sm.DOC_TOTAL) else periods_country
        # 恒等式要成立：world = opec + nonOpec
        base = {"world": 70.0, "opec": 20.0, "nonOpec": 50.0, sm.DOC_TOTAL: 14.0}.get(sid, 1.0)
        raw[sid] = {p: base for p in per}
    # 让 world = opec + nonOpec 精确成立
    for p in periods_world:
        raw[sm.SERIES["world"]][p] = raw[sm.SERIES["opec"]][p] + raw[sm.SERIES["nonOpec"]][p]
    return raw


FULL = sm._month_range("2022-01", "2027-12")          # 72 月
HIST = sm._month_range("2022-01", "2026-09")          # 57 月


def main():
    fails = []
    orig = sm._fetch_all

    def check(name, periods_world, periods_country, want_len, want_start, want_index):
        sm._fetch_all = lambda: _mk(periods_world, periods_country)
        try:
            d = sm.fetch()
        finally:
            sm._fetch_all = orig
        if not d:
            fails.append(name + "：fetch() 返回 None")
            return
        months = d["months"]
        tag = "%s（%d 月, %s~%s）" % (name, len(months), months[0], months[-1])
        if len(months) != want_len:
            fails.append("%s：月份数应 %d，实际 %d" % (name, want_len, len(months)))
        if d.get("forecastStart") != want_start:
            fails.append("%s：forecastStart 应 %r，实际 %r" % (name, want_start, d.get("forecastStart")))
        if d.get("forecastIndex") != want_index:
            fails.append("%s：forecastIndex 应 %r，实际 %r" % (name, want_index, d.get("forecastIndex")))
        # 所有数组必须与 months 等长
        arrs = [("world", d["world"]["crude"]), ("opec", d["opec"]["crude"]),
                ("nonOpec", d["nonOpec"]["crude"]), ("docTotal", d["docTotal"])]
        arrs += [("opecMembers." + k, v) for k, v in d["opecMembers"].items()]
        arrs += [("docMembers." + k, v) for k, v in d["docMembers"].items()]
        for k, a in arrs:
            if len(a) != len(months):
                fails.append("%s：%s 长度 %d != months %d" % (name, k, len(a), len(months)))
        if months[-1] != (d["lastHistorical"] if want_start is None else months[-1]):
            pass
        print("  %s → forecastStart=%r forecastIndex=%r lastHistorical=%r"
              % (tag, d.get("forecastStart"), d.get("forecastIndex"), d.get("lastHistorical")))
        return d

    print("case A：合计行含预测段（复刻线上形态）")
    a = check("case A", FULL, HIST, 72, "2026-10", 57)
    print("case B：合计行也只到 2026-09（API 完全没给预测）")
    b = check("case B", HIST, HIST, 57, None, None)
    if b:
        if b["months"][-1] != "2026-09":
            fails.append("case B：月份轴末月应 2026-09，实际 " + b["months"][-1])
        if b["world"]["crude"][-1] is None:
            fails.append("case B：截断后世界线末点为空")
        # 分国末点必须仍有值（历史段完整保留）
        for k, v in list(b["opecMembers"].items())[:3]:
            if v[-1] is None:
                fails.append("case B：%s 末点被误截为 None" % k)

    print()
    if fails:
        print("FAIL")
        for f in fails:
            print("  " + f)
        return 1
    print("ALL OK — STEO 月度抓取：有预测（72 月 / 2026-10 起）与无预测（截断 57 月）两分支均自洽")
    return 0


if __name__ == "__main__":
    sys.exit(main())
