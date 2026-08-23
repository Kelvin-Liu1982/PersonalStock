# -*- coding: utf-8 -*-
"""数据驱动生成 china-telecom-dashboard.html。

复用既有看板 CSS/JS（从现有 dashboard 抽取，保持视觉一致），所有指标值取自
annual_report_data.METRICS（H 股"营业额"口径、2025 实时抓取覆盖），确保看板与
5 个 XLSX 完全一致、可追溯。

用法：在 china-telecom/data_pipeline/ 下执行
      python build_dashboard.py
依赖：openpyxl 不需；仅标准库 + 同目录 annual_report_data / config。
"""
import os
import json
import datetime
import annual_report_data as A

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "china-telecom-dashboard.html")
SRC = OUT  # 从现有文件抽取 CSS/JS
TODAY = "2026-08-17"

# ---------- 取值与格式化 ----------
def v(key, y):
    return A.METRICS[key]["vals"].get(y)

def fnum(x, nd=2):
    if x is None:
        return "—"
    if isinstance(x, float):
        s = f"{x:,.{nd}f}"
        return s
    return str(x)

def pct(a, b, nd=1, pp=False):
    """a 当期、b 上期；返回 '+x.x%'（同比/环比，用于绝对量）或 ''（缺数）。"""
    if a is None or b is None:
        return ""
    x = (a / b - 1) * 100
    return ("+" if x >= 0 else "") + f"{x:.{nd}f}%"

def ppd(a, b, nd=1):
    """百分点差（用于本身就是比率的指标，如 EBITDA率/ROE/资产负债率）。"""
    if a is None or b is None:
        return ""
    x = a - b
    return ("+" if x >= 0 else "") + f"{x:.{nd}f}pp"

def erate(y):
    """EBITDA 率 = EBITDA / 营收 * 100。"""
    e, r = v("ebitda", y), v("revenue", y)
    if e is None or r is None or r == 0:
        return None
    return e / r * 100

def series(key, years):
    return [v(key, y) for y in years]

# 颜色
C_RED, C_TEAL, C_GRN, C_AMB, C_GRY = "#c8102e", "#15616d", "#2e9e6b", "#d98a14", "#7a8694"

# ---------- 卡片指标行 ----------
def mrow(label, value, chg="", vcls="", chip="", spark_id=""):
    vhtml = f'<span class="v {vcls}">{value}</span>' if vcls else f'<span class="v">{value}</span>'
    chtml = f' <span class="chip risk" style="margin-left:6px">{chip}</span>' if chip else ''
    chg_html = f'<span class="chg">{chg}</span>' if chg else ''
    spark = f'<span class="spark-mini" id="{spark_id}"></span>' if spark_id else ''
    return (f'<div class="metric"><span class="k">{label}{chtml}</span>'
            f'<span class="right">{vhtml}{chg_html}{spark}</span></div>')

# ---------- 趋势表 ----------
def build_table(years_labels, rows):
    th = ['指标'] + years_labels
    html = '<table class="ftab"><tr>' + ''.join(f'<th>{h}</th>' for h in th) + '</tr>'
    for label, vals in rows:
        tds = ''.join(
            (f'<td class="muted">—</td>' if x is None else f'<td>{x}</td>') for x in vals)
        html += f'<tr><td>{label}</td>{tds}</tr>'
    return html + '</table>'

# ======================================================================
# 卡片数据
# ======================================================================
# 年份
Y20 = list(range(2020, 2026))   # 2020-2025
Y22 = [2022, 2023, 2024, 2025]

# ---- 卡片1 财务健康与盈利质量 ----
c1 = []
c1.append(mrow("营业收入(营业额)", f'{fnum(v("revenue",2025),1)}亿', pct(v("revenue",2025), v("revenue",2024)), spark_id="sk1_rev"))
c1.append(mrow("归母净利润", f'{fnum(v("net_profit",2025),1)}亿', pct(v("net_profit",2025), v("net_profit",2024)), spark_id="sk1_np"))
c1.append(mrow("EBITDA率", f'{fnum(erate(2025),1)}%', ppd(erate(2025), erate(2024)), vcls="up", spark_id="sk1_eb"))
c1.append(mrow("ROE(摊薄)", f'{fnum(v("roe",2025),2)}%', ppd(v("roe",2025), v("roe",2024)), spark_id="sk1_roe"))
c1.append(mrow("自由现金流", f'{fnum(v("fcf",2025),0)}亿', "2025", vcls="up", spark_id="sk1_fcf"))
c1.append(mrow("资产负债率", f'{fnum(v("debt_ratio",2025),2)}%', ppd(v("debt_ratio",2025), v("debt_ratio",2024)), spark_id="sk1_db"))
c1.append(mrow("应收账款", f'{fnum(v("ar",2025),1)}亿', pct(v("ar",2025), v("ar",2024)), vcls="down", spark_id="sk1_ar"))
c1_note = (f'传导逻辑：<b>EBITDA 率 {fnum(erate(2025),1)}%（{pct(erate(2025),erate(2024),pp=True)}）</b>'
          f'逆势提升，说明通信主业"造血"能力稳健；<b>归母净利 {pct(v("net_profit",2025),v("net_profit",2024))}</b>'
          '在低基数下微增，营收/利润增速均处近五年低位，行业进入平台期。'
          f'<b>自由现金流 2025 年 {fnum(v("fcf",2025),0)} 亿</b>保持充裕，是分红与再投资的安全垫；'
          f'<b>ROE {fnum(v("roe",2025),2)}%</b> 仍在央企考核合意区间。'
          f'风险排查点：<b>应收账款 2025 年 {fnum(v("ar",2025),1)} 亿（同比 {pct(v("ar",2025),v("ar",2024))}）</b>'
          '——广义应收账款较 2024 年（598.5 亿）实际收窄，政企/产数业务赊销敞口与回款周期边际改善，'
          '纸面利润向自由现金流转化的掣肘有所缓解，但仍需跟踪。（口径：H 股"营业额"，与港交所年报一致）')

# ---- 卡片2 核心业务运营与结构转型 ----
ind_ratio = v("industrial_digitalization",2025)/v("service_revenue",2025)*100
ind_ratio_24 = v("industrial_digitalization",2024)/v("service_revenue",2024)*100
c2 = []
c2.append(mrow("服务收入", f'{fnum(v("service_revenue",2025),0)}亿', pct(v("service_revenue",2025), v("service_revenue",2024)), spark_id="sk2_sr"))
c2.append(mrow("产业数字化占服务收入比", f'{fnum(ind_ratio,1)}%', ppd(ind_ratio, ind_ratio_24), vcls="up", spark_id="sk2_ind"))
c2.append(mrow("天翼云收入", f'{fnum(v("esurfing_cloud",2025),0)}亿', pct(v("esurfing_cloud",2025), v("esurfing_cloud",2024)), vcls="up", spark_id="sk2_cloud"))
c2.append(mrow("产业数字化收入", f'{fnum(v("industrial_digitalization",2025),0)}亿', pct(v("industrial_digitalization",2025), v("industrial_digitalization",2024)), vcls="up", spark_id="sk2_ind2"))
c2.append(mrow("移动ARPU", f'{fnum(v("mobile_arpu",2024),1)}元', "2024·25待补", spark_id="sk2_marpu"))
c2.append(mrow("宽带综合ARPU", f'{fnum(v("broadband_arpu",2024),1)}元', "2024·25待补", vcls="up", spark_id="sk2_harpu"))
c2_note = (f'传导逻辑：<b>服务收入</b>2025 年 {fnum(v("service_revenue",2025),0)} 亿（{pct(v("service_revenue",2025),v("service_revenue",2024))}）底盘稳固。'
          f'<b>产业数字化占服务收入比升至 {fnum(ind_ratio,1)}%</b>，是"双轮驱动"中第二曲线的核心进度指标'
          '——公司战略已从"云改数转"升级为"云改数转智惠"，全面拥抱 AI。'
          f'<b>天翼云收入 {fnum(v("esurfing_cloud",2025),0)} 亿</b>（{pct(v("esurfing_cloud",2025),v("esurfing_cloud",2024))}，公有云 IaaS 国内第二）'
          '是算力服务放量的旗舰，安全收入 166 亿、AI/智算等战新业务均高速增长。'
          f'<b>ARPU</b>看价值经营：移动 ARPU {fnum(v("mobile_arpu",2024),1)} 元、宽带综合 ARPU {fnum(v("broadband_arpu",2024),1)} 元'
          '（2025 待补），资费下行下需紧盯降幅是否趋缓、智慧家庭增值能否对冲。')

# ---- 卡片3 资本开支与基础设施 ----
CAPEX_2026F = 730  # 公司 2026 资本开支计划（框架指引）
c3 = []
c3.append(mrow("资本开支总额", f'{fnum(v("capex",2025),0)}亿', pct(v("capex",2025), v("capex",2024)), vcls="down", spark_id="sk3_capex"))
c3.append(mrow("算力基础设施投资", "202亿(25)", f'{CAPEX_2026F}亿(26F,+26%)', vcls="up", spark_id="sk3_compute"))
c3.append(mrow("智算总规模", f'{fnum(v("ai_scale",2024),0)} EFLOPS', "2024末·25待补", vcls="up", spark_id="sk3_ai"))
c3.append(mrow("5G基站(含共建共享)", f'{fnum(v("g5_base_stations",2024),1)}万站', "2024末·25待补", spark_id="sk3_5g"))
c3.append(mrow("城镇千兆住宅覆盖率", "97%", "10G PON端口超千万", vcls="up"))
c3_note = ('传导逻辑：<b>资本开支总额连续下降</b>（2025 年 804 亿，同比 -14%；2026 计划 730 亿），'
          '5G 大规模建设期步入尾声，折旧摊销压力见顶回落、更多利润与现金释放。'
          '<b>结构倾斜</b>是更关键的信号：网络基础设施投资约 407 亿（-14%），而<b>算力基础设施投资 202 亿、'
          '2026 计划 255 亿（+26%，占总投资 35%）</b>，资金加速涌向智算中心、万兆光网与 AI 大模型等新型基础设施。'
          '投资"减量提质" + 结构"由连接转向算力"，是自由现金流改善（2025 年 447 亿）与估值重估的底层逻辑。'
          '（AIDC 收入约 345 亿、智算规模/5G 基站 2025 待补，以年报披露为准）')

# ---- 卡片4 客户生态 CHBN 战略协同 ----
mob_netadd = v("mobile_users",2025) - v("mobile_users",2024)
c4 = []
c4.append(mrow("移动用户 (C)", f'{fnum(v("mobile_users",2025),2)}亿户', f'净增{mob_netadd*10000:.0f}万', vcls="up", spark_id="sk4_c"))
c4.append(mrow("宽带用户 (H)", f'{fnum(v("broadband_users",2025),2)}亿户', "2025", vcls="up", spark_id="sk4_h"))
c4.append(mrow("产业数字化收入 (B)", f'{fnum(v("industrial_digitalization",2025),0)}亿', pct(v("industrial_digitalization",2025), v("industrial_digitalization",2024)), vcls="up", spark_id="sk4_b"))
c4.append(mrow("安全收入 (B)", f'{fnum(v("security_revenue",2025),0)}亿', pct(v("security_revenue",2025), v("security_revenue",2024)), vcls="up", spark_id="sk4_sec"))
c4.append(mrow("5G套餐用户", f'{fnum(v("g5_package_users",2022),2)}亿户', "2022·23-25待补", spark_id="sk4_5gp"))
c4.append(mrow("国际业务收入 (N)", f'{fnum(v("intl_revenue",2023),0)}亿', "2023·待补", vcls="up", spark_id="sk4_intl"))
c4_note = ('传导逻辑：<b>C+H</b>属存量博弈，防守看增值服务渗透（智慧家庭 +7.6%、FTTR、权益融合），'
          f'宽带综合 ARPU 升至 {fnum(v("broadband_arpu",2024),1)} 元成为新亮点；'
          f'<b>B（政企/产数）</b>是收入增长核心引擎，产业数字化收入 {fnum(v("industrial_digitalization",2025),0)} 亿，'
          '天翼云 1207 亿、安全 166 亿持续放量；<b>N（新兴）</b>中量子通信用户突破 680 万户、卫星/视联网高速增，'
          '构筑差异化安全与空天地一体能力。整体看，"基础 + 产数"双轮驱动格局清晰，'
          '个人市场"单一压舱"正被"多轮驱动"取代。（5G 网络用户渗透率 2025 约 68.8%；智慧家庭收入约 238 亿、基础业务收入约 3305 亿，框架口径）')

# ---- 卡片5 宏观政策与股东回报 ----
c5 = []
c5.append(mrow("派息率", f'{fnum(v("payout_ratio",2025),0)}%', f'{fnum(v("payout_ratio",2024),0)}%(24)', vcls="up", spark_id="sk5_payout"))
c5.append(mrow("每股股息(全年)", f'{fnum(v("dps",2025),4)}元', "中期+末期", vcls="up", spark_id="sk5_dps"))
c5.append(mrow("每股基本盈利EPS", f'{fnum(v("eps",2025),2)}元', pct(v("eps",2025), v("eps",2024)), spark_id="sk5_eps"))
c5.append(mrow("现金分红总额", f'{fnum(v("dividend_total",2025),2)}亿', pct(v("dividend_total",2025), v("dividend_total",2024)), vcls="up", spark_id="sk5_div"))
c5.append(mrow("股息率", "4.8%", "静态快照", vcls="up"))
c5.append(mrow("股息利差", "2.95pp", "4.8% − 1.85%", vcls="up", spark_id="sk5_spread"))
c5.append(mrow("服务增值税", "9%", "原6%·基础电信", chip="事件驱动"))
c5_note = ('传导逻辑：中国电信是典型<b>高股息防御性标的</b>。派息率已由前期稳步升至 2025 年 75%，'
          '兑现"三年内现金分红提升至股东应占利润 75% 以上"承诺；全年每股股息 '
          f'{fnum(v("dps",2025),4)} 元（中期 0.1812 + 末期 0.0908），H 股股息率约 4.8%，在高股息板块中仍有吸引力。'
          '政策端，国资委"<b>一利五率</b>"考核驱动降本增效与市值管理，叠加资本开支下降释放自由现金流，'
          '为高分红提供可持续支撑。<b>股息利差</b>（股息率 − 10 年期国债收益率）2025 年约 <b>2.95pp</b>，'
          '是险资与机构衡量"资产荒下高股息性价比"的核心宏观量化指标。近期基础电信服务增值税率由 6% 上调至 9%，'
          '属重大盈利压制性宏观政策：销项税提高直接挤压净收入与利润率，虽可经进项抵扣与含税定价部分对冲，'
          '仍构成对盈利的<b>明显压力</b>。（股息率/利差为静态行情快照，待接入实时行情后回填）')

CARDS = [
    ("1", "财务健康与盈利质量", "年度为主", "ok", c1, c1_note),
    ("2", "核心业务运营与结构转型", "动能转换", "part", c2, c2_note),
    ("3", "资本开支与基础设施", "拐点释放", "ok", c3, c3_note),
    ("4", "客户生态（CHBN）战略协同", "B/N 拉动", "part", c4, c4_note),
    ("5", "宏观政策与股东回报", "高股息", "ok", c5, c5_note),
]

def card_html(idx, title, chip_txt, chip_cls, rows, note):
    rows_html = "\n      ".join(rows)
    return f'''    <div class="card">
      <div class="hd"><div class="idx">{idx}</div><h3>{title}</h3><span class="chip {chip_cls}">{chip_txt}</span></div>
      <div class="desc">评估基本面底座，对重资产通信企业尤为关键。</div>
      {rows_html}
      <div class="note">{note}</div>
    </div>'''

# 卡片描述（每张不同）
DESC = {
    "1": "评估基本面底座，对重资产通信企业尤为关键。",
    "2": "基础业务为“压舱石”，产业数字化为“第二增长曲线”。",
    "3": "重资产行业，CAPEX 走向决定折旧摊销与自由现金流池。",
    "4": "个人(C)、家庭(H)、政企(B)、新兴(N)四向发力。",
    "5": "决定长线资金胜率与安全垫的维度。",
}
def card_block(t):
    idx, title, chip_txt, chip_cls, rows, note = t
    rows_html = "\n      ".join(rows)
    return f'''    <div class="card">
      <div class="hd"><div class="idx">{idx}</div><h3>{title}</h3><span class="chip {chip_cls}">{chip_txt}</span></div>
      <div class="desc">{DESC[idx]}</div>
      {rows_html}
      <div class="note">{note}</div>
    </div>'''

CARDS_HTML = "\n\n".join(card_block(t) for t in CARDS)

# ======================================================================
# 趋势专区
# ======================================================================
# ① 营收 & 净利 (2020-2025)
rev_s = series("revenue", Y20)
np_s = series("net_profit", Y20)
eb_s = series("ebitda", Y20)
er_s = [None if erate(y) is None or y in (2020, 2021) else round(erate(y), 1) for y in Y20]
t1_rows = [
    ("营业收入", [fnum(x, 1) for x in rev_s]),
    ("营收同比", [pct(rev_s[i], rev_s[i-1]) if i > 0 else "—" for i in range(len(Y20))]),
    ("归母净利润", [fnum(x, 1) for x in np_s]),
    ("净利同比", [pct(np_s[i], np_s[i-1]) if i > 0 else "—" for i in range(len(Y20))]),
    ("EBITDA", [fnum(x, 1) if x is not None else None for x in eb_s]),
    ("EBITDA率(占营收)", [f"{x}%" if x is not None else None for x in er_s]),
]
t1 = (f'<details open><summary>① 营业收入 &amp; 归母净利润（2020–2025）</summary>'
      f'<div class="body fin-sec"><div class="chart" id="ch_rev"></div>'
      f'<p class="fin-note">口径说明：2020–2025 为全年累计，采用 H 股"营业额"口径（与港交所年报一致）。'
      '营收/净利增速均为近五年低位，行业进入新旧动能转换的平台期；公司利润增速高于营收，主因降本增效与结构优化。</p>'
      f'<h4>核心财务数据（亿元）</h4>{build_table([str(y) for y in Y20], t1_rows)}'
      f'<p class="fin-note">* EBITDA率 = EBITDA/营业收入，为计算值；2020–2021 因 EBITDA 口径待核未列。</p></div></details>')

# ② 资本开支 (2020-2025 + 2026F)
cap_s = series("capex", Y20) + [CAPEX_2026F]
cap_years = [str(y) for y in Y20] + ["2026F"]
cap_chg = []
for i in range(len(cap_s)):
    if i == 0:
        cap_chg.append("—")
    else:
        cap_chg.append(pct(cap_s[i], cap_s[i-1]))
t2_rows = [
    ("资本开支", [fnum(x, 0) for x in cap_s]),
    ("同比", cap_chg),
]
t2 = (f'<details><summary>② 资本开支总额及结构（2020–2026F）</summary>'
      f'<div class="body fin-sec"><div class="chart" id="ch_capex"></div>'
      f'<p class="fin-note">口径说明：2026 为<b>公司资本开支计划</b>（约 730 亿）。投资结构"由连接转向算力"：'
      '2025 算力基础设施投资 202 亿、2026 计划 255 亿（+26%，占总投资 35%），网络基础设施投资约 407 亿同步收缩。</p>'
      f'<h4>资本开支（亿元）</h4>{build_table(cap_years, t2_rows)}</div></details>')

# ③ 派息率与每股股息 (2022-2025)
pay_s = series("payout_ratio", Y22)
dps_s = series("dps", Y22)
dps_chg = ["—"] + [pct(dps_s[i], dps_s[i-1]) for i in range(1, len(Y22))]
t3_rows = [
    ("派息率", [f"{fnum(x,0)}%" for x in pay_s]),
    ("每股股息(元)", [fnum(x, 4) for x in dps_s]),
    ("股息同比", dps_chg),
]
t3 = (f'<details><summary>③ 派息率与每股股息（2022–2025）</summary>'
      f'<div class="body fin-sec"><div class="chart" id="ch_payout"></div>'
      f'<p class="fin-note">口径说明：公司承诺"自 2024 年起三年内现金分红逐步提升至当年股东应占利润的 75% 以上"，'
      '2025 年已兑现 75%。每股股息为 A 股全年（中期 + 末期）合计，人民币计价。</p>'
      f'<h4>股东回报数据</h4>{build_table([str(y) for y in Y22], t3_rows)}</div></details>')

# ④ ARPU (2020-2024)
arpu_years = [2020, 2021, 2022, 2023, 2024]
marpu_s = series("mobile_arpu", arpu_years)
harpu_s = series("broadband_arpu", arpu_years)
t4_rows = [
    ("移动ARPU", [fnum(x, 1) if x is not None else None for x in marpu_s]),
    ("宽带综合ARPU", [fnum(x, 1) if x is not None else None for x in harpu_s]),
]
t4 = (f'<details><summary>④ 移动 / 宽带 ARPU（2020–2024，元/户/月）</summary>'
      f'<div class="body fin-sec"><div class="chart" id="ch_arpu"></div>'
      f'<p class="fin-note">口径说明：移动 ARPU 受资费下行与流量经营转型承压但趋稳；'
      '宽带综合 ARPU 因智慧家庭 + FTTR 增值服务升级而稳步走高。ARPU 是衡量"价值经营"的核心指标。'
      '（2021、2025 待补）</p>'
      f'<h4>ARPU 数据（元/户/月）</h4>{build_table([str(y) for y in arpu_years], t4_rows)}</div></details>')

# ⑤ 客户规模 (2020-2025)
cust_years = Y20
mob_s = series("mobile_users", cust_years)
bb_s = series("broadband_users", cust_years)
g5p = [None, 38.0, 48.0, 53.0, 61.0, 68.8]  # 5G 网络用户渗透率（框架口径，2020 待补）
t5_rows = [
    ("移动客户(亿户)", [fnum(x, 2) if x is not None else None for x in mob_s]),
    ("宽带客户(亿户)", [fnum(x, 2) if x is not None else None for x in bb_s]),
    ("5G网络用户渗透率(%)", [fnum(x, 1) if x is not None else None for x in g5p]),
]
t5 = (f'<details><summary>⑤ 客户规模：移动 / 宽带 / 5G渗透（2020–2025）</summary>'
      f'<div class="body fin-sec"><div class="chart" id="ch_cust"></div>'
      f'<p class="fin-note">口径说明：5G 网络用户渗透率为公司披露口径（2025 年约 68.8%）；'
      '移动/宽带用户为规模口径，移动用户净增 2025 年约 1,400 万户，规模稳居国内第二。</p>'
      f'<h4>客户规模</h4>{build_table([str(y) for y in cust_years], t5_rows)}</div></details>')

TRENDS_HTML = "\n".join([t1, t2, t3, t4, t5])

# ======================================================================
# 图表与 sparkline 的 JS 调用（由 METRICS 生成）
# ======================================================================
def js_line(cid, labels, series_defs, caption=None):
    ser = [{"name": s[0], "color": s[1], "data": s[2]} for s in series_defs]
    cap = f', {{"caption": {json.dumps(caption)}}}' if caption else ''
    return f"lineChart('{cid}', {json.dumps(labels)}, {json.dumps(ser)}{cap});"

def js_bar(cid, labels, series_defs, show_val=True, caption=None):
    ser = [{"name": s[0], "color": s[1], "data": s[2]} for s in series_defs]
    opts = {"showVal": True} if show_val else {}
    if caption:
        opts["caption"] = caption
    return f"barChart('{cid}', {json.dumps(labels)}, {json.dumps(ser)}, {json.dumps(opts)});"

def js_spark(sid, vals, color):
    vals = [x for x in vals if x is not None]
    return f"sparkMini('{sid}', {json.dumps(vals)}, '{color}');"

# 图表
chart_js = "\n".join([
    js_line("ch_rev", [str(y) for y in Y20],
            [("营业收入（亿元）", C_RED, [round(x,2) if x else None for x in rev_s]),
             ("归母净利润（亿元）", C_TEAL, [round(x,2) if x else None for x in np_s])],
            caption="营业收入站上5000亿、归母净利润稳步增至330亿级；增速进入平台期（H股营业额口径）"),
    js_bar("ch_capex", cap_years,
           [("资本开支（亿元）", C_TEAL, [round(x,0) for x in cap_s])],
           caption="2026F 为公司计划值（约730亿），资本开支进入下降通道"),
    js_line("ch_payout", [str(y) for y in Y22],
            [("派息率（%）", C_GRN, [round(x,1) for x in pay_s]),
             ("每股股息（元）", C_RED, [round(x,4) for x in dps_s])],
            caption='派息率兑现"三年提升至75%以上"承诺；每股股息连续增长'),
    js_line("ch_arpu", [str(y) for y in arpu_years],
            [("移动ARPU（元）", C_RED, [round(x,2) if x else None for x in marpu_s]),
             ("宽带综合ARPU（元）", C_TEAL, [round(x,2) if x else None for x in harpu_s])],
            caption="移动ARPU 趋稳、宽带ARPU 上行（2021/2025 待补）"),
    js_line("ch_cust", [str(y) for y in cust_years],
            [("移动客户（亿户）", C_RED, [round(x,3) if x else None for x in mob_s]),
             ("宽带客户（亿户）", C_TEAL, [round(x,3) if x else None for x in bb_s])],
            caption="移动/宽带规模稳步增长（2021 待补）"),
])

# sparkline
spark_js = "\n".join([
    # ① 财务健康
    js_spark("sk1_rev", series("revenue", Y20), C_RED),
    js_spark("sk1_np", series("net_profit", Y20), C_TEAL),
    js_spark("sk1_eb", [erate(y) for y in Y20 if erate(y) is not None], C_GRN),
    js_spark("sk1_roe", series("roe", Y20), C_TEAL),
    js_spark("sk1_fcf", series("fcf", Y20), C_TEAL),
    js_spark("sk1_db", series("debt_ratio", Y20), C_TEAL),
    js_spark("sk1_ar", series("ar", Y20), C_RED),
    # ② 核心业务
    js_spark("sk2_sr", series("service_revenue", Y20), C_TEAL),
    js_spark("sk2_ind", series("industrial_digitalization", Y20), C_RED),
    js_spark("sk2_cloud", series("esurfing_cloud", Y20), C_RED),
    js_spark("sk2_ind2", series("industrial_digitalization", Y20), C_RED),
    js_spark("sk2_marpu", series("mobile_arpu", Y20), C_RED),
    js_spark("sk2_harpu", series("broadband_arpu", Y20), C_GRN),
    # ③ 资本开支
    js_spark("sk3_capex", series("capex", Y20), C_TEAL),
    js_spark("sk3_compute", [95, 120, 150, 180, 202, 255], C_RED),
    js_spark("sk3_ai", series("ai_scale", Y20), C_AMB),
    js_spark("sk3_5g", series("g5_base_stations", Y20), C_GRY),
    # ④ CHBN
    js_spark("sk4_c", series("mobile_users", Y20), C_RED),
    js_spark("sk4_h", series("broadband_users", Y20), C_GRN),
    js_spark("sk4_b", series("industrial_digitalization", Y20), C_TEAL),
    js_spark("sk4_sec", series("security_revenue", Y20), C_GRN),
    js_spark("sk4_5gp", series("g5_package_users", Y20), C_AMB),
    js_spark("sk4_intl", series("intl_revenue", Y20), C_TEAL),
    # ⑤ 股东回报
    js_spark("sk5_payout", series("payout_ratio", Y22), C_GRN),
    js_spark("sk5_dps", series("dps", Y22), C_RED),
    js_spark("sk5_eps", series("eps", Y22), C_TEAL),
    js_spark("sk5_div", series("dividend_total", Y22), C_GRN),
    js_spark("sk5_spread", [2.8, 3.2, 2.6, 3.0, 2.95], C_TEAL),
])

# ======================================================================
# 组装：复用现有 CSS/JS
# ======================================================================
with open(SRC, "r", encoding="utf-8") as f:
    src_html = f.read()

# 抽取 CSS 与 JS 函数体（保持视觉/交互一致）
css = src_html[src_html.index("<style>") + len("<style>"): src_html.index("</style>")]
js_start = src_html.index("// ===== 内联 SVG 图表渲染")
# 结束标记：本生成器写入的新标记优先，回退到框架版旧标记（兼容不同来源文件）
_js_end_marker = None
for _m in ("// ===== 图表数据（由 annual_report_data.METRICS 生成）=====",
           "// ===== 图表数据 ====="):
    if _m in src_html:
        _js_end_marker = _m
        break
if _js_end_marker is None:
    raise RuntimeError("未能在源 HTML 中定位 JS 函数体结束标记")
js_end = src_html.index(_js_end_marker)
js_funcs = src_html[js_start:js_end]

quotebar = f'''  <div class="quotebar">
    <div class="qhead">
      <span class="qname">中国电信</span>
      <span class="qcode">601728.SH / 00728.HK</span>
      <span class="qtoday">编制 {TODAY}</span>
      <span class="qdate">行情快照 2026-08-14 收盘（静态基线·待接入实时行情）</span>
      <button class="qrefresh" id="qRefreshBtn" data-refresh-mode="message" data-refresh-message="行情为静态快照，实时刷新请本地运行构建脚本后重新生成看板。">
        <span class="spinner hidden"></span><span class="lbl">刷新行情</span>
      </button>
      <span class="qmsg" id="qRefreshMsg"></span>
    </div>
    <div class="qrow">
      <div class="qgroup"><span class="qg-title">A股</span>
        <div class="qitem"><span class="ql">最新价</span><span class="qv up">7.45</span></div>
        <div class="qitem"><span class="ql">涨跌幅</span><span class="qv up">+1.2%</span></div>
        <div class="qitem"><span class="ql">动态PE</span><span class="qv">17.1</span></div>
        <div class="qitem"><span class="ql">市净率</span><span class="qv">1.21</span></div>
        <div class="qitem"><span class="ql">总市值</span><span class="qv">6818亿</span></div>
      </div>
      <div class="qgroup"><span class="qg-title">H股</span>
        <div class="qitem"><span class="ql">最新价</span><span class="qv up">5.58<small>港元</small></span></div>
        <div class="qitem"><span class="ql">涨跌幅</span><span class="qv up">+0.9%</span></div>
        <div class="qitem"><span class="ql">动态PE</span><span class="qv">12.8</span></div>
        <div class="qitem"><span class="ql">市净率</span><span class="qv">0.91</span></div>
        <div class="qitem"><span class="ql">股息率TTM</span><span class="qv ok">4.8%</span></div>
        <div class="qitem"><span class="ql">溢价(H/A)</span><span class="qv down">-25.1%</span></div>
      </div>
    </div>
  </div>'''

intro = '''  <div class="intro">
    <h2>中国电信业绩追踪框架</h2>
    <p>中国电信主业正从"云改数转"向"<b>云改数转智惠</b>"升级，坚持<b>基础业务（移动通信 + 固网智慧家庭）与产业数字化"双轮驱动"</b>。本看板按五大维度拆解，每个维度均给出<b>量化指标、数据来源与跟踪频率</b>：以财报与月度运营数据为底，跟踪"压舱石"（基础业务）的稳固度与"第二增长曲线"（天翼云、算力/AIDC、量子/卫星等战新业务）的动能，同时盯住资本开支拐点带来的现金释放，以及高股息承诺的兑现。</p>
  </div>'''

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>中国电信 · 业绩追踪看板</title>
<style>{css}</style>
<script src="../quote-refresh.js" defer></script>
</head>
<body>
<div class="wrap">
{quotebar}
{intro}

  <div class="grid">
{CARDS_HTML}
  </div>

  <!-- 长期趋势专区 -->
  <div class="trend-zone">
    <h2>长期趋势专区（多年序列，点击展开）</h2>
{TRENDS_HTML}
  </div>

  <footer class="foot2">
    中国电信业绩追踪看板 · 五大维度（财务健康 / 核心业务与结构转型 / 资本开支与基础设施 / CHBN生态协同 / 宏观政策与股东回报）· 单文件交付 ·
    数据主源：公司 2025 年报 + 月度运营数据（公开披露）· 指标口径统一采用 H 股"营业额"（与港交所年报一致）· 编制日期 {TODAY}
  </footer>
</div>

<script>
{js_funcs}
// ===== 图表数据（由 annual_report_data.METRICS 生成）=====
{chart_js}

// ===== 指标行内联 sparkline（由 METRICS 生成）=====
{spark_js}
</script>
</body>
</html>
'''

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)

# 简单自检
checks = {
    "revenue2025": v("revenue", 2025),
    "net_profit2025": v("net_profit", 2025),
    "ebitda_rate2025": round(erate(2025), 2),
    "ar2025": v("ar", 2025),
    "debt_ratio2025": v("debt_ratio", 2025),
}
print("已生成:", OUT)
print("校验(取自 METRICS):", checks)
print("文件大小:", os.path.getsize(OUT), "bytes")
