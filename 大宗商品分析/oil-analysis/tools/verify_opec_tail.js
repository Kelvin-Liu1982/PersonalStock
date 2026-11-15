/* 校验「OPEC 原油产量（月度）」ECharts 双格图（2026-10-11 换源后：STEO 表 3d 11 国）。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_opec_tail.js
   【换源背景】数据由 MOMR 表 5-7 的 12 国（含阿联酋，2023-11~2026-08 共 34 月）换成
   EIA STEO base tables Excel 表 3d 的 OPEC 11 国分项（脚注 c 口径、不含阿联酋；
   与全球图同一条 steoMonths 轴，截到末个历史月 → 2022-01~2026-09 共 57 月）。
   ⚠️ STEO 分国行只有历史段有值（2026-10 起无分国预测）→ x 轴止于 26/09。
   检查项：2 个 grid（上=沙特 / 下=其余十国）→ 两条 xAxis 同 57 月且 gridIndex 显式 →
   11 条 series 的归属/颜色/末值/endLabel（仅数值）/标签避叠 → 图例 11 个中文项且无「阿联酋」→
   徽章 = 合计 20.80 · 截至 26/09 → 页尾单段 STEO 表 3d 文案 → axisPointer.link → JS 报错数。
   ⚠️ 该图是 ECharts，实例挂在 ecCharts（不是 charts）。 */
const {chromium}=require('playwright');
const FILE='file:///Users/sto1/WorkBuddy/大宗商品分析追踪/oil-analysis/output/crude_oil_dashboard.html';
(async()=>{
  const b=await chromium.launch();
  const p=await b.newPage({viewport:{width:1440,height:1600}});
  const errs=[];
  p.on('pageerror',e=>errs.push('PAGEERROR '+e.message+'\n'+(e.stack||'').split('\n')[1]));
  p.on('console',m=>{if(m.type()==='error')errs.push('CONSOLE '+m.text());});
  await p.goto(FILE); await p.waitForTimeout(3000);
  const el=await p.$('#box_supply_prodcap_opec');
  if(!el){ console.log('FAIL 找不到 #box_supply_prodcap_opec'); await b.close(); return; }
  await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(1200);
  const out=await p.evaluate(()=>{
    const id='supply_prodcap_opec';
    const inst=ecCharts[id];
    if(!inst) return {err:'ecCharts 实例未找到（该图应为 ECharts 双格）'};
    const o=inst.getOption();
    const box=document.getElementById('box_'+id);
    const H=(box||{}).clientHeight||0;
    const badge=document.querySelector('.cstat[data-stat="opecMonthly"]');
    const src=box&&box.parentNode?(box.parentNode.querySelector('.src')||{}).textContent||'':'';
    const series=(o.series||[]).map(function(s){
      const d=s.data||[]; let k=-1;
      for(let i=d.length-1;i>=0;i--) if(d[i]!=null&&d[i]!=="-"){k=i;break;}
      const ml=(s.markLine&&s.markLine.data)?s.markLine.data.map(function(x){return x.name;}).filter(Boolean):[];
      return {name:s.name,xi:s.xAxisIndex,yi:s.yAxisIndex,col:s.lineStyle&&s.lineStyle.color,
              item:s.itemStyle&&s.itemStyle.color,
              end:(s.endLabel||{}).show===true,
              overlap:(s.labelLayout||{}).moveOverlap||null,
              lastIdx:k,last:d[k],marks:ml};
    });
    // 图例标记的**实渲染填充色**：ECharts 图例取 series.itemStyle.color，
    // 只设 lineStyle.color 时会回落默认调色盘（#5470c6/#91cc75/#fac858/…）→ 与折线对不上。
    const legendFills=(function(){
      const list=inst.getZr().storage.getDisplayList(false)||[];
      const out=[];
      list.forEach(function(el){
        let par=el,isLeg=false;
        while(par){ if(par.__ecComponentInfo&&par.__ecComponentInfo.mainType==='legend'){isLeg=true;break;} par=par.parent; }
        if(!isLeg) return;
        if(el.type==='path'&&el.style&&el.style.fill&&String(el.style.fill)!=='transparent')
          out.push(String(el.style.fill).toLowerCase());
      });
      return out;
    })();
    return {
      boxH:H,
      grids:(o.grid||[]).length,
      legendFills:legendFills,
      xAxis:(o.xAxis||[]).map(function(a){return {gi:a.gridIndex,n:(a.data||[]).length,
        first:(a.data||[])[0],last:(a.data||[])[(a.data||[]).length-1]};}),
      yAxis:(o.yAxis||[]).map(function(a){return {gi:a.gridIndex,min:a.min,max:a.max};}),
      legend:((o.legend||[])[0]||{}).data,
      series:series,
      badge:badge?badge.textContent.trim():'(no .cstat)',
      src:src,
      axisPointerLink:JSON.stringify((((o.axisPointer||[])[0])||{}).link||[])
    };
  });
  console.log(JSON.stringify(out,null,1));
  console.log('ERRORS='+errs.length+(errs.length?'\n'+errs.join('\n'):''));
  // ---- 断言 ----
  // 末点 = 末个历史月 2026-09（STEO 表 3d，mb/d）。g=0 上格（沙特）/ g=1 下格（其余十国）
  const EXPECT={'沙特':{v:8.10,col:'#dc2626',g:0},
                '伊拉克':{v:3.70,col:'#ea580c',g:1},'伊朗':{v:1.90,col:'#d97706',g:1},
                '科威特':{v:1.62,col:'#0891b2',g:1},'尼日利亚':{v:1.49,col:'#db2777',g:1},
                '利比亚':{v:1.27,col:'#7c3aed',g:1},'委内瑞拉':{v:1.21,col:'#0d9488',g:1},
                '阿尔及利亚':{v:0.98,col:'#65a30d',g:1},'刚果':{v:0.27,col:'#2563eb',g:1},
                '加蓬':{v:0.22,col:'#f43f5e',g:1},'赤道几内亚':{v:0.04,col:'#facc15',g:1}};
  const fails=[];
  if(out.err) fails.push('图表未找到: '+out.err);
  if(out.grids!==2) fails.push('应有 2 个 grid，实际 '+out.grids);
  if(!out.xAxis||out.xAxis.length!==2) fails.push('应有 2 条 xAxis，实际 '+(out.xAxis?out.xAxis.length:0));
  (out.xAxis||[]).forEach(function(a,i){
    if(a.gi!==i) fails.push('xAxis['+i+'].gridIndex 应为 '+i+'，实际 '+a.gi+'（省略会整图白屏）');
    if(a.n!==57) fails.push('xAxis['+i+'] 应为 57 月（2022-01~2026-09 历史段，分国无预测），实际 '+a.n);
    if(a.first!=='2022-01'||a.last!=='2026-09') fails.push('xAxis['+i+'] 首末月 '+a.first+'~'+a.last+' != 2022-01~2026-09');
  });
  if(out.xAxis&&out.xAxis.length===2&&(out.xAxis[0].first!==out.xAxis[1].first||out.xAxis[0].n!==out.xAxis[1].n))
    fails.push('两格 x 轴数据不一致（未真正共享 x 轴）');
  const ya=out.yAxis||[];
  if(ya.length!==2) fails.push('应有 2 条 yAxis，实际 '+ya.length);
  if(ya.length===2){
    if(ya[0].gi!==0||ya[1].gi!==1) fails.push('yAxis gridIndex 应为 0/1，实际 '+ya[0].gi+'/'+ya[1].gi);
    // 上格贴沙特（6.46–11.00）→ 6.25–11.25（0.25 步进取整）；下格 0 基线到 4.75（伊拉克 4.58）
    if(!(ya[0].min>=6&&ya[0].min<=6.5)) fails.push('上格 min 应贴 6.25 附近，实际 '+ya[0].min);
    if(!(ya[0].max>=11&&ya[0].max<=11.5)) fails.push('上格 max 应贴 11.25 附近，实际 '+ya[0].max);
    if(ya[1].min!==0) fails.push('下格 min 应为 0，实际 '+ya[1].min);
    if(!(ya[1].max>=4.5&&ya[1].max<=5.1)) fails.push('下格 max 应贴 4.75 附近，实际 '+ya[1].max);
    if(ya[0].min===ya[1].min&&ya[0].max===ya[1].max) fails.push('两格 Y 轴上下界相同（未起到分格作用）');
  }
  if(!out.series||out.series.length!==11) fails.push('应有 11 条 series，实际 '+(out.series?out.series.length:0));
  (out.series||[]).forEach(function(s){
    const e=EXPECT[s.name];
    if(!e){ fails.push('出现未预期的序列: '+s.name); return; }
    if(s.xi!==e.g||s.yi!==e.g) fails.push(s.name+' 应挂 grid'+e.g+'，实际 '+s.xi+'/'+s.yi);
    if(String(s.col).toLowerCase()!==e.col) fails.push(s.name+' 颜色 '+s.col+' != '+e.col);
    // 图例取色源：itemStyle 必须与 lineStyle 同色，否则图例回落默认调色盘（2026-10-11 修）
    if(String(s.item).toLowerCase()!==e.col) fails.push(s.name+' itemStyle.color '+s.item+' != '+e.col+'（图例会回落默认调色盘）');
    if(!s.end) fails.push(s.name+' endLabel 未开启（末点应只显示数值）');
    if(s.overlap!=='shiftY') fails.push(s.name+' labelLayout.moveOverlap 应为 shiftY（下格末值密集，必然叠字），实际 '+s.overlap);
    if(s.lastIdx!==56) fails.push(s.name+' 末点应在 index 56（2026-09），实际 '+s.lastIdx);
    if(Math.abs(s.last-e.v)>0.005) fails.push(s.name+' 末点 '+s.last+' != 期望 '+e.v);
  });
  Object.keys(EXPECT).forEach(function(k){
    if(!(out.series||[]).some(s=>s.name===k)) fails.push('缺少序列: '+k);
  });
  // 换源核心：不再有阿联酋（STEO 的 OPEC 定义不含 UAE）
  if((out.series||[]).some(s=>s.name==='阿联酋')) fails.push('不应再出现「阿联酋」序列（STEO 11 国口径）');
  if(!out.legend||out.legend.length!==11) fails.push('图例应有 11 个中文项，实际 '+(out.legend?out.legend.length:0));
  Object.keys(EXPECT).forEach(function(k){
    if(out.legend&&out.legend.indexOf(k)<0) fails.push('图例缺少: '+k);
  });
  if(out.legend&&out.legend.indexOf('阿联酋')>=0) fails.push('图例不应再含「阿联酋」');
  // 图例实渲染色 == 折线色（按 series 顺序逐项比对）
  const EXPCOLS=['#dc2626','#ea580c','#d97706','#0891b2','#db2777','#7c3aed',
                 '#0d9488','#65a30d','#2563eb','#f43f5e','#facc15'];
  if(!out.legendFills||out.legendFills.length!==11)
    fails.push('图例标记应渲染 11 个，实际 '+(out.legendFills?out.legendFills.length:0));
  if(out.legendFills&&out.legendFills.length===11)
    out.legendFills.forEach(function(c,i){
      if(c!==EXPCOLS[i]) fails.push('图例['+i+'] 填充色 '+c+' != 折线色 '+EXPCOLS[i]);
    });
  if(/刚果（布）/.test(String(out.legend))) fails.push('图例仍含「刚果（布）」（应简写为「刚果」）');
  // 徽章：走 STEO 11 国合计（steoHistCut 截到末个历史月 2026-09 = 20.80）
  if(!(/20\.80/.test(out.badge)&&/26\/09/.test(out.badge)&&/合计/.test(out.badge)))
    fails.push('徽章应为「合计 20.80 · 截至 26/09」，实际 '+JSON.stringify(out.badge));
  if(/24\.08/.test(out.badge)) fails.push('徽章仍是旧 MOMR 12 国值 24.08（换源未生效）');
  // 页尾：单段 STEO 月度 API 简化文案（2026-10-16 起：EIA STEO 月度 API（序列 COPR_OPEC ＋ OPEC 11 国分项）· 实时抓取脚本）
  if(/secondary sources|opec_momr\.py/.test(out.src)) fails.push('页尾仍含 MOMR 旧文案特征（secondary sources / opec_momr.py），换源未生效');
  if(/不含阿联酋|表 3d/.test(out.src)) fails.push('页尾不应再含「不含阿联酋」/「表 3d」旧长文案，简化未生效');
  if(!(/EIA STEO 月度 API/.test(out.src)&&/COPR_OPEC/.test(out.src)
       &&/steo_monthly\.py/.test(out.src)&&/OPEC 11 国分项/.test(out.src)))
    fails.push('页尾应为 STEO 月度 API 单段（COPR_OPEC ＋ OPEC 11 国分项 + 脚本路径），实际 '+JSON.stringify(out.src));
  if(!out.axisPointerLink||out.axisPointerLink.indexOf('xAxisIndex')<0)
    fails.push('axisPointer.link 未配置（十字线无法上下贯穿两格）');
  // 历史事件竖线：2026-02-28 中东军事行动 + 霍尔木兹海峡事实性关闭（OPEC 全线供给冲击，上下 grid 都画）
  const saSeries=(out.series||[]).find(function(s){return s.name==='沙特';});
  if(!saSeries) fails.push('找不到沙特序列（无法校验历史事件竖线）');
  else{
    if(saSeries.marks.indexOf('霍尔木兹关闭 26/02')<0) fails.push('沙特序列 markLine 缺少历史事件竖线: 霍尔木兹关闭 26/02');
    if(saSeries.marks.length!==1) fails.push('沙特序列 markLine 应为 1 条，实际 '+saSeries.marks.length);
  }
  const botHasLine=(out.series||[]).some(function(s){return s.xi===1&&s.marks&&s.marks.length>0;});
  if(!botHasLine) fails.push('下格（grid 1）应出现历史事件竖线（事件影响整个 OPEC）');
  if(errs.length) fails.push('页面报错 '+errs.length+' 条');
  console.log('\n--- 断言 ---');
  console.log(fails.length?('FAIL\n  '+fails.join('\n  '))
    :'ALL OK — OPEC 月图（STEO API 11 国）：上格沙特 / 下格十国、57 月历史段、末点仅数值且自动避叠、无阿联酋');
  await el.screenshot({path:'/Users/sto1/WorkBuddy/大宗商品分析追踪/oil-analysis/output/_shot_opec_11.png'}).catch(()=>{});
  await b.close();
  process.exit(fails.length?1:0);
})();
