// GDT 供需图校验：堆叠段数、命中区、图例、卡片数值、悬浮明细构建
const fs=require('fs');
const html=fs.readFileSync(__dirname+'/../output/gold-terminal.html','utf8');
const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
const store={};
const mk=(id)=>({id,_h:'',set innerHTML(v){this._h=v;store[id]=v;},get innerHTML(){return this._h;},setAttribute(){},getAttribute:()=>null,style:{},addEventListener(){}});
const txtEl=id=>({id,_t:'',set textContent(v){this._t=v;},get textContent(){return this._t;},setAttribute(){},getAttribute:()=>null,addEventListener(){},classList:{add(){},toggle(){},contains:()=>false},style:{}});
const ids=['gdtDemandChart','gdtSupplyChart']; const byId={};
ids.forEach(i=>byId[i]=mk(i));
['gdtDemLegend','gdtSupLegend','gdtDemMeta','gdtSupMeta'].forEach(i=>byId[i]={_h:'',set innerHTML(v){this._h=v;store[i]=v;},get innerHTML(){return this._h;},setAttribute(){},addEventListener(){}});
['cbCountry','cbMonthly','cbAnnual','cnCbMonthly','dtDebt'].forEach(i=>byId[i]=byId[i]||mk(i));
['gdtQuarter','gdtDemand','gdtSupply','gdtMix','gdtTip'].forEach(i=>byId[i]=byId[i]||txtEl(i));
byId['gdtFoot']={_h:'',set innerHTML(v){this._h=v;store['gdtFoot']=v;},get innerHTML(){return this._h;},setAttribute(){},addEventListener(){}};
global.window={GOLD_PANEL_DATA:{},addEventListener(){},location:{protocol:'file:'},confirm:()=>false,alert(){},prompt(){},innerWidth:1400,innerHeight:900};
global.navigator={}; global.setInterval=()=>{};
global.IntersectionObserver=class{constructor(){}observe(){}unobserve(){}};
global.document={getElementById:id=>byId[id]||txtEl(id),querySelector:()=>txtEl('q'),querySelectorAll:()=>[],createElement:()=>txtEl('t'),body:{appendChild(){},removeChild(){}}};
try{eval(scripts[1]);}catch(e){console.log('data err',e.message);}
try{eval(scripts[2]);}catch(e){console.log('main err:',e.message);}
const rows=(window.GOLD_PANEL_DATA||{}).gdtQuarter||[];
for(const id of ids){
  const h=store[id]||'';
  const segs=(h.match(/<rect/g)||[]).length;
  const hits=(h.match(/class="gdt-hit"/g)||[]).length;
  const qLabels=(h.match(/class="lab"/g)||[]).length;
  console.log(`${id}: len=${h.length} rect=${segs} 命中区=${hits} 季度=${rows.length}`);
  if(hits!==rows.length) console.log('  ✗ 命中区数量与季度数不符');
  if(!/<text[^>]*>\d{3,4}<\//.test(h)) console.log('  ✗ 未见合计标签');
}
console.log('图例(需求):', (store['gdtDemLegend']||'').replace(/<[^>]+>/g,'|'));
console.log('图例(供应):', (store['gdtSupLegend']||'').replace(/<[^>]+>/g,'|'));
console.log('卡片:', ['gdtQuarter','gdtDemand','gdtSupply','gdtMix'].map(i=>byId[i].textContent).join(' | '));
console.log('说明:', (store['gdtFoot']||'').replace(/<[^>]+>/g,'').slice(0,160));

// --- 几何校验：文本出界 / X 轴标签重叠 / 柱宽 ---
function geom(id){
  const h=store[id]||'';
  const vbW=900, vbH=330;
  const texts=[...h.matchAll(/<text[^>]*x="(-?[\d.]+)"[^>]*y="(-?[\d.]+)"[^>]*text-anchor="(\w+)"[^>]*>([^<]*)</g)]
    .map(m=>({x:+m[1],y:+m[2],a:m[3],t:m[4]}));
  const box=o=>{const w=o.t.length*5.4;const x=o.a==='end'?o.x-w:(o.a==='middle'?o.x-w/2:o.x);return{x0:x,x1:x+w,y0:o.y-9,y1:o.y+3,t:o.t};};
  const bs=texts.map(box);
  const oob=bs.filter(b=>b.x0<0||b.x1>vbW||b.y0<0||b.y1>vbH);
  let hit=0; const pairs=[];
  for(let i=0;i<bs.length;i++)for(let j=i+1;j<bs.length;j++){
    const a=bs[i],b=bs[j];
    if(a.y1>b.y0&&b.y1>a.y0&&a.x1>b.x0&&b.x1>a.x0){hit++; if(pairs.length<4)pairs.push(a.t+'('+a.x0.toFixed(0)+'-'+a.x1.toFixed(0)+',y'+a.y0.toFixed(0)+') × '+b.t+'('+b.x0.toFixed(0)+'-'+b.x1.toFixed(0)+',y'+b.y0.toFixed(0)+')');}
  }
  if(hit) console.log('    重叠明细:', pairs.join(' ; '));
  const bw=[...h.matchAll(/width="([\d.]+)" height="\d+"/g)].map(m=>+m[1]).filter(v=>v>2&&v<30);
  console.log(`  ${id}: 文本 ${bs.length} | 越界 ${oob.length} | 重叠 ${hit} | 柱宽 ${bw.length?bw[0].toFixed(1):'?'}px`);
  return {oob:oob.length,hit};
}
const g1=geom('gdtDemandChart'), g2=geom('gdtSupplyChart');


// --- 负半轴校验：可负系列是否真的画在零轴下方 ---
function negAxis(chartId, key, color, label){
  const h=store[chartId]||'';
  const m=h.match(/<line x1="[\d.]+" y1="([\d.]+)"[^>]*stroke-width="1.6"/);
  if(!m) return console.log(`  ${chartId}: 未找到零轴`);
  const zeroY=+m[1];
  const hits=[...h.matchAll(/class="gdt-hit"[^>]*data-i="(\d+)" x="([\d.]+)"/g)];
  const rects=[...h.matchAll(/<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" fill="(#\w+)"/g)]
    .map(t=>({x:+t[1],y:+t[2],w:+t[3],h:+t[4],c:t[5]}));
  let ok=0, wrong=0, posInStack=0;
  rows.forEach((r,i)=>{
    const x0=+hits[i][2];
    const seg=rects.find(t=>t.c===color && Math.abs(t.x-(x0+2.5))<3.5);
    const v=Number(r[key])||0;
    if(v<0){
      if(seg && seg.y>=zeroY-0.8 && (seg.y+seg.h)>zeroY+0.2) ok++; else wrong++;
    }else if(seg){ posInStack++; }
  });
  console.log(`  ${chartId} 零轴y=${zeroY} | ${label}：负值季 ${ok} 个在零轴下方，异常 ${wrong} | 为正的 ${posInStack} 个并入上方堆叠`);
  return wrong;
}
const n1=negAxis('gdtSupplyChart','hedging','#7FA8C9','套保');
const n2=negAxis('gdtDemandChart','cb','#C026D3','央行及其他');

const bad=(store['gdtDemandChart']||'').match(/NaN|undefined/g);
console.log('异常值:', bad?bad.length:0);
const last=rows[rows.length-1];
const okCard = byId['gdtDemand'].textContent === last.demand.toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})+'t';
console.log('卡片数值与数据一致:', okCard);
console.log('结论:', (store['gdtDemandChart']&&store['gdtSupplyChart']&&okCard&&!bad&&!g1.oob&&!g1.hit&&!g2.oob&&!g2.hit)?'PASS':'FAIL');
