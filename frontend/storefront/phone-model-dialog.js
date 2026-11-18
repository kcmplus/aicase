import {esc} from './art.js';
import {phoneBrand} from './phone-catalog.js';

export function phoneModelChoices({models=[],status='ready',brand='',selected='',lang='en-US',busy=false,selection}={}){
 const say=(en,zh)=>lang==='zh-CN'?zh:en;
 const brandOf=model=>selection?.(model)?.brand||phoneBrand(model);
 const brands=[...new Set(models.map(brandOf).filter(Boolean))],active=brands.includes(brand)?brand:brands[0]||'';
 if(status!=='ready'||!models.length)return `<div class="v35-model-empty" role="status"><p>${say('Phone models are unavailable. Please try again.','机型暂不可用，请重新加载。')}</p><button type="button" data-picker-retry ${busy?'disabled':''}>${say(busy?'Loading…':'Try again',busy?'正在加载…':'重新加载')}</button></div>`;
 return `<div class="v35-model-brands" role="group" aria-label="${say('Phone brand','手机品牌')}">${brands.map(b=>`<button type="button" data-picker-brand="${esc(b)}" aria-pressed="${b===active}">${esc(b)}</button>`).join('')}</div><div class="v35-model-list" role="group" aria-label="${say('Phone model','手机机型')}">${models.filter(model=>brandOf(model)===active).map(model=>`<button type="button" data-picker-model="${esc(model)}" aria-pressed="${model===selected}"><span>${esc(model)}</span>${model===selected?'<b aria-hidden="true">✓</b>':''}</button>`).join('')}</div>`;
}

// Shared by homepage, editor and AI confirmation. Catalog order and scope stay intact.
export function openPhoneModelDialog({root,selected='',catalog,refresh,lang='en-US',onSelect}){
 const opener=document.activeElement,dialog=document.createElement('dialog');
 dialog.className='v35-model-dialog';dialog.setAttribute('aria-labelledby','v35-model-title');
 const first=selected||catalog().models[0];
 let brand=catalog().selection?.(first)?.brand||phoneBrand(first),closed=false,busy=false;
 function draw(focusBrand){
  const data=catalog();
  dialog.innerHTML=`<header><h2 id="v35-model-title">${lang==='zh-CN'?'选择手机机型':'Choose phone model'}</h2><button type="button" data-picker-close aria-label="${lang==='zh-CN'?'关闭':'Close'}">×</button></header><div class="v35-model-body">${phoneModelChoices({...data,brand,selected,lang,busy})}</div>`;
  const target=focusBrand?[...dialog.querySelectorAll('[data-picker-brand]')].find(el=>el.dataset.pickerBrand===focusBrand):dialog.querySelector('[data-picker-model][aria-pressed=true]');
  (target||dialog.querySelector('[data-picker-close]'))?.focus({preventScroll:true});
 }
 function dispose(){if(closed)return;closed=true;dialog.close();dialog.remove();document.body.classList.remove('v35-model-open');if(opener?.isConnected)opener.focus({preventScroll:true});}
 // Keep editing shortcuts inactive while the model sheet owns keyboard focus.
 dialog.addEventListener('keydown',event=>event.stopPropagation());
 dialog.addEventListener('cancel',event=>{event.preventDefault();dispose();});
 dialog.addEventListener('click',async event=>{
  event.stopPropagation();const el=event.target.closest('button');if(!el||el.disabled)return;
  if(el.hasAttribute('data-picker-close'))return dispose();
  if(busy)return;
  if(el.dataset.pickerBrand){brand=el.dataset.pickerBrand;draw(brand);return;}
  if(el.hasAttribute('data-picker-retry')){busy=true;draw();try{await refresh();}finally{busy=false;if(!closed)draw();}return;}
  if(el.dataset.pickerModel){const data=catalog();if(data.status!=='ready'||!data.models.includes(el.dataset.pickerModel)){draw();return;}const model=el.dataset.pickerModel;dispose();onSelect(model);}
 });
 root.append(dialog);draw();dialog.showModal();document.body.classList.add('v35-model-open');
 dialog.querySelector('[data-picker-close]')?.focus({preventScroll:true});
 return dispose;
}
