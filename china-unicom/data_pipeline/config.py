# -*- coding: utf-8 -*-
"""配置：代码、路径、年份范围、输出目录。

中国联通（中国联合网络通信(香港)股份有限公司，股票代码 00762.HK）数据本地化管道。
A 股 600050.SH 与 H 股 00762.HK 为同一合并主体，A 股宽表提供 2020-2025 全历史营收，
H 股 F10 提供最新的 H 股口径利润表/资产负债表（本公司权益持有者应占盈利）。
"""
import os

# ---- 标的 ----
H_SHARE_CODE = "00762"          # 港交所代码（无后缀）
H_SHARE_SECID = "116.00762"     # Eastmoney secid：116=港股
A_SHARE_CODE = "600050"         # 上交所代码（同一合并主体，A 股口径）
A_SHARE_SECID = "1.600050"

COMPANY_NAME = "中国联通"
COMPANY_FULL = "中国联合网络通信(香港)股份有限公司"

# ---- 年份范围（看板口径：2020-2025 全年；2026 为计划/中报值单列）----
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
CURRENCY = "人民币亿元（每股指标单位为元/股，比率见列名）"

# ---- 输出目录：china-unicom/（数据管道在其子目录 data_pipeline/ 下）----
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.abspath(os.path.join(HERE, ".."))          # -> china-unicom/
CACHE_DIR = os.path.join(HERE, "cache")                       # 原始抓取 JSON 缓存

# ---- Eastmoney 接口 ----
EMAPI_BASE = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
QUOTE_BASE = "https://push2.eastmoney.com/api/qt/stock/get"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      "Referer": "https://emweb.securities.eastmoney.com/"}

# H 股 F10 三大表（长表：每行一个科目 ITEM_NAME + AMOUNT）
RPT_HK_INCOME = "RPT_HKF10_FN_INCOME"
RPT_HK_BALANCE = "RPT_HKF10_FN_BALANCE"
# A 股宽表（每行一个报告期，列即指标）
RPT_A_INCOME = "RPT_DMSK_FN_INCOME"
RPT_A_CASHFLOW = "RPT_DMSK_FN_CASHFLOW"

# 报告期类型编码：001=年报(全年)，002=中报(H1)，003=一季/三季，004=前三季
DATE_TYPE_ANNUAL = "001"
