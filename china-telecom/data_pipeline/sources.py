# -*- coding: utf-8 -*-
"""数据来源登记表（可追溯性核心）。

每一个持久化字段都应能映射到下面某一来源。运行 run.py 时会在 XLSX 的
"数据来源与口径说明" sheet 与 DATA_SOURCES.md 中引用本登记表。

标的：中国电信股份有限公司（00728.HK / 601728.SH，同一合并主体，A/H 双上市）。
口径：统一采用 H 股（00728.HK）合并口径（与中国移动、中国联通看板一致）。
"""
SOURCES = {
    "EM_HK_F10_INCOME": {
        "name": "东方财富 Eastmoney · 港股 F10 利润表",
        "endpoint": "datacenter.eastmoney.com · reportName=RPT_HKF10_FN_INCOME · SECURITY_CODE=00728",
        "scope": "00728.HK 最新年度/季度利润表（长表，科目级：ITEM_NAME + AMOUNT），币种人民币。",
        "authority": "权威第三方聚合（原始数据源自港交所披露易 HKEXnews 公告）",
        "used_for": "营业额(营业收入)、股东应占溢利(净利)、每股基本盈利、毛利、折旧与摊销、经营溢利（最新年度 2025 实时抓取）",
    },
    "EM_HK_F10_BALANCE": {
        "name": "东方财富 Eastmoney · 港股 F10 资产负债表",
        "endpoint": "datacenter.eastmoney.com · reportName=RPT_HKF10_FN_BALANCE · SECURITY_CODE=00728",
        "scope": "00728.HK 最新年度/季度资产负债表（科目级），币种人民币。",
        "authority": "权威第三方聚合（原始数据源自港交所披露易 HKEXnews 公告）",
        "used_for": "总资产、总负债、股东权益、应收账款（最新年度 2025 实时抓取）",
    },
    "EM_A_F10_INCOME": {
        "name": "东方财富 Eastmoney · A 股 F10 利润表（宽表）",
        "endpoint": "datacenter.eastmoney.com · reportName=RPT_DMSK_FN_INCOME · SECURITY_CODE=601728",
        "scope": "601728.SH 2020-2025 全历史年度/季度利润表（宽表，期间级：每行一个报告期）。",
        "authority": "权威第三方聚合（原始数据源自上交所 SSE 年报/季报）",
        "used_for": "营业收入 2020-2025 全序列交叉核验（A 股宽表 TOTAL_OPERATE_INCOME 与 H 股合并营收同源可比，金额约低 57 亿，为列报口径差异）",
        "note": "601728 与 00728 为同一合并主体；A 股宽表提供全历史营收与负债率，H 股 F10 提供最新年度利润表/资产负债表及每股指标。",
    },
    "EM_QUOTE": {
        "name": "东方财富 Eastmoney · 实时行情",
        "endpoint": "push2.eastmoney.com · api/qt/stock/get · secid=116.00728",
        "scope": "00728.HK 实时/收盘行情（f43 最新价、f57 代码、f58 名称等）。",
        "authority": "交易所行情快照",
        "used_for": "行情快照条基线；H 股股息率(TTM)=每股股息/股价、股息利差=股息率-10Y 国债收益率（随行情每日变动，预留字段待回填）",
    },
    "HKEX_AR_2020_2025": {
        "name": "港交所披露易 HKEXnews · 中国电信 2020–2025 年度报告与年度业绩公告",
        "url": "https://www1.hkexnews.hk/search/titlesearch.xhtml?stockId=728",
        "scope": "2020-2025 全年经审计合并业绩、营运数据、资本开支、股东回报、业务结构。",
        "authority": "官方一手披露（公司备案，最高权威）",
        "used_for": "服务收入、产业数字化收入、天翼云收入、IDC 收入、智能(AI)收入、安全收入、智算规模、"
                    "5G 基站、移动/宽带用户、移动/宽带 ARPU、5G 套餐用户、国际业务收入、"
                    "资本开支、EPS、每股股息、派息率、现金分红总额、ROE、净利率、自由现金流、"
                    "资产负债率（2020-2025 全序列主来源）",
    },
    "HKEX_RESULTS_2025": {
        "name": "港交所披露易 HKEXnews · 中国电信 2025 年度业绩公告（Highlights）",
        "url": "https://www1.hkexnews.hk/search/titlesearch.xhtml?stockId=728",
        "scope": "2025 年度业绩摘要（经营收入、股东应占溢利、每股股息、派息率、资本开支等）。",
        "authority": "官方一手披露",
        "used_for": "2025 经营收入≈5296 亿、净利≈332 亿、天翼云 1207 亿、派息率 75%、全年股息 0.2720 元 等交叉核验",
    },
    "BROKER_RESEARCH": {
        "name": "券商研究/媒体汇编（引用公司披露的产业数字化、天翼云、IDC 等序列）",
        "url": "https://www1.hkexnews.hk/search/titlesearch.xhtml?stockId=728",
        "scope": "2020-2025 产业数字化、天翼云、IDC 收入序列（公司披露，券商/媒体二次汇编）。",
        "authority": "媒体/券商汇编（原始数据来自公司历年年报，可回溯 HKEXnews）",
        "used_for": "产业数字化收入、天翼云收入、IDC 收入 的逐年序列补充（年报口径一致）",
    },
}
