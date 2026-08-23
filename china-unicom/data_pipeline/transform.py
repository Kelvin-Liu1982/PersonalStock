# -*- coding: utf-8 -*-
"""转换层：把已核验指标(METRICS) 与 实时抓取快照(fetcher) 组装为 5 个 XLSX 文件所需的表结构。

存储规范（与中国移动一致）：
  每个 .xlsx 含三张 sheet：年报数据 / 季报数据 / 数据来源与口径说明。
  "年报数据"：指标为行、年份(2020-2025)为列（metrics-as-rows 布局），最后一列"备注"。
单位写进指标名后缀（如"营业收入(亿元)"），比率标"%"，规模标单位。
无法核验的年份值为 None（写入 XLSX 显示为"—"）。
"""
import config as C
import sources as S
import annual_report_data as A
import fetcher as F


# 合并数据集（METRICS + 实时抓取覆盖）由 build_dataset 写入，_row 从此读取
DV = None


def _row(key, unit_suffix=True):
    m = A.METRICS[key]
    label = m["label"] + (("(%s)" % m["unit"]) if unit_suffix and m["unit"] not in ("%",) else ("(%s)" % m["unit"] if unit_suffix else ""))
    vals = list(DV[key]) if DV is not None else [m["vals"].get(y) for y in C.YEARS]
    note = m.get("note", "")
    if m.get("source"):
        note = (note + " ｜源:" + m["source"]) if note else ("源:" + m["source"])
    return (label, vals, note)


def reconcile_with_fetch(dataset_vals):
    """用实时抓取的 H 股最新年度值覆盖 2025 单元格（实时抓取优先）。"""
    try:
        snap = F.build_fetched_snapshot()
    except Exception as e:  # 网络失败则保留已核验值
        print("[reconcile] 实时抓取失败，沿用已核验值：", e)
        return dataset_vals
    y = 2025
    inc = snap.get("income_yi", {})
    bal = snap.get("balance_yi", {})
    opt = inc.get("opt", {}).get(y)
    da = inc.get("da", {}).get(y)
    ta = bal.get("total_assets", {}).get(y)
    tl = bal.get("total_liab", {}).get(y)
    overrides = {
        "revenue": inc.get("rev", {}).get(y),
        "net_profit": inc.get("np", {}).get(y),
        "eps": inc.get("eps", {}).get(y),
        "ebitda": round(opt + da, 2) if isinstance(opt, (int, float)) and isinstance(da, (int, float)) else None,
        "ar": bal.get("ar", {}).get(y),
        "debt_ratio": round(tl / ta * 100, 2) if isinstance(ta, (int, float)) and isinstance(tl, (int, float)) and ta else None,
    }
    for k, v in overrides.items():
        if v is not None and k in dataset_vals:
            dataset_vals[k][C.YEARS.index(y)] = v
            print("[reconcile] 2025 %s 已用实时抓取覆盖 = %s" % (k, v))
    return dataset_vals


def _quarterly_rows():
    """从 H 股 F10 累计利润表推导单季 营业收入/净利（真实）。"""
    try:
        inc = F.fetch_hk_income()
    except Exception as e:
        print("[quarterly] 抓取失败：", e)
        return [], []
    def series(item):
        # 不限制报告期类型：取所有报告期（累计）的金额
        return {r.get("REPORT_DATE"): r.get("AMOUNT")
                for r in inc if r.get("ITEM_NAME") == item and r.get("REPORT_DATE")}
    rev = series("营业额")
    npf = series("股东应占溢利")
    # 取 2025 各期（累计）与 2026Q1
    periods = [
        ("2025-03-31 00:00:00", "2025Q1"),
        ("2025-06-30 00:00:00", "2025H1"),
        ("2025-09-30 00:00:00", "2025Q3"),
        ("2025-12-31 00:00:00", "2025全年"),
        ("2026-03-31 00:00:00", "2026Q1"),
    ]
    cum_rev = [(lab, rev.get(p)) for p, lab in periods]
    cum_np = [(lab, npf.get(p)) for p, lab in periods]
    def single(cum):
        out = []
        prev = 0
        for lab, v in cum:
            if v is None:
                out.append((lab, None, None))
            else:
                base = prev if v >= prev else 0  # 跨入新财年时累计归零（如 2026Q1）
                sv = (v - base) / 1e8
                out.append((lab, round(sv, 2), None))
                prev = v
        return out
    qr = single(cum_rev)
    qn = single(cum_np)
    # 组装行：每行一个指标，列=5 个期间
    labels = [p[1] for p in periods]
    rev_row = ("营业收入(单季,亿元)", [r[1] for r in qr], "由累计利润表推导单季；Q1=一季报，H1=上半年")
    np_row = ("本公司权益持有者应占盈利(单季,亿元)", [r[1] for r in qn], "由累计利润表推导单季")
    q_headers = ["指标"] + labels + ["备注"]
    q_rows = [rev_row, np_row]
    return q_headers, q_rows


def build_dataset():
    # 先把 METRICS 抽成 {key: [2020..2025 值]}
    dv = {k: [A.METRICS[k]["vals"].get(y) for y in C.YEARS] for k in A.METRICS}
    dv = reconcile_with_fetch(dv)
    global DV
    DV = dv  # 供 _row 读取合并后（含实时抓取）的值

    # 派生：资本开支占服务收入比（%）
    cap = dv["capex"]
    srev = dv["service_revenue"]
    cap_ratio = []
    for i, y in enumerate(C.YEARS):
        c, s = cap[i], srev[i]
        cap_ratio.append(round(c / s * 100, 1) if (c and s) else None)
    # 把派生项挂回 dv（仅用于文件3）
    dv["capex_ratio"] = cap_ratio

    q_headers, q_rows = _quarterly_rows()

    files = []

    # ---- 文件1：财务健康与盈利质量 ----
    f1_rows = [
        _row("revenue"), _row("net_profit"), _row("ebitda"), _row("roe"),
        _row("net_margin"), _row("debt_ratio"), _row("fcf"), _row("ar"),
    ]
    files.append({
        "file_name": "中国联通_财务健康与盈利质量.xlsx",
        "title": "中国联通 · 财务健康与盈利质量（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f1_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：东方财富 Eastmoney 港股 F10 利润表/资产负债表（00762.HK，源自港交所披露易）、A 股 F10 利润表（600050.SH，2020-2025 全历史营收）、港交所 2024/2025 年报、2020-2025 六年汇总（工信智媒体）。",
            "· 单位：人民币亿元；比率%；应收账款/资产来自最新年度资产负债表（H 股 F10，币种人民币）。",
            "· 净利润采用 H 股合并口径『本公司权益持有者应占盈利』（2025=208.16 亿），与 A 股归母净利润（约 90 亿）口径不同，源于红筹结构。",
            "· EBITDA(2025)=经营溢利+折旧与摊销（来自实时抓取的利润表），为近似口径；历史年度待补利润表科目。",
            "· 2025 年营收/净利/EPS/应收账款/资产负债率由数据管道实时抓取自 Eastmoney 并覆盖已核验值。",
            "· 无法核验的年份显示为'—'，待补公司历年年报。",
        ],
    })

    # ---- 文件2：核心业务运营与结构转型 ----
    f2_rows = [
        _row("service_revenue"), _row("cdsa_revenue"), _row("ai_scale"),
        _row("unicom_cloud"), _row("idc_revenue"), _row("g5_base_stations"),
        _row("mobile_arpu"), _row("intl_revenue"),
    ]
    files.append({
        "file_name": "中国联通_核心业务运营与结构转型.xlsx",
        "title": "中国联通 · 核心业务运营与结构转型（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f2_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：港交所 2024/2025 年报（服务收入、算网数智、联通云、IDC、智算规模、5G 基站、国际业务）、业绩公告。",
            "· 单位：收入亿元；智算 EFLOPS；基站万站；ARPU 元/户/月。",
            "· 中国联通两大主业：联网通信（移动/宽带/物联网/车联网/专线）与算网数智（联通云/IDC/数据/智能/安全）。2024 起收入分析将网间结算归入联网通信，历史同口径列示。",
            "· 智算规模：2024=17 → 2025=45 EFLOPS（三年快速扩张）；5G 基站（含 4G）2024>450 万、2025>470 万。",
            "· 移动 ARPU、5G 套餐用户绝对数年报未单列精确值，显示为'—'待补。",
        ],
    })

    # ---- 文件3：资本开支与基础设施 ----
    f3_rows = [
        _row("capex"),
        ("资本开支占服务收入比(%)", cap_ratio, "=资本开支/服务收入；2024≈17.7%、2025≈15.6%（年报披露2025≈16%）"),
        _row("ai_scale"),
        _row("g5_base_stations"),
    ]
    files.append({
        "file_name": "中国联通_资本开支与基础设施.xlsx",
        "title": "中国联通 · 资本开支与基础设施（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f3_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：资本开支 2020-2024 源自券商研报引用之公司披露，2025=542 亿来自港交所 2025 年报；智算规模/5G 基站来自年报。",
            "· 单位：资本开支亿元；智算 EFLOPS；基站万站。",
            "· 资本开支连续下降（739→614→542），占服务收入比降至 16%；2026 预计约 500 亿、算力投资占比>35%（超 175 亿）。",
            "· 智算规模 2024=17 → 2025=45 EFLOPS；5G 基站（含 4G）2025>470 万。",
        ],
    })

    # ---- 文件4：客户生态与政企业务 ----
    f4_rows = [
        _row("mobile_users"), _row("broadband_users"), _row("iot_connections"),
        _row("fusion_penetration"), _row("g5_package_users"), _row("g5_private_net"),
        _row("unicom_cloud"), _row("intl_revenue"),
    ]
    files.append({
        "file_name": "中国联通_客户生态与政企业务.xlsx",
        "title": "中国联通 · 客户生态与政企业务（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f4_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：港交所 2024/2025 年报、业绩公告（用户规模、物联网、融合渗透率、5G 专网、联通云、国际业务）。",
            "· 单位：用户亿户；连接数亿个；渗透率%；收入亿元。",
            "· 用户总量（移动+宽带+固话+物联网+专线）2025 突破 12 亿（+1.1 亿）；移动和宽带用户净增超 2000 万。",
            "· 5G 套餐用户、移动 ARPU 年报未单列精确值（仅披露渗透率/ARPU 区间），显示为'—'待补。",
        ],
    })

    # ---- 文件5：宏观政策与股东回报 ----
    vat_row = ("服务增值税(%)", [None, None, None, None, None, 9],
               "事件驱动：基础电信服务增值税由 6% 调整为 9%（2025 起执行），对收入/利润/现金流短期有负面影响，利润最显著")
    dy_row = ("H股股息率(TTM,%)", [None, None, None, None, None, None],
              "=每股股息/股价，随行情每日变动；需刷新行情快照后填入（见 quote-refresh 机制）")
    ds_row = ("股息利差=股息率-10Y国债(%)", [None, None, None, None, None, None],
              "=H股股息率 - 10年期国债收益率；需行情快照与国债收益率后填入")
    f5_rows = [
        _row("eps"), _row("dps"), _row("payout_ratio"), _row("dividend_total"),
        dy_row, ds_row, vat_row,
    ]
    files.append({
        "file_name": "中国联通_宏观政策与股东回报.xlsx",
        "title": "中国联通 · 宏观政策与股东回报（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f5_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：港交所 2024/2025 年报与业绩公告（EPS、每股股息、派息率、现金分红总额）、2020-2025 六年汇总。",
            "· 单位：EPS/每股股息 元；派息率/股息率 %；分红总额亿元。",
            "· 派息率：2024=60%、2025=61.3%（年报披露）；2020-2023=现金分红总额/净利 估算。",
            "· 每股股息(全年)=中期+末期；2025=0.4170 元（+3.1%）。",
            "· 服务增值税：基础电信服务增值税由 6% 调升为 9%（事件驱动，不存年度序列）。",
            "· 股息率/股息利差随行情变动，需在刷新行情快照后回填（本地存储预留字段）。",
        ],
    })

    return files
