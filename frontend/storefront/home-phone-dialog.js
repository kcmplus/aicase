import {openPhoneModelDialog} from './phone-model-dialog.js';
import {esc} from './art.js';
import {phoneBrand} from './phone-catalog.js';
import {caseStylePicker} from './case-styles.js';
import {reconcilePhoneColor} from './phone-colors.js';

// Choices stay local until confirmation. This dialog never creates an order or AI job.
export function openHomePhoneDialog({root,initial={},catalog,refresh,lang='en-US',scoped=false,onConfirm}){
 const say=(en,zh)=>lang==='zh-CN'?zh:en;
 const opener=document.activeElement,dialog=document.createElement('dialog');
 dialog.className='v35-home-phone';dialog.setAttribute('aria-labelledby','home-phone-title');
 let draft={model:initial.model||'',caseMaterial:initial.caseMaterial||'',phoneColor:initial.phoneColor||null};
 let brand=catalog().selection(draft.model||catalog().models[0])?.brand||phoneBrand(draft.model||catalog().models[0]),closed=false,refreshing=false,closeModels=()=>{};
 function selection(){
  const {models,status,selection}=catalog();
  if(status!=='ready'||!models.includes(draft.model))return null;
  return selection(draft.model,draft.caseMaterial);
 }
 function draw(focus){
  const {models,status,selection:lookup}=catalog(),brands=[...new Set(models.map(model=>lookup(model)?.brand||phoneBrand(model)))];
  if(!brands.includes(brand))brand=brands[0]||'';
  const record=models.includes(draft.model)?lookup(draft.model):null;
  const choice=selection(),colors=choice?.colors||[];
  draft.phoneColor=reconcilePhoneColor(draft.phoneColor,colors).color;
  const ready=Boolean(choice)&&!refreshing;
  dialog.innerHTML=`<header><h2 id="home-phone-title">${say('Choose your phone & color','选择机型与颜色')}</h2><button type="button" data-home-close aria-label="${say('Close','关闭')}">×</button></header><div class="v35-home-phone-body"><button type="button" class="v35-phone-selects" id="home-phone-model" data-home-model-open aria-haspopup="dialog"><span>${esc(brand||say('Phone','手机'))}</span><span>${esc(draft.model||say('Choose phone model','选择手机机型'))} <i aria-hidden="true">⌄</i></span></button>${status!=='ready'||!models.length?`<p role="status">${say('Available models could not be loaded or none are available.','机型暂不可用或暂无可选机型。')} <button type="button" data-home-retry ${refreshing?'disabled':''}>${say(refreshing?'Loading…':'Try again',refreshing?'正在加载…':'重新加载')}</button></p>`:''}${record?caseStylePicker(record,draft.caseMaterial,{lang,scoped}).replaceAll('data-case-material','data-home-material'):''}${colors.length?`<fieldset class="v35-home-colors"><legend>${say('Phone body color','机身颜色')}</legend><div>${colors.map(c=>`<button type="button" data-home-color="${esc(c.code)}" aria-label="${esc(c.name)}" aria-pressed="${draft.phoneColor?.code===c.code}" style="--body-color:rgb(${c.rgb.r},${c.rgb.g},${c.rgb.b})"></button>`).join('')}</div><p aria-live="polite">${esc(draft.phoneColor?.name||'')}</p><p>${say('Matches your phone body and camera area. It does not change your artwork or printed colors.','仅用于机身与镜头区域的近似颜色预览，不改变你的设计或打印颜色。')}</p></fieldset>`:''}${choice&&!choice.templateId?`<p class="field-note">${say('Illustrative preview. The exact case template will be confirmed before printing.','当前为示意预览，打印前将核实准确模板。')}</p>`:''}</div><footer><span>${esc(!draft.model?say('Choose a model','请选择机型'):!choice?say('Choose case style','请选择款式'):draft.model)}</span><button type="button" class="v35-entry v35-primary" data-home-confirm ${ready?'':'disabled'}>${say('Start designing','开始设计')} →</button></footer>`;
  const target=(focus&&dialog.querySelector(focus))||dialog.querySelector('#home-phone-model:not(:disabled)')||dialog.querySelector('[data-home-close]');
  target?.focus({preventScroll:true});
 }
 function dispose(){if(closed)return;closed=true;closeModels();dialog.close();dialog.remove();document.body.classList.remove('v35-phone-open');if(opener?.isConnected)opener.focus({preventScroll:true});}
 dialog.addEventListener('cancel',event=>{event.preventDefault();dispose();});
 // The editor's document shortcut must not consume a native dialog's Escape.
 dialog.addEventListener('keydown',event=>{if(event.key==='Escape')event.stopPropagation();});
 dialog.addEventListener('click',async event=>{
  event.stopPropagation();
  const el=event.target.closest('button');if(!el||el.disabled)return;
  if(el.hasAttribute('data-home-close'))return dispose();
  if(refreshing)return;
  if(el.hasAttribute('data-home-model-open')){
   closeModels=openPhoneModelDialog({root,selected:draft.model,catalog,refresh,lang,onSelect:model=>{brand=catalog().selection(model)?.brand||phoneBrand(model);if(model!==draft.model)draft={model,caseMaterial:'',phoneColor:null};draw('#home-phone-model');}});return;
  }
  if(el.hasAttribute('data-home-retry')){
   refreshing=true;draw();
   try{await refresh();}finally{refreshing=false;if(!closed)draw('[data-home-retry]');}
   return;
  }
  if(el.dataset.homeMaterial){draft.caseMaterial=el.dataset.homeMaterial;draw(`[data-home-material="${draft.caseMaterial}"]`);}
  if(el.dataset.homeColor){const color=selection()?.colors?.find(c=>c.code===el.dataset.homeColor);if(color){draft.phoneColor=color;draw(`[data-home-color="${color.code}"]`);}}
  if(el.hasAttribute('data-home-confirm')){
   const choice=selection();
   // Re-read the live catalog: background refreshes may invalidate an open choice.
   if(!choice)return draw();
   const current=reconcilePhoneColor(draft.phoneColor,choice.colors||[]).color;
   if(JSON.stringify(current)!==JSON.stringify(draft.phoneColor)){draft.phoneColor=current;draw();return;}
   const result={...draft,phoneColor:current,phoneTemplateId:choice.templateId};dispose();onConfirm(result);
  }
 });
 root.append(dialog);draw();dialog.showModal();document.body.classList.add('v35-phone-open');dialog.querySelector('#home-phone-model')?.focus();
 return dispose;
}
