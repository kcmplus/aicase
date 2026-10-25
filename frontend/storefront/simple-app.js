import {imageTag} from './image-view.js';
import {orderRequest,savedOrder,checkoutBody} from './order-service.js';
import {phoneBrand,phoneBrands,findPhoneModels} from './phone-catalog.js';
import {fonts} from './editor-model.js';
import {dragPlacement,scaleFromPointer,rotationFromPointer,rotateGroup} from './artwork-drag.js';
import {freshOrders,orderForCode,currentOrder,commitPrintOrder,beginOrderPrint} from './print-orders.js';
import {freshMembership,refreshMembership,subscribe,stopRenewal,addRender,startRender,updateRender,migrateRender} from './ai-membership.js';
import {PRINT_PRICE,PRINT_PRICE_CENTS,PRINT_AVAILABLE,money} from './simple-pricing.js';
import {loadCatalog,catalogStatus} from './runtime-catalog.js';
import {aiExamples,exampleFor} from './ai-examples.js';
import {designFor,stickers} from './catalog.js';
import {phone, icon, brandLogo, esc} from './art.js';
import {designs, phoneModels, stations, readPass, stationAvailability, advancePrint, createPersonalPass} from './simple-core.js';

import {effects, collectionForPhoto, validateAddedArtwork, validatePlacement, isPhoto, makePersonalDesign, personalPassName} from './simple-personalize.js';
import {readDesign, writeDesign, updateDesign} from './simple-storage.js';
import {stylePanel, aiPage, membershipPage, trialOffer, planSummary} from './ai-view.js';
import {aiStyles,refreshAIOrder,canApplyAIOrder,DEMO_QUEUE_MS,DEMO_RENDER_MS} from './ai-core.js';
import {importPhoto} from './simple-upload.js';
import {create as createQR} from './vendor/qr.js';

const KEY = 'popomo-simple-v1';
const app = document.querySelector('#app');
app.textContent='Loading POPOMO…';
await loadCatalog();
let state = {designId:'bloom',model:'',pass:null,stationId:'DEMO-01',job:null,source:'collection',photo:'',effect:'original',intensity:65,zoom:100,x:50,y:50,aiStyle:'anime',aiExample:'portrait',artworkLayouts:{},photoArtwork:[],keepCollection:false,photoPlacement:null,photoOrigin:'upload',ai:null,aiJobId:null};
let storageWarning = false;
let aiJob=null,aiBusy=false;
let membership=await updateDesign('ai-membership-v1',refreshMembership,freshMembership());
let orderBook=await updateDesign('print-orders-v1',v=>v,freshOrders());
let checkoutDraft=await readDesign('checkout-draft');
let orderRows=[],orderPage=1,orderHasMore=false,orderError='';
try {
  const saved = JSON.parse(localStorage.getItem(KEY));
  if (saved) {
    if (designs.some(d=>d.id===saved.designId)) state.designId=saved.designId;
    if (phoneModels.includes(saved.model)) state.model=saved.model;
    if (stations.some(s=>s.id===saved.stationId)) state.stationId=saved.stationId;
    if(aiStyles.some(s=>s.id===saved.aiStyle))state.aiStyle=saved.aiStyle;
    state.aiExample=exampleFor(saved.aiExample).id;
    if(!exampleFor(state.aiExample).results[state.aiStyle])state.aiStyle=Object.keys(exampleFor(state.aiExample).results)[0];
    state.photoOrigin=aiExamples.some(e=>e.origin===saved.photoOrigin)?saved.photoOrigin:'upload';
    if(typeof saved.editOrderId==='string')state.editOrderId=saved.editOrderId;
    if(saved.ai&&/^[a-zA-Z0-9_-]{1,80}$/.test(saved.ai.styleId||''))state.ai=saved.ai;
    if(typeof saved.aiJobId==='string'){try{aiJob=await updateDesign('ai-job:'+saved.aiJobId,refreshAIOrder);state.aiJobId=aiJob.id;}catch{}
      if(membership.jobs[saved.aiJobId]){aiJob=membership.jobs[saved.aiJobId];state.aiJobId=aiJob.id;}}
    if(saved.artworkLayouts&&typeof saved.artworkLayouts==='object')for(const [id,layout] of Object.entries(saved.artworkLayouts)){
      try{const p=createPersonalPass({source:'collection',designId:id,model:phoneModels[0],effect:'original',intensity:0,zoom:layout.zoom,x:layout.x,y:layout.y,artworkEdits:layout.artworkEdits,addedArtwork:layout.addedArtwork});state.artworkLayouts[id]={zoom:p.zoom,x:p.x,y:p.y,artworkEdits:p.artworkEdits||{},addedArtwork:p.addedArtwork||[]};}catch{}
    }
    try{state.photoArtwork=validateAddedArtwork(saved.photoArtwork);if(saved.photoPlacement)state.photoPlacement=validatePlacement(saved.photoPlacement);}catch{}
    if (saved.source==='photo')state.source='photo';
    state.keepCollection=saved.keepCollection===true;
    if(effects.some(e=>e.id===saved.effect))state.effect=saved.effect;
    for(const [key,min,max] of [['intensity',0,100],['zoom',100,180],['x',0,100],['y',0,100]])if(Number.isFinite(saved[key]))state[key]=Math.max(min,Math.min(max,saved[key]));
    try{const photo=await readDesign('draft-photo');if(isPhoto(photo))state.photo=photo;}catch{}
    if (saved.pass) {try{state.pass=await resolvePass(saved.pass.code);}catch{}}
    if (saved.job && ['printing','ready','collected'].includes(saved.job.status) && stations.some(s=>s.id===saved.job.stationId)) {
      try{state.job={...saved.job,pass:await resolvePass(saved.job.pass.code)};}catch{}
    }
  }
} catch { /* Missing or invalid local data starts a fresh session. */ }
state.aiExample=exampleFor(state.aiExample).id;
if(!exampleFor(state.aiExample).results[state.aiStyle])state.aiStyle=Object.keys(exampleFor(state.aiExample).results)[0]||'';
membership=await updateDesign('ai-membership-v1',a=>migrateRender(a,aiJob),freshMembership());
if(aiJob)aiJob=membership.jobs[aiJob.id];
let scannedPass = null;
let noticeTimer;
let comparing=false,photoBusy=false,passBusy=false;
let effectPanelOpen=false,cropPanelOpen=false,selectedArtwork=null,libraryExpanded=false;
let modelBrand=phoneBrand(state.model||phoneModels[0]),modelQuery='';
let textDraft={font:'sans',color:'#242822'},inlineTextId=null;
function layoutSelection(value){
 if(value.source==='collection'&&value.artworkLayouts)return {...value,zoom:100,x:50,y:50,artworkEdits:{},addedArtwork:[],...value.artworkLayouts[value.designId]};
 if(value.source==='photo'&&value.artworkLayouts){
  const layout=value.artworkLayouts[value.designId]||{zoom:100,x:50,y:50,artworkEdits:{}};
  if(value.keepCollection&&!value.photo)return {...value,...layout,source:'collection',addedArtwork:value.photoArtwork||[]};
  return {...value,addedArtwork:value.photoArtwork||[],...(value.keepCollection?{collectionLayout:{zoom:layout.zoom,x:layout.x,y:layout.y,artworkEdits:layout.artworkEdits}}:{}),photoPlacement:value.photoPlacement||{x:50,y:50,scale:value.zoom,rotation:0}};
 }
 return value;
}
function artworkLayout(){return state.artworkLayouts[state.designId]??={zoom:100,x:50,y:50,artworkEdits:{},addedArtwork:[]};}
function extraArtwork(){return state.source==='photo'?state.photoArtwork:(artworkLayout().addedArtwork??=[]);}
function photoTarget(){return state.photoPlacement??={x:50,y:50,scale:state.zoom,rotation:0};}
function artworkTarget(){
 if(selectedArtwork==='photo')return photoTarget();
 const extra=extraArtwork().find(a=>a.id===selectedArtwork);if(extra)return extra;
 const layout=artworkLayout();if(selectedArtwork==='all')return layout;
 const layer=designFor(state.designId).layers.find(l=>l.id===selectedArtwork);
 if(!layer)return null;
 return layout.artworkEdits[layer.id]??={x:layer.x,y:layer.y,scale:100,rotation:layer.rotation};
}
function selectedText(){if(!selectedArtwork||selectedArtwork==='photo'||state.source==='photo'&&!state.photo&&!state.keepCollection)return null;return makePersonalDesign(layoutSelection(state)).layers.find(l=>l.id===selectedArtwork&&l.type==='text');}
function syncTextTools(canvas){
 const selected=selectedText();let tools=canvas.querySelector('.text-quick-tools');
 if(!selected){tools?.remove();return;}
 if(!tools||tools.dataset.forText!==selected.id){
  tools?.remove();tools=document.createElement('div');tools.className='text-quick-tools';tools.dataset.forText=selected.id;tools.setAttribute('role','group');tools.setAttribute('aria-label','Text style shortcuts');
  tools.innerHTML=`<span class="quick-label">Font</span><div class="quick-fonts">${[['sans','Modern'],['serif','Classic'],['hand','Handwritten'],['mono','Typewriter']].map(([font,name])=>`<button type="button" data-quick-font="${font}" aria-label="${name} font" title="${name}" style="font-family:${fonts[font]}">Aa</button>`).join('')}</div><span class="quick-label">Color</span><div class="quick-colors">${['#242822','#ffffff','#e44592','#146561','#f3c44d','#7964ac'].map((color,i)=>`<button type="button" data-quick-color="${color}" style="--color:${color}" aria-label="${['Charcoal','White','Pink','Teal','Gold','Purple'][i]} text" title="${['Charcoal','White','Pink','Teal','Gold','Purple'][i]}"></button>`).join('')}</div><label class="quick-custom">Custom<input type="color" data-text-field="color" aria-label="Custom text color"></label>`;
  canvas.append(tools);
 }
 for(const button of tools.querySelectorAll('[data-quick-font]'))button.setAttribute('aria-pressed',String(button.dataset.quickFont===selected.font));
 for(const button of tools.querySelectorAll('[data-quick-color]'))button.setAttribute('aria-pressed',String(button.dataset.quickColor===selected.color.toLowerCase()));
 const colorInput=tools.querySelector('input');if(document.activeElement!==colorInput)colorInput.value=selected.color;
 const phone=canvas.querySelector('.phone-case');tools.style.top=Math.max(0,Math.min(phone.clientHeight-tools.offsetHeight,phone.clientHeight*selected.y/100-tools.offsetHeight/2))+'px';
}
function writeInlineText(element){
 const selected=selectedText();if(!selected||selected.id!==inlineTextId)return;
 const text=element.innerText.replace(/\r/g,'').replace(/\u00a0/g,' ').slice(0,80);
 if(element.innerText.length>80){element.textContent=text;const range=document.createRange();range.selectNodeContents(element);range.collapse(false);getSelection().removeAllRanges();getSelection().addRange(range);}
 Object.assign(artworkTarget(),{text,font:selected.font,color:selected.color});save();
}
function finishInlineText(){
 if(!inlineTextId)return;
 const element=document.querySelector('[data-inline-text]');if(element)writeInlineText(element);
 inlineTextId=null;
 if(element){element.removeAttribute('contenteditable');element.removeAttribute('data-inline-text');element.removeAttribute('role');element.removeAttribute('aria-label');element.removeAttribute('aria-multiline');element.removeAttribute('tabindex');element.blur();}
 highlightArtwork();
}
function beginInlineText(selectAll=true){
 const selected=selectedText();if(!selected)return;
 if(inlineTextId&&inlineTextId!==selected.id)finishInlineText();
 inlineTextId=selected.id;
 const element=document.querySelector(`.artwork-canvas [data-layer-id="${selected.id}"] .layer-text`);
 element.setAttribute('contenteditable','plaintext-only');element.dataset.inlineText='true';element.setAttribute('role','textbox');element.setAttribute('aria-label','Edit text on case');element.setAttribute('aria-multiline','true');element.tabIndex=0;element.spellcheck=false;
 element.closest('.large-preview').scrollIntoView({block:'nearest'});element.focus({preventScroll:true});
 const range=document.createRange();range.selectNodeContents(element);if(!selectAll)range.collapse(false);getSelection().removeAllRanges();getSelection().addRange(range);highlightArtwork();
}
function applyTextStyle(field,value){
 const selected=selectedText();if(!selected)return;
 Object.assign(artworkTarget(),{text:selected.text,font:selected.font,color:selected.color,[field]:value});
 const element=document.querySelector(`.artwork-canvas [data-layer-id="${selected.id}"] .layer-text`);element.style[field==='font'?'fontFamily':'color']=field==='font'?fonts[value]:value;save();highlightArtwork();
}
function deleteSelectedArtwork(){
 if(!selectedArtwork||selectedArtwork==='photo'||selectedArtwork==='all'||artworkDrag||photoBusy||passBusy||aiBusy)return false;
 const id=selectedArtwork;
 if(!makePersonalDesign(layoutSelection(state)).layers.some(layer=>layer.id===id))return false;
 finishInlineText();
 if(id.startsWith('extra-')){
  // An overlay copied between the two sources is still the same user-created object.
  state.photoArtwork=state.photoArtwork.filter(item=>item.id!==id);
  const layout=artworkLayout();layout.addedArtwork=(layout.addedArtwork||[]).filter(item=>item.id!==id);
 }else artworkTarget().deleted=true;
 selectedArtwork=null;lastArtworkTap=null;save();updatePreview();notify('Artwork deleted.');return true;
}
function resetPresetLayer(id){const edits=artworkLayout().artworkEdits,edit=edits[id],base=designFor(state.designId).layers.find(l=>l.id===id);if(edit?.deleted)return;if(edit?.text!==undefined&&base)edits[id]={x:base.x,y:base.y,scale:100,rotation:base.rotation,text:edit.text,font:edit.font,color:edit.color};else delete edits[id];}
function revealArtwork(){if(window.innerWidth<=700)document.querySelector('.large-preview')?.scrollIntoView({behavior:'smooth',block:'center'});}
function setArtwork(key,value){artworkTarget()[key]=value;save();updatePreview();}
function creativeLibrary(){
 const disabled=state.source==='photo'&&!state.photo&&!state.keepCollection,items=[...stickers.slice(12),...stickers.slice(0,12)];
 return `<section class="graphic-library"><div class="library-title"><h2>Graphic library</h2><span>24 graphics</span></div><p>Little details. A little more you.</p><div class="graphic-grid">${items.slice(0,libraryExpanded?24:12).map(a=>`<button type="button" data-add-graphic="${a.id}" aria-label="Add ${esc(a.en)}" title="${esc(a.en)}" ${disabled?'disabled':''}>${imageTag(a.src,{alt:"",sizes:"64px"})}<span>${esc(a.en)}</span></button>`).join('')}</div><button class="text-button library-more" data-action="toggle-library">${libraryExpanded?'Show less':'View all 24 graphics'} ${libraryExpanded?'−':'+'}</button><p class="library-credit">Original POPOMO artwork + OpenMoji · CC BY-SA 4.0</p></section>
 <section class="text-editor"><h2>Your words</h2><p>Double-click text on your case to edit.<br>Choose fonts and colors right beside it.</p><button class="button text-add" data-action="text-submit" ${disabled?'disabled':''}>Add text ${icon('spark',16)}</button>${disabled?'<p class="field-note">Upload a photo to start adding graphics and text.</p>':''}</section>`;
}

async function rememberOrder(data){
 const previous=orderBook.orders[data.reference],order=savedOrder(data,previous);
 orderBook=await updateDesign('print-orders-v1',book=>{book.orders[order.id]=order;return book;},freshOrders());return order;
}
async function refreshOrder(id){return rememberOrder(await orderRequest(id+'/'));}
async function resolvePass(code){
 const key=String(code).trim().toUpperCase();orderBook=await readDesign('print-orders-v1')||freshOrders();let order=orderForCode(orderBook,key);
 if(order?.server)order=await refreshOrder(order.id);
 if(order)return currentOrder(orderBook,key).pass;
 return readPass(key,key.startsWith('POP-C-')?await readDesign(key):undefined);
}
async function orderAction(order,action,stationId){
 const data=await orderRequest(order.id+'/actions/',{method:'POST',body:{revision:order.revision,action,code:order.pass.code,...(stationId?{station_id:stationId}:{})}});
 return rememberOrder(data);
}
function qrSource(pass){
 if(pass.version!==2)return `./assets/passes/${pass.code}.svg`;
 const matrix=createQR(pass.code,{errorCorrectionLevel:'M'}).modules;let path='';
 for(let y=0;y<matrix.size;y++)for(let x=0;x<matrix.size;x++)if(matrix.get(y,x))path+=`M${x+4} ${y+4}h1v1h-1z`;
 const size=matrix.size+8;return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}"><path fill="white" d="M0 0h${size}v${size}H0z"/><path fill="#242822" d="${path}"/></svg>`);
}
function personalizedPreview(selection,model,label,original=false){
 return phone(makePersonalDesign(layoutSelection(selection),original),model).replace(/aria-label="[^"]*"/,`aria-label="${esc(label+' on '+model)}"`).replace('alt="你上传的设计照片"',`alt="Your uploaded photo"`);
}
const passName=p=>p.version===2?personalPassName(p,designs):currentDesign(p.designId).name;
const passPreview=p=>p.version===2?personalizedPreview(p,p.model,passName(p)):casePreview(p.designId,p.model);
const effectCaption=p=>p.source==='photo'&&p.ai?`<span class="effect-caption">✦ ${esc(aiStyles.find(s=>s.id===p.ai.styleId)?.name||'AI style')} · Demo sample</span>`:p.version===2&&p.effect!=='original'&&p.intensity>0?`<span class="effect-caption">${icon('spark',13)} ${effects.find(e=>e.id===p.effect).name} · AI effect preview</span>`:'';
function updatePreview(){finishInlineText();const el=document.querySelector('.large-case');if(el&&!(state.source==='photo'&&!state.photo&&!state.keepCollection))el.innerHTML=personalizedPreview(state,state.model||phoneModels[0],state.source==='photo'?'Your photo':currentDesign(state.designId).name,comparing);highlightArtwork();}
function highlightArtwork(){
 document.querySelector('.artwork-selection-actions')?.remove();
 const canvas=document.querySelector('.artwork-canvas');if(!canvas)return;
 const phone=canvas.querySelector('.phone-case');phone?.setAttribute('role','group');canvas.querySelector('.artwork-gizmo')?.remove();
 for(const layer of canvas.querySelectorAll('.design-layer')){layer.classList.remove('artwork-selected');layer.removeAttribute('aria-hidden');layer.setAttribute('role',layer.dataset.layerId===inlineTextId?'group':'button');layer.tabIndex=layer.dataset.layerId===inlineTextId?-1:0;layer.setAttribute('aria-label','Move '+(layer.textContent.trim()||'graphic'));layer.setAttribute('aria-pressed',String(layer.dataset.layerId===selectedArtwork));}
 canvas.classList.remove('whole-design-selected');
 const photo=canvas.querySelector('[data-photo-layer]');if(photo){photo.setAttribute('role','button');photo.tabIndex=0;photo.setAttribute('aria-label','Move your photo');photo.setAttribute('aria-pressed',String(selectedArtwork==='photo'));}
 syncTextTools(canvas);
 const caption=canvas.closest('.large-preview').querySelector('.preview-caption');
 caption.textContent=inlineTextId?'Type right here · Up to 80 characters · Tap outside to finish':selectedArtwork?'Drag to move · Corners to resize · ↻ to rotate · Tap outside to finish':'Tap artwork to adjust · Double-click text to edit';
 if(!selectedArtwork)return;
 const all=selectedArtwork==='all',isPhotoLayer=selectedArtwork==='photo',model=makePersonalDesign(layoutSelection(state)),layer=model.layers.find(l=>l.id===selectedArtwork),element=isPhotoLayer?photo:all?null:canvas.querySelector(`[data-layer-id="${selectedArtwork}"]`),layout=artworkLayout(),placement=isPhotoLayer?photoTarget():null;
 if(!all&&!element)return;
 if(layer){
  const actions=document.createElement('div');actions.className='artwork-selection-actions';
  actions.innerHTML=`<button type="button" data-action="delete-artwork" aria-label="Delete selected artwork" title="Delete selected artwork (Delete / Backspace)">${icon('trash',17)} Delete</button>`;
  canvas.closest('.large-preview').append(actions);
 }
 const visualScale=isPhotoLayer?Math.min(placement.scale,100)/100:1;
 const cx=phone.offsetLeft+phone.clientLeft+(isPhotoLayer?phone.clientWidth*placement.x/100:all?phone.clientWidth*layout.x/100:element.offsetLeft),cy=phone.offsetTop+phone.clientTop+(isPhotoLayer?phone.clientHeight*placement.y/100:all?phone.clientHeight*layout.y/100:element.offsetTop),width=isPhotoLayer?phone.clientWidth*visualScale:all?phone.clientWidth*layout.zoom/100:element.offsetWidth,height=isPhotoLayer?phone.clientHeight*visualScale:all?phone.clientHeight*layout.zoom/100:element.offsetHeight;
 const box=document.createElement('div');box.className='artwork-gizmo';box.style.cssText=`left:${cx}px;top:${cy}px;width:${width}px;height:${height}px;transform:translate(-50%,-50%) rotate(${isPhotoLayer?placement.rotation:all?0:layer.rotation}deg)`;
 box.innerHTML=`${['nw','ne','sw','se'].map(c=>`<button type="button" class="artwork-handle resize-${c}" data-transform="scale" aria-label="Resize artwork ${c}" title="Drag to resize"></button>`).join('')}<span class="rotation-stem" aria-hidden="true"></span><button type="button" class="artwork-handle rotate-handle" data-transform="rotate" aria-label="Rotate artwork" title="Drag to rotate">↻</button><button type="button" class="artwork-reset" data-action="reset-artwork" aria-label="Reset selected artwork" title="Reset selected artwork">↺</button>${layer?.type==='text'?`<button type="button" class="artwork-edit-text" data-action="edit-text" aria-label="${inlineTextId?'Finish editing text':'Edit text on case'}" title="${inlineTextId?'Done':'Edit text'}">${inlineTextId?'✓':'✎'}</button>`:''}`;
 canvas.append(box);
}
function refreshArtworkControls(){highlightArtwork();}
const arrow = () => icon('arrow',18);
const currentDesign = id => designs.find(d=>d.id===id) || designs[0];
const casePreview = (id,model='iPhone 16 Pro') => phone(designFor(id),model,'',{loading:'lazy',sizes:'(max-width: 700px) 100px, 180px'}).replace(/aria-label="[^"]*"/,`aria-label="${esc(currentDesign(id).name+' on '+model)}"`);
function save() {
  try {const ref=p=>p?.version===2?{code:p.code}:p;localStorage.setItem(KEY,JSON.stringify({...state,photo:undefined,pass:ref(state.pass),job:state.job?{...state.job,pass:ref(state.job.pass)}:null}));storageWarning=false;}
  catch {storageWarning=true;notify('Your browser could not save this pass. Download the QR code or write down the code.');}
}
function notify(message) {
  const el=document.querySelector('#notice');el.textContent=message;el.classList.add('visible');
  clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>el.classList.remove('visible'),5000);
}
function go(route) {if(location.hash==='#'+route)render();else location.hash=route;}
function header() {
  return `<header class="header wrap"><a class="wordmark" href="#home" aria-label="POPOMO home">${brandLogo()}</a><nav aria-label="Main navigation"><a href="#designs">The designs</a><a href="#orders">My orders</a></nav><a class="saved-link" href="#pass">${icon('scan',18)}<span>My design</span>${state.pass?'<i aria-label="Design saved"></i>':''}</a></header>${aiJob&&['queued','generating','ready'].includes(aiJob.status)&&state.ai?.jobId!==aiJob.id?`<div class="ai-resume wrap"><a href="#ai">✦ AI studio · ${aiJob.status==='ready'?'Your example is ready':aiJob.status==='queued'?'Waiting in queue':'Rendering'} <span>View render →</span></a></div>`:''}`;
}
function footer() {
  return `<footer class="footer wrap"><a href="#home" class="footer-wordmark">POPOMO<span> A little more you.</span></a><p>Prototype · Scanning & printing are simulated.</p><a href="#kiosk">Station demo ${arrow()}</a></footer>`;
}
function steps(active) {
  return `<ol class="steps" aria-label="Your design journey">${['Pick your design','Confirm & save','Scan & print'].map((label,i)=>`<li ${i===active?'aria-current="step"':''} class="${i===active?'active':i<active?'complete':''}"><span>${i<active?'✓':i+1}</span>${label}</li>`).join('')}</ol>`;
}
function home() {
  return `<section class="hero wrap"><div class="hero-copy"><p class="eyebrow">YOUR PHONE. YOUR LITTLE WORLD.</p><h1>A little more<br><em>you.</em></h1><p class="intro">Pick a design you love.<br>Bring it to life at a POPOMO station.</p><a class="button primary" href="#designs">Find your design ${arrow()}</a><a class="upload-home-link" href="#choose?source=photo">Or start with your own photo ${icon('upload',15)}</a><p class="hero-note">Choose online. Scan in store. Make it yours.<br>Standard printing ${PRINT_PRICE} per print.</p></div><div class="hero-scene" aria-label="Two colorful POPOMO phone case designs"><span class="scene-top">GOOD THINGS ARE PERSONAL.</span><div class="hero-case back-case">${casePreview('type')}</div><div class="hero-case front-case">${casePreview('bloom')}</div><span class="scene-star" aria-hidden="true">✳</span><span class="scene-bottom">DESIGNED TO GO WITH YOU.</span><span class="scene-number">01 — 06</span></div></section>
  <section class="collection wrap" id="designs"><div class="section-heading"><div><p class="eyebrow">THE SMALL, GOOD COLLECTION</p><h2>Find your kind of happy.</h2></div><p>Six designs. One that feels like you.</p></div><div class="design-grid">${designs.map((d,i)=>`<a class="design-card" href="#choose?design=${d.id}" aria-label="Choose ${d.name}"><div class="design-image" style="--card:${d.color}"><span class="card-index">0${i+1}</span><div class="card-case">${casePreview(d.id)}</div><span class="card-arrow">${arrow()}</span></div><div class="card-caption"><div><h3>${d.name}</h3><p>${d.category}</p></div></div></a>`).join('')}</div></section>
  <section class="how-section" id="how-it-works"><div class="wrap how-layout"><div><p class="eyebrow">FROM YOUR SCREEN TO YOUR HAND.</p><h2>Love it.<br>Scan it.<br>Keep it.</h2></div><ol class="how-list"><li><span>01</span><div><h3>Find your design.</h3><p>Choose your phone model first. Then pick a design or upload your photo, with optional AI effects.</p></div></li><li><span>02</span><div><h3>Keep your code.</h3><p>Preview your design, confirm your ${PRINT_PRICE} print order, then save the QR code.</p></div></li><li><span>03</span><div><h3>Make it real.</h3><p>Show your code to the station scanner. Confirm your prepaid design, then print and collect.</p></div></li></ol></div></section>`;
}
function modelResults(){
 const models=findPhoneModels(phoneModels,modelBrand,modelQuery);
 return `<p class="model-result-count" role="status">${models.length} ${models.length===1?'model':'models'} available</p><div class="model-options" role="group" aria-label="${esc(modelBrand)} models">${models.map(model=>`<button type="button" data-phone-model="${esc(model)}" aria-pressed="${model===state.model}"><span>${esc(model)}</span><span aria-hidden="true">${model===state.model?'✓':'→'}</span></button>`).join('')}</div>${models.length?'':'<p class="model-empty">No matching model. Try another search or brand.</p>'}`;
}
function modelPickerBody(){
 return `<div class="model-brand-section"><h2>1. Brand</h2><div class="model-brands" role="group" aria-label="Phone brand">${phoneBrands(phoneModels).map(brand=>`<button type="button" data-phone-brand="${esc(brand)}" aria-pressed="${brand===modelBrand}">${esc(brand)}</button>`).join('')}</div></div><div class="model-device-section"><label for="model-search">2. Model</label><input id="model-search" type="search" placeholder="Search ${esc(modelBrand)} models" aria-label="Search phone models" aria-describedby="model-first-note" autocomplete="off" value="${esc(modelQuery)}"><div class="model-results">${modelResults()}</div><p id="model-first-note">Choose the exact model in your phone’s settings. Pro and standard cases fit differently.</p></div>`;
}
function phonePicker(){
 modelBrand=phoneBrand(state.model||phoneModels[0]);modelQuery='';
 return `<details class="model-first" ${state.model?'':'open'}><summary><span class="model-summary-label">${state.model?'Your phone':'First, choose your phone'}</span><strong class="model-summary-value">${esc(state.model||'')}</strong><span class="model-summary-action">${state.model?'Change':'Choose'}</span><span class="model-summary-chevron" aria-hidden="true">⌄</span></summary><div class="model-first-body">${modelPickerBody()}</div></details>`;
}
function selectPhoneModel(model){
 if(!phoneModels.includes(model))return;
 state.model=model;modelBrand=phoneBrand(model);modelQuery='';save();updatePreview();
 const panel=document.querySelector('.model-first');
 panel.querySelector('.model-summary-label').textContent='Your phone';
 panel.querySelector('.model-summary-value').textContent=model;
 panel.querySelector('.model-summary-action').textContent='Change';
 panel.querySelector('.model-first-body').innerHTML=modelPickerBody();
 panel.open=false;panel.querySelector('summary').focus({preventScroll:true});
}
function choose() {
  const d=currentDesign(state.designId), own=state.source==='photo', hasPhoto=Boolean(state.photo);
  
  return `<section class="flow wrap">${steps(0)}${phonePicker()}<div class="choose-layout"><div class="large-preview" style="--card:${own?'#eeece7':d.color}"><span class="preview-label">${comparing?'ORIGINAL PREVIEW':'YOUR NEXT EVERYDAY FAVORITE'}</span>${own&&!hasPhoto&&!state.keepCollection?`<div class="photo-placeholder">${icon('image',48)}<h2>A moment.<br>Made yours.</h2><p>Your favorite photo, on your everyday case.</p><label class="button primary" for="photo-file">Upload a photo ${icon('upload',17)}</label></div>`:`<div class="large-case artwork-canvas">${personalizedPreview(state,state.model||phoneModels[0],own?'Your photo':d.name,comparing)}</div>`}<span class="preview-caption">${own?'Illustrative preview · Camera cutouts vary by model':'Tap a design element to edit'}</span></div><div class="choose-details"><a class="back-link" href="#designs">${icon('back',16)} All designs</a><div class="source-switch" role="group" aria-label="Design source"><button data-source="collection" aria-pressed="${!own}">The collection</button><button data-source="photo" aria-pressed="${own}">${icon('upload',15)} Your photo</button></div><h1>${own?'Make it personal.':d.name+'.'}</h1><p class="intro">${own?'Your memories. Your everyday favorite.':d.category}</p>${own?`<section class="photo-upload-prominent" aria-labelledby="upload-title"><div class="upload-heading"><span class="upload-icon" aria-hidden="true">${icon('upload',28)}</span><div><h2 id="upload-title">Upload your photo</h2><p>${own&&hasPhoto?'Photo added. Make it yours or try another.':'Turn a favorite memory into your next case.'}</p></div></div><button type="button" class="button upload-primary full" data-ai-action="upload" ${photoBusy?'disabled':''}>${icon('upload',20)} ${photoBusy?'Reading your photo…':own&&hasPhoto?'Replace photo':'Choose a photo'} <span aria-hidden="true">↗</span></button><p class="upload-formats">JPG, PNG or WebP · Up to 10 MB<br>Your photo stays here until you confirm an order.</p></section>`:''}<div class="print-price-card" aria-label="Printing price"><div><span>Standard printing</span><strong>${PRINT_PRICE}<small> / print</small></strong></div><p>${own?'Your photo, printed your way.':'Choose a design from the collection.'}</p>${own?`<p class="print-price-extra">${trialOffer()}.<br>Optional AI plan: <b>${planSummary()}</b>.<br>Printing is billed separately.</p>`:''}</div>${own?`<input class="file-input" type="file" id="photo-file" accept="image/jpeg,image/png,image/webp" aria-label="Upload your photo" ${photoBusy?'disabled':''}>`:''}${own?'':`<fieldset class="design-choices visual-design-choices"><legend>Pick a design</legend>${designs.map(item=>`<button type="button" data-design="${item.id}" class="design-thumbnail ${d.id===item.id?'selected':''}" aria-label="${item.name}" aria-pressed="${d.id===item.id}" style="--swatch:${designFor(item.id).background}"><span class="design-thumbnail-case">${casePreview(item.id,state.model||phoneModels[0])}</span><span class="design-thumbnail-check" aria-hidden="true">${d.id===item.id?'✓':''}</span></button>`).join('')}</fieldset>`}
  ${creativeLibrary()}${own?stylePanel(state,aiJob,effectPanelOpen,membership):''}${state.source==='photo'&&state.ai?'<p class="effect-selection">✓ AI sample applied · Original photo can be replaced above.</p>':''}
  <form id="design-form"><button class="button primary full" type="submit" ${photoBusy||passBusy||own&&!hasPhoto||!PRINT_AVAILABLE&&!state.editOrderId?'disabled':''}>${passBusy?'Saving your design…':state.editOrderId?'Review updated design':`Review ${PRINT_PRICE} print order`} ${arrow()}</button></form><div class="next-note">${icon('scan',23)}<p>Preview first. Confirm your order. Then scan in store.<br><span>Printing ${PRINT_PRICE} per print${own?' · AI is optional.':'.'}</span></p></div></div></div></section>`;
}
function passPage() {
  const pass=state.pass;
  if(!pass)return `<section class="empty wrap"><span class="empty-icon">${icon('scan',36)}</span><p class="eyebrow">YOUR NEXT FAVORITE IS WAITING.</p><h1>Make it yours.</h1><p>Pick a design and phone model to get your code.</p><a class="button primary" href="#designs">Explore the designs ${arrow()}</a></section>`;
  const d=currentDesign(pass.designId),qr=qrSource(pass),order=orderForCode(orderBook,pass.code);
  const editable=!order||order.status==='paid';
 const price=order?money(order.priceCents):PRINT_PRICE;
  return `<section class="flow wrap">${steps(1)}<div class="pass-heading"><p class="eyebrow">A LITTLE SOMETHING TO LOOK FORWARD TO.</p><h1>You picked a good one.</h1><p>${order?`Your ${price} test order is ${orderStatus(order.status).toLowerCase()}.`:'Your design is saved. Confirm a print order before printing.'} Bring this code to a POPOMO station.</p></div><div class="pass-card"><div class="pass-product" style="--card:${d.color}"><div class="pass-case">${passPreview(pass)}</div><h2>${passName(pass)}</h2><p>${esc(pass.model)}</p>${effectCaption(pass)}</div><div class="pass-code"><span class="eyebrow">YOUR DESIGN PASS</span><p class="pass-print-price">${order?'Test order · '+esc(orderStatus(order.status)):'Printing'} <strong>${price}</strong><br>${order?.status==='cancelled'?'This order cannot be printed.':order?'No real payment was taken.':'Confirm an order before printing.'}</p><img class="qr" src="${qr}" alt="Scannable design QR code: ${pass.code}" width="208" height="208"><strong class="human-code">${pass.code}</strong><p>${order?.server?'Design saved with your order.<br>Use the station demo in this browser.':pass.version===2?'Custom design saved locally.<br>Use this code in the station demo in this browser.':'Show this QR code to the station scanner.<br>You can also enter the code on its screen.'}</p><a class="button primary full" href="${qr}" download="${pass.code}.svg">${icon('box',18)} Save QR code</a><button class="text-button" data-action="copy-code">Copy design code</button></div></div><p class="saved-note">${storageWarning?'This pass could not be saved in this browser. Save the QR code before leaving.':'Saved in this browser. You can return through “My design.”'}</p>${order?.server?`<p class="order-reference">Order ${esc(order.id)} · Revision ${order.revision}<br><a href="#orders">View all my orders →</a></p>`:''}<div class="pass-actions"><a class="back-link" href="#choose" data-action="edit-pass">${icon('back',16)} ${editable?'Edit design before printing':'Use design for a new order'}</a><a class="text-button" href="#kiosk?code=${pass.code}">Try the station demo ${arrow()}</a></div>${order?.server&&editable?'<button class="text-button cancel-order" data-action="cancel-order">Cancel test order</button>':''}<p class="demo-note">${order?(editable?'You can edit until printing starts. Saving changes replaces this QR code; the old code stops working.<br>':'This print is locked. Changes require a new order.<br>'):''}${order?.server?'Order and design are saved on the server. Access belongs to this browser; keep its site data. Payments and station printing are simulated.':pass.version===2?'Photo and effect passes are browser-local in this prototype. Real stations will need a connected design service.':'Prototype: this code contains your preset and phone model. It is not a paid order or a reservation.'}</p></section>`;
}
function kioskPage() {
  const job=state.job;
  if(job && ['printing','ready','collected'].includes(job.status))return printPage(job);
  const p=scannedPass;
  const availability=p?stationAvailability(state.stationId,p):null;
  const order=p?orderForCode(orderBook,p.code):null,paid=order?.status==='paid'&&order.pass.code===p?.code;
 const price=order?money(order.priceCents):PRINT_PRICE;
  return `<section class="flow wrap station-flow">${steps(2)}<div class="station-top"><span class="station-dot"></span> POPOMO STATION <span class="demo-badge">DEMO</span></div><h1>${p?'Looks like you.':'Hello, good taste.'}</h1><p class="intro">${p?'Confirm your design and phone model before printing.':'Scan your design pass at the machine to get started.'}</p><div class="station-card">${p?`<div class="station-review"><div class="station-case">${passPreview(p)}</div><div><p class="eyebrow">DESIGN RECOGNIZED</p><h2>${passName(p)}</h2><p>${esc(p.model)}</p>${effectCaption(p)}<span class="human-code">${p.code}</span></div></div>`:`<div class="scanner-icon">${icon('scan',58)}</div><form id="scan-form"><label for="design-code">Enter your design code</label><div class="scan-input"><input id="design-code" name="code" placeholder="POP-1117" maxlength="32" required autocomplete="off" autocapitalize="characters" aria-describedby="scan-error"><button class="button primary" type="submit">Find design ${arrow()}</button></div><p id="scan-error" class="error" role="alert"></p></form>${state.pass?'<button class="text-button" data-action="scan-saved">Simulate scanning my saved pass</button>':''}`}
  <label class="station-label" for="station">Demo machine</label><select id="station">${stations.map(s=>`<option value="${s.id}" ${s.id===state.stationId?'selected':''}>${s.name}</option>`).join('')}</select>${p?`<p class="availability ${availability.ok?'available':'unavailable'}" role="status">${icon(availability.ok?'check':'clock',17)} ${availability.message}</p><div class="price-row station-print-price"><span>${paid?'Print order · Demo paid':'Standard printing'}</span><strong>${price}</strong></div><p class="field-note">${paid?'Already paid in the demo order. No second print charge.':'Confirm a print order before starting.'}</p><button class="button primary full" data-action="start-print" ${availability.ok&&paid?'':'disabled'}>Start prepaid demo print ${arrow()}</button>${!paid?'<a class="text-button" href="#choose">Review a new print order →</a>':''}<button class="text-button" data-action="rescan">Use a different code</button>`:''}</div><p class="demo-note">Station preview · No camera or printer is connected.<br>Printing and collection below are simulated.</p></section>`;
}
function printPage(job) {
  const status=job.status;
  const d=currentDesign(job.pass.designId);
  const titles={printing:'A little magic in progress.',ready:'Your case is ready.',collected:'Go make it your everyday.'};
  return `<section class="flow wrap station-flow">${steps(2)}<div class="station-top">POPOMO STATION <span class="demo-badge">DEMO</span></div><div class="completion-icon ${status==='printing'?'working':''}">${icon(status==='printing'?'spark':'check',32)}</div><h1>${titles[status]}</h1><p class="intro">${status==='printing'?'Your design is making itself at home.':status==='ready'?'Take your new case from the collection tray.':'A small thing. A little more you.'}</p><div class="print-summary"><div class="station-case">${passPreview(job.pass)}</div><h2>${passName(job.pass)}</h2>${effectCaption(job.pass)}<p>${esc(job.pass.model)} · ${esc(job.stationId)}</p><ol class="print-progress">${['Design confirmed','Printing','Ready to collect'].map((label,i)=>`<li class="${i<=(status==='printing'?1:2)?'done':''}"><span>${icon('check',14)}</span>${label}</li>`).join('')}</ol>${status==='collected'?'<button class="button primary full" data-action="finish-session">Back to the designs '+arrow()+'</button>':`<button class="button primary full" data-action="advance-print">${status==='printing'?'Finish demo print':'I’ve collected my case'} ${arrow()}</button>`}</div><p class="demo-note">Demo only · No physical item has been printed.</p></section>`;
}
function orderStatus(status){return ({paid:'Confirmed',printing:'Printing',ready:'Ready to collect',completed:'Collected',collected:'Collected',cancelled:'Cancelled'})[status]||status;}
function ordersPage(){return `<section class="flow wrap"><div class="ai-heading"><p class="eyebrow">YOUR DESIGNS, ALL TOGETHER.</p><h1>My orders.</h1><p>Your test orders are saved on the server and accessible from this browser.</p></div><button class="text-button" data-action="refresh-orders">Refresh orders ↻</button>${orderError?`<p class="error" role="alert">${esc(orderError)}</p>`:orderRows.length?`<div class="order-list">${orderRows.map(o=>`<article class="order-row"><div><span class="eyebrow">${esc(orderStatus(o.status))} · TEST PAYMENT</span><h2>${esc(o.model_name)}</h2><p>${esc(o.reference)}</p><small>${new Date(o.created_at).toLocaleString()}</small></div><div><strong>${esc(o.currency)} ${Number(o.amount).toFixed(2)}</strong><button class="button secondary" data-action="view-order" data-id="${esc(o.reference)}">View design →</button></div></article>`).join('')}</div><div class="pass-actions">${orderPage>1?`<button class="text-button" data-action="orders-page" data-page="${orderPage-1}">← Previous</button>`:''}${orderHasMore?`<button class="text-button" data-action="orders-page" data-page="${orderPage+1}">Next →</button>`:''}</div>`:'<div class="empty"><h2>Your first design is waiting.</h2><p>Confirm a print order to see it here.</p><a class="button primary" href="#choose">Create a design →</a></div>'}<p class="demo-note">Test payments do not charge money. Keep this browser’s site data to retain access to your orders.</p></section>`;}
function checkoutPage(){
 if(!checkoutDraft)return '<section class="empty wrap"><h1>Choose your design first.</h1><a class="button primary" href="#choose">Back to your design</a></section>';
 const {pass,editId}=checkoutDraft,order=editId?orderBook.orders[editId]:null,locked=editId&&order?.status!=='paid';
 const price=order?money(order.priceCents):PRINT_PRICE;
 return `<section class="flow wrap"><a class="back-link" href="#choose">← Keep editing</a><div class="ai-heading"><p class="eyebrow">REVIEW YOUR PRINT · DEMO</p><h1>${editId?'Make it just right.':'Happy with your design?'}</h1><p>Check your artwork and phone model before confirming.</p></div><div class="ai-order-layout"><div class="checkout-preview"><div class="checkout-case">${passPreview(pass)}</div><h2>${passName(pass)}</h2><p>${esc(pass.model)}</p>${effectCaption(pass)}</div><div class="ai-order-card"><div class="price-row"><span>One standard print</span><strong>${price}</strong></div><div class="price-row"><span>${editId?'Already paid · Demo':'Due now · Demo'}</span><strong>${price}</strong></div>${editId?'<div class="price-row"><span>Design update</span><strong>$0.00</strong></div>':''}<p class="ai-demo-note">AI membership is separate. ${trialOffer()}. ${planSummary()}. Printing is not included.</p><p class="field-note">You can edit your design until printing starts. Saving a revision replaces the QR code. After printing starts, changes need a new order.</p>${!PRINT_AVAILABLE&&!editId?'<p class="error">Printing is unavailable. Please reload and try again.</p>':locked?'<p class="error">This order has started printing. Return to My design to create a new order.</p>':`<form id="print-checkout-form">${!editId?'<label class="order-email">Email (optional)<input name="email" type="email" maxlength="254" autocomplete="email" placeholder="you@example.com"><small>Saved with your order for support. No email will be sent.</small></label>':''}<label class="ai-consent"><input name="accepted" type="checkbox" required><span>I confirm this design and phone model. ${editId?'Replace my existing design and QR code at no extra printing charge.':`Simulate a ${price} payment for one print.`} No real charge. The design and any photo will be securely saved with this order.</span></label><button class="button primary full">${editId?'Save changes & replace QR code':`Pay ${price} & get my code · Demo`}</button></form>`}</div></div></section>`;
}
function render(preserveScroll=false) {
  finishInlineText();
  const oldY=window.scrollY;
  const [route='home',query='']=location.hash.slice(1).split('?');
  const pages={choose,pass:passPage,kiosk:kioskPage,ai:()=>aiPage(aiJob,membership),membership:()=>membershipPage(membership),checkout:checkoutPage,orders:ordersPage};
  app.innerHTML=header()+`<main id="main" tabindex="-1">${catalogStatus==='unavailable'?'<div class="catalog-warning" role="status">Prices and AI previews could not be loaded. Your saved designs are still available. <button class="text-button" data-action="reload-catalog">Try again</button></div>':''}${(Object.hasOwn(pages,route)?pages[route]:home)()}</main>`+footer();
  if(aiBusy)document.querySelectorAll('[data-ai-action],#ai-credit-form button,#ai-subscription-form button').forEach(el=>el.disabled=true);
  const title=({choose:'Choose your case',pass:'Your design pass',kiosk:'Station demo',ai:'Your AI render',membership:'AI membership',checkout:'Review print order',orders:'My orders'})[route];
  document.title=title?`${title} · POPOMO`:'POPOMO — A little more you.';
  document.querySelector('.ai-studio-card')?.addEventListener('toggle',e=>{if(e.target.isConnected)effectPanelOpen=e.target.open;});
  highlightArtwork();
  document.querySelector('.crop-panel')?.addEventListener('toggle',e=>cropPanelOpen=e.target.open);
  if(preserveScroll)window.scrollTo(0,oldY);
  else if(['designs','how-it-works'].includes(route))document.getElementById(route)?.scrollIntoView();
  else window.scrollTo(0,0);
}
// A stable outer canvas retains capture while the selected artwork and handles update.
let artworkDrag=null,lastArtworkTap=null;
function deselectArtwork(){
 finishInlineText();
 if(!selectedArtwork)return;
 selectedArtwork=null;
 if(document.activeElement?.closest('.artwork-canvas'))document.activeElement.blur();
 highlightArtwork();
}
document.addEventListener('pointerdown',event=>{
 if(event.isPrimary===false||event.button!==0||artworkDrag)return;
 if(!event.target.closest('.artwork-canvas [data-layer-id],.artwork-canvas [data-photo-layer],.artwork-gizmo,.text-quick-tools,.artwork-selection-actions'))deselectArtwork();
});
document.addEventListener('keydown',event=>{
 if(['Delete','Backspace'].includes(event.key)&&!event.isComposing&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.target.closest('input,textarea,select,[contenteditable],[role="textbox"]')){
  if(deleteSelectedArtwork())event.preventDefault();
 }
 if(event.key==='Escape'&&!artworkDrag&&!event.isComposing){event.preventDefault();finishInlineText();deselectArtwork();}
});
app.addEventListener('pointerdown',event=>{
 const canvas=event.target.closest('.artwork-canvas');
 if(!canvas||event.button!==0||event.isPrimary===false||event.target.closest('.camera,.artwork-reset,.artwork-delete,.artwork-edit-text,.text-quick-tools,[data-inline-text]')||artworkDrag)return;
 const handle=event.target.closest('[data-transform]'),layer=event.target.closest('[data-layer-id],[data-photo-layer]');
 if(!handle&&!layer)return;
 finishInlineText();
 if(!handle)selectedArtwork=layer.dataset.photoLayer?'photo':layer.dataset.layerId;
 if(document.activeElement?.closest('.text-editor'))document.activeElement.blur();
 highlightArtwork();
 const target=artworkTarget(),phone=canvas.querySelector('.phone-case'),box=canvas.querySelector('.artwork-gizmo').getBoundingClientRect(),cx=box.x+box.width/2,cy=box.y+box.height/2;
 artworkDrag={mode:handle?.dataset.transform||'move',pointerId:event.pointerId,canvas,startX:event.clientX,startY:event.clientY,x:target.x,y:target.y,width:phone.clientWidth,height:phone.clientHeight,groupScale:selectedArtwork==='all'||selectedArtwork==='photo'||selectedArtwork.startsWith('extra-')?1:artworkLayout().zoom/100,cx,cy,startDistance:Math.max(1,Math.hypot(event.clientX-cx,event.clientY-cy)),startAngle:Math.atan2(event.clientY-cy,event.clientX-cx),scale:selectedArtwork==='all'?target.zoom:target.scale,rotation:target.rotation||0,snapshot:structuredClone(artworkLayout()),photoSnapshot:structuredClone({photoPlacement:state.photoPlacement,photoArtwork:state.photoArtwork})};
 canvas.setPointerCapture(event.pointerId);canvas.classList.add('is-dragging');event.preventDefault();
});
app.addEventListener('pointermove',event=>{
 const drag=artworkDrag;if(!drag||event.pointerId!==drag.pointerId)return;
 if(!drag.moved&&Math.hypot(event.clientX-drag.startX,event.clientY-drag.startY)<4)return;
 drag.moved=true;lastArtworkTap=null;
 const target=artworkTarget(),all=selectedArtwork==='all';
 if(drag.mode==='move')Object.assign(target,dragPlacement({x:drag.x,y:drag.y,dx:event.clientX-drag.startX,dy:event.clientY-drag.startY,width:drag.width,height:drag.height,groupScale:drag.groupScale}));
 if(drag.mode==='scale')target[all?'zoom':'scale']=scaleFromPointer({scale:drag.scale,startDistance:drag.startDistance,distance:Math.hypot(event.clientX-drag.cx,event.clientY-drag.cy),min:all?50:25,max:all?180:200});
 if(drag.mode==='rotate'){
  const angle=Math.atan2(event.clientY-drag.cy,event.clientX-drag.cx);
  if(all)artworkLayout().artworkEdits=rotateGroup(drag.snapshot.artworkEdits,designFor(state.designId).layers,rotationFromPointer({startAngle:drag.startAngle,angle}),drag.width/drag.height);
  else target.rotation=rotationFromPointer({rotation:drag.rotation,startAngle:drag.startAngle,angle});
 }
 updatePreview();event.preventDefault();
});
function finishArtworkDrag(event,cancelled=false){
 const drag=artworkDrag;if(!drag||event.pointerId!==drag.pointerId)return;
 if(cancelled){state.artworkLayouts[state.designId]=drag.snapshot;Object.assign(state,drag.photoSnapshot);updatePreview();}
 artworkDrag=null;drag.canvas.classList.remove('is-dragging');if(drag.canvas.hasPointerCapture(event.pointerId))drag.canvas.releasePointerCapture(event.pointerId);save();
 // Pointer capture retargets native clicks to the canvas, so recognize a text double-tap here.
 if(!cancelled&&!drag.moved&&drag.mode==='move'&&selectedText()){
  const tap={id:selectedArtwork,time:event.timeStamp,x:drag.startX,y:drag.startY};
  if(lastArtworkTap?.id===tap.id&&tap.time-lastArtworkTap.time<450&&Math.hypot(tap.x-lastArtworkTap.x,tap.y-lastArtworkTap.y)<12){lastArtworkTap=null;beginInlineText();}
  else lastArtworkTap=tap;
 }else lastArtworkTap=null;
}
app.addEventListener('pointerup',event=>finishArtworkDrag(event));
app.addEventListener('pointercancel',event=>finishArtworkDrag(event,true));
app.addEventListener('lostpointercapture',event=>finishArtworkDrag(event,true));
app.addEventListener('dblclick',event=>{
 if(event.target.closest('[data-inline-text]'))return;
 const layer=event.target.closest('.artwork-canvas [data-layer-id]');if(!layer?.querySelector('.layer-text'))return;
 event.preventDefault();finishInlineText();selectedArtwork=layer.dataset.layerId;beginInlineText();
});
app.addEventListener('compositionend',event=>{if(event.target.matches('[data-inline-text]')){writeInlineText(event.target);highlightArtwork();}});
app.addEventListener('keydown',event=>{
 if(event.target.closest('[data-inline-text]')){
  if((event.ctrlKey||event.metaKey)&&event.key==='Enter'&&!event.isComposing){event.preventDefault();finishInlineText();}
  return;
 }
 const canvas=event.target.closest('.artwork-canvas'),layer=event.target.closest('[data-layer-id],[data-photo-layer]'),handle=event.target.closest('[data-transform]'),delta={ArrowLeft:['x',-1],ArrowRight:['x',1],ArrowUp:['y',-1],ArrowDown:['y',1]}[event.key];
 if(!canvas)return;
 if(layer&&['Enter',' '].includes(event.key)){event.preventDefault();selectedArtwork=layer.dataset.photoLayer?'photo':layer.dataset.layerId;if(selectedText())beginInlineText();else highlightArtwork();return;}
 if(!delta||(!layer&&!handle))return;event.preventDefault();if(layer)selectedArtwork=layer.dataset.photoLayer?'photo':layer.dataset.layerId;
 const target=artworkTarget(),all=selectedArtwork==='all',amount=delta[1]*(event.shiftKey?5:1);
 if(handle?.dataset.transform==='scale'){const key=all?'zoom':'scale';target[key]=Math.max(all?50:25,Math.min(all?180:200,target[key]+amount));}
 else if(handle?.dataset.transform==='rotate'){if(all)target.artworkEdits=rotateGroup(target.artworkEdits,designFor(state.designId).layers,amount,canvas.querySelector('.phone-case').clientWidth/canvas.querySelector('.phone-case').clientHeight);else target.rotation=rotationFromPointer({rotation:target.rotation,startAngle:0,angle:amount*Math.PI/180});}
 else target[delta[0]]=Math.max(0,Math.min(100,target[delta[0]]+amount));
 const selector=handle?'.'+[...handle.classList].find(c=>c!=='artwork-handle'):(selectedArtwork==='photo'?'[data-photo-layer]':`[data-layer-id="${selectedArtwork}"]`);save();updatePreview();canvas.querySelector(selector)?.focus({preventScroll:true});
});
app.addEventListener('change',async event=>{
  if(event.target.id==='station'){state.stationId=event.target.value;save();render(true);document.querySelector('#station')?.focus({preventScroll:true});}
  if(event.target.id==='photo-file'){
    const file=event.target.files[0];if(!file||photoBusy)return;
    photoBusy=true;render(true);
    try{const photo=await importPhoto(file);await writeDesign('draft-photo',photo);state.photo=photo;state.photoOrigin='upload';state.ai=null;state.effect='original';state.source='photo';state.zoom=100;state.x=50;state.y=50;state.photoPlacement=null;selectedArtwork='photo';comparing=false;save();notify('Photo added. Drag to move, or use the corners to resize.');}
    catch(error){notify(error.message||'Your photo could not be saved. Try a smaller image.');}
    finally{photoBusy=false;render(true);}
  }
});
app.addEventListener('input',event=>{
 if(event.target.id==='model-search'){modelQuery=event.target.value;document.querySelector('.model-results').innerHTML=modelResults();return;}
 if(event.target.matches('[data-inline-text]')){if(!event.isComposing){writeInlineText(event.target);highlightArtwork();}return;}
 if(event.target.dataset.textField){applyTextStyle(event.target.dataset.textField,event.target.value);return;}

  if(event.target.dataset.artwork){const key=event.target.dataset.artwork;setArtwork(key,Number(event.target.value));}
  if(event.target.dataset.crop){const key=event.target.dataset.crop;state[key]=Number(event.target.value);document.getElementById(key+'-value').textContent=state[key]+'%';updatePreview();save();}
  if(event.target.id==='effect-strength'){state.intensity=Number(event.target.value);document.getElementById('intensity-value').textContent=state.intensity+'%';document.getElementById('selected-strength').textContent=state.intensity+'%';updatePreview();save();}
  if(event.target.id==='design-code'){event.target.removeAttribute('aria-invalid');document.getElementById('scan-error').textContent='';}
});
app.addEventListener('submit',async event=>{
  if(event.target.id==='ai-credit-form'||event.target.id==='ai-subscription-form'){
    event.preventDefault();if(aiBusy)return;const accepted=new FormData(event.target).has('accepted');
    await changeMembership(a=>event.target.id==='ai-credit-form'?startRender(a,aiJob.id,{accepted}):subscribe(a,{accepted}));return;
  }
  if(event.target.id==='print-checkout-form'){event.preventDefault();if(passBusy||!checkoutDraft)return;passBusy=true;
    const button=event.target.querySelector('button');button.disabled=true;button.textContent='Saving your order…';
    try{
      const values=new FormData(event.target),accepted=values.has('accepted'),existing=orderBook.orders[checkoutDraft.editId];let order;
      if(checkoutDraft.editId&&!existing)throw Error('This order could not be loaded. Open it from My orders and retry.');
      if(existing&&!existing.server){let result;orderBook=await updateDesign('print-orders-v1',b=>{result=commitPrintOrder(b,checkoutDraft.pass,{accepted,editId:existing.id});return result.book;},freshOrders());order=result.order;}
      else{
        checkoutDraft.requestKey||=crypto.randomUUID();await writeDesign('checkout-draft',checkoutDraft);
        const data=existing?await orderRequest(existing.id+'/',{method:'PATCH',body:{accepted,revision:checkoutDraft.revision??existing.revision,snapshot:checkoutDraft.pass}}):await orderRequest('',{method:'POST',body:checkoutBody(checkoutDraft,{accepted,email:String(values.get('email')||''),amount:(PRINT_PRICE_CENTS/100).toFixed(2)})});
        order=await rememberOrder(data);
      }
      state.pass=order.pass;state.job=null;scannedPass=null;state.editOrderId=null;checkoutDraft=null;await writeDesign('checkout-draft',null);save();go('pass');
    }
    catch(error){notify(error.message);}finally{passBusy=false;render(true);}return;
  }
  if(event.target.id==='design-form'){
    event.preventDefault();if(passBusy||photoBusy)return;
    if(!phoneModels.includes(state.model)){const panel=document.querySelector('.model-first');panel.open=true;panel.scrollIntoView({block:'start',behavior:'smooth'});panel.querySelector('#model-search').focus({preventScroll:true});notify('Choose your phone model first.');return;}
    const submitted={...state};passBusy=true;render(true);
    try{
      const pass=createPersonalPass(layoutSelection(submitted));
      checkoutDraft={pass,editId:state.editOrderId||null,requestKey:crypto.randomUUID(),revision:orderBook.orders[state.editOrderId]?.revision};await writeDesign('checkout-draft',checkoutDraft);comparing=false;go('checkout');
    }catch(error){notify(error.message||'The design could not be saved. Please try again.');}
    finally{passBusy=false;if(location.hash.startsWith('#choose'))render(true);}
  }
  if(event.target.id==='scan-form'){
    event.preventDefault();
    try{scannedPass=await resolvePass(new FormData(event.target).get('code'));render(true);}
    catch(error){const el=document.querySelector('#scan-error');if(el){el.textContent=error.message;document.querySelector('#design-code').setAttribute('aria-invalid','true');}}
  }
});
app.addEventListener('click',async event=>{
  const el=event.target.closest('[data-phone-brand],[data-phone-model],[data-action],[data-design],[data-source],[data-effect],[data-ai-action],[data-ai-style],[data-ai-example],[data-artwork-item],[data-add-graphic],[data-quick-font],[data-quick-color]');if(!el||el.disabled||photoBusy||passBusy||aiBusy)return;
  if(el.dataset.action==='reload-catalog'){location.reload();return;}
  if(el.dataset.phoneBrand){
   if(!phoneBrands(phoneModels).includes(el.dataset.phoneBrand))return;
   modelBrand=el.dataset.phoneBrand;modelQuery='';document.querySelector('.model-first-body').innerHTML=modelPickerBody();
   document.querySelector(`[data-phone-brand="${modelBrand}"]`)?.focus({preventScroll:true});return;
  }
  if(el.dataset.phoneModel){selectPhoneModel(el.dataset.phoneModel);return;}
  if(el.dataset.quickFont){applyTextStyle('font',el.dataset.quickFont);return;}
  if(el.dataset.quickColor){applyTextStyle('color',el.dataset.quickColor);return;}
  if(el.dataset.addGraphic){
   if(extraArtwork().length>=20){notify('You can add up to 20 graphics and text elements.');return;}
   if(!stickers.some(a=>a.id===el.dataset.addGraphic)||state.source==='photo'&&!state.photo&&!state.keepCollection)return;
   finishInlineText();const item={id:'extra-'+crypto.randomUUID(),type:'sticker',asset:el.dataset.addGraphic,x:50,y:55,scale:100,rotation:0};extraArtwork().push(item);selectedArtwork=item.id;save();updatePreview();revealArtwork();return;
  }
  if(el.dataset.artworkItem){selectedArtwork=el.dataset.artworkItem;refreshArtworkControls();document.querySelector(`[data-artwork-item="${selectedArtwork}"]`)?.focus({preventScroll:true});return;}
  if(el.dataset.aiExample){const example=exampleFor(el.dataset.aiExample);state.aiExample=example.id;if(!example.results[state.aiStyle])state.aiStyle=Object.keys(example.results)[0];effectPanelOpen=true;save();render(true);document.querySelector(`[data-ai-example="${example.id}"]`)?.focus({preventScroll:true});return;}
  if(el.dataset.aiStyle){state.aiStyle=el.dataset.aiStyle;effectPanelOpen=true;save();render(true);document.querySelector(`[data-ai-style="${state.aiStyle}"]`)?.focus({preventScroll:true});return;}
  if(el.dataset.aiAction){await handleAI(el.dataset.aiAction);return;}
  if(el.dataset.source){
   finishInlineText();
   if(el.dataset.source==='photo'&&state.source==='collection'){
    try{const retained=collectionForPhoto(layoutSelection(state),state.photoArtwork);state.photoArtwork=retained.addedArtwork;state.keepCollection=true;}
    catch(error){notify(error.message);return;}
   }
   selectedArtwork=null;state.source=el.dataset.source;comparing=false;history.replaceState(null,'','#choose');save();render(true);return;
  }
  if(el.dataset.design){selectedArtwork='all';state.designId=el.dataset.design;state.source='collection';save();history.replaceState(null,'',`#choose?design=${state.designId}`);render(true);document.querySelector(`[data-design="${state.designId}"]`)?.focus({preventScroll:true});return;}
  if(el.dataset.effect){state.effect=el.dataset.effect;comparing=false;effectPanelOpen=true;save();render(true);document.querySelector(`[data-effect="${state.effect}"]`)?.focus({preventScroll:true});return;}
  try {
    if(el.dataset.action==='toggle-library'){libraryExpanded=!libraryExpanded;render(true);return;}
    if(el.dataset.action==='edit-text'){if(inlineTextId)finishInlineText();else beginInlineText();return;}
    if(el.dataset.action==='text-submit'){
     if(extraArtwork().length>=20){notify('You can add up to 20 graphics and text elements.');return;}
     finishInlineText();
     const item={id:'extra-'+crypto.randomUUID(),type:'text',...textDraft,text:'Your text',x:50,y:65,scale:100,rotation:0};extraArtwork().push(item);selectedArtwork=item.id;save();updatePreview();beginInlineText();return;
    }
    if(el.dataset.action==='delete-artwork'){deleteSelectedArtwork();return;}
    if(el.dataset.action==='reset-artwork'){
     if(selectedArtwork==='photo'){state.photoPlacement={x:50,y:50,scale:100,rotation:0};state.zoom=100;state.x=50;state.y=50;save();updatePreview();return;}
     if(selectedArtwork?.startsWith('extra-')){Object.assign(artworkTarget(),{x:50,y:55,scale:100,rotation:0});save();updatePreview();return;}
if(selectedArtwork==='all'){const layout=artworkLayout();layout.zoom=100;layout.x=50;layout.y=50;for(const id of Object.keys(layout.artworkEdits))resetPresetLayer(id);}else resetPresetLayer(selectedArtwork);save();updatePreview();refreshArtworkControls();}
    if(el.dataset.action==='center-artwork'){const target=artworkTarget();target.x=50;target.y=50;save();updatePreview();refreshArtworkControls();}
    if(el.dataset.action?.startsWith('nudge-')){const direction=el.dataset.action.slice(6),key=['left','right'].includes(direction)?'x':'y',delta=['left','up'].includes(direction)?-5:5,target=artworkTarget();setArtwork(key,Math.max(0,Math.min(100,target[key]+delta)));render(true);}
    if(el.dataset.action==='compare'){comparing=!comparing;render(true);document.querySelector('[data-action="compare"]')?.focus({preventScroll:true});}
    if(el.dataset.action==='reset-crop'){state.zoom=100;state.x=50;state.y=50;save();render(true);}
    if(el.dataset.action==='edit-pass'){
      event.preventDefault();const current=orderForCode(orderBook,state.pass.code);if(current?.server){const latest=await refreshOrder(current.id);state.pass=latest.pass;}const p=state.pass;orderBook=await readDesign('print-orders-v1')||freshOrders();const order=orderForCode(orderBook,p.code);selectedArtwork=null;if(p.source==='collection')state.artworkLayouts[p.designId]={zoom:p.zoom,x:p.x,y:p.y,artworkEdits:structuredClone(p.artworkEdits||{}),addedArtwork:structuredClone(p.addedArtwork||[])};state.editOrderId=order?.status==='paid'?order.id:null;
      if(p.version===2){if(p.source==='photo')await writeDesign('draft-photo',p.photo);Object.assign(state,{source:p.source,designId:p.designId,model:p.model,photo:p.source==='photo'?p.photo:state.photo,effect:p.effect,intensity:p.intensity,zoom:p.zoom,x:p.x,y:p.y,ai:p.ai||null,photoOrigin:'upload',...(p.source==='photo'?{photoArtwork:structuredClone(p.addedArtwork||[]),photoPlacement:structuredClone(p.photoPlacement||null),keepCollection:Boolean(p.collectionLayout)}:{})});}
      else Object.assign(state,{source:'collection',designId:p.designId,model:p.model,effect:'original'});
      if(p.source==='photo'&&p.collectionLayout)state.artworkLayouts[p.designId]={...structuredClone(p.collectionLayout),addedArtwork:structuredClone(p.addedArtwork||[])};
      comparing=false;save();go('choose');
    }
    if(el.dataset.action==='copy-code'){
      try{await navigator.clipboard.writeText(state.pass.code);notify('Design code copied.');}
      catch{notify('Your design code: '+state.pass.code);}
    }
    if(el.dataset.action==='scan-saved'){scannedPass=await resolvePass(state.pass.code);render();}
    if(el.dataset.action==='rescan'){scannedPass=null;render(true);}
    if(el.dataset.action==='start-print'){const order=orderForCode(orderBook,scannedPass.code);if(order?.server){const updated=await orderAction(order,'start',state.stationId);state.job={pass:updated.pass,stationId:updated.stationId,status:updated.status,orderId:updated.id};save();render();return;}let result;orderBook=await updateDesign('print-orders-v1',b=>{result=beginOrderPrint(b,scannedPass.code,state.stationId);return result.book;},freshOrders());state.job=result.job;save();render();}
    if(el.dataset.action==='advance-print'){const order=orderBook.orders[state.job?.orderId];if(order?.server){const updated=await orderAction(order,state.job.status==='printing'?'ready':'collect');state.job={pass:updated.pass,stationId:updated.stationId,status:updated.status,orderId:updated.id};save();render();return;}const job=advancePrint(state.job);if(job.orderId)orderBook=await updateDesign('print-orders-v1',b=>{b.orders[job.orderId].status=job.status;return b;});state.job=job;save();render();}
    if(el.dataset.action==='view-order'){const order=await refreshOrder(el.dataset.id);state.pass=order.pass;state.job=order.stationId&&['printing','ready','collected'].includes(order.status)?{pass:order.pass,stationId:order.stationId,status:order.status,orderId:order.id}:null;save();go('pass');}
    if(el.dataset.action==='cancel-order'){const order=orderForCode(orderBook,state.pass.code);if(order?.server){await orderAction(order,'cancel');notify('Test order cancelled. No money was charged.');render(true);}}
    if(el.dataset.action==='orders-page'){orderPage=Number(el.dataset.page);await navigate();}
    if(el.dataset.action==='refresh-orders')await navigate();
    if(el.dataset.action==='finish-session'){state.job=null;scannedPass=null;save();go('designs');}
  } catch(error){notify(error.message||'Your design could not be saved. Please try again.');}
});
document.querySelector('.skip-link').addEventListener('click',event=>{event.preventDefault();document.querySelector('#main')?.focus();});
async function navigate(){
 const [route,query='']=location.hash.slice(1).split('?');const params=new URLSearchParams(query),code=params.get('code');
 if(route==='pass'||route==='kiosk'){
   orderBook=await readDesign('print-orders-v1')||freshOrders();const order=state.pass&&orderForCode(orderBook,state.pass.code);
   if(order?.server)try{const latest=await refreshOrder(order.id);state.pass=latest.pass;if(state.job?.orderId===latest.id)state.job={...state.job,status:latest.status,pass:latest.pass};}catch(e){notify(e.message);}
 }
 if(route==='orders'){try{const data=await orderRequest('?page='+orderPage);orderRows=data.results;orderHasMore=data.has_more;orderError='';}catch(e){orderError=e.message;}}
 if(route==='choose'&&designs.some(d=>d.id===params.get('design'))){state.designId=params.get('design');state.source='collection';}
 if(route==='choose'&&params.get('source')==='photo')state.source='photo';
 if(route==='kiosk'&&code){try{scannedPass=await resolvePass(code);const order=orderForCode(orderBook,scannedPass.code);state.job=order?.stationId&&['printing','ready','collected'].includes(order.status)?{pass:order.pass,stationId:order.stationId,status:order.status,orderId:order.id}:null;save();}catch(error){scannedPass=null;notify(error.message);}history.replaceState(null,'','#kiosk');}
 render();document.querySelector('#main')?.focus({preventScroll:true});
}
window.addEventListener('hashchange',navigate);
window.addEventListener('resize',()=>{if(!artworkDrag)highlightArtwork();});
app.addEventListener('load',event=>{if(!artworkDrag&&event.target.closest?.('.artwork-canvas'))highlightArtwork();},true);
await navigate();

async function loadAssetPhoto(url){
 const response=await fetch(url);if(!response.ok)throw Error('The style sample could not be loaded. Please try again.');
 const blob=await response.blob();return importPhoto(new File([blob],'sample.png',{type:blob.type}));
}
async function changeMembership(transform){
 if(aiBusy)return;aiBusy=true;
 try{membership=await updateDesign('ai-membership-v1',transform,freshMembership());if(aiJob)aiJob=membership.jobs[aiJob.id];save();}
 catch(error){notify(error.message||'Your AI plan could not be saved.');}
 finally{aiBusy=false;render(true);}
}
async function newAI(input){
 let result;membership=await updateDesign('ai-membership-v1',a=>{result=addRender(a,input);return result.account;},freshMembership());aiJob=result.job;state.aiJobId=aiJob.id;save();go('ai');
}
async function handleAI(action){
 if(action==='upload'){document.querySelector('#photo-file').click();return;}
 if(['cancel','fail'].includes(action)){await changeMembership(a=>updateRender(a,aiJob.id,action));return;}
 if(action==='stop-renewal'||action==='resume-renewal'){await changeMembership(a=>action==='stop-renewal'?stopRenewal(a):subscribe(a,{accepted:true}));return;}
 aiBusy=true;
 try{
  if(action==='sample'){
   const example=exampleFor(state.aiExample);const photo=await loadAssetPhoto(example.original);await writeDesign('draft-photo',photo);
   Object.assign(state,{photo,source:'photo',photoOrigin:example.origin,ai:null,effect:'original',zoom:100,x:50,y:50,photoPlacement:null});effectPanelOpen=true;selectedArtwork='photo';save();render(true);
  }
  if(action==='create'){
   if(aiJob&&['awaiting_confirmation','awaiting_payment','payment_failed','queued','generating'].includes(aiJob.status)){go('ai');notify('Finish or cancel your current render before starting another.');}
   else await newAI({photo:state.photo,sourceKind:state.photoOrigin===exampleFor(state.aiExample).origin?'sample':'upload',styleId:state.aiStyle,exampleId:state.aiExample});
  }
  if(action==='retry')await newAI({photo:aiJob.photo,sourceKind:aiJob.sourceKind,styleId:aiJob.styleId,exampleId:aiJob.exampleId});
  if(action==='apply'){
   membership=await updateDesign('ai-membership-v1',a=>updateRender(a,aiJob.id));aiJob=membership.jobs[aiJob.id];
   if(!canApplyAIOrder(aiJob))throw Error('Wait until the render is ready before using its result.');
   const photo=await loadAssetPhoto(aiJob.result);await writeDesign('draft-photo',photo);
   Object.assign(state,{photo,source:'photo',photoOrigin:'upload',effect:'original',zoom:100,x:50,y:50,photoPlacement:null,ai:{styleId:aiJob.styleId,jobId:aiJob.id,mode:'demo'}});
   save();go('choose');notify('AI sample applied. Adjust your crop, then review your print order.');
  }
 }catch(error){notify(error.message||'The AI demo could not be saved. Please try again.');}
 finally{aiBusy=false;render(true);}
}
let pollBusy=false;
setInterval(async()=>{
 if(!aiJob||aiBusy||pollBusy||!['queued','generating'].includes(aiJob.status))return;
 pollBusy=true;
 try{
  const previous=aiJob.status;membership=await updateDesign('ai-membership-v1',a=>updateRender(a,aiJob.id));aiJob=membership.jobs[aiJob.id];
  if(previous!==aiJob.status){if(location.hash==='#ai')render(true);else{const banner=document.querySelector('.ai-resume a');if(banner)banner.innerHTML=`✦ AI studio · ${aiJob.status==='ready'?'Your example is ready':aiJob.status==='queued'?'Waiting in queue':'Rendering'} <span>View render →</span>`;}if(aiJob.status==='ready')notify('Your AI style example is ready. Open AI studio to use it.');}
  const countdown=document.querySelector('.ai-countdown');
  if(countdown&&['queued','generating'].includes(aiJob.status)){
   const remaining=Math.max(0,Math.ceil((aiJob.paidAt+DEMO_QUEUE_MS+DEMO_RENDER_MS-Date.now())/1000));
   countdown.textContent=`${aiJob.status==='queued'?'Waiting for a render slot':'Rendering'} · About ${remaining}s left in this demo`;
  }
 }catch{notify('We could not update your render. Reload to try again.');}
 finally{pollBusy=false;}
},1000);
