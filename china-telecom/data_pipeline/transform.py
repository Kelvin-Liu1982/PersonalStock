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
        return {r.get("REPORT_DATE"): r.get("AMOUNT")
                for r in inc if r.get("ITEM_NAME") == item and r.get("REPORT_DATE")}
    rev = series("营业额")
    npf = series("股东应占溢利")
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
    labels = [p[1] for p in periods]
    rev_row = ("营业收入(单季,亿元)", [r[1] for r in qr], "由累计利润表推导单季；Q1=一季报，H1=上半年")
    np_row = ("本公司股东应占溢利(单季,亿元)", [r[1] for r in qn], "由累计利润表推导单季")
    q_headers = ["指标"] + labels + ["备注"]
    q_rows = [rev_row, np_row]
    return q_headers, q_rows


def build_dataset():
    dv = {k: [A.METRICS[k]["vals"].get(y) for y in C.YEARS] for k in A.METRICS}
    dv = reconcile_with_fetch(dv)
    global DV
    DV = dv

    # 派生：资本开支占服务收入比（%）
    cap = dv["capex"]
    srev = dv["service_revenue"]
    cap_ratio = []
    for i, y in enumerate(C.YEARS):
        c, s = cap[i], srev[i]
        cap_ratio.append(round(c / s * 100, 1) if (c and s) else None)
    dv["capex_ratio"] = cap_ratio

    q_headers, q_rows = _quarterly_rows()

    files = []

    # ---- 文件1：财务健康与盈利质量 ----
    f1_rows = [
        _row("revenue"), _row("net_profit"), _row("ebitda"), _row("roe"),
        _row("net_margin"), _row("debt_ratio"), _row("fcf"), _row("ar"),
    ]
    files.append({
        "file_name": "中国电信_财务健康与盈利质量.xlsx",
        "title": "中国电信 · 财务健康与盈利质量（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f1_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：东方财富 Eastmoney 港股 F10 利润表/资产负债表（00728.HK，源自港交所披露易）、A 股合并报表复合指标（00728 港股财务指标，源自历年年报）、港交所 2020-2025 年报与业绩公告。",
            "· 单位：人民币亿元；比率%；应收账款/资产来自最新年度资产负债表（H 股 F10，币种人民币）。",
            "· 营业收入采用 H 股'营业额'（经营收入）口径：2020-2025 与港交所年报披露一致（如 2025=5296 亿）。A 股合并利润表'营业收入'为较窄列报，约低 57 亿元，二者为同一合并主体不同列报口径。",
            "· 净利润采用 H 股'本公司股东应占溢利'（=A 股归母净利润），2025=331.85 亿≈332 亿。",
            "· EBITDA=经营溢利+折旧与摊销（来自实时抓取的利润表），2025=1438.7≈1439 亿；历史年度待补利润表科目。",
            "· 2025 年营收/净利/EPS/应收账款/资产负债率由数据管道实时抓取自 Eastmoney 并覆盖已核验值。",
            "· 无法核验的年份显示为'—'，待补公司历年年报。",
        ],
    })

    # ---- 文件2：核心业务运营与结构转型 ----
    f2_rows = [
        _row("service_revenue"), _row("industrial_digitalization"), _row("esurfing_cloud"),
        _row("idc_revenue"), _row("ai_revenue"), _row("security_revenue"),
        _row("ai_scale"), _row("g5_base_stations"),
    ]
    files.append({
        "file_name": "中国电信_核心业务运营与结构转型.xlsx",
        "title": "中国电信 · 核心业务运营与结构转型（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f2_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：港交所 2020-2025 年报/业绩公告（服务收入、产业数字化、天翼云、IDC、智能/安全收入、智算、5G 基站）、业绩推介材料。",
            "· 单位：收入亿元；智算 EFLOPS；基站万站。",
            "· 中国电信两大主业：基础业务（移动通信+固网智慧家庭）与产业数字化（天翼云/IDC/智算/安全/智能/视联网/量子/卫星）。",
            "· 天翼云：2020=138 → 2025=1207 亿，IaaS 国内第二、IaaS+PaaS 前三；产业数字化收入 2025=1473 亿。",
            "· 智算规模：2023=11.0 → 2024=62.0 EFLOPS（自有+接入）；5G 基站（含与中国联通共建共享）2024=137.5 万站。",
            "· 移动/宽带 ARPU、5G 套餐用户绝对数（2023-2025）、IDC(2023/2025)、智算(2025) 年报未单列精确值，显示为'—'待补。",
        ],
    })

    # ---- 文件3：资本开支与基础设施 ----
    f3_rows = [
        _row("capex"),
        ("资本开支占服务收入比(%)", cap_ratio, "=资本开支/服务收入；2025≈16.6%（年报披露资本开支占收比下降）"),
        _row("ai_scale"),
        _row("g5_base_stations"),
    ]
    files.append({
        "file_name": "中国电信_资本开支与基础设施.xlsx",
        "title": "中国电信 · 资本开支与基础设施（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f3_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：资本开支 2020-2025 来自港交所年报（2020=848、2021=870、2022=925、2023=988、2024=935、2025=804）；智算规模/5G 基站来自年报。",
            "· 单位：资本开支亿元；智算 EFLOPS；基站万站。",
            "· 资本开支连续下降（988→935→804），占服务收入比降至约 16.6%；2026 指引约 700 亿级、算力投资占比进一步提升。",
            "· 智算规模 2023=11.0 → 2024=62.0 EFLOPS（自有+接入）；5G 基站（含共建共享）2024=137.5 万站。",
        ],
    })

    # ---- 文件4：客户生态与政企业务 ----
    f4_rows = [
        _row("mobile_users"), _row("broadband_users"), _row("mobile_arpu"),
        _row("broadband_arpu"), _row("g5_package_users"), _row("esurfing_cloud"),
        _row("industrial_digitalization"), _row("security_revenue"), _row("intl_revenue"),
    ]
    files.append({
        "file_name": "中国电信_客户生态与政企业务.xlsx",
        "title": "中国电信 · 客户生态与政企业务（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f4_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：港交所 2020-2025 年报、业绩公告（用户规模、ARPU、5G 套餐、天翼云、产业数字化、安全、国际业务）。",
            "· 单位：用户亿户；ARPU 元/户/月；收入亿元。",
            "· 移动用户 2025 达 4.39 亿户（5G 网络用户渗透率 68.8%）；宽带用户 2.01 亿户（千兆渗透率 31.6%）。",
            "· 政企业务以产业数字化（2025=1473 亿）、天翼云（2025=1207 亿）、安全（2025=166 亿）、国际业务为核心引擎。",
            "· 5G 套餐用户绝对数、移动/宽带 ARPU（2021/2025）、IDC(2023/2025) 年报未单列精确值，显示为'—'待补。",
        ],
    })

    # ---- 文件5：宏观政策与股东回报 ----
    vat_row = ("服务增值税(%)", [None, None, None, None, None, 9],
               "事件驱动：基础电信服务增值税由 6% 调整为 9%（2025 起执行），对收入/利润/现金流短期有负面影响")
    dy_row = ("H股股息率(TTM,%)", [None, None, None, None, None, None],
              "=每股股息/股价，随行情每日变动；需刷新行情快照后填入（见 quote-refresh 机制）")
    ds_row = ("股息利差=股息率-10Y国债(%)", [None, None, None, None, None, None],
              "=H股股息率 - 10年期国债收益率；需行情快照与国债收益率后填入")
    f5_rows = [
        _row("eps"), _row("dps"), _row("payout_ratio"), _row("dividend_total"),
        dy_row, ds_row, vat_row,
    ]
    files.append({
        "file_name": "中国电信_宏观政策与股东回报.xlsx",
        "title": "中国电信 · 宏观政策与股东回报（2020–2025）",
        "annual_headers": ["指标", "2020", "2021", "2022", "2023", "2024", "2025", "备注"],
        "annual_rows": f5_rows,
        "q_headers": q_headers, "q_rows": q_rows,
        "source_text": [
            "· 数据来源：港交所 2022-2025 年报与业绩公告（EPS、每股股息、派息率、现金分红总额）。2020-2021 每股股息为港元末期息，未纳入人民币序列。",
            "· 单位：EPS/每股股息 元；派息率/股息率 %；分红总额亿元。",
            "· 派息率：2022=65%、2023>70%、2024=72%、2025=75%（承诺三年内提升至 75% 以上）。",
            "· 每股股息(全年)=中期+末期；2025=0.2720 元（+4.7%）。",
            "· 服务增值税：基础电信服务增值税由 6% 调升为 9%（事件驱动，不存年度序列）。",
            "· 股息率/股息利差随行情变动，需在刷新行情快照后回填（本地存储预留字段）。",
        ],
    })

    return files
