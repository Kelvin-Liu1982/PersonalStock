/* 校验「Non-OPEC DoC 原油产量（月度）」ECharts 双格图（2026-10-11 换源后：STEO 表 3d 10 国）。
   用法（oil-analysis 目录下）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_nonopec_doc.js
   【换源背景】数据由 MOMR 表 5-7 的 Total Non-OPEC DoC + 10 国（31 月，2024-02~2026-08）
   换成 EIA STEO base tables Excel 表 3d 的 `OPEC+ other participants` 段（脚注 b 后半句：
   Azerbaijan/Bahrain/Brunei/Kazakhstan/Malaysia/Mexico/Oman/Russia/South Sudan/Sudan ——
   与 MOMR DoC 同一份 10 国清单），合计行 = copr_opecplus_other，轴与全球图同一条 steoMonths，
   截到末个历史月 → **57 月 2022-01~2026-09**。分国行仅历史段有值（STEO 无分国预测）。
   检查项：2 个 grid（上=俄罗斯 / 下=其余九国）→ 两条 xAxis 同 57 月且 gridIndex 显式 →
   两条 yAxis 上下界分别贴合各自量级 → 10 条 series 的归属/颜色/末值（index 56）/endLabel/避叠
   → 图例 10 个中文项 → 10 国分项之和 == 合计 → 徽章 = 合计 14.05 · 截至 26/09 →
   页尾单段 STEO 表 3d 文案 → 与 OPEC 双格图并排等高 → JS 报错数（含 pageerror 栈）。
   ⚠️ 该图是 ECharts，实例挂在 ecCharts（不是 charts）。 */
const {chromium}=require('playwright');
const FILE='file:///Users/sto1/WorkBuddy/业绩追踪看板/大宗商品分析/oil-analysis/output/crude_oil_dashboard.html';
(async()=>{
  const b=await chromium.launch();
  const p=await b.newPage({viewport:{width:1440,height:1600}});
  const errs=[];
  p.on('pageerror',e=>errs.push('PAGEERROR '+e.message+'\n'+(e.stack||'').split('\n')[1]));
  p.on('console',m=>{if(m.type()==='error')errs.push('CONSOLE '+m.text());});
  await p.goto(FILE); await p.waitForTimeout(3000);
  const el=await p.$('#box_supply_prodcap_nonopecdoc');
  if(!el){ console.log('FAIL 找不到 #box_supply_prodcap_nonopecdoc'); await b.close(); return; }
  await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(1200);
  const out=await p.evaluate(()=>{
    const id='supply_prodcap_nonopecdoc';
    const inst=ecCharts[id];
    if(!inst) return {err:'ecCharts 实例未找到（该图应为 ECharts 双格）'};
    const o=inst.getOption();
    const box=document.getElementById('box_'+id);
    const H=(box||{}).clientHeight||0;
    const gpx=function(g){ return (g.height!=null)?g.height:(H-(g.top||0)-(g.bottom||0)); };
    const badge=document.querySelector('.cstat[data-stat="nonOpecDoCTotal"]');
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
    // 图例标记的**实渲染填充色**（ECharts 图例取 series.itemStyle.color，见 OPEC 图的同款问题）
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
      legendFills:legendFills,
      grids:(o.grid||[]).map(function(g){return {left:g.left,right:g.right,top:g.top,bottom:g.bottom,height:g.height,px:gpx(g)};}),
      xAxis:(o.xAxis||[]).map(function(a){return {gi:a.gridIndex,n:(a.data||[]).length,
        first:(a.data||[])[0],last:(a.data||[])[(a.data||[]).length-1]};}),
      yAxis:(o.yAxis||[]).map(function(a){return {gi:a.gridIndex,min:a.min,max:a.max};}),
      legend:((o.legend||[])[0]||{}).data,
      series:series,
      badge:badge?badge.textContent.trim():'(no .cstat)',
      src:src,
      // ⚠️ getOption() 把 axisPointer 返回成**数组**（与 legend 同），link 在 [0] 里
      axisPointerLink:JSON.stringify((((o.axisPointer||[])[0])||{}).link||[]),
      // 与 OPEC 双格图并排显示在同一行：grid 版式与总高必须逐像素一致（2026-10-10 用户要求）
      opecInst:(function(){return !!ecCharts['supply_prodcap_opec'];})(),
      gridsAligned:(function(){
        const oi=ecCharts['supply_prodcap_opec']; if(!oi) return null;
        const gsig=function(gs){return JSON.stringify((gs||[]).map(function(g){return [g.left,g.right,g.top,g.height,g.bottom];}));};
        return gsig(oi.getOption().grid)===gsig(o.grid);
      })(),
      opecH:(function(){
        const oi=ecCharts['supply_prodcap_opec']; if(!oi) return null;
        return (document.getElementById('box_supply_prodcap_opec')||{}).clientHeight||0;
      })(),
      // 恒等：10 国分项之和 == 合计（图内不画合计线但自洽须保持；分国只有历史段）
      sumBad:(function(){
        const ms=STATE.steoMonths||[], cs=STATE.steoDocMembers||{}, tt=STATE.steoDoCTotal||[];
        const bad=[]; let mx=0, n=0;
        ms.forEach(function(m,i){
          let s=0,k=0;
          Object.keys(cs).forEach(function(nm){ if(cs[nm][i]!=null){ s+=cs[nm][i]; k++; } });
          if(k!==10) return;                       // 预测月分国为空，跳过
          n++;
          const d=Math.abs(s-tt[i]); if(d>mx) mx=d;
          if(d>0.05) bad.push(m+':'+s.toFixed(3)+'vs'+tt[i]);
        });
        return {bad:bad.slice(0,5),maxAbs:Number(mx.toFixed(4)),nCountries:Object.keys(cs).length,nChecked:n};
      })()
    };
  });
  console.log(JSON.stringify(out,null,1));
  console.log('ERRORS='+errs.length+(errs.length?'\n'+errs.join('\n'):''));
  // ---- 断言 ----
  // 末点 = 末个历史月 2026-09（STEO 表 3d，mb/d）。g=0 上格（俄罗斯）/ g=1 下格（其余九国）
  const EXPECT={'俄罗斯':{v:8.773,col:'#4f81bd',g:0},
                '哈萨克斯坦':{v:1.866,col:'#92d050',g:1},
                '墨西哥':{v:1.431,col:'#f5c842',g:1},
                '阿曼':{v:0.850,col:'#e94e5a',g:1},
                '阿塞拜疆':{v:0.438,col:'#7c3aed',g:1},
                '马来西亚':{v:0.344,col:'#ea580c',g:1},
                '南苏丹':{v:0.130,col:'#6366f1',g:1},
                '文莱':{v:0.087,col:'#0d9488',g:1},
                '巴林':{v:0.100,col:'#0891b2',g:1},
                '苏丹':{v:0.030,col:'#db2777',g:1}};
  const fails=[];
  if(out.err) fails.push('图表未找到: '+out.err);
  if(!out.grids||out.grids.length!==2) fails.push('应有 2 个 grid，实际 '+(out.grids?out.grids.length:0));
  if(!out.xAxis||out.xAxis.length!==2) fails.push('应有 2 条 xAxis，实际 '+(out.xAxis?out.xAxis.length:0));
  (out.xAxis||[]).forEach(function(a,i){
    if(a.gi!==i) fails.push('xAxis['+i+'].gridIndex 应为 '+i+'，实际 '+a.gi+'（省略会导致整图白屏）');
    if(a.n!==57) fails.push('xAxis['+i+'] 应为 57 月（2022-01~2026-09 历史段，分国无预测），实际 '+a.n);
    if(a.first!=='2022-01'||a.last!=='2026-09') fails.push('xAxis['+i+'] 首末月 '+a.first+'~'+a.last+' != 2022-01~2026-09');
  });
  if(out.xAxis&&out.xAxis.length===2&&(out.xAxis[0].first!==out.xAxis[1].first||out.xAxis[0].n!==out.xAxis[1].n))
    fails.push('两格 x 轴数据不一致（未真正共享 x 轴）');
  if(!out.yAxis||out.yAxis.length!==2) fails.push('应有 2 条 yAxis，实际 '+(out.yAxis?out.yAxis.length:0));
  const ya=out.yAxis||[];
  if(ya.length===2){
    if(ya[0].gi!==0||ya[1].gi!==1) fails.push('yAxis gridIndex 应为 0/1，实际 '+ya[0].gi+'/'+ya[1].gi);
    // 上格贴俄罗斯（全史 8.723–10.066）→ 8.5–10.25（0.25 步进取整）；下格 0–2.0（哈萨克 1.866）
    if(!(ya[0].min>=8.25&&ya[0].min<=8.75)) fails.push('上格 min 应贴 8.5 附近，实际 '+ya[0].min);
    if(!(ya[0].max>=10&&ya[0].max<=10.5)) fails.push('上格 max 应贴 10.25 附近，实际 '+ya[0].max);
    // 下格起点取 0：苏丹/巴林 0.03 量级，压掉 0–0.5 会把小国整条裁掉
    if(!(ya[1].min>=0&&ya[1].min<=0.05)) fails.push('下格 min 应取 0（九国里有 0.03 量级的苏丹/巴林），实际 '+ya[1].min);
    if(!(ya[1].max>=1.9&&ya[1].max<=2.6)) fails.push('下格 max 应贴 2.0 附近，实际 '+ya[1].max);
    if(ya[0].min===ya[1].min&&ya[0].max===ya[1].max) fails.push('两格 Y 轴上下界相同（未起到分格作用）');
  }
  if(!out.series||out.series.length!==10) fails.push('应有 10 条 series，实际 '+(out.series?out.series.length:0));
  (out.series||[]).forEach(function(s){
    const e=EXPECT[s.name];
    if(!e){ fails.push('出现未预期的序列: '+s.name); return; }
    if(s.xi!==e.g||s.yi!==e.g) fails.push(s.name+' 应挂 grid'+e.g+'（xAxisIndex/yAxisIndex='+e.g+'），实际 '+s.xi+'/'+s.yi);
    if(String(s.col).toLowerCase()!==e.col) fails.push(s.name+' 颜色 '+s.col+' != '+e.col);
    // 图例取色源：itemStyle 必须与 lineStyle 同色（2026-10-11 随 OPEC 图一并修）
    if(String(s.item).toLowerCase()!==e.col) fails.push(s.name+' itemStyle.color '+s.item+' != '+e.col+'（图例会回落默认调色盘）');
    if(!s.end) fails.push(s.name+' endLabel 未开启（末点应只显示数值）');
    // 下格九线末值密集（苏丹 0.03 ~ 哈萨克 1.866，最小相邻差 0.013），必须开纵向避叠
    if(e.g===1&&s.overlap!=='shiftY') fails.push(s.name+' labelLayout.moveOverlap 应为 shiftY（下格 9 线末值密集必然叠字），实际 '+s.overlap);
    if(s.lastIdx!==56) fails.push(s.name+' 末点应在 index 56（2026-09），实际 '+s.lastIdx);
    if(Math.abs(s.last-e.v)>0.002) fails.push(s.name+' 末点 '+s.last+' != 期望 '+e.v);
  });
  Object.keys(EXPECT).forEach(function(k){
    if(!(out.series||[]).some(s=>s.name===k)) fails.push('缺少序列: '+k);
  });
  if(!out.legend||out.legend.length!==10) fails.push('图例应有 10 个中文项，实际 '+(out.legend?out.legend.length:0));
  Object.keys(EXPECT).forEach(function(k){
    if(out.legend&&out.legend.indexOf(k)<0) fails.push('图例缺少: '+k);
  });
  // 图例实渲染色 == 折线色（按 series 顺序逐项比对）
  const EXPCOLS=['#4f81bd','#92d050','#f5c842','#e94e5a','#7c3aed',
                 '#ea580c','#6366f1','#0d9488','#0891b2','#db2777'];
  if(!out.legendFills||out.legendFills.length!==10)
    fails.push('图例标记应渲染 10 个，实际 '+(out.legendFills?out.legendFills.length:0));
  if(out.legendFills&&out.legendFills.length===10)
    out.legendFills.forEach(function(c,i){
      if(c!==EXPCOLS[i]) fails.push('图例['+i+'] 填充色 '+c+' != 折线色 '+EXPCOLS[i]);
    });
  // 历史事件竖线：俄乌冲突 2022-02 / 欧盟对俄海运原油禁运 2022-12 / OPEC+ 自愿减产 2023-11
  // （仅上格 grid 0 俄罗斯序列，事件与俄罗斯相关，不画下格那 9 国）
  const ruSeries=(out.series||[]).find(function(s){return s.name==='俄罗斯';});
  if(!ruSeries) fails.push('找不到俄罗斯序列（无法校验历史事件竖线）');
  else{
    const want=['俄乌冲突 22/02','欧盟禁运 22/12','OPEC+ 自愿减产 23/11'];
    want.forEach(function(w){ if(ruSeries.marks.indexOf(w)<0) fails.push('俄罗斯序列 markLine 缺少历史事件竖线: '+w); });
    if(ruSeries.marks.length!==3) fails.push('俄罗斯序列 markLine 应为 3 条（俄乌冲突/欧盟禁运/OPEC+ 自愿减产），实际 '+ruSeries.marks.length);
  }
  // 下格（grid 1）不应有该竖线：事件与那 9 国无关，避免误读
  const bottomHasLine=(out.series||[]).some(function(s){return s.xi===1&&s.marks&&s.marks.length>0;});
  if(bottomHasLine) fails.push('下格（grid 1）不应出现历史事件竖线（事件仅与俄罗斯相关）');
  // 徽章：走 STEO 合计（steoHistCut 截到末个历史月 2026-09 = 14.05）
  if(!(/14\.05/.test(out.badge)&&/26\/09/.test(out.badge)&&/合计/.test(out.badge)))
    fails.push('徽章应为「合计 14.05 · 截至 26/09」，实际 '+JSON.stringify(out.badge));
  if(/13\.97/.test(out.badge)) fails.push('徽章仍是旧 MOMR 值 13.97（换源未生效）');
  // 页尾：单段 STEO 月度 API 简化文案（2026-10-16 起：EIA STEO 月度 API（序列 COPR_OPECPLUS_OTHER ＋ DoC 10 国分项）· 实时抓取脚本）
  if(/secondary sources|opec_momr\.py/.test(out.src)) fails.push('页尾仍含 MOMR 旧文案特征（secondary sources / opec_momr.py），换源未生效');
  if(/other participants|表 3d/.test(out.src)) fails.push('页尾不应再含「other participants」/「表 3d」旧长文案，简化未生效');
  if(!(/EIA STEO 月度 API/.test(out.src)&&/COPR_OPECPLUS_OTHER/.test(out.src)
       &&/steo_monthly\.py/.test(out.src)&&/DoC 10 国分项/.test(out.src)))
    fails.push('页尾应为 STEO 月度 API 单段（COPR_OPECPLUS_OTHER ＋ DoC 10 国分项 + 脚本路径），实际 '+JSON.stringify(out.src));
  if(!out.axisPointerLink||out.axisPointerLink.indexOf('xAxisIndex')<0)
    fails.push('axisPointer.link 未配置（十字线无法上下贯穿两格）');
  if(out.gridsAligned!==true) fails.push('与 OPEC 双格图 grid 版式不一致（两图并排，y 轴必须逐像素对齐）');
  // 上下两格等高（用户要求：两个 y 轴高度差不多）
  if(out.grids&&out.grids.length===2){
    out.gridHeightDiff=Math.abs(out.grids[0].px-out.grids[1].px);
    if(out.gridHeightDiff>4) fails.push('上下两格高度差 '+out.gridHeightDiff+'px（应等高）');
  }
  if(out.opecH!=null&&out.opecH!==out.boxH) fails.push('两图总高不一致: nonopec='+out.boxH+'px opec='+out.opecH+'px');
  if(out.sumBad&&out.sumBad.nCountries!==10) fails.push('国别数据应有 10 国，实际 '+out.sumBad.nCountries);
  if(out.sumBad&&out.sumBad.bad.length) fails.push('10 国之和 != 合计: '+out.sumBad.bad.join(','));
  if(out.sumBad&&!(out.sumBad.nChecked>=57)) fails.push('恒等校验月数应 ≥57，实际 '+out.sumBad.nChecked);
  if(errs.length) fails.push('页面报错 '+errs.length+' 条');
  console.log('\n--- 断言 ---');
  console.log(fails.length?('FAIL\n  '+fails.join('\n  '))
    :'ALL OK — Non-OPEC DoC 图（STEO API 10 国）：上格俄罗斯 / 下格九国、57 月历史段、末点仅数值、10 国恒等');
  await el.screenshot({path:'/Users/sto1/WorkBuddy/业绩追踪看板/大宗商品分析/oil-analysis/output/_shot_nonopec_steo.png'}).catch(()=>{});
  await b.close();
  process.exit(fails.length?1:0);
})();
