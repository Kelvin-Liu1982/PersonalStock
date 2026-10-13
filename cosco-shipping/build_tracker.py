# -*- coding: utf-8 -*-
"""
中远海控 · 主营与业绩追踪看板（方向C + 趋势增强）构建脚本
=====================================================================
数据主源: 中远海控_行业供需与运价数据.xlsx
约定    : 该 Excel 为唯一主数据源；更新文件后重跑本脚本即可刷新整个看板。
输出    : cosco-shipping/cosco-dashboard.html  (单文件，双击即开)
机制    : 时序数据抽成 JS 数组 + 长期趋势图 base64 内嵌，快照与趋势同源驱动。
"""
import os, re, json, base64, io, math
import openpyxl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

# ---------- 路径 ----------
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
WS   = os.path.dirname(HERE)  # 工作区根
sys.path.insert(0, WS)
# Phase 2 重构：折线/堆叠柱 SVG 生成器统一收口到跨看板公共库 common/svg_charts
from common.svg_charts import make_line_svg_wide, make_stacked_bar_svg, make_pct_stacked_bar_svg
SRC  = os.path.join(HERE, "数据源")  # 所有 Excel 数据源集中存放
XLSX = os.path.join(SRC, "中远海控_行业供需与运价数据.xlsx")
OUT  = os.path.join(HERE, "cosco-dashboard.html")

# ---------- 中文字体（候选优先级：PingFang SC/HK → Songti SC → Heiti TC → STHeiti → SimHei） ----------
try:
    fm._load_fonts(rebuild_cache=True)  # 让 Matplotlib 重新扫系统字体
except Exception:
    try:
        fm.fontManager.__init__()
    except Exception:
        pass
_available = {f.name for f in fm.fontManager.ttflist}
_CANDIDATES = ["PingFang SC", "PingFang HK", "Songti SC", "Heiti TC",
              "STHeiti", "Hei", "Hiragino Sans GB", "Arial Unicode MS",
              "SimHei", "Microsoft YaHei", "Noto Sans CJK SC"]
CN = next((c for c in _CANDIDATES if c in _available), None)
if CN is None:
    CN = next((n for n in sorted(_available)
              if any(k in n for k in ("SC", "TC", "Han", "Hei", "Song", "Kai", "CJK"))),
              "DejaVu Sans")
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [CN, "DejaVu Sans", "Arial"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 11

# ---------- 配色 ----------
C_SCFI="#c8102e"; C_CCFI="#15616d"; C_EU="#2e6f9e"; C_MED="#d98a14"
C_USW="#2e9e6b"; C_USE="#1f7a8c"; C_GULF="#7a8694"
C_THRU="#15616d"; C_EXP="#c8102e"
C_ASEAN="#2e9e6b"; C_EUY="#1f7a8c"; C_USY="#d98a14"; C_TY="#c8102e"
C_FLEET="#15616d"; C_ORDER="#7a8694"; C_IDLE="#d98a14"
C_BLUS="c8102e"; C_BLEU="15616d"

# ---------- 读 Excel ----------
wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)

# ---------- 中远海控_货运量与航线结构数据.xlsx（季度货运量等，来自另一 xlsx） ----------
OPX = os.path.join(SRC, "中远海控_货运量与航线结构数据.xlsx")
opwb = openpyxl.load_workbook(OPX, read_only=True, data_only=True)
def op_sheet_rows(name):
    ws = opwb[name]
    return [list(r) for r in ws.iter_rows(values_only=True)]

# 季度货运量明细(2021-)：单季货运量 / 同比 / 累计 / 外贸单箱收入 / 单季归母净利
qv = op_sheet_rows("季度货运量明细(2021-)")
_qv_rows = [r for r in qv[1:] if r[1] is not None]
qvol_dates = [str(r[1]) for r in _qv_rows]                       # "2021 Q1" ...
qvol       = [float(r[2]) for r in _qv_rows]                       # 单季货运量(万TEU)
qvol_yoy   = [float(r[3]) for r in _qv_rows]                       # 货运量同比(%)
qvol_cum   = [float(r[4]) for r in _qv_rows]                       # 累计货运量(万TEU)
qrev       = [float(r[5]) for r in _qv_rows]                       # 外贸单箱收入(USD/TEU)
qnp        = [float(r[6]) for r in _qv_rows]                       # 单季归母净利润(亿元RMB)

def sheet_rows(name):
    ws = wb[name]
    return [list(r) for r in ws.iter_rows(values_only=True)]

fr = sheet_rows("周运价指数(SCFI&CCFI)")
de = sheet_rows("需求端-港口吞吐量&出口")
su = sheet_rows("供给端-运力&闲置率")
def _qkey(s):
    m=re.search(r"(\d{4})\s*Q(\d)", str(s)); return (int(m.group(1)),int(m.group(2))) if m else (0,0)
su = [su[0]] + [r for r in su[1:] if _qkey(r[0]) <= (2026,2)]   # 仅取干净季频数据至 2026Q2
co = sheet_rows("供需调控-停航率&联盟")
co = [co[0]] + [r for r in co[1:] if _qkey(r[0]) <= (2026,2)]   # 仅取干净季频数据至 2026Q2

# --- 运价 ---
fr_dates=[str(r[0]) for r in fr[1:]]
scfi=[float(r[1]) for r in fr[1:]]
scfi_w=[float(r[2]) for r in fr[1:]]   # 周环比
ccfi=[float(r[3]) for r in fr[1:]]
ccfi_w=[float(r[4]) for r in fr[1:]]
eu=[float(r[5]) for r in fr[1:]]
med=[float(r[6]) for r in fr[1:]]
usw=[float(r[7]) for r in fr[1:]]
use=[float(r[8]) for r in fr[1:]]
gulf=[float(r[9]) for r in fr[1:]]
util_raw=[r[10] for r in fr[1:]]
notes_fr=[str(r[11]) for r in fr[1:]]

def parse_util(v):
    if isinstance(v,(int,float)):          # Excel 数字单元格存的是小数比例: 0.95=95%、1=100%
        x=float(v)
        return round(x*100,1) if x<=1.5 else round(x,1)
    s=str(v); nums=[int(n) for n in re.findall(r"\d+", s)]
    if not nums: return None
    if "-" in s and len(nums)>=2: return round((nums[0]+nums[1])/2,1)
    if ">" in s: return nums[0]+2.5
    if "~" in s: return nums[0]
    return nums[0]
util=[parse_util(v) for v in util_raw]

# --- 需求 ---
de_dates=[str(r[0]) for r in de[1:]]
def _or_none(v):
    if v is None or (isinstance(v, str) and v.strip()==""):
        return None
    return float(v)
thru=[_or_none(r[1]) for r in de[1:]]
thru_y=[_or_none(r[2]) for r in de[1:]]
exp=[float(r[3]) for r in de[1:]]
exp_y=[float(r[4]) for r in de[1:]]
asean_y=[float(r[5]) for r in de[1:]]
eu_y=[float(r[6]) for r in de[1:]]
us_y=[float(r[7]) for r in de[1:]]

# --- 供给 ---
su_dates=[str(r[0]) for r in su[1:]]
fleet=[float(r[1]) for r in su[1:]]
fleet_y=[float(r[2]) for r in su[1:]]
order=[float(r[3]) for r in su[1:]]
idle_s=[float(r[4]) for r in su[1:]]
idle_r=[float(r[5]) for r in su[1:]]
notes_su=[str(r[6]) for r in su[1:]]

# --- 调控 ---
co_dates=[str(r[0]) for r in co[1:]]
blank_us=[float(r[1]) for r in co[1:]]
blank_eu=[float(r[2]) for r in co[1:]]
notes_co=[str(r[3]) for r in co[1:]]

# --- 财务核心（独立交付文件：财报核心数据.xlsx）---
FIN_XLSX = os.path.join(SRC, "中远海控_财报核心数据.xlsx")
fws = openpyxl.load_workbook(FIN_XLSX, read_only=True, data_only=True)

# --- 宏观与政策环境（独立交付文件：中远海控_宏观与政策环境数据.xlsx）---
# 原硬编码于本脚本的 6 项宏观指标 + PMI 明细已抽为数据源文档，编辑该文件后重跑本脚本即生效。
MACRO_XLSX = os.path.join(SRC, "中远海控_宏观与政策环境数据.xlsx")
mws = openpyxl.load_workbook(MACRO_XLSX, read_only=True, data_only=True)
def macro_sheet_dicts(name):
    ws = mws[name]; rows=list(ws.iter_rows(values_only=True))
    hdr=[str(c) for c in rows[0]]; out=[]
    for r in rows[1:]:
        if r[0] is None: continue
        out.append({hdr[i]: (r[i] if i < len(r) else None) for i in range(len(hdr))})
    return out
_mrows = macro_sheet_dicts("宏观核心数据(年度)")
_mpmi  = macro_sheet_dicts("PMI明细(年度)")
def mcol(rows, key): return [float(d[key]) for d in rows]
# 6 项核心指标（2021–2025 年度；公开数据近似，非公司披露）
MYEARS          = [str(int(d["年份"])) for d in _mrows]
m_fuel          = mcol(_mrows, "VLSFO燃油价($/mt)")
m_charter       = mcol(_mrows, "Harpex租船费率指数")
m_ets           = mcol(_mrows, "EU_ETS碳价(€/t)")
m_redsea_ratio  = mcol(_mrows, "亚欧绕航好望角比例(%)")
m_redsea_absorb = mcol(_mrows, "运力吸收率(%)")
m_pmi           = mcol(_mrows, "欧美综合PMI")
# PMI 明细（美 ISM / 欧 HCOB，制造业 + 服务业）
_m_us_manuf = mcol(_mpmi, "美制造业PMI")
_m_us_serv  = mcol(_mpmi, "美服务业PMI")
_m_eu_manuf = mcol(_mpmi, "欧制造业PMI")
_m_eu_serv  = mcol(_mpmi, "欧服务业PMI")

def sheet_to_dicts(name):
    ws = fws[name]; rows=list(ws.iter_rows(values_only=True))
    hdr=[str(c) for c in rows[0]]; out=[]
    for r in rows[1:]:
        if r[0] is None: continue
        out.append({hdr[i]: (r[i] if i < len(r) else None) for i in range(len(hdr))})
    return out
fin_a = sheet_to_dicts("年度核心数据")
fin_q = sheet_to_dicts("季度核心数据")
def fnum(v):
    try: return float(v)
    except: return None
fin_years=[str(d["报告期"]).replace("年","") for d in fin_a]
fin_rev_a=[fnum(d["营业收入(亿元)"]) for d in fin_a]
fin_np_a=[fnum(d["归母净利润(亿元)"]) for d in fin_a]
fin_gm_a=[fnum(d["毛利率(%)"]) for d in fin_a]
fin_roe_a=[fnum(d["ROE摊薄(%)"]) for d in fin_a]
fin_ocf_a=[fnum(d["经营现金流(亿元)"]) for d in fin_a]
fin_dar_a=[fnum(d["资产负债率(%)"]) for d in fin_a]
fin_eps_a=[fnum(d["基本EPS(元)"]) for d in fin_a]
fin_div = sheet_to_dicts("分红数据")
fin_q_lbl=[str(d["报告期"]) for d in fin_q]
fin_rev_q=[fnum(d["营业收入(亿元)"]) for d in fin_q]
fin_np_q=[fnum(d["归母净利润(亿元)"]) for d in fin_q]
fin_gm_q=[fnum(d["毛利率(%)"]) for d in fin_q]
# 分红（2021-2025，A+H 全体股东）
div_years=[str(d["报告期"]).replace("年","") for d in fin_div]
div_ps=[fnum(d["全年每股分红(元)"]) for d in fin_div]
div_payout=[fnum(d["分红比例(%)"]) for d in fin_div]
div_amt=[fnum(d["全年现金分红总额(亿元,A+H)"]) for d in fin_div]
# 成本结构（集装箱航运业务，2021-2025，来源：财报核心数据.xlsx 成本结构表）
fin_cost = sheet_to_dicts("成本结构(集装箱航运业务)")
cost_years=[str(d["报告期"]).replace("年","") for d in fin_cost]
cost_total=[fnum(d["集装箱航运业务成本(亿元)"]) for d in fin_cost]
cost_equip=[fnum(d["设备及货物运输成本(亿元)"]) for d in fin_cost]
cost_voyage=[fnum(d["航程成本(含燃油,亿元)"]) for d in fin_cost]
cost_vessel=[fnum(d["船舶成本(含租船,亿元)"]) for d in fin_cost]
cost_other=[fnum(d["其他业务成本(亿元)"]) for d in fin_cost]
cost_perbox=[fnum(d["航线单箱成本(美元/TEU)"]) for d in fin_cost]
cost_vol=[fnum(d["货运量(万TEU)"]) for d in fin_cost]
# 燃油费/租船费估算：财报核心数据.xlsx · 成本结构(集装箱航运业务) 已单列 2021–2025 列，直接读取（列名无 (2025) 后缀）
cost_fuel=[fnum(d["燃油费估算(亿元)"]) for d in fin_cost]
cost_charter=[fnum(d["租船费估算(亿元)"]) for d in fin_cost]
# 港口码头业务（2021-2025，来源：财报核心数据.xlsx 港口码头业务表）
fin_port = sheet_to_dicts("港口码头业务")
port_years=[str(d["报告期"]).replace("年","") for d in fin_port]
port_rev=[fnum(d["码头业务收入(亿元)"]) for d in fin_port]
port_cost=[fnum(d["码头业务成本(亿元)"]) for d in fin_port]
port_gm=[fnum(d["码头业务毛利率(%)"]) for d in fin_port]
port_gp=[fnum(d["码头业务毛利(亿元)"]) for d in fin_port]
port_thru=[fnum(d["码头总吞吐量(万TEU)"]) for d in fin_port]
port_share=[fnum(d["营收占比(%)"]) for d in fin_port]

# ---------- 计算最新快照值（供卡片文本） ----------
def pct(x, d=1): return f"{x*100:.{d}f}%"

# 航线结构占比（集装箱航运业务，分航线箱量与收入，2021–2025 全年，来源：中远海控_货运量与航线结构数据.xlsx）
ROUTE_XLSX = os.path.join(SRC, "中远海控_货运量与航线结构数据.xlsx")
_rows = [list(r) for r in openpyxl.load_workbook(ROUTE_XLSX, read_only=True, data_only=True)
         ["分航线箱量与收入明细"].iter_rows(values_only=True)]
ROUTE_FY = ["2021", "2022", "2023", "2024", "2025"]
ROUTE_SHORT = {"跨太平洋 (美线)": "美线", "亚欧 (欧地线)": "欧地线",
               "亚洲区域内 (近洋线)": "近洋线", "中国大陆 (内贸线)": "内贸线",
               "其它国际 (南北线等)": "其它国际"}
ROUTE_NAMES = ["美线", "欧地线", "近洋线", "内贸线", "其它国际"]
_yby = {}  # year -> list of (short_name, vol, rev_rmb)
for rec in _rows[1:]:
    name, period, vol, vol_yoy, rev, rev_usd, pb_u, pb_r = rec
    if not str(period).strip().endswith("FY"):
        continue
    if name not in ROUTE_SHORT:
        continue
    _yby.setdefault(str(period).replace("FY", "").strip(), []).append(
        (ROUTE_SHORT[name], float(vol or 0), float(rev or 0)))
route_vol = {nm: [] for nm in ROUTE_NAMES}
route_rev = {nm: [] for nm in ROUTE_NAMES}
for _yr in ROUTE_FY:
    _recs = _yby.get(_yr, [])
    _tv = sum(r[1] for r in _recs); _tr = sum(r[2] for r in _recs)
    for nm in ROUTE_NAMES:
        _v = next((r[1] for r in _recs if r[0] == nm), 0)
        _r = next((r[2] for r in _recs if r[0] == nm), 0)
        route_vol[nm].append(round(_v, 1)); route_rev[nm].append(round(_r, 1))
route_vshare = {nm: [round(route_vol[nm][i] / sum(route_vol[n][i] for n in ROUTE_NAMES) * 100, 1)
                     for i in range(len(ROUTE_FY))] for nm in ROUTE_NAMES}
route_rshare = {nm: [round(route_rev[nm][i] / sum(route_rev[n][i] for n in ROUTE_NAMES) * 100, 1)
                     for i in range(len(ROUTE_FY))] for nm in ROUTE_NAMES}
ROUTE = {"years": ROUTE_FY, "routes": ROUTE_NAMES,
         "vol": route_vol, "rev": route_rev,
         "vol_share": route_vshare, "rev_share": route_rshare}
# 2025 货运量份额降序摘要（卡片展示用）
_route_mix25 = sorted(((nm, route_vshare[nm][-1]) for nm in ROUTE_NAMES), key=lambda x: -x[1])
route_mix25 = "/".join(f"{nm}{s:.0f}%" for nm, s in _route_mix25)

VALUES = {
    "scfi": f"{scfi[-1]:.2f}", "scfi_chg": pct(scfi_w[-1]), "scfi_dir": "up" if scfi_w[-1]>=0 else "down",
    "ccfi": f"{ccfi[-1]:.2f}", "ccfi_chg": pct(ccfi_w[-1]), "ccfi_dir": "up" if ccfi_w[-1]>=0 else "down",
    "eu": f"{eu[-1]:.0f}", "med": f"{med[-1]:.0f}", "usw": f"{usw[-1]:.0f}",
    "use": f"{use[-1]:.0f}", "gulf": f"{gulf[-1]:.0f}",
    "util": f"{util[-1]:.0f}%",
    "thru": (f"{thru[-1]:.0f} 万TEU" if thru[-1] is not None else "待更新"),
    "thru_yoy": (pct(thru_y[-1]) if thru_y[-1] is not None else "待更新"),
    "thru_dir": ("up" if thru_y[-1] >= 0 else "down") if thru_y[-1] is not None else "flat",
    "exp": f"{exp[-1]:.0f} 亿美元", "exp_yoy": pct(exp_y[-1]), "exp_dir":"up",
    "asean": pct(asean_y[-1]), "eu_yoy": pct(eu_y[-1]), "us_yoy": pct(us_y[-1]),
    "export_yoy_detail": f"总出口{pct(exp_y[-1])}/东盟{pct(asean_y[-1])}/欧盟{pct(eu_y[-1])}/美国{pct(us_y[-1])}",
    "fleet": f"{fleet[-1]:.0f} 万TEU", "fleet_yoy": pct(fleet_y[-1]), "fleet_dir":"up",
    "idle": pct(idle_r[-1],2), "order": pct(order[-1],1),
    "blank_us": pct(blank_us[-1],1), "blank_eu": pct(blank_eu[-1],1),
    # 财务核心指标（来源：财报核心数据.xlsx）
    "fin_rev25": f"{fin_rev_a[-1]:.1f}亿",
    "fin_np25": f"{fin_np_a[-1]:.1f}亿",
    "fin_np25_chg": ("%.2f%%" % ((fin_np_a[-1]/fin_np_a[-2]-1)*100)),
    "fin_np_q1": f"{fnum(fin_q[-1]['归母净利润(亿元)']):.1f}亿",
    "fin_np_q1_chg": ("%.2f%%" % fnum(fin_q[-1]["归母同比(%)"])),
    "fin_gm25": f"{fin_gm_a[-1]:.1f}%",
    "fin_ocf25": f"{fnum(fin_a[-1]['经营现金流(亿元)']):.1f}亿",
    "fin_dar25": f"{fnum(fin_a[-1]['资产负债率(%)']):.1f}%",
    "fin_roe25": f"{fin_roe_a[-1]:.1f}%",
    "fin_eps25": f"{fnum(fin_a[-1]['基本EPS(元)']):.2f}元",
    # 股东回报（分红来源：财报核心数据.xlsx；回购来源：中远海控_回购明细.xlsx）
    "div_payout25": f"{div_payout[-1]:.1f}%",
    "div_ps25": f"{div_ps[-1]:.2f}元",
    "div_amt25": f"{div_amt[-1]:.1f}亿",
    "bb_a5_shares": "2911.65万股",
    "bb_a5_amt": "4.22亿",
    "bb_a5_cap": "15.4亿",
    "bb_h_ytd": "4489.35万股",
    "bb_h_ytd_amt": "6.66亿港元",
    # 成本结构（来源：财报核心数据.xlsx 成本结构表）
    "cost_perbox25": f"{cost_perbox[-1]:.0f} 美元/TEU",
    "cost_perbox_yoy": ("%.1f%%" % ((cost_perbox[-1]/cost_perbox[-2]-1)*100)),
    "cost_total25": f"{cost_total[-1]:.0f} 亿",
    "cost_fuel25": (f"{cost_fuel[-1]:.1f} 亿" if cost_fuel[-1] else "待更新"),
    "cost_charter25": (f"{cost_charter[-1]:.1f} 亿" if cost_charter[-1] else "待更新"),
    # 航线结构占比（来源：中远海控_货运量与航线结构数据.xlsx 分航线箱量与收入明细）
    "route_year": "2025",
    "route_mix25": route_mix25,
    # 季度航运货运量（来源：中远海控_货运量与航线结构数据.xlsx 季度货运量明细(2021-)）
    "qvol25": f"{qvol[-1]:.2f}",
    "qvol_chg": ("+%.2f%%" if qvol_yoy[-1]>=0 else "%.2f%%") % (qvol_yoy[-1]*100),
    "qvol_dir": "up" if qvol_yoy[-1]>=0 else "down",
    "qvol_cum25": f"{qvol_cum[-1]:.2f} 万TEU",
    "qvol_q": qvol_dates[-1],
    # 港口码头业务（来源：财报核心数据.xlsx 港口码头业务表）
    "port_rev25": f"{port_rev[-1]:.1f}亿",
    "port_rev_yoy": ("%.1f%%" % ((port_rev[-1]/port_rev[-2]-1)*100)),
    "port_gm25": f"{port_gm[-1]:.1f}%",
    "port_thru25": f"{port_thru[-1]:.0f}万TEU",
    "port_thru_yoy": ("%.1f%%" % ((port_thru[-1]/port_thru[-2]-1)*100)),
    "port_share25": f"{port_share[-1]:.1f}%",
    # 宏观与政策环境（维度7）：6 项核心数据，数据源 中远海控_宏观与政策环境数据.xlsx（公开数据近似）
    "macro_fuel25": f"{m_fuel[-1]:g} $/mt",
    "macro_charter25": f"{m_charter[-1]:.0f}",
    "macro_ets25": f"{m_ets[-1]:.0f} €/t",
    "macro_redsea_ratio25": f"{m_redsea_ratio[-1]:.0f}%",
    "macro_redsea_absorb25": f"{m_redsea_absorb[-1]:.0f}%",
    "macro_pmi25": f"美制{_m_us_manuf[-1]:.1f}/美服{_m_us_serv[-1]:.1f}/欧制{_m_eu_manuf[-1]:.1f}/欧服{_m_eu_serv[-1]:.1f}",
}
# 红涨绿跌（A股惯例）：数值上行=红，下行=绿
for k in ("thru_dir","exp_dir","fleet_dir"):
    pass

# ---------- 趋势图生成（matplotlib → base64） ----------
def fig_to_b64(fig):
    buf=io.BytesIO(); fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                                  facecolor="#ffffff"); plt.close(fig)
    return "data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()

def style_ax(ax):
    ax.grid(True, ls="--", lw=0.5, color="#e3e8ee")
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.tick_params(colors="#1f2733")

CHARTS={}
step=max(1,len(fr_dates)//8)

# C1/C2 七张 SVG 直接复用主源 周运价指数(SCFI&CCFI) 已提取的 fr_dates/scfi/ccfi/eu/med/usw/use/gulf
# （周报文件为此 sheet 的复本，已删除；统一单源避免双写漂移）

def _nice_ceil(v):
    if v <= 0: return 1
    p = 10 ** math.floor(math.log10(v))
    for s in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= s*p: return s*p
    return 10*p

def _fmt_axis(v):
    if v == 0: return "0"
    a = abs(v)
    if a >= 1000: return f"{v:,.0f}"
    if a >= 100: return f"{v:.0f}"
    return f"{v:.1f}"

def make_weekly_svg(title, unit, labels, values, color, W=780, H=300):
    """周度折线图 SVG（浅色主题，x 轴稀疏标周、最新值与峰值标注）。"""
    padL, padR, padT, padB = 54, 18, 40, 42
    plotW = W - padL - padR
    plotH = H - padT - padB
    xs, xf = padL, W - padR
    ys, yf = padT, H - padB
    vs = [v for v in values if isinstance(v, (int, float))]
    if not vs: return ""
    vmax, vmin = max(vs), min(vs)
    ylo = 0.0 if vmin >= 0 else vmin * 1.02
    yhi = float(_nice_ceil(vmax))
    if yhi == ylo: yhi = ylo + 1
    n = len(values)
    def X(i): return xs + (plotW * (i / (n - 1)) if n > 1 else plotW / 2)
    def Y(v): return ys + plotH * (1 - (v - ylo) / (yhi - ylo))
    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('<text x="%d" y="19" fill="#1f2733" font-size="14" font-weight="700">%s</text>' % (padL, title))
    o.append('<text x="%d" y="34" fill="#9aa6b2" font-size="10">单位：%s · 样本 %d 周 · %s ~ %s · 数据源：中远海控_行业供需与运价数据.xlsx · 周运价指数(SCFI&CCFI)</text>' % (padL, unit, n, labels[0], labels[-1]))
    for g in range(5):
        val = ylo + (yhi - ylo) * g / 4
        gy = Y(val)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (xs, gy, xf, gy))
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="10" text-anchor="end">%s</text>' % (xs - 6, gy + 3.5, _fmt_axis(val)))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (xs, yf, xf, yf))
    xstep = max(1, math.ceil(n / 8))
    for i, lb in enumerate(labels):
        if i % xstep == 0 or i == n - 1:
            o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (X(i), ys, X(i), yf))
            o.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="9.5" text-anchor="middle">%s</text>' % (X(i), H - 16, lb[5:]))
    d = ""
    for i, v in enumerate(values):
        if v is None: continue
        d += ("L" if d else "M") + "%.1f %.1f " % (X(i), Y(v))
    if d:
        o.append('<path d="%s" fill="none" stroke="%s" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>' % (d, color))
    for i, v in enumerate(values):
        if v is None: continue
        o.append('<circle cx="%.1f" cy="%.1f" r="2.6" fill="%s"/>' % (X(i), Y(v), color))
    last_i = n - 1
    lv = values[last_i]
    if lv is not None:
        o.append('<text x="%.1f" y="%.1f" fill="%s" font-size="11" font-weight="700" text-anchor="end">%.2f</text>' % (X(last_i) - 4, Y(lv) - 8, color, lv))
    imax = max(range(n), key=lambda i: values[i] if values[i] is not None else -1e18)
    if imax != last_i:
        o.append('<text x="%.1f" y="%.1f" fill="#1f2733" font-size="10" text-anchor="middle">%.2f</text>' % (X(imax), Y(values[imax]) - 8, values[imax]))
    o.append('</svg>')
    return "".join(o)

def make_util_svg(title, unit, labels, values, color, ylo=70, yhi=105, W=780, H=300):
    """舱位利用率（周度）折线 SVG（浅色主题，复刻 matplotlib 原图：固定 y 轴 70–105、稀疏标周 MM-DD、无逐点值标签）。"""
    padL, padR, padT, padB = 54, 18, 40, 42
    plotW = W - padL - padR; plotH = H - padT - padB
    xs, xf = padL, W - padR; ys, yf = padT, H - padB
    vs = [v for v in values if isinstance(v, (int, float))]
    if not vs: return ""
    n = len(values)
    def X(i): return xs + (plotW * (i / (n - 1)) if n > 1 else plotW / 2)
    def Y(v): return ys + plotH * (1 - (v - ylo) / (yhi - ylo))
    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('<text x="%d" y="19" fill="#1f2733" font-size="14" font-weight="700">%s</text>' % (padL, title))
    o.append('<text x="%d" y="34" fill="#9aa6b2" font-size="10">单位：%s · 样本 %d 周 · %s ~ %s · 数据源：中远海控_行业供需与运价数据.xlsx · 周运价指数(SCFI&amp;CCFI)</text>' % (padL, unit, n, labels[0], labels[-1]))
    T = 5
    for g in range(T + 1):
        val = ylo + (yhi - ylo) * g / T
        gy = Y(val)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (xs, gy, xf, gy))
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="10" text-anchor="end">%s</text>' % (xs - 6, gy + 3.5, _fmt_axis(val)))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (xs, yf, xf, yf))
    xstep = max(1, math.ceil(n / 8))
    for i, lb in enumerate(labels):
        if i % xstep == 0 or i == n - 1:
            o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (X(i), ys, X(i), yf))
            o.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="9.5" text-anchor="middle">%s</text>' % (X(i), H - 16, lb[5:]))
    d = ""
    for i, v in enumerate(values):
        if v is None: continue
        d += ("L" if d else "M") + "%.1f %.1f " % (X(i), Y(v))
    if d:
        o.append('<path d="%s" fill="none" stroke="%s" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' % (d, color))
    for i, v in enumerate(values):
        if v is None: continue
        o.append('<circle cx="%.1f" cy="%.1f" r="2.4" fill="%s"/>' % (X(i), Y(v), color))
    o.append('</svg>')
    return "".join(o)

def make_demand_yoy_svg(dates, series, ylo=-0.20, yhi=0.30, W=780, H=340):
    """分区域出口同比增速（月频）多线 SVG（浅色主题，复刻 matplotlib 原图：4 色折线、零基准、顶部横排图例、x 轴月份标签斜排）。"""
    padL, padR, padT, padB = 52, 18, 40, 90
    plotW = W - padL - padR; plotH = H - padT - padB
    xs, xf = padL, W - padR; ys, yf = padT, H - padB
    n = len(dates)
    if n == 0: return ""
    def X(i): return xs + (plotW * (i / (n - 1)) if n > 1 else plotW / 2)
    def Y(v): return ys + plotH * (1 - (v - ylo) / (yhi - ylo))
    def yfmt(v): return "0%" if abs(v) < 1e-9 else "%+.0f%%" % (v * 100)
    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('<text x="%d" y="19" fill="#1f2733" font-size="14" font-weight="700">分区域出口同比增速（月频）</text>' % padL)
    o.append('<text x="%d" y="34" fill="#9aa6b2" font-size="10">单位：%% · 样本 %d 期 · %s ~ %s · 数据源：中远海控_行业供需与运价数据.xlsx · 需求端-港口吞吐量&amp;出口</text>' % (padL, n, dates[0], dates[-1]))
    T = 5
    for g in range(T + 1):
        val = ylo + (yhi - ylo) * g / T
        gy = Y(val)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (xs, gy, xf, gy))
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="10" text-anchor="end">%s</text>' % (xs - 6, gy + 3.5, yfmt(val)))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (xs, yf, xf, yf))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#bbb" stroke-width="0.8"/>' % (xs, Y(0), xf, Y(0)))
    # x 轴月份标签（斜排，复刻 matplotlib rotation=40 ha=right；整体上移避免底部裁剪）
    yBot = H - 28
    for i, lb in enumerate(dates):
        o.append('<text x="%.1f" y="%d" transform="rotate(-40 %.1f %d)" fill="#1f2733" font-size="8" text-anchor="end">%s</text>' % (X(i), yBot, X(i), yBot, lb))
    # 4 条折线（无逐点标记，与原图一致）
    for vals, col, lab in series:
        d = ""
        for i, v in enumerate(vals):
            if v is None: continue
            d += ("L" if d else "M") + "%.1f %.1f " % (X(i), Y(v))
        if d:
            o.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>' % (d, col))
    # 顶部横排图例
    ly = ys + 13
    lx = xs + 2
    for vals, col, lab in series:
        o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.8"/>' % (lx, ly, lx + 16, ly, col))
        o.append('<text x="%d" y="%d" fill="#1f2733" font-size="9">%s</text>' % (lx + 21, ly + 3, lab))
        lx += 70
    o.append('</svg>')
    return "".join(o)

def make_fin_svg(key, title, unit, a_lbl, a_val, q_lbl, q_val, color, avfmt, qvfmt, has_q=True, W=780, H=320, view="annual"):
    """财务单指标 SVG：年度视图(view='annual') 或 季度视图(view='quarterly') 单图，浅色主题。
    has_q=False 时季度视图显示占位文字（该指标仅披露年度数据）。"""
    padL, padR, padT, padB = 54, 16, 40, 42
    plotW = W - padL - padR; plotH = H - padT - padB
    xs, xf = padL, W - padR; ys, yf = padT, H - padB
    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('<text x="%d" y="20" fill="#1f2733" font-size="14" font-weight="700">%s</text>' % (padL, title))
    if view == "annual":
        sub = '单位：%s · 数据源：中远海控_财报核心数据.xlsx · 年度核心数据' % unit
    else:
        sub = '单位：%s · 数据源：中远海控_财报核心数据.xlsx · 季度核心数据 · 当季单季还原' % unit
    o.append('<text x="%d" y="35" fill="#9aa6b2" font-size="10">%s</text>' % (padL, sub))

    def _draw(gid, gcls, labels, vals, vfmt, xq):
        g = ['<g class="%s" id="%s">' % (gcls, gid)]
        vs = [v for v in vals if isinstance(v, (int, float))]
        if not vs:
            g.append('<text x="%d" y="%d" fill="#9aa6b2" font-size="12" text-anchor="middle">无数据</text>' % (W // 2, (ys + yf) // 2)); g.append('</g>'); return g
        vmax, vmin = max(vs), min(vs)
        span = (vmax - vmin) or 1
        ylo = vmin - span * 0.15; yhi = vmax + span * 0.15
        if ylo == yhi: ylo = yhi - 1; yhi = yhi + 1
        n = len(vals)
        def X(i): return xs + plotW * (i / (n - 1) if n > 1 else 0.5)
        def Y(v): return ys + plotH * (1 - (v - ylo) / (yhi - ylo))
        for t in range(6):
            val = ylo + (yhi - ylo) * t / 5; gy = Y(val)
            g.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (xs, gy, xf, gy))
            g.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="9" text-anchor="end">%s</text>' % (xs - 6, gy + 3.2, vfmt(val)))
        g.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (xs, yf, xf, yf))
        if xq:
            for i, lb in enumerate(labels):
                if lb.endswith("Q1"):
                    gx = X(i)
                    g.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#f1f4f7" stroke-width="1"/>' % (gx, ys, gx, yf))
                    g.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="8.5" text-anchor="middle">%s</text>' % (gx, H - 16, lb[:4]))
            gx = X(n - 1)
            g.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="8.5" text-anchor="middle">%s</text>' % (gx, H - 16, labels[-1][:4]))
        else:
            for i, lb in enumerate(labels):
                gx = X(i)
                g.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef2f6" stroke-width="1"/>' % (gx, ys, gx, yf))
                g.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="9" text-anchor="middle">%s</text>' % (gx, H - 16, lb))
        d = ""
        for i, v in enumerate(vals):
            if v is None: continue
            d += ("L" if d else "M") + "%.1f %.1f " % (X(i), Y(v))
        if d: g.append('<path d="%s" fill="none" stroke="%s" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' % (d, color))
        for i, v in enumerate(vals):
            if v is None: continue
            g.append('<circle cx="%.1f" cy="%.1f" r="2.8" fill="%s"/>' % (X(i), Y(v), color))
            if (not xq) or labels[i].endswith("Q1"):
                g.append('<text x="%.1f" y="%.1f" fill="%s" font-size="8.5" text-anchor="middle">%s</text>' % (X(i), Y(v) - 7, color, vfmt(v)))
        g.append('</g>')
        return g

    if view == "annual":
        o += _draw("%s-annual" % key, "fin-a", a_lbl, a_val, avfmt, False)
    else:
        if has_q:
            o += _draw("%s-q" % key, "fin-q", q_lbl, q_val, qvfmt, True)
        else:
            o.append('<g class="fin-q" id="%s-q">' % key)
            o.append('<text x="%d" y="%d" fill="#9aa6b2" font-size="13" text-anchor="middle">该指标仅披露年度数据</text>' % (W // 2, (ys + yf) // 2))
            o.append('</g>')
    o.append('</svg>')
    return "".join(o)

def make_multi_line_svg(title, unit, labels, series, colors, vfmt=None, W=780, H=330,
                        src_note=None, ptype="年", hline=None):
    """多序列折线 SVG（浅色主题，顶部图例、自动 y 轴、网格、可选参考横线）。
    series=[(name, values), ...] 与 colors 等长；hline=(value, label) 如 PMI 荣枯线 (50,"荣枯线 50")。
    多序列不画逐点数值标签（避免拥挤），由 y 轴刻度 + 图例 + 底部数据表读取。"""
    if vfmt is None: vfmt=lambda v:f"{v:.1f}"
    if src_note is None: src_note = "中远海控_宏观与政策环境数据.xlsx"
    padL, padR, padT, padB = 54, 18, 60, 48
    plotW = W - padL - padR; plotH = H - padT - padB
    xs, xf = padL, W - padR; ys, yf = padT, H - padB
    allv = [v for _, vals in series for v in vals if isinstance(v, (int, float))]
    if not allv: return ""
    n = len(labels)
    vmax, vmin = max(allv), min(allv)
    if hline is not None:
        vmax = max(vmax, hline[0]); vmin = min(vmin, hline[0])
    span = (vmax - vmin) or 1
    ylo = vmin - span * 0.12; yhi = vmax + span * 0.12
    if ylo == yhi: ylo -= 1; yhi += 1
    def X(i): return xs + (plotW * (i / (n - 1)) if n > 1 else plotW / 2)
    def Y(v): return ys + plotH * (1 - (v - ylo) / (yhi - ylo))
    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('<text x="%d" y="19" fill="#1f2733" font-size="14" font-weight="700">%s</text>' % (padL, title))
    o.append('<text x="%d" y="34" fill="#9aa6b2" font-size="10">单位：%s · 样本 %d %s · %s ~ %s · 数据源：%s</text>' % (padL, unit, n, ptype, labels[0], labels[-1], src_note))
    # 图例（顶部一行）
    step = min(170, plotW // max(1, len(series)))
    for i, (nm, _) in enumerate(series):
        lx = padL + i * step
        o.append('<circle cx="%.1f" cy="45" r="4" fill="%s"/>' % (lx, colors[i]))
        o.append('<text x="%.1f" y="49" fill="#1f2733" font-size="10.5">%s</text>' % (lx + 8, nm))
    # 横向网格 + y 刻度
    T = 5
    for g in range(T + 1):
        val = ylo + (yhi - ylo) * g / T; gy = Y(val)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (xs, gy, xf, gy))
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="10" text-anchor="end">%s</text>' % (xs - 6, gy + 3.5, vfmt(val)))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (xs, yf, xf, yf))
    # 参考横线（如 PMI 荣枯线 50）
    if hline is not None:
        gy = Y(hline[0])
        o.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#9aa6b2" stroke-width="1" stroke-dasharray="4 3"/>' % (xs, gy, xf, gy))
        if len(hline) > 1 and hline[1]:
            o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="9.5" text-anchor="end">%s</text>' % (xf - 2, gy - 4, hline[1]))
    # 纵向网格 + x 标签
    for i, lbx in enumerate(labels):
        anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
        lx = X(i) + (4 if i == 0 else (-4 if i == n - 1 else 0))
        o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef2f6" stroke-width="1"/>' % (X(i), ys, X(i), yf))
        o.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="8.5" text-anchor="%s">%s</text>' % (lx, H - 16, anchor, lbx))
    # 数据线 + 数据点
    for idx, (nm, vals) in enumerate(series):
        c = colors[idx]; d = ""
        for i, v in enumerate(vals):
            if v is None: continue
            d += ("L" if d else "M") + "%.1f %.1f " % (X(i), Y(v))
        if d:
            o.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"/>' % (d, c))
        for i, v in enumerate(vals):
            if v is None: continue
            o.append('<circle cx="%.1f" cy="%.1f" r="2.6" fill="%s"/>' % (X(i), Y(v), c))
    o.append('</svg>')
    return "".join(o)

def make_monthly_yoy_svg(title, unit, labels, values, color_now, color_prev="#9aa6b2", W=780, H=300):
    """月度同比对比折线图：按年分组，每年一条线，x 轴固定为 1–12 月。"""
    padL, padR, padT, padB = 54, 18, 56, 42
    plotW = W - padL - padR
    plotH = H - padT - padB
    xs, xf = padL, W - padR
    ys, yf = padT, H - padB
    groups = {}
    for lb, v in zip(labels, values):
        if v is None: continue
        try:
            yy = int(str(lb)[:4]); mm = int(str(lb)[5:7])
        except (ValueError, IndexError):
            continue
        groups.setdefault(yy, {})[mm] = v
    if not groups: return ""
    years = sorted(groups.keys())
    ymax = max(years)
    vs = [v for g in groups.values() for v in g.values() if isinstance(v, (int, float))]
    vmax, vmin = max(vs), min(vs)
    ylo = 0.0 if vmin >= 0 else vmin * 1.02
    yhi = float(_nice_ceil(vmax))
    if yhi == ylo: yhi = ylo + 1
    def X(m): return xs + plotW * ((m - 1) / 11.0)
    def Y(v): return ys + plotH * (1 - (v - ylo) / (yhi - ylo))
    o = ['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">' % (W, H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    o.append('<text x="%d" y="19" fill="#1f2733" font-size="14" font-weight="700">%s</text>' % (padL, title))
    o.append('<text x="%d" y="34" fill="#9aa6b2" font-size="10">单位：%s · 月度同比（x 轴=1–12 月）· 数据源：中远海控_行业供需与运价数据.xlsx · 需求端-港口吞吐量&amp;出口</text>' % (padL, unit))
    for g in range(5):
        val = ylo + (yhi - ylo) * g / 4
        gy = Y(val)
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>' % (xs, gy, xf, gy))
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="10" text-anchor="end">%s</text>' % (xs - 6, gy + 3.5, _fmt_axis(val)))
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>' % (xs, yf, xf, yf))
    for m in range(1, 13):
        gx = X(m)
        o.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#eef2f6" stroke-width="1"/>' % (gx, ys, gx, yf))
        o.append('<text x="%.1f" y="%d" fill="#7a8694" font-size="8.5" text-anchor="middle">%d</text>' % (gx, H - 14, m))
    for yy in years:
        col = color_now if yy == ymax else color_prev
        pts = [(m, groups[yy][m]) for m in sorted(groups[yy])]
        d = ""
        for i, (m, v) in enumerate(pts):
            d += ("L" if d else "M") + "%.1f %.1f " % (X(m), Y(v))
        if d:
            o.append('<path d="%s" fill="none" stroke="%s" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>' % (d, col))
        for m, v in pts:
            o.append('<circle cx="%.1f" cy="%.1f" r="2.6" fill="%s"/>' % (X(m), Y(v), col))
        m, v = pts[-1]
        anchor = "end" if m == 12 else "middle"
        dx = X(m) - 5 if m == 12 else X(m)
        o.append('<text x="%.1f" y="%.1f" fill="%s" font-size="10" font-weight="700" text-anchor="%s">%d %s</text>' % (dx, Y(v) - 9, col, anchor, yy, _fmt_axis(v)))
    lx = padL
    for yy in years:
        col = color_now if yy == ymax else color_prev
        o.append('<circle cx="%d" cy="%d" r="3.2" fill="%s"/>' % (lx, 47, col))
        o.append('<text x="%d" y="%d" fill="#1f2733" font-size="10">%d</text>' % (lx + 8, 50, yy))
        lx += 42
    o.append('</svg>')
    return "".join(o)

def make_qvol_svg(dates, yoy, vol, W=780, H=390):
    """季度航运货运量组合图（复刻 matplotlib 原图）：左轴 货运量同比% 柱状（红涨绿跌 alpha0.2），
    右轴 单季货运量(万TEU) 红色折线（圆点+值标签），x 轴季度标签竖排，双轴标题，双图例。"""
    C_RED="#c8102e"; C_GRN="#2e9e6b"
    padL, padR, padT, padB = 50, 50, 42, 58
    plotW = W - padL - padR; plotH = H - padT - padB
    xs, xf = padL, W - padR; ys, yf = padT, H - padB
    n = len(dates)
    if n == 0: return ""
    yv = [v for v in yoy if isinstance(v,(int,float))]
    ylo_y = min(0.0, min(yv)); yhi_y = max(0.0, max(yv)); span = (yhi_y - ylo_y) or 1
    ylo_y -= span*0.12; yhi_y += span*0.12
    vmin, vmax = min(vol), max(vol)
    ylo_v = vmin*0.92; yhi_v = vmax*1.08   # 与原 matplotlib twinx ylim 一致
    def Xc(i): return xs + plotW*(i+0.5)/n
    def Yy(v): return ys + plotH*(1-(v-ylo_y)/(yhi_y-ylo_y))
    def Yv(v): return ys + plotH*(1-(v-ylo_v)/(yhi_v-ylo_v))
    bar_w = 0.6*plotW/n
    o=['<svg viewBox="0 0 %d %d" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system,Segoe UI,Microsoft YaHei,sans-serif">'%(W,H)]
    o.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>'%(W,H))
    o.append('<text x="%d" y="22" fill="#1f2733" font-size="14" font-weight="700">季度航运货运量（单季，%s–%s）</text>'%(padL, dates[0], dates[-1]))
    # 水平网格（5 段）+ 左轴(同比%)刻度 + 右轴(万TEU)刻度（同一像素行）
    T=5
    for g in range(T+1):
        gy = ys + plotH*g/T
        o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eef2f6" stroke-width="1"/>'%(xs,gy,xf,gy))
        vy = ylo_y + (yhi_y-ylo_y)*g/T
        o.append('<text x="%d" y="%.1f" fill="#7a8694" font-size="9" text-anchor="end">%s</text>'%(xs-6, gy+3, ("%+.0f%%"%(vy*100)) ))
        vv = ylo_v + (yhi_v-ylo_v)*g/T
        o.append('<text x="%d" y="%.1f" fill="%s" font-size="9" text-anchor="start">%s</text>'%(xf+6, gy+3, C_RED, ("%d"%round(vv))))
    # x 轴线
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#c3ccd6" stroke-width="1"/>'%(xs,yf,xf,yf))
    # 零基准线（灰）
    o.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#bbb" stroke-width="0.8"/>'%(xs,Yy(0),xf,Yy(0)))
    # 柱状（同比%，红涨绿跌 alpha0.2）
    for i,v in enumerate(yoy):
        cx=Xc(i); col=C_RED if v>=0 else C_GRN
        y0=Yy(0); y1=Yy(v); top=min(y0,y1); h=abs(y1-y0)
        o.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" fill-opacity="0.20"/>'%(cx-bar_w/2, top, bar_w, h, col))
    # 折线（万TEU，红，圆点+值标签）
    d=""
    for i,v in enumerate(vol):
        d+=("L" if d else "M")+"%.1f %.1f "%(Xc(i),Yv(v))
    o.append('<path d="%s" fill="none" stroke="%s" stroke-width="1.9" stroke-linejoin="round" stroke-linecap="round"/>'%(d,C_RED))
    for i,v in enumerate(vol):
        o.append('<circle cx="%.1f" cy="%.1f" r="2.4" fill="%s"/>'%(Xc(i),Yv(v),C_RED))
        o.append('<text x="%.1f" y="%.1f" fill="%s" font-size="7" text-anchor="middle">%d</text>'%(Xc(i),Yv(v)-5,C_RED,round(v)))
    # x 轴季度标签（竖排）
    yBot=H-14
    for i,lb in enumerate(dates):
        cx=Xc(i)
        o.append('<text x="%.1f" y="%d" transform="rotate(-90 %.1f %d)" fill="#1f2733" font-size="6.5" text-anchor="start">%s</text>'%(cx,yBot,cx,yBot,lb))
    # 双轴标题
    cy=(ys+yf)/2
    o.append('<text x="%d" y="%.1f" transform="rotate(-90 %d %.1f)" fill="#7a8694" font-size="10" text-anchor="middle">货运量同比 %%</text>'%(15,cy,15,cy))
    o.append('<text x="%d" y="%.1f" transform="rotate(-90 %d %.1f)" fill="%s" font-size="10" text-anchor="middle">单季货运量(万TEU)</text>'%(W-12,cy,W-12,cy,C_RED))
    # 图例：左=柱状(同比%)，右=折线(万TEU)
    o.append('<rect x="%d" y="%d" width="14" height="9" fill="%s" fill-opacity="0.20"/>'%(xs+6, ys+6, C_RED))
    o.append('<text x="%d" y="%d" fill="#1f2733" font-size="8">货运量同比(%%)</text>'%(xs+24, ys+13))
    lx=xf-150
    o.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.9"/>'%(lx,ys+10,lx+16,ys+10,C_RED))
    o.append('<circle cx="%.1f" cy="%d" r="2.4" fill="%s"/>'%(lx+8,ys+10,C_RED))
    o.append('<text x="%d" y="%d" fill="#1f2733" font-size="8">单季货运量(万TEU)</text>'%(lx+22, ys+13))
    o.append('</svg>')
    return "".join(o)

# C1 运价指数：SCFI / CCFI 各自独立 SVG（数据源：主源 周运价指数(SCFI&CCFI)）
CHARTS["scfi"] = make_weekly_svg("SCFI 综合指数（2026 周度）", "指数点", fr_dates, scfi, C_SCFI)
CHARTS["ccfi"] = make_weekly_svg("CCFI 综合指数（2026 周度）", "指数点", fr_dates, ccfi, C_CCFI)

# C2 主力航线即期运价：五航线各自独立 SVG（数据源：主源 周运价指数(SCFI&CCFI)）
CHARTS["route_eu"]   = make_weekly_svg("欧洲航线即期运价（2026 周度）",   "USD/TEU", fr_dates, eu,   C_EU)
CHARTS["route_med"]  = make_weekly_svg("地中海航线即期运价（2026 周度）", "USD/TEU", fr_dates, med,  C_MED)
CHARTS["route_usw"]  = make_weekly_svg("美西航线即期运价（2026 周度）",   "USD/FEU", fr_dates, usw,  C_USW)
CHARTS["route_use"]  = make_weekly_svg("美东航线即期运价（2026 周度）",   "USD/FEU", fr_dates, use,  C_USE)
CHARTS["route_gulf"] = make_weekly_svg("波斯湾航线即期运价（2026 周度）", "USD/TEU", fr_dates, gulf, C_GULF)

# C3 舱位利用率：内联 SVG 折线图（复刻 matplotlib，浅色主题）
CHARTS["util"]=make_util_svg("舱位利用率（周度，区间值取中值）", "%", fr_dates, util, C_IDLE)

# C4 需求：全国港口吞吐量（月度同比，独立 SVG）
CHARTS["demand_thru"] = make_monthly_yoy_svg("全国港口吞吐量（月度同比）", "万TEU", de_dates, thru, C_THRU)
# C4b 需求：海关出口总额（月度同比，独立 SVG）
CHARTS["demand_exp"]  = make_monthly_yoy_svg("海关出口总额（月度同比）", "亿美元", de_dates, exp, C_EXP)

# C5 需求：分区域出口同比（内联 SVG 多线图，复刻 matplotlib）
CHARTS["demand_yoy"]=make_demand_yoy_svg(de_dates, [(exp_y,C_TY,"总出口"),(asean_y,C_ASEAN,"东盟"),(eu_y,C_EUY,"欧盟"),(us_y,C_USY,"美国")])

# C6 供给：全球船队运力 / 手持订单占比 / 闲置率 —— 三张内联 SVG 单线图（复刻 matplotlib 双面板，浅色主题）
CHARTS["supply_fleet"]=make_line_svg_wide("全球集装箱船队总运力（季频）", "万TEU", su_dates, fleet, C_FLEET, vfmt=lambda v:f"{v:.0f}")
CHARTS["supply_order"]=make_line_svg_wide("手持订单占运力比例（季频）", "%", su_dates, order, C_ORDER, vfmt=lambda v:f"{v*100:.1f}%")
CHARTS["supply_idle"] =make_line_svg_wide("闲置运力比例（季频）", "%", su_dates, idle_r, C_IDLE, vfmt=lambda v:f"{v*100:.2f}%")

# C7 调控：美线/欧线停航率 —— 两张内联 SVG 单线图（复刻 matplotlib 双线，浅色主题）
CHARTS["control_us"]=make_line_svg_wide("美线停航率（季频）", "%", co_dates, blank_us, "#"+C_BLUS, vfmt=lambda v:f"{v*100:.1f}%")
CHARTS["control_eu"]=make_line_svg_wide("欧线停航率（季频）", "%", co_dates, blank_eu, "#"+C_BLEU, vfmt=lambda v:f"{v*100:.1f}%")

# C8/C9 财务核心指标：7 张内联 SVG（年度+季度双视图 toggle，浅色主题，复刻原 matplotlib 双面板）
# 年度(累计) 视图
CHARTS["fin_rev"] =make_fin_svg("fin_rev","营业收入（亿元）","亿元", fin_years, fin_rev_a, fin_q_lbl, fin_rev_q, "#15616d", lambda v:f"{v:.0f}", lambda v:f"{v:.0f}", has_q=True, view="annual")
CHARTS["fin_np"]  =make_fin_svg("fin_np","归母净利润（亿元）","亿元", fin_years, fin_np_a, fin_q_lbl, fin_np_q, "#c8102e", lambda v:f"{v:.0f}", lambda v:f"{v:.0f}", has_q=True, view="annual")
CHARTS["fin_gm"]  =make_fin_svg("fin_gm","毛利率（%）","%", fin_years, fin_gm_a, fin_q_lbl, fin_gm_q, "#2e9e6b", lambda v:f"{v:.1f}%", lambda v:f"{v:.1f}%", has_q=True, view="annual")
CHARTS["fin_ocf"] =make_fin_svg("fin_ocf","经营现金流（亿元）","亿元", fin_years, fin_ocf_a, fin_q_lbl, None, "#d98a14", lambda v:f"{v:.0f}", lambda v:f"{v:.0f}", has_q=False, view="annual")
CHARTS["fin_dar"] =make_fin_svg("fin_dar","资产负债率（%）","%", fin_years, fin_dar_a, fin_q_lbl, None, "#7a8694", lambda v:f"{v:.1f}%", lambda v:f"{v:.1f}%", has_q=False, view="annual")
CHARTS["fin_roe"] =make_fin_svg("fin_roe","ROE摊薄（%）","%", fin_years, fin_roe_a, fin_q_lbl, None, "#1f7a8c", lambda v:f"{v:.1f}%", lambda v:f"{v:.1f}%", has_q=False, view="annual")
CHARTS["fin_eps"] =make_fin_svg("fin_eps","基本EPS（元）","元", fin_years, fin_eps_a, fin_q_lbl, None, "#c8102e", lambda v:f"{v:.2f}", lambda v:f"{v:.2f}", has_q=False, view="annual")
# 季度(当季单季还原) 视图
CHARTS["fin_rev_q"] =make_fin_svg("fin_rev_q","营业收入（当季，亿元）","亿元", fin_years, fin_rev_a, fin_q_lbl, fin_rev_q, "#15616d", lambda v:f"{v:.0f}", lambda v:f"{v:.0f}", has_q=True, view="quarterly")
CHARTS["fin_np_q"]  =make_fin_svg("fin_np_q","归母净利润（当季，亿元）","亿元", fin_years, fin_np_a, fin_q_lbl, fin_np_q, "#c8102e", lambda v:f"{v:.0f}", lambda v:f"{v:.0f}", has_q=True, view="quarterly")
CHARTS["fin_gm_q"]  =make_fin_svg("fin_gm_q","当季毛利率（%）","%", fin_years, fin_gm_a, fin_q_lbl, fin_gm_q, "#2e9e6b", lambda v:f"{v:.1f}%", lambda v:f"{v:.1f}%", has_q=True, view="quarterly")
# 经营现金流/资产负债率/ROE摊薄/基本EPS 无季度披露，季度图不生成（仅保留年度图）

# C10 分红：全年每股分红(柱) + 分红比例(线)
fig,ax=plt.subplots(figsize=(8.8,3.6))
x=range(len(div_years))
ax.bar(x, div_ps, color="#2e9e6b", alpha=.85, width=.55, label="全年每股分红(元)")
for i,v in enumerate(div_ps): ax.text(i, v+0.03, f"{v:.2f}", ha="center", fontsize=8, color="#2e9e6b")
ax.set_ylabel("全年每股分红(元)", color="#2e9e6b"); ax.tick_params(axis="y", colors="#2e9e6b")
ax.set_xticks(list(x)); ax.set_xticklabels(div_years)
ax2=ax.twinx()
ax2.plot(x, div_payout, color="#c8102e", lw=2.6, marker="o", ms=6, label="分红比例")
for i,v in enumerate(div_payout): ax2.text(i, v+1.2, f"{v:.0f}%", ha="center", fontsize=8, color="#c8102e")
ax2.set_ylabel("分红比例(%)", color="#c8102e"); ax2.tick_params(axis="y", colors="#c8102e")
style_ax(ax); ax.set_title("全年每股分红 & 分红比例（2021–2026）", fontsize=12, weight="bold")
l1,la1=ax.get_legend_handles_labels(); l2,la2=ax2.get_legend_handles_labels()
ax.legend(l1+l2, la1+la2, loc="upper right", frameon=False, fontsize=9)
CHARTS["dividend"]=fig_to_b64(fig)

# C11 成本结构：航线成本分项堆叠柱 + 4 个核心指标单线 SVG（年度水平值，2021–2025）
# 数据源：中远海控_财报核心数据.xlsx · 成本结构(集装箱航运业务)
_CNOTE = "中远海控_财报核心数据.xlsx · 成本结构(集装箱航运业务)"
CHARTS["cost_breakdown"] = make_stacked_bar_svg(
    "成本结构：航线成本分项（年度堆叠）", "亿元", cost_years,
    [("设备及货物运输", cost_equip), ("航程成本(含燃油)", cost_voyage),
     ("船舶成本(含租船)", cost_vessel), ("其他业务成本", cost_other)],
    ["#6ea8cd", "#f2b376", "#8cc69b", "#b39bd8"],
    vfmt=lambda v:f"{v:.0f}", ptype="年", src_note=_CNOTE)
CHARTS["cost_total"]   = make_line_svg_wide("集装箱航运业务成本", "亿元", cost_years, cost_total,   "#c8102e", vfmt=lambda v:f"{v:.0f}", ptype="年", src_note=_CNOTE)
CHARTS["cost_fuel"]    = make_line_svg_wide("燃油费估算", "亿元", cost_years, cost_fuel,    "#d98a14", vfmt=lambda v:f"{v:.1f}", ptype="年", src_note=_CNOTE)
CHARTS["cost_charter"] = make_line_svg_wide("租船费估算", "亿元", cost_years, cost_charter, "#2e9e6b", vfmt=lambda v:f"{v:.1f}", ptype="年", src_note=_CNOTE)
CHARTS["cost_perbox"]  = make_line_svg_wide("航线单箱成本", "$/TEU", cost_years, cost_perbox, "#15616d", vfmt=lambda v:f"{v:.0f}", ptype="年", src_note=_CNOTE)

# C12 航线结构占比：各航线货运量份额（100% 堆叠柱 SVG，2021–2025）
_CMAP = {"美线": "#c8102e", "欧地线": "#15616d", "近洋线": "#2e9e6b", "内贸线": "#d98a14", "其它国际": "#7a8694"}
_ROUTE_NOTE = "中远海控_货运量与航线结构数据.xlsx · 分航线箱量与收入明细"
CHARTS["routemix"] = make_pct_stacked_bar_svg(
    "航线结构占比：各航线货运量份额（年度堆叠）", ROUTE_FY, ROUTE_NAMES,
    route_vshare, [_CMAP[nm] for nm in ROUTE_NAMES], src_note=_ROUTE_NOTE)

# C13 港口码头业务：4 个年度指标各一张内联 SVG 折线图（2021–2025，来源：财报核心数据.xlsx·港口码头业务）
_PNOTE = "中远海控_财报核心数据.xlsx · 港口码头业务"
CHARTS["port_rev"]   = make_line_svg_wide("码头业务收入", "亿元", port_years, port_rev,   "#15616d", vfmt=lambda v:f"{v:.1f}", ptype="年", src_note=_PNOTE)
CHARTS["port_gm"]    = make_line_svg_wide("码头业务毛利率", "%", port_years, port_gm,    "#c8102e", vfmt=lambda v:f"{v:.1f}", ptype="年", src_note=_PNOTE)
CHARTS["port_thru"]  = make_line_svg_wide("码头总吞吐量", "万TEU", port_years, port_thru, "#2e9e6b", vfmt=lambda v:f"{v:.0f}", ptype="年", src_note=_PNOTE)
CHARTS["port_share"] = make_line_svg_wide("码头营收占合并营收", "%", port_years, port_share, "#d98a14", vfmt=lambda v:f"{v:.1f}", ptype="年", src_note=_PNOTE)

# ---------- 维度7 宏观与政策环境：5 项核心数据（2021–2025 年度近似） ----------
# 成本驱动（指数化）: 燃油 / 租船 / EU 碳价；运力与需求（水平值）: 红海绕行 + 欧美PMI
# 数据来源：中远海控_宏观与政策环境数据.xlsx（公开数据近似：Ship&Bunker/Argus、Harper Petersen、EU ETS/EEX、ISM/HCOB PMI）
# MYEARS / m_fuel / m_charter / m_ets / m_redsea_ratio / m_redsea_absorb / m_pmi 已在文件头部由该 xlsx 读取
# 宏观与政策环境：6 项核心数据各出一张内联 SVG
# 数据源：中远海控_宏观与政策环境数据.xlsx · 宏观核心数据(年度)（2021–2025，公开数据近似，非公司披露）
_MNOTE = "中远海控_宏观与政策环境数据.xlsx · 宏观核心数据(年度)"
CHARTS["macro_fuel"]          = make_line_svg_wide("VLSFO 燃油价", "$/mt", MYEARS, m_fuel,           "#c8102e", vfmt=lambda v:f"{v:g}",   ptype="年", src_note=_MNOTE)
CHARTS["macro_charter"]       = make_line_svg_wide("Harpex 租船费率指数", "指数", MYEARS, m_charter, "#d98a14", vfmt=lambda v:f"{v:.0f}", ptype="年", src_note=_MNOTE)
CHARTS["macro_ets"]           = make_line_svg_wide("EU ETS 碳价", "€/t", MYEARS, m_ets,             "#2e9e6b", vfmt=lambda v:f"{v:.0f}", ptype="年", src_note=_MNOTE)
CHARTS["macro_redsea_ratio"]  = make_line_svg_wide("亚欧绕航好望角比例", "%", MYEARS, m_redsea_ratio, "#d84315", vfmt=lambda v:f"{v:.0f}%", ptype="年", src_note=_MNOTE)
CHARTS["macro_redsea_absorb"] = make_line_svg_wide("运力吸收率", "%", MYEARS, m_redsea_absorb,        "#ff8f00", vfmt=lambda v:f"{v:.0f}%", ptype="年", src_note=_MNOTE)
CHARTS["macro_pmi"]           = make_multi_line_svg(
    "欧美制造业/服务业 PMI", "指数", MYEARS,
    [("美制造业", _m_us_manuf), ("美服务业", _m_us_serv),
     ("欧制造业", _m_eu_manuf), ("欧服务业", _m_eu_serv)],
    ["#c8102e", "#d98a14", "#15616d", "#2e9e6b"],
    vfmt=lambda v:f"{v:.1f}", ptype="年",
    src_note="中远海控_宏观与政策环境数据.xlsx · PMI明细(年度)", hline=(50, "荣枯线 50"))

# ---------- 季度航运货运量（单季，2021Q1–2026Q2）：内联 SVG 组合图（复刻 matplotlib） ----------
CHARTS["qvol"]=make_qvol_svg(qvol_dates, qvol_yoy, qvol)

# ---------- 序列化 ----------
SERIES = {
    "fr_dates":fr_dates, "scfi":scfi, "ccfi":ccfi, "eu":eu, "med":med, "usw":usw, "use":use, "gulf":gulf, "util":util,
    "de_dates":de_dates, "thru":[v for v in thru if v is not None], "exp":exp, "asean_y":asean_y, "eu_y":eu_y, "us_y":us_y, "exp_y":exp_y,
    "su_dates":su_dates, "fleet":fleet, "idle_r":idle_r, "order":order,
    "co_dates":co_dates, "blank_us":blank_us, "blank_eu":blank_eu,
    "fin_years":fin_years, "fin_rev_a":fin_rev_a, "fin_np_a":fin_np_a, "fin_gm_a":fin_gm_a, "fin_roe_a":fin_roe_a, "fin_ocf_a":fin_ocf_a, "fin_dar_a":fin_dar_a, "fin_eps_a":fin_eps_a,
    "fin_q_lbl":fin_q_lbl, "fin_rev_q":fin_rev_q, "fin_np_q":fin_np_q, "fin_gm_q":fin_gm_q,
    "div_years":div_years, "div_ps":div_ps, "div_payout":div_payout, "div_amt":div_amt,
    "cost_years":cost_years, "cost_equip":cost_equip, "cost_voyage":cost_voyage,
    "cost_vessel":cost_vessel, "cost_perbox":cost_perbox, "cost_vol":cost_vol,
    "cost_total":cost_total, "cost_fuel":cost_fuel, "cost_charter":cost_charter,
    "port_rev":port_rev, "port_gm":port_gm, "port_thru":port_thru, "port_share":port_share,
    "macro_fuel":m_fuel, "macro_charter":m_charter, "macro_ets":m_ets,
    "macro_redsea_ratio":m_redsea_ratio, "macro_redsea_absorb":m_redsea_absorb, "macro_pmi":m_pmi,
    "qvol_dates":qvol_dates, "qvol":qvol, "qvol_yoy":qvol_yoy, "qvol_cum":qvol_cum, "qrev":qrev, "qnp":qnp,
}
NOTES = {
    "freight": "",
    "supply": "",
    "control": notes_co[-1],
    "demand": f"2026年1–8月全国港口集装箱吞吐量在{de[1][1]:.0f}–3130万TEU区间运行（1/2月为 MOT 合并口径折半）；3–6月维持3100万TEU以上平台，8月为{thru[-1]:.0f}万TEU（同比{pct(thru_y[-1])}，受外贸吞吐量下滑拖累）。对东盟出口增速持续领跑，对美国增速波动最大。",
    "fin": "2021–2022 为周期峰值（净利 893 / 1097 亿），2023 谷底（239 亿，-78%），2024–2025 修复至 491 / 309 亿；2026H1 归母 134.19 亿（-23.48%，运价/成本/汇率三重挤压），其中 Q2 单季约 75.4 亿（H1−Q1 推算，受 Q2 运价强反弹驱动、环比 H1 显著改善）。资产负债率由 56.8% 降至 41.0%，财务结构持续优化。",
    "div": "2022–2025 分红比例稳定在 ~50%（年报+中报合计）；2021 中报仅转增不派现，比例仅 15.6%。2025 全年每股分红 1.00 元、现金分红 154 亿元（A+H）。",
    "cost": "2021–2022 周期高位单箱成本 1000/1205 美元，2023 运价腰斩降至 786 美元，2024–2025 红海绕行+成本管控趋稳于约 863/866 美元。成本结构中设备及货物运输占比约 48–59%（随运价同向涨跌），航程成本(含燃油)约 17–22%，船舶成本(含租船/折旧)约 16–21%。年报未单列燃油费、租船费明细行；现按 航程成本×70%、船舶成本×30% 估算 2025 年燃油费≈260.6 亿、租船费≈107.9 亿（估算值，非官方披露）。",
}
FIN = {
  "annual": [{"period":fin_years[i], "rev":fin_rev_a[i], "rev_yoy":fnum(fin_a[i]["营收同比(%)"]),
              "np":fin_np_a[i], "np_yoy":fnum(fin_a[i]["归母同比(%)"]),
              "deduct":fnum(fin_a[i]["扣非净利润(亿元)"]), "gm":fin_gm_a[i],
              "nm":fnum(fin_a[i]["净利率(%)"]), "ocf":fnum(fin_a[i]["经营现金流(亿元)"]),
              "dar":fnum(fin_a[i]["资产负债率(%)"]), "roe":fin_roe_a[i],
              "eps":fnum(fin_a[i]["基本EPS(元)"])} for i in range(len(fin_a))],
  "q": [{"period":fin_q_lbl[i], "rev":fin_rev_q[i], "rev_yoy":fnum(fin_q[i]["营收同比(%)"]),
         "np":fin_np_q[i], "np_yoy":fnum(fin_q[i]["归母同比(%)"]),
         "deduct":fnum(fin_q[i]["扣非净利润(亿元)"]), "gm":fnum(fin_q[i]["毛利率(%)"]),
         "nm":fnum(fin_q[i]["净利率(%)"])} for i in range(len(fin_q))],
}
# 分红（2021-2025，A+H 全体股东现金分红）
DIV = {
  "annual": [{"period":div_years[i], "annual_ps":div_ps[i]- (fnum(fin_div[i]["中报每股分红(元)"]) or 0),
              "interim_ps":fnum(fin_div[i]["中报每股分红(元)"]), "ps":div_ps[i], "amt":div_amt[i],
              "np":fnum(fin_div[i]["归母净利润(亿元)"]), "payout":div_payout[i]} for i in range(len(fin_div))],
}
# 回购（来源：中远海控_回购明细.xlsx）
BUYBACK = {
  "a_round4": {"first":"2025-11-05","complete":"2026-01-13","cancel":"2026-01-15",
               "shares":55101715,"amt":8.25,"price_low":14.86,"price_high":14.98,"status":"已完成并注销"},
  "a_round5": {"as_of":"2026-08-14","shares":37157524,"amt":5.45,"cap":15.40,
               "price_low":13.69,"price_high":15.40,"status":"进行中·全部注销"},
  "h_ytd": {"as_of":"2026-05-22","times":21,"shares_wan":4489.35,"amt_yi_hkd":6.66,"status":"2026.03.23–05.22 逐日·已注销"},
  "h_round4": {"period":"2025-10~12","shares":123340000,"status":"已完成并注销"},
}
# 成本结构（集装箱航运业务，2021-2025，来源：财报核心数据.xlsx 成本结构表）
# 航线成本分项单位：亿元人民币(RMB)；单箱成本：美元/TEU；货运量：万TEU。
# 燃油费隐含于航程成本、租船费隐含于船舶成本，年报未单列。
COST = {
  "annual": [{"period":cost_years[i], "total":cost_total[i], "equip":cost_equip[i],
              "voyage":cost_voyage[i], "vessel":cost_vessel[i], "other":cost_other[i],
              "perbox":cost_perbox[i], "vol":cost_vol[i],
              "fuel_est":cost_fuel[i], "charter_est":cost_charter[i]} for i in range(len(fin_cost))],
}

# 港口码头业务（2021-2025，来源：财报核心数据.xlsx 港口码头业务表）
# 用户确认：泊位利用率 / 海外布局暂不细化（码头业务占合并营收仅约 2%–6%，占比小）。
PORT = {
  "years": port_years,
  "rev": port_rev, "cost": port_cost, "gm": port_gm, "gp": port_gp,
  "thru": port_thru, "share": port_share,
}

# 宏观与政策环境（维度7）：6 项核心数据（2021–2025 年度，数据源：中远海控_宏观与政策环境数据.xlsx）
# 成本驱动(指数化): 燃油/租船/EU碳价；运力与需求(水平值): 红海绕行比例/吸收率、欧美PMI。
# 均为公开数据近似，非公司披露。
MACRO = {
  "years": MYEARS,
  "fuel": m_fuel, "charter": m_charter, "ets": m_ets,
  "redsea_ratio": m_redsea_ratio, "redsea_absorb": m_redsea_absorb,
  "pmi": m_pmi,
  "pmi_detail": {"us_manuf":_m_us_manuf, "us_services":_m_us_serv,
                 "eu_manuf":_m_eu_manuf, "eu_services":_m_eu_serv},
  "latest": {"fuel":m_fuel[-1], "charter":m_charter[-1], "ets":m_ets[-1],
             "redsea_ratio":m_redsea_ratio[-1], "redsea_absorb":m_redsea_absorb[-1],
             "pmi":m_pmi[-1],
             "pmi_detail":f"美制造业{_m_us_manuf[-1]:.1f}/服务业{_m_us_serv[-1]:.1f} · 欧制造业{_m_eu_manuf[-1]:.1f}/服务业{_m_eu_serv[-1]:.1f}"},
}

# 当日行情快照（A股 + 港股，公开行情近似，非本数据库字段）
# 来源：证券之星 / 腾讯行情，2026-08-06 收盘
QUOTE = {
  "date": "2026-08-06",
  "note": "行情快照（收盘），公开数据近似，非本数据库字段；重跑 build_tracker.py 以刷新",
  "a": {"code":"601919.SH", "name":"中远海控",
        "price":15.37, "chg":-0.03, "pct":-0.19,
        "prev":15.40, "open":15.31, "high":15.45, "low":15.25,
        "amount":"10.29亿", "volume":"67.07万手", "turnover":0.53,
        "pe":9.37, "pb":1.02, "mktcap":"2346.71亿"},
  "h": {"code":"01919.HK",
        "price":15.13, "chg":-0.06, "pct":-0.39,
        "prev":15.19, "open":15.05, "high":15.24, "low":14.96,
        "amount":"1.79亿", "volume":"1189万股", "turnover":0.44,
        "pe":8.14, "pb":0.87, "ah":-15.34},
}


# 每个 SVG（趋势图）的更新频率参数：chart key -> 周/月/季/年
# 卡片指标名后的频率标签由该表自动追加（render_html.py），不在模板里手写。
FREQ = {
    # 周度：SCFI/CCFI 综合指数、主力航线即期运价、舱位利用率
    "scfi":"周","ccfi":"周","route_eu":"周","route_med":"周","route_usw":"周","route_use":"周","route_gulf":"周","util":"周",
    # 月频：港口吞吐量、海关出口总额、分区域出口同比增速
    "demand_thru":"月","demand_exp":"月","demand_yoy":"月",
    # 季频：季度航运货运量、全球运力供给、停航率、财务单季
    "qvol":"季","supply_fleet":"季","supply_order":"季","supply_idle":"季","control_us":"季","control_eu":"季","fin_rev_q":"季","fin_np_q":"季","fin_gm_q":"季",
    # 年频：财务年度、股东回报、成本结构、航线结构占比、港口码头、宏观与政策
    "fin_rev":"年","fin_np":"年","fin_gm":"年","fin_ocf":"年","fin_dar":"年","fin_roe":"年","fin_eps":"年",
    "dividend":"年","cost_breakdown":"年","cost_total":"年","cost_fuel":"年","cost_charter":"年","cost_perbox":"年",
    "routemix":"年","port_rev":"年","port_gm":"年","port_thru":"年","port_share":"年",
    "macro_fuel":"年","macro_charter":"年","macro_ets":"年","macro_redsea_ratio":"年","macro_redsea_absorb":"年","macro_pmi":"年",
}

DATA_JS = "__FREQ__=" + json.dumps(FREQ, ensure_ascii=False) + ";\n" \
        + "__SERIES__=" + json.dumps(SERIES, ensure_ascii=False) + ";\n" \
        + "__CHARTS__=" + json.dumps(CHARTS, ensure_ascii=False) + ";\n" \
        + "__VALUES__=" + json.dumps(VALUES, ensure_ascii=False) + ";\n" \
        + "__NOTES__=" + json.dumps(NOTES, ensure_ascii=False) + ";\n" \
        + "__FIN__=" + json.dumps(FIN, ensure_ascii=False) + ";\n" \
        + "__DIV__=" + json.dumps(DIV, ensure_ascii=False) + ";\n" \
        + "__BUYBACK__=" + json.dumps(BUYBACK, ensure_ascii=False) + ";\n" \
        + "__COST__=" + json.dumps(COST, ensure_ascii=False) + ";\n" \
        + "__ROUTE__=" + json.dumps(ROUTE, ensure_ascii=False) + ";\n" \
        + "__PORT__=" + json.dumps(PORT, ensure_ascii=False) + ";\n" \
        + "__MACRO__=" + json.dumps(MACRO, ensure_ascii=False) + ";\n" \
        + "__QUOTE__=" + json.dumps(QUOTE, ensure_ascii=False) + ";\n" \
        + "__META__=" + json.dumps({
            "freight_range": f"{fr_dates[0]} ~ {fr_dates[-1]}（{len(fr_dates)} 周）",
            "demand_range": f"{de_dates[0]} ~ {de_dates[-1]}（{len(de_dates)} 期）",
            "supply_range": f"{su_dates[0]} ~ {su_dates[-1]}（{len(su_dates)} 季）",
            "control_range": f"{co_dates[0]} ~ {co_dates[-1]}（{len(co_dates)} 季）",
            "fin_range": f"{fin_years[0]}–{fin_years[-1]} 年报 + {fin_q_lbl[0]}–{fin_q_lbl[-1]} 季报",
            "route_range": "分航线箱量与收入明细，2021–2025 年报口径（全年）",
            "port_range": "港口码头业务，2021–2025 年报口径（全年）",
            "macro_range": "宏观与政策 6 项核心数据：VLSFO燃油价 / Harpex租船费率 / EU ETS碳价 / 亚欧绕航比例 / 运力吸收率 / 欧美制造业·服务业PMI（4 条明细线，2021–2025 年度水平值），数据源 中远海控_宏观与政策环境数据.xlsx，公开数据近似",
            "qvol_range": f"季度货运量明细(2021-)，{qvol_dates[0]} ~ {qvol_dates[-1]}（{len(qvol_dates)} 季）· 来源：中远海控_货运量与航线结构数据.xlsx",
            "gen_time": "2026-08-06",
        }, ensure_ascii=False) + ";"

print("charts:", list(CHARTS.keys()))
print("series lens:", {k:len(v) for k,v in SERIES.items()})
print("VALUES sample:", {k:VALUES[k] for k in ["scfi","ccfi","thru","fleet","idle","blank_us"]})

# 把 DATA_JS 暂存，供下一步合成 HTML
with open(os.path.join(HERE,"_data_js.txt"),"w",encoding="utf-8") as f:
    f.write(DATA_JS)
print("DATA_JS bytes:", len(DATA_JS))
