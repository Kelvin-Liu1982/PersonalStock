
const SNAPSHOT = __DATA__;
/* 评分 / 预警模型的常量表：由 build_html.py 从 src/config.py + src/score/* 序列化注入。
   页面实时重算（computeDerived）必须复用与 Python 产线完全相同的数值，
   否则同一份数据在「离线快照」与「实时拉取」两种模式下会给出不同分数。
   ⚠️ 禁止在这里或 computeDerived 里再硬编码阈值 —— 一律走 CONST。 */
const CONST = __CONST__;
/* API Key：由 build_html.py 注入（本地免输入，不再显示在界面上）。
   ⚠️ 会随产物一起发布 —— 产物仅限本地/内网使用；若要公开部署，
   必须先改走服务端代理并删除本常量，否则 view-source 即可拿到 Key。 */
const API_KEYS = { fred: "__FRED_KEY__", eia: "__EIA_KEY__" };
/* EIA 周度石油周报序列 id 表：由 build_html.py 从 src/fetch/supply/eia_weekly.py 注入。
   ⚠️ 这里**不再手抄第二份 id 表** —— 抓取侧（python）/ 快照侧 / 实时拉取侧必须同源。
   2026-10-07 的故障就是前端手抄表漏了 `spr`：首屏读快照正常，点「拉取实时」后
   STATE.eia.spr 不存在，该图渲染成空画布「图没了」。新增序列只改 python 的 EIA_SERIES，
   本常量与静态校验 tools/check_eia_series.js 会自动跟上。
   ids: {name: series_id}；million: 原始单位为千桶、需要 /1000 的序列名。 */
const EIA_SERIES = __EIA_SERIES__;
const EIA_MILLION = new Set(EIA_SERIES.million || []);
/* EIA **日度**油价 id 表：由 build_html.py 从 src/fetch/prices.py 注入（2026-10-08 新增）。
   ⚠️ 刻意与上面的 EIA_SERIES（周度）**分成两张表**，不是一个疏漏而是必须的隔离：
   fetchEIA() 用 EIA_SERIES.ids 的 period 并集生成「周轴」weekly / eiaDates，
   一旦把日度价格混进那张表，周轴会从约 2296 个周点膨胀到几千个日点，
   所有周度图的 x 轴会整片塌掉。日度价格只做日轴对齐，绝不参与周轴并集。
   同理 loadLive 的价格通道走 /api/eia 拿这一张表，而周度库存仍走 EIA_SERIES。
   ids: {name: series_id}；fallback: EIA 不可用时回落的 FRED 序列 id。 */
const EIA_PRICE_IDS = __EIA_PRICE_IDS__;
let STATE = SNAPSHOT;
let RANGE = 252;            // 默认近1年
// 支持 All/1y 区间切换的维度（右上角按钮）："1y"=近252交易日，"all"=全量(2024-01 起)
const RANGE_TOGGLE_DIMS = ["other","geo"];
const RANGE_MODE = {}; RANGE_TOGGLE_DIMS.forEach(function(d){ RANGE_MODE[d] = "1y"; });
function dimIsAll(key){ return RANGE_TOGGLE_DIMS.indexOf(key)>=0 && RANGE_MODE[key]==="all"; }
let currentTab = 'supply';
const charts = {};
const ecCharts = {};        // ECharts 实例（实验图：制造业 PMI）；与 Chart.js 实例分开管理
// ECharts 不会自动跟随容器尺寸变化（Chart.js 靠 responsive:true 内部处理），需显式 resize
window.addEventListener("resize", function(){
  Object.keys(ecCharts).forEach(function(k){
    const c = ecCharts[k];
    try { if(c && !c.isDisposed()) c.resize(); } catch(e) { /* 面板未渲染时忽略 */ }
  });
  syncRiskHeights();   // 首屏三卡等高：布局列数变化后重新钉高
});

/* 维度区间切换（All / 1y）：目前 其他突发 + 地缘政治 两 tab 的图标题右上角带切换按钮。
   1y=近252交易日，All=全量(2024-01 起)。每个维度独立记忆状态（RANGE_MODE）。
   点任意一张图的按钮 → 切换该维度状态 → 重渲染该维度的图与 KPI。
   按钮 DOM 由 buildPanels 在 h3 内生成（带 data-rngdim），事件走委托，切 tab 不重建按钮（class 状态保留）。 */
document.addEventListener("click", function(e){
  const b = e.target && e.target.closest ? e.target.closest(".rngtgl button") : null;
  if(!b) return;
  const grp = b.closest(".rngtgl");
  const dim = grp && grp.getAttribute("data-rngdim");
  if(!dim || RANGE_TOGGLE_DIMS.indexOf(dim)<0) return;
  const mode = b.getAttribute("data-rng");            // "1y" | "all"
  RANGE_MODE[dim] = mode;
  document.querySelectorAll('.rngtgl[data-rngdim="'+dim+'"] button').forEach(function(x){
    x.classList.toggle("on", x.getAttribute("data-rng") === mode);
  });
  if(DIMS[dim]){ dimKPIs(dim); renderDimCharts(dim); }
});

/* 维度区间切换按钮组（仅 RANGE_TOGGLE_DIMS 内的维度注入）。data-rngdim 标记所属维度，
   点击委托据此定位；按钮 class "on" 高亮当前模式。hClass 给 h3 加 h-tgl（space-between 把按钮推到右上角）。 */
function hClass(key){ return RANGE_TOGGLE_DIMS.indexOf(key)>=0 ? "h-tgl" : ""; }
function rngTgl(key){
  if(RANGE_TOGGLE_DIMS.indexOf(key)<0) return "";
  const m = RANGE_MODE[key] || "1y";
  return `<span class="rngtgl" data-rngdim="${key}">`
    + `<button type="button" data-rng="1y" class="${m==="1y"?"on":""}">1y</button>`
    + `<button type="button" data-rng="all" class="${m==="all"?"on":""}">All</button></span>`;
}

/* ===== 全局图表视觉规范（一次性统一坐标轴 / 图例 / 提示框 / 动效） ===== */
if(window.Chart){
  Chart.defaults.responsive=true;
  Chart.defaults.maintainAspectRatio=false;
  Chart.defaults.font.family='-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif';
  Chart.defaults.font.size=12;
  Chart.defaults.color='#64748b';
  // 注意：animation / interaction 不能整体替换（会破坏 Chart.js v4 内部 descriptor → this._fn is not a function），
  // 必须逐属性赋值以保留内部脚本化描述符。
  Chart.defaults.animation.duration=720;
  Chart.defaults.animation.easing='easeOutQuart';
  Chart.defaults.interaction.mode='index';
  Chart.defaults.interaction.intersect=false;
  // 坐标轴：去外框、淡网格、水平刻度
  Chart.defaults.scale.grid.color='#eef2f7';
  Chart.defaults.scale.grid.drawTicks=false;
  Chart.defaults.scale.grid.tickColor='#eef2f7';
  Chart.defaults.scale.border.display=false;
  Chart.defaults.scale.ticks.color='#94a3b8';
  Chart.defaults.scale.ticks.font={size:11};
  Chart.defaults.scale.ticks.maxRotation=0;
  Chart.defaults.scale.ticks.autoSkip=true;
  Chart.defaults.scale.ticks.maxTicksLimit=10;
  // 图例：点状标记 + 紧凑
  Chart.defaults.plugins.legend.labels.usePointStyle=true;
  Chart.defaults.plugins.legend.labels.boxWidth=8;
  Chart.defaults.plugins.legend.labels.boxHeight=8;
  Chart.defaults.plugins.legend.labels.color='#334155';
  Chart.defaults.plugins.legend.labels.padding=14;
  Chart.defaults.plugins.legend.labels.font={size:11.5,weight:'600'};
  // 提示框：深色圆角 + 点状
  Chart.defaults.plugins.tooltip.backgroundColor='rgba(15,23,42,.92)';
  Chart.defaults.plugins.tooltip.titleColor='#f8fafc';
  Chart.defaults.plugins.tooltip.bodyColor='#e2e8f0';
  Chart.defaults.plugins.tooltip.borderColor='rgba(255,255,255,.14)';
  Chart.defaults.plugins.tooltip.borderWidth=1;
  Chart.defaults.plugins.tooltip.cornerRadius=10;
  Chart.defaults.plugins.tooltip.padding=11;
  Chart.defaults.plugins.tooltip.boxPadding=6;
  Chart.defaults.plugins.tooltip.usePointStyle=true;
  Chart.defaults.plugins.tooltip.titleFont={size:12.5,weight:'700'};
  Chart.defaults.plugins.tooltip.bodyFont={size:12};
}

/* ---------- 水位型序列：轴起点标注插件（review 第 4 条，方案 B） ----------
   背景：库存 / 产量这类「存量水位」序列的波动幅度远小于绝对量级，纵轴常从非 0
   起点（如库欣 400、SPR 280、OECD 1200）。此时若再把曲线下方填成面积，读者会把
   「色块大小」误读成「囤了多少」——而面积在非 0 基线下本就没有量的含义。
   处理：① 去掉这类图的 fill；② 在图内把轴起点画出来并注明「非 0」。
   用法：图表配置里加 `level:true`，渲染器据此关掉 fill 并置 `plugins.baseNote.on`。
   插件只在 y.min > 0 时绘制，故 OPEC 产量 / 剩余产能（本就 0 基线）天然跳过。 */
Chart.register({
  id:"baseNote",
  beforeDatasetsDraw:function(chart){
    const o=chart.options.plugins&&chart.options.plugins.baseNote;
    if(!o||!o.on) return;
    const area=chart.chartArea;
    if(!area) return;
    const ctx=chart.ctx;
    ctx.save();
    ctx.font='10px '+(Chart.defaults.font.family||'sans-serif');
    // 遍历所有 value 轴：双轴图（如 OECD 库存）左右各画一条基线并分别标注，
    // 标签文案按轴位置区分「轴起点 / 右轴起点」，右轴的靠右对齐避免与左轴标签重叠。
    Object.keys(chart.scales).forEach(function(id){
      const sc=chart.scales[id];
      // ⚠️ Chart.js v4 的 scale 实例**没有 .type 属性**（别用 sc.type!=="value" 判断，
      // 会把所有轴都跳过、标注整个不显示）；改用 position 判断值轴。
      if(!sc || (sc.position!=="left" && sc.position!=="right") || !(sc.min>0)) return;
      const yy=sc.getPixelForValue(sc.min);
      if(yy<area.top-1 || yy>area.bottom+1) return;
      ctx.setLineDash([4,3]); ctx.lineWidth=1;
      ctx.strokeStyle=o.color||'#94a3b8';
      ctx.beginPath(); ctx.moveTo(area.left,yy); ctx.lineTo(area.right,yy); ctx.stroke();
      ctx.setLineDash([]);
      const right=(sc.position==="right");
      const label=(right?"右轴起点 ":"轴起点 ")+Math.round(sc.min)+"（非 0）";
      const tw=ctx.measureText(label).width;
      ctx.fillStyle=o.bg||'rgba(255,255,255,.88)';
      ctx.fillRect(right?area.right-tw-8:area.left+2, yy-15, tw+6, 13);
      ctx.fillStyle=o.color||'#94a3b8';
      ctx.textBaseline='bottom'; ctx.textAlign=right?"right":"left";
      ctx.fillText(label, right?area.right-5:area.left+5, yy-3);
    });
    ctx.restore();
  }
});

/* ---------- 末点强调：末点圆点 + 数值气泡（review 第 6 条） ----------
   折线默认 pointRadius:0，读者只能靠右侧轴刻度目测「最新值到底是多少」。
   本插件在最后一个非空点上画一个圆点并贴一枚数值气泡，让最新值在图上有确定位置。
   只在显式 `endTag:{on:true}` 时绘制；多序列图（OPEC 6 国、OECD 双线）不启用，
   否则 7 枚气泡会互相压盖。气泡默认放在点的右侧，贴到绘图区右边界时翻到左侧。 */
Chart.register({
  id:"endTag",
  afterDatasetsDraw:function(chart){
    const o=chart.options.plugins&&chart.options.plugins.endTag;
    if(!o||!o.on) return;
    const area=chart.chartArea;
    if(!area) return;
    const ctx=chart.ctx;
    ctx.save();
    ctx.font='600 10px '+(Chart.defaults.font.family||'sans-serif');
    // 已占用的气泡矩形：同一 x 上有多个数据集时（库欣图 = 库存折线 + 周变动柱）竖向错开，
    // 否则两枚气泡会精确重叠、只能看见后画的那枚。默认空数组 → 单数据集图行为完全不变。
    const placed=[];
    chart.data.datasets.forEach(function(ds,di){
      const meta=chart.getDatasetMeta(di);
      if(!meta||meta.hidden||!meta.data||!meta.data.length) return;
      let pi=-1;
      for(let i=ds.data.length-1;i>=0;i--){ if(ds.data[i]!=null){ pi=i; break; } }
      if(pi<0) return;
      const el=meta.data[pi];
      if(!el) return;
      const x=el.x, y=el.y;
      if(x<area.left-1||x>area.right+1||y<area.top-1||y>area.bottom+1) return;
      // 数据集级覆写：双轴图里「周变动」是派生量，气泡要带正负号、用中性灰，不能套折线的边框色。
      const col=ds.endTagColor||ds.borderColor||o.color||'#0f766e';
      const txt=o.fmt?o.fmt(ds.data[pi])
                     :(ds.endTagFmt?ds.endTagFmt(ds.data[pi]):fmtNum(ds.data[pi],o.n==null?1:o.n));
      ctx.beginPath(); ctx.arc(x,y,3.2,0,Math.PI*2);
      ctx.fillStyle='#ffffff'; ctx.fill();
      ctx.lineWidth=2; ctx.strokeStyle=col; ctx.stroke();
      const bw=ctx.measureText(txt).width+10, bh=15;
      let bx=x+7, by=y-bh/2;
      for(let k=0;k<placed.length;k++){const q=placed[k];
        if(bx<q.x2&&bx+bw>q.x1&&by<q.y2&&by+bh>q.y1) by=q.y2+2;}   // 与已放的气泡竖向错开
      // 气泡默认放末点右侧；右轴刻度画在 chartArea 之外，气泡贴边时会盖住右轴刻度数字
      // （双轴库存图的「+0.9」压住「0」），故把可用右边界外扩一个右轴宽度再判定翻转。
      // 单轴图没有 y1 → rightW=0 → 判定退回流、行为与以前一致。
      const rightW=(chart.scales.y1&&chart.scales.y1.position==="right")?(chart.scales.y1.width||0):0;
      if(bx+bw>area.right+rightW-6) bx=x-7-bw;
      if(bx<area.left) bx=area.left;
      if(by<area.top+1) by=area.top+1;
      if(by+bh>area.bottom-1) by=area.bottom-1-bh;
      ctx.fillStyle=col;
      ctx.beginPath();
      if(ctx.roundRect) ctx.roundRect(bx,by,bw,bh,4); else ctx.rect(bx,by,bw,bh);
      ctx.fill();
      ctx.fillStyle='#ffffff'; ctx.textBaseline='middle'; ctx.textAlign='left';
      ctx.fillText(txt,bx+5,by+bh/2+0.5);
      placed.push({x1:bx,x2:bx+bw,y1:by,y2:by+bh});
    });
    ctx.restore();
  }
});

/* 线图面积填充：默认垂直渐变（顶部浓 → 底部透明）；传 alpha 则返回平铺半透明纯色，用于降低填充视觉权重 */
function vg(ctx, hex, alpha){
  const c=hex.replace('#','');
  const r=parseInt(c.slice(0,2),16),g=parseInt(c.slice(2,4),16),b=parseInt(c.slice(4,6),16);
  if(alpha!=null) return `rgba(${r},${g},${b},${alpha})`;
  const a=ctx&&ctx.chart&&ctx.chart.chartArea;
  if(!a) return hex+'18';
  const grd=ctx.chart.ctx.createLinearGradient(0,a.top,0,a.bottom);
  grd.addColorStop(0,`rgba(${r},${g},${b},.26)`);
  grd.addColorStop(1,`rgba(${r},${g},${b},.01)`);
  return grd;
}

const DIMS = {
  supply:{name:"供给侧",color:"#2563eb",
    note:"真实数据：库欣原油库存（PET.W_EPC0_SAX_YCUOK_MBBL.W）、全美商业原油库存（PET.WCESTUS1.W）、美国原油产量、炼厂开工率来自 EIA 周报；OPEC 原油产量来自 EIA 短期能源展望（STEO）API 的 COPR_* 序列（11 国分项，不含阿联酋）；OPEC 有效剩余产能来自 EIA 短期能源展望（STEO，COPS_OPEC_R05）；全球钻井平台数（World Rig Count）来自 Baker Hughes 官方月度/历史报告。库存周度意外是短线最重要扰动之一。投机持仓与期货期限结构属原油金融/情绪侧信号，已归入「地缘政治」维度（CFTC 持仓报告 + Brent 期货曲线）。",
    groups:[
      {id:"prodcap",title:"产量与产能",desc:"供给能力的核心：美国本土产量与 OPEC 联盟产量。",
        charts:[
          {id:"prod",title:"美国原油产量 (百万桶/日, 周度)",key:"eia.prod",type:"line",level:true,yPadding:0.08,niceY:true,yTicks:6,fillAlpha:0.2,wFrom:"2024-01",
            // 事件竖线：与 Non-OPEC DoC 图的 markLine 风格一致（灰虚线 + 顶部标签）。
            // 单条竖线落在事件起点；文字为事件名。
            // ① 2026-10-07 飓风 Isaias：墨西哥湾离岸油田预防性停产，10-09/10-16 产量连续下滑（看板新闻流 10-07~10-21 连贯记录）。
            // ② 2024-01-13 冬季风暴 Heather：零下气温致 Permian 盆地井口/设备冻结、Bakken freeze-off，01-19 当周产量 13.3→12.3 mb/d，01-26 反弹回 13.0（路透/John Kemp、East Daley 一致口径）。
            events:[
              {date:"2026-10-07",label:"飓风 Isaias"},
              {date:"2024-01-13",label:"冬季风暴 Heather"}],

            source:"<b>数据源：</b>EIA 周度石油周报 API（序列 PET.WCRFPUS2.W）· 实时抓取脚本 src/fetch/supply/eia_weekly.py"},
          {id:"worldq",title:"全球原油产量 (百万桶/日, 月度)",key:"steoWorld",type:"line",monthly:true,fillAlpha:0.12,source:"<b>数据源：</b>EIA STEO 月度 API（序列 COPR_WORLD / COPR_OPEC / COPR_NONOPEC）· 实时抓取脚本 src/fetch/supply/steo_monthly.py"},
          {id:"nonopecdoc",title:"Non-OPEC DoC 原油产量 (百万桶/日, 月度)",key:"nonOpecDoCTotal",type:"line",monthly:true,fillAlpha:0.2,source:"<b>数据源：</b>EIA STEO 月度 API（序列 COPR_OPECPLUS_OTHER ＋ DoC 10 国分项）· 实时抓取脚本 src/fetch/supply/steo_monthly.py"},
          {id:"opec",title:"OPEC 原油产量 (百万桶/日, 月度)",key:"opecMonthly",type:"line",monthly:true,fillAlpha:0.2,source:"<b>数据源：</b>EIA STEO 月度 API（序列 COPR_OPEC ＋ OPEC 11 国分项）· 实时抓取脚本 src/fetch/supply/steo_monthly.py"}]},
      {id:"sparecap",title:"OPEC 剩余产能缓冲",desc:"剩余产能是油市的缓冲垫：越低说明吸收供给冲击的能力越弱、溢价越高。采用柱状图：月度存量是离散量，逐月一根柱比连线更能读出单月变化。2026-03 起剩余产能实际降至 0，2027-04 起 EIA 预测回升至 2.35。",
        charts:[
          {id:"spare",title:"OPEC 有效剩余产能 / Brent 月均价 (百万桶/日 vs 美元/桶, 月度)",key:"opecSpare",type:"line",monthly:true,source:"<span class=\"sline\"><b>数据源：</b>EIA 短期能源展望（STEO）API（序列 COPS_OPEC_R05）· 实时抓取脚本 src/fetch/supply/opec_spare.py；Brent 月均价 = EIA 日度现货 PET.RBRTE.D 的自然月算术均值，抓取脚本 src/fetch/prices.py</span><span class=\"sline\"><b>注解：</b>蓝柱=有效剩余产能（EIA 实际值），橙柱=EIA 预测段（2027-04 起）；剩余产能是油市缓冲垫，归零后市场失去吸收供给冲击的余量。</span><span class=\"sline\"><b>双轴：</b>紫线=Brent 月均价（右轴，美元/桶）；柱压到 0 附近时油价往往抬升，两条曲线的背离比单看柱子更能读出紧平衡。</span>"}]},
      {id:"inv",title:"库存指标",desc:"周度实际累库/去库：短线最重要扰动之一。",
        charts:[
          {id:"cushing",title:"库欣原油库存 (百万桶, 周度)",key:"eia.cushing",type:"linebar",level:true,fillAlpha:0.2,wFrom:"2024-01",source:"<span class=\"sline\"><b>数据源：</b>EIA 周度石油周报 API（序列 <b>PET.W_EPC0_SAX_YCUOK_MBBL.W</b> = Cushing, OK Ending Stocks excluding SPR of Crude Oil）· 抓取脚本 src/fetch/supply/eia_weekly.py</span><span class=\"sline\"><b>注解：</b>库欣是 WTI 交割地，这张图衡量的是交割地的挤仓/宽松压力；数值在 22–30 百万桶量级。</span><span class=\"sline\"><b>双轴：</b>蓝线=库存水平（左轴），红/绿柱=较上周增减（右轴）红柱为累库、绿柱为去库，0 线即两者分界；柱高看单周变化幅度，连续多周同色才构成趋势。</span>"},
          {id:"total",title:"全美商业原油库存 (百万桶, 周度)",key:"eia.total",type:"linebar",level:true,fillAlpha:0.2,wFrom:"2024-01",source:"<span class=\"sline\"><b>数据源：</b>EIA 周度石油周报 API（序列 <b>PET.WCESTUS1.W</b> = U.S. Ending Stocks <u>excluding SPR</u> of Crude Oil）· 抓取脚本 src/fetch/supply/eia_weekly.py</span><span class=\"sline\"><b>注解：</b>全美商业库存反映整体供需，不含战略储备（SPR），425–430 百万桶量级。</span><span class=\"sline\"><b>双轴：</b>蓝线=库存水平（左轴），红/绿柱=较上周增减（右轴）红柱为累库、绿柱为去库，0 线即两者分界；柱高看单周变化幅度，连续多周同色才构成趋势。</span>"},
          {id:"oecd",title:"OECD 商业库存：原油 / 成品油 (百万桶, 月度)",key:"oecdCrude",type:"line",level:true,monthly:true,fillAlpha:0.2,source:"<span class=\"sline\"><b>数据源：</b>OPEC 月度石油市场报告（MOMR）表 9-1（IEA 口径）的 Crude oil 与 Products 两行 · 提取脚本 src/fetch/supply/oecd_stocks.py</span><span class=\"sline\"><b>注解：</b>OECD 国家合计的商业库存，含原油与成品油、不含战略储备；成品油行含石化产品、本身不含原油。</span><span class=\"sline\"><b>同轴：</b>蓝实线=商业原油库存（1,313 百万桶），青虚线=成品油库存（1,451 百万桶）；两序列量级接近（成品油≈原油的 1.1 倍、占合计 52%）。</span>"},
          {id:"usspr",title:"美国战略石油储备 SPR·原油 (百万桶, 周度)",key:"eia.spr",type:"linepct",level:true,fillAlpha:0.2,wFrom:"2024-01",source:"<span class=\"sline\"><b>数据源：</b>EIA 周度石油周报 API（序列 PET.WCSSTUS1.W = U.S. Ending Stocks of Crude Oil in SPR）· 抓取脚本 src/fetch/supply/eia_weekly.py</span><span class=\"sline\"><b>注解：</b>SPR 是国家战略储备，平时不参与商业流通；含 SPR 的原油总库存 gross = 全美商业库存 + SPR。</span><span class=\"sline\"><b>双轴：</b>蓝线=SPR 库存水平（左轴），橙虚线=SPR 占原油总库存比重（右轴）；占比抬升说明商业库存去化更快、SPR 缓冲垫相对变薄。</span>"}]},
      {id:"lead",title:"前瞻性指标",desc:"领先信号：全球活跃钻井平台数（Baker Hughes World Rig Count）通常领先原油产量约 6–12 个月。",
        charts:[
          {id:"rig",title:"全球旋转钻井平台数 World Rig Count (台, 月度)",key:"rigWorld",type:"line",monthly:true,fillAlpha:0.2,ecH:420,source:"<b>数据源：</b>rigcount.bakerhughes.com Worldwide Rig Count Excel 文件解析而来 · 提取脚本 src/fetch/supply/rig_count.py<br/><b>口径提示：</b>2024-01 起 Baker Hughes 明细并入沙特 <b>Operating Rigs</b>（约 +263 台），官方 Worldwide = Active + Operating；此前为 Active 口径，<b>前后两段不可直接比较</b>（2023-12 = 1,739 → 2024-01 = 2,002，+15% 为口径台阶，非真实跳升）。"}]}
    ]},
  demand:{name:"需求侧",color:"#16a34a",
    note:"真实数据：宏观先行指标（制造业 PMI 中美欧 + 全球 GDP 增速预期）用于前瞻原油需求；中游炼厂高频（裂解价差 + 中美炼厂开工/加工）刻画供给端景气度；表观消费指标（美国成品油供应量 + 中国原油进口量）反映终端需求的实物侧强度。三者并列构成需求侧的核心观测维度。",
    macroGroups:[
      {id:"macro_leading",title:"宏观先行指标",desc:"制造业 PMI 盯中美欧三大经济体（荣枯线 50）；全球 GDP 增速预期采用 IMF WEO 各期次预测，并展示逐期修订路径。",
        charts:[
          {id:"pmi",title:"制造业 PMI： 美 /中 / 欧 (%, 月度)",key:"pmi",type:"line",monthly:true,ec:true,ecH:320,
            source:"<b>数据源：</b>美国 ISM / 中国 PMI / 欧元区 HCOB（data/raw/pmi_manufacturing.xlsx 手动）·维护脚本 src/fetch/demand/pmi_gdp.py"},
          // ⚠️ 页尾的 {latest} 是占位符，渲染时由 STATE.imfWoeMeta.latestLabel 替换成真实期次
          //    （如「2026 年 10 月 13 日更新（WEO October 2026）」）—— 不要再在这里写死期次。
          {id:"gdp",title:"IMF《WEO》全球 GDP 增速预测（逐期修正） (%)",key:"woeRev",type:"line",ec:true,ecH:320,
            source:"<b>数据源：</b>IMF《世界经济展望》{latest}，逐期（1/4/7/10 月）对 2026 / 2027 年全球增速的预测值 · 维护脚本 src/fetch/demand/pmi_gdp.py"}]}
    ],
    refineryGroups:[
      {id:"refinery",title:"中游炼厂高频指标",desc:"裂解价差反映炼厂利润与需求强度；炼厂开工率（美国，EIA 周度）与原油加工量（中国，国家统计局月度）刻画中美炼厂端高频景气度。",
        charts:[
          {id:"crack",title:"裂解价差 $/bbl（月度均值）",key:"crack",type:"bar",mFrom:"2024-01",
            source:"<b>数据源：</b>EIA 美国常规汽油零售价 × 42 − WTI 实时价派生（无独立抓取脚本，渲染时由 build_html.py 计算）"},
          {id:"util",title:"炼厂开工率（美国） / 原油加工量（中国）",key:"refinery",type:"refinery",
            source:"<b>数据源：</b>美国 EIA 周度石油周报 API（序列 PET.WPULEUS3.W）（月度均值）+ 中国原油加工量（data/raw/cn_crude_import and processing.xlsx 手动）· 抓取/维护脚本 src/fetch/demand/refinery.py"}]}
    ],
    apparentGroups:[
      {id:"apparent",title:"表观消费指标",desc:"美国成品油供应量（周度，Mb/d）vs 中国原油进口（月度，万吨）。单位与频率不同，分图对照，共同反映中美原油需求的实物侧强度。",
        charts:[
          {id:"gas",title:"美国汽油成品油供应量 (百万桶/日, 周度)",key:"eia.gasSupplied",type:"line",yPadding:0.22,wFrom:"2024-01",
            source:"<b>数据源：</b>EIA 周度石油周报 API（序列 PET.WGFUPUS2.W）· 实时抓取脚本 src/fetch/supply/eia_weekly.py"},
          {id:"cnimp",title:"中国原油进口量（海关，万吨/月）· 分年度",key:"cnCrudeImport",type:"line",monthly:true,
            source:"<b>数据源：</b>中国原油进口量（data/raw/cn_crude_import and processing.xlsx 手动）· 提取脚本 src/fetch/demand/refinery.py"}]}
    ]},
  geo:{name:"地缘政治",color:"#dc2626",
    note:"<b>地缘与情绪恐慌指数 I_geo（0–4，下限为 0：地缘只提供做多溢价，不提供做空动能）</b> = Score(OVX) + Score(Brent–WTI 价差) + Score(剩余产能)。规则：OVX &gt;45→+2、35–45→+1、&lt;30→0（30–35 缺口按 0）；价差 &gt;$7→+1（3–5 正常、5–7 及 &lt;$3 缺口按 0）；剩余产能 &lt;200 万桶/日→+1、&gt;400 万桶/日→0（200–400 缺口按 0）。剩余产能采用 EIA OPEC 有效剩余产能（COPS_OPEC_R05，≈全球有效剩余产能，非 OPEC 可忽略）作代理；模型原文标注 IEA 口径，两者当前均使该分项 = 0。归一化风险 = I_geo/4×100，已并入「各维度风险贡献」与综合风险。"
      + "<br><b>原油专属投机与期限结构（I_geo 候选补充信号，当前仅作观测、未计入评分）：</b>① <b>ICE 布伦特投机净持仓（Managed Money）</b>取自 CFTC 持仓报告（disaggregated）管理基金多头−空头，是非商业/投机头寸的现代口径代理；净多扩张=看涨情绪、净空=常对应价格底部。② <b>Brent 12 个月期限结构（近月−远月）</b>为正=backwardation（近端溢价、即期偏紧、地缘/供给风险溢价高），为负=contango（近端宽松、库存充裕）。两者口径与 I_geo 同源互补，后续可纳入恐慌系数。",
    main:{title:"Brent–WTI 价差 $/bbl",key:"spread_bw",type:"line"},
    sub:{title:"OVX 原油波动率指数",key:"ovx",type:"line"},
    pos:{title:"ICE 布伦特 投机净持仓（Managed Money）",key:"brentCot",type:"line"},
    term:{title:"Brent 12个月期限结构（近月−远月）",key:"brentTerm",type:"line"},
    third:{title:"地缘恐慌系数 I_geo（0–4）",key:"igeo",type:"line"}},
  macro:{name:"宏观金融",color:"#d97706",
    from:"2024-01",   // 利率/汇率两张图都回溯到 2024-01，不走 RANGE=252 滚动窗口
    note:"<b>利率端：</b>联邦基金有效利率（政策基准，阶梯式只在议息日跳变）与 10 年期美债收益率（长端，已 price-in 政策预期）同轴对照（左轴 %），两线之间的填充带表示利差大小；第三条<b>期限利差 10Y−DFF</b>走右轴（bp，虚线），<b>跌破零线即倒挂</b>——意味着市场预期央行未来必须降息，该区间的虚线转红。<b>汇率端：</b>广义美元指数水平与 5 日变动率分列左右轴——油价以美元计价，美元走强通常压制油价（负相关）。",
    main:{title:"联邦基金有效利率 DFF 与 10年期美债收益率 %",key:"dff",key2:"dgs10",type:"rate"},
    sub:{title:"广义美元指数（DTWEXBGS）与 5日变动 %",type:"dxydual"}},
  other:{name:"其他突发",color:"#7c3aed",
    groups:[
      {id:"jump",title:"突发跳变事件",desc:"Brent 单日跳变>2.5% 的真实检测事件及其月度频次。",
        charts:[
          {id:"evt",title:"Brent 价格与突发跳变标记",key:"brent",type:"events"},
          {id:"evtbar",title:"月度突发跳变次数",type:"eventbar"}
        ]},
      {id:"vol",title:"波动率",desc:"Brent 20日年化波动率与日度波动率日历热力图。",
        charts:[
          {id:"vol20",title:"Brent 20日年化波动率 %",key:"vol20",type:"line"},
          {id:"heat",title:"波动率日历热力图（日度）",type:"heat"}
        ]}
    ]},
};

/* 防呆：元素缺失时返回 no-op 代理，避免整页渲染崩溃（多为浏览器缓存了旧版本导致）。
   ⚠️ 代理会**静默吞掉**所有读写 —— 连 `if($(id))` 也恒为真（对象是 truthy），
   所以仅靠 console.warn 极易被忽略。故三管齐下：
     ① 每个缺失 id 只在控制台告警一次；
     ② 代理暴露 `__missing` 标记，便于调用方主动识别；
     ③ 页面顶部挂一条可见横幅，直接告诉用户硬刷新。 */
function showMissingBanner(ids){
  let el=document.getElementById("__missbanner");
  if(!el){
    el=document.createElement("div");
    el.id="__missbanner";
    el.style.cssText="position:fixed;left:0;right:0;top:0;z-index:9999;padding:8px 12px;"
      +"background:#dc2626;color:#fff;font:13px/1.5 system-ui,-apple-system,sans-serif;text-align:center";
    (document.body||document.documentElement).appendChild(el);
  }
  el.textContent="页面模板缺少元素 #"+ids.join(", #")+" —— 多半是浏览器缓存了旧版，请硬刷新（Cmd/Ctrl+Shift+R）";
}
function $(id){
  const e=document.getElementById(id);
  if(e)return e;
  if(!window.__miss)window.__miss={};
  if(!window.__miss[id]){
    window.__miss[id]=1;
    console.warn("[dashboard] 缺失元素 #"+id+" — 多半是浏览器缓存了旧版，请硬刷新（Cmd/Ctrl+Shift+R）");
    showMissingBanner(Object.keys(window.__miss));
  }
  return new Proxy({},{get:(t,p)=>{
    if(p==="__missing")return true;
    if(p==="style")return {};
    if(p==="classList")return {add(){},remove(){},toggle(){}};
    if(p==="value")return "";
    return ()=>{};
  },set:()=>true});
}
/* 皮尔逊相关系数（与 src/common/series.py::pearson 同口径：有效配对 < 5 组返回 null）。 */
function pearson(a,b){
  const n=Math.min(a.length,b.length);
  let cnt=0,sx=0,sy=0;
  for(let i=0;i<n;i++){ if(a[i]!=null&&b[i]!=null){ cnt++; sx+=a[i]; sy+=b[i]; } }
  if(cnt<5)return null;
  const mx=sx/cnt,my=sy/cnt;
  let num=0,dx=0,dy=0;
  for(let i=0;i<n;i++){ if(a[i]!=null&&b[i]!=null){ const x=a[i]-mx,y=b[i]-my; num+=x*y; dx+=x*x; dy+=y*y; } }
  dx=Math.sqrt(dx); dy=Math.sqrt(dy);
  return (dx&&dy)?num/(dx*dy):null;
}
/* 对称相关方阵：只算上三角（含对角线）再镜像，pearson 调用 n(n+1)/2 次而非 n² 次。 */
function corrMatrix(list){
  const n=list.length, m=[];
  for(let i=0;i<n;i++){ m.push(new Array(n).fill(null)); }
  for(let i=0;i<n;i++){ for(let j=i;j<n;j++){ const v=pearson(list[i],list[j]); m[i][j]=v; m[j][i]=v; } }
  return m;
}
function lastVal(a){if(!a)return null;for(let i=a.length-1;i>=0;i--)if(a[i]!=null)return a[i];return null;}
function lv2(a){return a?lastVal(a):null;}
function pctChg(a){
  // 末值 vs 约 252 个观测之前的第一个非空值（1 年近似）
  const v=lastVal(a);
  if(v==null)return null;
  const j=Math.max(0,a.length-252);
  for(let i=j;i<a.length;i++){ const b=a[i]; if(b)return (v/b-1)*100; }
  return null;
}
function sliceN(arr,n){if(!arr)return [];return arr.slice(Math.max(0,arr.length-n));}
/* ---------- x 轴时间标签统一格式（全站唯一定义，禁止各处自己 replace） ----------
   规则：年月 → 年/月 各两位  2024-01 → 24/01
        年月日 → 年/月/日 各两位  2024-01-05 → 24/01/05
   非时间标签（年度 2024、月份序号 01、数值轴）原样返回，由调用方决定是否另作处理。 */
function fmtX(v){
  if(typeof v!=="string") return v;
  if(/^\d{4}-\d{2}-\d{2}$/.test(v)) return v.slice(2,4)+"/"+v.slice(5,7)+"/"+v.slice(8,10);
  if(/^\d{4}-\d{2}$/.test(v)) return v.slice(2,4)+"/"+v.slice(5,7);
  return v;
}
// Chart.js x 轴 ticks 配置：n=最大刻度数，lb=标签数组（按 index 取值后走 fmtX），slant=45°倾斜
function xTime(n,lb,slant){
  const t={maxTicksLimit:n,callback:function(value){return fmtX(lb?lb[value]:value);}};
  if(slant) Object.assign(t,{maxRotation:45,minRotation:45,autoSkip:true});
  return t;
}
// 带正负号的刻度/读数（右轴「周增减」专用）：0 不加号，避免「+0」这种噪音
function labelSign(v){return (v>0?"+":"")+v;}

/* ---------- 最新值 + 数据截止日（review 第 6 条） ----------
   背景：供给侧各图频率与滞后都不同（EIA 周度 / OPEC 月度 / OECD 月度 / Rig 月度…），
   而页面顶部那条「数据截至 X」只是 Brent 价格序列的末日，与它们无关 —— 读者会把
   OECD（落后 2 个月）误当成当期值。故按图逐个标注。
   口径（2026-10-07 定）：截止日 = 该序列**最后一个非空值对应的日期**，
   不是今天、也不是官方发布日。v 返回 null 时只标日期（合成图无法归属到单一数值）。 */
function fmtNum(v,n){return v==null?"—":v.toLocaleString("en-US",{minimumFractionDigits:n,maximumFractionDigits:n});}
// ⚠️ 值数组与日期数组一律**尾部对齐**：eiaDates 从 1982-08 起共 2296 条，而 eia.cushing
// 只有窗口化的 1007 条；opecMonths 也比 STATE.opec 长。若按下标 0 对齐，库欣会被标成
// 「截至 02/01/11」这种荒谬日期。故统一取 off = d.length - v.length，从尾部对齐。
function asOf(v,d){
  if(!v||!d||!v.length) return "";
  const off=Math.max(0,d.length-v.length);
  for(let i=v.length-1;i>=0;i--) if(v[i]!=null) return fmtX(String(d[i+off]));
  return "";
}
/* ⚠️ eia.* 徽章必须**与曲线同源**：图上画的是原生周度轴（eiaAxis 用 STATE.eiaWeekly + eiaDates），
     徽章也用「周度值 + 周轴」。这里踩过两次坑（2026-10-07）：
       1) 曾用日度数组（STATE.eia[name]）+ 日轴 STATE.dates → 「截至」落到日轴末日
          （SPR 值其实观测于 09-25，却被标成 10-05，等于凭空往后推了 10 天）；
       2) 又改成日度数组 + 周轴 → 离线快照下周轴(1982 起 2296 点)比日轴长，asOf 尾部对齐恰好蒙对；
          但「拉取实时」后周轴塌成十几个点、日轴几百点，off 被 Math.max(0,…) 夹成 0、i+off 越界，
          徽章整片变空。
     周度值长度恒等于 eiaDates（python 侧 build_axes 与前端 fetchEIA 都按同一周网格产出），
     离线/实时两种口径下对齐都成立；eia.* 的取数拿不到周度值时才回退日度数组。 */
const eiaStat=(n,digits)=>({
  v:()=>((STATE.eiaWeekly&&STATE.eiaWeekly[n])||(STATE.eia&&STATE.eia[n])||null),
  d:()=>STATE.eiaDates, n:digits||1
});
// 截取到**末个历史月**（不含 STEO 预测段）：用于把徽章标在**实际值**上，而不是预测值上。
// ⚠️ steoLastHistorical 由 STEO API 分国行的**最后非空月**推导（如 "2026-09"，2026-10-16 起）。
//    2026-10-11 用户要求：徽章改标最新实际值（26/09），不再标预测段末点（27/12）。
//    statText 取「最后一个非空值」，故只要把 v/d 都截断到历史段即可，不必改 statText 本身。
function steoHistCut(arr){
  const a=arr||[], m=STATE.steoMonths||[];
  const i=(STATE.steoLastHistorical!=null)?m.indexOf(STATE.steoLastHistorical):-1;
  return (i>=0)?a.slice(0,i+1):a;
}
const STAT_MAP={
  "eia.prod":        eiaStat("prod",2),
  "eia.cushing":     eiaStat("cushing"),
  "eia.total":       eiaStat("total"),
  "eia.gasSupplied": eiaStat("gasSupplied",2),
  // OPEC 原油产量图徽章。⚠️ 2026-10-11 换源：原走 STATE.opecMonthly（MOMR 12 国 {month:v}，
  // 末点 2026-08 = 24.08），现走 **STEO API 的 OPEC 合计 COPR_OPEC**——即 STATE.steoOpecMonthly
  // （与 API 的 OPEC 11 国分项逐月相加恒等，脚本内自验）。
  // 经 steoHistCut 截到末个历史月（2026-09 = 20.80）→「合计 20.80 · 截至 26/09」。
  // 11 国 ≠ MOMR 12 国口径（少阿联酋），与旧徽章数值不可直接对比。
  // ⚠️ 不能误用 STATE.opec —— 那是**年度**序列（opecYears 2022/23/24/25），与月度轴无关。
  "opecMonthly":     {v:()=>steoHistCut(STATE.steoOpecMonthly),
                     d:()=>steoHistCut(STATE.steoMonths), n:2, tag:"合计 "},
  // OPEC+ 非 OPEC 参与国（DoC 10 国）合计徽章。⚠️ 2026-10-11 换源：原走
  // STATE.nonOpecDoCTotal（MOMR {month:v}，末点 2026-08 = 13.97），现走 **STEO API 的
  // COPR_OPECPLUS_OTHER**（STATE.steoDoCTotal 纯数组，与 steoMonths 同轴）。
  // 经 steoHistCut 截到末个历史月（2026-09 = 14.05）→「合计 14.05 · 截至 26/09」。
  // ⚠️ 合计行本身有预测段（2026-10 起到 27/12），但徽章按全站惯例只标实际值。
  "nonOpecDoCTotal": {v:()=>steoHistCut(STATE.steoDoCTotal),
                     d:()=>steoHistCut(STATE.steoMonths), n:2, tag:"合计 "},
  // 全球月度（EIA STEO API 的 COPR_* 序列）。2026-10-10 起由**季度**改**月度**：值是纯数组，
  // 与 STATE.steoMonths 等长（72 个月 2022-01~2027-12），不再从 {quarter:{}} 里取。
  // ⚠️ 徽章只标**历史段末点**（2026-09 实际值 75.97），不标预测段末点（2027-12 = 82.97）：
  //    v/d 都经 steoHistCut 截断到 steoLastHistorical，prep 走默认「截至」（不写「预测至」）。
  "steoWorld":      {v:()=>steoHistCut(STATE.steoWorldMonthly),
                     d:()=>steoHistCut(STATE.steoMonths), n:2},
  // 剩余产能尾部是 EIA 18 个月滚动预测，最后一点不是实际值 → 用「预测至」而非「截至」
  "opecSpare":       {v:()=>STATE.opecSpare,                  d:()=>STATE.opecSpareMonths,n:2, prep:"预测至 "},
  "oecdCrude":       {v:()=>STATE.oecdCrude,                  d:()=>STATE.oecdMonths,     n:0, tag:"原油 "},
  // SPR 图上走原生周度轴画曲线，徽章同源（周度值 + 周轴），截至到最后一个真实观测周
  "eia.spr":         eiaStat("spr"),
  "rigWorld":        {v:()=>STATE.rigWorld,                   d:()=>STATE.rigMonths,      n:0},
  // PMI 卡是美/中/欧三条线，徽章只标美国那条 → 加 tag 消歧
  "pmi":             {v:()=>STATE.pmiUS,                      d:()=>STATE.pmiMonths,      n:1, tag:"美 "},
  "gdp":             {v:()=>STATE.gdpValues,                  d:()=>STATE.gdpYears,       n:1, prep:"预测至 "},
  "crack":           {v:()=>STATE.crack,                      d:()=>STATE.dates,          n:1},
  "cnCrudeImport":   {v:()=>STATE.cnImport,                   d:()=>STATE.cnImportMonths, n:0},
  // 合成图（美国开工率 + 中国加工量两条线共用 usUtilMonths）：只标日期，不标值
  "refinery":        {v:()=>null, d:()=>STATE.usUtilMonths, n:0,
    probe:()=>{const a=STATE.usUtil||[],b=STATE.cnProc||[],o=[];
      const n=Math.max(a.length,b.length);
      for(let i=0;i<n;i++) o.push((a[i]!=null||b[i]!=null)?1:null);
      return o;}}
};
function statText(key){
  const s=STAT_MAP[key];
  if(!s) return "";
  const ds=s.d()||[];
  const vs=s.v?s.v():null;            // 可能为 null（合成图只标日期）
  const probe=s.probe?s.probe():null; // 找末点用的探针数组，缺省用值数组本身
  const arr=(probe&&probe.length)?probe:(vs||[]);
  if(!ds.length||!arr.length) return "";
  const off=Math.max(0,ds.length-arr.length);
  let i=-1;
  for(let k=arr.length-1;k>=0;k--){ if(arr[k]!=null){ i=k; break; } }
  if(i<0||i+off>=ds.length) return "";
  const v=vs?vs[i]:null;              // ⚠️ vs 可能为 null，不能写 vs[i]（会抛 "reading 'i'"）
  const d=(s.prep||"截至 ")+fmtX(String(ds[i+off]));
  return (v!=null?(s.tag||"")+fmtNum(v,s.n||0)+" · ":"")+d;
}
function fillStats(){
  document.querySelectorAll(".cstat").forEach(function(el){
    el.textContent=statText(el.getAttribute("data-stat"))||"";
  });
}
// 按起始日期截取展示窗口：from 形如 "2024-01"（月）或 "2024-01-01"（日），
// 缺省时仍走 RANGE=252 的滚动窗口（windowDates/sliceN 的既有行为）。
// 说明：底层数据一律从 config.START_DATE(2024-01-01) 抓全量，RANGE 只控制可见区间，
// 因此这里不需要重新抓数，只需放开窗口即可回溯到 2024 年 1 月。
function sliceFrom(arr, from){
  if(!arr || !arr.length) return [];
  if(!from) return sliceN(arr, RANGE);
  const all=STATE.dates||[];
  let i=all.findIndex(d=>typeof d==="string" && d>=from);
  if(i<0) i=0;
  const off=Math.max(0, all.length-i);          // 从序列末尾往前数 off 个点
  return arr.slice(Math.max(0, arr.length-off));
}
// 取序列并按窗口裁剪（from 为空则回落 RANGE=252）
function gsFrom(key, from){ const s=getSeries(key); return from?sliceFrom(s,from):sliceN(s,RANGE); }
// 生成「整齐且严格等距」的 y 轴范围：返回 {min,max,stepSize}；数据不足返回 null。
// 做法：先按 padRatio 向两侧留白，再把 min/max 吸附到整齐步长（1/2/2.5/5/10 x 10^k）的整数倍。
// 这样轴的两个端点都落在刻度上，含首尾在内的每一格间距完全相同（否则端点落在刻度之间会首尾格偏窄）。
function niceYScale(arr,padRatio,maxTicks){
  const v=(arr||[]).filter(x=>x!=null&&isFinite(x));
  if(v.length<2) return null;
  let mn=Math.min.apply(null,v), mx=Math.max.apply(null,v);
  const pad=(mx-mn)*(padRatio||0);
  mn=mn-pad; mx=mx+pad;
  if(Math.min.apply(null,v)>=0 && mn<0) mn=0;          // 非负序列不穿 0
  const span=mx-mn;
  if(!(span>0)) return null;
  const raw=span/Math.max(1,((maxTicks||6)-1));
  const mag=Math.pow(10,Math.floor(Math.log(raw)/Math.LN10));
  const frac=raw/mag;
  const step=(frac<=1?1:frac<=2?2:frac<=2.5?2.5:frac<=5?5:10)*mag;
  const q=Math.max(0,Math.round(-Math.log(step)/Math.LN10))+1;   // 步长小数位，消除浮点尾巴
  const lo=Math.floor(mn/step)*step, hi=Math.ceil(mx/step)*step;
  return {min:parseFloat(lo.toFixed(q)),max:parseFloat(hi.toFixed(q)),stepSize:parseFloat(step.toFixed(q))};
}
function windowDates(){return sliceN(STATE.dates,RANGE);}
// 兼容顶层键与嵌套键（如 "eia.cushing"）
function getSeries(key){if(key==null)return null;if(key.indexOf(".")<0)return STATE[key];let o=STATE;for(const p of key.split(".")){o=o==null?null:o[p];}return o;}
// 周度轴的窗口起点：默认取近 1 年（与日度 RANGE≈1 年大致对齐），图表可配 wFrom（起始年月）
// 覆盖以展示更长历史。周轴本身可回溯至 1982 年，默认只取近 1 年；wFrom 只放大、不缩小窗口。
// ⚠️ 抽成独立函数是为了让「分子分母同源切片」有唯一出处：派生序列（如 gross）必须
//    与它参与计算的序列取**同一个 i0**，否则左右轴的比值会整体错位。
function eiaI0(opt){
  if(!STATE.eiaDates||!STATE.eiaDates.length) return 0;
  let i0=Math.max(0,STATE.eiaDates.length-Math.max(12,Math.round(RANGE/5)));
  if(opt&&opt.wFrom){
    const k=STATE.eiaDates.findIndex(function(d){return d.slice(0,7)>=opt.wFrom;});
    if(k>=0) i0=Math.min(i0,k);
  }
  return i0;
}
// EIA 序列优先使用「原生周度坐标轴」（如已拉取），否则回退日度轴；实时拉取后周轴自动延伸
function eiaAxis(key, opt){
  if(!key||key.indexOf("eia.")!==0)return null;
  const name=key.split(".")[1];
  if(STATE.eiaDates&&STATE.eiaDates.length&&STATE.eiaWeekly&&STATE.eiaWeekly[name]){
    const i0=eiaI0(opt);
    return {dates:STATE.eiaDates.slice(i0), data:STATE.eiaWeekly[name].slice(i0)};
  }
  return null;
}
/* 派生序列取数（当前只有 gross = 全美商业库存 total + SPR，EIA 口径逐周恒等）。
   ⚠️ 只能走**周度**数组（eiaWeekly）并按 eiaI0(c) 切片：日度 STATE.eia.gross 的长度是
      日度轴长度，与周度折线索引对不上，拿它算比值会得到一串错位到离谱的百分比。 */
function eiaGrossWeekly(c){
  const w=STATE.eiaWeekly||{};
  const i0=eiaI0(c);
  // 目标长度 = 折线（同一窗口的周度序列）长度；长度对不上就判为「取不到」，不让错位数据混进比值
  const n=((STATE.eiaDates&&STATE.eiaDates.length?STATE.eiaDates.length:0)-i0);
  const sameLen=(a)=>(Array.isArray(a)&&a.length===n)?a:null;
  let g=sameLen((w.gross||[]).slice(i0));
  if(!g&&w.total&&w.spr){
    const t=w.total,s=w.spr;
    // 兜底：任一路派生漏算 gross 时按恒等式现算，右轴仍有值（python 与前端各算一份，理论上不会走到）
    g=sameLen(t.map(function(v,i){return (v!=null&&s[i]!=null)?v+s[i]:null;}).slice(i0));
  }
  return g;
}

/* ---------- Pearson ---------- */
function pearson(a,b){const pa=[];for(let i=0;i<a.length;i++){if(a[i]!=null&&b[i]!=null)pa.push([a[i],b[i]]);}
  if(pa.length<5)return null;const n=pa.length;let sa=0,sb=0;pa.forEach(p=>{sa+=p[0];sb+=p[1];});
  const ma=sa/n,mb=sb/n;let num=0,da=0,db=0;pa.forEach(p=>{num+=(p[0]-ma)*(p[1]-mb);da+=(p[0]-ma)**2;db+=(p[1]-mb)**2;});
  return (da&&db)?num/Math.sqrt(da*db):null;}

/* ---------- KPI row ---------- */
function renderKPIs(){
  const k=STATE.kpis;
  const ch=k.brent!=null?pctChg(STATE.brent):null;
  const items=[
    {l:"Brent",v:k.brent!=null?"$"+k.brent.toFixed(2):"—",c:ch,up:ch>=0},
    {l:"WTI",v:k.wti!=null?"$"+k.wti.toFixed(2):"—",c:pctChg(STATE.wti),up:pctChg(STATE.wti)>=0},
    {l:"广义美元指数（DTWEXBGS）",v:k.dxy!=null?k.dxy.toFixed(2):"—",c:pctChg(STATE.dxy),up:pctChg(STATE.dxy)>=0},
    {l:"BW价差",v:k.spread_bw!=null?"$"+k.spread_bw.toFixed(2):"—",c:null},
    {l:"波动率",v:k.vol20!=null?k.vol20.toFixed(0)+"%":"—",c:null},
    {l:"综合风险",v:k.composite!=null?k.composite.toFixed(0):"—",c:null},
  ];
  $("kpis").innerHTML=items.map(i=>`<div class="kpi"><div class="l">${i.l}</div><div class="v">${i.v}</div>`+
    (i.c!=null?`<div class="c ${i.up?'up':'down'}">${i.up?'▲':'▼'} ${Math.abs(i.c).toFixed(1)}% (1Y)</div>`:`<div class="c" style="color:var(--sub)">实时</div>`)+
    `</div>`).join("");
  $("asof").textContent="数据截至 "+k.latest_date;
}

/* ---------- Risk gauge ---------- */
function riskLevel(v){if(v<33)return["低","#16a34a"];if(v<55)return["中","#d97706"];if(v<75)return["偏高","#ea580c"];return["高","#dc2626"];}
function renderGauge(){
  const v=STATE.kpis.composite||0;
  const [lbl,col]=riskLevel(v);
  if(charts.gauge)charts.gauge.destroy();
  charts.gauge=new Chart($("gauge"),{type:"doughnut",data:{datasets:[{data:[v,100-v],backgroundColor:[col,"#eef2f7"],borderWidth:0}]},
    options:{rotation:-90,circumference:180,cutout:"72%",plugins:{legend:{display:false},tooltip:{enabled:false}}}});
  $("gaugeval").textContent=v.toFixed(0);$("gaugeval").style.color=col;
  $("gaugelbl").textContent="风险等级："+lbl;
}
/* 各维度风险贡献（当前）—— 2026-10-15 起**缩小合并进「整体风险概览」卡**（原独占一卡，
   该卡位让给 Crude Oil News）。画幅变窄后相应收紧字体/间距，保持五维可辨。 */
function renderRiskBar(){
  const d=STATE.dims;const cur=windowDates();
  const getLast=(arr)=>{const s=sliceN(arr,RANGE);for(let i=s.length-1;i>=0;i--)if(s[i]!=null)return s[i];return 0;};
  const vals=[getLast(d.supply),getLast(d.demand),getLast(d.geo),getLast(d.macro),getLast(d.other)];
  const cols=["#2563eb","#16a34a","#dc2626","#d97706","#7c3aed"];
  if(charts.riskbar)charts.riskbar.destroy();
  charts.riskbar=new Chart($("riskbar"),{
    type:"bar",
    data:{labels:["供给","需求","地缘","宏观","其他"],datasets:[{data:vals,backgroundColor:cols,borderRadius:3,barPercentage:0.82,categoryPercentage:0.9}]},
    options:{
      indexAxis:"y",responsive:true,maintainAspectRatio:false,
      layout:{padding:{left:0,right:4,top:0,bottom:0}},
      interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:false},tooltip:{mode:"index",intersect:false,callbacks:{label:c=>"风险指数 "+c.parsed.x.toFixed(0)}}},
      scales:{
        x:{min:0,max:100,grid:{color:"#eef2f7"},border:{display:false},
           ticks:{font:{size:9},callback:v=>v}},
        y:{grid:{display:false},border:{display:false},ticks:{font:{size:10}}}
      },
      onClick:function(e,c){if(c&&c[0]){const dim=["supply","demand","geo","macro","other"][c[0].index];switchTab(dim);}}
    }
  });
}
/* Crude Oil News —— 2026-10-15 新增，占原「各维度风险贡献（当前）」卡位。
   数据 = data/dataset/news.json 的 crudeNews（**纯手工维护**：Argus 有反爬，
   curl 一律 202/0 字节，无 extract 脚本）。只渲染「标题 + 超链接」，新窗口打开。
   读数回落：STATE 可能被 computeDerived / loadLive 整体替换，故再回落 SNAPSHOT。 */
function renderNews(){
  const el=$("news");
  if(!el) return;
  const raw=((STATE&&STATE.crudeNews)||(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.crudeNews)||[]);
  // **最新在前**：按 date 倒序（Array.prototype.sort 在 V8 里稳定，同日保持原有顺序）
  const list=raw.slice().sort(function(a,b){
    return String((b&&b.date)||"").localeCompare(String((a&&a.date)||""));
  });
  if(!list.length){ el.innerHTML="<div class='newsempty'>暂无原油快讯</div>"; return; }
  el.innerHTML=list.map(function(n){
    const t=(n&&n.title)||"";
    const u=(n&&n.url)||"";
    const d=(n&&n.date)||"";
    const s=(n&&n.source)||"";
    const meta=[d,s].filter(Boolean).join(" · ");
    const titleHtml = u
      ? "<a href='"+esc(u)+"' target='_blank' rel='noopener noreferrer' class='newstitle'>"+esc(t)+"</a>"
      : "<span class='newstitle'>"+esc(t)+"</span>";
    return "<div class='newsitem'>"+titleHtml+(meta?"<div class='newsmeta'>"+esc(meta)+"</div>":"")+"</div>";
  }).join("");
}
/* HTML 转义：标题/URL/来源可能含 & < > " ' ，直接拼进 innerHTML 会破坏结构或注入 */
function esc(v){
  return String(v==null?"":v).replace(/[&<>"']/g,function(c){
    return ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c];
  });
}
/* 卡片右上角 Fetch 按钮：调用本地服务端的 /api/news 做**整页完整抓取**
   （抓 Argus filtered 完整 feed 第一页 ≈ 最近 27 条，服务端按 URL 去重后写回 news.json）。
   ⚠️ 两个使用前提：
     ① 本页必须经 `python run.py serve` 打开才有 /api/news；直接双击静态 HTML 会 404
        （与首屏「拉取实时」按钮同一限制）。
     ② Argus 有 AWS WAF 挑战，服务端直连会被拦；此时返回 blocked=true，
        这里把原因如实显示，**不假装抓取成功**。 */
function fetchNews(btn){
  const st=$("newsstatus");
  const setStatus=(msg,cls)=>{ if(st){ st.textContent=msg||""; st.className="newsstatus"+(cls?" "+cls:""); } };
  if(btn){ btn.disabled=true; btn.textContent="…"; }
  setStatus("正在抓取…");
  fetch("/api/news").then(function(r){ return r.json(); }).then(function(res){
    if(!res || !res.ok){
      const why=(res && res.blocked)
        ? (res.message || "Argus 返回 AWS WAF 挑战页，非浏览器请求取不到新闻")
        : ((res && res.error) || "抓取失败");
      setStatus(why, "warn");
      return;
    }
    const items=res.items||[];
    if(items.length) STATE.crudeNews=items;   // 服务端已去重并按日期倒序
    renderNews();
    setStatus(res.added
      ? ("新增 "+res.added+" 条 · 区间 "+res.since+" → "+res.until)
      : ("已是最新 · 区间 "+res.since+" → "+res.until),
      res.added ? "ok" : "");
  }).catch(function(){
    setStatus("抓取失败：请用 python run.py serve 打开本页（静态页面无 /api/news）", "warn");
  }).then(function(){
    if(btn){ btn.disabled=false; btn.textContent="↻ Fetch"; }
  });
}
function renderAlerts(){
  const list=STATE.alerts||[];
  const sub=list.filter(a=>inWindow(a.date));
  const show=sub.length?sub.slice(0,30):list.slice(0,8);
  $("alerts").innerHTML=show.map(a=>`<div class="alert ${a.level}"><b>[${a.dim}]</b> ${a.msg}<div class="d">${a.date}</div></div>`).join("")
    || "<div class='alert mid'>当前时间窗口内无触发预警</div>";
}
function inWindow(date){const all=STATE.dates;const idx=all.indexOf(date);if(idx<0)return false;return idx>=all.length-RANGE;}

/* ---------- Dimension panels ---------- */
/* 维度页尾：解释该维度指标与油价的关联口径（cfg.footer 可选，缺省则不渲染） */
function dimFooter(cfg){
  const f=cfg.footer;
  if(!f||!f.items||!f.items.length)return "";
  const lis=f.items.map(t=>`<li>${t}</li>`).join("");
  const src=f.src?`<div class="ftsrc">${f.src}</div>`:"";
  // 用维度色做强调色（--fc）与左边框，五个维度复用同一套样式
  const col=cfg.color||"var(--other)";
  return `<div class="dfoot" style="--fc:${col};border-left-color:${col}"><h4>${f.title||"指标与油价的关联"}</h4><ul>${lis}</ul>${src}</div>`;
}

function buildPanels(){
  for(const key of Object.keys(DIMS)){
    const cfg=DIMS[key];
    if(cfg.groups){
      // 分组渲染（如 供给侧 拆成 产量与产能 / 库存指标 / 前瞻性指标）
      const lastMonth=(STATE.steoMonths&&STATE.steoMonths.length)?STATE.steoMonths[STATE.steoMonths.length-1]:"-";
      const lastRig=(STATE.rigMonths&&STATE.rigMonths.length)?STATE.rigMonths[STATE.rigMonths.length-1]:"-";
      const lastOecd=(STATE.oecdMonths&&STATE.oecdMonths.length)?STATE.oecdMonths[STATE.oecdMonths.length-1]:"-";
      const lastSpr=(STATE.usSprMonths&&STATE.usSprMonths.length)?STATE.usSprMonths[STATE.usSprMonths.length-1]:"-";
      const lastSpare=(STATE.opecSpareMonths&&STATE.opecSpareMonths.length)?STATE.opecSpareMonths[STATE.opecSpareMonths.length-1]:"-";
      let groupsHtml="";
      for(const g of cfg.groups){
        const cards=g.charts.map(c=>{
          const boxId="box_"+key+"_"+g.id+"_"+c.id;
          const note=c.note?`<div class="note" style="border:none;background:none;padding:6px 0">${c.note.replace(/\{lastMonth\}/g,lastMonth).replace(/\{lastRig\}/g,lastRig).replace(/\{lastOecd\}/g,lastOecd).replace(/\{lastSpr\}/g,lastSpr).replace(/\{lastSpare\}/g,lastSpare)}</div>`:"";
          return `<div class="card"><h3 class="${hClass(key)}">${c.title}<span class="cstat" data-stat="${c.key}"></span>${rngTgl(key)}</h3><div class="box" id="${boxId}"></div>${note}</div>`;
        }).join("");
        groupsHtml+=`<div class="subgroup"><div class="subhead"><span class="subnum">${g.title}</span>`+(g.desc?`<span class="subdesc">${g.desc}</span>`:"")+`</div><div class="${g.charts.length>1?'grid2':'grid1'}">${cards}</div></div>`;
      }
      $("p_"+key).innerHTML=`
        <div class="card">
          <h3><span class="dot" style="background:${cfg.color}"></span>${cfg.name} · 关键指标</h3>
          <div class="dimkpi" id="dk_${key}"></div>
        </div>
        ${groupsHtml}
        ${dimFooter(cfg)}
        ${cfg.note?`<div class="note">${cfg.note}</div>`:""}`;
      continue;
    }
    let apparentHtml="";
    if(cfg.apparentGroups){
      apparentHtml=cfg.apparentGroups.map(g=>{
        const cards=g.charts.map(c=>{
          const boxId="box_"+key+"_"+g.id+"_"+c.id;
          const note=c.note?`<div class="note" style="border:none;background:none;padding:6px 0">${c.note}</div>`:"";
          return `<div class="card"><h3>${c.title}<span class="cstat" data-stat="${c.key}"></span></h3><div class="box" id="${boxId}"></div>${note}</div>`;
        }).join("");
        return `<div class="subgroup" style="margin-top:14px"><div class="subhead"><span class="subnum">${g.title}</span>`+(g.desc?`<span class="subdesc">${g.desc}</span>`:"")+`</div><div class="${g.charts.length>1?'grid2':'grid1'}">${cards}</div></div>`;
      }).join("");
    }
    const thirdHtml = cfg.third ? `<div class="card" style="margin-top:14px"><h3 class="${hClass(key)}">${cfg.third.title}${rngTgl(key)}</h3><div class="box"><canvas id="t_${key}"></canvas></div></div>` : "";
    const posTermHtml = (cfg.pos||cfg.term) ? `<div class="grid2">
      ${cfg.pos?`<div class="card" style="margin-top:14px"><h3 class="${hClass(key)}">${cfg.pos.title}${rngTgl(key)}</h3><div class="box"><canvas id="pos_${key}"></canvas></div></div>`:""}
      ${cfg.term?`<div class="card" style="margin-top:14px"><h3 class="${hClass(key)}">${cfg.term.title}${rngTgl(key)}</h3><div class="box" id="box_term_${key}"><canvas id="term_${key}"></canvas></div></div>`:""}
    </div>` : "";
    let macroHtml="";
    if(cfg.macroGroups){
      macroHtml=cfg.macroGroups.map(g=>{
        const cards=g.charts.map(c=>{
          const boxId="box_"+key+"_"+g.id+"_"+c.id;
          const note=c.note?`<div class="note" style="border:none;background:none;padding:6px 0">${c.note}</div>`:"";
          return `<div class="card"><h3>${c.title}<span class="cstat" data-stat="${c.key}"></span></h3><div class="box" id="${boxId}"></div>${note}</div>`;
        }).join("");
        return `<div class="subgroup" style="margin-top:14px"><div class="subhead"><span class="subnum">${g.title}</span>`+(g.desc?`<span class="subdesc">${g.desc}</span>`:"")+`</div><div class="${g.charts.length>1?'grid2':'grid1'}">${cards}</div></div>`;
      }).join("");
    }
    const lastUtil=(STATE.usUtilMonths&&STATE.usUtilMonths.length)?STATE.usUtilMonths[STATE.usUtilMonths.length-1]:"-";
    let refineryHtml="";
    if(cfg.refineryGroups){
      refineryHtml=cfg.refineryGroups.map(g=>{
        const cards=g.charts.map(c=>{
          const boxId="box_"+key+"_"+g.id+"_"+c.id;
          const note=c.note?`<div class="note" style="border:none;background:none;padding:6px 0">${c.note.replace(/\{lastUtil\}/g,lastUtil)}</div>`:"";
          return `<div class="card"><h3>${c.title}<span class="cstat" data-stat="${c.key}"></span></h3><div class="box" id="${boxId}"></div>${note}</div>`;
        }).join("");
        return `<div class="subgroup" style="margin-top:14px"><div class="subhead"><span class="subnum">${g.title}</span>`+(g.desc?`<span class="subdesc">${g.desc}</span>`:"")+`</div><div class="${g.charts.length>1?'grid2':'grid1'}">${cards}</div></div>`;
      }).join("");
    }
    const mainHtml = cfg.main ? `<div class="card"><h3 class="${hClass(key)}">${cfg.main.title}${rngTgl(key)}</h3><div class="box"><canvas id="m_${key}"></canvas></div></div>` : "";
    const subHtml = cfg.sub ? `<div class="card"><h3 class="${hClass(key)}">${cfg.sub.title}${rngTgl(key)}</h3><div class="box" id="s_${key}"></div></div>` : "";
    $("p_"+key).innerHTML=`
      <div class="card">
        <h3><span class="dot" style="background:${cfg.color}"></span>${cfg.name} · 关键指标</h3>
        <div class="dimkpi" id="dk_${key}"></div>
      </div>
      ${(cfg.main||cfg.sub)?`<div class="grid2">${mainHtml}${subHtml}</div>`:""}
      ${posTermHtml}
      ${thirdHtml}
      ${macroHtml}
      ${refineryHtml}
      ${apparentHtml}
      ${cfg.note?`<div class="note">${cfg.note}</div>`:""}`;
  }
  // corr panel
  $("p_corr").innerHTML=`
    <div class="grid2">
      <div class="card"><h3>维度指标相关性热力图（当前窗口）</h3><div id="corrHeat"></div>
        <div class="note">红=正相关（同向），蓝=负相关（反向）。例如广义美元指数与油价通常为负相关。</div></div>
      <div class="card"><h3>Brent 价格 × 广义美元指数 散点（联动演示）</h3><div class="box"><canvas id="corrScatter"></canvas></div>
        <div class="note">点越偏右下，体现美元走强→油价走弱的典型反向关系。</div></div>
    </div>`;
}

function dimKPIs(key){
  const cfg=DIMS[key];const last=(arr)=>{const s=sliceN(arr,RANGE);for(let i=s.length-1;i>=0;i--)if(s[i]!=null)return s[i];return null;};
  const map={
    // 单位统一为图标题用的「百万桶 / 百万桶/日」（原先芯片用 Mb / Mb/d，与标题不一致）；
    // 第三项为数据截止日小字（asOf = 序列最后一个非空值对应的日期）。
    supply:(function(){
      const ei=STATE.eia||{}, ed=STATE.eiaDates;
      const g=k=>lv2(ei[k]);
      return [
        ["库欣库存", g("cushing")!=null?fmtNum(g("cushing"),1)+" 百万桶":"—", asOf(ei.cushing,ed)],
        ["全美库存", g("total")!=null?fmtNum(g("total"),1)+" 百万桶":"—", asOf(ei.total,ed)],
        ["美国产量", g("prod")!=null?fmtNum(g("prod"),2)+" 百万桶/日":"—", asOf(ei.prod,ed)],
        ["开工率",   g("util")!=null?g("util").toFixed(1)+"%":"—", asOf(ei.util,ed)],
        ["OECD原油库存", last(STATE.oecdCrude)!=null?fmtNum(last(STATE.oecdCrude),0)+" 百万桶":"—", asOf(STATE.oecdCrude,STATE.oecdMonths)],
        ["美国SPR",      last(STATE.usSpr)!=null?fmtNum(last(STATE.usSpr),1)+" 百万桶":"—", asOf(STATE.usSpr,STATE.usSprMonths)],
        // 剩余产能末点是 EIA 滚动预测值 → 用「预测至」而非「截至」
        ["OPEC剩余产能", last(STATE.opecSpare)!=null?fmtNum(last(STATE.opecSpare),2)+" 百万桶/日":"—", "预测至 "+asOf(STATE.opecSpare,STATE.opecSpareMonths)]
      ];
    })(),
    demand:(function(){
      const ei=STATE.eia||{}, ed=STATE.eiaDates;
      return [
        ["裂解价差", last(STATE.crack)!=null?"$"+last(STATE.crack).toFixed(1):"—", asOf(STATE.crack,STATE.dates)],
        ["汽油库存", lv2(ei.gasinv)!=null?fmtNum(lv2(ei.gasinv),1)+" 百万桶":"—", asOf(ei.gasinv,ed)],
        ["美开工率", last(STATE.usUtil)!=null?last(STATE.usUtil).toFixed(1)+"%":"—", asOf(STATE.usUtil,STATE.usUtilMonths)],
        ["美PMI(ISM)", last(STATE.pmiUS)!=null?last(STATE.pmiUS).toFixed(1):"—", asOf(STATE.pmiUS,STATE.pmiMonths)],
        // 芯片显示的是 gdpValues[2]（2026 年那格），截止日必须跟它对齐，不能取序列末点（2027 预测）
        ["全球GDP预期", (STATE.gdpValues&&STATE.gdpValues.length>2)?STATE.gdpValues[2].toFixed(1)+"% (26)":"—",
          (STATE.gdpYears&&STATE.gdpYears[2])?fmtX(String(STATE.gdpYears[2])):""],
        ["美国汽油供应", last(STATE.gasSupplied)!=null?fmtNum(last(STATE.gasSupplied),2)+" 百万桶/日":"—", asOf(ei.gasSupplied,ed)],
        ["中国原油进口", (function(){const ms=STATE.cnImportMonths||[],vs=STATE.cnImport||[];for(let i=ms.length-1;i>=0;i--){if(vs[i]!=null)return fmtNum(vs[i],0)+" 万吨";}return "—";})(), asOf(STATE.cnImport,STATE.cnImportMonths)]
      ];
    })(),
    geo:(function(){
      const ig=last(STATE.igeo), ib=last(STATE.igeoBreak)||{ovx:0,bw:0,spare:0};
      const ov=last(STATE.ovx), bw=last(STATE.spread_bw), sp=last(STATE.opecSpare);
      return [
        ["I_geo 地缘恐慌系数", ig!=null?ig.toFixed(1)+" / 4":"—", asOf(STATE.igeo,STATE.dates)],
        ["恐慌指数分", "OVX "+(ov!=null?ov.toFixed(1):"—")+" → +"+ib.ovx, asOf(STATE.ovx,STATE.dates)],
        ["跨区分", "BW价差 "+(bw!=null?"$"+bw.toFixed(2):"—")+" → +"+ib.bw, asOf(STATE.spread_bw,STATE.dates)],
        ["产能分", "剩余产能 "+(sp!=null?sp.toFixed(2)+" 百万桶/日":"—")+" → +"+ib.spare, "预测至 "+asOf(STATE.opecSpare,STATE.opecSpareMonths)],
        ["布伦特投机净持仓", (function(){const v=last(STATE.brentCot);return v!=null?fmtNum(v,0)+" 手":"—";})(), asOf(STATE.brentCot,STATE.dates)],
        ["Brent 12M 期限结构", (function(){const v=last(STATE.brentTerm);return v!=null?(v>0?"backwardation +":"contango ")+v.toFixed(1)+" $/bbl":"—";})(), asOf(STATE.brentTerm,STATE.dates)],
        ["归一化地缘风险", ig!=null?(ig/4*100).toFixed(0)+" / 100":"—", asOf(STATE.igeo,STATE.dates)]
      ];
    })(),
    macro:[["广义美元指数",last(STATE.dxy)!=null?last(STATE.dxy).toFixed(2):"—",asOf(STATE.dxy,STATE.dates)],
           ["10Y美债",last(STATE.dgs10)!=null?last(STATE.dgs10).toFixed(2)+"%":"—",asOf(STATE.dgs10,STATE.dates)],
           ["宏观风险",last(STATE.dims.macro)!=null?last(STATE.dims.macro).toFixed(0):"—",asOf(STATE.dims.macro,STATE.dates)]],
    other:(function(){
      const last20=new Set(STATE.dates.slice(-CONST.jumpWindow));
      const jump20=(STATE.events||[]).filter(e=>last20.has(e.date)).length;
      return [
        ["近20日跳变", jump20],
        ["窗口事件",(STATE.events||[]).filter(e=>{
          if(key!=="other") return inWindow(e.date);
          const i=STATE.dates.indexOf(e.date);
          return i>=0 && i>=STATE.dates.length-(RANGE_MODE.other==="all"?STATE.dates.length:252);
        }).length],
        ["突发风险",last(STATE.dims.other)!=null?last(STATE.dims.other).toFixed(0):"—"]
      ];
    })(),
  };
  const rows=map[key]||[];
  // r[2] 可能自带前缀（如「预测至 27/12」），此时不要再叠一个「截至」
  $("dk_"+key).innerHTML=rows.map(r=>`<div><b>${r[1]}</b>${r[0]}<div class="as">${!r[2]?"":(/^(截至|预测至)/.test(r[2])?r[2]:"截至 "+r[2])}</div></div>`).join("");
}

/* ---------- 维度主图 / 副图：按 type 查表渲染 ----------
   原先 renderDimCharts 里是两条长 if-else 链（main 3 支 / sub 5 支），
   新增一种图必须去改那个 200 行的函数。现拆成两张表：
     MAIN_RENDERERS  维度主图（按 cfg.main.type 查）
     SUB_RENDERERS   维度副图（按 cfg.sub.type 查）
   都不命中时各自走 __default__（通用单序列折线）。
   另抽出 axisLineChart —— 「优先 EIA 原生周轴、否则窗口日轴」的单线画法，
   原先在 main / sub / third 三处各写了一遍。 */
function axisLineChart(canvasId, item, col, dates, opt){
  opt=opt||{};
  const a=axisLineData(item.key, dates, opt.eiaOpt);
  const tickN=a.ea?(opt.tickEa||12):(opt.tickBase||8);
  charts[canvasId]=new Chart($(canvasId),{type:"line",data:{labels:a.labels,datasets:[
    {label:item.title.split(" ")[0],data:a.data,borderColor:col,borderWidth:2,fill:true,backgroundColor:(ctx)=>vg(ctx,col),tension:.25,pointRadius:0}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
      scales:{x:{grid:{display:false},ticks:xTime(tickN,a.labels)},y:{grid:{color:"#eef2f7"}}}}});
}

const MAIN_RENDERERS = {
  // 利率端（政策 vs 长端）：两者同为 % → 同轴，两线之间填充 = 期限利差 10Y−DFF。
  // DFF 是阶梯型政策利率（只在议息日跳变），用 stepped:true 如实表达其不连续性；10Y 用平滑线。
  // 第三条：期限利差本身（bp，右轴虚线）——倒挂信号由这条线承担（零下转红、零上青绿），
  // 不再让 10Y 主线转红：红色在看板里惯用于风险/下跌，10Y 转红易被误读为"长端收益率下跌"，
  // 且与利差线的信息重复。右轴只画零线，作为倒挂分界。
  rate: function(p){
    const {mkey,col,dates,from,cfg}=p;
    const dPolicy=gsFrom(cfg.main.key,from);    // DFF
    const dLong=gsFrom(cfg.main.key2,from);     // DGS10
    const dSpread=dLong.map((v,i)=>(v!=null&&dPolicy[i]!=null)?(v-dPolicy[i])*100:null);
    charts[mkey]=new Chart($(mkey),{type:"line",data:{labels:dates,datasets:[
      {label:"10年期美债收益率 %",data:dLong,borderColor:"#0891b2",borderWidth:2,fill:"+1",
       backgroundColor:"rgba(8,145,178,.14)",tension:.25,pointRadius:0,spanGaps:true,order:1},
      {label:"联邦基金有效利率 DFF %",data:dPolicy,borderColor:col,borderWidth:2.4,stepped:true,
       fill:false,pointRadius:0,spanGaps:true,order:2},
      {label:"期限利差 10Y−DFF",data:dSpread,borderColor:"#1d9e75",borderWidth:1.6,borderDash:[5,3],
       fill:false,tension:0,pointRadius:0,spanGaps:true,yAxisID:"y1",order:3,
       segment:{borderColor:ctx=>{
         const i=ctx.p0DataIndex, v=dSpread[i];
         return (v!=null&&v<0)?"#dc2626":"#1d9e75";}}}]},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
        plugins:{legend:{position:"top",labels:{boxWidth:12,font:{size:10}}},
          tooltip:{callbacks:{
            label:c=>{
              if(c.dataset.label.indexOf("利差")>=0){
                const v=c.parsed.y;
                return "期限利差 10Y−DFF："+(v!=null?((v>0?"+":"")+Math.round(v)+" bp"+(v<0?"（倒挂）":"")):"-");
              }
              return c.dataset.label+"："+(c.parsed.y!=null?c.parsed.y.toFixed(2):"-")+" %";
            }}}},scales:{
          x:{grid:{display:false},ticks:xTime(from?12:8,dates)},
          y:{grid:{color:"#eef2f7"},title:{display:true,text:"%"}},
          y1:{position:"right",title:{display:true,text:"利差 bp"},
              grid:{display:true,drawTicks:false,drawBorder:false,
                    color:ctx=>(ctx.tick&&ctx.tick.value===0)?"#b8bfc9":"transparent"},
              min:-180,max:150,
              // 自动步长（当前 55）会跳过 0，导致"倒挂分界"这根零线画不出来 → 强制补一个 0 刻度
              afterBuildTicks:ax=>{
                if(!ax.ticks.some(t=>t.value===0)) ax.ticks.push({value:0});
                ax.ticks.sort((a,b)=>a.value-b.value);
                return ax.ticks;
              },
              ticks:{font:{size:10},callback:v=>(v>0?"+":"")+v}}}}});
  },
  // Brent 价格 + 跳变标记
  events: function(p){
    const {mkey,col,dates}=p;
    const d=sliceN(STATE.brent,RANGE);
    const evDates=new Set((STATE.events||[]).filter(e=>inWindow(e.date)).map(e=>e.date));
    charts[mkey]=new Chart($(mkey),{type:"line",data:{labels:dates,datasets:[
      {label:"Brent $/bbl",data:d,borderColor:col,borderWidth:2,fill:true,backgroundColor:"rgba(124,58,237,.08)",tension:.25,pointRadius:0,
       pointBackgroundColor:dates.map(x=>evDates.has(x)?"#dc2626":"transparent"),pointRadius:dates.map(x=>evDates.has(x)?5:0)}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"top"},
        tooltip:{callbacks:{label:c=>`Brent $${c.parsed.y?.toFixed(2)}`+(evDates.has(c.label)?"  ⚡突发事件":"")}}},
        scales:{x:{grid:{display:false},ticks:xTime(8,dates)},y:{grid:{color:"#eef2f7"}}}}});
  },
  __default__: function(p){
    const {mkey,cfg,col,dates}=p;
    axisLineChart(mkey, cfg.main, col, dates, {});
  }
};

const SUB_RENDERERS = {
  // 月度聚合 bar
  bar: function(p){
    const {key,cfg,col,dates}=p;
    const d=sliceN(getSeries(cfg.sub.key),RANGE);
    const byMonth={};dates.forEach((dt,i)=>{const mk=dt.slice(0,7);if(d[i]!=null){if(!byMonth[mk])byMonth[mk]={s:0,n:0};byMonth[mk].s+=d[i];byMonth[mk].n++;}});
    const mk=Object.keys(byMonth).sort();const mv=mk.map(m=>(byMonth[m].s/byMonth[m].n));
    const sbox=$("s_"+key);
    if(charts["s_"+key])charts["s_"+key].destroy();
    sbox.innerHTML="<canvas id='sc_"+key+"'></canvas>";
    charts["s_"+key]=new Chart($("sc_"+key),{type:"bar",data:{labels:mk,datasets:[{data:mv,backgroundColor:col+"cc",borderRadius:4}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
        scales:{x:{grid:{display:false},ticks:Object.assign(xTime(10,mk),{font:{size:10}})},y:{grid:{color:"#eef2f7"}}}}});
  },
  // 汇率端（水平 + 变化率）：左轴=广义美元指数日度水平，右轴=5日变动 %（日度）。
  // 两者同为日度、点位一一对应（原先 5 日变动按月聚合，与日度水平无法对齐）。
  dxydual: function(p){
    const {key,col,dates,from}=p;
    const dd=gsFrom("dxy",from);
    const dc=gsFrom("dxy_chg5",from);
    const sbox=$("s_"+key);
    sbox.innerHTML="<canvas id='sc_"+key+"'></canvas>";
    if(charts["s_"+key])charts["s_"+key].destroy();
    charts["s_"+key]=new Chart($("sc_"+key),{type:"line",data:{labels:dates,datasets:[
      {label:"广义美元指数",data:dd,borderColor:col,borderWidth:2,fill:true,backgroundColor:(ctx)=>vg(ctx,col),
       tension:.25,pointRadius:0,spanGaps:true,yAxisID:"y",order:2},
      {label:"5日变动 %",data:dc,borderColor:"#0891b2",borderWidth:1.4,tension:0,
       fill:false,pointRadius:0,spanGaps:true,yAxisID:"y1",order:1}]},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
        plugins:{legend:{position:"top",labels:{boxWidth:12,font:{size:10}}},
          tooltip:{callbacks:{label:c=>c.dataset.label+"："+(c.parsed.y!=null?c.parsed.y.toFixed(2):"-")+(c.dataset.label.indexOf("变动")>=0?" %":"")}}},
        scales:{
          x:{grid:{display:false},ticks:xTime(from?12:8,dates)},
          y:{position:"left",grid:{color:"#eef2f7"},title:{display:true,text:"指数"}},
          y1:{position:"right",grid:{display:false},title:{display:true,text:"5日变动 %"}}}}});
  },
  // 波动率日历热力图
  heat: function(p){
    const {key,dates}=p;
    const sbox=$("s_"+key);
    const d=sliceN(STATE.vol20,RANGE);
    let cells="";dates.forEach((dt,i)=>{const v=d[i];let bg="#eef2f7";if(v!=null){const t=Math.min(1,v/60);bg=`rgb(${Math.round(239-(239-220)*t)},${Math.round(242-(242-38)*t)},${Math.round(247-(247-38)*t)})`;}
      cells+=`<div class="cell" title="${dt}: ${v!=null?v.toFixed(0):'-'}%" style="background:${bg}"></div>`;});
    sbox.innerHTML=`<div class="heatmap">${cells}</div><div class="note" style="border:none;background:none;padding:4px 0">颜色越红=波动率越高（地缘/供给冲击信号）</div>`;
  },
  // 月度突发跳变次数（bar）
  eventbar: function(p){
    const {key}=p;
    const sbox=$("s_"+key);
    const byMonth={};(STATE.events||[]).forEach(e=>{if(inWindow(e.date)){const mk=e.date.slice(0,7);byMonth[mk]=(byMonth[mk]||0)+1;}});
    const mk=Object.keys(byMonth).sort();const mv=mk.map(m=>byMonth[m]);
    sbox.innerHTML="<canvas id='sc_"+key+"'></canvas>";
    if(charts["s_"+key])charts["s_"+key].destroy();
    charts["s_"+key]=new Chart($("sc_"+key),{type:"bar",data:{labels:mk,datasets:[{data:mv,backgroundColor:"#7c3aedcc",borderRadius:4}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
        scales:{x:{grid:{display:false},ticks:Object.assign(xTime(10,mk),{font:{size:10}})},y:{grid:{color:"#eef2f7"},title:{display:true,text:"次数"}}}}});
  },
  // type === "line"（如 全美商业原油库存）
  __default__: function(p){
    const {key,cfg,col,dates}=p;
    const sbox=$("s_"+key);
    if(charts["s_"+key])charts["s_"+key].destroy();
    sbox.innerHTML="<canvas id='sc_"+key+"'></canvas>";
    axisLineChart("sc_"+key, cfg.sub, col, dates, {tickBase:10});
  }
};

function renderDimCharts(key){
  const cfg=DIMS[key];
  // 展示窗口：维度配置 from（如 "2024-01"）时回溯到该起点，否则沿用 RANGE=252 滚动窗口
  // 支持区间切换的维度（其他突发 / 地缘政治）：区间随 All/1y 切换（All=全量 2024-01 起，1y=近252交易日）
  const from=cfg.from||null;
  const dates = RANGE_TOGGLE_DIMS.indexOf(key)>=0
    ? (dimIsAll(key) ? STATE.dates : windowDates())
    : (from ? sliceFrom(STATE.dates,from) : windowDates());
  // 分组维度（如供给侧拆成多个子分组）优先走 renderSupplyChart
  if(cfg.groups){
    for(const g of cfg.groups){
      for(const c of g.charts){ renderSupplyChart(key, g, c, cfg.color, dates); }
    }
    return;
  }
  const mkey="m_"+key;
  if(charts[mkey])charts[mkey].destroy();
  const col=cfg.color;
  // 维度无 headline（如 需求侧 已将汽油供应移入「表观消费指标」）时 cfg.main 为空，仅渲染 sub/分组
  if(cfg.main){
    (MAIN_RENDERERS[cfg.main.type]||MAIN_RENDERERS.__default__)({key:key,mkey:mkey,cfg:cfg,col:col,dates:dates,from:from});
  }
  // sub（仅当维度配置了 sub 时才渲染）
  if(cfg.sub){
    (SUB_RENDERERS[cfg.sub.type]||SUB_RENDERERS.__default__)({key:key,cfg:cfg,col:col,dates:dates,from:from});
  }
  // third（可选，如 美国原油产量，与主线图同款周度行图）
  if(cfg.third){
    const tkey="t_"+key;
    if(charts[tkey])charts[tkey].destroy();
    axisLineChart(tkey, cfg.third, col, dates, {});
  }
  // pos（ICE 布伦特投机净持仓，周度→日度前向填充）/ term（Brent 12M 期限结构，日度）
  if(cfg.pos)  renderPosChart(key, cfg, col, dates);
  if(cfg.term) renderTermChart(key, cfg, col, dates);
  // macroGroups / refineryGroups / apparentGroups（需求侧 宏观先行 / 中游炼厂高频 / 表观消费）：复用分组单图渲染
  for(const grp of [].concat(cfg.macroGroups||[], cfg.refineryGroups||[], cfg.apparentGroups||[])){
    for(const c of grp.charts){ renderSupplyChart(key, grp, c, cfg.color, dates); }
  }
}

/* ICE 布伦特投机净持仓（周度 → 日度前向填充） */
function renderPosChart(key, cfg, col, dates){
  const pkey="pos_"+key;
  if(charts[pkey])charts[pkey].destroy();
  const d=sliceN(getSeries(cfg.pos.key),dates.length);
  charts[pkey]=new Chart($(pkey),{type:"line",data:{labels:dates,datasets:[
    {label:cfg.pos.title.split(" ")[0],data:d,borderColor:col,borderWidth:2,fill:true,
     backgroundColor:(ctx)=>vg(ctx,col),tension:.25,pointRadius:0,spanGaps:true}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>c.dataset.label+"："+(c.parsed.y!=null?c.parsed.y.toFixed(0):"-")+" 手"}}},
      scales:{x:{grid:{display:false},ticks:xTime(8,dates)},y:{grid:{color:"#eef2f7"}}}}});
}

/* Brent 12M 期限结构（近月 − 远月）。
   2026-10-06 起与地缘维度其余图（主图 Brent–WTI 价差 / 副图 OVX / I_geo / 投机净持仓）
   同款画法：维度色 #dc2626 实线 + 渐变填充、x 轴 8 格时间刻度、y 轴浅灰网格。
   此前是「零轴上下分色（负=contango 蓝 / 正=backwardation 琥珀）+ 零线加粗 + 强制补 0 刻度」，
   与同维度其它图视觉语言不一致；backwardation / contango 的判定改由 tooltip 文案承担，
   维度 note 里也有完整说明。 */
function renderTermChart(key, cfg, col, dates){
  const tmkey="term_"+key;
  if(charts[tmkey])charts[tmkey].destroy();
  // ⚠️ 必须靠 .box 自己的 id 定位（见上方 posTermHtml 的 box_term_${key}），不能由
  // canvas 反查 parentNode：一旦走了下面的"数据暂缺"分支，画布已被说明文案替换掉，
  // 反查会拿到 null，数据恢复后画布永远回不来。
  const box=$("box_term_"+key);
  if(!box) return;
  // 每次重渲染都重建画布：上一轮若走了"数据暂缺"分支，画布已被说明文案替换掉，
  // 不补回来会让 new Chart(null) 直接抛错（切走再切回该 tab 时触发）。
  box.innerHTML="<canvas id='term_"+key+"'></canvas>";
  const d=sliceN(getSeries(cfg.term.key),dates.length);
  // 抓取失败时整段序列为 null。此时不画空图 —— 用户看不出是"没数据"还是"图坏了"：
  // 2026-10-06 实测 Yahoo 批量抓取被限流后落库成 1006 个 null，页面静默空白。
  if(!d.some(v=>v!=null)){
    const m=STATE.brentTermMeta||{};
    box.innerHTML="<div class='note' style='border:none;background:none;padding:6px 0'>"
      + "本期未取到 Brent 期限结构数据"
      + (m.error?"（"+m.error+"）":"")
      + "。重跑 <code>python run.py dataset</code> 即可恢复；"
      + "该图缺失不影响其余数据源。</div>";
    return;
  }
  charts[tmkey]=new Chart($(tmkey),{type:"line",data:{labels:dates,datasets:[
    {label:cfg.term.title.split(" ")[0],data:d,borderColor:col,borderWidth:2,fill:true,
     backgroundColor:(ctx)=>vg(ctx,col),tension:.25,pointRadius:0,spanGaps:true}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>{
        const v=c.parsed.y;
        if(v==null) return c.dataset.label+"：-";
        // 仅在 tooltip 里保留方向语义：正=backwardation（近端升水）/ 负=contango（近端贴水）
        return c.dataset.label+"："+(v>0?"+":"")+v.toFixed(2)+" 美元/桶"
               +(v>0?"（backwardation）":v<0?"（contango）":"");
      }}}},
      scales:{x:{grid:{display:false},ticks:xTime(8,dates)},y:{grid:{color:"#eef2f7"}}}}});
}

/* 数据区域缩放滑块（type=slider）：在图下方挂一个双滑块，拖动选择可见区间。
   说明：chartjs-plugin-zoom 只提供拖拽/滚轮/双指缩放，没有 slider 组件；
   这里用两个原生 input[type=range] 叠放实现，零新增依赖、离线可用。
   用法：图表配置加 dataZoom:true，并在 moveSource(box) 之后调用 mountDataZoom(box, chart, labels)。
   现状：PMI 图已改走 ECharts（自带 dataZoom slider），当前无图表设置 dataZoom:true，
   本函数保留作为 Chart.js 回落路径的可用能力。 */
function mountDataZoom(box, chart, labels){
  const n=(labels&&labels.length)||0;
  if(!n||n<3) return;
  const MIN_GAP=1;                       // 至少保留 2 个点，避免两个滑块完全重叠后无法再分开
  const parent=box.parentNode;
  // 幂等：清除上一次渲染留下的滑块，避免重绘时重复
  parent.querySelectorAll(".dz").forEach(function(el){el.remove();});
  const full=chart.data.datasets.map(function(ds){return ds.data.slice();});

  const wrap=document.createElement("div");
  wrap.className="dz";
  wrap.innerHTML=
    '<div class="dz-track"><div class="dz-sel"></div></div>'+
    '<input class="dz-in dz-a" type="range" min="0" max="'+(n-1)+'" step="1" value="0" aria-label="区间起始">'+
    '<input class="dz-in dz-b" type="range" min="0" max="'+(n-1)+'" step="1" value="'+(n-1)+'" aria-label="区间结束">'+
    '<div class="dz-lab"><span class="dz-s"></span><span class="dz-e"></span></div>';
  parent.insertBefore(wrap, box.nextSibling);

  const sel=wrap.querySelector(".dz-sel");
  const labS=wrap.querySelector(".dz-s"), labE=wrap.querySelector(".dz-e");
  const a=wrap.querySelector(".dz-a"), b=wrap.querySelector(".dz-b");

  function apply(){
    let i0=parseInt(a.value,10), i1=parseInt(b.value,10);
    if(!(i1-i0>=MIN_GAP)) return;
    sel.style.left=(i0/(n-1)*100)+"%";
    sel.style.width=((i1-i0)/(n-1)*100)+"%";
    labS.textContent=fmtX(labels[i0]);
    labE.textContent=fmtX(labels[i1]);
    chart.data.labels=labels.slice(i0,i1+1);
    chart.data.datasets.forEach(function(ds,k){ ds.data=full[k].slice(i0,i1+1); });
    chart.update("none");
  }
  a.addEventListener("input",function(){
    if(parseInt(a.value,10) > parseInt(b.value,10)-MIN_GAP) a.value=String(Math.max(0,parseInt(b.value,10)-MIN_GAP));
    apply();
  });
  b.addEventListener("input",function(){
    if(parseInt(b.value,10) < parseInt(a.value,10)+MIN_GAP) b.value=String(Math.min(n-1,parseInt(a.value,10)+MIN_GAP));
    apply();
  });
  // 两个 range 叠放时后写的默认在上层。按指针落点把「更近的那个滑块」提到上层，
  // 避免窗口很窄、两个滑块靠在一起时抓错滑块。
  wrap.addEventListener("pointerdown",function(ev){
    const r=wrap.getBoundingClientRect();
    const px=(ev.clientX-r.left);
    const x=Math.max(0,Math.min(r.width,px))/r.width*(n-1);
    const dA=Math.abs(x-parseInt(a.value,10)), dB=Math.abs(x-parseInt(b.value,10));
    a.style.zIndex = dA<dB ? 3 : 2;
    b.style.zIndex = dA<dB ? 2 : 3;
  });
  apply();
}

/* ===== ECharts 实验图：制造业 PMI 中 / 美 / 欧 =====
   为什么单独走 ECharts：下面这批组件 Chart.js 没有原生对应（chartjs-plugin-zoom 也只提供
   拖拽/滚轮缩放，没有 slider），换成 ECharts 后均是一等公民：
     · axisPointer     十字对齐参考线（横竖双向 + 轴上跟随标签）
     · markPoint       自动标记每条曲线的最大 / 最小值
     · dataZoom        紧贴 x 轴的底部滑块（slider）+ 图内滚轮/拖拽（inside）
     · markLine        50 荣枯线虚线
     · tooltip         多线 axis 联动
   三条线用不同颜色区分（蓝=美国 ISM / 红=中国 PMI / 橙=欧元区 HCOB），不再用 visualMap / markArea。 */
function renderPmiEcharts(box, id, c){
  const months=(STATE.pmiMonths||[]).slice().sort();
  const us=STATE.pmiUS||[], cn=STATE.pmiChina||[], eu=STATE.pmiEuro||[];
  if(!months.length){ box.innerHTML="<div class='note'>PMI 数据缺失</div>"; return; }
  if(c.ecH) box.style.height=c.ecH+"px";   // 底部要放 dataZoom 滑块，比常规图高一些
  box.innerHTML="<div id='ec_"+id+"' class='ecbox'></div>"+(c.source?("<div class='src'>"+c.source+"</div>"):"");
  const el=$("ec_"+id);
  if(!el || !window.echarts) return;
  if(ecCharts[id]){ ecCharts[id].dispose(); delete ecCharts[id]; }

  const all=[].concat(us,cn,eu).filter(function(v){return v!=null;});
  const yMin=Math.floor(Math.min.apply(null,all)-1);
  const yMax=Math.ceil(Math.max.apply(null,all)+1);
  const mkPt=function(){
    return {symbolSize:34,symbolOffset:[0,-2],
      label:{fontSize:9,color:"#fff",fontWeight:"600",
        formatter:function(p){return p.value!=null?Number(p.value).toFixed(1):"";}},
      data:[{type:"max",name:"最大"},{type:"min",name:"最小"}]};
  };
  // 三条线用不同颜色 + 不同线型（颜色为主、线型为辅，便于色弱辨识）
  const line=function(name,data,color,type,symbol){
    return {name:name,type:"line",data:data,smooth:true,symbol:symbol,symbolSize:5.5,
      itemStyle:{color:color},lineStyle:{width:2.5,color:color,type:type},
      emphasis:{focus:"series",lineStyle:{width:3.5}},
      markPoint:mkPt()};
  };
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:46,right:16,top:46,bottom:46},
    legend:{data:["美国 ISM","中国 PMI","欧元区 HCOB"],top:6,left:0,
      itemWidth:18,itemHeight:9,itemGap:14,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",
      axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},
        label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      valueFormatter:function(v){return v==null?"-":Number(v).toFixed(1)+" %";}},
    xAxis:{type:"category",data:months,boundaryGap:false,
      axisTick:{alignWithLabel:true},
      axisLine:{lineStyle:{color:"#e4e9f0"}},
      // x 轴标签统一格式：2024-01 → 24/01（fmtX 为全站唯一定义）
      axisLabel:{fontSize:10,color:"#94a3b8",interval:"auto",hideOverlap:true,
        formatter:function(v){return fmtX(v);}}},
    yAxis:{type:"value",min:yMin,max:yMax,
      splitLine:{lineStyle:{color:"#eef2f7"}},
      axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    dataZoom:[
      {type:"inside",xAxisIndex:0,zoomOnMouseWheel:true,moveOnMouseMove:true},
      {type:"slider",xAxisIndex:0,height:18,bottom:16,borderColor:"#e4e9f0",
        fillerColor:"rgba(15,118,110,.10)",
        handleStyle:{color:"#0f766e",borderColor:"#0f766e"},
        moveHandleStyle:{color:"#cbd5e1"},
        dataBackground:{lineStyle:{color:"#cbd5e1",width:1},areaStyle:{color:"#eef2f7"}},
        selectedDataBackground:{lineStyle:{color:"#0f766e",width:1},areaStyle:{color:"rgba(15,118,110,.14)"}},
        labelFormatter:function(v,vs){return fmtX(vs);},
        textStyle:{fontSize:10,color:"#94a3b8"}}
    ],
    series:[
      Object.assign(line("美国 ISM",us,"#2563eb","solid","circle"),{
        markLine:{silent:true,symbol:"none",
          data:[{yAxis:50,label:{formatter:"荣枯线 50",position:"insideEndTop",fontSize:10,color:"#64748b"},
                 lineStyle:{color:"#64748b",type:"dashed",width:1.5}}]}}),
      line("中国 PMI",cn,"#dc2626","dashed","rect"),
      line("欧元区 HCOB",eu,"#d97706","dotted","triangle")
    ]
  };
  ecCharts[id]=echarts.init(el);
  ecCharts[id].setOption(opt);
}

/* IMF《世界经济展望》逐期 GDP 增速修正 —— 与「未来展望」的 outlook1/3/5（IEA OMR /
   OPEC MOMR / EIA STEO 逐期需求增速修正）同构，但 WEO 是**季度**频率（1/4/7/10 月四期），
   且纵坐标是「增速 %」而非「增量 mb/d」。
   x 轴 = 期次，两条线 = 当年 / 次年；另画一条「上年实际」基准参考线，
   因为替换掉的旧柱状图原本承担的就是「实际 vs 预期」的对照，这条线把它接住。
   最新一点的 Δ（较上一期）放进 tooltip —— 折线本身已经能看出方向，Δ 只做精确读数。 */
function renderWoeRevisions(box, id, c){
  const months=(STATE.imfWoeMonths||[]).slice();
  const g26=STATE.imfWoe2026Growth||[], g27=STATE.imfWoe2027Growth||[];
  if(!months.length){ box.innerHTML="<div class='note'>IMF WEO 期次数据缺失</div>"; return; }
  if(c.ecH) box.style.height=c.ecH+"px";
  // 上年实际值基准线：取 gdpActual 为真的最后一格（当前即 2025 = 3.5）
  let base=null, baseYear="";
  const gy=STATE.gdpYears||[], gv=STATE.gdpValues||[], ga=STATE.gdpActual||[];
  for(let i=0;i<gy.length;i++){ if(ga[i] && gv[i]!=null){ base=gv[i]; baseYear=gy[i]; } }
  const vals=[].concat(g26,g27).filter(function(v){return v!=null;});
  if(base!=null) vals.push(base);
  if(!vals.length){ box.innerHTML="<div class='note'>IMF WEO 期次数据缺失</div>"; return; }
  box.innerHTML="<div id='ec_"+id+"' class='ecbox'></div>"+(c.source?("<div class='src'>"+c.source+"</div>"):"");
  const el=$("ec_"+id);
  if(!el || !window.echarts) return;
  if(ecCharts[id]){ ecCharts[id].dispose(); delete ecCharts[id]; }
  const yMin=Math.floor((Math.min.apply(null,vals)-0.2)*10)/10;
  const yMax=Math.ceil((Math.max.apply(null,vals)+0.2)*10)/10;
  const arrs=[g26,g27];
  const mkPt=function(){
    return {symbolSize:30,symbolOffset:[0,-2],
      label:{fontSize:9,color:"#fff",fontWeight:"600",
        formatter:function(p){return p.value!=null?Number(p.value).toFixed(1):"";}},
      data:[{type:"max",name:"最高"},{type:"min",name:"最低"}]};};
  const line=function(name,data,color,type){
    return {name:name,type:"line",data:data,smooth:true,symbol:"circle",symbolSize:6,
      itemStyle:{color:color},lineStyle:{width:2.5,color:color,type:type},
      emphasis:{focus:"series",lineStyle:{width:3.5}},
      endLabel:{show:true,distance:6,fontSize:10,fontWeight:600,color:color,
        formatter:function(pp){return pp.value!=null?Number(pp.value).toFixed(1):"";}},
      markPoint:mkPt()};};
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:46,right:30,top:46,bottom:46},
    legend:{data:["2026 增速预测","2027 增速预测"],top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:16,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",
      axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},
        label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      formatter:function(ps){
        if(!ps||!ps.length) return "";
        let s=String(ps[0].name);
        ps.forEach(function(q){
          if(q.value==null) return;
          const arr=arrs[q.seriesIndex]||[];
          const prev=(q.dataIndex>0&&arr[q.dataIndex-1]!=null)?arr[q.dataIndex-1]:null;
          const d=(prev==null)?"":("（较上期 "+((q.value-prev>0?"+":"")+(q.value-prev).toFixed(1))+" pp）");
          s+="<br/>"+q.marker+q.seriesName+"："+Number(q.value).toFixed(1)+" % "+d;
        });
        return s;
      }},
    xAxis:{type:"category",data:months,boundaryGap:false,
      axisTick:{alignWithLabel:true},
      axisLine:{lineStyle:{color:"#e4e9f0"}},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:0,hideOverlap:true,
        formatter:function(v){return fmtX(v);}}},
    yAxis:{type:"value",min:yMin,max:yMax,name:"% 同比",
      nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      splitLine:{lineStyle:{color:"#eef2f7"}},
      axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    series:[
      Object.assign(line("2026 增速预测",g26,"#0d9488","solid"),{
        markLine:{silent:true,symbol:"none",
          data:base==null?[]:[{yAxis:base,
            label:{formatter:baseYear+" 实际 "+base.toFixed(1)+"%",position:"insideEndTop",
                   fontSize:10,color:"#64748b"},
            lineStyle:{color:"#64748b",type:"dashed",width:1.5}}]}}),
      line("2027 增速预测",g27,"#7c3aed","dashed")
    ]
  };
  ecCharts[id]=echarts.init(el);
  ecCharts[id].setOption(opt);
}

/* ---------- 图表挂载样板（原先在每个分支里重复 8 次以上） ----------
   canvasBox(id,c)             生成 .box 的 innerHTML（canvas + 可选 .src）
   moveSource(box)             把 .src 移到 .box 外面（幂等，重绘不重复）
   axisLineData(key,dates,opt) 单序列取轴：优先 EIA 原生周轴，否则窗口日轴 */
// 「合计走右轴 + 国别走左轴 + 右侧标注槽」的公共绘制插件（含合计气泡）。
// 2026-10-08 抽出：原供 OPEC 12 国图使用。2026-10-09 OPEC 图改走 makeInlineTailPlugin（删合计线/右轴）
// 后，本函数已不再被任何图调用，暂留作可复用工具（如需恢复右侧槽式标注可直接复用）。
// ⚠️ pluginId 每张图必须不同 —— Chart.js 按 id 注册插件，同 id 会互相覆盖。
// ⚠️ 绘制回调一律包 try/catch：Chart.js 的绘制回调里抛异常会打断 rAF 动画帧循环，
//    元素坐标被永久冻结在动画中途（实测：整张图所有线塌到底部 0–2.5 区间、标签完全不画，
//    而 scales.y.min/max 看着一切正常，极易误判成数据错）。
function makeOpecTailPlugin(pluginId, major, opt){
  opt = opt || {};
  const GAP = opt.gap || 12.5, col = opt.col, note = opt.note || "合计(右轴)";
  return {
    id:pluginId,
    afterDatasetsDraw:function(chart){
      try{ drawTail(chart); }catch(e){ if(window.console)console.warn(pluginId+" 绘制失败",e); }
      function drawTail(chart){
      const area=chart.chartArea, ctx=chart.ctx;
      if(!area) return;
      const items=[];
      let tMeta=null;
      chart.data.datasets.forEach(function(ds,di){
        const meta=chart.getDatasetMeta(di);
        if(!meta||meta.hidden) return;
        let k=-1;
        for(let i=ds.data.length-1;i>=0;i--) if(ds.data[i]!=null){k=i;break;}
        if(k<0||!meta.data[k]) return;
        const rec={px:meta.data[k].x, py:meta.data[k].y, v:ds.data[k]};
        if(ds.yAxisID==="y2"){ tMeta=rec; }
        else{
          const nm=major.filter(m=>m[1]===ds.label)[0];
          if(nm) items.push({py:rec.py, ly:rec.py, v:rec.v, col:ds.borderColor, t:nm[1]});
        }
      });
      ctx.save();
      ctx.font='600 10px '+(Chart.defaults.font.family||'sans-serif');
      ctx.textBaseline='middle'; ctx.textAlign='left';
      // 扇出：自上而下保证相邻标签至少 GAP 间距；随后自底回推，避免整体顶出画布
      items.sort(function(a,b){return a.py-b.py;});
      for(let i=0;i<items.length;i++) items[i].ly=Math.max(items[i].ly, i?items[i-1].ly+GAP:area.top+6);
      let lim=area.bottom-4;
      for(let i=items.length-1;i>=0;i--){ items[i].ly=Math.min(items[i].ly,lim); lim=items[i].ly-GAP; }
      items.forEach(function(it){ it.ly=Math.max(it.ly,area.top+6); });
      const lx=area.right+14;            // 引线水平肩起点（已让开右轴刻度宽度）
      items.forEach(function(it){
        ctx.beginPath(); ctx.arc(it.px,it.py,2.6,0,Math.PI*2);
        ctx.fillStyle='#ffffff'; ctx.fill(); ctx.lineWidth=1.8; ctx.strokeStyle=it.col; ctx.stroke();
        ctx.beginPath(); ctx.globalAlpha=.7;
        ctx.moveTo(it.px,it.py); ctx.lineTo(it.px+5,it.ly); ctx.lineTo(lx,it.ly);
        ctx.lineWidth=1; ctx.strokeStyle=it.col; ctx.stroke(); ctx.globalAlpha=1;
        ctx.fillStyle=it.col;
        ctx.fillText(it.t+" "+(typeof it.v==="number"?it.v.toFixed(2):"—"), lx+4, it.ly+0.5);
      });
      // 右轴说明：只留首尾两个刻度（中间空出来给末端标注），故在其下方补一句说明这条轴只服务合计线
      if(tMeta){
        ctx.fillStyle='#94a3b8'; ctx.font='500 9px '+(Chart.defaults.font.family||'sans-serif');
        ctx.fillText(note, area.right+2, area.top+13);
        const txt="合计 "+(typeof tMeta.v==="number"?tMeta.v.toFixed(2):"—");
        ctx.font='600 10px '+(Chart.defaults.font.family||'sans-serif');
        const bw=ctx.measureText(txt).width+10, bh=15;
        let bx=tMeta.px-8-bw;                 // 默认放末点左侧（绘图区右上部是空的）
        if(bx<area.left+2) bx=tMeta.px+8;
        if(bx+bw>area.right) bx=area.right-bw;
        let by=tMeta.py-bh/2;
        if(by<area.top+1) by=area.top+1;
        if(by+bh>area.bottom-1) by=area.bottom-1-bh;
        ctx.fillStyle=col; ctx.beginPath();
        if(ctx.roundRect) ctx.roundRect(bx,by,bw,bh,4); else ctx.rect(bx,by,bw,bh);
        ctx.fill();
        ctx.fillStyle='#ffffff'; ctx.textAlign='left';
        ctx.fillText(txt,bx+5,by+bh/2+0.5);
      }
      ctx.restore();
      }
    }
  };
}

/* 末端内联标签插件：把每个序列末点（最新值）直接标在绘图区内、紧贴末点，
   不占用右侧标注槽（与 makeOpecTailPlugin 的「右侧独立列」相反）。
   国家/序列名由顶部 Chart.js 图例承担；末点只保留数值，避免标签过长溢出。
   ⚠️ 适用场景：单左轴、多序列末点同 x（最右月），标签按 y 扇出错行、限定在 plot 内；
      若右侧空间不足则把标签翻到末点左侧（右对齐），保证不溢出画布。 */
function makeInlineTailPlugin(pluginId, major){
  return {
    id:pluginId,
    afterDatasetsDraw:function(chart){
      try{ drawTail(chart); }catch(e){ if(window.console)console.warn(pluginId+" 绘制失败",e); }
      function drawTail(chart){
        const area=chart.chartArea, ctx=chart.ctx;
        if(!area) return;
        const items=[];
        chart.data.datasets.forEach(function(ds,di){
          const meta=chart.getDatasetMeta(di);
          if(!meta||meta.hidden) return;
          if(ds.yAxisID==="y2") return;          // 本图无右轴；保险跳过
          let k=-1;
          for(let i=ds.data.length-1;i>=0;i--) if(ds.data[i]!=null){k=i;break;}
          if(k<0||!meta.data[k]) return;
          const nm=major.filter(m=>m[1]===ds.label)[0];
          if(!nm) return;
          items.push({px:meta.data[k].x, py:meta.data[k].y, v:ds.data[k],
                      col:ds.borderColor, t:nm[1]});
        });
        if(!items.length) return;
        ctx.save();
        ctx.font='600 10px '+(Chart.defaults.font.family||'sans-serif');
        ctx.textBaseline='middle';
        // 扇出：垂直错行防重叠，限定在绘图区内
        const GAP=12.5;
        items.sort(function(a,b){return a.py-b.py;});
        for(let i=0;i<items.length;i++) items[i].ly=Math.max(items[i].py, i?items[i-1].ly+GAP:area.top+6);
        let lim=area.bottom-4;
        for(let i=items.length-1;i>=0;i--){ items[i].ly=Math.min(items[i].ly,lim); lim=items[i].ly-GAP; }
        items.forEach(function(it){ it.ly=Math.max(it.ly,area.top+6); });
        // 末点同 x：无右侧标注槽，故标签一律贴在末点左侧（右对齐），保证不溢出绘图区
        items.forEach(function(it){
          const txt=(typeof it.v==="number"?it.v.toFixed(2):"—");
          const w=ctx.measureText(txt).width;
          let lx=it.px-6, align='right';
          // 白心圆点
          ctx.beginPath(); ctx.arc(it.px,it.py,2.6,0,Math.PI*2);
          ctx.fillStyle='#ffffff'; ctx.fill(); ctx.lineWidth=1.8; ctx.strokeStyle=it.col; ctx.stroke();
          // 引线（dot → label 起点，仅 2px 短肩，不拉到右侧槽）
          ctx.beginPath(); ctx.globalAlpha=.7;
          ctx.moveTo(it.px,it.py); ctx.lineTo(align==='left'?lx-2:lx+2, it.ly);
          ctx.lineWidth=1; ctx.strokeStyle=it.col; ctx.stroke(); ctx.globalAlpha=1;
          // 文字（白描边保证压线仍可读）
          ctx.fillStyle=it.col; ctx.textAlign=align;
          ctx.lineWidth=3; ctx.strokeStyle='#ffffff'; ctx.lineJoin='round';
          ctx.strokeText(txt, lx, it.ly);
          ctx.fillText(txt, lx, it.ly);
          ctx.textAlign='left';
        });
        ctx.restore();
      }
    }
  };
}

function canvasBox(id, c){
  return "<canvas id='cv_"+id+"'></canvas>"+(c.source?("<div class='src'>"+c.source+"</div>"):"");
}
function moveSource(box){
  const parent=box.parentNode;
  const src=box.querySelector('.src');
  // 幂等：清除上一次渲染已移到 .box 外部的旧 .src，避免重绘时重复
  parent.querySelectorAll('.src').forEach(el=>{ if(el!==src) el.remove(); });
  if(src) parent.insertBefore(src, box.nextSibling);
}
/* 双格 ECharts 图统一版式（2026-10-10）：nonopecdoc 与 opec 两张月图**并排显示在同一行**，
   两图的 grid 必须逐像素一致（用户要求：y 轴上下对齐、整轴高度一样）。
   ⚠️ 上格 top=44 是给 OPEC 的两行图例预留的——Non-OPEC 只有单行图例，多出的留白是对齐的代价；
   若日后把 OPEC 图例压回一行，两处可同时收到 ~26。
   grid 数组每次渲染都深拷贝：避免两个 ECharts 实例共享同一引用、被 setOption 归一化时互相污染。 */
const EC2_H=400;   // 两张双格图统一总高（px）
// 上下两格**等高**（2026-10-10 追加：用户要求两个 y 轴高度差不多）：
// H 400 - 图例 44 - 下边距 48 = 308，留 18px 间隙 → 每格 145px。
// ⚠️ 下格 145px 仍够放 OPEC 的 8 条末点标签（moveOverlap shiftY 需 8×12≈96px）。
const ec2Grid=function(){
  return [{left:52,right:64,top:44,height:145},{left:52,right:64,top:207,bottom:48}]
         .map(function(g){return Object.assign({},g);});
};
function axisLineData(key, dates, opt){
  const ea=eiaAxis(key, opt);
  return ea?{labels:ea.dates,data:ea.data,ea:true}
           :{labels:dates,data:sliceN(getSeries(key),dates.length),ea:false};
}

/* ---------- 供给侧 / 需求侧 / 其他突发 的单图渲染器注册表 ----------
   分派顺序：先按 c.key、再按 c.type 查表，都不命中走 __default__（通用折线）。
   先 key 后 type 是有意的：crack 与 gdp 的 type 同为 "bar"，只能靠 key 区分。
   新增一种图表只需往这里加一项，不必再改动 renderSupplyChart 本身。 */
/* 线图左轴配置：__default__ 与 linebar（双轴）共用，保证同一序列在两种画法下刻度口径一致。
   c.yPadding 为「相对数据范围的比例」（默认 0 = 沿用 Chart.js 自动缩放）；niceY 走 niceYScale 取整刻度。 */
function lineYAxis(c, d){
  const ylabel = (c.key && c.key.indexOf("prod")>=0) ? "百万桶/日" : "百万桶";
  const yOpt={grid:{color:"#eef2f7"},title:{display:!!ylabel,text:ylabel}};
  if(c.niceY){
    const ns=niceYScale(d, c.yPadding||0, c.yTicks||6);
    if(ns){yOpt.min=ns.min;yOpt.max=ns.max;yOpt.ticks={stepSize:ns.stepSize};}
  } else if(c.yPadding && c.yPadding>0){
    const vals=d.filter(v=>v!=null);
    if(vals.length){
      const minV=Math.min(...vals), maxV=Math.max(...vals);
      const pad=(maxV-minV)*c.yPadding;
      yOpt.min=minV>=0?Math.max(0,minV-pad):minV-pad; // 非负序列不穿 0
      yOpt.max=maxV+pad;
    }
  }
  return yOpt;
}

/* ---------- 事件竖线插件（Chart.js 内联插件）----------
   在折线图上按日期标注事件，视觉语言与 Non-OPEC DoC 图的 ECharts markLine 完全一致：
   灰色虚线（#64748b / 1.4px / 5-4 虚线）+ 顶部标签（#475569 / 10px / 600）。
   仅当 c.events 配置存在时返回插件，对其它图零副作用。
   c.events = [{date:"2026-10-07", label:"Isaias 停产 10/07"}, ...]
   ⚠️ x 定位按**真实日期在相邻周网格间线性插值**，而非吸附到最近标签——
   否则 10-07 与 10-11 这种相邻事件会落在同一根周网格、两根线重叠。 */
function makeEventVlines(c){
  const evs=(c&&c.events)||[];
  if(!evs.length) return null;
  return {
    id:"eventVlines_"+(c.id||"x"),
    afterDatasetsDraw(chart){
      const labels=chart.data.labels||[];
      const x=chart.scales&&chart.scales.x;
      const area=chart.chartArea;
      if(!labels.length||!x||!area) return;
      const ctx=chart.ctx;
      // 按真实日期插值出 x 像素：落在相邻两标签之间时线性内插，端点外则夹到端点
      function pxForDate(dateEv){
        const tEv=Date.parse(dateEv);
        if(isNaN(tEv)) return null;
        const n=labels.length;
        if(n===1) return x.getPixelForValue(0);
        const first=Date.parse(labels[0]), last=Date.parse(labels[n-1]);
        if(!isNaN(first)&&tEv<=first) return x.getPixelForValue(0);
        if(!isNaN(last)&&tEv>=last) return x.getPixelForValue(n-1);
        for(let i=0;i<n-1;i++){
          const a=Date.parse(labels[i]), b=Date.parse(labels[i+1]);
          if(isNaN(a)||isNaN(b)) continue;
          if(tEv>=a&&tEv<=b){
            const pa=x.getPixelForValue(i), pb=x.getPixelForValue(i+1);
            const t=(b===a)?0:(tEv-a)/(b-a);
            return pa+(pb-pa)*t;
          }
        }
        return null;
      }
      evs.forEach(function(ev){
        const xp=pxForDate(ev.date);
        if(xp==null||isNaN(xp)) return;
        ctx.save();
        ctx.strokeStyle="#64748b"; ctx.lineWidth=1.4; ctx.setLineDash([5,4]);
        ctx.beginPath(); ctx.moveTo(xp, area.top); ctx.lineTo(xp, area.bottom); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle="#475569"; ctx.font="600 10px -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif";
        ctx.textAlign="center"; ctx.textBaseline="top";
        const lx=Math.max(area.left+24, Math.min(area.right-24, xp));
        ctx.fillText(ev.label, lx, area.top+4);
        ctx.restore();
      });
    }
  };
}

const SUPPLY_RENDERERS = {
  // 突发跳变：Brent 价格 + 跳变标记（其他突发）
  events: function(p){
    const {box,id,c,col,dates}=p;
    const d=sliceN(STATE.brent,dates.length);
    const evDates=new Set((STATE.events||[]).filter(e=>{const i=STATE.dates.indexOf(e.date);return i>=0&&i>=STATE.dates.length-dates.length;}).map(e=>e.date));
    box.innerHTML=canvasBox(id,c);
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:dates,datasets:[
      {label:"Brent $/bbl",data:d,borderColor:col,borderWidth:2,fill:true,backgroundColor:"rgba(124,58,237,.08)",tension:.25,pointRadius:0,
       pointBackgroundColor:dates.map(x=>evDates.has(x)?"#dc2626":"transparent"),pointRadius:dates.map(x=>evDates.has(x)?5:0)}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"top"},
        tooltip:{callbacks:{label:cx=>`Brent $${cx.parsed.y?.toFixed(2)}`+(evDates.has(cx.label)?"  ⚡突发事件":"")}}},
        scales:{x:{grid:{display:false},ticks:xTime(8,dates)},y:{grid:{color:"#eef2f7"}}}}});
    moveSource(box);
  },
  // 月度突发跳变次数（bar）
  eventbar: function(p){
    const {box,id,c,dates}=p;
    const byMonth={};(STATE.events||[]).forEach(e=>{const i=STATE.dates.indexOf(e.date);if(i>=0&&i>=STATE.dates.length-dates.length){const mk=e.date.slice(0,7);byMonth[mk]=(byMonth[mk]||0)+1;}});
    const mk=Object.keys(byMonth).sort();const mv=mk.map(m=>byMonth[m]);
    box.innerHTML=canvasBox(id,c);
    charts[id]=new Chart($("cv_"+id),{type:"bar",data:{labels:mk,datasets:[{data:mv,backgroundColor:"#7c3aedcc",borderRadius:4}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
        scales:{x:{grid:{display:false},ticks:Object.assign(xTime(10,mk),{font:{size:10}})},y:{grid:{color:"#eef2f7"},title:{display:true,text:"次数"}}}}});
    moveSource(box);
  },
  // 波动率日历热力图（日度）
  heat: function(p){
    const {box,dates}=p;
    const d=sliceN(STATE.vol20,dates.length);
    let cells="";dates.forEach((dt,i)=>{const v=d[i];let bg="#eef2f7";if(v!=null){const t=Math.min(1,v/60);bg=`rgb(${Math.round(239-(239-220)*t)},${Math.round(242-(242-38)*t)},${Math.round(247-(247-38)*t)})`;}
      cells+=`<div class="cell" title="${dt}: ${v!=null?v.toFixed(0):'-'}%" style="background:${bg}"></div>`;});
    box.innerHTML=`<div class="heatmap">${cells}</div><div class="note" style="border:none;background:none;padding:4px 0">颜色越红=波动率越高（地缘/供给冲击信号）</div>`;
    moveSource(box);
  },
  // 制造业 PMI：中/美/欧 多线（月度）
  // 走 ECharts 的原因：Chart.js 无 markPoint / dataZoom(slider) 原生组件，
  // 这些是「极值自动标注 + 底部滑块缩放」的一等公民能力（本图不再用 visualMap / markArea）。
  pmi: function(p){
    const {box,id,c}=p;
    if(c.ec){ renderPmiEcharts(box, id, c); moveSource(box); return; }  // c.ec 关闭时的 Chart.js 回落路径
    const months=(STATE.pmiMonths||[]).slice().sort();
    const us=STATE.pmiUS||[], cn=STATE.pmiChina||[], eu=STATE.pmiEuro||[];
    const ud=months.map((m,i)=> us[i]!=null?us[i]:null);
    const cd=months.map((m,i)=> cn[i]!=null?cn[i]:null);
    const ed=months.map((m,i)=> eu[i]!=null?eu[i]:null);
    box.innerHTML=canvasBox(id,c);
    const datasets=[
      {label:"美国 ISM",data:ud,borderColor:"#2563eb",borderWidth:2.5,fill:false,tension:.25,pointRadius:2},
      {label:"中国 PMI",data:cd,borderColor:"#dc2626",borderWidth:2.5,fill:false,tension:.25,pointRadius:2},
      {label:"欧元区 HCOB",data:ed,borderColor:"#d97706",borderWidth:2.5,fill:false,tension:.25,pointRadius:2},
      {label:"荣枯线 50",data:months.map(()=>50),borderColor:"#64748b",borderWidth:1.5,borderDash:[6,4],fill:false,pointRadius:0,tension:0,order:99}
    ];
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:months,datasets},
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:true,labels:{boxWidth:12,font:{size:10}}},
          tooltip:{callbacks:{label:cx=>cx.dataset.label+"："+(cx.parsed.y!=null?cx.parsed.y.toFixed(1):"-")+" %"}}},
        scales:{x:{grid:{display:false},ticks:xTime(12,months)},
          y:{grid:{color:"#eef2f7"},title:{display:true,text:"PMI（50=荣枯线）"},suggestedMin:44,suggestedMax:56,grace:"5%"}}}});
    moveSource(box);
    if(c.dataZoom) mountDataZoom(box, charts[id], months);
  },
  // IMF《WEO》全球 GDP 增速「逐期修正」（季度，1/4/7/10 月四期 × 当年/次年两条线）
  // ⚠️ 2026-10-13 替换掉原来的「全球 GDP 增速预期（年度，实际/预期分色）」柱状图 ——
  //    旧图只画最新一期的 2024–2027 四个柱子，看不到 IMF 一年四期的修订过程；
  //    新图把「水平」换成「路径」，2025 实际值改用基准参考线接住（见 renderWoeRevisions）。
  //    gdpYears / gdpValues / gdpActual 仍保留在 STATE（KPI 芯片「全球GDP预期」读 gdpValues[2]），
  //    且已改为由 pmi_gdp.py 的 WOE_VINTAGES 期次矩阵派生，不再单独硬编码。
  woeRev: function(p){
    const {box,id,c}=p;
    // 页尾 {latest} 占位符 → 由数据派生的最新期次标签（如「2026 年 10 月 13 日更新（WEO October 2026）」）。
    // ⚠️ 2026-10-13 的教训：此前页尾把期次写死在 dashboard.js，改了数值却漏改文案。
    //    现在期次矩阵是唯一事实源，这里只做一次占位符替换，任何期次都不会再出现"数值新、文案旧"。
    const meta=(STATE.imfWoeMeta&&typeof STATE.imfWoeMeta==="object")?STATE.imfWoeMeta:{};
    const cc=Object.assign({},c,{source:(c.source||"").replace("{latest}",meta.latestLabel||"最新期次")});
    if(cc.ec && window.echarts){ renderWoeRevisions(box, id, cc); moveSource(box); return; }
    // ECharts 未加载时的回落：Chart.js 双线图（保底可用，不白屏）
    const months=(STATE.imfWoeMonths||[]).slice();
    const g26=STATE.imfWoe2026Growth||[], g27=STATE.imfWoe2027Growth||[];
    box.innerHTML=canvasBox(id,cc);
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:months,datasets:[
      {label:"2026 增速预测",data:g26,borderColor:"#0d9488",borderWidth:2.5,fill:false,tension:.2,pointRadius:3},
      {label:"2027 增速预测",data:g27,borderColor:"#7c3aed",borderWidth:2.5,borderDash:[6,4],fill:false,tension:.2,pointRadius:3}
    ]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:true,labels:{boxWidth:12,font:{size:10}}},
        tooltip:{callbacks:{label:cx=>cx.dataset.label+"："+(cx.parsed.y!=null?cx.parsed.y.toFixed(1):"-")+" %"}}},
      scales:{x:{grid:{display:false},ticks:xTime(8,months)},
        y:{grid:{color:"#eef2f7"},title:{display:true,text:"% 同比"}}}}});
    moveSource(box);
  },
  // 全球钻井平台数 World Rig Count 月度（1974 起 50+ 年长历史）
  // 双格联动（ECharts）：上格 = 全史概览并高亮「近 10 年」区间，下格 = 近 10 年细节；
  // 底部 dataZoom 同时作用于两格，十字线通过 axisPointer.link 上下贯穿。
  // 为什么不用单格：50 年跨度下近 10 年只占右侧约 20% 宽度，单格看不清近期趋势
  //（2020 前后约 1,800 台的低点、2024 回升到 2,400 台全被压平）。
  // 为什么不用对数轴：台数量级只差约 2.5 倍，取对数会把 2000–2020 的上升段压得更平。
  rigWorld: function(p){
    const {box,id,c,col}=p;
    const months=(STATE.rigMonths||[]).slice().sort();
    const vals=STATE.rigWorld||[];
    if(!months.length){ box.innerHTML="<div class='note'>钻井数数据缺失</div>"; return; }
    const tdata=months.map((m,i)=> vals[i]!=null?vals[i]:null);
    const src=c.source?("<div class='src'>"+c.source+"</div>"):"";
    const H=c.ecH||420;
    box.style.height=H+"px";

    if(!window.echarts){
      // ECharts 未加载时回落 Chart.js 单格（保持可用，不白屏）
      box.innerHTML=canvasBox(id,c);
      charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:months,datasets:[
        {label:c.title.split(" ")[0],data:tdata,borderColor:col,borderWidth:2,fill:true,backgroundColor:(ctx)=>vg(ctx,col,c.fillAlpha),tension:.2,pointRadius:0}]},
        options:{responsive:true,maintainAspectRatio:false,
          plugins:{legend:{display:false},tooltip:{callbacks:{label:cx=>cx.dataset.label+"："+(cx.parsed.y!=null?cx.parsed.y.toFixed(0):"-")+" 台"}}},
          scales:{x:{grid:{display:false},ticks:xTicks(12,months)},y:{grid:{color:"#eef2f7"},title:{display:true,text:"台"}}}}});
      moveSource(box);
      return;
    }
    box.innerHTML="<div id='ec_"+id+"' class='ecbox'></div>"+src;
    // .ecbox 是 height:100%，若把 .src 留在 .box 里会被 420px 的画布顶出框外（溢出卡片）。
    // 必须像其它 Chart.js 渲染器一样调 moveSource：把数据源条移到图框下方、卡片内部。
    moveSource(box);
    const el=$("ec_"+id);
    if(!el) return;
    if(ecCharts[id]){ ecCharts[id].dispose(); delete ecCharts[id]; }

    const n=months.length;
    const REC=Math.min(n,121);                       // 近 10 年 = 120 个月，+1 端点
    const all=tdata.filter(v=>v!=null);
    const rec=tdata.slice(n-REC).filter(v=>v!=null);
    // 轴上下界取整到 500 / 1000 的整数倍，避免出现 835.4 / 2486.6 这类脏刻度
    const aMin=Math.min.apply(null,all), aMax=Math.max.apply(null,all);
    const rMin=Math.min.apply(null,rec), rMax=Math.max.apply(null,rec);
    const aLo=Math.floor(aMin/1000)*1000, aHi=Math.ceil(aMax/1000)*1000;
    const rLo=Math.floor(rMin/500)*500, rHi=Math.ceil(rMax/500)*500;
    const startPct=Math.max(0,(n-REC)/n*100);
    const col2=col||"#0f766e";
    // 口径断点：2024-01 起 Baker Hughes 明细并入沙特 Operating Rigs（约 +263 台），
    // 官方 Worldwide = Active + Operating；此前仅 Active。前后两段不可直接比较，
    // 故在近 10 年格上打一条竖线标注（概览格里 2024-01 已贴在右边缘，标注无意义故不加）。
    const BRK="2024-01";
    const brkLine=months.indexOf(BRK)<0?[]:[{xAxis:BRK,
      label:{formatter:"口径调整",position:"insideEndTop",fontSize:10,color:"#b45309",
             backgroundColor:"rgba(255,255,255,.85)",padding:[2,4],borderRadius:3},
      lineStyle:{color:"#f59e0b",type:"dashed",width:1.2}}];
    const yAx=function(gi,min,max,ntick,showName){
      // ⚠️ gridIndex 必须显式写：多 grid + 多 yAxis 时省略它，ECharts 会在 setOption
      // 阶段抛 "Cannot read properties of undefined (reading 'type')"，整图白屏。
      // 上格（概览）不显示刻度标签：区间 1,016–6,227 台若按 splitNumber 细分会出现
      // -494.9 / 6.748k 这类脏刻度，反而干扰读图；概览只需形状，刻度交给下格。
      return {type:"value",gridIndex:gi,min:min,max:max,splitNumber:ntick,
        // 不设 axis name：单位「台」已写在卡片标题里，轴名会在顶端与最高刻度标签打架
        splitLine:{lineStyle:{color:"#eef2f7"}},
        axisLabel:{show:!!showName,fontSize:10,color:"#94a3b8",formatter:function(v){return v>=1000?(v/1000)+"k":""+v;}},
        axisLine:{show:false},axisTick:{show:false}};
    };
    const xAx=function(showLabel,sparse){
      return {type:"category",data:months,boundaryGap:false,
        axisTick:{alignWithLabel:true,show:showLabel},
        axisLine:{show:showLabel,lineStyle:{color:"#e4e9f0"}},
        axisLabel:{show:showLabel,fontSize:10,color:"#94a3b8",
          interval:sparse?Math.floor(months.length/3):"auto",hideOverlap:!sparse,
          showMinLabel:sparse,showMaxLabel:sparse,
          formatter:function(v){return fmtX(v);}}};
    };
    const tip={backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5}};
    const opt={
      animation:true,animationDuration:720,animationEasing:"cubicOut",
      backgroundColor:"transparent",
      grid:[{left:52,right:18,top:14,height:104},{left:52,right:18,top:156,bottom:64}],
      axisPointer:{link:[{xAxisIndex:"all"}],label:{backgroundColor:"#334155",fontSize:10}},
      tooltip:Object.assign({trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1}},
        formatter:function(ps){
          const q=ps[ps.length-1];
          if(!q||q.value==null) return q?q.name:"";
          return q.name+"<br/>"+c.title.split(" ")[0]+"："+Math.round(q.value).toLocaleString("en-US")+" 台";
        }},tip),
      xAxis:[Object.assign(xAx(true,true),{gridIndex:0}),Object.assign(xAx(true,false),{gridIndex:1})],
      yAxis:[yAx(0,aLo,aHi,3,false),yAx(1,rLo,rHi,4,true)],
      // ⚠️ dataZoom 只作用在下格（xAxisIndex:1）：若把上格也加进 xAxisIndex，
      // 上格会被一起放大而失去「全史概览」的意义（默认就该看 50 年）。
      // 上格改为用 markArea 高亮当前窗口，拖动滑块时同步更新（见下方 dataZoom 回调）。
      dataZoom:[
        {type:"inside",xAxisIndex:1,zoomOnMouseWheel:true,moveOnMouseMove:true,start:startPct,end:100},
        {type:"slider",xAxisIndex:1,height:16,bottom:8,start:startPct,end:100,
         borderColor:"#e4e9f0",fillerColor:"rgba(15,118,110,.10)",
         handleStyle:{color:"#0f766e",borderColor:"#0f766e"},moveHandleStyle:{color:"#cbd5e1"},
         dataBackground:{lineStyle:{color:"#cbd5e1",width:1},areaStyle:{color:"#eef2f7"}},
         selectedDataBackground:{lineStyle:{color:"#0f766e",width:1},areaStyle:{color:"rgba(15,118,110,.14)"}},
         labelFormatter:function(v,vs){return fmtX(vs);},textStyle:{fontSize:10,color:"#94a3b8"}}
      ],
      series:[
        // 上格：全史概览，淡灰无填充（非 0 基线下面积无量含义，方案 B）；近 10 年区间高亮
        {name:"全史",type:"line",xAxisIndex:0,yAxisIndex:0,data:tdata,symbol:"none",silent:true,
         lineStyle:{width:1.3,color:"#c3cbd5"},
         markArea:{silent:true,
           itemStyle:{color:"rgba(15,118,110,.10)",borderColor:"rgba(15,118,110,.40)",borderWidth:0.5},
           data:[[{xAxis:n-REC},{xAxis:n-1}]]},
         markLine:{silent:true,symbol:"none",precision:0,
           data:[{yAxis:aLo,label:{formatter:"轴起点 "+aLo+"（非 0）",position:"insideStartTop",fontSize:10,color:"#94a3b8"},
         lineStyle:{color:"#cbd5e1",type:"dashed",width:1}}]}},
        // 下格：细节（同一份全量数据，被 dataZoom 窗口裁出近 10 年）
        {name:"近 10 年",type:"line",xAxisIndex:1,yAxisIndex:1,data:tdata,symbol:"none",
         lineStyle:{width:2,color:col2},
         markLine:brkLine.length?{silent:true,symbol:"none",precision:0,data:brkLine}:undefined}
      ]
    };
    ecCharts[id]=echarts.init(el);
    ecCharts[id].setOption(opt);
    // inside 与 slider 是两个独立组件，拖动其中之一要把窗口同步给另一个；
    // 同时把当前窗口回写为上格的 markArea 高亮（flag 防自激循环）。
    (function(inst,n0,start0,seriesData){
      let syncing=false;
      function currentRange(){
        const dz=inst.getOption().dataZoom.filter(function(d){return d.start!=null;})[0];
        if(!dz) return [Math.max(0,Math.round(start0/100*(n0-1))), n0-1];
        return [Math.round((dz.start||0)/100*(n0-1)), Math.min(n0-1,Math.round((dz.end||100)/100*(n0-1)))];
      }
      function paint(){
        if(syncing) return;
        syncing=true;
        try{
          const dzs=inst.getOption().dataZoom;
          const dz=dzs.filter(function(d){return d.type==="slider";})[0]||dzs[0];
          if(dz) inst.dispatchAction({type:"dataZoom",dataZoomIndex:dzs.length-1,start:dz.start,end:dz.end});
          const r=currentRange();
          // 下格 Y 轴随窗口自适应（否则放大到早期窗口时，2014 年 4,000+ 峰值会被削平在轴顶）
          const win=seriesData.slice(r[0],r[1]+1).filter(function(v){return v!=null;});
          let lo=Math.floor(Math.min.apply(null,win)/500)*500;
          let hi=Math.ceil(Math.max.apply(null,win)/500)*500;
          if(hi<=lo) hi=lo+500;
          inst.setOption({
            yAxis:[{}, {min:lo, max:hi}],
            series:[{name:"全史",markArea:{data:[[{xAxis:r[0]},{xAxis:r[1]}]]}}]
          });
        }catch(e){ /* 面板已销毁时忽略 */ }
        syncing=false;
      }
      inst.on("dataZoom",paint);
      paint();
    })(ecCharts[id],n,startPct,tdata);
  },
  // OPEC 原油产量月度（含主要产油国细线）
  // ⚠️ 2026-10-11 **换源**：数据由 MOMR 表 5-7 的 12 国（含阿联酋，2023-11~2026-08 共 34 月）
  //    整体换成 **EIA STEO API** 的 **OPEC 11 国分项**（COPR_SA/IZ/IR/KU/VE/NI/LY/AG/CF/EK/GB，
  //    不含阿联酋；月份轴与全球图同一条 steoMonths，2022-01~2026-09 历史段共 57 个月）。
  //    国家增删：**−阿联酋**（STEO 的 OPEC 定义本就不含），其余 11 国不变。
  //    恒等：11 国之和 == OPEC total（steo_monthly.py 脚本内逐月自验，容差 0.05，0 违例）。
  //    ⚠️ STEO **分国行只有历史段有值**（2026-10 起预测月为 null，EIA 不提供分国预测）
  //    → x 轴截到末个历史月（steoLastHistorical = 2026-09），不画空段；
  //      合计的预测段不在此图（见上方全球图），卡头徽章 =「合计 20.80 · 截至 26/09」。
  //    ⚠️ 11 国 ≠ MOMR 12 国口径（少阿联酋 ~3.3 mb/d），与换源前的 24.08 徽章不可直接对比。
  // 2026-10-10 改造（沿用）：**ECharts 双格**：上格 = 沙特，下格 = 其余十国，共享 x 轴；
  //    末点 endLabel 数值 + labelLayout moveOverlap:'shiftY' 避叠（下格末值密集：
  //    1.49/1.27/1.21/0.98/0.27/0.22/0.04，最小相邻差不足 4px，必须避叠）。
  //    ⚠️ grid / xAxis / yAxis 必须显式 gridIndex（省略 → setOption 抛错 → 整图白屏，同 rigWorld）。
  //    ⚠️ 图例 11 项会折行（2~3 行），故上格 top 预留 44px（不是 nonopecdoc 的 26px）。
  //    ECharts 未加载时回落到 Chart.js 单轴版，不白屏。
  opecMonthly: function(p){
    const {box,id,c,xTicks}=p;
    // 月份轴：STEO 72 月截到末个历史月（分国无预测段）
    const all=(STATE.steoMonths||[]).slice();
    const histEnd=(STATE.steoLastHistorical!=null)?all.indexOf(STATE.steoLastHistorical):-1;
    const months=(histEnd>=0)?all.slice(0,histEnd+1):all;
    const members=STATE.steoOpecMembers||{};
    // 11 国（STEO 脚注 c 口径），按末个历史月产量降序；色板沿用旧 12 国版（去阿联酋绿）
    const major=[["沙特","沙特","#dc2626"],["伊拉克","伊拉克","#ea580c"],
                 ["伊朗","伊朗","#d97706"],["科威特","科威特","#0891b2"],
                 ["尼日利亚","尼日利亚","#db2777"],["利比亚","利比亚","#7c3aed"],
                 ["委内瑞拉","委内瑞拉","#0d9488"],["阿尔及利亚","阿尔及利亚","#65a30d"],
                 ["刚果","刚果","#2563eb"],["加蓬","加蓬","#f43f5e"],
                 ["赤道几内亚","赤道几内亚","#facc15"]];
    const data={}; major.forEach(function(m){
      if(members[m[0]]) data[m[0]]=(members[m[0]]||[]).slice(0,months.length);
    });
    if(!window.echarts){
      box.innerHTML=canvasBox(id,c);
      const datasets=[];
      for(const [zh,,cc] of major){ if(data[zh]) datasets.push({label:zh,data:data[zh],borderColor:cc,borderWidth:1.8,fill:false,tension:.25,pointRadius:0,yAxisID:"y"}); }
      charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:months,datasets},
        options:{responsive:true,maintainAspectRatio:false,
          plugins:{legend:{display:true,labels:{boxWidth:12,font:{size:10}}},
            tooltip:{callbacks:{label:function(cx){return cx.dataset.label+"："+(cx.parsed.y!=null?cx.parsed.y.toFixed(2):"-")+" 百万桶/日";}}},
          scales:{x:{grid:{display:false},ticks:xTicks(12,months)},
            y:{position:"left",min:0,max:10.5,grid:{color:"#eef2f7"},ticks:{font:{size:10}},title:{display:true,text:"百万桶/日"}}}}}});
      moveSource(box);
      return;
    }
    const H=c.ecH||EC2_H;
    box.style.height=H+"px";
    const src=c.source?("<div class='src'>"+c.source+"</div>"):"";
    box.innerHTML="<div id='ec_"+id+"' class='ecbox'></div>"+src;
    moveSource(box);
    const el=$("ec_"+id);
    if(!el) return;
    if(ecCharts[id]){ ecCharts[id].dispose(); delete ecCharts[id]; }
    const nice=function(v,step,up){ return up?Math.ceil(v/step)*step:Math.floor(v/step)*step; };
    const flat=function(ks){ const o=[]; ks.forEach(function(k){ (data[k]||[]).forEach(function(v){ if(v!=null) o.push(v); }); }); return o; };
    const TOP=["沙特"];                               // 上格成员（唯一的高量级产油国）
    const have=major.filter(function(m){return data[m[0]];}).map(function(m){return m[0];});
    const topN=have.filter(function(k){return TOP.indexOf(k)>=0;});
    const botN=have.filter(function(k){return TOP.indexOf(k)<0;});
    const tAll=flat(topN), bAll=flat(botN);
    const tLo=tAll.length?nice(Math.min.apply(null,tAll)-0.1,0.25,false):7.75;
    const tHi=tAll.length?nice(Math.max.apply(null,tAll)+0.1,0.25,true):10.25;
    const bHi=bAll.length?nice(Math.max.apply(null,bAll)+0.1,0.25,true):5;
    const yAx=function(gi,min,max,nt){
      return {type:"value",gridIndex:gi,min:min,max:max,splitNumber:nt,
        splitLine:{lineStyle:{color:"#eef2f7"}},
        axisLabel:{fontSize:10,color:"#94a3b8",formatter:function(v){return Number(v).toFixed(1);}},
        axisLine:{show:false},axisTick:{show:false}};
    };
    const xAx=function(gi,showLabel){
      return {type:"category",gridIndex:gi,data:months,boundaryGap:false,
        axisTick:{alignWithLabel:true,show:showLabel},
        axisLine:{show:showLabel,lineStyle:{color:"#e4e9f0"}},
        axisLabel:{show:showLabel,fontSize:10,color:"#94a3b8",
          interval:Math.floor(months.length/6),hideOverlap:true,showMinLabel:true,showMaxLabel:true,
          formatter:function(v){return fmtX(v);}}};
    };
    const tip={backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5}};
    const series=major.filter(function(m){return data[m[0]];}).map(function(m,idx){
      const isTop=TOP.indexOf(m[0])>=0;
      const s={name:m[1],type:"line",
        xAxisIndex:isTop?0:1, yAxisIndex:isTop?0:1,
        data:data[m[0]], symbol:"none", connectNulls:false,
        // ⚠️ itemStyle.color 必须与 lineStyle.color 同色：ECharts 的**图例标记取 itemStyle**，
        //    只设 lineStyle 时图例回落默认调色盘（#5470c6/#91cc75/…），与折线配色对不上。
        itemStyle:{color:m[2]},
        lineStyle:{width:isTop?2.2:1.9,color:m[2]},
        endLabel:{show:true,distance:6,fontSize:10,fontWeight:600,color:m[2],
          formatter:function(pp){return (pp.value!=null&&pp.value!=="-")?Number(pp.value).toFixed(2):"";}},
        labelLayout:{moveOverlap:"shiftY",hideOverlap:false}
      };
      // 历史事件竖线：2026-02-28 中东军事行动（伊朗冲突）+ 霍尔木兹海峡事实性关闭，
      // 中东多国（沙特/伊拉克/科威特等）关停原油生产 → OPEC 全线供给冲击，上下 grid 都画；
      // 标签仅上格（沙特），下格首序列（伊拉克 idx===1）仅画线不重复标签。
      if(isTop||idx===1){
        s.markLine={
          symbol:["none","none"],
          lineStyle:{color:"#64748b",type:"dashed",width:1.4},
          label:{show:isTop,color:"#475569",fontSize:10,fontWeight:600,
                 position:"end",formatter:"{b}"},
          data:[
            {xAxis:"2026-02",name:"霍尔木兹关闭 26/02"}
          ]
        };
      }
      return s;
    });
    const opt={
      animation:true,animationDuration:720,animationEasing:"cubicOut",
      backgroundColor:"transparent",
      legend:{top:0,left:"center",itemGap:12,icon:"circle",itemWidth:9,itemHeight:9,
        textStyle:{fontSize:9,color:"#334155",fontWeight:600},
        data:major.filter(function(m){return data[m[0]];}).map(function(m){return m[1];})},
      grid:ec2Grid(),
      axisPointer:{link:[{xAxisIndex:"all"}],label:{backgroundColor:"#334155",fontSize:10}},
      tooltip:Object.assign({trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1}},
        formatter:function(ps){
          if(!ps||!ps.length) return "";
          let s=String(ps[0].name);
          ps.forEach(function(q){ if(q.value!=null&&q.value!=="-") s+="<br/>"+q.marker+q.seriesName+"："+Number(q.value).toFixed(2)+" 百万桶/日"; });
          return s;
        }},tip),
      xAxis:[xAx(0,false),xAx(1,true)],
      yAxis:[yAx(0,tLo,tHi,3),yAx(1,0,bHi,4)],
      series:series
    };
    ecCharts[id]=echarts.init(el);
    ecCharts[id].setOption(opt);
  },
  // OPEC+ 里的**非 OPEC**参与国（DoC 10 国）原油产量月度。
  // ⚠️ 2026-10-11 **换源**：数据由 MOMR 表 5-7 的 `Total Non-OPEC DoC` + 10 国（31 月，
  //    2024-02~2026-08）整体换成 **EIA STEO API** 的 **OPEC+ other
  //    participants** 段（COPR_RS/KZ/MX/MU/AJ/MY/OD/BX/BA/SU）—— **与 MOMR DoC 同一份 10 国清单**，
  //    合计行 = COPR_OPECPLUS_OTHER，月份轴与全球图同一条 steoMonths，截到末个历史月
  //    → **57 月 2022-01~2026-09**（比 MOMR 版早 26 个月、晚 1 个月）。
  //    恒等：10 国之和 == COPR_OPECPLUS_OTHER（steo_monthly.py 脚本内逐月自验，0 违例）。
  //    量级互证：STE 2026-08 合计 13.94 vs MOMR 13.97（二手来源 vs EIA 估计，差 0.03 属正常）。
  //    ⚠️ STEO **分国行只有历史段有值**（2026-10 起预测月为 null）→ x 轴止于 26/09；
  //       合计的预测段不在此图，卡头徽章 =「合计 14.05 · 截至 26/09」（steoHistCut）。
  //    口径：单位 mb/d，原油不含 NGL。恒等仍在数据层校验，图内不画合计线。
  // 2026-10-10 改造（沿用）：**ECharts 双格**——上格 = 俄罗斯，下格 = 其余九国，共享 x 轴；
  //    末点 endLabel 数值 + `moveOverlap:'shiftY'` 避叠；axisPointer.link 十字线贯穿两格。
  //    ⚠️ grid / xAxis / yAxis 必须显式 gridIndex（省略 → setOption 抛错 → 整图白屏，同 rigWorld）。
  //    ⚠️ 下格起点取 0：苏丹/巴林/文莱/南苏丹 0.03–0.1 量级贴底属真实分布。
  //    ECharts 未加载时回落到 Chart.js 单轴版，不白屏。
  nonOpecDoCTotal: function(p){
    const {box,id,c,xTicks}=p;
    // 月份轴：STEO 72 月截到末个历史月（分国无预测段）
    const all=(STATE.steoMonths||[]).slice();
    const histEnd=(STATE.steoLastHistorical!=null)?all.indexOf(STATE.steoLastHistorical):-1;
    const months=(histEnd>=0)?all.slice(0,histEnd+1):all;
    const members=STATE.steoDocMembers||{};
    // 10 国（STEO 脚注 b 的 other participants），色板沿用旧 MOMR DoC 版
    const major=[["俄罗斯","俄罗斯","#4f81bd"],["哈萨克斯坦","哈萨克斯坦","#92d050"],
                 ["墨西哥","墨西哥","#f5c842"],["阿曼","阿曼","#e94e5a"],
                 ["阿塞拜疆","阿塞拜疆","#7c3aed"],["马来西亚","马来西亚","#ea580c"],
                 ["南苏丹","南苏丹","#6366f1"],["文莱","文莱","#0d9488"],
                 ["巴林","巴林","#0891b2"],["苏丹","苏丹","#db2777"]];
    const data={}; major.forEach(function(m){
      if(members[m[0]]) data[m[0]]=(members[m[0]]||[]).slice(0,months.length);
    });
    if(!window.echarts){
      box.innerHTML=canvasBox(id,c);
      const tailPlugin=makeInlineTailPlugin("nonDocTail",major);
      const datasets=[];
      for(const m of major){
        const zh=m[0], cc=m[2];
        if(data[zh]) datasets.push({label:zh,data:data[zh],borderColor:cc,borderWidth:1.9,fill:false,tension:.25,pointRadius:0,yAxisID:"y"});
      }
      charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:months,datasets},
        options:{responsive:true,maintainAspectRatio:false,
          plugins:{legend:{display:true,labels:{boxWidth:12,font:{size:10}}},
            tooltip:{callbacks:{label:function(cx){return cx.dataset.label+"："+(cx.parsed.y!=null?cx.parsed.y.toFixed(2):"-")+" 百万桶/日";}}},
          scales:{x:{grid:{display:false},ticks:xTicks(12,months)},
            y:{position:"left",min:0,max:10.5,grid:{color:"#eef2f7"},ticks:{font:{size:10}},title:{display:true,text:"百万桶/日"}}}}},
        plugins:[tailPlugin]});
      moveSource(box);
      return;
    }
    const H=c.ecH||EC2_H;
    box.style.height=H+"px";
    const src=c.source?("<div class='src'>"+c.source+"</div>"):"";
    box.innerHTML="<div id='ec_"+id+"' class='ecbox'></div>"+src;
    moveSource(box);
    const el=$("ec_"+id);
    if(!el) return;
    if(ecCharts[id]){ ecCharts[id].dispose(); delete ecCharts[id]; }
    // 轴上下界（数据驱动）：上格贴俄罗斯（全史 8.72–10.07）→ 0.25 步进取整；
    // 下格覆盖其余九国（0.03–1.87 量级）→ 0 起
    const nice=function(v,step,up){ return up?Math.ceil(v/step)*step:Math.floor(v/step)*step; };
    const flat=function(ks){ const o=[]; ks.forEach(function(k){ (data[k]||[]).forEach(function(v){ if(v!=null) o.push(v); }); }); return o; };
    const oAll=flat(major.filter(function(m){return m[0]!=="俄罗斯";}).map(function(m){return m[0];}));
    const rAll=flat(["俄罗斯"]);
    // 步长取 0.25（0.5 会把上格上界从 9.75 顶到 10、下格从 2.0 顶到 2.5，线又被压扁一半）
    const rLo=rAll.length?nice(Math.min.apply(null,rAll)-0.1,0.25,false):8.5;
    const rHi=rAll.length?nice(Math.max.apply(null,rAll)+0.1,0.25,true):9.75;
    const oHi=oAll.length?nice(Math.max.apply(null,oAll)+0.1,0.25,true):2;
    // 下格起点取 0：九国最低值 0.021（苏丹），若压掉 0–0.5 会把这些小国整条裁掉；
    // 故本图下格从 0 起（与 OPEC 图下格 0–4.5 一致）。九国里苏丹/巴林/文莱/南苏丹贴底属真实量级。
    const oLo=oAll.length?Math.max(0,nice(Math.min.apply(null,oAll)-0.1,0.25,false)):0;
    const yAx=function(gi,min,max,nt){
      return {type:"value",gridIndex:gi,min:min,max:max,splitNumber:nt,
        splitLine:{lineStyle:{color:"#eef2f7"}},
        axisLabel:{fontSize:10,color:"#94a3b8",formatter:function(v){return Number(v).toFixed(1);}},
        axisLine:{show:false},axisTick:{show:false}};
    };
    const xAx=function(gi,showLabel){
      return {type:"category",gridIndex:gi,data:months,boundaryGap:false,
        axisTick:{alignWithLabel:true,show:showLabel},
        axisLine:{show:showLabel,lineStyle:{color:"#e4e9f0"}},
        axisLabel:{show:showLabel,fontSize:10,color:"#94a3b8",
          interval:Math.floor(months.length/6),hideOverlap:true,showMinLabel:true,showMaxLabel:true,
          formatter:function(v){return fmtX(v);}}};
    };
    const tip={backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5}};
    const series=major.filter(function(m){return data[m[0]];}).map(function(m,idx){
      const isRu=m[0]==="俄罗斯";
      const s={name:m[1],type:"line",
        xAxisIndex:isRu?0:1, yAxisIndex:isRu?0:1,
        data:data[m[0]], symbol:"none", connectNulls:false,
        // ⚠️ 同 OPEC 图：itemStyle.color 必须与 lineStyle.color 同色，否则图例回落默认调色盘
        itemStyle:{color:m[2]},
        lineStyle:{width:isRu?2.2:1.9,color:m[2]},
        endLabel:{show:true,distance:6,fontSize:10,fontWeight:600,color:m[2],
          formatter:function(pp){return (pp.value!=null&&pp.value!=="-")?Number(pp.value).toFixed(2):"";}},
        labelLayout:{moveOverlap:"shiftY",hideOverlap:false}};
      // 历史事件竖线：事件完全是俄罗斯的，只挂在上格（grid 0 俄罗斯序列）即可，
      // 不画到下格（grid 1 那 9 国）——避免让人误以为事件也影响了它们。
      // 俄乌冲突 2022-02-24、欧盟对俄海运原油禁运 2022-12-05 生效、
      // OPEC+ 自愿减产 2023-11 宣布（2.2 mb/d 集团减产，2024 起生效，驱动俄 2023→2024 台阶下行）。
      if(isRu){
        s.markLine={
          symbol:["none","none"],
          lineStyle:{color:"#64748b",type:"dashed",width:1.4},
          label:{show:true,color:"#475569",fontSize:10,fontWeight:600,
                 position:"end",formatter:"{b}"},
          data:[
            {xAxis:"2022-02",name:"俄乌冲突 22/02"},
            {xAxis:"2022-12",name:"欧盟禁运 22/12"},
            {xAxis:"2023-11",name:"OPEC+ 自愿减产 23/11"}
          ]
        };
      }
      return s;
    });
    const opt={
      animation:true,animationDuration:720,animationEasing:"cubicOut",
      backgroundColor:"transparent",
      legend:{top:0,left:"center",itemGap:16,icon:"circle",itemWidth:9,itemHeight:9,
        textStyle:{fontSize:9,color:"#334155",fontWeight:600},
        data:major.filter(function(m){return data[m[0]];}).map(function(m){return m[1];})},
      grid:ec2Grid(),
      axisPointer:{link:[{xAxisIndex:"all"}],label:{backgroundColor:"#334155",fontSize:10}},
      tooltip:Object.assign({trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1}},
        formatter:function(ps){
          if(!ps||!ps.length) return "";
          let s=String(ps[0].name);
          ps.forEach(function(q){ if(q.value!=null&&q.value!=="-") s+="<br/>"+q.marker+q.seriesName+"："+Number(q.value).toFixed(2)+" 百万桶/日"; });
          return s;
        }},tip),
      xAxis:[xAx(0,false),xAx(1,true)],
      yAxis:[yAx(0,rLo,rHi,3),yAx(1,oLo,oHi,4)],
      series:series
    };
    ecCharts[id]=echarts.init(el);
    ecCharts[id].setOption(opt);
  },
  // 全球原油产量：EIA STEO API 的 COPR_* 序列（月度，窗口 2022-01~2027-12 共 72 个月）。
  // ⚠️ 2026-10-10 由 STEO 月报 PDF 的**季度**列改为**月度**；2026-10-16 再换源：
  //    由「手工下载 base tables Excel（3atab/3dtab）+ 离线解析」改为 **实时 API**。
  // 四条线 = World / OPEC / Non-OPEC DoC / Others，均为 **Crude oil**（原油，不含 NGL），同源故预测段同画虚线。
  //   - World / OPEC / Non-OPEC：COPR_WORLD / COPR_OPEC / COPR_NONOPEC。
  //   - Non-OPEC DoC：COPR_OPECPLUS_OTHER（DoC 10 国合计，STATE.steoDoCTotal，含预测段）。
  //   - Others = Non-OPEC − Non-OPEC DoC（元素级相减，任一为 null 则置 null）。
  //     阿联酋按本看板口径计入 Others（OPEC 线为 11 国 ex-UAE；UAE 自 2026-05 已非 OPEC+，落在 Others 合规）。
  // ⚠️ 值是 mb/d **日均速率**（月值即该月日均），**不得做任何月度加总/平均换算**。
  // 预测边界由 API 分国行的最后非空月推导（lastHistorical=2026-09 → 2026-10 起为预测），
  // 四条线同源同表，故**四者**的预测段都画虚线。
  steoWorld: function(p){
    const {box,id,c,col,fillFn,xTicks}=p;
    const months=(STATE.steoMonths||[]).slice();
    const w=STATE.steoWorldMonthly||[], o=STATE.steoOpecMonthly||[], n=STATE.steoNonOpecMonthly||[], doc=STATE.steoDoCTotal||[];
    // Others = Non-OPEC − Non-OPEC DoC（元素级相减；阿联酋含在其中，按口径不单独拆分）
    const others=n.map(function(v,i){ return (v!=null&&doc[i]!=null)?v-doc[i]:null; });
    box.innerHTML=canvasBox(id,c);
    // x 轴标签就是月份键 "YYYY-MM"，经 xTime→fmtX 渲染成 "22/01"（与全站日期格式一致）。
    const xlab=months.slice();
    // 预测段起点：优先后端算好的 forecastIndex；缺失时按 forecastStart 月份反查（防御）。
    // ⚠️ 兜底取 months.length（而非 0）：既不越界，也不会把整条线误画成虚线。
    let fcIdx=(STATE.steoForecastIndex!=null)?STATE.steoForecastIndex:months.indexOf(STATE.steoForecastStart);
    if(!(fcIdx>0)) fcIdx=months.length;
    const dashSegment=function(ctx){return ctx.p1DataIndex<fcIdx?[]:[6,4];};
    // 实线尾端数值徽章：只挂在最新实际值（< fcIdx），不挂预测虚线尾；配色与线同色、白字。
    const endBadgePlugin={
      id:'endBadge',
      afterDatasetsDraw:function(chart){
        const ctx=chart.ctx, area=chart.chartArea;
        const font='600 10px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        const badges=[];
        chart.data.datasets.forEach(function(ds,di){
          const meta=chart.getDatasetMeta(di);
          if(meta.hidden) return;
          let idx=-1;
          const limit=Math.min(fcIdx, ds.data.length)-1;
          for(let j=limit;j>=0;j--){
            if(ds.data[j]!=null && isFinite(ds.data[j])){ idx=j; break; }
          }
          if(idx<0) return;
          const pt=meta.data[idx];
          if(!pt) return;
          const val=Number(ds.data[idx]);
          const color=ds.borderColor;
          ctx.font=font;
          const text=val.toFixed(2);
          const tw=ctx.measureText(text).width;
          const padX=5, padY=3, h=10+padY*2, r=6, gap=7;
          const w=tw+padX*2;
          badges.push({x:pt.x+gap, y:pt.y, w,h,r,text,color, cx:pt.x, cy:pt.y, di});
        });
        // 简易防重叠：按 y 排序，重叠则向下推开
        badges.sort(function(a,b){return a.y-b.y;});
        for(let i=1;i<badges.length;i++){
          const prev=badges[i-1], cur=badges[i];
          if(cur.y-cur.h/2 < prev.y+prev.h/2+2){
            cur.y=prev.y+prev.h/2+cur.h/2+3;
          }
        }
        badges.forEach(function(b){
          ctx.save();
          // 线端小圆点
          ctx.beginPath();
          ctx.arc(b.cx, b.cy, 3.5, 0, Math.PI*2);
          ctx.fillStyle='#fff';
          ctx.strokeStyle=b.color;
          ctx.lineWidth=2;
          ctx.fill();
          ctx.stroke();
          // 保持徽章在绘图区内
          let bx=b.x;
          if(bx+b.w > area.right-2) bx=area.right-b.w-2;
          if(bx < area.left+2) bx=area.left+2;
          let by=b.y;
          if(by+b.h/2 > area.bottom-2) by=area.bottom-b.h/2-2;
          if(by-b.h/2 < area.top+2) by=area.top+b.h/2+2;
          // 圆角矩形
          ctx.beginPath();
          const rr=Math.min(b.r, b.w/2, b.h/2);
          ctx.moveTo(bx+rr, by-b.h/2);
          ctx.lineTo(bx+b.w-rr, by-b.h/2);
          ctx.quadraticCurveTo(bx+b.w, by-b.h/2, bx+b.w, by-b.h/2+rr);
          ctx.lineTo(bx+b.w, by+b.h/2-rr);
          ctx.quadraticCurveTo(bx+b.w, by+b.h/2, bx+b.w-rr, by+b.h/2);
          ctx.lineTo(bx+rr, by+b.h/2);
          ctx.quadraticCurveTo(bx, by+b.h/2, bx, by+b.h/2-rr);
          ctx.lineTo(bx, by-b.h/2+rr);
          ctx.quadraticCurveTo(bx, by-b.h/2, bx+rr, by-b.h/2);
          ctx.closePath();
          ctx.fillStyle=b.color;
          ctx.fill();
          // 文字
          ctx.fillStyle='#fff';
          ctx.textBaseline='middle';
          ctx.textAlign='center';
          ctx.font=font;
          ctx.fillText(b.text, bx+b.w/2, by);
          ctx.restore();
        });
      }
    };
    // 视觉沿用 2026-10-09 定的那套：不铺面积（fill:false）、不画圆点（pointRadius:0）、
    // 靠颜色区分；线宽层级保留——World 2.6 当主线，其余 1.9。`fillFn`/`c.fillAlpha` 不使用。
    const datasets=[
      {label:"World",data:w,borderColor:col,borderWidth:2.6,fill:false,tension:.2,pointRadius:0,borderDash:[6,4],segment:{borderDash:dashSegment}},
      {label:"OPEC",data:o,borderColor:"#dc2626",borderWidth:1.9,fill:false,tension:.2,pointRadius:0,borderDash:[6,4],segment:{borderDash:dashSegment}},
      {label:"Non-OPEC DoC",data:doc,borderColor:"#d97706",borderWidth:1.9,fill:false,tension:.2,pointRadius:0,borderDash:[6,4],segment:{borderDash:dashSegment}},
      {label:"Others",data:others,borderColor:"#7c3aed",borderWidth:1.9,fill:false,tension:.2,pointRadius:0,borderDash:[6,4],segment:{borderDash:dashSegment}}
    ];
    // y 轴：**数据驱动**的非 0 起点（沿用图1「轴起点贴近数据最小值」的标准）。
    // ⚠️ 三条线的实际跨度：OPEC 16.41（**2026-05 深坑**，STEO 情景里的中东非计划停产）
    //    ~ World 83.03（2027-11）。若让 Chart.js 自动缩放 → 10–90，底部 10~16.4 仍是空白。
    //    故按数据 min/max 向 **5 的整数倍**取整：15–85，刻度步长交给 Chart.js 自动
    //    （不写死 stepSize，否则 15/85 这种非整十端点会与刻度错位）。
    const all=[].concat(w,o,doc,others).filter(v=>v!=null&&isFinite(v));
    let yOpt={grid:{color:"#eef2f7"},ticks:{font:{size:10}},title:{display:true,text:"百万桶/日"}};
    if(all.length){
      const lo=Math.floor(Math.min.apply(null,all)/5)*5, hi=Math.ceil(Math.max.apply(null,all)/5)*5;
      if(hi>lo){ yOpt.min=lo; yOpt.max=hi; }
    }
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:xlab,datasets},
      plugins:[endBadgePlugin],
      options:{responsive:true,maintainAspectRatio:false,
        // 2026-10-10：沿用「美国原油产量」图的 level 标准——y 轴非 0 起点时画「轴起点 X（非 0）」
        //   虚线基线，避免读者把曲线下方误读为面积/量级。本图 fill 已关，符合 baseNote 前提。
        plugins:{legend:{display:true,labels:{boxWidth:12,font:{size:10}}},baseNote:{on:true},
          tooltip:{callbacks:{title:ts=>months[ts[0].dataIndex]!=null?months[ts[0].dataIndex]:"",
                              label:cx=>cx.dataset.label+"："+(cx.parsed.y!=null?cx.parsed.y.toFixed(2):"-")+" 百万桶/日"}}},
        // ⚠️ x 轴有 72 个点，刻度上限必须压到 12（约每半年一个）；若沿用 points 数会让
        //    72 个 "22/01" 式标签糊成一片（Chart.js 的 maxTicksLimit 需显式给，不会自动稀疏）。
        scales:{x:{grid:{display:false},ticks:xTicks(12,xlab)}, y:yOpt}}});
    moveSource(box);
  },
  // OECD 商业原油库存月度（原油实线 + 商业总库存含油品虚线对照）
  // OECD 商业库存（月度）：商业原油库存 vs 成品油库存（IEA 口径 Products 行）
  // 两行量级接近（crude ~1,330 / products ~1,440 mb），故**同轴**即可，不需要左右双轴。
  // ⚠️ 口径：Products = 成品油 + 石化产品等非原油商业库存，**不含原油**；
  //    MOMR 表 9-1 另有 Total 行（= crude + products，含原油），两者不可混用。
  oecdCrude: function(p){
    const {box,id,c,col,fillFn,xTicks}=p;
    const months=(STATE.oecdMonths||[]).slice().sort();
    const crude=STATE.oecdCrude||[]; const prod=STATE.oecdProducts||[];
    const cdata=months.map((m,i)=> crude[i]!=null?crude[i]:null);
    const pdata=months.map((m,i)=> prod[i]!=null?prod[i]:null);
    box.innerHTML=canvasBox(id,c);
    const datasets=[
      {label:"商业原油库存",data:cdata,borderColor:col,borderWidth:2.5,fill:!c.level,backgroundColor:fillFn,tension:.25,pointRadius:3},
      {label:"成品油库存（含石化产品）",data:pdata,borderColor:"#0891b2",borderWidth:2,borderDash:[6,4],fill:false,tension:.25,pointRadius:2}
    ];
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:months,datasets},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
        plugins:{legend:{display:true,labels:{boxWidth:12,font:{size:10}}},baseNote:{on:!!c.level},endTag:{on:true,n:0},
          tooltip:{callbacks:{label:cx=>cx.dataset.label+"："+(cx.parsed.y!=null?cx.parsed.y.toFixed(0):"-")+" 百万桶"}}},
        scales:{x:{grid:{display:false},ticks:xTicks(12,months)},
          y:{grid:{color:"#eef2f7"},title:{display:true,text:"百万桶"}}}}});
    moveSource(box);
  },
  // 美国战略石油储备 SPR：2026-10-07 起直接走 EIA 周度原始序列（key "eia.spr"），
  // 由 __default__ 的原生周轴渲染，不再自建月度渲染器（月度序列只供维度 KPI 芯片）。
  // 裂解价差（月度均值，bar）
  crack: function(p){
    const {box,id,c,col}=p;
    // 可选 mFrom（起始年月，如 "2024-01"）：覆盖默认 RANGE 窗口，用于展示更长历史。
    // 前提：底层数据已覆盖该起点（由 config.START_DATE 控制 FRED 抓取起点）。
    // 未配 mFrom 时行为与原来完全一致（仅取近 RANGE 天）。
    const full=getSeries("crack")||[];
    let i0=Math.max(0,STATE.dates.length-RANGE);
    if(c.mFrom){
      const k=STATE.dates.findIndex(function(x){return x.slice(0,7)>=c.mFrom;});
      if(k>=0) i0=k;
    }
    const win=STATE.dates.slice(i0), dwin=full.slice(i0);
    const byMonth={};win.forEach((dt,i)=>{const mk=dt.slice(0,7);if(dwin[i]!=null){if(!byMonth[mk])byMonth[mk]={s:0,n:0};byMonth[mk].s+=dwin[i];byMonth[mk].n++;}});
    const mk=Object.keys(byMonth).sort();const mv=mk.map(m=>(byMonth[m].s/byMonth[m].n));
    box.innerHTML=canvasBox(id,c);
    charts[id]=new Chart($("cv_"+id),{type:"bar",data:{labels:mk,datasets:[{data:mv,backgroundColor:col+"cc",borderRadius:4}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:cx=>"裂解价差："+(mv[cx.dataIndex]!=null?mv[cx.dataIndex].toFixed(1):"-")+" $/bbl"}}},
        scales:{x:{grid:{display:false},ticks:Object.assign(xTime(10,mk),{font:{size:10}})},y:{grid:{color:"#eef2f7"},title:{display:true,text:"$/bbl"}}}}});
    moveSource(box);
  },
  // 炼厂开工率（美国）/ 原油加工量（中国）：双轴
  refinery: function(p){
    const {box,id,c,col}=p;
    const months=(STATE.usUtilMonths||[]).slice().sort();
    const us=STATE.usUtil||[];
    const cnMonths=STATE.cnProcMonths||[];
    const cn=STATE.cnProc||[];
    const ud=months.map((m,i)=> us[i]!=null?us[i]:null);
    const cd=months.map(m=>{const idx=cnMonths.indexOf(m);return idx>=0?cn[idx]:null;});
    const hasCn=cd.some(v=>v!=null);
    box.innerHTML=canvasBox(id,c);
    const datasets=[{label:"美国炼厂开工率 (%)",data:ud,borderColor:col,borderWidth:2.5,fill:false,tension:.25,pointRadius:3,yAxisID:"y"}];
    if(hasCn){datasets.push({label:"中国原油加工量 (万吨/月)",data:cd,borderColor:"#0891b2",borderWidth:2,fill:false,tension:.25,pointRadius:3,yAxisID:"y1"});}
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:months,datasets},
      options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"index",intersect:false},
        plugins:{legend:{display:true,labels:{boxWidth:12,font:{size:10}}},
          tooltip:{callbacks:{label:cx=>cx.dataset.label+"："+(cx.parsed.y!=null?cx.parsed.y.toFixed(cx.dataset.yAxisID==="y"?1:0):"-")+(cx.dataset.yAxisID==="y"?" %":" 万吨")}}},
        scales:{x:{grid:{display:false},ticks:xTime(12,months)},
          y:{position:"left",grid:{color:"#eef2f7"},title:{display:true,text:"%"},suggestedMin:80,suggestedMax:100},
          y1:{position:"right",grid:{display:false},title:{display:hasCn,text:"万吨/月"},display:hasCn}}}});
    moveSource(box);
  },
  // 中国原油进口量（海关总署，万吨/月，当月值）—— 季节性：x=12 月，每年一条线，图例可逐线隐藏/显示
  cnCrudeImport: function(p){
    const {box,id,c}=p;
    const months=(STATE.cnImportMonths||[]).slice().sort();
    const vals=STATE.cnImport||[];
    const byYear={};
    months.forEach((m,i)=>{
      const mm=(m&&m.length>=7)?m.slice(0,7):"";
      if(!/^\d{4}-\d{2}$/.test(mm)) return;
      const y=mm.slice(0,4), mo=parseInt(mm.slice(5,7),10)-1;
      if(mo<0||mo>11) return;
      if(!byYear[y]) byYear[y]={year:y,data:new Array(12).fill(null)};
      byYear[y].data[mo]= vals[i]!=null?vals[i]:null;
    });
    const years=Object.keys(byYear).sort();
    const labels=["01","02","03","04","05","06","07","08","09","10","11","12"];
    const palette=["#2563eb","#ea580c","#16a34a","#dc2626","#7c3aed","#0891b2"];
    const datasets=years.map((y,idx)=>({
      label:y+" 年",
      data:byYear[y].data,
      borderColor:palette[idx%palette.length],
      borderWidth:2.2, fill:false, tension:.25, pointRadius:3, spanGaps:true
    }));
    box.innerHTML=canvasBox(id,c);
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels,datasets},
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:true,position:"top",labels:{boxWidth:14,font:{size:11}}},
          tooltip:{callbacks:{label:cx=>{
            const v=cx.parsed.y;
            return cx.dataset.label+"："+(v!=null?v.toFixed(1):"-")+" 万吨";
          }}}},
        scales:{x:{grid:{display:false},ticks:{font:{size:10}}},
          y:{grid:{color:"#eef2f7"},title:{display:true,text:"万吨/月"},min:0}}}});
    moveSource(box);
  },
  // OPEC 有效剩余产能（EIA STEO COPS_OPEC_R05，月度；尾部 EIA 18 个月滚动预测用不同色 + 虚线区分）
// OPEC 有效剩余产能（EIA STEO COPS_OPEC_R05，月度）—— 柱状图，蓝色=实际值 / 橙色=EIA 预测段
  opecSpare: function(p){
    const {box,id,c,col,fillFn,xTicks}=p;
    const months=(STATE.opecSpareMonths||[]).slice().sort();
    // 按「月份键」取值，不按排序后数组的下标取：原数组若非升序，按位置对齐会把整条
    // 柱序打乱（此前只排序 months 却仍按 i 取 vals[i]，属潜在错位）。
    const monthMap={};
    const vals=STATE.opecSpare||[];
    for(let i=0;i<(STATE.opecSpareMonths||[]).length;i++){
      if(vals[i]!=null) monthMap[STATE.opecSpareMonths[i]]=vals[i];
    }
    const cdata=months.map(m=>(monthMap[m]!=null?monthMap[m]:null));
    // 右轴 Brent 月均价（月键缺失即为 null，折线自动断在该月）
    const price=months.map(m=>(STATE.brentMonthly&&STATE.brentMonthly[m]!=null)?STATE.brentMonthly[m]:null);
    // 预测段检测：EIA 对超出真实数据范围的部分返回固定常量（当前 2.35 Mb/d），表现为尾部一段连续相同值。
    // 检测「与末值相同且 >=2 个月的尾部段」作为预测区间，避免真实数据巧合末值重复（如 0）导致的误判。
    const FC_COLOR="#ea580c";
    let fcStart=months.length;
    if(months.length>=2 && cdata[months.length-1]!=null){
      const lastV=cdata[months.length-1];
      for(let i=months.length-1;i>=0;i--){ if(cdata[i]===lastV) fcStart=i; else break; }
      if(!(fcStart<=months.length-2 && fcStart>0)) fcStart=months.length;
    }
    box.innerHTML=canvasBox(id,c);
    // 柱状图（2026-10-06 由线+面积改来，参照 MacroMicro 风格）。理由：月度存量是离散量，
    // 逐月一根柱比连线更能读出单月变化；2026-03 起剩余产能实际降至 0（无柱），2027-04 起为 EIA 预测段。
    // 颜色：蓝 = EIA 实际值，橙 = EIA 预测段。
    const colors=cdata.map((v,i)=> i>=fcStart?"rgba(234,88,12,.55)":col+"cc");
    // 价格线配色刻意避开柱子的蓝（左轴）与预测段的橙（别把两种橙色语义搅在一起）：
    // 紫 #7c3aed = Brent 月均价，灰度下也能靠实线（且无面积填充）分辨。
    const PRICE="#7c3aed";
    charts[id]=new Chart($("cv_"+id),{type:"bar",data:{labels:months,datasets:[
      {label:"OPEC 剩余产能（左轴）",data:cdata,backgroundColor:colors,borderWidth:0,
       barPercentage:.92,categoryPercentage:.92,yAxisID:"y",order:1},
      // 双轴（2026-10-07 起）：紫折线 = Brent 月均价（右轴，美元/桶），用来对照
      // 「缓冲垫被吃掉 / 油价抬升」这两条同源曲线。绘制次序 order 柱 1、线 2（序号大的画在上）。
      {label:"Brent 月均价（右轴）",data:price,type:"line",yAxisID:"y1",order:2,
       borderColor:PRICE,borderWidth:1.8,tension:.25,pointRadius:0,spanGaps:true,
       endTagFmt:v=>v.toFixed(2),endTagColor:PRICE}]},
      options:{responsive:true,maintainAspectRatio:false,
        interaction:{mode:"index",intersect:false},
        plugins:{legend:{position:"top",labels:{boxWidth:12,font:{size:10}}},
          // 柱、线各一枚末值气泡：剩余产能末值与 Brent 末价同屏可读。
          // endTag 插件自带 placed[] 竖向避让，两枚气泡不会精确重叠。
          endTag:{on:true,n:2},
          tooltip:{callbacks:{label:cx=>{
            const v=cx.parsed.y; if(v==null)return null;
            if(cx.dataset.yAxisID==="y1") return "Brent 月均价："+v.toFixed(2)+" 美元/桶";
            return (cx.dataIndex>=fcStart?"预测 · ":"")+v.toFixed(2)+" 百万桶/日";}}}},
        scales:{x:{grid:{display:false},ticks:xTicks(12,months)},
          y:{grid:{color:"#eef2f7"},title:{display:true,text:"百万桶/日"},min:0},
          // 右轴：与 linepct 同画法——只留刻度数字，网格线不插进绘图区
          y1:{position:"right",beginAtZero:false,
              title:{display:true,text:"美元/桶"},
              grid:{display:false,drawTicks:false,drawBorder:false},
              // ⚠️ 这里必须 6 个右括号收到底：font / ticks / y1 / scales / options / 图表配置对象。
              //    少一个（写成 5 个）整段页面脚本会 Unexpected token ')'），幻灯片全白（2026-10-07 踩）。
              ticks:{font:{size:10}}}}}});
    moveSource(box);
  },
  // 通用 line：eia.* 用原生周轴，其余用窗口日轴
  // 折线 + 自身周期变动柱（双轴）。左轴=库存水平（百万桶），右轴=逐周增减（百万桶）。
  //   库欣、全美商业原油库存两张图共用（2026-10-07 起全美商业同款）。
  //   变动量 = 折线同一数组逐周差分（首点无前值 → null）。
  //   ⚠️ 柱与线必须取**同一份** ea.data（eiaAxis 返回的窗口化周度数组），不能一边取 eiaWeekly、
  //      一边取日度前向填充数组：两者索引不对齐 → 实时拉取后柱子整体错一周，看起来像「数据对不上」。
  //   只显示一条序列的横向变动，不动 c.level 的面积开关；右轴照 rate 渲染器的画法：只把 0 画成网格线。
  linebar: function(p){
    const {box,id,c,col,dates,fillFn,xTicks}=p;
    const ea=eiaAxis(c.key, c);
    const plotDates=ea?ea.dates:dates;
    const d=ea?ea.data:sliceN(getSeries(c.key),RANGE);
    const chg=d.map((v,i)=>(i>0&&v!=null&&d[i-1]!=null)?Math.round((v-d[i-1])*100)/100:null);
    // 颜色沿用量价惯例「涨红跌绿」：+ 红 = 累库（库存增、偏空），− 绿 = 去库。
    // ⚠️ 与 rate 渲染器（正绿负红，用于标出倒挂异常）相反——那处红色是「异常」语义，不是涨跌幅语义。
    const barFill=(v)=>v==null?"transparent":(v>=0?"rgba(220,38,38,.62)":"rgba(22,163,74,.62)");
    // ⚠️ 线名不能写死「库欣」：两张图共用本渲染器，复用标题首词（"库欣原油库存"/"全美商业原油库存"）。
    const name=(c.title||"库存").split(" ")[0];
    box.innerHTML=canvasBox(id,c);
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:plotDates,datasets:[
      {label:name+"（左轴）",data:d,borderColor:col,borderWidth:2,fill:!c.level,backgroundColor:fillFn,
       tension:.25,pointRadius:0,spanGaps:true,yAxisID:"y",order:2,endTagFmt:v=>fmtNum(v,1)},
      {label:"周增减（右轴）",data:chg,type:"bar",yAxisID:"y1",order:1,
       backgroundColor:ctx=>barFill(ctx&&ctx.raw),borderRadius:2,
       barPercentage:.72,categoryPercentage:.86,
       endTagFmt:v=>(v>0?"+":"")+v.toFixed(1),endTagColor:"#64748b"}]},
      options:{responsive:true,maintainAspectRatio:false,
        interaction:{mode:"index",intersect:false},
        plugins:{legend:{position:"top",labels:{boxWidth:12,font:{size:10}}},baseNote:{on:!!c.level},
          // 两个数据集各画一枚末值气泡（库存水平走 n=1，周增减走数据集级 endTagFmt 带正负号）
          endTag:{on:true,n:1},
          tooltip:{callbacks:{label:function(t){
            const v=t.parsed.y; if(v==null) return null;
            if(t.dataset.yAxisID==="y1") return "周增减："+labelSign(v)+(v>=0?"（累库）":"（去库）")+" 百万桶";
            return name+"："+fmtNum(v,1)+" 百万桶";}}}},
        scales:{
          x:{grid:{display:false},ticks:xTicks(plotDates===dates?8:12, plotDates)},
          y:lineYAxis(c,d),
          y1:{position:"right",title:{display:true,text:"周增减 百万桶"},
              grid:{display:true,drawTicks:false,drawBorder:false,
                    color:ctx=>(ctx.tick&&ctx.tick.value===0)?"#b8bfc9":"transparent"},
              // 自动步长常会跳过 0，导致「累/去」分界这根线画不出来 → 强制补一个 0 刻度
              afterBuildTicks:ax=>{ if(!ax.ticks.some(t=>t.value===0)) ax.ticks.push({value:0});
                                    ax.ticks.sort((a,b)=>a.value-b.value); return ax.ticks; },
              ticks:{font:{size:10},callback:v=>labelSign(v)}}}}});
    moveSource(box);
  },
  // 折线 + 派生占比折线（双轴）。左轴=原始量（百万桶），右轴=该量在总量中的比重（%）。
  //   实例：美国 SPR 库存（左轴）+ SPR 占「含 SPR 原油总库存」比重（右轴，= spr ÷ gross）。
  //   ⚠️ 分子分母必须**同源同窗口**：spr 走 eiaAxis(c.key, c)、gross 走 eiaGrossWeekly(c)，
  //      两者都由 eiaI0(c) 决定起点，比值才不会整周错位。
  //   ⚠️ 右轴**先按折线画**（用户明确「暂时」是折线），日后要改柱只需把第二个数据集的
  //      type 换成 "bar" 并把 backgroundColor 换成静态色，其余不用动。
  linepct: function(p){
    const {box,id,c,col,dates,fillFn,xTicks}=p;
    const ea=eiaAxis(c.key, c);
    const plotDates=ea?ea.dates:dates;
    const d=ea?ea.data:sliceN(getSeries(c.key),RANGE);
    const gross=eiaGrossWeekly(c)||[];
    const share=d.map((v,i)=>(v!=null&&gross[i]!=null&&gross[i]>0)?Math.round(v/gross[i]*1000)/10:null);
    const PCT="#d97706";   // 琥珀：与左轴库存蓝明显区分，且与右轴「派生量」的画法一致
    box.innerHTML=canvasBox(id,c);
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:plotDates,datasets:[
      {label:"SPR 库存（左轴）",data:d,borderColor:col,borderWidth:2,fill:!c.level,backgroundColor:fillFn,
       tension:.25,pointRadius:0,spanGaps:true,yAxisID:"y",order:2,endTagFmt:v=>fmtNum(v,1)},
      {label:"SPR 占总库存比重（右轴）",data:share,borderColor:PCT,borderWidth:1.6,borderDash:[5,3],
       fill:false,tension:.25,pointRadius:0,spanGaps:true,yAxisID:"y1",order:1,
       endTagFmt:v=>v.toFixed(1)+"%",endTagColor:PCT}]},
      options:{responsive:true,maintainAspectRatio:false,
        interaction:{mode:"index",intersect:false},
        plugins:{legend:{position:"top",labels:{boxWidth:12,font:{size:10}}},baseNote:{on:!!c.level},
          endTag:{on:true,n:1},
          tooltip:{callbacks:{label:function(t){
            const v=t.parsed.y; if(v==null) return null;
            if(t.dataset.yAxisID==="y1") return "SPR 占原油总库存比重："+v.toFixed(1)+"%";
            return "SPR 库存："+fmtNum(v,1)+" 百万桶";}}}},
        scales:{
          x:{grid:{display:false},ticks:xTicks(plotDates===dates?8:12, plotDates)},
          y:lineYAxis(c,d),
          // 占比恒为正（40% 上下），不需要强制 0 刻度，也不把 0 画成网格线
          y1:{position:"right",title:{display:true,text:"占原油总库存 %"},
              grid:{display:false,drawTicks:false,drawBorder:false},
              ticks:{font:{size:10},callback:v=>v+"%"}}}}});
    moveSource(box);
  },
  __default__: function(p){
    const {box,id,c,col,dates,fillFn,xTicks}=p;
    // 其他突发维度：区间随 ALL/1y 切换（dates 已是相应窗口）；其余维度维持 RANGE=252
    const r = (p.key==="other") ? dates.length : RANGE;
    let plotDates, d;
    if(c.key && c.key.indexOf("eia.")===0){
      const ea=eiaAxis(c.key, c);
      plotDates=ea?ea.dates:dates; d=ea?ea.data:sliceN(getSeries(c.key),r);
    } else {
      plotDates=dates; d=sliceN(getSeries(c.key),r);
    }
    const yOpt=lineYAxis(c,d);
    box.innerHTML=canvasBox(id,c);
    // 所有时间轴统一走 fmtX：年月 → 24/01，年月日 → 24/01/05
    const xTickCfg=xTicks(plotDates===dates?8:12, plotDates);
    const vlines=makeEventVlines(c);
    charts[id]=new Chart($("cv_"+id),{type:"line",data:{labels:plotDates,datasets:[
      {label:c.title.split(" ")[0],data:d,borderColor:col,borderWidth:2,fill:!c.level,backgroundColor:fillFn,tension:.25,pointRadius:0}]},
      options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},baseNote:{on:!!c.level},
        endTag:{on:true,n:(c.key==="eia.prod"||c.key==="eia.gasSupplied")?2:1}},
        scales:{x:{grid:{display:false},ticks:xTickCfg},y:yOpt}},
      plugins: vlines?[vlines]:[]});
    moveSource(box);
  }
};

/* ---------- 空数据守卫 ----------
   2026-10-07 故障：SPR 图「首屏正常、点『拉取实时』后整张图空白」。
   根因是前端序列 id 表漏了 spr，实时拉取后 STATE.eia.spr 不存在，
   eiaAxis() 回退 null → __default__ 用空数组当数据集 → 画布什么都没画（静默空白）。
   这类失败之前只能靠肉眼发现、靠猜，现在统一兜底：
   渲染后若某个图**所有数据集的非空点数都是 0**，就销毁图表、换成明确的占位文案。
   ⚠️ 必须在 fn(p) 之后跑（Chart 建好才知道数据）；且必须 destroy 旧实例，
      否则 resize / 绘制插件还会往已经从 DOM 摘掉的 canvas 上画。 */
function guardEmpty(id, c){
  const ch=charts[id];
  if(!ch)return;
  let nn=0;
  ((ch.data&&ch.data.datasets)||[]).forEach(function(ds){
    ((ds&&ds.data)||[]).forEach(function(v){ if(v!=null && !isNaN(v)) nn++; });
  });
  if(nn>0)return;
  try{ ch.destroy(); }catch(e){}
  delete charts[id];
  const box=$("box_"+id);
  const key=(c&&c.key)||"";
  if(box) box.innerHTML="<div class='nodata'>本图暂无数据"+
    (key?("<span>序列 \u201C"+key+"\u201D 在当前数据源里取不到值</span>"):"")+
    "</div>";
  // 诊断按 key 分流：eia.* 才是「序列可能漏登记」的场景（2026-10-07 SPR 故障），
  // 其余（vol20 / 事件条等）大多只是窗口内确实没有事件/样本不足，别把人往 EIA 上带偏。
  const hint = key.indexOf("eia.")===0
    ? " 若发生在「拉取实时」之后：检查 src/fetch/supply/eia_weekly.py 的 EIA_SERIES 是否已包含该序列、"+
      "以及构建产物里的 EIA_SERIES 常量是否与之一致（跑 node tools/check_eia_series.js）。"
    : " 常见原因：当前窗口内没有事件 / 样本不足（如 vol20 需要 CONST.volWindow 个交易日）。";
  console.error("[dashboard] 图 "+id+" 数据为空（key="+(key||"-")+"），已渲染占位提示。"+hint);
}

/* 分组单图渲染入口：只负责准备上下文并查表，具体画法都在 SUPPLY_RENDERERS 里。 */
function renderSupplyChart(key, g, c, col, dates){
  const id=key+"_"+g.id+"_"+c.id;
  const box=$("box_"+id);
  if(!box)return;
  if(charts[id])charts[id].destroy();
  const p={
    box:box, id:id, c:c, col:col, dates:dates, key:key,
    // 面积填充：供给图通过 c.fillAlpha 开启轻量化纯色，未配置则回落默认垂直渐变
    fillFn:(ctx)=>vg(ctx,col,c.fillAlpha),
    // 传 lb（标签数组）即自动挂 fmtX 回调，统一走 x 轴时间格式
    xTicks:(n,lb)=>xTime(n,lb,c.xSlant)
  };
  const fn=SUPPLY_RENDERERS[c.key] || SUPPLY_RENDERERS[c.type] || SUPPLY_RENDERERS.__default__;
  fn(p);
  guardEmpty(id, c);   // 统一兜底：宁可显示「暂无数据」，也不要一张什么都没有的空白画布
}

function renderCorr(){
  const labels=STATE.corr.labels;
  const disp=(l)=>l==="广义美元指数（DTWEXBGS）"?"广义美元指数":l;  // 热力图单元格用短名，避免溢出
  const dates=windowDates();
  const get=(k)=>sliceN(STATE[k],RANGE);
  const series=[get("brent"),get("crack"),get("vol20"),get("dxy"),get("spread_bw")];
  const M=labels.map((_,i)=>labels.map((_,j)=>pearson(series[i],series[j])));
  let html="<table class='corr'><tr><th></th>"+labels.map(l=>`<th>${disp(l)}</th>`).join("")+"</tr>";
  labels.forEach((l,i)=>{html+=`<tr><td class='lbl'>${disp(l)}</td>`;labels.forEach((_,j)=>{const v=M[i][j];let bg="#fff",tx="#1f2933";if(v!=null){const t=Math.max(-1,Math.min(1,v));if(t>=0){bg=`rgba(220,38,38,${t*0.75})`;}else{bg=`rgba(37,99,235,${(-t)*0.75})`;}tx=t>0.5||t<-0.5?"#fff":"#1f2933";}
    html+=`<td style="background:${bg};color:${tx}">${v!=null?v.toFixed(2):'-'}</td>`;});html+="</tr>";});
  html+="</table>";
  $("corrHeat").innerHTML=html;
  // scatter brent vs dxy
  const bx=sliceN(STATE.brent,RANGE),dy=sliceN(STATE.dxy,RANGE);
  const pts=[];for(let i=0;i<bx.length;i++){if(bx[i]!=null&&dy[i]!=null)pts.push({x:dy[i],y:bx[i]});}
  if(charts.corrScatter)charts.corrScatter.destroy();
  charts.corrScatter=new Chart($("corrScatter"),{type:"scatter",data:{datasets:[{label:"日度",data:pts,backgroundColor:"rgba(15,118,110,.5)",pointRadius:3}]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:"nearest",intersect:true},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`广义美元指数 ${c.parsed.x.toFixed(1)} / Brent $${c.parsed.y.toFixed(1)}`}}},
      scales:{x:{title:{display:true,text:"广义美元指数"},grid:{color:"#eef2f7"}},y:{title:{display:true,text:"Brent $/bbl"},grid:{color:"#eef2f7"}}}}});
}

/* IMF 油价基准预测（WEO「全球假设」，逐期修正）—— outlook7。
   渲染**某一辑（edition，如 2025 / 2026）**的完整视图：x 轴 = 该辑的期次，
   每条线 = 该辑预测的一个目标年（当年 + 次年）。与 GDP 逐期修正图同构。
   卡片右上角的年份按钮在「2025 辑 / 2026 辑 …」之间切换，各辑独立成图，
   故同一目标年（如 2026）在 2025 辑为「次年」、2026 辑为「当年」也只会在各自页面出现，
   不会在一张图上撞线。参考线：① 已实油价（同口径三品种均价，灰虚线）② 看板实测 Brent 当年日均。
   ⚠️ WEO 给的是**假设**（期货曲线推导），不是供需平衡预测；Δ 只做精确读数。 */
function renderOutlookChart7(edKey, ed){
  const el=$("ec_outlook7");
  if(!el || !ed) return;
  const months=ed.months||[], price=ed.price||{}, actual=ed.actual||{};
  // 切换辑时复用同一实例：先 dispose 再 init，避免旧 series / 轴残留
  if(ecCharts.outlook7){ try{ ecCharts.outlook7.dispose(); }catch(e){} delete ecCharts.outlook7; }
  const years=Object.keys(price).map(Number).sort(function(a,b){return a-b;});
  const arrs=years.map(function(y){return price[String(y)]||[];});
  const vals=[].concat.apply([],arrs).filter(function(v){return v!=null;});
  const lines=[];
  // ① 本辑当年实际（同口径，灰虚线）—— 用于「WEO 逐期修订 vs 该年真实落点」。
  //    ⚠️ 按辑取当年（actual[edKey]），不再取「全局最新已实年份」——
  //      后者会让 2026 辑画出与该辑主题无关的 2025 实际。
  //    该年未走完 / 官方未披露全年实际时 actual 为空 → 不画这条线。
  let base=null, baseYear="";
  if(actual && actual[edKey]!=null){ base=actual[edKey]; baseYear=edKey; }
  if(base==null){
    Object.keys(actual||{}).forEach(function(y){
      const v=actual[y];
      if(v!=null && (base==null || Number(y)>Number(baseYear))){ base=v; baseYear=y; }
    });
  }
  if(base!=null){
    vals.push(base);
    lines.push({yAxis:base,
      label:{formatter:baseYear+" 实际 "+base.toFixed(2),position:"insideEndTop",fontSize:10,color:"#64748b"},
      lineStyle:{color:"#64748b",type:"dashed",width:1.5}});
  }
  if(!vals.length){ el.innerHTML="<div class='note'>IMF 油价期次数据缺失</div>"; return; }
  const lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
  const yMin=Math.floor((lo-6)/5)*5, yMax=Math.ceil((hi+6)/5)*5;
  // 配色：按目标年固定分配；2026 用红（焦点年）、2027 用蓝，其余紫/绿/琥珀依次
  const palette=["#dc2626","#2563eb","#7c3aed","#059669","#d97706"];
  const mkPt=function(){
    return {symbolSize:30,symbolOffset:[0,-2],
      label:{fontSize:9,color:"#fff",fontWeight:"600",
        formatter:function(p){return p.value!=null?Number(p.value).toFixed(1):"";}},
      data:[{type:"max",name:"最高"},{type:"min",name:"最低"}]};};
  const line=function(name,data,color){
    return {name:name,type:"line",data:data,smooth:true,symbol:"circle",symbolSize:6,
      connectNulls:false,
      itemStyle:{color:color},lineStyle:{width:2.5,color:color},
      emphasis:{focus:"series",lineStyle:{width:3.5}},
      endLabel:{show:true,distance:6,fontSize:10,fontWeight:600,color:color,
        formatter:function(pp){return pp.value!=null?Number(pp.value).toFixed(1):"";}},
      markPoint:mkPt()};};
  const series=years.map(function(y,i){
    const color=palette[i%palette.length];
    const s=line(y+" 油价假设", price[String(y)], color);
    if(i===0) s.markLine={silent:true,symbol:"none",data:lines};
    return s;
  });
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:48,right:34,top:46,bottom:52},
    legend:{data:years.map(function(y){return y+" 油价假设";}),top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:16,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",
      axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},
        label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      formatter:function(ps){
        if(!ps||!ps.length) return "";
        let s=String(ps[0].name);
        ps.forEach(function(q){
          if(q.value==null) return;
          const arr=arrs[q.seriesIndex]||[];
          const prev=(q.dataIndex>0&&arr[q.dataIndex-1]!=null)?arr[q.dataIndex-1]:null;
          const d=(prev==null)?"":("（较上期 "+((q.value-prev>0?"+":"")+(q.value-prev).toFixed(2))+"）");
          s+="<br/>"+q.marker+q.seriesName+"：$"+Number(q.value).toFixed(2)+" /桶 "+d;
        });
        return s;
      }},
    xAxis:{type:"category",data:months,boundaryGap:false,
      axisTick:{alignWithLabel:true},axisLine:{lineStyle:{color:"#e4e9f0"}},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:0,hideOverlap:true,
        formatter:function(v){return fmtX(v);}}},
    yAxis:{type:"value",min:yMin,max:yMax,name:"美元/桶",
      nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      splitLine:{lineStyle:{color:"#eef2f7"}},
      axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    series:series
  };
  ecCharts.outlook7=echarts.init(el);
  ecCharts.outlook7.setOption(opt);
}

/* EIA 油价基准预测（STEO 表 2，逐月修正）—— outlook8。
   与 outlook7（IMF）并列成「原油价格预测」组，故骨架完全同构，只改三处：
   ① 期次轴是**月度**（本地 10 期 PDF，2026-01 ~ 2026-10），比 IMF 的季度 4 期更密；
   ② 配色与线型跟 outlook7 的 **2026 辑对齐**：2026 红 #dc2626 / 2027 蓝 #2563eb，
      **两条都是实线**（2026-10-15 应需求改动；原为 EIA 身份色琥珀 #d97706 / 青 #0891b2，
      且 2027 是虚线，与 outlook7 同名的 2026/2027 线观感不一致）；
   ③ 参考线 = **当年（2026）实际**（与 outlook7 同一逻辑：按「当年」取，不再用「上年实际」
      作锚）。2026 年尚未走完 → 官方全年 Brent 实际未披露 → **不画线**；
      等 2026 实际出来后加进 `actual` 即自动出现。原「2025 实际 69.04」线已于 2026-10-15 移除。
   ⚠️ 2025Q1–2026Q2 在多数期次 PDF 里已是历史值，把它当预测读会高估先见之明；
   本图只画年度预测列（Y2026 / Y2027），天然规避了这个问题。 */
function renderOutlookChart8(months, p26, p27, actual){
  const el=$("ec_outlook8");
  if(!el) return;
  // 本图预测的目标年 = 2026（当年）+ 2027（次年），与下方 series 名 / legend 字面量一致。
  // 参考线按「当年」取实际（与 outlook7 同逻辑），故这里把「当年」定为首个目标年。
  const CUR_YEAR="2026";
  const vals=[].concat(p26,p27).filter(function(v){return v!=null;});
  const lines=[];
  // ① 当年（2026）实际值（EIA 自身表 2 年度列，Brent 现货口径，与预测线同口径）
  //    ⚠️ 2026-10-15 起与 outlook7 同一逻辑：**按「当年」取实际**，不再用「上年实际」作锚
  //    （原「2025 实际 69.04」线已按需求移除）。
  //    ⚠️ 这里**绝不能**回退到「取 actual 里最大年份」——那会把 2025 实际 69.04 又捞回来。
  //    2026 年尚未走完 → 官方全年实际未披露 → 不画线；等 2026 实际出来后加进 actual 即可。
  let base=null, baseYear="";
  if(actual && actual[CUR_YEAR]!=null){ base=actual[CUR_YEAR]; baseYear=CUR_YEAR; }
  if(base!=null){
    vals.push(base);
    lines.push({yAxis:base,
      label:{formatter:baseYear+" 实际 "+base.toFixed(2),position:"insideEndTop",fontSize:10,color:"#64748b"},
      lineStyle:{color:"#64748b",type:"dashed",width:1.5}});
  }
  if(!vals.length){ el.innerHTML="<div class='note'>EIA 油价期次数据缺失</div>"; return; }
  const lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
  const yMin=Math.floor((lo-6)/5)*5, yMax=Math.ceil((hi+6)/5)*5;
  const arrs=[p26,p27];
  const mkPt=function(){
    return {symbolSize:30,symbolOffset:[0,-2],
      label:{fontSize:9,color:"#fff",fontWeight:"600",
        formatter:function(p){return p.value!=null?Number(p.value).toFixed(1):"";}},
      data:[{type:"max",name:"最高"},{type:"min",name:"最低"}]};};
  const line=function(name,data,color,type){
    return {name:name,type:"line",data:data,smooth:true,symbol:"circle",symbolSize:6,
      itemStyle:{color:color},lineStyle:{width:2.5,color:color,type:type},
      emphasis:{focus:"series",lineStyle:{width:3.5}},
      endLabel:{show:true,distance:6,fontSize:10,fontWeight:600,color:color,
        formatter:function(pp){return pp.value!=null?Number(pp.value).toFixed(1):"";}},
      markPoint:mkPt()};};
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:48,right:34,top:46,bottom:52},
    legend:{data:["2026 油价预测","2027 油价预测"],top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:16,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",
      axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},
        label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      formatter:function(ps){
        if(!ps||!ps.length) return "";
        let s=String(ps[0].name);
        ps.forEach(function(q){
          if(q.value==null) return;
          const arr=arrs[q.seriesIndex]||[];
          const prev=(q.dataIndex>0&&arr[q.dataIndex-1]!=null)?arr[q.dataIndex-1]:null;
          const d=(prev==null)?"":("（较上期 "+((q.value-prev>0?"+":"")+(q.value-prev).toFixed(2))+"）");
          s+="<br/>"+q.marker+q.seriesName+"：$"+Number(q.value).toFixed(2)+" /桶 "+d;
        });
        return s;
      }},
    xAxis:{type:"category",data:months,boundaryGap:false,
      axisTick:{alignWithLabel:true},axisLine:{lineStyle:{color:"#e4e9f0"}},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:0,hideOverlap:true,
        formatter:function(v){return fmtX(v);}}},
    yAxis:{type:"value",min:yMin,max:yMax,name:"美元/桶",
      nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      splitLine:{lineStyle:{color:"#eef2f7"}},
      axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    series:[
      Object.assign(line("2026 油价预测",p26,"#dc2626","solid"),{
        markLine:{silent:true,symbol:"none",data:lines}}),
      line("2027 油价预测",p27,"#2563eb","solid")
    ]
  };
  ecCharts.outlook8=echarts.init(el);
  ecCharts.outlook8.setOption(opt);
}

/* ---------- 未来展望（IEA / OPEC / EIA / IMF 四家预测体系） ----------
   数据来自 data/dataset/{iea,opec,eia,imf}_forecast.json，每张图一个面板（outlook1 … outlook8）：
     outlook1   IEA  OMR   逐月需求增速修正        （ieaOmrMeta.omrSrc）
     outlook2   IEA《Oil 20XX》中期需求路径至 2030  （ieaOmrMeta.oilSrc）
     outlook3   OPEC MOMR  逐月需求增速修正        （opecForecastMeta.momrSrc）
     outlook4   OPEC《WOO》长期需求路径至 2050      （opecForecastMeta.wooSrc）
     outlook5   EIA  STEO  逐月需求增速修正        （eiaForecastMeta.steoSrc）
     outlook6   EIA《AEO》美国液体燃料消费至 2050   （eiaForecastMeta.aeoSrc）
     outlook7   IMF《WEO》油价基准假设逐期修正      （imfOilMeta.oilSrc）
     outlook8   EIA  STEO  表 2 油价基准逐月修正    （eiaSteoPriceMeta.steoSrc）
   前三家（IEA / OPEC / EIA）做的是**需求**预测；**油价**预测全球只有 IMF 与 EIA 两家，
   outlook7 + outlook8 并列成「原油价格预测」组（一行两图）。两家口径不同：IMF 是
   Brent/Dubai/WTI 三品种简单平均（期货曲线推导的「全球假设」，按季随 WEO 四期修订），
   EIA 是 Brent 现货单一品种（逐月随 STEO 修订），绝对值差 1~14 美元，只比修订路径。
   页尾「数据：取自 …」各条文案由上面四个 meta 对象统一提供，改文案只改 dataset json，
   不要写死在这里；月度图 2026-02 处的竖线由各 *WarOnset 键绘制，无需在文案里描述。
   八张图实例统一存 ecCharts 以复用 resize 监听。 */
function renderOutlook(){
  const el=$("p_outlook");
  if(!el) return;
  // 读数回落：STATE 可能被 computeDerived / loadLive 整体替换，IEA 为纯静态数据，
  // 缺失时回落 SNAPSHOT，避免任何替换路径下本页取空。
  const gv=(k,dflt)=>{
    if(STATE&&STATE[k]!=null&&(!Array.isArray(STATE[k])||STATE[k].length)) return STATE[k];
    if(typeof SNAPSHOT!=="undefined"&&SNAPSHOT[k]!=null&&(!Array.isArray(SNAPSHOT[k])||SNAPSHOT[k].length)) return SNAPSHOT[k];
    return dflt;
  };
  const m=gv("ieaOmrMonths",[]), d=gv("ieaOmr2026Demand",[]), d27=gv("ieaOmr2027Demand",[]);
  const y=gv("ieaOutlookYears",[]), o23=gv("ieaOutlook2023",[]), o24=gv("ieaOutlook2024",[]), o25=gv("ieaOutlook2025",[]);
  const war=gv("ieaOmrWarOnset",""), meta=gv("ieaOutlookMeta",{});
  // OPEC 侧（独立成图，不与 IEA 混线）
  const pm=gv("opecMomrMonths",[]), pd=gv("opecMomr2026Demand",[]), pd27=gv("opecMomr2027Demand",[]);
  const pw=gv("opecMomrWarOnset",""), wy=gv("opecWooYears",[]), wd=gv("opecWooDemand",[]);
  const w25=gv("opecWoo2025",[]), w24=gv("opecWoo2024",[]), w23=gv("opecWoo2023",[]);
  // EIA 侧（独立成块；STEO 为全球口径，AEO 为美国国内口径）
  const em=gv("eiaSteoMonths",[]), ed=gv("eiaSteo2026Demand",[]), ed27=gv("eiaSteo2027Demand",[]);
  const ew=gv("eiaSteoWarOnset",""), ay=gv("eiaAeoYears",[]), ah=gv("eiaAeoConsHigh",[]), al=gv("eiaAeoConsLow",[]);
  const ab=gv("eiaAeoConsBase",[]), ach=gv("eiaAeoCaseHigh",""), acb=gv("eiaAeoCaseBase",""), acl=gv("eiaAeoCaseLow","");
  const emeta=gv("eiaForecastMeta",{});
  const pmeta=gv("opecForecastMeta",{});
  // IMF 侧：WEO「全球假设」的油价基准值，按 WEO 辑（edition）分组；卡片右上角年份按钮切换
  const imEd=gv("imfOilEditions",[]), imByEd=gv("imfOilByEdition",{});
  const imActive = imEd.length ? imEd[imEd.length-1] : "";   // 默认展示最新一辑（2026）
  // EIA 侧油价：STEO 表 2 的 Brent 现货均价预测（月度频率，本地 10 期 PDF）
  const sm=gv("eiaSteoPriceMonths",[]), sp26=gv("eiaSteoBrent2026",[]), sp27=gv("eiaSteoBrent2027",[]);
  const spAct=gv("eiaSteoBrentActual2025",{}), smeta=gv("eiaSteoPriceMeta",{});
  if(!m.length && !y.length){ el.innerHTML="<div class='note'>IEA 预测数据缺失</div>"; return; }

  // 布局：与供给侧一致，每组一个 subhead 标题条（深蓝徽章+说明）+ grid2 一行两图（<920px 回落单列）。
  // 每组左列=月度滚动预测、右列=年度长期展望，三家横向对照。
  const head=function(t,d){return "<div class='subhead'><span class='subnum'>"+t+"</span>"+(d?"<span class='subdesc'>"+d+"</span>":"")+"</div>";};
  const card=function(t,id,src){return "<div class='card'><h3>"+t+"</h3><div class='box tall'><div id='ec_"+id+"' class='ecbox'></div></div><div class='src'>"+(src||"")+"</div></div>";};
  // IMF 油价卡专用：标题左侧、右上角放「年份（WEO 辑）切换」按钮组（id 固定 imf_yr_switch，
  // 由下方事件委托驱动）。各辑独立成图，点击只切该卡片内的视图。
  const imfCard=function(t,id,src,editions,active){
    const btns=editions.map(function(e){
      return "<button type='button' data-ed='"+e+"'"+(e===active?" class='on'":"")+">"+e+"</button>";
    }).join("");
    return "<div class='card imf-card'><div class='card-hd'><h3>"+t+"</h3>"+
           "<div class='yr-switch' id='imf_yr_switch'>"+btns+"</div></div>"+
           "<div class='box tall'><div id='ec_"+id+"' class='ecbox'></div></div>"+
           "<div class='src'>"+(src||"")+"</div></div>";
  };
  let html="";
  html+="<div class='subgroup'>"+head("IEA 预测体系","月度 OMR 滚动修正（当年与次年）＋《Oil 20XX》年度中期展望（至 2030）。")+
        "<div class='grid2'>"+card("IEA 全球石油需求增速预测（逐月 OMR 修正）","outlook1",meta.omrSrc)+
        card("IEA 《Oil 20XX》中期需求路径对比（至 2030）","outlook2",meta.oilSrc)+"</div></div>";
  let opecCards="";
  if(pm.length) opecCards+=card("OPEC 全球石油需求增速预测（逐月 MOMR 修正）","outlook3",pmeta.momrSrc);
  if(wy.length) opecCards+=card("OPEC《World Oil Outlook》长期需求路径对比（2025–2050）","outlook4",pmeta.wooSrc);
  if(opecCards) html+="<div class='subgroup' style='margin-top:14px'>"+head("OPEC 预测体系","月度 MOMR 滚动修正 ＋《World Oil Outlook》长期展望（至 2050），与 IEA 逐层对应。")+
        "<div class='grid2'>"+opecCards+"</div></div>";
  let eiaCards="";
  if(em.length) eiaCards+=card("EIA 全球石油需求增速预测（逐月 STEO 修正）","outlook5",emeta.steoSrc);
  if(ay.length) eiaCards+=card("EIA《Annual Energy Outlook 2026》美国液体燃料消费路径（至 2050）","outlook6",emeta.aeoSrc);
  if(eiaCards) html+="<div class='subgroup' style='margin-top:14px'>"+head("EIA 预测体系","月度 STEO 滚动修正（与 OMR/MOMR 对等）；长期仅 AEO 美国国内口径，全球性 IEO 已停滞。")+
        "<div class='grid2'>"+eiaCards+"</div></div>";
  // 原油价格预测组（2026-10-14 新增）：油价预测全球只有 IMF 与 EIA 两家，一行两图并列。
  // IMF = 季度 4 期（三品种均价假设），EIA = 月度 10 期（Brent 现货），期次轴密度不同，
  // 图的骨架一致（期次修正图）便于横向比修订路径；任一家缺数据时只渲染存在的那张。
  let priceCards="";
  if(imEd.length && imByEd[imActive]){
    const imSrc=(imByEd[imActive].meta||{}).oilSrc||"";
    priceCards+=imfCard("IMF 油价基准预测（逐期 WEO 修正）","outlook7",imSrc,imEd,imActive);
  }
  if(sm.length) priceCards+=card("EIA 油价基准预测（逐月 STEO 修正）","outlook8",smeta.steoSrc);
  if(priceCards) html+="<div class='subgroup' style='margin-top:14px'>"+
        head("原油价格预测","IMF 按季随 WEO 1/4/7/10 四期修订（Brent/Dubai/WTI 三品种均价假设），EIA 逐月随 STEO 修订（Brent 现货）。")+
        "<div class='grid2'>"+priceCards+"</div></div>";
  el.innerHTML=html;

  if(window.echarts){
    ["outlook1","outlook2","outlook3","outlook4","outlook5","outlook6","outlook7","outlook8"].forEach(function(k){ if(ecCharts[k]){ ecCharts[k].dispose(); delete ecCharts[k]; } });
    renderOutlookChart1(m, d, d27, war);
    renderOutlookChart2(y, o23, o24, o25);
    if(pm.length) renderOutlookChart3(pm, pd, pd27, pw);
    if(wy.length) renderOutlookChart4(wy, wd, w25, w24, w23);
    if(em.length) renderOutlookChart5(em, ed, ed27, ew);
    if(ay.length) renderOutlookChart6(ay, ah, ab, al, ach, acb, acl);
    if(imEd.length) renderOutlookChart7(imActive, imByEd[imActive]);
    if(sm.length) renderOutlookChart8(sm, sp26, sp27, spAct);
    // IMF 油价图：右上角年份按钮切换 WEO 辑（2025 / 2026 …），各辑独立成图
    if(imEd.length && imByEd[imActive]){
      const sw=$("imf_yr_switch");
      if(sw){
        sw.addEventListener("click", function(ev){
          const b=ev.target.closest("button"); if(!b) return;
          const ed=b.getAttribute("data-ed"); if(!ed || !imByEd[ed]) return;
          sw.querySelectorAll("button").forEach(function(x){ x.classList.remove("on"); });
          b.classList.add("on");
          renderOutlookChart7(ed, imByEd[ed]);
        });
      }
    }
  }
}

function renderOutlookChart1(months, d26, d27, warOnset){
  const el=$("ec_outlook1");
  if(!el) return;
  const mkPt=function(){return {symbolSize:30,symbolOffset:[0,-2],
    label:{fontSize:9,color:"#fff",fontWeight:"600",
      formatter:function(p){return p.value!=null?Number(p.value).toFixed(2):"";}},
    data:[{type:"max",name:"最高"},{type:"min",name:"最低"}]};};
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:48,right:18,top:42,bottom:58},
    legend:{data:["2026 需求增速预测","2027 需求增速预测"],top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:16,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      valueFormatter:function(v){return v==null?"-":Number(v).toFixed(2)+" mb/d";}},
    xAxis:{type:"category",data:months,boundaryGap:false,axisTick:{alignWithLabel:true},
      axisLine:{lineStyle:{color:"#e4e9f0"}},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:"auto",hideOverlap:true,formatter:function(v){return fmtX(v);}}},
    yAxis:{type:"value",name:"同比增量 mb/d",nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      splitLine:{lineStyle:{color:"#eef2f7"}},axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    dataZoom:[
      {type:"inside",xAxisIndex:0,zoomOnMouseWheel:true,moveOnMouseMove:true},
      {type:"slider",xAxisIndex:0,height:18,bottom:18,borderColor:"#e4e9f0",
        fillerColor:"rgba(13,148,136,.10)",handleStyle:{color:"#0d9488",borderColor:"#0d9488"},
        moveHandleStyle:{color:"#cbd5e1"},
        dataBackground:{lineStyle:{color:"#cbd5e1",width:1},areaStyle:{color:"#eef2f7"}},
        selectedDataBackground:{lineStyle:{color:"#0d9488",width:1},areaStyle:{color:"rgba(13,148,136,.14)"}},
        labelFormatter:function(v,vs){return fmtX(vs);},textStyle:{fontSize:10,color:"#94a3b8"}}
    ],
    series:[
      {name:"2026 需求增速预测",type:"line",data:d26,smooth:true,symbol:"circle",symbolSize:6,
        itemStyle:{color:"#dc2626"},lineStyle:{width:2.5,color:"#dc2626"},
        emphasis:{focus:"series",lineStyle:{width:3.5}},
        markPoint:mkPt(),
        markLine:{silent:true,symbol:"none",
          data:[{xAxis:warOnset,label:{formatter:"地缘冲突爆发",position:"insideEndTop",fontSize:10,color:"#64748b"},
                 lineStyle:{color:"#64748b",type:"dashed",width:1.5}}]}},
      {name:"2027 需求增速预测",type:"line",data:d27,smooth:true,symbol:"emptyCircle",symbolSize:6,
        itemStyle:{color:"#16a34a"},lineStyle:{width:2.5,color:"#16a34a",type:"dashed"},
        emphasis:{focus:"series",lineStyle:{width:3.5}}}
    ]
  };
  ecCharts.outlook1=echarts.init(el);
  ecCharts.outlook1.setOption(opt);
}

function renderOutlookChart2(years, o23, o24, o25){
  const el=$("ec_outlook2");
  if(!el) return;
  // 极值点：小圆点 + 顶部数值（不用 markPoint 默认图钉 —— symbolSize 30 的图钉
  // 会把 5 位数字（如 105.7）压得只剩末 4 位）
  const mkPt=function(){return {symbol:"circle",symbolSize:9,
    label:{position:"top",distance:8,fontSize:10,fontWeight:"600",color:"#334155",
      formatter:function(p){return p.value!=null?Number(p.value).toFixed(1):"";}},
    data:[{type:"max",name:"最高"},{type:"min",name:"最低"}]};};
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:48,right:18,top:52,bottom:40},
    legend:{data:["Oil 2023","Oil 2024","Oil 2025"],top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:14,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      valueFormatter:function(v){return v==null?"-":Number(v).toFixed(1)+" mb/d";}},
    xAxis:{type:"category",data:years.map(String),boundaryGap:false,
      axisTick:{alignWithLabel:true},axisLine:{lineStyle:{color:"#e4e9f0"}},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:0}},
    yAxis:{type:"value",name:"需求水平 mb/d",nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      scale:true,splitLine:{lineStyle:{color:"#eef2f7"}},axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    series:[
      {name:"Oil 2023",type:"line",data:o23,connectNulls:false,smooth:false,symbol:"circle",symbolSize:5,
        itemStyle:{color:"#2563eb"},lineStyle:{width:2.5,color:"#2563eb"},emphasis:{focus:"series",lineStyle:{width:3.5}},markPoint:mkPt()},
      {name:"Oil 2024",type:"line",data:o24,connectNulls:false,smooth:false,symbol:"rect",symbolSize:5,
        itemStyle:{color:"#d97706"},lineStyle:{width:2.5,color:"#d97706"},emphasis:{focus:"series",lineStyle:{width:3.5}},markPoint:mkPt()},
      {name:"Oil 2025",type:"line",data:o25,connectNulls:false,smooth:false,symbol:"triangle",symbolSize:6,
        itemStyle:{color:"#7c3aed"},lineStyle:{width:2.5,color:"#7c3aed"},emphasis:{focus:"series",lineStyle:{width:3.5}},markPoint:mkPt()}
    ]
  };
  ecCharts.outlook2=echarts.init(el);
  ecCharts.outlook2.setOption(opt);
}

/* OPEC 逐月 MOMR 需求增速预测修正（与 IEA 图1 同构，但独立成图、不混线） */
function renderOutlookChart3(months, d26, d27, warOnset){
  const el=$("ec_outlook3");
  if(!el) return;
  const mkPt=function(){return {symbolSize:30,symbolOffset:[0,-2],
    label:{fontSize:9,color:"#fff",fontWeight:"600",
      formatter:function(p){return p.value!=null?Number(p.value).toFixed(2):"";}},
    data:[{type:"max",name:"最高"},{type:"min",name:"最低"}]};};
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:48,right:18,top:42,bottom:58},
    legend:{data:["2026 需求增速预测","2027 需求增速预测"],top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:16,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      valueFormatter:function(v){return v==null?"-":Number(v).toFixed(2)+" mb/d";}},
    xAxis:{type:"category",data:months,boundaryGap:false,axisTick:{alignWithLabel:true},
      axisLine:{lineStyle:{color:"#e4e9f0"}},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:"auto",hideOverlap:true,formatter:function(v){return fmtX(v);}}},
    yAxis:{type:"value",name:"同比增量 mb/d",nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      splitLine:{lineStyle:{color:"#eef2f7"}},axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    dataZoom:[
      {type:"inside",xAxisIndex:0,zoomOnMouseWheel:true,moveOnMouseMove:true},
      {type:"slider",xAxisIndex:0,height:18,bottom:18,borderColor:"#e4e9f0",
        fillerColor:"rgba(13,148,136,.10)",handleStyle:{color:"#0d9488",borderColor:"#0d9488"},
        moveHandleStyle:{color:"#cbd5e1"},
        dataBackground:{lineStyle:{color:"#cbd5e1",width:1},areaStyle:{color:"#eef2f7"}},
        selectedDataBackground:{lineStyle:{color:"#0d9488",width:1},areaStyle:{color:"rgba(13,148,136,.14)"}},
        labelFormatter:function(v,vs){return fmtX(vs);},textStyle:{fontSize:10,color:"#94a3b8"}}
    ],
    series:[
      {name:"2026 需求增速预测",type:"line",data:d26,smooth:true,symbol:"circle",symbolSize:6,
        itemStyle:{color:"#0d9488"},lineStyle:{width:2.5,color:"#0d9488"},
        emphasis:{focus:"series",lineStyle:{width:3.5}},
        markPoint:mkPt(),
        markLine:{silent:true,symbol:"none",
          data:[{xAxis:warOnset,label:{formatter:"地缘冲突爆发",position:"insideEndTop",fontSize:10,color:"#64748b"},
                 lineStyle:{color:"#64748b",type:"dashed",width:1.5}}]}},
      {name:"2027 需求增速预测",type:"line",data:d27,smooth:true,symbol:"emptyCircle",symbolSize:6,
        itemStyle:{color:"#7c3aed"},lineStyle:{width:2.5,color:"#7c3aed",type:"dashed"},
        emphasis:{focus:"series",lineStyle:{width:3.5}}}
    ]
  };
  ecCharts.outlook3=echarts.init(el);
  ecCharts.outlook3.setOption(opt);
}

/* OPEC《World Oil Outlook》四版长期需求路径对比（2030–2050）
   各版基准年与展望终点不同，缺失节点为该版未公布 → 用 null，线在该处断开。 */
function renderOutlookChart4(years, w26, w25, w24, w23){
  const el=$("ec_outlook4");
  if(!el) return;
  // 四版起点年份不同（WOO 2023 首点为 2025，其余从 2030 起），故 x 轴用数值轴、
  // 数据为 [年份, 需求] 二维点，按实际年份落点；基准年（2022/2023/2024/2025）数据不绘入。
  const line=function(name,data,color,showLabel){
    return {name:name,type:"line",data:data,connectNulls:false,smooth:false,
      symbol:"circle",symbolSize:6,itemStyle:{color:color},lineStyle:{width:2.5,color:color},
      emphasis:{focus:"series",lineStyle:{width:3.5}},
      // 4 条线全开数值标签会互相压叠，只给最新版（WOO 2026）标数值，其余走 tooltip
      label:showLabel?{show:true,position:"top",fontSize:10,color:"#334155",fontWeight:"600",
        formatter:function(p){return p.value&&p.value[1]!=null?Number(p.value[1]).toFixed(1):"";}}:{show:false}};
  };
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:52,right:28,top:42,bottom:40},
    // 图例按「2023 → 2026」递增排列（WOO 2023 最左、2026 最右）；series 顺序未动，
    // 故 tooltip 行顺序仍是 2026 在上、绘制层级也仍是旧版压新版。要一起反就同步 series 数组。
    legend:{data:["WOO 2023","WOO 2024","WOO 2025","WOO 2026"],top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:14,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},
        label:{backgroundColor:"#334155",fontSize:10,
          // 数值轴下 axisPointer.label 默认把 x 值按数字格式化（2040 → “2,040.00”），这里改回年份
          formatter:function(p){var v=p&&p.value!=null?p.value:p;return String(Math.round(Number(v)));}}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      // 注意：x 轴为数值轴、数据为 [x,y] 二维点时 valueFormatter 拿到的是标量 x，
      // 取 v[1] 会得 undefined → 显示 NaN。故改走自定义 formatter，直接读 param.value[1]。
      formatter:function(ps){
        if(!ps||!ps.length) return "";
        var rows=[];
        ps.forEach(function(p){
          var v=p&&p.value, val=(v&&v[1]!=null)?Number(v[1]).toFixed(1):"-";
          var dot=(p&&p.color)?("background:"+p.color):"background:#94a3b8";
          rows.push('<span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;'+dot+'"></span>'+
                    (p?p.seriesName:"")+'　<strong style="font-variant-numeric:tabular-nums">'+val+'</strong> mb/d');
        });
        return rows.join("<br/>");
      }},
    // min 取 2025：无论 ECharts 从 min 还是从 5 的倍数对齐出刻度，落点都是 5 的倍数，
    // formatter 过滤后轴上只显示 2025–2050 的整五年份，不会出现错位标签。
    xAxis:{type:"value",min:2025,max:2051,interval:5,
      axisLine:{lineStyle:{color:"#e4e9f0"}},axisTick:{show:false},splitLine:{show:false},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:0,
        formatter:function(v){return (Number(v)%5===0&&Number(v)>=2025&&Number(v)<=2050)?String(Math.round(v)):"";}}},
    yAxis:{type:"value",name:"需求水平 mb/d",nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      scale:true,splitLine:{lineStyle:{color:"#eef2f7"}},axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    series:[
      line("WOO 2026",w26,"#0d9488",true),
      line("WOO 2025",w25,"#2563eb",false),
      line("WOO 2024",w24,"#d97706",false),
      line("WOO 2023",w23,"#7c3aed",false)
    ]
  };
  ecCharts.outlook4=echarts.init(el);
  ecCharts.outlook4.setOption(opt);
}

/* EIA 逐月 STEO 全球需求增速预测修正（与 IEA 图1、OPEC 图3 同构，独立成图） */
function renderOutlookChart5(months, d26, d27, warOnset){
  const el=$("ec_outlook5");
  if(!el) return;
  const mkPt=function(){return {symbolSize:30,symbolOffset:[0,-2],
    label:{fontSize:9,color:"#fff",fontWeight:"600",
      formatter:function(p){return p.value!=null?Number(p.value).toFixed(2):"";}},
    data:[{type:"max",name:"最高"},{type:"min",name:"最低"}]};};
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:48,right:18,top:42,bottom:58},
    legend:{data:["2026 需求增速预测","2027 需求增速预测"],top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:16,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      valueFormatter:function(v){return v==null?"-":Number(v).toFixed(2)+" mb/d";}},
    xAxis:{type:"category",data:months,boundaryGap:false,axisTick:{alignWithLabel:true},
      axisLine:{lineStyle:{color:"#e4e9f0"}},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:"auto",hideOverlap:true,formatter:function(v){return fmtX(v);}}},
    yAxis:{type:"value",name:"同比增量 mb/d",nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      splitLine:{lineStyle:{color:"#eef2f7"}},axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    dataZoom:[
      {type:"inside",xAxisIndex:0,zoomOnMouseWheel:true,moveOnMouseMove:true},
      {type:"slider",xAxisIndex:0,height:18,bottom:18,borderColor:"#e4e9f0",
        fillerColor:"rgba(217,119,6,.10)",handleStyle:{color:"#d97706",borderColor:"#d97706"},
        moveHandleStyle:{color:"#cbd5e1"},
        dataBackground:{lineStyle:{color:"#cbd5e1",width:1},areaStyle:{color:"#eef2f7"}},
        selectedDataBackground:{lineStyle:{color:"#d97706",width:1},areaStyle:{color:"rgba(217,119,6,.14)"}},
        labelFormatter:function(v,vs){return fmtX(vs);},textStyle:{fontSize:10,color:"#94a3b8"}}
    ],
    series:[
      {name:"2026 需求增速预测",type:"line",data:d26,smooth:true,symbol:"circle",symbolSize:6,
        itemStyle:{color:"#d97706"},lineStyle:{width:2.5,color:"#d97706"},
        emphasis:{focus:"series",lineStyle:{width:3.5}},
        markPoint:mkPt(),
        markLine:{silent:true,symbol:"none",
          data:[{xAxis:warOnset,label:{formatter:"地缘冲突爆发",position:"insideEndTop",fontSize:10,color:"#64748b"},
                 lineStyle:{color:"#64748b",type:"dashed",width:1.5}}]}},
      {name:"2027 需求增速预测",type:"line",data:d27,smooth:true,symbol:"emptyCircle",symbolSize:6,
        itemStyle:{color:"#0891b2"},lineStyle:{width:2.5,color:"#0891b2",type:"dashed"},
        emphasis:{focus:"series",lineStyle:{width:3.5}}}
    ]
  };
  ecCharts.outlook5=echarts.init(el);
  ecCharts.outlook5.setOption(opt);
}

/* EIA《AEO 2026》美国液体燃料消费长期路径（11 情景扇面 + 基准线三条）
   口径：淡带 = 11 个情景里 2050 最高 / 最低的两条（Combination / Low Economic Growth，
   都是官方表内真实情景，非插值）；加一条加粗的 EIA 基准 Counterfactual Baseline。
   扇面用手绘 polygon 而非 stack——stack 会把上下界相加把 y 轴顶到 2 倍高。 */
const BAND_NAME="__aeo_band__";   // 扇面辅助系列：不进图例、不进 tooltip
function renderOutlookChart6(years, high, low, base, caseHi, caseBase, caseLo){
  // 图例/序列名直接用情景原名（eiaAeoCaseHigh/eiaAeoCaseBase/eiaAeoCaseLow 注入），
  // 不再硬编码「上界 · /基准 ·/下界 ·」前缀，也彻底丢掉 −11%/−23% 的推导口径
  const nmHi=caseHi||"上界", nmB=caseBase||"基准", nmLo=caseLo||"下界";
  const C_HI="#d97706", C_Base="#475569", C_LO="#0891b2", C_Band="#94a3b8";
  const el=$("ec_outlook6");
  if(!el) return;
  const line=function(name,data,color,w){
    return {name:name,type:"line",data:data,connectNulls:false,smooth:false,
      symbol:"circle",symbolSize:6,itemStyle:{color:color},lineStyle:{width:w||2.5,color:color},
      emphasis:{focus:"series",lineStyle:{width:(w||2.5)+1}},
      label:{show:true,position:"top",fontSize:10,color:"#334155",fontWeight:"600",
        formatter:function(p){return p.value!=null?Number(p.value).toFixed(1):"";}}};
  };
  // 扇面：custom series 手绘「上界→下界」闭合多边形，data = [x序号, 上界, 下界]
  const band={name:BAND_NAME,type:"custom",silent:true,clip:true,z:1,
    dimensions:["x","hi","lo"],
    renderItem:function(p,api){
      const pts=[];
      for(let i=0;i<years.length;i++) pts.push(api.coord([i,high[i]]));
      for(let i=years.length-1;i>=0;i--) pts.push(api.coord([i,low[i]]));
      return {type:"polygon",shape:{points:pts},style:{fill:C_Band,opacity:0.12}};
    },
    data:years.map(function(_,i){return [i,high[i],low[i]];})};
  const opt={
    animation:true,animationDuration:720,animationEasing:"cubicOut",
    backgroundColor:"transparent",
    grid:{left:48,right:24,top:42,bottom:40},
    legend:{data:[nmHi,nmB,nmLo],top:6,left:"center",
      itemWidth:18,itemHeight:9,itemGap:14,textStyle:{fontSize:11,color:"#334155"}},
    tooltip:{trigger:"axis",axisPointer:{type:"cross",crossStyle:{color:"#94a3b8",width:1},label:{backgroundColor:"#334155",fontSize:10}},
      backgroundColor:"rgba(15,23,42,.92)",borderWidth:0,borderRadius:8,padding:[8,12],
      textStyle:{color:"#f8fafc",fontSize:11.5},
      formatter:function(ps){
        const rows=(ps||[]).filter(function(x){return x.seriesName!==BAND_NAME;});
        if(!rows.length) return "";
        let s="<div style='font-weight:600;margin-bottom:4px'>"+rows[0].axisValue+"</div>";
        rows.forEach(function(x){
          s+="<div>"+x.marker+x.seriesName+"：<b>"+(x.value==null?"-":Number(x.value).toFixed(2))+"</b> mb/d</div>";
        });
        return s;
      }},
    xAxis:{type:"category",data:years.map(String),boundaryGap:false,
      axisTick:{alignWithLabel:true},axisLine:{lineStyle:{color:"#e4e9f0"}},
      axisLabel:{fontSize:10,color:"#94a3b8",interval:0}},
    yAxis:{type:"value",name:"美国消费 mb/d",nameTextStyle:{fontSize:10,color:"#94a3b8",align:"left"},
      scale:true,splitLine:{lineStyle:{color:"#eef2f7"}},axisLabel:{fontSize:10,color:"#94a3b8"},
      axisLine:{show:false},axisTick:{show:false}},
    series:[
      band,
      line(nmHi,high,C_HI),
      line(nmB,base,C_Base,3.2),
      line(nmLo,low,C_LO)
    ]
  };
  ecCharts.outlook6=echarts.init(el);
  ecCharts.outlook6.setOption(opt);
}

/* ---------- master render (lazy: only build active tab at init) ---------- */
function renderTop(){
  renderKPIs();renderGauge();renderRiskBar();renderAlerts();renderNews();
}
function renderTab(key){
  if(DIMS[key]){ dimKPIs(key); renderDimCharts(key); }
  else if(key==="corr"){ renderCorr(); }
  else if(key==="outlook"){ renderOutlook(); }
  // 卡片徽章在 buildPanels 时已建好 DOM，但值随数据刷新变化 → 每次渲染后重填
  fillStats();
}
function renderAll(){
  renderTop();
  renderTab(currentTab);   // 懒渲染：初始化只构建当前激活维度，其余切到时再渲染
}

/* 首屏三卡等高：高度以「整体风险概览」(.gaugewrap) 的自然高度为准，
   Crude Oil News (.newscard) 与 异常预警 (.alertscard) 跟随该高度并**内部滚动**
   （两卡已是 flex 列 + 列表 flex:1，这里只负责把卡高钉到 gauge 卡高度）。
   仅桌面三列布局生效；窄屏（单列）恢复各自自然高度。 */
function syncRiskHeights(){
  var wrap=document.querySelector(".risk");
  if(!wrap) return;
  var g=wrap.querySelector(".gaugewrap");
  var n=wrap.querySelector(".newscard");
  var a=wrap.querySelector(".alertscard");
  if(!g||!n||!a) return;
  var cols=(getComputedStyle(wrap).gridTemplateColumns||"").trim().split(/\s+/);
  if(cols.length<3){ n.style.height=""; a.style.height=""; return; }  // 单列：放开
  var gh=g.offsetHeight;          // gauge 卡 align-self:start → 即其真实所需高度
  if(!gh) return;
  n.style.height=gh+"px";
  a.style.height=gh+"px";
}

/* ---------- interaction ---------- */
function setRange(n){RANGE=n;renderAll();}
function switchTab(key,el){
  currentTab=key;
  document.querySelectorAll("#tabs button").forEach(b=>b.classList.remove("on"));
  if(el){el.classList.add("on");}
  else{const tb=document.querySelector('#tabs button[data-d="'+key+'"]');if(tb)tb.classList.add("on");}
  document.querySelectorAll(".panel").forEach(p=>p.classList.remove("on"));
  $("p_"+key).classList.add("on");
  renderTab(key);   // 切到该维度/视图时再构建图表，避免一次性渲染全部面板拖慢加载
}

/* ---------- live fetch ---------- */
async function loadLive(){
  const key=(API_KEYS.fred||"").trim();
  if(!key){$("status").textContent="未配置 FRED API Key（src/config.py 或环境变量 FRED_KEY）";return;}
  if(window.location.protocol==="file:"){$("status").textContent="实时拉取需本地服务：运行 python -m src.serve 后访问 http://localhost:8000/";return;}
  $("status").textContent="拉取实时数据中…";
  /* 2026-10-22 故障隔离（此前 FRED 一挂就 throw，价格与 EIA 周度根本没机会执行）：
     三个源各自独立 try/catch —— FRED 宏观 / 价格 / EIA 周度。
     任一源失败只让它自己取不到数据（记入 failed），后续源照常拉取、照常渲染，
     状态栏标注缺失项。仅当「日期轴完全建不出来」（油价全无）才算整次失败。 */
  const failed=[];
  const noteFail=(s)=>{if(failed.indexOf(s)<0)failed.push(s);};
  const stale=[];
  const noteStale=(s)=>{if(stale.indexOf(s)<0)stale.push(s);};
  // 2026-10-08：价格（Brent/WTI）改走 **EIA 日度**。FRED 的 DCOILBRENTEU/DCOILWTICO
  // 是 EIA 这两条的转载（同值），但 FRED 每周才批量补更一次 —— 价格若仍走 FRED，
  // 「拉取实时」会拿回比快照更旧的数据。FRED 这里只留宏观与汽油价。
  const ids={dxy:"DTWEXBGS",dff:"DFF",dgs10:"DGS10",gas:"GASREGW"};
  // ---- 源 1：FRED 宏观与汽油价（失败 → 仅该源缺失，继续） ----
  let map={};
  try{
    const fr=await fetch(`/api/fred?key=${encodeURIComponent(key)}&ids=${Object.values(ids).join(",")}&start=__START_DATE__`);
    const fj=await fr.json();
    if(!fr.ok||fj.error)throw new Error(fj.error||("FRED代理错误 "+fr.status));
    map=fj.map||{};
  }catch(e){
    console.warn("[dashboard] FRED 宏观拉取失败，该组序列回落快照：",e);
    // 快照回落（与 computeDerived 里 EIA 周度的「底稿」同思路）：
    // crack = 汽油零售价×42 − WTI，而汽油零售价只走 FRED（GASREGW）。若这里把 map 留空，
    // 拉取「成功」后 gas 全 null → crack 全 null → guardEmpty 判「本图暂无数据」
    // （2026-10-22 FRED 维护期实测，用户截图）。按日期把 SNAPSHOT 宏观序列填回 map，
    // 派生链（crack / z 分数 / 相关矩阵）照常工作；状态栏以「=快照」标注非实时。
    const S=(typeof SNAPSHOT!=="undefined"&&SNAPSHOT)||{};
    const sd=S.dates||[];
    for(let i=0;i<sd.length;i++){
      for(const k in ids){
        const v=S[k]?S[k][i]:null;
        if(v!=null){ (map[sd[i]]=map[sd[i]]||{})[ids[k]]=v; }
      }
    }
    noteStale("FRED宏观");
  }
  // ---- 源 2：价格（EIA 日度，内部失败回落 FRED；两者都空 → 仅该源缺失，继续） ----
  const eiakey=(API_KEYS.eia||"").trim();
  let pm={__src:""};
  try{
    pm=await fetchPrices(eiakey,key);
  }catch(e){
    console.warn("[dashboard] 价格拉取失败（仅该源缺失）：",e);
    noteFail("油价");
  }
  if(!Object.keys(pm.brent||{}).length)noteFail("油价");

  // 日期轴 = FRED 并集 ∪ EIA 日度价格日期。
  // ⚠️ 必须按 START_DATE 过滤：EIA 序列从 2006 年起，不过滤会把日轴拉长 20 年
  //    （python 侧 prices._fetch_eia_daily 有同样的过滤，两边要一起保留）。
  const dset=new Set();
  for(const d in map) if(d>="__START_DATE__") dset.add(d);
  for(const k of ["brent","wti"]) for(const d in (pm[k]||{})) if(d>="__START_DATE__") dset.add(d);
  let dates=Array.from(dset).sort();
  // 日期轴是各序列的并集，末尾常有 1~2 天只有个别序列（如 DFF / OVX）已发布、
  // 而 Brent / WTI 尚未出数。在这种"补尾日"上算出的分数是残缺的
  // （缺 Brent/WTI → BW 价差分项归 0 → I_geo 凭空少 1 分）。
  // 与快照口径保持一致：裁掉尾部 Brent 仍为空的日期，"截至"即最后一个有真实行情的日子。
  while(dates.length && !(pm.brent&&pm.brent[dates[dates.length-1]]!=null)) dates.pop();
  // 只有「日期轴建不出来」才是整次失败：没有油价就没有行情轴，无法派生任何分数。
  // 有别于单源缺失 —— 此时其余源已照常取到，故在状态栏点名，而不是整页报错。
  if(!dates.length){
    console.error("[dashboard] 无法构建日期轴：油价为空",failed);
    $("status").textContent="拉取失败：未取到油价，无法构建日期轴"
      +(failed.length?"（失败源："+failed.join("/")+"）":"");
    return;
  }
  try{
    // 与 Python src/common/series.py::align 同口径：前向填充（轴首端未知区间保留 null）。
    // ⚠️ 不做填充会让周度序列（GASREGW 每周一更新）在日轴上约 80% 为空，
    //    进而使 crack 在 252 日窗口内的有效样本 < SCORE_MIN_PERIODS(60)，
    //    z-score 置 null → 供给/需求维度塌回中性 50，综合分严重失真。
    const ffill=a=>{let last=null;return a.map(v=>{if(v!=null)last=v;return last;});};
    const get=s=>ffill(dates.map(d=>map[d]&&map[d][ids[s]]!=null?map[d][ids[s]]:null));
    const getP=k=>ffill(dates.map(d=>pm[k]&&pm[k][d]!=null?pm[k][d]:null));
    const series={dates,brent:getP("brent"),wti:getP("wti"),dxy:get("dxy"),dff:get("dff"),dgs10:get("dgs10"),gas:get("gas")};
    // ---- 源 3：EIA 周度（库存/产量；失败 → 仅该源缺失，仍有价格与宏观可渲染） ----
    let eia=null;
    if(eiakey){
      try{eia=await fetchEIA(eiakey,dates);}
      catch(e2){console.warn("[dashboard] EIA 周度拉取失败（仅该源缺失）",e2);noteFail("EIA周度");}
    }
    // OPEC 月度原油产量（来自 MOMR PDF，静态嵌入快照），无需实时拉取；computeDerived 回落 SNAPSHOT 取值。
    STATE=computeDerived(series,eia);
    STATE.kpis.latest_date=dates[dates.length-1];STATE.kpis.n=dates.length;
    renderAll();
    $("status").textContent="实时数据（截至 "+dates[dates.length-1]+"）"
      +(eia?" · 含EIA":"")+(pm.__src?" · 油价"+pm.__src:"")
      +(stale.length?" · "+stale.join("/")+"=快照":"")
      +(failed.length?" · ⚠ 缺失："+failed.join("/"):"");
  }catch(e){
    // 三个拉取源已各自隔离，走到这里只会是派生/渲染异常，故不再笼统报「拉取失败」。
    console.error("[dashboard] 派生/渲染异常：",e);
    const msg=(e&&e.message)!=null?e.message:String(e);
    // 具体错误详情保留在 Console，避免状态栏被长错误撑爆
    const isRespErr=/json|response|unexpected\s+token|parse|syntax/i.test(msg);
    $("status").textContent="渲染失败："+(isRespErr?"响应解析异常":msg);
  }
}
/* 拉 Brent / WTI **日度**价：优先 EIA 日度，失败整体回落 FRED。
   与 python src/fetch/prices.py::fetch() 同策略：
   ⚠️ 任一条拿不到就**两条一起**回落 —— 两条同源，只回落一条会让 BW 价差
      变成「新 vs 旧」的假价差，回落后也要先清掉 EIA 的残留避免混源。
   ⚠️ /api/eia 返回 {series_id:{date:value}}，/api/fred 返回 {date:{series_id:value}}，
      两个代理的嵌套顺序相反，别照抄。
   返回对象里的 __src 仅用于状态栏标注，不参与序列计算。 */
async function fetchPrices(eiakey,fredkey){
  const out={__src:""};
  const ids=(EIA_PRICE_IDS&&EIA_PRICE_IDS.ids)||{};
  const fb=(EIA_PRICE_IDS&&EIA_PRICE_IDS.fallback)||{};
  const lastDate=o=>{const ks=Object.keys(o||{}).sort();return ks.length?ks[ks.length-1]:null;};
  // 两序列最小末日：EIA 的 WTI(RWTC) 发布常比 Brent 晚，只看 brent 会误判「已最新」
  const pairEdge=o=>{const a=lastDate(o&&o.brent),b=lastDate(o&&o.wti);return (a&&b)?(a<b?a:b):null;};
  // 取 FRED 回落价（brent/wti），供「较新者优先」对比；失败返回 null
  async function fredPrices(){
    if(!fredkey||!Object.keys(fb).length) return null;
    try{
      const r2=await fetch(`/api/fred?key=${encodeURIComponent(fredkey)}&ids=${Object.values(fb).join(",")}&start=__START_DATE__`);
      const j2=await r2.json();
      if(!r2.ok||j2.error) return null;
      const m=j2.map||{}; const o={};
      for(const k in fb){
        const sid=fb[k];const s={};
        for(const d in m){if(m[d]&&m[d][sid]!=null)s[d]=m[d][sid];}
        o[k]=s;
      }
      return o;
    }catch(e){console.warn("[dashboard] FRED 价格回落失败",e);return null;}
  }
  if(eiakey&&Object.keys(ids).length){
    try{
      // ⚠️ 2026-11-27：**不带 &length**。实测 EIA 的 length 参数返回陈旧分页且慢 10 倍
      //    （length=1500 约 22s、末日停在 11-17；无 length 2s 返回全量 5000 条、末日最新）。
      //    前端下方按 __START_DATE__ 过滤即可。
      const r=await fetch(`/api/eia?key=${encodeURIComponent(eiakey)}&ids=${Object.values(ids).join(",")}`);
      const j=await r.json();
      if(r.ok&&!j.error){
        const raw=j.map||{};
        for(const k in ids) out[k]=raw[ids[k]]||{};
        if(Object.keys(out.brent||{}).length&&Object.keys(out.wti||{}).length){
          // 「较新者优先」：EIA 可能返回陈旧副本；对比 FRED 的两序列最小末日，
          // FRED 更新则整体改用 FRED（同值同源，brent/wti 不混用）。
          const eiaEdge=pairEdge(out);
          const fp=await fredPrices();
          const fredEdge=fp?pairEdge(fp):null;
          if(fredEdge&&eiaEdge&&fredEdge>eiaEdge){
            for(const k in fb) delete out[k];
            for(const k in fb) out[k]=fp[k];
            out.__src="FRED回落";
            return out;
          }
          out.__src="EIA日度";return out;
        }
      }
    }catch(e){console.warn("[dashboard] EIA 价格拉取失败，回落 FRED",e);}
  }
  for(const k in fb) delete out[k];
  const fp=await fredPrices();
  if(fp){for(const k in fb) out[k]=fp[k];out.__src="FRED回落";return out;}
  return out;
}
async function fetchEIA(key,dates){
  // id 表来自构建注入的 EIA_SERIES（python 唯一事实源），与 python 抓取同口径：
  // 缺一个序列 = 实时拉取后该图空白，所以这里绝不允许再手抄一份。
  // ⚠️ 这张表**只放周度序列**：日度油价在 EIA_PRICE_IDS，混进来会把周轴撑成日轴。
  const ids=EIA_SERIES.ids;
  const r=await fetch(`/api/eia?key=${encodeURIComponent(key)}&ids=${Object.values(ids).join(",")}`);
  const j=await r.json();
  if(!r.ok||j.error)throw new Error(j.error||("EIA代理错误 "+r.status));
  const raw=j.map||{};
  // 原生周度坐标轴：EIA 库存/产量均为「周报、每周更新一次」。所有序列共享同一周度网格
  const seen=new Set(); const eiaDates=[];
  for(const k in ids){ const m=raw[ids[k]]||{}; for(const p of Object.keys(m)) if(!seen.has(p)){seen.add(p);eiaDates.push(p);} }
  eiaDates.sort();
  const map={}; const weekly={};
  for(const k in ids){
    const m=raw[ids[k]]||{};
    // 日度对齐（前向填充）：供 KPI / 预警使用
    const arr=[];let last=null;
    for(const d of dates){if(m[d]!=null)last=m[d];arr.push(last);}
    // util（%）不在 EIA_MILLION 里 = 不除 1000，与 python MILLION_UNITS 同口径
    map[k]=EIA_MILLION.has(k)?arr.map(v=>v==null?null:v/1000):arr;
    // 原生周度（仅真实点，不做前向填充）：供图表「周轴」使用，实时拉取后会自动延伸
    weekly[k]=eiaDates.map(d=> m[d]!=null ? (EIA_MILLION.has(k)? m[d]/1000 : m[d]) : null);
  }
  // 派生序列（python eia_weekly.build_axes 同口径，见 DERIVED）：
  //   含SPR原油总库存 = 全美商业原油(ex-SPR) + SPR。不单独 fetch，靠恒等推出，
  //   免得「同一事实抄两处」再出现静默失效（2026-10-07 那次的根因）。
  // 快照态由 python 算、实时态由这里算，两边都必须有，否则开页拉取后该键会消失。
  if(map.total&&map.spr)map.gross=map.total.map((v,i)=>(v==null||map.spr[i]==null)?null:v+map.spr[i]);
  if(weekly.total&&weekly.spr)weekly.gross=weekly.total.map((v,i)=>(v==null||weekly.spr[i]==null)?null:v+weekly.spr[i]);
  return {map, dates:eiaDates, weekly};
}
function resetSnapshot(){STATE=SNAPSHOT;renderAll();$("status").textContent="数据截至 "+STATE.kpis.latest_date;}

/* ---------- JS-side derive (mirror python) ---------- */
function computeDerived(S, EIA){
  const {dates}=S;const n=dates.length;
  // ⚠️ 2026-10-11「OPEC 原油产量」图换源（MOMR 表 5-7 12 国 → STEO 表 3d 11 国）后，
  //    旧键 opecMonths/opecMonthly/opecMonthlyCountries 已随 build_dataset 移除；
  //    图与徽章现走 steoMonths / steoOpecMonthly / steoOpecMembers（见下方 STEO 块）。
  // ⚠️ 2026-10-11「OPEC 原油产量」与「Non-OPEC DoC 原油产量」双图换源（MOMR → STEO 表 3d）：
  //    旧键 opecMonths/opecMonthly/opecMonthlyCountries 与 nonOpecDoCMonths/nonOpecDoCTotal/
  //    nonOpecDoCCountries 已随 build_dataset 移除；两图现走下方 steoOpecMembers / steoDocMembers
  //    （合计徽章走 steoOpecMonthly / steoDoCTotal + steoHistCut）。
  // 全球月度（EIA STEO 官方 API 的 COPR_* 序列，月度 2022-01~2027-12 共 72 个月；
  // 2026-10-10 起由**季度**改**月度**，2026-10-16 起由「手工下载 base tables xlsx」改为
  // **实时 API**（随 dataset 步骤刷新，旧季度键已整体移除）。
  const steoMonths=(S.steoMonths&&S.steoMonths.length)?S.steoMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.steoMonths)||[];
  const steoWorldMonthly=(S.steoWorldMonthly&&S.steoWorldMonthly.length)?S.steoWorldMonthly:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.steoWorldMonthly)||[];
  const steoOpecMonthly=(S.steoOpecMonthly&&S.steoOpecMonthly.length)?S.steoOpecMonthly:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.steoOpecMonthly)||[];
  const steoNonOpecMonthly=(S.steoNonOpecMonthly&&S.steoNonOpecMonthly.length)?S.steoNonOpecMonthly:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.steoNonOpecMonthly)||[];
  // 预测边界：forecastStart="2026-10" / forecastIndex=57（由 API 分国行最后非空月
  // = lastHistorical 2026-09 推导，不再依赖 xlsx 的 Dates 表）。
  // ⚠️ 标量 0 是合法值，判空必须用 !=null，不能写成 (S.x||...) —— 那会把 0 吞掉。
  const _sc=(k)=>(S[k]!=null)?S[k]:((typeof SNAPSHOT!=="undefined"&&SNAPSHOT[k]!=null)?SNAPSHOT[k]:null);
  const steoForecastStart=_sc("steoForecastStart"), steoForecastIndex=_sc("steoForecastIndex");
  const steoLastHistorical=_sc("steoLastHistorical");
  const steoWorldMeta=(S.steoWorldMeta&&S.steoWorldMeta.length)?S.steoWorldMeta:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.steoWorldMeta)||"";
  // OPEC 11 国分项（EIA STEO API 的 COPR_* 序列；2026-10-11 起供「OPEC 原油产量」图）。
  // {中文名: [72 值]}，与 steoMonths 同轴；分国行仅历史段有值（预测月为 null）。
  const steoOpecMembers=(S.steoOpecMembers&&Object.keys(S.steoOpecMembers).length)?S.steoOpecMembers:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.steoOpecMembers)||{};
  // OPEC+ 非 OPEC 参与国（DoC）10 国分项 + 合计（EIA STEO API 的 COPR_* 序列；
  // 2026-10-11 起供「Non-OPEC DoC 原油产量」图）。{中文名: [72 值]}，分国仅历史段有值；
  // 合计（COPR_OPECPLUS_OTHER）为纯数组 72 值，含预测段。
  const steoDocMembers=(S.steoDocMembers&&Object.keys(S.steoDocMembers).length)?S.steoDocMembers:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.steoDocMembers)||{};
  const steoDoCTotal=(S.steoDoCTotal&&S.steoDoCTotal.length)?S.steoDoCTotal:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.steoDoCTotal)||[];
  // OPEC 有效剩余产能（EIA STEO COPS_OPEC_R05，月度；静态，失败回落快照）
  const opecSpareMonths=(S.opecSpareMonths&&S.opecSpareMonths.length)?S.opecSpareMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.opecSpareMonths)||[];
  const opecSpare=(S.opecSpare&&S.opecSpare.length)?S.opecSpare:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.opecSpare)||[];
  // Brent 月均价（{YYYY-MM: v}，2015 起）—— 叠加在剩余产能图上做双轴对照。
  // ⚠️ 对象型静态键同样要「GROUPS + computeDerived」双登记：只写 dataio.GROUPS 时，
  //    开页自动拉取后 STATE 被 computeDerived 整体替换，右轴价格线会整条消失。
  const brentMonthly=(S.brentMonthly&&Object.keys(S.brentMonthly).length)?S.brentMonthly:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.brentMonthly)||{};
  // 全球钻井平台数（Baker Hughes World Rig Count，静态；优先 series，失败回落快照）
  const rigMonths=(S.rigMonths&&S.rigMonths.length)?S.rigMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.rigMonths)||[];
  const rigWorld=(S.rigWorld&&S.rigWorld.length)?S.rigWorld:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.rigWorld)||[];
  // OECD 商业原油库存（OPEC MOMR Table 9-1 转引 IEA，静态；优先 series，失败回落快照）
  const oecdMonths=(S.oecdMonths&&S.oecdMonths.length)?S.oecdMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.oecdMonths)||[];
  const oecdCrude=(S.oecdCrude&&S.oecdCrude.length)?S.oecdCrude:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.oecdCrude)||[];
  // 成品油/石化产品库存（MOMR 表 9-1 的 Products 行）。⚠️ 2026-10-06 修：本键此前只登记在
  // dataio.GROUPS，漏了 computeDerived —— 首屏 STATE=SNAPSHOT 能取到，但开页自动拉取
  // （setTimeout loadLive）后 STATE 被 computeDerived 整体替换，成品油折线就消失了。
  // 静态数据必须「GROUPS + computeDerived」双登记，缺一即在此类刷新后丢键。
  const oecdProducts=(S.oecdProducts&&S.oecdProducts.length)?S.oecdProducts:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.oecdProducts)||[];
  const oecdTotal=(S.oecdTotal&&S.oecdTotal.length)?S.oecdTotal:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.oecdTotal)||[];
  // 美国战略石油储备 SPR（EIA 周度石油周报 API PET.WCSSTUS1.W，月末口径；回落快照）
  const usSprMonths=(S.usSprMonths&&S.usSprMonths.length)?S.usSprMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.usSprMonths)||[];
  const usSpr=(S.usSpr&&S.usSpr.length)?S.usSpr:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.usSpr)||[];
  const usUtilMonths=(S.usUtilMonths&&S.usUtilMonths.length)?S.usUtilMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.usUtilMonths)||[];
  const usUtil=(S.usUtil&&S.usUtil.length)?S.usUtil:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.usUtil)||[];
  const cnProcMonths=(S.cnProcMonths&&S.cnProcMonths.length)?S.cnProcMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.cnProcMonths)||[];
  const cnProc=(S.cnProc&&S.cnProc.length)?S.cnProc:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.cnProc)||[];
  const cnImportMonths=(S.cnImportMonths&&S.cnImportMonths.length)?S.cnImportMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.cnImportMonths)||[];
  const cnImport=(S.cnImport&&S.cnImport.length)?S.cnImport:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.cnImport)||[];
  // 制造业 PMI 中/美/欧（月度，静态；回落快照）
  const pmiMonths=(S.pmiMonths&&S.pmiMonths.length)?S.pmiMonths:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.pmiMonths)||[];
  const pmiUS=(S.pmiUS&&S.pmiUS.length)?S.pmiUS:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.pmiUS)||[];
  const pmiChina=(S.pmiChina&&S.pmiChina.length)?S.pmiChina:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.pmiChina)||[];
  const pmiEuro=(S.pmiEuro&&S.pmiEuro.length)?S.pmiEuro:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.pmiEuro)||[];
  // 全球 GDP 增速预期（IMF WEO，年度，静态；回落快照）
  const gdpYears=(S.gdpYears&&S.gdpYears.length)?S.gdpYears:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.gdpYears)||[];
  const gdpValues=(S.gdpValues&&S.gdpValues.length)?S.gdpValues:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.gdpValues)||[];
  const gdpActual=(S.gdpActual&&S.gdpActual.length)?S.gdpActual:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.gdpActual)||[];
  const brent=S.brent,wti=S.wti,dxy=S.dxy,gas=S.gas;
  const pct=(a,b)=>(a!=null&&b!=null&&b!=0)?(a/b-1)*100:null;
  const ret=dates.map((_,i)=>i>0?pct(brent[i],brent[i-1]):null);
  // 20日年化波动率：日收益(已为%)的标准差 × √252；ret 已是百分比，无需再 ×100
  // （原有一个未被引用的 rstd() 死函数已删除：它按 i<n 遍历却用 vals[j] 取值，且与下面的 vol20 重复）
  let vol20=dates.map((_,i)=>{let s=0,ss=0,c=0;for(let j=Math.max(0,i-CONST.volWindow+1);j<=i;j++)if(ret[j]!=null){s+=ret[j];ss+=ret[j]*ret[j];c++;}if(c<CONST.volMinPeriods)return null;const mean=s/c;const variance=Math.max(0,ss/c-mean*mean);return Math.sqrt(variance)*Math.sqrt(CONST.annualizePeriods);});
  const crack=dates.map((_,i)=>(gas[i]!=null&&wti[i]!=null)?gas[i]*CONST.galPerBbl-wti[i]:null);
  const spread_bw=dates.map((_,i)=>(brent[i]!=null&&wti[i]!=null)?brent[i]-wti[i]:null);
  const dxy_chg5=dates.map((_,i)=>i>=CONST.dxyChgWindow?pct(dxy[i],dxy[i-CONST.dxyChgWindow]):null);
  // 与 Python src.common.series.rolling_zscore 对齐：按位置滚动 z-score（基线=最近 252 个观测）
  function rollingZscore(arr, window, minPeriods){
    window = window||CONST.scoreWindow; minPeriods = minPeriods||CONST.scoreMinPeriods;
    const out=[];
    for(let i=0;i<arr.length;i++){
      const lo=Math.max(0,i-window+1);
      let s=0,ss=0,c=0;
      for(let j=lo;j<=i;j++){ if(arr[j]!=null){ s+=arr[j]; ss+=arr[j]*arr[j]; c++; } }
      if(c<minPeriods){ out.push(null); continue; }
      const mean=s/c, sd=Math.sqrt(Math.max(0,ss/c-mean*mean));
      const v=arr[i];
      out.push(v==null?null:(sd===0?0:(v-mean)/sd));
    }
    return out;
  }
  const zc=rollingZscore(crack),zg=rollingZscore(gas),zd=rollingZscore(dxy);
  const clip=(x)=>Math.max(0,Math.min(100,x));
  const supply=zc.map(z=>clip(50+CONST.sensSupply*(z||0)));
  const demand=zg.map(z=>clip(50+CONST.sensDemand*(z||0)));
  const macro=zd.map(z=>clip(50+CONST.sensMacro*(z||0)));
  // ---------- 地缘与情绪恐慌指数 I_geo（0–4）----------
  const ovx=(S.ovx!=null)?S.ovx:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.ovx?SNAPSHOT.ovx:dates.map(()=>null));
  function scoreIgeoOVX(v){ if(v==null)return 0; if(v>CONST.ovxHigh)return 2; if(v>=CONST.ovxMid)return 1; return 0; }   // <30=0；30–35 缺口按 0
  function scoreIgeoSpread(s){ if(s==null)return 0; if(s>CONST.spreadHigh)return 1; return 0; }                       // 3–5=0；5–7、<3 缺口按 0
  function scoreIgeoSpare(c){ if(c==null)return 0; if(c<CONST.spareLow)return 1; return 0; }                          // <200万桶/日=+1；>400=0；2.0–4.0 缺口按 0
  // 剩余产能查表：先按月份排序一次（不再依赖 opecSpareMonths 的输入顺序），
  // 再二分找「<= 目标月」的最新一条 —— 旧实现对每个交易日线性扫描全部月份，
  // 997 天 × 156 月 ≈ 15.5 万次比较，且源数据乱序时会静默取错月份。
  const sparePairs=[];
  for(let i=0;i<opecSpareMonths.length;i++){ if(opecSpareMonths[i]!=null) sparePairs.push([opecSpareMonths[i],opecSpare[i]]); }
  sparePairs.sort((a,b)=>a[0]<b[0]?-1:(a[0]>b[0]?1:0));
  const spareM=sparePairs.map(p=>p[0]), spareV=sparePairs.map(p=>p[1]);
  function spareAt(dStr){
    const mk=dStr.slice(0,7);
    let lo=0,hi=spareM.length;                    // bisect_right
    while(lo<hi){const mid=(lo+hi)>>1; if(spareM[mid]<=mk)lo=mid+1; else hi=mid;}
    return lo>0?spareV[lo-1]:null;
  }
  const igeoBreak=dates.map((_,i)=>({ovx:scoreIgeoOVX(ovx[i]),bw:scoreIgeoSpread(spread_bw[i]),spare:scoreIgeoSpare(spareAt(dates[i]))}));
  const igeo=igeoBreak.map(b=>b.ovx+b.bw+b.spare);
  const geo=igeo.map(v=>clip(v/CONST.geoMaxScore*100)); // 归一化 0–100，并入维度风险与综合风险
  const other=dates.map((_,i)=>{let c=0;for(let j=Math.max(0,i-CONST.jumpWindow+1);j<=i;j++)if(ret[j]!=null&&Math.abs(ret[j])>CONST.jumpThreshold)c++;return clip(c*CONST.perJumpScore);});
  // 综合分：geo 与 other 同源(波动率)，先合并为「地缘·波动」块再四通道等权，去双计
  const composite=dates.map((_,i)=>{
    const gv=(geo[i]!=null&&other[i]!=null)?(geo[i]+other[i])/2:null;
    const vals=[supply[i],demand[i],macro[i],gv];
    return vals.every(v=>v!=null)?clip((supply[i]+demand[i]+macro[i]+gv)/4):null;
  });
  const EIA_MAP=EIA?EIA.map:null;
  const eia_gasSupplied=EIA_MAP?EIA_MAP.gasSupplied:(S.gasSupplied||dates.map(()=>null));
  /* ⚠️ 2026-10-07：这里原来是一张**手写白名单** `eia:{cushing,total,prod,gasinv,util,gasSupplied}`。
     加 spr 后白名单没跟上 → 「拉取实时」后 STATE.eia.spr 不存在 → SPR 图空白（用户报的「图没了」），
     连徽章也一起空。改法：**EIA.map 里的序列全部原样带出**，不再逐个点名；
     新增序列只要进了 python 的 EIA_SERIES 就自动生效（离线侧由 dataio.GROUPS 兜住）。
     底部先把快照的 eia.* 抄一份作底稿，这样 EIA 拉取失败/未配 Key 时不会把已有值洗空 ——
     与整文件其它静态序列「优先 S、缺失回落 SNAPSHOT」的约定一致。 */
  const eia_all=Object.assign({},(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.eia)||{});
  if(EIA_MAP) Object.keys(EIA_MAP).forEach(function(k){ eia_all[k]=EIA_MAP[k]; });
  // alerts
  const alerts=[];
  for(let i=1;i<n;i++){if(ret[i]!=null&&Math.abs(ret[i])>=CONST.alertRet)alerts.push({date:dates[i],dim:"其他突发",level:Math.abs(ret[i])>=CONST.alertRetHigh?"high":"mid",msg:`Brent 单日变动 ${ret[i].toFixed(1)}%`});
    if(vol20[i]!=null&&vol20[i]>=CONST.alertVol)alerts.push({date:dates[i],dim:"地缘政治",level:"high",msg:`${CONST.volWindow}日年化波动率 ${vol20[i].toFixed(0)}%`});
    if(dxy_chg5[i]!=null&&Math.abs(dxy_chg5[i])>=CONST.alertDxy)alerts.push({date:dates[i],dim:"宏观金融",level:"mid",msg:`美元 ${CONST.dxyChgWindow} 日变动 ${dxy_chg5[i].toFixed(1)}%`});}
  const events=[];for(let i=0;i<n;i++)if(ret[i]!=null&&Math.abs(ret[i])>CONST.jumpThreshold)events.push({date:dates[i],ret:ret[i],level:Math.abs(ret[i])>=CONST.alertRetHigh?"high":"mid"});
  if(EIA_MAP&&EIA_MAP.cushing){
    for(let i=1;i<n;i++){if(EIA_MAP.cushing[i]!=null&&EIA_MAP.cushing[i-1]!=null){const dg=EIA_MAP.cushing[i]-EIA_MAP.cushing[i-1];if(Math.abs(dg)>=CONST.cushingAlert){const amt=(dg>=0?"+":"")+dg.toFixed(1);alerts.push({date:dates[i],dim:"供给侧",level:Math.abs(dg)>=CONST.cushingHigh?"high":"mid",msg:"库欣原油库存周变动 "+amt+" 百万桶"});}}}
  }
  alerts.sort((a,b)=>b.date<a.date?-1:1);
  if(alerts.length>CONST.maxAlerts)alerts.length=CONST.maxAlerts;   // 库欣库存预警追加后再统一截断，保留最近 CONST.maxAlerts 条
  // 相关系数矩阵：实时模式下序列已刷新，必须同步重算。
  // 旧实现恒用 SNAPSHOT.corr，导致「拉取实时」后矩阵仍是旧数据的。
  // ⚠️ 2026-10-06 补齐：上面算出的 corr 一度**没有真的返回**（return 里又写了一遍
  // SNAPSHOT.corr 字面量），等于注释宣称的修复从未生效。现在 return 直接带出 corr。
  // 口径与 src.pipeline.build_dataset._build_correlation 一致（只算上三角再镜像）。
  const corr={labels:(SNAPSHOT.corr&&SNAPSHOT.corr.labels)||[],matrix:corrMatrix([brent,crack,vol20,dxy,spread_bw])};
  const last=v=>{for(let i=n-1;i>=0;i--)if(v[i]!=null)return v[i];return null;};
  const kpis={brent:last(brent),wti:last(wti),dxy:last(dxy),spread_bw:last(spread_bw),crack:last(crack),vol20:last(vol20),composite:last(composite)};
  // 静态预测数据读取（IEA / OPEC 通用）：优先传入的 S，缺失回落 SNAPSHOT（与上面各静态序列同一约定）
  const sv=(k,dflt)=>{
    if(S&&S[k]!=null&&(!Array.isArray(S[k])||S[k].length)) return S[k];
    if(typeof SNAPSHOT!=="undefined"&&SNAPSHOT[k]!=null&&(!Array.isArray(SNAPSHOT[k])||SNAPSHOT[k].length)) return SNAPSHOT[k];
    return dflt;
  };
  return {meta:SNAPSHOT.meta,dates,brent,wti,dxy,dff:S.dff,dgs10:S.dgs10,gas,gasSupplied:eia_gasSupplied,crack,spread_bw,dxy_chg5,vol20,
    ovx:ovx,igeo:igeo,igeoBreak:igeoBreak,
    brentCot:(S.brentCot&&S.brentCot.length)?S.brentCot:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.brentCot?SNAPSHOT.brentCot:dates.map(()=>null)),
    brentTerm:(S.brentTerm&&S.brentTerm.length)?S.brentTerm:(typeof SNAPSHOT!=="undefined"&&SNAPSHOT.brentTerm?SNAPSHOT.brentTerm:dates.map(()=>null)),
    // 抓取状态（ok / error / points / last）：序列整段为空时据此在卡内给出可操作说明，
    // 而不是让用户对着一张没有任何提示的空图猜（2026-10-06 修）。
    brentTermMeta:S.brentTermMeta||null,
    // eia_all = 全部序列原样带出（含 spr 等新增序列），不再用手写白名单逐个点名
    eia:eia_all,
    eiaDates:EIA?EIA.dates:[], eiaWeekly:EIA?EIA.weekly:{},
    dims:{supply,demand,geo,macro,other},composite,alerts,events,corr,kpis,
    steoDocMembers,steoDoCTotal,
    steoMonths,steoWorldMonthly,steoOpecMonthly,steoNonOpecMonthly,steoOpecMembers,
    steoForecastStart,steoForecastIndex,steoLastHistorical,steoWorldMeta,
    opecSpareMonths,opecSpare,brentMonthly,
    rigMonths,rigWorld,
    oecdMonths,oecdCrude,oecdProducts,oecdTotal,
    usSprMonths,usSpr,
    usUtilMonths,usUtil,cnProcMonths,cnProc,cnImportMonths,cnImport,
    pmiMonths,pmiUS,pmiChina,pmiEuro,
    gdpYears,gdpValues,gdpActual,
    // IEA 预测体系：纯静态（无实时对应）。computeDerived 会整体替换 STATE，
    // 若不在此带出，内嵌 FRED Key 开页自动拉取（setTimeout loadLive）后
    // 「未来展望」会取到空值并显示"IEA 预测数据缺失"。
    ieaOmrMonths:sv("ieaOmrMonths",[]),ieaOmr2026Demand:sv("ieaOmr2026Demand",[]),
    ieaOmr2027Demand:sv("ieaOmr2027Demand",[]),ieaOmrWarOnset:sv("ieaOmrWarOnset",""),
    ieaOutlookYears:sv("ieaOutlookYears",[]),ieaOutlook2023:sv("ieaOutlook2023",[]),
    ieaOutlook2024:sv("ieaOutlook2024",[]),ieaOutlook2025:sv("ieaOutlook2025",[]),
    ieaOutlookMeta:sv("ieaOutlookMeta",{}),
    // OPEC 预测体系：同为纯静态（无实时对应），同上必须在此带出。
    opecMomrMonths:sv("opecMomrMonths",[]),opecMomr2026Demand:sv("opecMomr2026Demand",[]),
    opecMomr2027Demand:sv("opecMomr2027Demand",[]),opecMomrWarOnset:sv("opecMomrWarOnset",""),
    opecWooYears:sv("opecWooYears",[]),opecWooDemand:sv("opecWooDemand",[]),
    opecWoo2025:sv("opecWoo2025",[]),opecWoo2024:sv("opecWoo2024",[]),opecWoo2023:sv("opecWoo2023",[]),
    opecForecastMeta:sv("opecForecastMeta",{}),
    // EIA 预测体系：同为纯静态（无实时对应），同上必须在此带出。
    eiaSteoMonths:sv("eiaSteoMonths",[]),eiaSteo2026Demand:sv("eiaSteo2026Demand",[]),
    eiaSteo2027Demand:sv("eiaSteo2027Demand",[]),eiaSteoWarOnset:sv("eiaSteoWarOnset",""),
    eiaAeoYears:sv("eiaAeoYears",[]),eiaAeoConsHigh:sv("eiaAeoConsHigh",[]),
    eiaAeoConsLow:sv("eiaAeoConsLow",[]),eiaAeoCaseHigh:sv("eiaAeoCaseHigh",""),
    eiaAeoCaseLow:sv("eiaAeoCaseLow",""),eiaAeoConsBase:sv("eiaAeoConsBase",[]),
    eiaAeoCaseBase:sv("eiaAeoCaseBase",""),eiaForecastMeta:sv("eiaForecastMeta",{}),
    // 其余落库静态键的统一兜底带出：computeDerived 会整体替换 STATE，凡未在此列出的
    // SNAPSHOT 键都会在实时刷新后丢失（2026-10-06 用 Object.keys(SNAPSHOT) 与
    // computeDerived 返回值做全量比对，揪出 13 个漏登记键，oecdProducts 是唯一已有
    // 读取方、因此肉眼可见的那个）。下列键当前页面未直接读取，但同属落库数据，
    // 一并用 sv() 带出，避免后续新增引用时再踩同一个坑。
    oecdMeta:sv("oecdMeta",{}),usSprMeta:sv("usSprMeta",{}),rigMonthlyMeta:sv("rigMonthlyMeta",{}),
    steoOpecMembersMeta:sv("steoOpecMembersMeta",{}),
    pmiMeta:sv("pmiMeta",{}),gdpMeta:sv("gdpMeta",{}),
    // IMF《WEO》期次面板：同为纯静态（无实时对应）。除序列外，latestLabel 是页尾
    // 「IMF《世界经济展望》X 更新」里 X 的唯一来源，漏带出会让页尾回落到占位文案。
    imfWoeMonths:sv("imfWoeMonths",[]),imfWoe2026Growth:sv("imfWoe2026Growth",[]),
    imfWoe2027Growth:sv("imfWoe2027Growth",[]),imfWoeMeta:sv("imfWoeMeta",{}),
    // IMF 油价基准假设期次面板（「未来展望」模块 outlook7；按 WEO 辑分组，右上角年份按钮切换）
    imfOilEditions:sv("imfOilEditions",[]),imfOilByEdition:sv("imfOilByEdition",{}),
    // EIA STEO 表 2 油价基准预测期次面板（outlook8，2026-10-14 新增；与 IMF 并列成
    // 「原油价格预测」组；同为纯静态、无实时对应）
    eiaSteoPriceMonths:sv("eiaSteoPriceMonths",[]),eiaSteoBrent2026:sv("eiaSteoBrent2026",[]),
    eiaSteoBrent2027:sv("eiaSteoBrent2027",[]),eiaSteoBrentActual2025:sv("eiaSteoBrentActual2025",{}),
    eiaSteoPriceMeta:sv("eiaSteoPriceMeta",{}),
    usUtilMeta:sv("usUtilMeta",{}),cnProcMeta:sv("cnProcMeta",{}),cnImportMeta:sv("cnImportMeta",{}),
    opecYears:sv("opecYears",[]),opec:sv("opec",[]),ret:sv("ret",[])};
}

/* ---------- EIA 序列一致性自检（init 时跑一次） ----------
   复现路径：首屏读快照一切正常 → 开页 400ms 自动拉取一次实时 → 某张图整张空白。
   2026-10-07 的 SPR 图就是这个：前端序列 id 表漏了 spr，「拉取实时」后 STATE.eia.spr
   根本不存在。这里在初始化后立刻对一次账：EIA_SERIES 里声明的每个序列，快照必须
   同时有日度值（STATE.eia.*）和周度值（STATE.eiaWeekly.*），缺就点名报错 ——
   让断点提前到 Console，而不是等用户看到一张空白图来反馈。 */
(function auditEiaSeries(){
  const ids=(typeof EIA_SERIES!=="undefined"&&EIA_SERIES.ids)||{};
  const missing=[];
  Object.keys(ids).forEach(function(k){
    const wk=STATE.eiaWeekly&&STATE.eiaWeekly[k], dy=STATE.eia&&STATE.eia[k];
    if(!wk||!dy||!wk.length||!dy.length) missing.push(k+"（"+ids[k]+"）");
  });
  if(!missing.length)return;
  console.error("[dashboard] EIA 序列在快照里缺失："+missing.join("、")+
    "。通常是新增序列后没重新 build（产物里的 EIA_SERIES 常量是旧的），"+
    "或 build_axes / dataio.GROUPS 没带上它；离线跑 node tools/check_eia_series.js 可复现。");
  const s=$("status");
  if(s)s.textContent="⚠ 数据不完整："+missing.length+" 个 EIA 序列缺失，详见 Console";
})();

/* ---------- init ---------- */
buildPanels();
renderAll();
syncRiskHeights();   // 首屏三卡等高：以「整体风险概览」卡高度为基准钉高，另两卡内部滚动
// 已内嵌 FRED Key 时开页自动拉取一次（无需手动点按钮）
if((API_KEYS.fred||"").trim()){ setTimeout(loadLive, 400); }
