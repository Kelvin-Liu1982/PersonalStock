# -*- coding: utf-8 -*-
"""月份名 / 月份键公共层。

四个离线解析脚本都要做同一件事：从文件名或 PDF 表头文本里认出月份，
再拼出 ``YYYY-MM`` 键。此前 opec_momr / oecd_stocks / rig_count
各写一份 MONTHS / ABBR 映射与 pub_month()，四处重复且大小写口径不一致
（opec_momr / oecd_stocks 按文件名期号匹配），改一个词要改三个文件。
（opec_momr 已于 2026-10-23 移出仓库，现只剩 oecd_stocks / rig_count /
eia_steo_price / iea_oil / eia_aeo 等脚本在用本模块。）

集中到这里后：新增月份写法或修正期号正则只改一处。
"""
import os
import re

# 全名 -> 月份序号（键为 Title Case）
FULL = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11,
    "December": 12,
}

# 三字母缩写 -> 月份序号
ABBR = {k[:3]: v for k, v in FULL.items()}

# 供正则复用：Jan|Feb|...|Dec
ABBR_PATTERN = "|".join(ABBR)

# MOMR 文件名期号：OPEC_MOMR_July_2026.pdf / momr-january-2026.pdf
_PUB_RE = re.compile(
    r"(?:OPEC_MOMR_|momr[-_])?([A-Za-z]+)[-_](\d{4})\.pdf", re.IGNORECASE)


def from_name(name):
    """月份名 -> 序号（1–12）。识别全名与三字母缩写，大小写不敏感；无法识别返回 None。"""
    if not name:
        return None
    key = str(name).strip().title()
    return FULL.get(key) or ABBR.get(key[:3])


def pub_month(fname):
    """从 MOMR 文件名解析发布期号 -> ``(年, 月)``；无法识别返回 None。"""
    m = _PUB_RE.search(os.path.basename(fname))
    if not m:
        return None
    mm = from_name(m.group(1))
    return (int(m.group(2)), mm) if mm else None


def key(year, month):
    """拼 ``YYYY-MM`` 月份键。"""
    return f"{int(year):04d}-{int(month):02d}"


def shift(year, month, back=1):
    """往前推 ``back`` 个月，返回 ``(年, 月)``；跨年自动回退。"""
    total = int(year) * 12 + (int(month) - 1) - int(back)
    return total // 12, total % 12 + 1
