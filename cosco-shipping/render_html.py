# -*- coding: utf-8 -*-
"""读取 build_tracker.py 产出的 _data_js.txt，合成正式版追踪看板 HTML（方向C + 趋势增强）。"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_JS = open(os.path.join(HERE, "_data_js.txt"), encoding="utf-8").read()
OUT = os.path.join(HERE, "cosco-dashboard.html")

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
/* 内联 SVG 图表（SCFI/CCFI 等） */
.svg-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px}
.svgi{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:10px}
.svgi figcaption{font-size:12px;color:var(--dim);font-weight:600;margin-bottom:6px}
.svgi svg,.imgbox svg{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:6px;background:#fff}
/* 财务图：年度 / 季度 两组网格 */
.fin-grid{grid-template-columns:repeat(auto-fill,minmax(340px,1fr))}
.svg-grid+.svg-grid{margin-top:14px}
.fin-fig{padding:8px}
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
.modal .close{position:absolute;top:10px;right:16px;cursor:pointer;color:var(--dim);font-size:22px;line-height:1}
.modal .box img{max-width:100%;border:1px solid var(--line);border-radius:6px}
footer.foot2{margin-top:34px;text-align:center;color:var(--todo);font-size:11px}
</style>
<script src="__REL__quote-live.js" defer></script>
<script src="__REL__chart-zoom.js" defer></script>
</head>
<body>
<div class="wrap">
  <div class="quotebar" data-a-code="sh601919" data-h-code="hk01919" id="quotebar"></div>

  <div class="grid">

    <!-- 1 集装箱航运主业 -->
    <div class="card">
      <div class="hd"><div class="idx">1</div><h3>集装箱航运主业</h3></div>
      <div class="desc">核心基本盘，占总营收约 96%。</div>
      <div class="metric"><span class="k">SCFI 综合指数</span><span class="right"><span class="v" data-val="scfi"></span><span class="spark" data-spark="scfi" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('scfi','SCFI 综合指数（2026 周度）')">趋势</button></span></div>
      <div class="metric"><span class="k">CCFI 综合指数</span><span class="right"><span class="v" data-val="ccfi"></span><span class="spark" data-spark="ccfi" data-color="#15616d"></span><button class="tbtn" onclick="openChart('ccfi','CCFI 综合指数（2026 周度）')">趋势</button></span></div>
      <div class="metric"><span class="k">单季货运量</span><span class="right"><span class="v" data-val="qvol25"></span><span class="spark" data-spark="qvol" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('qvol','季度航运货运量（单季）')">趋势</button></span></div>
      <div class="metric"><span class="k">舱位利用率</span><span class="right"><span class="v" data-val="util"></span><span class="spark" data-spark="util" data-color="#d98a14"></span><button class="tbtn" onclick="openChart('util','舱位利用率')">趋势</button></span></div>
      <div class="metric"><span class="k">航线结构占比</span><span class="right"><span class="v" style="font-size:11px;white-space:normal" data-val="route_mix25"></span><button class="tbtn" onclick="openChart('routemix','航线结构占比')">趋势</button></span></div>
      <div class="note">传导逻辑：本主业收入 ≈ <b>货运量</b> × <b>单箱运价</b>，运价弹性主导利润。需求端，8月传统出货旺季前的赶舱推升<b>舱位利用率</b>与<b>单季货运量</b>，货量撑起收入底盘；价格端，船公司通过 <b>GRI（综合费率上涨附加费）</b> 主动提价，叠加旺季舱位偏紧，驱动 <b>SCFI / CCFI</b> 综合指数在连跌三周后全线强反弹。运价（价）的边际弹性远大于货量（量），故运价回暖对单箱收入乃至净利的杠杆效应最强；后续须盯紧出货节奏回落后运力复航（停航率下降）对运价的反向压力。</div>
    </div>

    <!-- 2 港口码头业务 -->
    <div class="card">
      <div class="hd"><div class="idx">2</div><h3>港口码头业务</h3></div>
      <div class="desc">压舱石，毛利率最高、逆周期正增长。</div>
      <div class="metric"><span class="k">全国港口吞吐量</span><span class="right"><span class="v" data-val="thru"></span><span class="spark" data-spark="thru" data-color="#15616d"></span><button class="tbtn" onclick="openChart('demand_thru','全国港口吞吐量（月频）')">趋势</button></span></div>
      <div class="metric"><span class="k">海关出口总额</span><span class="right"><span class="v" data-val="exp"></span><span class="spark" data-spark="exp" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('demand_exp','海关出口总额（月频）')">趋势</button></span></div>
      <div class="metric"><span class="k">分区域出口增速</span><span class="right"><span class="v" style="font-size:11px;white-space:normal" data-val="export_yoy_detail"></span><button class="tbtn" onclick="openChart('demand_yoy','分区域出口增速')">趋势</button></span></div>
      <div class="metric"><span class="k">码头业务收入</span><span class="right"><span class="v" data-val="port_rev25"></span><span class="spark" data-spark="port_rev" data-color="#15616d"></span><button class="tbtn" onclick="openChart('port_rev','码头业务收入（亿元）')">趋势</button></span></div>
      <div class="metric"><span class="k">码头业务毛利率</span><span class="right"><span class="v" data-val="port_gm25"></span><span class="spark" data-spark="port_gm" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('port_gm','码头业务毛利率（%）')">趋势</button></span></div>
      <div class="metric"><span class="k">码头总吞吐量</span><span class="right"><span class="v" data-val="port_thru25"></span><span class="spark" data-spark="port_thru" data-color="#2e9e6b"></span><button class="tbtn" onclick="openChart('port_thru','码头总吞吐量（万TEU）')">趋势</button></span></div>
      <div class="metric"><span class="k">码头营收占合并营收</span><span class="right"><span class="v" data-val="port_share25"></span><span class="spark" data-spark="port_share" data-color="#d98a14"></span><button class="tbtn" onclick="openChart('port_share','码头营收占合并营收（%）')">趋势</button></span></div>
      <div class="note">传导逻辑：码头业务的量价根基来自<b>全国港口吞吐量</b>，而吞吐量由出口需求驱动——<b>海关出口总额</b>（尤其<b>对东盟出口</b>）越景气，生成的可装箱货量越多，经港口装卸、堆存的集装箱量越大，码头装卸及延伸服务收入随之上行。三者均为码头业务货量的先行/同步指标，出口走强即预示码头吞吐量向好。</div>
    </div>

    <!-- 3 财务核心指标 -->
    <div class="card">
      <div class="hd"><div class="idx">3</div><h3>财务核心指标</h3></div>
      <div class="desc">2021-至今年报。</div>
      <div class="metric"><span class="k">营业收入</span><span class="right"><span class="v" data-val="fin_rev25"></span><span class="spark" data-spark="fin_rev_a" data-color="#15616d"></span><button class="tbtn" onclick="openChart('fin_rev','营业收入（亿元）')">趋势</button></span></div>
      <div class="metric"><span class="k">归母净利润</span><span class="right"><span class="v" data-val="fin_np25"></span><span class="spark" data-spark="fin_np_a" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('fin_np','归母净利润（亿元）')">趋势</button></span></div>
      <div class="metric"><span class="k">毛利率</span><span class="right"><span class="v" data-val="fin_gm25"></span><span class="spark" data-spark="fin_gm_a" data-color="#2e9e6b"></span><button class="tbtn" onclick="openChart('fin_gm','毛利率（%）')">趋势</button></span></div>
      <div class="metric"><span class="k">经营现金流</span><span class="right"><span class="v" data-val="fin_ocf25"></span><span class="spark" data-spark="fin_ocf_a" data-color="#d98a14"></span><button class="tbtn" onclick="openChart('fin_ocf','经营现金流（亿元）')">趋势</button></span></div>
      <div class="metric"><span class="k">资产负债率</span><span class="right"><span class="v" data-val="fin_dar25"></span><span class="spark" data-spark="fin_dar_a" data-color="#7a8694"></span><button class="tbtn" onclick="openChart('fin_dar','资产负债率（%）')">趋势</button></span></div>
      <div class="metric"><span class="k">ROE摊薄</span><span class="right"><span class="v" data-val="fin_roe25"></span><span class="spark" data-spark="fin_roe_a" data-color="#1f7a8c"></span><button class="tbtn" onclick="openChart('fin_roe','ROE摊薄（%）')">趋势</button></span></div>
      <div class="metric"><span class="k">基本EPS</span><span class="right"><span class="v" data-val="fin_eps25"></span><span class="spark" data-spark="fin_eps_a" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('fin_eps','基本EPS（元）')">趋势</button></span></div>
      <div class="note" id="note-fin"></div>
    </div>

    <!-- 4 行业供需格局 -->
    <div class="card">
      <div class="hd"><div class="idx">4</div><h3>行业供需格局</h3></div>
      <div class="desc">运力、闲置率与停航调控，决定运价的中长期天花板。</div>
      <div class="metric"><span class="k">全球船队运力</span><span class="right"><span class="v" data-val="fleet"></span><span class="spark" data-spark="fleet" data-color="#15616d"></span><button class="tbtn" onclick="openChart('supply_fleet','全球集装箱船队总运力（季频）')">趋势</button></span></div>
      <div class="metric"><span class="k">闲置率</span><span class="right"><span class="v" data-val="idle"></span><span class="spark" data-spark="idle_r" data-color="#d98a14"></span><button class="tbtn" onclick="openChart('supply_idle','闲置运力比例（季频）')">趋势</button></span></div>
      <div class="metric"><span class="k">手持订单/运力</span><span class="right"><span class="v" data-val="order"></span><span class="spark" data-spark="order" data-color="#7a8694"></span><button class="tbtn" onclick="openChart('supply_order','手持订单占运力比例（季频）')">趋势</button></span></div>
      <div class="metric"><span class="k">美线停航率</span><span class="right"><span class="v" data-val="blank_us"></span><span class="spark" data-spark="blank_us" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('control_us','美线停航率（季频）')">趋势</button></span></div>
      <div class="metric"><span class="k">欧线停航率</span><span class="right"><span class="v" data-val="blank_eu"></span><span class="spark" data-spark="blank_eu" data-color="#15616d"></span><button class="tbtn" onclick="openChart('control_eu','欧线停航率（季频）')">趋势</button></span></div>
      <div class="note">传导逻辑：运力（供给）侧是<b>运价</b>中长期天花板与底部的决定性变量。当<b>全球运力</b>持续扩张、<b>手持订单/运力</b>比居高，意味着未来有效供给放量，对 SCFI/CCFI 形成向下压制；反之<b>闲置率</b>低、船队高周转，说明在役运力偏紧、对运价形成支撑。船公司还可通过<b>美线/欧线停航率</b>（主动空班）在需求走弱时抽离有效运力，人为托住运价——停航率越高、运力收缩越深，运价底部越牢。运力扩张（增量投放）与停航调控（减量抽离）此消彼长，直接决定<b>单箱运价</b>弹性，进而传导至<b>单箱收入</b>与<b>净利</b>；跟踪手持订单/运力与美线/欧线停航率即可预判运价方向。</div>
    </div>

    <!-- 5 成本结构 -->
    <div class="card">
      <div class="hd"><div class="idx">5</div><h3>成本结构</h3></div>
      <div class="desc">利润的另一半：单箱成本与成本分项，决定盈利弹性。</div>
      <div class="metric"><span class="k">航线单箱成本</span><span class="right"><span class="v" data-val="cost_perbox25"></span><span class="spark" data-spark="cost_perbox" data-color="#15616d"></span><button class="tbtn" onclick="openChart('cost_perbox','航线单箱成本')">趋势</button></span></div>
      <div class="metric"><span class="k">集装箱航运业务成本</span><span class="right"><span class="v" data-val="cost_total25"></span><span class="spark" data-spark="cost_total" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('cost_total','集装箱航运业务成本')">趋势</button></span></div>
      <div class="metric"><span class="k">成本结构</span><span class="right"><span class="v ex">设备48%/航程22%/船舶21%/其他9%</span><button class="tbtn" onclick="openChart('cost_breakdown','成本结构（年度分项）')">趋势</button></span></div>
      <div class="metric"><span class="k">燃油费估算</span><span class="right"><span class="v" data-val="cost_fuel25"></span><span class="spark" data-spark="cost_fuel" data-color="#d98a14"></span><button class="tbtn" onclick="openChart('cost_fuel','燃油费估算（估算值）')">趋势</button></span></div>
      <div class="metric"><span class="k">租船费估算</span><span class="right"><span class="v" data-val="cost_charter25"></span><span class="spark" data-spark="cost_charter" data-color="#2e9e6b"></span><button class="tbtn" onclick="openChart('cost_charter','租船费估算（估算值）')">趋势</button></span></div>
      <div class="note" id="note-cost"></div>
    </div>

    <!-- 6 股东回报与资本运作（暂隐藏，不显示） -->
    <div class="card" style="display:none">
      <div class="hd"><div class="idx">6</div><h3>股东回报与资本运作</h3></div>
      <div class="desc">分红与回购是估值锚；分红来源财报核心数据.xlsx，回购来源中远海控_回购明细.xlsx。</div>
      <div class="metric"><span class="k">分红比例(最新)</span><span class="right"><span class="v up" data-val="div_payout25"></span><span class="spark" data-spark="div_payout" data-color="#2e9e6b"></span><button class="tbtn" onclick="openChart('dividend','全年每股分红 & 分红比例')">趋势</button></span></div>
      <div class="metric"><span class="k">全年每股分红(最新)</span><span class="right"><span class="v" data-val="div_ps25"></span><button class="tbtn" onclick="openChart('dividend','全年每股分红 & 分红比例')">趋势</button></span></div>
      <div class="metric"><span class="k">现金分红总额(最新,A+H)</span><span class="right"><span class="v" data-val="div_amt25"></span><button class="tbtn" onclick="openChart('dividend','全年每股分红 & 分红比例')">趋势</button></span></div>
      <div class="metric"><span class="k">A股回购(截至08-14)</span><span class="right"><span class="v" data-val="bb_a5_shares"></span><span class="chg" data-val="bb_a5_amt"></span><span class="chg">/上限<span data-val="bb_a5_cap"></span></span><button class="tbtn" onclick="openChart('dividend','全年每股分红 & 分红比例')">趋势</button></span></div>
      <div class="metric"><span class="k">H股回购(2026年内)</span><span class="right"><span class="v" data-val="bb_h_ytd"></span><span class="chg" data-val="bb_h_ytd_amt"></span><button class="tbtn" onclick="openChart('dividend','全年每股分红 & 分红比例')">趋势</button></span></div>
      <div class="note" id="note-div"></div>
    </div>

    <!-- 6 宏观与政策环境（由维度7 顺移） -->
    <div class="card">
      <div class="hd"><div class="idx">6</div><h3>宏观与政策环境</h3></div>
      <div class="desc">需求/成本/运力/监管四渠道，均映射到中远海控的损益线。</div>
      <div class="metric"><span class="k">VLSFO 燃油价</span><span class="right"><span class="v" data-val="macro_fuel25"></span><span class="spark" data-spark="macro_fuel" data-color="#c8102e"></span><button class="tbtn" onclick="openChart('macro_fuel','VLSFO 燃油价（$/mt）')">趋势</button></span></div>
      <div class="metric"><span class="k">租船费率 Harpex</span><span class="right"><span class="v" data-val="macro_charter25"></span><span class="spark" data-spark="macro_charter" data-color="#d98a14"></span><button class="tbtn" onclick="openChart('macro_charter','Harpex 租船费率指数')">趋势</button></span></div>
      <div class="metric"><span class="k">EU ETS 碳价</span><span class="right"><span class="v" data-val="macro_ets25"></span><span class="spark" data-spark="macro_ets" data-color="#2e9e6b"></span><button class="tbtn" onclick="openChart('macro_ets','EU ETS 碳价（€/t）')">趋势</button></span></div>
      <div class="metric"><span class="k">亚欧绕航好望角比例</span><span class="right"><span class="v" data-val="macro_redsea_ratio25"></span><span class="spark" data-spark="macro_redsea_ratio" data-color="#d84315"></span><button class="tbtn" onclick="openChart('macro_redsea_ratio','亚欧绕航好望角比例（%）')">趋势</button></span></div>
      <div class="metric"><span class="k">运力吸收率</span><span class="right"><span class="v" data-val="macro_redsea_absorb25"></span><span class="spark" data-spark="macro_redsea_absorb" data-color="#ff8f00"></span><button class="tbtn" onclick="openChart('macro_redsea_absorb','运力吸收率（%）')">趋势</button></span></div>
      <div class="metric"><span class="k">欧美制造业/服务业 PMI</span><span class="right"><span class="v" style="font-size:12px;white-space:normal" data-val="macro_pmi25"></span><button class="tbtn" onclick="openChart('macro_pmi','欧美制造业/服务业 PMI')">趋势</button></span></div>
      <div class="note">传导逻辑：①需求：<b>欧美制造业/服务业 PMI</b> 表征海外景气，扩张则货量需求走强、支撑运价；②成本：<b>VLSFO 燃油价</b>、<b>租船费率 Harpex</b>、<b>EU ETS 碳价</b> 上行直接推高单箱成本（航程/船舶/碳合规），侵蚀利润弹性；③运力：<b>亚欧绕航好望角比例</b>与<b>运力吸收率</b> 上升，等于把有效运力"锁"在更长航线上，被动收紧供给、托底运价；④监管：碳价与排放合规抬升行业成本曲线。四者共振（需求旺 + 绕航吸运力 + 成本升）时利润弹性最大，反之需求弱 + 运力复航 + 成本降则利润收缩。</div>
    </div>

  </div>

  <!-- 长期趋势专区 -->
  <div class="trend-zone">
    <h2>长期趋势专区</h2>
    <details open><summary>1 集装箱航运主业</summary>
      <div class="body">
        <div class="svg-grid">
          <div class="imgbox" id="chart-scfi" data-img="scfi"></div>
          <div class="imgbox" id="chart-ccfi" data-img="ccfi"></div>
        </div>
        <div class="svg-grid">
          <div class="imgbox" id="chart-route-eu" data-img="route_eu"></div>
          <div class="imgbox" id="chart-route-med" data-img="route_med"></div>
          <div class="imgbox" id="chart-route-usw" data-img="route_usw"></div>
          <div class="imgbox" id="chart-route-use" data-img="route_use"></div>
          <div class="imgbox" id="chart-route-gulf" data-img="route_gulf"></div>
          <div class="imgbox" data-img="util"></div>
        </div>
        <div class="svg-grid">
          <div class="imgbox" data-img="qvol"></div>
          <div class="imgbox" data-img="routemix"></div>
        </div>
      </div>
    </details>
    <details ><summary>2 港口码头业务</summary>
      <div class="body">
        <div class="svg-grid">
          <div class="imgbox" id="chart-demand-thru" data-img="demand_thru"></div>
          <div class="imgbox" id="chart-demand-exp" data-img="demand_exp"></div>
        </div>
        <div class="svg-grid">
          <div class="imgbox" data-img="demand_yoy"></div>
        </div>
        <div class="svg-grid fin-grid">
          <div class="imgbox" id="chart-port-rev" data-img="port_rev"></div>
          <div class="imgbox" id="chart-port-gm" data-img="port_gm"></div>
          <div class="imgbox" id="chart-port-thru" data-img="port_thru"></div>
          <div class="imgbox" id="chart-port-share" data-img="port_share"></div>
        </div>
      </div>
    </details>
    <details open><summary>3 财务核心指标</summary>
      <div class="body">
        <div class="svg-grid fin-grid">
          <div class="imgbox" id="chart-fin-rev" data-img="fin_rev"></div>
          <div class="imgbox" id="chart-fin-np" data-img="fin_np"></div>
          <div class="imgbox" id="chart-fin-gm" data-img="fin_gm"></div>
          <div class="imgbox" id="chart-fin-ocf" data-img="fin_ocf"></div>
          <div class="imgbox" id="chart-fin-dar" data-img="fin_dar"></div>
          <div class="imgbox" id="chart-fin-roe" data-img="fin_roe"></div>
          <div class="imgbox" id="chart-fin-eps" data-img="fin_eps"></div>
        </div>
        <div class="svg-grid fin-grid">
          <div class="imgbox" id="chart-fin-rev-q" data-img="fin_rev_q"></div>
          <div class="imgbox" id="chart-fin-np-q" data-img="fin_np_q"></div>
          <div class="imgbox" id="chart-fin-gm-q" data-img="fin_gm_q"></div>
        </div>
        <div class="imgbox" data-img="dividend" style="display:none"></div>
      </div>
    </details>
    <details ><summary>4 行业供需格局</summary>
      <div class="body">
        <div class="svg-grid">
          <div class="imgbox" id="chart-supply-fleet" data-img="supply_fleet"></div>
          <div class="imgbox" id="chart-supply-order" data-img="supply_order"></div>
          <div class="imgbox" id="chart-supply-idle" data-img="supply_idle"></div>
        </div>
        <div class="svg-grid">
          <div class="imgbox" id="chart-control-us" data-img="control_us"></div>
          <div class="imgbox" id="chart-control-eu" data-img="control_eu"></div>
        </div>
      </div>
    </details>
    <details ><summary>5 成本结构</summary>
      <div class="body">
        <div class="svg-grid fin-grid">
          <div class="imgbox" id="chart-cost-breakdown" data-img="cost_breakdown"></div>
        </div>
        <div class="svg-grid fin-grid">
          <div class="imgbox" id="chart-cost-total" data-img="cost_total"></div>
          <div class="imgbox" id="chart-cost-fuel" data-img="cost_fuel"></div>
          <div class="imgbox" id="chart-cost-charter" data-img="cost_charter"></div>
          <div class="imgbox" id="chart-cost-perbox" data-img="cost_perbox"></div>
        </div>
      </div>
    </details>
    <details ><summary>6 宏观与政策环境</summary>
      <div class="body">
        <div class="svg-grid fin-grid">
          <div class="imgbox" id="chart-macro-fuel" data-img="macro_fuel"></div>
          <div class="imgbox" id="chart-macro-charter" data-img="macro_charter"></div>
          <div class="imgbox" id="chart-macro-ets" data-img="macro_ets"></div>
          <div class="imgbox" id="chart-macro-redsea-ratio" data-img="macro_redsea_ratio"></div>
          <div class="imgbox" id="chart-macro-redsea-absorb" data-img="macro_redsea_absorb"></div>
          <div class="imgbox" id="chart-macro-pmi" data-img="macro_pmi"></div>
        </div>
      </div>
    </details>
    <details open><summary>7 宏观 → 损益 传导框架</summary>
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
    中远海控主营与业绩追踪看板 · 方向C + 趋势增强 · 单文件交付（图表内联 SVG） ·
    数据主源：中远海控_行业供需与运价数据.xlsx（周运价指数 SCFF&CCFI，含 SCFI/CCFI 与五航线周度） · 更新后重跑 build_tracker.py 即可刷新
  </footer>
</div>

<div class="modal" id="modal" onclick="if(event.target===this)closeChart()">
  <div class="box">
    <span class="close" onclick="closeChart()">×</span>
    <div class="imgbox" id="modal-img"></div>
  </div>
</div>

<script src="__REL__common/charts.js"></script>
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

})();

// sparkline（指标行）由 common/charts.js 的 CommonCharts.spark 提供，见页面上方 <script src="__REL__common/charts.js">
// （baselineZero=false，与原 spark(el,data,color) 行为一致）

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
// 3) 趋势专区图片注入（支持内联 SVG 与 base64 图片）：由 common/charts.js 的 injectCharts 提供
CommonCharts.injectCharts("[data-img]", __CHARTS__);
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

// 5) 弹窗：SVG 内部已含标题/单位/数据源，弹窗不再重复显示标题与底部说明
//    弹窗生命周期（open/close/Esc/遮罩）由 common/charts.js 的 createTrendModal 提供
window.trendModal = CommonCharts.createTrendModal({
  modal: '#modal', openClass: 'show', body: '#modal-img'
});
// 供 HTML 内联 onclick="openChart('id','title')" 调用
window.openChart = function(id, title){
  const c = __CHARTS__[id];
  if (c) window.trendModal.open(c, title);
};
// 供 HTML 内联 onclick="closeChart()" / 遮罩点击 调用
window.closeChart = function(){ window.trendModal.close(); };

// 自动给每个指标名追加更新频率（周/月/季/年）：频率来自各 SVG 的 FREQ 参数（build_tracker.py 注入 __FREQ__），不在模板手写
// 由 common/charts.js 的 appendFreq 提供（读取全局 __FREQ__）
CommonCharts.appendFreq();
</script>
</body>
</html>
"""

html = TEMPLATE.replace("__DATA_JS__", DATA_JS)
# 脚本/资源路径按输出文件所在深度生成相对前缀，使三种打开方式都能解析：
#   cosco-shipping/cosco-dashboard.html   深度 1 -> ../
#   cosco-shipping/public/index.html      深度 2 -> ../../
# （原先统一用根绝对路径 "/..."，仅在生产(站点根=工作区根)与 HTTP 服务下可用，
#   双击 file:// 打开时会解析到磁盘根目录导致 CommonCharts undefined、图表全空。）
html_main = html.replace("__REL__", "../")
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html_main)
print("WROTE", OUT, "bytes=", len(html_main))

# 同时输出 public/index.html：规范入口文件名，供 Cloudflare Pages 等静态托管识别。
# 内容与主看板完全一致（单文件自包含），部署时只需指向 public/ 目录。
pub_dir = os.path.join(HERE, "public")
os.makedirs(pub_dir, exist_ok=True)
pub_out = os.path.join(pub_dir, "index.html")
html_pub = html.replace("__REL__", "../../")
with open(pub_out, "w", encoding="utf-8") as f:
    f.write(html_pub)
print("WROTE", pub_out, "bytes=", len(html_pub))
