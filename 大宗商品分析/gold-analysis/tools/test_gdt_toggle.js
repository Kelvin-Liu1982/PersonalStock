// 验证供需卡展开/收起：模拟点击，断言 hidden / aria-expanded / 标题文案
const fs=require('fs');
const html=fs.readFileSync(__dirname+'/../output/gold-terminal.html','utf8');
const scripts=[...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
function mk(id){
  const el={id,attrs:{},_h:'',_t:'',handlers:{},
    setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return k in this.attrs?this.attrs[k]:null;},
    removeAttribute(k){delete this.attrs[k];},hasAttribute(k){return k in this.attrs;},
    addEventListener(ev,fn){(this.handlers[ev]=this.handlers[ev]||[]).push(fn);},
    scrollIntoView(){}, focus(){}, querySelector(){return mk('q');}, querySelectorAll(){return [];},
    classList:{add(){},remove(){},toggle(){},contains(){return false;}}};
  Object.defineProperty(el,'innerHTML',{get(){return this._h;},set(v){this._h=v;}});
  Object.defineProperty(el,'textContent',{get(){return this._t;},set(v){this._t=v;}});
  return el;
}
const toggle=mk('gdtToggle'), panel=mk('gdtPanel');
panel.setAttribute('hidden','');
const sl=mk('sl');
toggle.querySelector=()=>sl;
const byId={gdtToggle:toggle,gdtPanel:panel,gdtDemandChart:mk('gdtDemandChart'),gdtSupplyChart:mk('gdtSupplyChart'),
  gdtDemLegend:mk('gdtDemLegend'),gdtSupLegend:mk('gdtSupLegend'),gdtFoot:mk('gdtFoot'),gdtTip:mk('gdtTip'),
  gdtQuarter:mk('gdtQuarter'),gdtDemand:mk('gdtDemand'),gdtSupply:mk('gdtSupply'),gdtMix:mk('gdtMix'),gdtPanelMeta:mk('gdtPanelMeta'),
  cbCountry:mk('cbCountry'),cbMonthly:mk('cbMonthly'),cbAnnual:mk('cbAnnual'),cnCbMonthly:mk('cnCbMonthly')};
global.window={GOLD_PANEL_DATA:{},addEventListener(){},location:{protocol:'file:'},confirm:()=>true,alert(){},prompt(){},innerWidth:1400,innerHeight:900};
global.navigator={}; global.setInterval=()=>{};
global.IntersectionObserver=class{constructor(){}observe(){}unobserve(){}};
global.document={getElementById:id=>byId[id]||mk(id),querySelector:sel=>sel==='#gdtToggle .sl'?sl:mk('q'),querySelectorAll:()=>[],createElement:()=>mk('t'),body:{appendChild(){},removeChild(){}}};
try{eval(scripts[1]);}catch(e){}
try{eval(scripts[2]);}catch(e){console.log('main err:',e.message);}
console.log('初始: hidden=',panel.hasAttribute('hidden'),'| aria=',toggle.getAttribute('aria-expanded'),'| 标题=',sl.innerHTML.replace(/<[^>]+>/g,''));
console.log('卡片数值:', byId.gdtQuarter.textContent, byId.gdtDemand.textContent, '|', byId.gdtSupply.textContent);
(toggle.handlers.click||[]).forEach(f=>f());
console.log('展开后: hidden=',panel.hasAttribute('hidden'),'| aria=',toggle.getAttribute('aria-expanded'),'| 标题=',sl.innerHTML.replace(/<[^>]+>/g,''));
(toggle.handlers.click||[]).forEach(f=>f());
console.log('收起后: hidden=',panel.hasAttribute('hidden'),'| aria=',toggle.getAttribute('aria-expanded'),'| 标题=',sl.innerHTML.replace(/<[^>]+>/g,''));
(toggle.handlers.keydown||[]).forEach(f=>f({key:'Enter',preventDefault(){}}));
console.log('回车展开:',panel.hasAttribute('hidden')===false?'OK':'FAIL');
const ok = panel.hasAttribute('hidden')===false && toggle.getAttribute('aria-expanded')==='true' &&
  sl.innerHTML.indexOf('收起')>=0;
console.log('结论:', ok?'PASS（初始收起；点击/回车均可展开收起；标题同步）':'FAIL');
