// 图 3 几何校验：柱数、年份标签、极值标注、说明文字、无越界/NaN
const fs=require('fs');
const html=fs.readFileSync(__dirname+'/../output/gold-terminal.html','utf8');
const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
let inner='', foot='';
const svg={id:'cbAnnual',set innerHTML(v){inner=v;},get innerHTML(){return inner;},setAttribute(){},getAttribute(){return null;}};
const footEl={id:'cbAnnualFoot',set innerHTML(v){foot=v;},get innerHTML(){return foot;}};
const mk=id=>({id,_h:'',set innerHTML(v){this._h=v;},get innerHTML(){return this._h;},setAttribute(){},getAttribute(){return null;},style:{}});
const byId={cbAnnual:svg,cbAnnualFoot:footEl};
['cbCountry','cbMonthly','cnCbMonthly'].forEach(i=>byId[i]=mk(i));
global.window={GOLD_PANEL_DATA:{},addEventListener(){},location:{protocol:'file:'},confirm:()=>false,alert(){},prompt(){}};
global.navigator={}; global.setInterval=()=>{};
global.IntersectionObserver=class{constructor(){}observe(){}unobserve(){}};
global.document={getElementById:id=>byId[id]||{setAttribute(){},addEventListener(){},classList:{add(){},toggle(){},contains:()=>false},style:{},querySelector:()=>null},querySelector:()=>({get textContent(){return '';},set textContent(v){},setAttribute(){},classList:{add(){},toggle(){}}}),querySelectorAll:()=>[],createElement:()=>({style:{}}),body:{appendChild(){},removeChild(){}}};
try{eval(scripts[1]);}catch(e){console.log('data err',e.message);}
try{eval(scripts[2]);}catch(e){console.log('main err',e.message);}
const rows=window.GOLD_PANEL_DATA.cbAnnual||[];
const rects=[...inner.matchAll(/<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/g)].map(m=>({x:+m[1],y:+m[2],w:+m[3],h:+m[4]}));
const texts=[...inner.matchAll(/<text[^>]*y="([\d.]+)"[^>]*>([^<]*)</g)].map(m=>({y:+m[1],t:m[2]}));
const years=texts.filter(t=>/^(19|20)\d\d$/.test(t.t)).map(t=>t.t);
const dashed=/stroke-dasharray="3 2"/.test(inner);
console.log('渲染长度', inner.length, '| 柱', rects.length, '| 年份标签', years.length, '| 首尾', years[0], years[years.length-1]);
console.log('极值标注:', texts.filter(t=>/^[+-]?\d+(\.\d+)?$/.test(t.t)&&t.y<240).map(t=>t.t).join(' '));
console.log('当年空心虚线柱:', dashed);
console.log('阶段说明:', foot.replace(/<[^>]+>/g,'').slice(0,150));
const bad=inner.match(/NaN|undefined/g);
console.log('异常值:', bad?bad.length:0);
const oob=[...inner.matchAll(/<rect x="(-?[\d.]+)" y="(-?[\d.]+)"/g)].filter(m=>+m[1]<0||+m[1]>920||+m[2]<0||+m[2]>300);
console.log('越界柱:', oob.length, '| 数据行数 == 柱数:', rows.length===rects.length);
console.log('结论:', (!bad && !oob.length && rows.length===rects.length && dashed && foot.includes('阶段读数'))?'PASS':'FAIL');
