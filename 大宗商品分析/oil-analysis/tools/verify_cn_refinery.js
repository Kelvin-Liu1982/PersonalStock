/* 校验中国原油加工量 / 中国原油进口量两张图已刷到 xlsx 修正后的值。
   用法（oil-analysis 目录）：
     NODE_PATH=/Users/sto1/.workbuddy/skills/huashu-design/node_modules \
     /Users/sto1/.workbuddy/binaries/node/versions/22.22.2-6/bin/node tools/verify_cn_refinery.js
   检查：两张图的序列末值 → 需求侧 KPI 芯片（中国原油加工量 / 中国原油进口）→
   卡片徽章 → 落库数组长度与末月 → JS 报错数。 */
const {chromium}=require('playwright');
const FILE='file:///Users/sto1/WorkBuddy/业绩追踪看板/大宗商品分析/oil-analysis/output/crude_oil_dashboard.html';
(async()=>{
  const b=await chromium.launch();
  const p=await b.newPage({viewport:{width:1440,height:1400}});
  const errs=[];
  p.on('pageerror',e=>errs.push('PAGEERROR '+e.message));
  p.on('console',m=>{if(m.type()==='error')errs.push('CONSOLE '+m.text());});
  await p.goto(FILE); await p.waitForTimeout(2600);
  await p.evaluate(()=>{
    const tb=[...document.querySelectorAll('#tabs button')].find(b=>/需求/.test(b.textContent));
    if(tb)tb.click();
  });
  await p.waitForTimeout(1600);
  const out=await p.evaluate(()=>{
    const tail=arr=>(arr||[]).slice(-6);
    const pick=k=>{
      const c=charts[k]; if(!c) return null;
      c.update('none');
      return {id:k, datasets:c.data.datasets.map(d=>({l:d.label, axis:d.yAxisID||'y', len:d.data.length,
        last:d.data[d.data.length-1], tail:tail(d.data)}))};
    };
    const keys=Object.keys(charts);
    return {
      chartKeys:keys,
      refinery:pick('demand_util_refinery')||pick(keys.filter(k=>/refinery/.test(k))[0]),
      cnimp:pick('demand_cnimp')||pick(keys.filter(k=>/cnimp|cnimp/.test(k))[0]),
      state:{cnProcMonths:(STATE.cnProcMonths||[]).slice(-3), cnProcTail:tail(STATE.cnProc),
             cnImportMonths:(STATE.cnImportMonths||[]).slice(-3), cnImportTail:tail(STATE.cnImport)},
      kpiChips:[...document.querySelectorAll('#dk_demand div')].map(d=>d.textContent.trim()).filter(t=>/中国/.test(t)),
      badges:[...document.querySelectorAll('.cstat')].map(e=>e.getAttribute('data-stat')+'='+(e.textContent||'(空)')).filter(s=>/cn|refin/.test(s))
    };
  });
  console.log(JSON.stringify(out,null,1));
  console.log('ERRORS='+errs.length+(errs.length?'\n'+errs.join('\n'):''));
  await p.screenshot({path:'/tmp/cn_refinery.png',fullPage:false}).catch(()=>{});
  await b.close();
})();
