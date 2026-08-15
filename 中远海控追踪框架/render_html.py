# -*- coding: utf-8 -*-
"""读取 build_tracker.py 产出的 _data_js.txt，合成正式版追踪看板 HTML（方向C + 趋势增强）。"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_JS = open(os.path.join(HERE, "_data_js.txt"), encoding="utf-8").read()
OUT = os.path.join(HERE, "中远海控追踪看板(方向C).html")

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>中远海控 · 主营与业绩追踪看板（方向C · 趋势增强）</title>
<style>
:root{--bg:#f4f6f8;--card:#fff;--line:#e3e8ee;--ink:#1f2733;--dim:#7a8694;--acc:#c8102e;--acc2:#15616d;--ok:#2e9e6b;--warn:#d98a14;--todo:#9aa6b2;--soft:#f7f9fb}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.6}
header.top{background:var(--card);border-bottom:1px solid var(--line);padding:18px 28px;position:sticky;top:0;z-index:5;box-shadow:0 1px 4px rgba(20,30,50,.04)}
.top h1{font-size:19px;font-weight:700;letter-spacing:.5px}
.top .sub{color:var(--dim);font-size:12px;margin-top:3px}
.wrap{max-width:1200px;margin:0 auto;padding:24px 22px 90px}
/* 顶部行情快照条 */
.quotebar{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-bottom:20px;display:flex;flex-direction:column;gap:10px}
.quotebar .qhead{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.quotebar .qname{font-size:16px;font-weight:700}
.quotebar .qcode{font-size:12px;color:var(--dim)}
.quotebar .qdate{margin-left:auto;font-size:11px;color:var(--todo)}
.quotebar .qtoday{font-size:11px;color:var(--ink);background:#eef2f6;border:1px solid var(--line);border-radius:10px;padding:2px 8px}
.quotebar .qrefresh{font-size:11px;color:#fff;background:var(--acc2);border:none;border-radius:10px;padding:4px 10px;cursor:pointer;display:inline-flex;align-items:center;gap:4px}
.quotebar .qrefresh:hover{background:#0e4a55}
.quotebar .qrefresh:disabled{background:var(--dim);cursor:not-allowed}
.quotebar .qrefresh .spinner{display:inline-block;width:10px;height:10px;border:1.5px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite}
.quotebar .qrefresh .spinner.hidden{display:none}
@keyframes spin{to{transform:rotate(360deg)}}
.quotebar .qmsg{font-size:10.5px;color:var(--dim);margin-left:6px}
.quotebar .qmsg.ok{color:var(--ok)}
.quotebar .qmsg.err{color:var(--acc)}
.quotebar .qrow{display:flex;gap:20px;flex-wrap:wrap}
.quotebar .qgroup{display:flex;align-items:center;gap:15px;flex-wrap:wrap}
.quotebar .qg-title{font-size:11px;font-weight:700;color:#fff;background:var(--acc2);padding:2px 8px;border-radius:10px;align-self:center}
.quotebar .qitem{display:flex;flex-direction:column;align-items:flex-start;min-width:60px}
.quotebar .ql{font-size:10.5px;color:var(--dim);white-space:nowrap}
.quotebar .qv{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.25}
.quotebar .qv.up{color:var(--acc)} .quotebar .qv.down{color:var(--ok)} .quotebar .qv.flat{color:var(--dim)}
.quotebar .qv small{font-size:11px;font-weight:400;color:var(--dim);margin-left:2px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px;align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(20,30,50,.04);display:flex;flex-direction:column}
.card .hd{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.card .idx{width:26px;height:26px;border-radius:7px;background:var(--acc);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;flex:none}
.card h3{font-size:15px;font-weight:700}
.chip{margin-left:auto;font-size:10px;padding:3px 9px;border-radius:12px;font-weight:600;white-space:nowrap}
.chip.ok{background:#e7f6ee;color:var(--ok)} .chip.part{background:#fdf3e3;color:var(--warn)} .chip.todo{background:#f0f2f5;color:var(--todo)}
.card .desc{font-size:12px;color:var(--dim);margin-bottom:10px}
.metric{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px dashed var(--line)}
.metric:last-of-type{border-bottom:none}
.metric .k{color:var(--dim);font-size:13px}
.metric .right{text-align:right;display:flex;align-items:center;gap:2px}
.metric .v{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.metric .v.up{color:var(--acc)} .metric .v.down{color:var(--ok)} .metric .v.todo{color:var(--todo);font-weight:400;font-size:12px}
.metric .v.ex{color:var(--ink);font-weight:600;font-size:12px}
.metric .chg{font-size:11px;color:var(--dim);margin-left:4px}
.spark{width:84px;height:26px;display:inline-block;vertical-align:middle;margin-left:6px}
.tbtn{font-size:10px;color:var(--acc);border:1px solid var(--line);background:var(--soft);border-radius:10px;padding:2px 8px;cursor:pointer;margin-left:6px;white-space:nowrap}
.tbtn:hover{background:#ffeef0}
.foot{display:flex;justify-content:space-between;margin-top:12px;font-size:11px;color:var(--todo);border-top:1px solid var(--line);padding-top:9px}
.note{font-size:11px;color:var(--dim);background:var(--soft);border-left:3px solid var(--acc2);padding:7px 10px;border-radius:0 6px 6px 0;margin-top:10px}
/* 长期趋势专区：宏观→损益传导框架（四渠道卡片） */
.channel-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:10px}
.channel-col{background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.channel-head{padding:11px 14px;color:#fff;font-weight:700;font-size:14px;display:flex;align-items:center;gap:8px}
.channel-head .num{width:22px;height:22px;border:2px solid rgba(255,255,255,.7);border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:700}
.channel-body{padding:13px 14px 14px}
.channel-item+.channel-item{margin-top:13px;padding-top:13px;border-top:1px dashed var(--line)}
.channel-item .metric-name{font-size:12.5px;font-weight:600;color:var(--ink);line-height:1.35}
.channel-item .metric-meta{font-size:10.5px;color:var(--dim);margin-top:3px}
@media (max-width:900px){.channel-grid{grid-template-columns:repeat(2,1fr)}}
/* 趋势专区 */
.trend-zone{margin-top:30px;border-top:2px solid var(--line);padding-top:20px}
.trend-zone h2{font-size:17px;margin-bottom:12px}
.trend-zone details{margin-bottom:10px;border:1px solid var(--line);border-radius:8px;background:#fff}
.trend-zone summary{padding:12px 16px;cursor:pointer;font-weight:600;font-size:14px}
.trend-zone summary:hover{background:var(--soft)}
.trend-zone .body{padding:6px 16px 16px}
.imgbox img{max-width:100%;border:1px solid var(--line);border-radius:6px}
/* 财务表 */
.fin-sec h4{font-size:13px;margin:16px 0 6px;color:var(--acc2);font-weight:700}
.fin-note{font-size:11.5px;color:var(--dim);background:var(--soft);border-left:3px solid var(--acc);padding:8px 11px;border-radius:0 6px 6px 0;margin:8px 0 4px;line-height:1.7}
.ftab{border-collapse:collapse;width:100%;font-size:12px;margin:4px 0 6px;font-variant-numeric:tabular-nums}
.ftab th,.ftab td{border:1px solid var(--line);padding:6px 9px;text-align:right;white-space:nowrap}
.ftab th{background:var(--soft);color:var(--ink);font-weight:600;text-align:center}
.ftab td:first-child,.ftab th:first-child{text-align:left}
.rt-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:6px}
@media(max-width:720px){.rt-grid{grid-template-columns:1fr}}
.ftab td.muted{color:var(--todo)}
/* 弹窗 */
.modal{display:none;position:fixed;inset:0;background:rgba(20,30,50,.55);z-index:50;align-items:center;justify-content:center;padding:24px}
.modal.show{display:flex}
.modal .box{background:#fff;border-radius:12px;max-width:980px;width:100%;padding:18px;position:relative;max-height:92vh;overflow:auto}
.modal .box h3{font-size:16px;margin-bottom:12px}
.modal .close{position:absolute;top:10px;right:16px;cursor:pointer;color:var(--dim);font-size:22px;line-height:1}
.modal .box img{max-width:100%;border:1px solid var(--line);border-radius:6px}
.modal .sub{font-size:12px;color:var(--dim);margin-top:8px}
footer.foot2{margin-top:34px;text-align:center;color:var(--todo);font-size:11px}
</style>
</head>
<body>
<header class="top">
  <h1>中远海控 · 主营与业绩追踪看板</h1>
</header>
<div class="wrap">
  <div class="quotebar" id="quotebar"></div>

  <div class="grid">

    <!-- 1 集装箱航运主业 -->
    <div class="card">
      <div class="hd"><div class="idx">1</div><h3>集装箱航运主业</h3></div>
      <div class="desc">核心基本盘，占总营收约 96%。</div>
      <div class="metric"><span class="k">SCFI 综合指数</span><span class="right"><span class="v" data-val="scfi"></span><span class="chg" data-val="scfi_chg"></span><span class="spark" data-spark="scfi" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('freight','SCFI / CCFI 综合指数')">趋势</button></span></div>
      <div class="metric"><span class="k">CCFI 综合指数</span><span class="right"><span class="v" data-val="ccfi"></span><span class="chg" data-val="ccfi_chg"></span><span class="spark" data-spark="ccfi" data-color="#15616d"></span><button class="tbtn" onclick="openChart('freight','SCFI / CCFI 综合指数')">趋势</button></span></div>
      <div class="metric"><span class="k">单季货运量</span><span class="right"><span class="v" data-val="qvol25"></span><span class="chg" data-val="qvol_chg"></span><span class="spark" data-spark="qvol" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('qvol','季度航运货运量（单季）')">趋势</button></span></div>
      <div class="metric"><span class="k">舱位利用率</span><span class="right"><span class="v" data-val="util"></span><span class="spark" data-spark="util" data-color="#d98a14"></span><button class="tbtn" onclick="openChart('util','舱位利用率')">趋势</button></span></div>
      <div class="metric"><span class="k">航线结构占比 (2025·按箱量)</span><span class="right"><span class="v" style="font-size:11px;white-space:normal" data-val="route_mix25"></span><button class="tbtn" onclick="openChart('routemix','航线结构占比')">趋势</button></span></div>
      <div class="note">传导逻辑：本主业收入 ≈ <b>货运量</b> × <b>单箱运价</b>，运价弹性主导利润。需求端，8月传统出货旺季前的赶舱推升<b>舱位利用率</b>与<b>单季货运量</b>，货量撑起收入底盘；价格端，船公司通过 <b>GRI（综合费率上涨附加费）</b> 主动提价，叠加旺季舱位偏紧，驱动 <b>SCFI / CCFI</b> 综合指数在连跌三周后全线强反弹。运价（价）的边际弹性远大于货量（量），故运价回暖对单箱收入乃至净利的杠杆效应最强；后续须盯紧出货节奏回落后运力复航（停航率下降）对运价的反向压力。</div>
    </div>

    <!-- 2 港口码头业务 -->
    <div class="card">
      <div class="hd"><div class="idx">2</div><h3>港口码头业务</h3></div>
      <div class="desc">压舱石，毛利率最高、逆周期正增长。</div>
      <div class="metric"><span class="k">全国港口吞吐量</span><span class="right"><span class="v" data-val="thru"></span><span class="chg" data-val="thru_yoy"></span><span class="spark" data-spark="thru" data-color="#15616d"></span><button class="tbtn" onclick="openChart('demand','港口吞吐量 & 出口总额')">趋势</button></span></div>
      <div class="metric"><span class="k">海关出口总额</span><span class="right"><span class="v" data-val="exp"></span><span class="chg" data-val="exp_yoy"></span><button class="tbtn" onclick="openChart('demand','港口吞吐量 & 出口总额')">趋势</button></span></div>
      <div class="metric"><span class="k">对东盟出口同比</span><span class="right"><span class="v" data-val="asean"></span><button class="tbtn" onclick="openChart('demand_yoy','分区域出口增速')">趋势</button></span></div>
      <div class="metric"><span class="k">码头业务收入(2025)</span><span class="right"><span class="v" data-val="port_rev25"></span><span class="chg" data-val="port_rev_yoy"></span><button class="tbtn" onclick="openChart('portmix','港口码头业务：收入&毛利率&吞吐量')">趋势</button></span></div>
      <div class="metric"><span class="k">码头业务毛利率(2025)</span><span class="right"><span class="v" data-val="port_gm25"></span><button class="tbtn" onclick="openChart('portmix','港口码头业务：收入&毛利率&吞吐量')">趋势</button></span></div>
      <div class="metric"><span class="k">码头总吞吐量(2025)</span><span class="right"><span class="v" data-val="port_thru25"></span><span class="chg" data-val="port_thru_yoy"></span><button class="tbtn" onclick="openChart('portmix','港口码头业务：收入&毛利率&吞吐量')">趋势</button></span></div>
      <div class="metric"><span class="k">码头营收占合并营收(2025)</span><span class="right"><span class="v" data-val="port_share25"></span></span></div>
      <div class="note">传导逻辑：码头业务的量价根基来自<b>全国港口吞吐量</b>，而吞吐量由出口需求驱动——<b>海关出口总额</b>（尤其<b>对东盟出口</b>）越景气，生成的可装箱货量越多，经港口装卸、堆存的集装箱量越大，码头装卸及延伸服务收入随之上行。三者均为码头业务货量的先行/同步指标，出口走强即预示码头吞吐量向好。</div>
    </div>

    <!-- 3 财务核心指标 -->
    <div class="card">
      <div class="hd"><div class="idx">3</div><h3>财务核心指标</h3></div>
      <div class="desc">2021-至今年报季报。</div>
      <div class="metric"><span class="k">营业收入(2025)</span><span class="right"><span class="v" data-val="fin_rev25"></span><span class="spark" data-spark="fin_rev_a" data-color="#15616d"></span><button class="tbtn" onclick="openChart('fin_annual','年度营收 & 归母净利润')">趋势</button></span></div>
      <div class="metric"><span class="k">归母净利润(2025)</span><span class="right"><span class="v" data-val="fin_np25"></span><span class="chg" data-val="fin_np25_chg"></span><span class="spark" data-spark="fin_np_a" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('fin_annual','年度营收 & 归母净利润')">趋势</button></span></div>
      <div class="metric"><span class="k">归母净利润(2026Q1)</span><span class="right"><span class="v" data-val="fin_np_q1"></span><span class="chg" data-val="fin_np_q1_chg"></span><button class="tbtn" onclick="openChart('fin_quarterly','季度营收 & 归母净利润')">趋势</button></span></div>
      <div class="metric"><span class="k">毛利率(2025)</span><span class="right"><span class="v" data-val="fin_gm25"></span></div>
      <div class="metric"><span class="k">经营现金流(2025)</span><span class="right"><span class="v" data-val="fin_ocf25"></span></div>
      <div class="metric"><span class="k">资产负债率(2025)</span><span class="right"><span class="v" data-val="fin_dar25"></span></div>
      <div class="metric"><span class="k">ROE摊薄(2025)</span><span class="right"><span class="v" data-val="fin_roe25"></span></div>
      <div class="metric"><span class="k">基本EPS(2025)</span><span class="right"><span class="v" data-val="fin_eps25"></span></div>
      <div class="note" id="note-fin"></div>
    </div>

    <!-- 4 行业供需格局 -->
    <div class="card">
      <div class="hd"><div class="idx">4</div><h3>行业供需格局</h3></div>
      <div class="desc">运力、闲置率、新船交付与停航调控，决定运价的中长期天花板。</div>
      <div class="metric"><span class="k">全球船队运力</span><span class="right"><span class="v" data-val="fleet"></span><span class="chg" data-val="fleet_yoy"></span><span class="spark" data-spark="fleet" data-color="#15616d"></span><button class="tbtn" onclick="openChart('supply','全球运力 & 闲置率/订单')">趋势</button></span></div>
      <div class="metric"><span class="k">闲置率</span><span class="right"><span class="v" data-val="idle"></span><button class="tbtn" onclick="openChart('supply','全球运力 & 闲置率/订单')">趋势</button></span></div>
      <div class="metric"><span class="k">手持订单/运力</span><span class="right"><span class="v" data-val="order"></span><button class="tbtn" onclick="openChart('supply','全球运力 & 闲置率/订单')">趋势</button></span></div>
      <div class="metric"><span class="k">美线停航率</span><span class="right"><span class="v" data-val="blank_us"></span><button class="tbtn" onclick="openChart('control','美线/欧线停航率')">趋势</button></span></div>
      <div class="metric"><span class="k">欧线停航率</span><span class="right"><span class="v" data-val="blank_eu"></span><button class="tbtn" onclick="openChart('control','美线/欧线停航率')">趋势</button></span></div>
      <div class="note">传导逻辑：运力（供给）侧是<b>运价</b>中长期天花板与底部的决定性变量。当<b>全球运力</b>持续扩张、<b>手持订单/运力</b>比居高，意味着未来有效供给放量，对 SCFI/CCFI 形成向下压制；反之<b>闲置率</b>低、船队高周转，说明在役运力偏紧、对运价形成支撑。船公司还可通过<b>美线/欧线停航率</b>（主动空班）在需求走弱时抽离有效运力，人为托住运价——停航率越高、运力收缩越深，运价底部越牢。运力扩张（增量投放）与停航调控（减量抽离）此消彼长，直接决定<b>单箱运价</b>弹性，进而传导至<b>单箱收入</b>与<b>净利</b>；跟踪手持订单/运力与美线/欧线停航率即可预判运价方向。</div>
    </div>

    <!-- 5 成本结构 -->
    <div class="card">
      <div class="hd"><div class="idx">5</div><h3>成本结构</h3></div>
      <div class="desc">利润的另一半：单箱成本与成本分项，决定盈利弹性。</div>
      <div class="metric"><span class="k">航线单箱成本(2025)</span><span class="right"><span class="v" data-val="cost_perbox25"></span><span class="chg" data-val="cost_perbox_yoy"></span><span class="spark" data-spark="cost_perbox" data-color="#15616d"></span><button class="tbtn" onclick="openChart('cost','成本结构：航线成本分项 & 单箱成本')">趋势</button></span></div>
      <div class="metric"><span class="k">集装箱航运业务成本(2025)</span><span class="right"><span class="v" data-val="cost_total25"></span></span></div>
      <div class="metric"><span class="k">成本结构(2025)</span><span class="right"><span class="v ex">设备48%/航程22%/船舶21%/其他9%</span></span></div>
      <div class="metric"><span class="k">燃油费估算（2025）</span><span class="right"><span class="v" data-val="cost_fuel25"></span><span class="chg ex">≈航程成本×70%</span></span></div>
      <div class="metric"><span class="k">租船费估算（2025）</span><span class="right"><span class="v" data-val="cost_charter25"></span><span class="chg ex">≈船舶成本×30%</span></span></div>
      <div class="note" id="note-cost"></div>
    </div>

    <!-- 6 股东回报与资本运作（暂隐藏，不显示） -->
    <div class="card" style="display:none">
      <div class="hd"><div class="idx">6</div><h3>股东回报与资本运作</h3></div>
      <div class="desc">分红与回购是估值锚；分红来源财报核心数据.xlsx，回购来源中远海控_回购明细.xlsx。</div>
      <div class="metric"><span class="k">分红比例(2025)</span><span class="right"><span class="v up" data-val="div_payout25"></span><span class="spark" data-spark="div_payout" data-color="#2e9e6b"></span><button class="tbtn" onclick="openChart('dividend','全年每股分红 & 分红比例')">趋势</button></span></div>
      <div class="metric"><span class="k">全年每股分红(2025)</span><span class="right"><span class="v" data-val="div_ps25"></span></span></div>
      <div class="metric"><span class="k">现金分红总额(2025,A+H)</span><span class="right"><span class="v" data-val="div_amt25"></span></span></div>
      <div class="metric"><span class="k">A股回购(截至08-14)</span><span class="right"><span class="v" data-val="bb_a5_shares"></span><span class="chg" data-val="bb_a5_amt"></span><span class="chg">/上限<span data-val="bb_a5_cap"></span></span></div>
      <div class="metric"><span class="k">H股回购(2026年内)</span><span class="right"><span class="v" data-val="bb_h_ytd"></span><span class="chg" data-val="bb_h_ytd_amt"></span></span></div>
      <div class="note" id="note-div"></div>
    </div>

    <!-- 6 宏观与政策环境（由维度7 顺移） -->
    <div class="card">
      <div class="hd"><div class="idx">6</div><h3>宏观与政策环境</h3></div>
      <div class="desc">需求/成本/运力/监管四渠道，均映射到中远海控的损益线。</div>
      <div class="metric"><span class="k">VLSFO 燃油价</span><span class="right"><span class="v" data-val="macro_fuel25"></span><span class="spark" data-spark="macro_fuel" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('macroidx','宏观成本驱动：燃油/租船/EU碳价(2021=100)')">趋势</button></span></div>
      <div class="metric"><span class="k">租船费率 Harpex</span><span class="right"><span class="v" data-val="macro_charter25"></span><span class="spark" data-spark="macro_charter" data-color="#d98a14"></span><button class="tbtn" onclick="openChart('macroidx','宏观成本驱动：燃油/租船/EU碳价(2021=100)')">趋势</button></span></div>
      <div class="metric"><span class="k">EU ETS 碳价</span><span class="right"><span class="v" data-val="macro_ets25"></span><span class="spark" data-spark="macro_ets" data-color="#2e9e6b"></span><button class="tbtn" onclick="openChart('macroidx','宏观成本驱动：燃油/租船/EU碳价(2021=100)')">趋势</button></span></div>
      <div class="metric"><span class="k">亚欧绕航好望角比例</span><span class="right"><span class="v" data-val="macro_redsea_ratio25"></span><span class="spark" data-spark="macro_redsea_ratio" data-color="#d84315"></span><button class="tbtn" onclick="openChart('macroop','运力与需求：红海绕行+欧美PMI(水平值)')">趋势</button></span></div>
      <div class="metric"><span class="k">运力吸收率</span><span class="right"><span class="v" data-val="macro_redsea_absorb25"></span><span class="spark" data-spark="macro_redsea_absorb" data-color="#ff8f00"></span><button class="tbtn" onclick="openChart('macroop','运力与需求：红海绕行+欧美PMI(水平值)')">趋势</button></span></div>
      <div class="metric"><span class="k">欧美制造业/服务业 PMI</span><span class="right"><span class="v" style="font-size:12px;white-space:normal" data-val="macro_pmi25"></span><span class="spark" data-spark="macro_pmi" data-color="#00897b"></span><button class="tbtn" onclick="openChart('macroop','运力与需求：红海绕行+欧美PMI(水平值)')">趋势</button></span></div>
      <div class="note">传导逻辑：①需求：<b>欧美制造业/服务业 PMI</b> 表征海外景气，扩张则货量需求走强、支撑运价；②成本：<b>VLSFO 燃油价</b>、<b>租船费率 Harpex</b>、<b>EU ETS 碳价</b> 上行直接推高单箱成本（航程/船舶/碳合规），侵蚀利润弹性；③运力：<b>亚欧绕航好望角比例</b>与<b>运力吸收率</b> 上升，等于把有效运力"锁"在更长航线上，被动收紧供给、托底运价；④监管：碳价与排放合规抬升行业成本曲线。四者共振（需求旺 + 绕航吸运力 + 成本升）时利润弹性最大，反之需求弱 + 运力复航 + 成本降则利润收缩。</div>
    </div>

  </div>

  <!-- 长期趋势专区 -->
  <div class="trend-zone">
    <h2>长期趋势专区（点击展开，数据同源）</h2>
    <details open><summary>① SCFI / CCFI 综合指数（周度）</summary><div class="body imgbox" data-img="freight"></div></details>
    <details><summary>② 主力航线即期运价（周度）</summary><div class="body imgbox" data-img="routes"></div></details>
    <details open><summary>③ 季度航运货运量（单季，2021Q1–2026Q1）</summary><div class="body imgbox" data-img="qvol"></div></details>
    <details><summary>④ 舱位利用率（周度）</summary><div class="body imgbox" data-img="util"></div></details>
    <details><summary>⑤ 全国港口吞吐量 & 出口总额（月频）</summary><div class="body imgbox" data-img="demand"></div></details>
    <details><summary>⑥ 分区域出口同比增速（月频）</summary><div class="body imgbox" data-img="demand_yoy"></div></details>
    <details><summary>⑦ 全球运力 & 闲置率/手持订单（季频）</summary><div class="body imgbox" data-img="supply"></div></details>
    <details><summary>⑧ 美线/欧线停航率（季频）</summary><div class="body imgbox" data-img="control"></div></details>

    <details open><summary>⑨ 财务核心指标：年度(累计) & 季度(当季单季还原)</summary>
      <div class="body fin-sec">
        <div class="imgbox" data-img="fin_annual"></div>
        <div class="imgbox" data-img="fin_quarterly"></div>
        <p class="fin-note">口径说明：季报原始披露为<b>累计值</b>（Q2=Q1+Q2，Q3=Q1+Q2+Q3，Q4=全年）。为便于横向对比各季真实经营表现，下方季度表已按公式 <b>当季ₙ = 本季累计ₙ − 上季累计ₙ</b>（Q1当季=Q1累计）还原为<b>单季(当季)</b>数据；同比亦为当季同比。</p>
        <h4>年度核心数据（2021–2025，全年累计）</h4>
        <div id="fin-annual-table"></div>
        <h4>季度核心数据（2021Q1–2026Q1，已还原单季）</h4>
        <div id="fin-quarterly-table"></div>
      </div>
    </details>

    <details style="display:none"><summary>⑩ 股东回报与资本运作：分红 & 回购（暂隐藏）</summary>
      <div class="body fin-sec">
        <div class="imgbox" data-img="dividend"></div>
        <p class="fin-note">口径说明：分红为<b>年报+中报合计</b>（A+H 全体股东现金分红）；2021 年中报仅转增股本不派现，故当年分红比例仅 15.6%。回购数据来源：公司回购公告（A股第4/5轮、H股2026年内逐日及第4轮），完整明细见 <b>中远海控_回购明细.xlsx</b>。</p>
        <h4>分红数据（2021–2025）</h4>
        <div id="div-table"></div>
        <h4>回购汇总（A股 + H股）</h4>
        <div id="bb-table"></div>
      </div>
    </details>

    <details><summary>⑪ 成本结构：航线成本分项 & 单箱成本</summary>
      <div class="body fin-sec">
        <div class="imgbox" data-img="cost"></div>
        <p class="fin-note">口径说明：航线成本分项来自年报成本分析表 / 业绩发布会，分为 <b>设备及货物运输成本</b>、<b>航程成本（含燃油）</b>、<b>船舶成本（含租船/船舶租金/折旧）</b>。年报<b>未单独列示</b>"燃油费""租船费"明细行，二者分别隐含于航程成本与船舶成本中（业绩发布会另披露<b>耗油单价(美元/吨)</b>季度值）。单箱成本为已披露的航线单箱成本（美元/TEU）。2023/2024 航线成本为百万美元折算人民币（汇率≈7.1），"其他"未单列。</p>
        <h4>成本结构数据（2021–2025）</h4>
        <div id="cost-table"></div>
      </div>
    </details>

    <details><summary>⑫ 航线结构占比（年度，分航线箱量 & 收入）</summary>
      <div class="body fin-sec">
        <div class="imgbox" data-img="routemix"></div>
        <p class="fin-note">口径说明：份额 = 该航线数值 ÷ 五条航线合计。五条航线为 <b>美线（跨太平洋）</b>、<b>欧地线（亚欧）</b>、<b>近洋线（亚洲区域内）</b>、<b>内贸线（中国大陆）</b>、<b>其它国际（南北线等）</b>。全年货运量与航线收入取自分航线箱量与收入明细，与核心运营指标概览的全年合计一致。2026 仅含 Q1，未纳入年度占比。</p>
        <div class="rt-grid">
          <div>
            <h4>货运量占比（%）</h4>
            <div id="route-vol-table"></div>
          </div>
          <div>
            <h4>航线收入占比（%）</h4>
            <div id="route-rev-table"></div>
          </div>
        </div>
      </div>
    </details>

    <details><summary>⑬ 港口码头业务（年度，收入 & 毛利率 & 吞吐量）</summary>
      <div class="body fin-sec">
        <div class="imgbox" data-img="portmix"></div>
        <p class="fin-note">口径说明：港口码头业务为公司第二大板块，占合并营收约 2%–6%，毛利率长期高于集运主业（逆周期正增长）。<b>泊位利用率 / 海外布局进度 按用户意见暂不细化</b>（业务占比小）。数据来源：财报核心数据.xlsx 港口码头业务表，2021–2025 年报口径；其中 2022/2025 成本为按毛利率倒算。</p>
        <div id="port-table"></div>
      </div>
    </details>
    <details><summary>⑭ 宏观与政策环境（5 项核心数据）</summary>
      <div class="body fin-sec">
        <div class="imgbox" data-img="macroidx"></div>
        <p class="fin-note">口径说明（上图）：<b>成本驱动</b>三项（燃油、租船、EU 碳价）按 2021=100 指数化以便跨量纲对比。</p>
        <div class="imgbox" data-img="macroop"></div>
        <p class="fin-note">口径说明（上图）：<b>运力与需求</b>三项为水平值——亚欧绕航好望角比例(%)、运力吸收率(%)、欧美综合PMI（制造业+服务业均值，虚线=50 荣枯线）。红海绕行自 2023-11 起使亚欧约 80–90% 箱量绕行好望角、吸收有效运力约 13–18%。</p>
        <h4>核心指标原始值（年度近似）</h4>
        <div id="macro-table"></div>
        <p class="fin-note">数据源：<b>公开数据近似</b>（Ship&amp;Bunker/Argus、Harper Petersen、EU ETS/EEX、ISM/HCOB PMI），非公司披露；红海绕行、PMI 为年度代理值，非平滑序列。</p>
      </div>
    </details>

    <details open><summary>⑮ 宏观 → 损益 传导框架</summary>
      <div class="body fin-sec">
        <p class="fin-note" style="margin-bottom:12px">原则：每个宏观/政策变量必须映射到一条损益线（货量 / 运价 / 成本 / 利润），否则只是背景噪声。</p>
        <div class="channel-grid">
          <div class="channel-col">
            <div class="channel-head" style="background:#1565c0"><span class="num">1</span>需求渠道</div>
            <div class="channel-body">
              <div class="channel-item">
                <div class="metric-name">中国出口金额 YoY</div>
                <div class="metric-meta">月频 · 海关总署 → 货量 → 营业收入</div>
              </div>
              <div class="channel-item">
                <div class="metric-name">欧美 PMI 新出口订单</div>
                <div class="metric-meta">月频 · S&amp;P Global → 货量/运价 → 营业收入</div>
              </div>
              <div class="channel-item">
                <div class="metric-name">美零售库存周期</div>
                <div class="metric-meta">月频 · US Census → 补库需求 → 货量</div>
              </div>
            </div>
          </div>
          <div class="channel-col">
            <div class="channel-head" style="background:#1976d2"><span class="num">2</span>成本渠道</div>
            <div class="channel-body">
              <div class="channel-item">
                <div class="metric-name">VLSFO 燃油价</div>
                <div class="metric-meta">周频 · 新加坡普氏 → 燃油成本 → 单箱成本</div>
              </div>
              <div class="channel-item">
                <div class="metric-name">租船费率 Harpex</div>
                <div class="metric-meta">周频 · Clarksons → 运力租赁成本 → 单箱成本</div>
              </div>
            </div>
          </div>
          <div class="channel-col">
            <div class="channel-head" style="background:#2e7d32"><span class="num">3</span>运力渠道</div>
            <div class="channel-body">
              <div class="channel-item">
                <div class="metric-name">红海绕行比例</div>
                <div class="metric-meta">事件频 · 船司公告 → 有效运力↓ → 运价↑</div>
              </div>
              <div class="channel-item">
                <div class="metric-name">亚欧航程天数</div>
                <div class="metric-meta">周频 · 航线跟踪 → 周转效率 → 运价</div>
              </div>
            </div>
          </div>
          <div class="channel-col">
            <div class="channel-head" style="background:#558b2f"><span class="num">4</span>监管渠道</div>
            <div class="channel-body">
              <div class="channel-item">
                <div class="metric-name">EU ETS 碳价</div>
                <div class="metric-meta">日频 · EEX → 合规成本 → 单箱成本</div>
              </div>
              <div class="channel-item">
                <div class="metric-name">IMO/CII 合规</div>
                <div class="metric-meta">年频 · IMO → 降速/技改成本 → 单箱成本</div>
              </div>
            </div>
          </div>
        </div>
        <p class="fin-note">损益映射：需求 + 运力共同决定 <b>运价 × 货量 = 营业收入</b>；成本 + 监管共同决定 <b>单箱成本</b>；最终 <b>营业收入 − 成本 = 净利/净利率</b>。当前看板已接入并趋势化的指标以 <b>粗体</b> 在维度6 卡片展示。</p>
      </div>
    </details>
  </div>

  <footer class="foot2">
    中远海控主营与业绩追踪看板 · 方向C + 趋势增强 · 单文件交付 ·
    数据主源：中远海控_行业供需与运价数据.xlsx · 更新该文件后重跑 build_tracker.py 即可刷新
  </footer>
</div>

<div class="modal" id="modal" onclick="if(event.target===this)closeChart()">
  <div class="box">
    <span class="close" onclick="closeChart()">×</span>
    <h3 id="modal-title">长期趋势</h3>
    <div class="imgbox" id="modal-img"></div>
    <div class="sub" id="modal-sub"></div>
  </div>
</div>

<script>
__DATA_JS__

const COLORS={scfi:"#c8102e",ccfi:"#15616d",thru:"#15616d",util:"#d98a14",fleet:"#15616d"};

// 0) 顶部行情快照条
(function(){
  const q=__QUOTE__; if(!q) return;
  const cls=v=> v>0?"up":(v<0?"down":"flat");
  const pct=v=>(v>0?"+":"")+v.toFixed(2)+"%";
  const chg=v=>(v>0?"+":"")+v.toFixed(2);
  const a=q.a, h=q.h;
  const today = new Date();
  const todayStr = today.getFullYear()+"-"+String(today.getMonth()+1).padStart(2,"0")+"-"+String(today.getDate()).padStart(2,"0");
  let html='<div class="qhead"><span class="qname">'+a.name+'</span>'
    +'<span class="qcode">'+a.code+' / '+h.code+'</span>'
    +'<span class="qtoday">今天 '+todayStr+'</span>'
    +'<span class="qdate">行情快照 '+q.date+' 收盘</span>'
    +'<button class="qrefresh" id="qRefreshBtn" title="重新运行 build_tracker.py 刷新行情数据">'
    +'<span class="spinner hidden"></span><span class="lbl">刷新行情</span></button>'
    +'<span class="qmsg" id="qRefreshMsg"></span></div>'
    +'<div class="qrow">'
    +'<div class="qgroup"><span class="qg-title">A股</span>'
    +'<div class="qitem"><span class="ql">最新价</span><span class="qv '+cls(a.pct)+'">'+a.price.toFixed(2)+'</span></div>'
    +'<div class="qitem"><span class="ql">涨跌幅</span><span class="qv '+cls(a.pct)+'">'+pct(a.pct)+'</span></div>'
    +'<div class="qitem"><span class="ql">涨跌额</span><span class="qv '+cls(a.chg)+'">'+chg(a.chg)+'</span></div>'
    +'<div class="qitem"><span class="ql">昨收</span><span class="qv">'+a.prev.toFixed(2)+'</span></div>'
    +'<div class="qitem"><span class="ql">今开</span><span class="qv">'+a.open.toFixed(2)+'</span></div>'
    +'<div class="qitem"><span class="ql">成交额</span><span class="qv">'+a.amount+'</span></div>'
    +'</div>'
    +'<div class="qgroup"><span class="qg-title">H股</span>'
    +'<div class="qitem"><span class="ql">最新价</span><span class="qv '+cls(h.pct)+'">'+h.price.toFixed(2)+'<small>港元</small></span></div>'
    +'<div class="qitem"><span class="ql">涨跌幅</span><span class="qv '+cls(h.pct)+'">'+pct(h.pct)+'</span></div>'
    +'<div class="qitem"><span class="ql">AH溢价</span><span class="qv flat">'+pct(h.ah)+'</span></div>'
    +'</div>'
    +'</div>';
  document.getElementById("quotebar").innerHTML=html;

  // 刷新行情按钮：浏览器侧 fetch('/rebuild')，由 serve.py 调用 build_tracker.py
  const btn=document.getElementById("qRefreshBtn");
  const sp =btn&&btn.querySelector(".spinner");
  const lb =btn&&btn.querySelector(".lbl");
  const mg =document.getElementById("qRefreshMsg");
  if(btn){
    btn.addEventListener("click",()=>{
      btn.disabled=true;
      if(sp)sp.classList.remove("hidden");
      if(lb)lb.textContent="刷新中…";
      if(mg){mg.className="qmsg";mg.textContent="";}
      const t0=Date.now();
      fetch("/rebuild",{cache:"no-store"})
        .then(r=>r.json().then(o=>({status:r.status,o})))
        .then(({status,o})=>{
          const dt=((Date.now()-t0)/1000).toFixed(1);
          if(o&&o.ok){
            if(mg){mg.className="qmsg ok";mg.textContent="✓ "+o.msg+"（"+dt+"s）";}
            if(lb)lb.textContent="刷新行情";
            // 自动重载页面，拉取新 HTML
            setTimeout(()=>location.reload(),800);
          }else{
            if(mg){mg.className="qmsg err";mg.textContent="✗ "+(o&&o.msg||("HTTP "+status));}
            if(lb)lb.textContent="重试";
          }
        })
        .catch(e=>{
          if(mg){mg.className="qmsg err";mg.textContent="✗ "+e;}
          if(lb)lb.textContent="重试";
        })
        .finally(()=>{
          btn.disabled=false;
          if(sp)sp.classList.add("hidden");
        });
    });
  }
})();

function spark(el,data,color){
  const w=el.clientWidth||84,h=26,pad=2;
  if(!data||data.length<2) return;
  const min=Math.min(...data),max=Math.max(...data),rng=(max-min)||1;
  const pts=data.map((v,i)=>{
    const x=pad+i*(w-2*pad)/(data.length-1);
    const y=h-pad-(v-min)/rng*(h-2*pad);
    return x.toFixed(1)+","+y.toFixed(1);
  }).join(" ");
  el.innerHTML='<svg width="100%" height="'+h+'" viewBox="0 0 '+w+' '+h+'"><polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="1.6" stroke-linejoin="round"/></svg>';
}

// 1) 填充卡片最新值 + 涨跌着色
for(const k in __VALUES__){
  const el=document.querySelector('[data-val="'+k+'"]');
  if(!el) continue;
  el.textContent=__VALUES__[k];
  const dir=__VALUES__[k+"_dir"];
  if(dir==="up") el.classList.add("up");
  else if(dir==="down") el.classList.add("down");
}
// 2) sparkline
document.querySelectorAll("[data-spark]").forEach(el=>{
  const key=el.getAttribute("data-spark");
  spark(el, __SERIES__[key], el.getAttribute("data-color")||"#15616d");
});
// 3) 趋势专区图片注入
document.querySelectorAll("[data-img]").forEach(el=>{
  const id=el.getAttribute("data-img");
  if(__CHARTS__[id]) el.innerHTML='<img src="'+__CHARTS__[id]+'" alt="'+id+'">';
});
// 4) 简评文本
const _nc=document.getElementById("note-control"); if(__NOTES__.control&&_nc) _nc.textContent="调控动态："+__NOTES__.control;
if(__NOTES__.fin)     document.getElementById("note-fin").textContent="业绩周期："+__NOTES__.fin;
if(__NOTES__.div)     document.getElementById("note-div").textContent="分红动态："+__NOTES__.div;
if(__NOTES__.cost)    document.getElementById("note-cost").textContent="成本动态："+__NOTES__.cost;

// 6) 财务表渲染
function fmtCell(v, fmt){
  if(v===null||v===undefined||v==="") return "<td class='muted'>—</td>";
  if(fmt==="pct1") return "<td>"+v.toFixed(1)+"%</td>";
  if(fmt==="pct2") return "<td>"+v.toFixed(2)+"%</td>";
  if(fmt==="eps")  return "<td>"+v.toFixed(2)+"</td>";
  return "<td>"+v.toFixed(1)+"</td>";
}
function buildTable(rows, cols){
  let h="<table class='ftab'><thead><tr>"+cols.map(c=>"<th>"+c.label+"</th>").join("")+"</tr></thead><tbody>";
  for(const r of rows){
    h+="<tr>"+cols.map(c=>fmtCell(r[c.k], c.fmt)).join("")+"</tr>";
  }
  return h+"</tbody></table>";
}
const finAnnCols=[
  {k:"period",label:"报告期"},{k:"rev",label:"营收(亿)"},{k:"rev_yoy",label:"营收同比",fmt:"pct1"},
  {k:"np",label:"归母净利(亿)"},{k:"np_yoy",label:"归母同比",fmt:"pct1"},{k:"deduct",label:"扣非(亿)"},
  {k:"gm",label:"毛利率",fmt:"pct1"},{k:"nm",label:"净利率",fmt:"pct1"},{k:"ocf",label:"经营现金流(亿)"},
  {k:"dar",label:"资产负债率",fmt:"pct1"},{k:"roe",label:"ROE",fmt:"pct1"},{k:"eps",label:"EPS",fmt:"eps"}
];
const finQCols=[
  {k:"period",label:"报告期"},{k:"rev",label:"营收(当季,亿)"},{k:"rev_yoy",label:"当季营收同比",fmt:"pct1"},
  {k:"np",label:"归母净利(当季,亿)"},{k:"np_yoy",label:"当季归母同比",fmt:"pct1"},{k:"deduct",label:"扣非(当季,亿)"},
  {k:"gm",label:"当季毛利率",fmt:"pct1"},{k:"nm",label:"当季净利率",fmt:"pct1"}
];
if(__FIN__){
  document.getElementById("fin-annual-table").innerHTML=buildTable(__FIN__.annual, finAnnCols);
  document.getElementById("fin-quarterly-table").innerHTML=buildTable(__FIN__.q, finQCols);
}

// 7) 分红表 + 回购汇总表
if(__DIV__){
  const finDivCols=[
    {k:"period",label:"年度"},{k:"annual_ps",label:"年报每股(元)"},{k:"interim_ps",label:"中报每股(元)"},
    {k:"ps",label:"全年每股(元)"},{k:"amt",label:"现金分红(亿,A+H)"},{k:"np",label:"归母净利润(亿)"},{k:"payout",label:"分红比例",fmt:"pct1"}
  ];
  document.getElementById("div-table").innerHTML=buildTable(__DIV__.annual, finDivCols);
}
if(__BUYBACK__){
  const b=__BUYBACK__;
  const bbRows=[
    ["A股第4轮（已完成注销）", b.a_round4.first+"~"+b.a_round4.complete, (b.a_round4.shares/1e4).toLocaleString()+"股", b.a_round4.amt+"亿", b.a_round4.price_low+"~"+b.a_round4.price_high, b.a_round4.status],
    ["A股第5轮（进行中）", "截至"+b.a_round5.as_of, (b.a_round5.shares/1e4).toLocaleString()+"股", b.a_round5.amt+"亿（上限"+b.a_round5.cap+"亿）", b.a_round5.price_low+"~"+b.a_round5.price_high, b.a_round5.status],
    ["H股2026年内（逐日）", b.h_ytd.as_of, b.h_ytd.shares_wan.toLocaleString()+"万股", b.h_ytd.amt_yi_hkd+"亿港元", "14.22~15.62", b.h_ytd.status],
    ["H股第4轮（已完成注销）", b.h_round4.period, (b.h_round4.shares/1e4).toLocaleString()+"股", "详见公告", "—", b.h_round4.status],
  ];
  let h="<table class='ftab'><thead><tr><th>轮次/类别</th><th>期间</th><th>股数</th><th>金额</th><th>价格区间</th><th>用途/状态</th></tr></thead><tbody>";
  for(const r of bbRows) h+="<tr>"+r.map(c=>"<td>"+c+"</td>").join("")+"</tr>";
  h+="</tbody></table>";
  document.getElementById("bb-table").innerHTML=h;
}

// 8) 成本结构表
if(__COST__){
  const costCols=[
    {k:"period",label:"年度"},{k:"total",label:"航运成本(亿)"},{k:"equip",label:"设备货物(亿)"},
    {k:"voyage",label:"航程含燃油(亿)"},{k:"vessel",label:"船舶含租船(亿)"},{k:"other",label:"其他(亿)"},
    {k:"perbox",label:"单箱成本(USD)"},{k:"vol",label:"货运量(万TEU)"},
    {k:"fuel_est",label:"燃油费估算(亿)"},{k:"charter_est",label:"租船费估算(亿)"}
  ];
  document.getElementById("cost-table").innerHTML=buildTable(__COST__.annual, costCols);
}

// 9) 航线结构占比表（货运量 / 收入，按航线×年度）
if(__ROUTE__){
  function buildShareTable(years, routes, shareMap){
    let h="<table class='ftab'><thead><tr><th>航线</th>"+years.map(y=>"<th>"+y+"</th>").join("")+"</tr></thead><tbody>";
    for(const r of routes){
      h+="<tr><td>"+r+"</td>"+shareMap[r].map(v=>"<td>"+v.toFixed(1)+"%</td>").join("")+"</tr>";
    }
    return h+"</tbody></table>";
  }
  document.getElementById("route-vol-table").innerHTML=buildShareTable(__ROUTE__.years, __ROUTE__.routes, __ROUTE__.vol_share);
  document.getElementById("route-rev-table").innerHTML=buildShareTable(__ROUTE__.years, __ROUTE__.routes, __ROUTE__.rev_share);
}

// 10) 港口码头业务表
if(__PORT__){
  const pCols=[
    {k:"period",label:"年度"},{k:"rev",label:"收入(亿)"},{k:"cost",label:"成本(亿)"},
    {k:"gm",label:"毛利率",fmt:"pct1"},{k:"gp",label:"毛利(亿)"},
    {k:"thru",label:"总吞吐量(万TEU)"},{k:"share",label:"营收占比",fmt:"pct1"}
  ];
  const pRows=__PORT__.years.map((y,i)=>({
    period:y+"年", rev:__PORT__.rev[i], cost:__PORT__.cost[i], gm:__PORT__.gm[i],
    gp:__PORT__.gp[i], thru:__PORT__.thru[i], share:__PORT__.share[i]
  }));
  document.getElementById("port-table").innerHTML=buildTable(pRows, pCols);
}

// 11) 宏观与政策环境表（5 项核心数据）
if(__MACRO__){
  const mCols=[
    {k:"period",label:"年度"},{k:"fuel",label:"VLSFO($/mt)"},{k:"charter",label:"Harpex"},
    {k:"ets",label:"EU ETS(€/t)"},{k:"ratio",label:"亚欧绕航(%)"},{k:"absorb",label:"运力吸收(%)"},
    {k:"pmi",label:"欧美PMI"}
  ];
  const mRows=__MACRO__.years.map((y,i)=>({
    period:y+"年", fuel:__MACRO__.fuel[i], charter:__MACRO__.charter[i], ets:__MACRO__.ets[i],
    ratio:__MACRO__.redsea_ratio[i], absorb:__MACRO__.redsea_absorb[i], pmi:__MACRO__.pmi[i]
  }));
  document.getElementById("macro-table").innerHTML=buildTable(mRows, mCols);
}

// 5) 弹窗
function openChart(id,title){
  const c=__CHARTS__[id];
  if(!c) return;
  document.getElementById("modal-title").textContent=title;
  document.getElementById("modal-img").innerHTML='<img src="'+c+'" alt="'+title+'">';
  let sub="";
  if(id==="freight") sub="样本 "+__SERIES__.fr_dates.length+" 周 · "+__META__.freight_range;
  else if(id==="demand"||id==="demand_yoy") sub="样本 "+__SERIES__.de_dates.length+" 期 · "+__META__.demand_range;
  else if(id==="fin_annual"||id==="fin_quarterly") sub="来源 "+__META__.fin_range;
  else if(id==="cost") sub="来源 财报核心数据.xlsx · 成本结构(2021–2025)";
  else if(id==="routemix") sub="来源 "+__META__.route_range;
  else if(id==="portmix") sub="来源 "+__META__.port_range;
  else if(id==="macroidx") sub="来源 "+__META__.macro_range;
  else if(id==="macroop") sub="来源 "+__META__.macro_range;
  else if(id==="qvol") sub="来源 "+__META__.qvol_range;
  else sub="样本 "+__SERIES__.su_dates.length+" 季 · "+__META__.supply_range;
  document.getElementById("modal-sub").textContent=sub;
  document.getElementById("modal").classList.add("show");
}
function closeChart(){document.getElementById("modal").classList.remove("show");}
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeChart();});
</script>
</body>
</html>
"""

html = TEMPLATE.replace("__DATA_JS__", DATA_JS)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("WROTE", OUT, "bytes=", len(html))

# 同时输出 public/index.html：规范入口文件名，供 Cloudflare Pages 等静态托管识别。
# 内容与主看板完全一致（单文件自包含），部署时只需指向 public/ 目录。
pub_dir = os.path.join(HERE, "public")
os.makedirs(pub_dir, exist_ok=True)
pub_out = os.path.join(pub_dir, "index.html")
with open(pub_out, "w", encoding="utf-8") as f:
    f.write(html)
print("WROTE", pub_out, "bytes=", len(html))
