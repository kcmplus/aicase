import {esc,icon} from './art.js';
import {caseMaterialLabel} from './case-styles.js';
import {deliveryLabel} from './fulfillment-service.js';
import {progressPanel,progressPaymentText} from './order-progress.js';

export function orderListPage({rows=[],loading=false,error='',page=1,hasMore=false,filter='all',search='',counts=null,lang='en-US',station='',statusLabel,designName}){
 const zh=lang==='zh-CN',say=(en,cn)=>zh?cn:en;
 const action=(id,label,kind='text-button')=>`<button class="${kind}" data-action="view-order" data-id="${esc(id)}">${label}</button>`;
 const card=o=>{
  const date=new Date(o.created_at),validDate=Number.isFinite(date.getTime());
  const label=o.refund||o.status==='cancelled'?statusLabel(o.status,o.refund):['printed','delivering','dispensed'].includes(o.progress?.code)?say('Printed','已打印'):o.progress?progressPaymentText(o.progress,lang):statusLabel(o.status);
  const amount=Number(o.amount),price=Number.isFinite(amount)&&/^[A-Z]{3}$/.test(o.currency)?new Intl.NumberFormat(zh?'zh-CN':'en-US',{style:'currency',currency:o.currency}).format(amount):'—';
  const title=designName?.(o)||say('My custom design','我的专属设计');
  const printer=o.fulfillment_type==='pickup'&&o.progress?.device?.device_id&&['paid','free'].includes(o.progress?.payment);
 const test=o.mode==='free_test'?say('Zero-payment test · No charge','0 元测试 · 无需扣款'):/^(demo|stripe_test|airwallex_test)$/.test(o.mode||'')?say('Test order · No real charge','测试订单 · 无实际扣款'):'';
  return `<article class="order-row"><header class="order-card-header"><span>${say('Order','订单编号')} <strong>${esc(o.reference)}</strong></span><span class="order-status-badge">${esc(label)}</span></header><div class="order-card-content"><button class="order-cover" data-order-preview="${esc(o.reference)}" data-action="view-order" data-id="${esc(o.reference)}" aria-label="${esc(say('View design','查看设计')+' · '+title)}"><span class="order-cover-placeholder" aria-hidden="true">▯</span></button><div class="order-card-info"><h2>${esc(title)}</h2><p>${esc(o.model_name)}${o.case_material?' · '+esc(caseMaterialLabel(o.case_material,lang)):''}</p><span class="order-delivery-tag">${icon(o.fulfillment_type==='pickup'?'box':'bag',14)} ${o.fulfillment_type==='pickup'?say('Device printing','设备打印'):deliveryLabel(o.fulfillment_type,lang)}</span><time ${validDate?`datetime="${date.toISOString()}"`:''}>${say('Created','创建时间')} ${validDate?date.toLocaleString(lang):'—'}</time>${test?`<small class="order-test-note">${test}</small>`:''}</div><div class="order-card-actions"><strong aria-label="${esc(o.currency+' '+(Number.isFinite(amount)?amount.toFixed(2):'—'))}">${esc(price)}</strong>${action(o.reference,say('Order details ↗','订单详情 ↗'))}</div>${o.status==='pending'&&!o.refund?`<div class="order-card-next">${action(o.reference,say('Pay now →','去支付 →'),'button primary')}</div>`:printer?`<div class="order-card-next"><button class="button secondary" data-action="view-order" data-order-section="printer" data-id="${esc(o.reference)}">${say('Printer & directions ↗','打印网点与导航 ↗')}</button></div>`:''}</div>${o.progress?`<details class="order-card-progress"><summary>${say('Order progress','订单进度')}</summary>${progressPanel(o.progress,{lang,compact:true})}</details>`:''}</article>`;
 };
 const empty=`<div class="orders-empty"><h2>${say('No matching orders','暂无相关订单')}</h2><p>${search||filter!=='all'?say('Try another search or order status.','试试其他关键词或订单状态。'):say('Choose a design to create your print order.','从喜欢的设计开始，创建你的打印订单。')}</p><a class="button primary" href="#my-designs">${say('My designs ↗','我的设计 ↗')}</a></div>`;
 return `<section class="flow wrap v35-orders" aria-busy="${loading}">${station}<div class="orders-heading"><p class="eyebrow">YOUR PRINT ORDERS</p><h1>${say('My orders','我的订单')}</h1><p>${say('Every creation has a story to keep.','每一份设计，都有自己的记录。')}</p></div><div class="orders-toolbar"><div class="orders-tabs" role="group" aria-label="${say('Order status','订单状态')}">${[['all','All','全部'],['pending','Unpaid','待支付'],['paid','Paid','已支付'],['printed','Printed','已打印']].map(([key,en,cn])=>`<button data-action="filter-orders" data-filter="${key}" aria-pressed="${filter===key}" ${loading?'disabled':''}>${say(en,cn)}${Number.isSafeInteger(counts?.[key])?` <small>${counts[key]}</small>`:''}</button>`).join('')}</div><form class="orders-search" id="orders-search-form" role="search"><button type="submit" aria-label="${say('Search orders','搜索订单')}" ${loading?'disabled':''}>${icon('search',19)}</button><input type="search" name="q" id="order-search" maxlength="120" placeholder="${say('Search orders or phone models','搜索订单编号或机型')}" aria-label="${say('Search orders or phone models','搜索订单编号或机型')}" value="${esc(search)}" ${loading?'disabled':''}></form></div><div class="orders-refresh"><button class="text-button" data-action="refresh-orders" ${loading?'disabled':''}>${say('Refresh orders ↻','刷新订单 ↻')}</button></div><div id="orders-results" aria-live="polite">${loading?'<p class="v35-order-notice" role="status">'+say('Loading your orders…','正在加载订单…')+'</p>':error?`<p class="error" role="alert">${esc(error)}</p>`:rows.length?`<div class="order-list">${rows.map(card).join('')}</div>`:empty}</div>${!loading&&!error?`<nav class="pass-actions" aria-label="${say('Order pages','订单分页')}">${page>1?`<button class="text-button" data-action="orders-page" data-page="${page-1}">← ${say('Previous','上一页')}</button>`:''}${hasMore?`<button class="text-button" data-action="orders-page" data-page="${page+1}">${say('Next','下一页')} →</button>`:''}</nav>`:''}</section>`;
}

// Fetch private design details only for visible thumbnails through the existing
// authenticated order API. Never put original photos into a public list payload.
export function mountOrderPreviews(root,{load,preview,active=()=>true,lang='en-US'}){
 let stopped=false,busy=false;const queue=[];
 const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){observer.unobserve(entry.target);queue.push(entry.target);}void next();},{rootMargin:'80px'});
 async function next(){
  if(busy||stopped)return;busy=true;
  while(queue.length&&!stopped){const node=queue.shift();if(!node.isConnected||!active())continue;
   try{const order=await load(node.dataset.orderPreview);if(stopped||!node.isConnected||!active())continue;node.innerHTML=preview(order.pass);node.dataset.previewReady='true';}
   catch{if(!stopped&&node.isConnected)node.innerHTML=`<span class="order-preview-unavailable">${lang==='zh-CN'?'查看设计':'View design'}</span>`;}
  }busy=false;
 }
 root.querySelectorAll('[data-order-preview]').forEach(node=>observer.observe(node));
 return ()=>{stopped=true;observer.disconnect();queue.length=0;};
}
