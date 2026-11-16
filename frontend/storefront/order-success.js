import {esc} from './art.js';

// Only fresh server responses can be passed to the caller's confirmation hook.
// Return URLs and these session markers express intent; neither proves payment.
export function orderSuccessContent(order,lang='en-US'){
 if(!order?.server||order.refund||!['paid','printing','ready','completed','collected'].includes(order.status)||!Number.isSafeInteger(order.priceCents)||order.priceCents<0||! /^[A-Z]{3}$/.test(order.currency||''))return null;
 const zh=lang==='zh-CN',say=(en,cn)=>zh?cn:en;
 let title,message;
 if(order.mode==='free_test'&&order.priceCents===0&&order.progress?.payment==='free'){
  title=say('Order confirmed','下单成功');message=say('Your no-charge order is confirmed and your design is saved. No payment was collected.','免付订单已确认，设计已保存，无需付款。');
 }else if(/^(stripe|airwallex)_live$/.test(order.mode||'')&&order.progress?.payment==='paid'){
  title=say('Payment successful','支付成功');message=say('Your payment is complete and your design is saved.','付款已完成，你的设计已保存。');
 }else if((/^(stripe|airwallex)_test$/.test(order.mode||'')||order.mode==='demo')&&order.progress?.payment==='test'){
  title=say('Test order confirmed','测试下单成功');message=say('Your test order and design are saved. No real payment was collected.','测试订单和设计已保存，未产生真实扣款。');
 }else return null;
 return {title,message,amount:new Intl.NumberFormat(zh?'zh-CN':'en-US',{style:'currency',currency:order.currency}).format(order.priceCents/100),reference:order.id};
}
export function createOrderSuccessTracker({key='popomo-order-success',storage=()=>globalThis.sessionStorage}={}){
 let pending=new Set(),seen=new Set();
 try{const data=JSON.parse(storage()?.getItem(key)||'{}');pending=new Set(Array.isArray(data.pending)?data.pending.filter(v=>typeof v==='string'):[]);seen=new Set(Array.isArray(data.seen)?data.seen.filter(v=>typeof v==='string'):[]);}catch{}
 const save=()=>{pending=new Set([...pending].slice(-100));seen=new Set([...seen].slice(-100));try{storage()?.setItem(key,JSON.stringify({pending:[...pending],seen:[...seen]}));}catch{}};
 const arm=id=>{if(typeof id==='string'&&!seen.has(id)){pending.add(id);save();}};
 return {arm,observe(order,{returned=false}={}){
  if(!order?.server)return false;
  if(order.refund||order.status==='cancelled'){pending.delete(order.id);save();return false;}
  if(order.status==='pending'||returned)arm(order.id);
  if(!pending.has(order.id)||seen.has(order.id)||!orderSuccessContent(order))return false;
  pending.delete(order.id);seen.add(order.id);save();return true;
 }};
}
export function openOrderSuccess(order,{lang='en-US',onOrders,onClose}={}){
 const content=orderSuccessContent(order,lang);if(!content)return null;
 const zh=lang==='zh-CN',dialog=document.createElement('dialog'),opener=document.activeElement;
 dialog.className='v35-order-success';dialog.setAttribute('aria-labelledby','order-success-title');dialog.setAttribute('aria-describedby','order-success-message');
 dialog.innerHTML=`<span class="order-success-check" aria-hidden="true">✓</span><h2 id="order-success-title">${esc(content.title)}</h2><p id="order-success-message">${esc(content.message)}</p><strong class="order-success-amount">${esc(content.amount)}</strong><p class="order-success-reference">${zh?'订单编号':'Order number'} <span>${esc(content.reference)}</span></p><div class="order-success-actions"><button type="button" class="button primary" data-success-details>${zh?'查看订单详情':'View order details'}</button><button type="button" class="button secondary" data-success-orders>${zh?'我的订单':'My orders'}</button></div>`;
 let closed=false;
 const close=()=>{if(closed)return;closed=true;window.removeEventListener('hashchange',close);dialog.close();dialog.remove();document.body.classList.remove('order-success-open');onClose?.();if(opener?.isConnected)opener.focus({preventScroll:true});else document.querySelector('#main')?.focus({preventScroll:true});};
 dialog.addEventListener('keydown',event=>event.stopPropagation());
 dialog.addEventListener('cancel',event=>{event.preventDefault();close();});dialog.addEventListener('close',close);
 dialog.querySelector('[data-success-details]').onclick=close;
 dialog.querySelector('[data-success-orders]').onclick=()=>{close();onOrders?.();};
 window.addEventListener('hashchange',close);document.body.append(dialog);document.body.classList.add('order-success-open');dialog.showModal();
 return {id:order.id,close};
}
