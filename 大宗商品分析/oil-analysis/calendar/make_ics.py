#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成可导入 Google Calendar / iOS 日历的财经发布日程 .ics。

当前覆盖三类发布：

    1. OPEC《月度石油市场报告》(MOMR)  —— 官方年度发布日程，维也纳上午出刊
    2. EIA《每周石油状态报告》(WPSR)    —— 每周三美东 10:30，节假日周顺延
    3. IEA《石油市场报告》(OMR)         —— 官方年度发布日程，巴黎当地 10:00 出刊

用法：
    python make_ics.py                          # 生成 finance_calendar.ics（仅剩余期次）
    python make_ics.py --only opec --from 2026-01-01 --out opec_momr_2026.ics
    python make_ics.py --only eia  --from 2026-01-01 --out eia_weekly_2026.ics
    python make_ics.py --only iea  --from 2026-01-01 --out iea_omr_2026.ics
    python make_ics.py --from 2026-01-01         # 全年（含已过期期次）

明年只需改 RELEASES_* 两张表重跑一次。

────────────────────────────────────────────────────────
时刻口径（关键，改之前先看懂）
────────────────────────────────────────────────────────
OPEC MOMR：维也纳当地时间上午出刊（约 11:00–12:00 CET/CEST）。
    统一取 10:00Z：CET 期 = 维也纳 11:00 = 北京 18:00；
                   CEST 期 = 维也纳 12:00 = 北京 18:00。
    ⇒ 北京时间全年恒定 18:00。

EIA WPSR：官方标准发布时间 **美东时间周三 10:30**（wpsrsummary.pdf /
    overview.pdf / 表 1-14 的 CSV·XLS）；其余 PDF/HTML 延至美东 13:00 后。
    换算北京时间（UTC+8）：
        美国夏令时 EDT(UTC-4)  → 14:30Z → 北京 **22:30**
        美国冬令时 EST(UTC-5)  → 15:30Z → 北京 **23:30**
    2026 年美国夏令时区间：3/8 – 11/1。
    节假日周顺延到周四（且改为美东 12:00，见 EIA_HOLIDAY_SHIFT_2026）：
        10/15 12:00 ET → 16:00Z → 北京 10/16 00:00
        11/12 12:00 ET → 17:00Z → 北京 11/13 01:00
IEA OMR：官方 NB 明示「released at 10H00 Paris local time」，即**巴黎当地时间 10:00**
    全年恒定（不是美东那种会切夏令时的口径）。换算北京时间：
        巴黎冬令 CET(UTC+1)  → 09:00Z → 北京 17:00（1/2/3 月、11/12 月）
        巴黎夏令 CEST(UTC+2) → 08:00Z → 北京 16:00（4 月至 10 月中）
    夏令时区间由 zoneinfo(Europe/Paris) 自动判定；2026 年为 3/29 – 10/25。
    来源：OMR 2026-01-21 号（data/raw/iea_omr/-21JAN2026_OilMarketReport.pdf）第 2 页
    “Publishing Schedule – 2026”。

所有时刻都写成 **UTC 绝对值**（DTSTART 以 Z 结尾，不用 TZID/VTIMEZONE），
换设备、换时区都不会错位；美东/巴黎夏令时由 zoneinfo 自动判定。
"""
import argparse
import datetime
import os
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
PARIS = ZoneInfo("Europe/Paris")
UTC = datetime.timezone.utc
UID_DOMAIN = "oil-analysis.local"

CAL_NAME = "财经发布日历（OPEC 月报 + EIA 周报 + IEA 月报）"

# ── 1. OPEC MOMR 2026 官方发布日程（MOMR Dec 2025 末页 publishing schedule） ──
RELEASES_MOMR_2026 = [
    ("2026-01-14", "1月号"), ("2026-02-11", "2月号"), ("2026-03-11", "3月号"),
    ("2026-04-13", "4月号"), ("2026-05-13", "5月号"), ("2026-06-11", "6月号"),
    ("2026-07-13", "7月号"), ("2026-08-12", "8月号"), ("2026-09-10", "9月号"),
    ("2026-10-13", "10月号"), ("2026-11-11", "11月号"), ("2026-12-14", "12月号"),
]
MOMR_URL = "https://www.opec.org/monthly-oil-market-report.html"

# ── 2. EIA WPSR 2026 ──
# 规则：每周三 10:30 ET；下面字典里的周三被顺延（键=原定周三，值=(顺延日, 美东时刻, 原因)）
EIA_HOLIDAY_SHIFT_2026 = {
    "2026-10-14": ("2026-10-15", "12:00", "哥伦布日（10/12 周一）顺延至周四 12:00 ET"),
    "2026-11-11": ("2026-11-12", "12:00", "退伍军人日（11/11 周三）顺延至周四 12:00 ET"),
}
EIA_WEEKLY_START = "2026-01-07"   # 2026 年第一个周三
EIA_WEEKLY_END = "2026-12-31"
EIA_URL = "https://www.eia.gov/petroleum/supply/weekly/"

# ── 3. IEA OMR 2026 官方发布日程 ──
# 源：OMR 2026-01-21 号（data/raw/iea_omr/-21JAN2026_OilMarketReport.pdf）第 2 页
#     “Publishing Schedule – 2026”，各期均于巴黎当地时间 10H00 发布。
# 值：(日期, 期次标签, PDF 脚注编号 or "")
RELEASES_OMR_2026 = [
    ("2026-01-21", "1月号", ""), ("2026-02-12", "2月号", ""),
    ("2026-03-12", "3月号", ""), ("2026-04-14", "4月号", "(1)"),
    ("2026-05-13", "5月号", ""), ("2026-06-17", "6月号", "(2)"),
    ("2026-07-10", "7月号", ""), ("2026-08-12", "8月号", "(3)"),
    ("2026-09-11", "9月号", ""), ("2026-10-14", "10月号", ""),
    ("2026-11-13", "11月号", ""), ("2026-12-11", "12月号", ""),
]
# 官方脚注（PDF 第 2 页原文）
OMR_FOOTNOTES = {
    "(1)": "供需预测将自本期起延长至 2027 年（后由 5 月号改到 6 月号首次给出 2027 线）",
    "(2)": "本期数据照常，正文为精简版",
    "(3)": "本期附带发布《2026 年度统计增补》(Annual Statistical Supplement 2026 Edition)",
}
OMR_URL = "https://www.iea.org/reports/oil-market-report"


def esc(text):
    """iCalendar TEXT 转义：反斜杠、分号、逗号、换行。"""
    return (text.replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\n", "\\n"))


def fold(line):
    """RFC 5545 折行：单行不超过 75 字节，续行以单个空格开头；按字符累加，
    避免把 UTF-8 多字节字符截断。"""
    out, cur, cur_bytes = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if cur_bytes + n > 74:
            out.append(cur)
            cur, cur_bytes = " ", 1
        cur += ch
        cur_bytes += n
    out.append(cur)
    return "\r\n".join(out)


def et_to_utc(date_str, hm):
    """把美东墙上时间转 UTC。夏令时由 America/New_York 自动判定。"""
    h, m = (int(x) for x in hm.split(":"))
    y, mo, d = (int(x) for x in date_str.split("-"))
    local = datetime.datetime(y, mo, d, h, m, tzinfo=NY)
    return local.astimezone(UTC)


def paris_to_utc(date_str, hm="10:00"):
    """把巴黎当地时间转 UTC。夏令时由 Europe/Paris 自动判定
    （2026 年 CEST 区间 3/29 – 10/25）。IEA OMR 官方口径即为巴黎当地 10H00。"""
    h, m = (int(x) for x in hm.split(":"))
    y, mo, d = (int(x) for x in date_str.split("-"))
    local = datetime.datetime(y, mo, d, h, m, tzinfo=PARIS)
    return local.astimezone(UTC)


def beijing_str(dt_utc):
    """UTC -> 北京时间（UTC+8）的可读串，带『次日』标记避免跨零点看错。"""
    bj = dt_utc + datetime.timedelta(hours=8)
    flag = "次日 " if bj.date() != dt_utc.date() else ""
    return "{}{:02d}:{:02d}".format(flag, bj.hour, bj.minute)


def vevent(uid, dtstart, dtend, summary, desc, url, alarms):
    lines = [
        "BEGIN:VEVENT",
        "UID:" + uid,
        "DTSTAMP:20261006T000000Z",
        "DTSTART:" + dtstart.strftime("%Y%m%dT%H%M%SZ"),
        "DTEND:" + dtend.strftime("%Y%m%dT%H%M%SZ"),
        "SUMMARY:" + esc(summary),
        "DESCRIPTION:" + esc(desc),
        "URL:" + url,
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
    ]
    for trigger, note in alarms:
        lines += ["BEGIN:VALARM", "TRIGGER:" + trigger, "ACTION:DISPLAY",
                  "DESCRIPTION:" + esc(note), "END:VALARM"]
    lines.append("END:VEVENT")
    return "\r\n".join(fold(x) for x in lines)


def opec_events(from_date):
    out = []
    for date_str, label in RELEASES_MOMR_2026:
        if date_str < from_date:
            continue
        y, m, d = (int(x) for x in date_str.split("-"))
        start = datetime.datetime(y, m, d, 10, 0, tzinfo=UTC)
        end = start + datetime.timedelta(hours=1)
        desc = ("OPEC《月度石油市场报告》(MOMR) {} 发布日。维也纳时间上午出刊"
                "（约 11:00–12:00 CET/CEST），对应北京时间 18:00。"
                "来源：MOMR Dec 2025 公布的 2026 年发布日程。 {}".format(label, MOMR_URL))
        out.append((start, vevent(
            "momr-{}@{}".format(date_str, UID_DOMAIN), start, end,
            "【OPEC 月报】MOMR {} 发布（北京时间 18:00）".format(label),
            desc, MOMR_URL,
            [("-P1D", "明日 OPEC 月报发布"), ("-PT60M", "1 小时后 OPEC 月报发布")])))
    return out


def eia_events(from_date):
    out = []
    y, m, d = (int(x) for x in EIA_WEEKLY_START.split("-"))
    cur = datetime.date(y, m, d)
    end = datetime.date(*(int(x) for x in EIA_WEEKLY_END.split("-")))
    while cur <= end:
        iso = cur.isoformat()
        date_str, hm, note = iso, "10:30", ""
        if iso in EIA_HOLIDAY_SHIFT_2026:
            date_str, hm, note = EIA_HOLIDAY_SHIFT_2026[iso]
        if date_str >= from_date:
            start = et_to_utc(date_str, hm)
            bj = beijing_str(start)
            desc = ("EIA《每周石油状态报告》(WPSR) 发布。摘要与表 1-14（CSV/XLS）"
                    "于美东 {} 上线，其余 PDF/HTML 于美东 13:00 后上线。"
                    "对应北京时间 {}。看板供给侧周度数据（库存/产量/开工率）来自此报告。"
                    " {}".format(hm, bj, note or "常规发布", ))
            desc += " 来源：" + EIA_URL
            out.append((start, vevent(
                "wpsr-{}@{}".format(date_str, UID_DOMAIN), start,
                start + datetime.timedelta(minutes=30),
                "【EIA 周报】WPSR 发布（北京时间 {}）".format(bj),
                desc, EIA_URL,
                [("-PT60M", "1 小时后 EIA 周报发布"), ("-PT15M", "15 分钟后 EIA 周报发布")])))
        cur += datetime.timedelta(days=7)
    return out


def iea_events(from_date):
    out = []
    for date_str, label, fn in RELEASES_OMR_2026:
        if date_str < from_date:
            continue
        start = paris_to_utc(date_str)          # 巴黎当地 10H00 → UTC
        end = start + datetime.timedelta(hours=1)
        bj = beijing_str(start)
        fnote = OMR_FOOTNOTES.get(fn, "")
        if fnote:
            fnote = "（官方脚注 " + fn + "：" + fnote + "）"
        desc = ("IEA《石油市场报告》(OMR) {} 发布日。官方 NB 明示本报告于各发布日"
                "**巴黎当地时间 10:00** 上线，对应北京时间 {}。"
                "看板【未来展望·IEA 全球石油需求增速预测（逐月 OMR 修正）】"
                "即逐期取用。来源：OMR 2026-01-21 号第 2 页 Publishing Schedule – 2026。"
                " {}{}".format(label, bj, fnote, OMR_URL))
        out.append((start, vevent(
            "omr-{}@{}".format(date_str, UID_DOMAIN), start, end,
            "【IEA 月报】OMR {} 发布（巴黎 10:00 / 北京时间 {}）".format(label, bj),
            desc, OMR_URL,
            [("-P1D", "明日 IEA 月报发布"), ("-PT60M", "1 小时后 IEA 月报发布")])))
    return out


def build(from_date, only):
    evs = []
    if only in ("all", "opec"):
        evs += opec_events(from_date)
    if only in ("all", "eia"):
        evs += eia_events(from_date)
    if only in ("all", "iea"):
        evs += iea_events(from_date)
    # 按 DTSTART 升序输出（ICS 本身与顺序无关，但便于人工 diff / 阅读）
    evs.sort(key=lambda pair: pair[0])
    head = ["BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//oil-analysis//finance release calendar//CN",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
            "X-WR-CALNAME:" + CAL_NAME, "X-WR-TIMEZONE:Asia/Shanghai"]
    return "\r\n".join(["\r\n".join(fold(x) for x in head)]
                       + [v for _, v in evs] + ["END:VCALENDAR"]) + "\r\n"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(here, "finance_calendar.ics"))
    ap.add_argument("--from", dest="from_date", default="2026-10-06",
                    help="只导出该日期及之后的期次（默认=今天起，避免历史事件撞上 "
                         "iOS 日历同步窗口）。要全年就给 2026-01-01")
    ap.add_argument("--only", choices=["all", "opec", "eia", "iea"], default="all")
    args = ap.parse_args()

    ics = build(args.from_date, args.only)
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        fh.write(ics)
    n = ics.count("BEGIN:VEVENT")
    print("written {} events -> {} ({} bytes)".format(n, args.out, len(ics.encode("utf-8"))))


if __name__ == "__main__":
    main()
