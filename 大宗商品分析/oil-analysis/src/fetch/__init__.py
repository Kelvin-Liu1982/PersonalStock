# -*- coding: utf-8 -*-
"""数据抓取层 —— 严格按看板的五个维度组织。

    fetch/prices.py     价格基准（Brent/WTI/汽油价），决定日度日期轴，多维度共用
    fetch/supply/       供给侧：EIA 周报、OPEC 产量与剩余产能、OECD 库存、SPR、钻井数
    fetch/demand/       需求侧：PMI/GDP 先行指标、炼厂开工与加工、中国进口
    fetch/geo/          地缘政治：OVX 恐慌指数、波动率
    fetch/macro/        宏观金融：美元指数、利率、国债收益率
    fetch/shocks/       其他突发：价格跳变与事件检测
"""
