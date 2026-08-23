# -*- coding: utf-8 -*-
"""数据来源登记表（可追溯性核心）。

每一个持久化字段都应能映射到下面某一来源。运行 run.py 时会在 XLSX 的
"数据来源与口径说明"sheet 与 DATA_SOURCES.md 中引用本登记表。
"""
SOURCES = {
    "EM_HK_F10_INCOME": {
        "name": "东方财富 Eastmoney · 港股 F10 利润表",
        "endpoint": "datacenter.eastmoney.com · reportName=RPT_HKF10_FN_INCOME · SECURITY_CODE=00762",
        "scope": "00762.HK 最新年度/季度利润表（长表，科目级），币种人民币。",
        "authority": "权威第三方聚合（源自港交所披露易 HKEXnews 公告）",
        "used_for": "营业收入、本公司权益持有者应占盈利、每股基本盈利、毛利、折旧与摊销（最新年度）",
    },
    "EM_HK_F10_BALANCE": {
        "name": "东方财富 Eastmoney · 港股 F10 资产负债表",
        "endpoint": "datacenter.eastmoney.com · reportName=RPT_HKF10_FN_BALANCE · SECURITY_CODE=00762",
        "scope": "00762.HK 最新年度资产负债表（科目级），币种人民币。",
        "authority": "权威第三方聚合（源自港交所披露易 HKEXnews 公告）",
        "used_for": "总资产、总负债、股东权益、应收账款（最新年度）",
    },
    "EM_A_F10_INCOME": {
        "name": "东方财富 Eastmoney · A股 F10 利润表（宽表）",
        "endpoint": "datacenter.eastmoney.com · reportName=RPT_DMSK_FN_INCOME · SECURITY_CODE=600050",
        "scope": "600050.SH 2020-2025 全历史年度/季度利润表（宽表，期间级）。",
        "authority": "权威第三方聚合（源自上交所 SSE 年报/季报）",
        "used_for": "营业收入 2020-2025 全序列（与 H 股合并营收一致）",
        "note": "600050 与 00762 为同一合并主体，营收金额一致；净利润口径不同（见字段说明）。",
    },
    "EM_QUOTE": {
        "name": "东方财富 Eastmoney · 实时行情",
        "endpoint": "push2.eastmoney.com · api/qt/stock/get · secid=116.00762",
        "scope": "00762.HK 实时/收盘行情。",
        "authority": "交易所行情快照",
        "used_for": "行情快照条（股价、涨跌、股息率 TTM 等基线值）",
    },
    "HKEX_AR_2025": {
        "name": "港交所披露易 HKEXnews · 中国联通 2025 年度报告",
        "url": "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0428/2026042801720_c.pdf",
        "scope": "2025 全年经审计合并业绩、营运数据、资本开支、股东回报。",
        "authority": "官方一手披露（公司备案）",
        "used_for": "服务收入、净利润、EPS、每股股息、自由现金流、资本开支、ROE、智算规模、"
                    "5G专网/IDC/国际业务收入、用户规模、融合渗透率、派息率（2025）",
    },
    "HKEX_AR_2024": {
        "name": "港交所披露易 HKEXnews · 中国联通 2024 年度报告",
        "url": "https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0429/2025042902073_c.pdf",
        "scope": "2024 全年经审计合并业绩与财务摘要（含 2023 同比）。",
        "authority": "官方一手披露",
        "used_for": "服务收入/联通云/IDC/算网数智/资本开支/派息率 2024 及同比（2023）",
    },
    "HKEX_RESULTS_2025": {
        "name": "港交所披露易 HKEXnews · 2025 年度业绩公告",
        "url": "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0319/2026031900255.pdf",
        "scope": "2025 年度业绩摘要（Highlights）。",
        "authority": "官方一手披露",
        "used_for": "净利润、自由现金流、资本开支、股息率/每股股息/派息率（2025）交叉核验",
    },
    "AR_COMPILED_2020_2025": {
        "name": "2020-2025 核心财务与分红六年汇总表（工信智媒体，源自历年年报）",
        "url": "https://new.qq.com/rain/a/20260319A07WAM00",
        "scope": "2020-2025 营业收入、净利润、现金分红总额的六年序列。",
        "authority": "媒体汇编（原始数据来自公司历年年报，可回溯）",
        "used_for": "营业收入、净利润（H 股口径）、现金分红总额 2020-2025 全序列",
    },
    "BROKER_CAPEX": {
        "name": "券商研究（光大证券）引用的公司资本开支序列",
        "url": "https://ima.qq.com/wiki/?shareId=07fd6fd8883f0d5c1248e9ab49e060f97522355b520b9312a2144ac625488b01",
        "scope": "2020-2024 资本开支（亿元）。",
        "authority": "券商研报引用公司披露",
        "used_for": "资本开支 2020-2024（2025 来自 HKEX 年报）",
    },
}
