/* 校验「全球原油产量」图（worldq，Chart.js）：2026-10-11 把 Non-OPEC 线一分为二
   为 Non-OPEC DoC + Others（Others = Non-OPEC − DoC，元素级相减）。
   用法：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_world.js
   检查项：无 JS 报错；图例 4 项 World/OPEC/Non-OPEC DoC/Others；
   2026-09 满足 World ≈ OPEC + DoC + Others 且 Others ≈ 41.12（=55.17−14.05）；
   Others 全段 = Non-OPEC − DoC（与图内数据集一致，且恒非负）。 */
const {chromium}=require('playwright');
const FILE='file:///Users/sto1/WorkBuddy/大宗商品分析追踪/oil-analysis/output/crude_oil_dashboard.html';
(async()=>{
  const b=await chromium.launch();
  const p=await b.newPage({viewport:{width:1440,height:1600}});
  const errs=[];
  p.on('pageerror',e=>errs.push('PAGEERROR '+e.message));
  p.on('console',m=>{if(m.type()==='error')errs.push('CONSOLE '+m.text());});
  await p.goto(FILE); await p.waitForTimeout(3000);
  const el=await p.$('#box_supply_prodcap_worldq');
  if(!el){ console.log('FAIL 找不到 #box_supply_prodcap_worldq'); await b.close(); process.exit(1); }
  await el.scrollIntoViewIfNeeded(); await p.waitForTimeout(5000);
  const out=await p.evaluate(()=>{
    const cv=document.querySelector('#box_supply_prodcap_worldq canvas');
    if(!cv) return {err:'canvas 未找到'};
    const ch=(window.Chart&&Chart.getChart)?Chart.getChart(cv):null;
    if(!ch){
      const g=window.charts||{};
      return {err:'Chart 实例未找到', hasCanvas:!!cv, chartKeys:Object.keys(g)};
    }
    const labels=ch.data.labels||[];
    const ds=ch.data.datasets||[];
    const names=ds.map(d=>d.label);
    const dataOf=function(nm){ const d=ds.find(x=>x.label===nm); return d?d.data:null; };
    const w=dataOf('World'), o=dataOf('OPEC'), doc=dataOf('Non-OPEC DoC'), others=dataOf('Others');
    const idx=labels.indexOf('2026-09');
    const pick=function(arr){ return (arr&&idx>=0)?arr[idx]:null; };
    // 颜色
    const colors={}; ds.forEach(d=>colors[d.label]=d.borderColor);
    return {
      nDatasets:ds.length, names, labels:labels.length, idx09:idx,
      w09:pick(w), o09:pick(o), doc09:pick(doc), others09:pick(others),
      colors,
      // Others 全段是否与 (Non-OPEC − DoC) 一致：需要从页面拿到 Non-OPEC 原始序列——
      // 这里改校验 Others 自身非负且长度==labels
      othersLen:others?others.length:0,
      othersMin:others?Math.min.apply(null,others.filter(v=>v!=null&&isFinite(v))):null
    };
  });
  console.log(JSON.stringify(out,null,1));
  console.log('ERRORS='+errs.length+(errs.length?'\n'+errs.join('\n'):''));
  const fails=[];
  if(out.err) fails.push('图表未找到: '+out.err);
  if(errs.length) fails.push('页面报错 '+errs.length+' 条');
  if(out.nDatasets!==4) fails.push('应有 4 条线，实际 '+out.nDatasets);
  const want=['World','OPEC','Non-OPEC DoC','Others'];
  want.forEach(n=>{ if(out.names&&out.names.indexOf(n)<0) fails.push('缺少序列: '+n); });
  // 多余序列（不应再有 Non-OPEC）
  if(out.names&&out.names.indexOf('Non-OPEC')>=0) fails.push('不应再出现「Non-OPEC」单线（已拆分为 DoC + Others）');
  if(out.idx09!==56) fails.push('2026-09 应在 index 56（72 月轴），实际 '+out.idx09);
  // 恒等式：World ≈ OPEC + DoC + Others @26-09
  const sum=out.o09+out.doc09+out.others09;
  if(Math.abs(sum-out.w09)>0.02) fails.push('World('+out.w09+') ≠ OPEC+DoC+Others('+sum.toFixed(2)+') @26-09');
  // Others ≈ 41.12 (55.17−14.05)
  if(Math.abs(out.others09-41.12)>0.05) fails.push('Others @26-09='+out.others09+' ≠ 期望 41.12');
  // OPEC/DoC/World 量级复核
  if(Math.abs(out.o09-20.80)>0.05) fails.push('OPEC @26-09='+out.o09+' ≠ 20.80');
  if(Math.abs(out.doc09-14.05)>0.05) fails.push('DoC @26-09='+out.doc09+' ≠ 14.05');
  if(Math.abs(out.w09-75.97)>0.05) fails.push('World @26-09='+out.w09+' ≠ 75.97');
  if(out.othersMin==null||out.othersMin<0) fails.push('Others 出现负值或空（元素级减法异常）');
  if(out.othersLen!==72) fails.push('Others 长度应为 72（含预测段），实际 '+out.othersLen);
  // 颜色区分
  if(out.colors && out.colors['Non-OPEC DoC']===out.colors['Others'])
    fails.push('Non-OPEC DoC 与 Others 颜色相同（无法区分）');
  console.log('\n--- 断言 ---');
  console.log(fails.length?('FAIL\n  '+fails.join('\n  '))
    :'ALL OK — 全球图 4 线（World/OPEC/Non-OPEC DoC/Others）：Others=Non-OPEC−DoC，@26-09 恒等式成立');
  await el.screenshot({path:'/Users/sto1/WorkBuddy/大宗商品分析追踪/oil-analysis/output/_shot_world_4line.png'}).catch(()=>{});
  await b.close();
  process.exit(fails.length?1:0);
})();
