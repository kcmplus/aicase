import {openPhoneModelDialog} from './phone-model-dialog.js';
import {openHomePhoneDialog} from './home-phone-dialog.js';
import {worksPage,workDetailPage,tutorialPage,aboutPage,locationsPage,membershipInfoPage} from './v35-pages.js';
import {shellHeader,shellFooter,homePresentation,mountShell} from './v35-shell.js';
import {caseStylePicker,caseMaterialLabel} from './case-styles.js';
import {createStationFinder,stationFinderPanel,locateUser} from './pickup-stations.js';
import {progressPanel,progressPaymentText} from './order-progress.js';
import {startVisiblePolling} from './visible-polling.js';
import {providerOrderRoute,requireDisplayedOrder,mergeOrderProgress} from './order-service.js';
import {stationScanPrompt,previewStationPanel,openStationScanner} from './station-scanner.js';
import {stationEntry} from './station-entry.js';
import {loadDeviceInfo,deviceInfoErrorMessage} from './device-info-service.js';
import {fulfillmentConfig,prepareDeviceOrder,fulfillmentView,scopeIds,scanScope,stationIdentity,isPickup,deliveryOptions,deliveryLabel,deliveryStatusPanel} from './fulfillment-service.js';
import {paymentState} from './payment-state.js';
import {openAirwallexCheckout} from './airwallex-checkout.js';
import {t,locale,setLocale,localized,languageControl,localize} from './simple-i18n.js';
import {imageTag} from './image-view.js';
import {orderRequest,savedOrder,checkoutBody,singlePrintDraft,singlePrintNotice,checkoutEmailField,getPaymentConfig,stripeCheckoutUrl} from './order-service.js';
import {stockedPhoneModels as phoneModels,stockCatalogStatus,stockSelection,loadStockCatalog,deviceScope} from './stock-catalog.js';
import {registerSupplierTemplates,phoneTemplate,selectSupplierTemplate} from './phone-templates.js';
import {fonts} from './editor-model.js';
import {frozenPhoneColor,reconcilePhoneColor,colorPicker} from './phone-colors.js';
import {dragPlacement,scaleFromPointer,rotationFromPointer,rotateGroup} from './artwork-drag.js';
import {freshOrders,orderForCode,currentOrder,commitPrintOrder} from './print-orders.js';
import {freshMembership,refreshMembership,migrateRender} from './ai-membership.js';
import {PRINT_PRICE,PRINT_PRICE_CENTS,PRINT_AVAILABLE,money} from './simple-pricing.js';
import {loadCatalog,catalogStatus,AI_GENERATION_CONNECTED} from './runtime-catalog.js';
import {aiExamples,exampleFor} from './ai-examples.js';
import {designFor,stickers} from './catalog.js';
import {phone, icon, esc} from './art.js';
import {designs, stations, readPass, createPersonalPass} from './simple-core.js';

import {effects, validateAddedArtwork, validatePlacement, isPhoto, makePersonalDesign, personalPassName} from './simple-personalize.js';
import {readDesign, writeDesign, updateDesign} from './simple-storage.js';
import {stylePanel, aiPage} from './ai-view.js';
import {setAIView,setAIComparison,mountAIStudio} from './ai-interactions.js';
import {activeLook,lookBrowserContent,setLookMode,setLookComparison,updateLookImageState} from './ai-look-browser.js';
import {aiStyles,refreshAIOrder,canApplyAIOrder} from './ai-core.js';
import {createLiveRender,getAIAccount,changeAIAccount,submitLiveRender,refreshLiveRender,cancelLiveRender} from './ai-service.js';
import {importPhoto} from './simple-upload.js';
import {customerPage,sendEmailCode,verifyEmailCode,signOutCustomer,updateCustomerName,getCustomerCredits} from './customer-account.js';
import {createDesignWorkspace,createDesignLibrary,designOwner} from './design-workspace.js';
import {myDesignsPage,designReview,designSteps} from './v35-designs.js';
import {showStorageStartupError} from './v35-startup.js';

async function startStorefront(){
let colorNotice=false;
const app = document.querySelector('#app');
app.textContent=t('Loading POPOMO…');
const stockScope=deviceScope();
if(stockScope){const url=new URL(location.href);for(const [key,value] of new URLSearchParams(stockScope))url.searchParams.set(key,value);history.replaceState(null,'',url);}
const scannedIds=scopeIds(stockScope);
let stationError='',lastScannedStation=null;
async function readScannedStation(){if(!scannedIds)return null;try{const data=await loadDeviceInfo({deviceId:scannedIds.device_id,shopId:scannedIds.shop_id});stationError='';lastScannedStation=data;return data;}catch(error){stationError=error.message||'connection';if(stationError!=='connection')lastScannedStation=null;return null;}}
let scannedStation=null;
const initialData=await Promise.all([loadCatalog(),loadStockCatalog(undefined,stockScope),fulfillmentConfig(),readScannedStation(),getAIAccount().catch(()=>null)]);
const devicePrinting=initialData[2];scannedStation=initialData[3];
const workspace=createDesignWorkspace(initialData[4],{read:readDesign,write:writeDesign,update:updateDesign});
const KEY=workspace.active?workspace.key('editor'):null;
// Orders retain their existing browser access contract. Private design/AI data
// has its own namespace and cannot be restored from an old unassigned cache.
const privateRead=name=>workspace.active?workspace.read(name):Promise.resolve(undefined);
const privateWrite=(name,value)=>workspace.write(name,value);
const privateUpdate=(name,transform,initial)=>workspace.update(name,transform,initial);
const library=createDesignLibrary(workspace,{validate:pass=>readPass(pass.code,pass)});
let localDesigns=[],localDesignError='',localDesignBusy=false,reviewPass=null,reviewSaved=false,noticeTimer;
let state = {designId:'bloom',model:'',caseMaterial:'',pass:null,stationId:'DEMO-01',job:null,source:'collection',photo:'',effect:'original',intensity:65,zoom:100,x:50,y:50,aiStyle:'anime',aiExample:'portrait',artworkLayouts:{},photoArtwork:[],keepCollection:false,photoPlacement:null,photoOrigin:'upload',ai:null,aiJobId:null};
let storageWarning = false;
let aiJob=null,aiBusy=false;
const aiUi={mode:'pair',compare:50,lookMode:'effect',lookCompare:50,accepted:false,error:'',reconnecting:false};
let cleanupAIStudio=()=>{};
let cleanupShell=()=>{};
let cleanupHomePhone=()=>{};
let cleanupPhoneModels=()=>{};
const customerUI={email:'',codeSent:false,busy:false,error:'',success:'',ledger:[],ledgerNext:null,ledgerOpen:false,ledgerBusy:false,ledgerError:'',resendAt:0,next:'choose'};
let resendTimer;
let membership={...freshMembership(),server:true,authenticated:false,customer:null,...(initialData[4]||{})};
const stopForStorage=()=>{
 app.textContent='Browser storage is unavailable. Allow site storage, then reload to try again. Existing designs have not been deleted.';
 return 'storage-unavailable';
};
try{if(workspace.active)membership=await privateUpdate('ai-membership-v1',a=>({...a,...membership,jobs:a.jobs||{}}),freshMembership());}
catch{return stopForStorage();}
let orderBook=await updateDesign('print-orders-v1',v=>v,freshOrders()).catch(()=>null);
if(!orderBook)return stopForStorage();
let checkoutDraft;
try{checkoutDraft=singlePrintDraft(await privateRead('checkout-draft'));if(checkoutDraft)await privateWrite('checkout-draft',checkoutDraft);}
catch{return stopForStorage();}
for(const order of Object.values(orderBook.orders||{}))if(order.phoneTemplate)try{registerSupplierTemplates([order.phoneTemplate]);}catch{}
if(checkoutDraft?.phoneTemplate)try{registerSupplierTemplates([checkoutDraft.phoneTemplate]);}catch{}
let orderLoading=false;
let orderRows=[],orderPage=1,orderHasMore=false,orderError='',entryOrders=null,entryOrderError='';
let paymentConfig=null,paymentError='',orderActionError='',paymentOrder=null,stopPaymentPolling=()=>{},paymentPollCount=0,paymentLoading=false,navigationId=0;
let userPosition=null,locatingStations=false,stationLocationError='';
const openStationMaps=new Set();
const stationFinder=createStationFinder({onChange:renderStationFinder});
function pickupContext(){
 const route=location.hash.split('?')[0];
 if(route==='#checkout'&&checkoutDraft&&!checkoutDraft.editId&&(checkoutDraft.fulfillmentType||'pickup')==='pickup')return {key:'checkout:'+checkoutDraft.pass.model+':'+checkoutDraft.pass.caseMaterial+':'+stockScope,model:checkoutDraft.pass.model,caseMaterial:checkoutDraft.pass.caseMaterial,scope:scannedIds};
 const o=paymentOrder,f=o?.fulfillment;
 if(route==='#payment'&&o&&isPickup(o)&&['stripe_live','airwallex_live','free_test'].includes(o.mode)&&['pending','paid'].includes(o.status)&&(!o.refund||o.refund.status==='failed')&&(!f||!f.print_confirmed&&['draft','prepared','rejected'].includes(f.state)))return {key:o.id+':'+(f?.device_id||'')+':'+(f?.shop_id||''),orderId:o.id,model:o.pass.model,caseMaterial:o.pass.caseMaterial};
 return null;
}
function syncStationFinder(){stationFinder.setContext(pickupContext());}
function pickupStationPanel(){
 const context=pickupContext();if(!context)return '';
 const finder=stationFinder.state.key===context.key?stationFinder.state:{rows:[],busy:true};
 return stationFinderPanel(finder,{model:context.model+' · '+caseMaterialLabel(context.caseMaterial,locale()),lang:locale(),position:userPosition,locating:locatingStations,locationError:stationLocationError,openMaps:openStationMaps});
}
function pickupCheckoutReady(){const c=pickupContext(),v=stationFinder.state;return c&&v.key===c.key&&!v.error&&!v.busy&&Date.now()-v.loadedAt<=60000&&v.rows.some(s=>s.availability==='available');}
async function requestStationLocation({force=false}={}){
 if(locatingStations||passBusy||(!force&&userPosition&&Date.now()-userPosition.acquiredAt<300000))return;
 locatingStations=true;stationLocationError='';
 // Start on the radio/button gesture, before storage writes or other awaits.
 const request=locateUser();renderStationFinder();
 try{userPosition=await request;}catch(error){stationLocationError=error.message;userPosition=null;}
 finally{locatingStations=false;renderStationFinder();}
}
function renderStationFinder(){
 const panel=document.querySelector('#pickup-station-panel');if(panel)panel.innerHTML=pickupStationPanel();
 const button=document.querySelector('#print-checkout-form button');if(button&&!checkoutDraft?.editId)button.disabled=passBusy||!pickupCheckoutReady();
}

try {
  const saved = KEY?JSON.parse(localStorage.getItem(KEY)):null;
  if (saved) {
    if (designs.some(d=>d.id===saved.designId)) state.designId=saved.designId;
    // An unreadable/refreshing catalog cannot establish that this saved model
    // disappeared. Keep the draft identity, without adding it to sale choices.
    if (typeof saved.model==='string'&&saved.model.length<=120&&(phoneModels.includes(saved.model)||stockCatalogStatus!=='ready')) state.model=saved.model;
    if (saved.phoneColor)try{state.phoneColor=frozenPhoneColor(saved.phoneColor);}catch{/* Invalid cached previews cannot be restored. */}
    if(['standard','magnetic'].includes(saved.caseMaterial)&&(stockSelection(state.model,saved.caseMaterial)||stockCatalogStatus!=='ready'))state.caseMaterial=saved.caseMaterial;
    if (stations.some(s=>s.id===saved.stationId)) state.stationId=saved.stationId;
    if(aiStyles.some(s=>s.id===saved.aiStyle))state.aiStyle=saved.aiStyle;
    state.aiExample=exampleFor(saved.aiExample).id;
    if(!exampleFor(state.aiExample).results[state.aiStyle])state.aiStyle=Object.keys(exampleFor(state.aiExample).results)[0];
    state.photoOrigin=aiExamples.some(e=>e.origin===saved.photoOrigin)?saved.photoOrigin:'upload';
    if(typeof saved.editOrderId==='string')state.editOrderId=saved.editOrderId;
    if(saved.ai&&/^[a-zA-Z0-9_-]{1,80}$/.test(saved.ai.styleId||''))state.ai=saved.ai;
    if(typeof saved.aiJobId==='string'){try{aiJob=await privateUpdate('ai-job:'+saved.aiJobId,refreshAIOrder);state.aiJobId=aiJob.id;}catch{}
      if(membership.jobs[saved.aiJobId]){aiJob=membership.jobs[saved.aiJobId];state.aiJobId=aiJob.id;}}
    if(saved.artworkLayouts&&typeof saved.artworkLayouts==='object')for(const [id,layout] of Object.entries(saved.artworkLayouts)){
      try{const p=createPersonalPass({source:'collection',designId:id,model:phoneModels[0]||'iPhone 17',effect:'original',intensity:0,zoom:layout.zoom,x:layout.x,y:layout.y,artworkEdits:layout.artworkEdits,addedArtwork:layout.addedArtwork});state.artworkLayouts[id]={zoom:p.zoom,x:p.x,y:p.y,artworkEdits:p.artworkEdits||{},addedArtwork:p.addedArtwork||[]};}catch{}
    }
    try{state.photoArtwork=validateAddedArtwork(saved.photoArtwork);if(saved.photoPlacement)state.photoPlacement=validatePlacement(saved.photoPlacement);}catch{}
    if (saved.source==='photo')state.source='photo';
    state.keepCollection=saved.keepCollection===true;
    if(effects.some(e=>e.id===saved.effect))state.effect=saved.effect;
    for(const [key,min,max] of [['intensity',0,100],['zoom',100,180],['x',0,100],['y',0,100]])if(Number.isFinite(saved[key]))state[key]=Math.max(min,Math.min(max,saved[key]));
    try{const photo=await privateRead('draft-photo');if(isPhoto(photo))state.photo=photo;}catch{return stopForStorage();}
    if (saved.pass) {try{state.pass=await resolvePass(saved.pass.code);}catch{}}
    if (saved.job && ['printing','ready','collected'].includes(saved.job.status) && stations.some(s=>s.id===saved.job.stationId)) {
      try{state.job={...saved.job,pass:await resolvePass(saved.job.pass.code)};}catch{}
    }
  }
} catch { /* Missing or invalid local data starts a fresh session. */ }
state.phoneTemplateId=stockSelection(state.model,state.caseMaterial)?.templateId;selectSupplierTemplate(state.model,state.phoneTemplateId);
if(state.phoneColor||stockSelection(state.model,state.caseMaterial)?.colors?.length)syncDraftColor();
state.aiExample=exampleFor(state.aiExample).id;
if(!exampleFor(state.aiExample).results[state.aiStyle])state.aiStyle=Object.keys(exampleFor(state.aiExample).results)[0]||'';
try{if(workspace.active)membership=await privateUpdate('ai-membership-v1',a=>migrateRender(a,aiJob),freshMembership());}
catch{return stopForStorage();}
if(aiJob)aiJob=membership.jobs[aiJob.id];
if(aiJob?.status==='awaiting_confirmation')customerUI.next='ai';
try{if(location.hash.slice(1).split('?')[0]!=='checkout')await syncAIAccount();if(aiJob?.mode==='live')await rememberLiveJob(await refreshLiveRender(aiJob));}catch{/* A saved job can be resumed when the service returns. */}
let comparing=false,photoBusy=false,passBusy=false;
let effectPanelOpen=false,cropPanelOpen=false,selectedArtwork=null,libraryExpanded=false;
const editorPanels={collection:false,graphics:false};
let canvasExpanded=false,canvasObserver=null,canvasHome=null;
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
// A newly chosen photo starts clean.
// Call only after the replacement image has been decoded and saved successfully.
function clearPreviousPhotoArtwork(){
 state.photoArtwork=[];state.keepCollection=false;state.photoPlacement=null;
 artworkDrag=null;selectedArtwork='photo';comparing=false;
}
// Starting another photo must clear both the visible draft and its persisted image.
// Saved orders and render snapshots have their own copies and remain resumable.
async function clearPhotoDraft(){
 finishInlineText();
 await privateWrite('draft-photo','');
 Object.assign(state,{photo:'',photoOrigin:'upload',ai:null,effect:'original',intensity:65,zoom:100,x:50,y:50});
 clearPreviousPhotoArtwork();selectedArtwork=null;
 effectPanelOpen=false;cropPanelOpen=false;
 editorPanels.collection=false;editorPanels.graphics=false;
 Object.assign(aiUi,{accepted:false,error:''});
}
// The editor keeps a draft per template. Choosing from the home gallery begins
// a fresh editing session so drafts from the previous visit cannot reappear.
async function selectCollectionDesign(id,{startFresh=false}={}){
 if(!designs.some(design=>design.id===id))return;
 finishInlineText();
 if(startFresh){await clearPhotoDraft();state.artworkLayouts={};state.editOrderId=null;}
 state.designId=id;state.source='collection';
 artworkDrag=null;lastArtworkTap=null;selectedArtwork=startFresh?null:'all';comparing=false;
 save();
}
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
 const selected=selectedText();let tools=document.querySelector('.text-quick-tools');
 if(!selected){tools?.remove();return;}
 if(!tools||tools.dataset.forText!==selected.id){
  tools?.remove();tools=document.createElement('div');tools.className='text-quick-tools';tools.dataset.forText=selected.id;tools.setAttribute('role','group');tools.setAttribute('aria-label',t('Text style shortcuts'));
  tools.innerHTML=`<span class="quick-label">Font</span><div class="quick-fonts">${[['sans','Modern'],['serif','Classic'],['hand','Handwritten'],['mono','Typewriter']].map(([font,name])=>`<button type="button" data-quick-font="${font}" aria-label="${name} font" title="${name}" style="font-family:${fonts[font]}">Aa</button>`).join('')}</div><span class="quick-label">Color</span><div class="quick-colors">${['#242822','#ffffff','#e44592','#146561','#f3c44d','#7964ac'].map((color,i)=>`<button type="button" data-quick-color="${color}" style="--color:${color}" aria-label="${['Charcoal','White','Pink','Teal','Gold','Purple'][i]} text" title="${['Charcoal','White','Pink','Teal','Gold','Purple'][i]}"></button>`).join('')}</div><label class="quick-custom">Custom<input type="color" data-text-field="color" aria-label="Custom text color"></label>`;
  localize(tools);(canvasExpanded?document.querySelector('.canvas-text-style'):canvas).append(tools);
 }
 for(const button of tools.querySelectorAll('[data-quick-font]'))button.setAttribute('aria-pressed',String(button.dataset.quickFont===selected.font));
 for(const button of tools.querySelectorAll('[data-quick-color]'))button.setAttribute('aria-pressed',String(button.dataset.quickColor===selected.color.toLowerCase()));
 const colorInput=tools.querySelector('input');if(document.activeElement!==colorInput)colorInput.value=selected.color;
 const host=canvasExpanded?document.querySelector('.canvas-text-style'):canvas;if(tools.parentElement!==host)host.append(tools);
 if(!canvasExpanded){const phone=canvas.querySelector('.phone-case');tools.style.top=Math.max(0,Math.min(phone.clientHeight-tools.offsetHeight,phone.clientHeight*selected.y/100-tools.offsetHeight/2))+'px';}
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
 element.setAttribute('contenteditable','plaintext-only');element.dataset.inlineText='true';element.setAttribute('role','textbox');element.setAttribute('aria-label',t('Edit text on case'));element.setAttribute('aria-multiline','true');element.tabIndex=0;element.spellcheck=false;
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
function revealArtwork(){openCanvasEditor();}
function setArtwork(key,value){artworkTarget()[key]=value;save();updatePreview();}
function creativeLibrary(){
 const disabled=state.source==='photo'&&!state.photo&&!state.keepCollection,items=[...stickers.slice(12),...stickers.slice(0,12)];
 return `<details class="editor-panel" data-editor-panel="graphics" ${editorPanels.graphics?'open':''}><summary><span class="editor-tool-icon" aria-hidden="true">${icon('image',18)}</span><span>Graphics & text</span><span class="editor-chevron" aria-hidden="true">⌄</span></summary><div class="editor-panel-body"><section class="graphic-library"><div class="library-title"><h2>Graphic library</h2><span>24 graphics</span></div><p>Little details. A little more you.</p><div class="graphic-grid">${items.slice(0,libraryExpanded?24:12).map(a=>`<button type="button" data-add-graphic="${a.id}" aria-label="Add ${esc(locale()==='zh-CN'?a.zh:a.en)}" title="${esc(locale()==='zh-CN'?a.zh:a.en)}" ${disabled?'disabled':''}>${imageTag(a.src,{alt:"",sizes:"64px"})}<span>${esc(locale()==='zh-CN'?a.zh:a.en)}</span></button>`).join('')}</div><button class="text-button library-more" data-action="toggle-library">${libraryExpanded?'Show less':'View all 24 graphics'} ${libraryExpanded?'−':'+'}</button><p class="library-credit">Original POPOMO artwork + OpenMoji · CC BY-SA 4.0</p></section>
 <section class="text-editor"><h2>Your words</h2><p>Double-click text on your case to edit.<br>Choose fonts and colors right beside it.</p><button class="button text-add" data-action="text-submit" ${disabled?'disabled':''}>Add text ${icon('spark',16)}</button>${disabled?'<p class="field-note">Upload a photo to start adding graphics and text.</p>':''}</section></div></details>`;
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
 return readPass(key,key.startsWith('POP-C-')?await privateRead(key):undefined);
}
async function orderAction(order,action,stationId){
 const data=await orderRequest(order.id+'/actions/',{method:'POST',body:{revision:order.revision,action,code:order.pass.code,...(stationId?{station_id:stationId}:{})}});
 return rememberOrder(data);
}
function personalizedPreview(selection,model,label,original=false){
 const changed=selection.phoneColor&&selection.phoneColor.resource.templateId!==phoneTemplate(model,selection.phoneTemplateId)?.id;
 const note=changed?`<p class="field-note" role="status">${locale()==='zh-CN'?'当前设备模板不适用原机身颜色，已显示基础预览；原订单颜色快照保留。':'The original body color does not match this station template. Showing the base preview; the original order color is preserved.'}</p>`:'';
 return note+phone(makePersonalDesign(layoutSelection(selection),original),model).replace(/aria-label="[^"]*"/,`aria-label="${esc(label+' on '+model)}"`).replace('alt="你上传的设计照片"',`alt="Your uploaded photo"`);
}
const passName=p=>p.version===2?personalPassName(p,designs):currentDesign(p.designId).name;
const passPreview=p=>p.version===2?personalizedPreview(p,p.model,passName(p)):casePreview(p.designId,p.model);
const effectCaption=p=>p.source==='photo'&&p.ai?`<span class="effect-caption">✦ ${esc(localized(aiStyles.find(s=>s.id===p.ai.styleId))||t('AI style'))} · ${p.ai.mode==='live'?'AI image':'Demo sample'}</span>`:p.version===2&&p.effect!=='original'&&p.intensity>0?`<span class="effect-caption">${icon('spark',13)} ${effects.find(e=>e.id===p.effect).name} · AI effect preview</span>`:'';
function updatePreview(){finishInlineText();const note=document.querySelector('#model-preview-note');if(note)note.hidden=!state.model||Boolean(state.phoneTemplateId);const el=document.querySelector('.large-case');if(el&&!(state.source==='photo'&&!state.photo&&!state.keepCollection))el.innerHTML=personalizedPreview(state,state.model||phoneModels[0],state.source==='photo'?'Your photo':currentDesign(state.designId).name,comparing);fitCanvasEditor();highlightArtwork();}
function highlightArtwork(){
 document.querySelector('.artwork-selection-actions')?.remove();
 const canvas=document.querySelector('.artwork-canvas');if(!canvas)return;
 const phone=canvas.querySelector('.phone-case');phone?.setAttribute('role','group');canvas.querySelector('.artwork-gizmo')?.remove();
 for(const layer of canvas.querySelectorAll('.design-layer')){layer.classList.remove('artwork-selected');layer.removeAttribute('aria-hidden');layer.setAttribute('role',layer.dataset.layerId===inlineTextId?'group':'button');layer.tabIndex=layer.dataset.layerId===inlineTextId?-1:0;layer.setAttribute('aria-label',t('Move')+' '+(layer.textContent.trim()||t('graphic')));layer.setAttribute('aria-pressed',String(layer.dataset.layerId===selectedArtwork));}
 canvas.classList.remove('whole-design-selected');
 const photo=canvas.querySelector('[data-photo-layer]');if(photo){photo.setAttribute('role','button');photo.tabIndex=0;photo.setAttribute('aria-label',t('Move your photo'));photo.setAttribute('aria-pressed',String(selectedArtwork==='photo'));}
 syncTextTools(canvas);
 syncCanvasControls();
 if(!canvasExpanded){for(const layer of canvas.querySelectorAll('[data-layer-id],[data-photo-layer]'))layer.tabIndex=-1;return;}
 canvas.setAttribute('aria-description',t(inlineTextId?'Type right here · Up to 80 characters · Tap outside to finish':selectedArtwork?'Drag to move · Corners to resize · ↻ to rotate · Tap outside to finish':'Tap artwork to adjust · Double-click text to edit'));
 if(!selectedArtwork)return;
 const all=selectedArtwork==='all',isPhotoLayer=selectedArtwork==='photo',model=makePersonalDesign(layoutSelection(state)),layer=model.layers.find(l=>l.id===selectedArtwork),element=isPhotoLayer?photo:all?null:canvas.querySelector(`[data-layer-id="${selectedArtwork}"]`),layout=artworkLayout(),placement=isPhotoLayer?photoTarget():null;
 if(!all&&!element)return;
 if(layer){
  const actions=document.createElement('div');actions.className='artwork-selection-actions';
  actions.innerHTML=`<button type="button" data-action="delete-artwork" aria-label="Delete selected artwork" title="Delete selected artwork (Delete / Backspace)">${icon('trash',17)} Delete</button>`;
  localize(actions);canvas.closest('.large-preview').append(actions);
 }
 const visualScale=isPhotoLayer?Math.min(placement.scale,100)/100:1;
 const cx=phone.offsetLeft+phone.clientLeft+(isPhotoLayer?phone.clientWidth*placement.x/100:all?phone.clientWidth*layout.x/100:element.offsetLeft),cy=phone.offsetTop+phone.clientTop+(isPhotoLayer?phone.clientHeight*placement.y/100:all?phone.clientHeight*layout.y/100:element.offsetTop),width=isPhotoLayer?phone.clientWidth*visualScale:all?phone.clientWidth*layout.zoom/100:element.offsetWidth,height=isPhotoLayer?phone.clientHeight*visualScale:all?phone.clientHeight*layout.zoom/100:element.offsetHeight;
 const box=document.createElement('div');box.className='artwork-gizmo';box.style.cssText=`left:${cx}px;top:${cy}px;width:${width}px;height:${height}px;transform:translate(-50%,-50%) rotate(${isPhotoLayer?placement.rotation:all?0:layer.rotation}deg)`;
 box.innerHTML=`${['nw','ne','sw','se'].map(c=>`<button type="button" class="artwork-handle resize-${c}" data-transform="scale" aria-label="Resize artwork ${c}" title="Drag to resize"></button>`).join('')}<span class="rotation-stem" aria-hidden="true"></span><button type="button" class="artwork-handle rotate-handle" data-transform="rotate" aria-label="Rotate artwork" title="Drag to rotate">↻</button><button type="button" class="artwork-reset" data-action="reset-artwork" aria-label="Reset selected artwork" title="Reset selected artwork">↺</button>${layer?.type==='text'?`<button type="button" class="artwork-edit-text" data-action="edit-text" aria-label="${inlineTextId?'Finish editing text':'Edit text on case'}" title="${inlineTextId?'Done':'Edit text'}">${inlineTextId?'✓':'✎'}</button>`:''}`;
 localize(box);canvas.append(box);
}
function refreshArtworkControls(){highlightArtwork();}
function canvasEditor(){
 return `<dialog class="canvas-editor" aria-labelledby="canvas-editor-title"><header class="canvas-editor-header"><div><h2 id="canvas-editor-title">Edit your design</h2><span>${esc(state.model||phoneModels[0])}</span></div><button type="button" class="canvas-done" data-action="close-canvas" autofocus>Done ${icon('check',16)}</button></header><div class="canvas-stage"></div><footer class="canvas-toolbar"><div class="canvas-toolbar-heading"><p class="canvas-selection-label">Tap a photo, graphic or text to adjust.</p><details class="canvas-text-options" hidden><summary>Text style <span>⌄</span></summary><div class="canvas-text-style"></div></details><button type="button" data-action="text-submit"><span aria-hidden="true">＋</span> Add text</button></div><div class="canvas-adjustments" hidden><div class="canvas-size"><label for="canvas-size">Size</label><input id="canvas-size" type="range" min="25" max="200" step="1" value="100"><output for="canvas-size">100%</output></div><div class="canvas-actions"><button type="button" data-action="rotate-canvas-artwork">↻ <span>Rotate</span></button><button type="button" data-action="reset-artwork">↺ <span>Reset</span></button><button type="button" data-action="edit-text" class="canvas-edit-text"><span aria-hidden="true">✎</span> <span>Edit text</span></button><button type="button" data-action="delete-artwork" class="canvas-delete">${icon('trash',16)} <span>Delete</span></button></div></div><p class="canvas-gesture-note">Drag to move · Use the corners to resize</p></footer></dialog>`;
}
function syncCanvasControls(){
 const dialog=document.querySelector('.canvas-editor');if(!dialog||!canvasExpanded)return;
 const target=selectedArtwork?artworkTarget():null,selected=selectedText();
 dialog.querySelector('.canvas-adjustments').hidden=false;
 dialog.querySelectorAll('.canvas-adjustments button,.canvas-adjustments input').forEach(control=>control.disabled=!target);
 dialog.querySelector('.canvas-selection-label').textContent=t(!target?'Tap a photo, graphic or text to adjust.':selected?'Text':selectedArtwork==='photo'?'Your photo':selectedArtwork==='all'?'Your design':'Graphic');
 dialog.querySelector('.canvas-edit-text').hidden=!selected;
 dialog.querySelector('.canvas-delete').hidden=!target||['all','photo'].includes(selectedArtwork);
 const textOptions=dialog.querySelector('.canvas-text-options');textOptions.hidden=!selected;if(!selected)textOptions.open=false;
 const value=target?target[selectedArtwork==='all'?'zoom':'scale']:100,slider=dialog.querySelector('#canvas-size');slider.min=selectedArtwork==='all'?50:25;slider.max=selectedArtwork==='all'?180:200;slider.value=value;dialog.querySelector('output').textContent=target?Math.round(value)+'%':'—';
}
function fitCanvasEditor(){
 const preview=document.querySelector('.large-preview'),canvas=preview?.querySelector('.artwork-canvas'),phone=canvas?.querySelector('.phone-case');if(!phone)return;
 const style=getComputedStyle(preview),number=value=>parseFloat(value)||0;
 const ratioParts=getComputedStyle(phone).aspectRatio.split('/').map(Number);
 const ratio=ratioParts.length===2&&ratioParts.every(n=>n>0)?ratioParts[0]/ratioParts[1]:phone.offsetWidth/phone.offsetHeight;
 if(!Number.isFinite(ratio)||ratio<=0)return;
 const siblings=[...preview.children].filter(el=>el!==canvas&&getComputedStyle(el).position!=='absolute');
 const reserved=siblings.reduce((sum,el)=>{const cs=getComputedStyle(el);return sum+el.getBoundingClientRect().height+number(cs.marginTop)+number(cs.marginBottom);},0);
 const extra=Math.max(0,canvas.offsetHeight-phone.offsetHeight);
 const width=Math.max(1,Math.min(preview.clientWidth-number(style.paddingLeft)-number(style.paddingRight),
  (preview.clientHeight-number(style.paddingTop)-number(style.paddingBottom)-reserved-extra-8)*ratio,
  canvasExpanded?430:window.innerWidth<=760?180:225));
 canvas.style.width=width+'px';highlightArtwork();
}
function observeCanvasPreview(){
 canvasObserver?.disconnect();
 const preview=document.querySelector('.large-preview');if(!preview)return;
 canvasObserver=new ResizeObserver(fitCanvasEditor);canvasObserver.observe(preview);
 const tools=preview.querySelector('.template-tools');if(tools)canvasObserver.observe(tools);
 fitCanvasEditor();
}
function openCanvasEditor(){
 const dialog=document.querySelector('.canvas-editor'),preview=document.querySelector('.large-preview');if(!dialog||!preview?.querySelector('.artwork-canvas')||dialog.open)return;
 finishInlineText();canvasExpanded=true;
 canvasHome=document.createComment('editor-preview');preview.before(canvasHome);dialog.querySelector('.canvas-stage').append(preview);
 if(state.source==='photo'&&!selectedArtwork)selectedArtwork='photo';
 document.body.classList.add('canvas-editor-open');dialog.showModal();
 observeCanvasPreview();
 fitCanvasEditor();
}
function closeCanvasEditor({restoreFocus=true}={}){
 const dialog=document.querySelector('.canvas-editor');if(!dialog)return;
 finishInlineText();canvasExpanded=false;canvasObserver?.disconnect();canvasObserver=null;
 const preview=dialog.querySelector('.large-preview');if(preview){canvasHome?.replaceWith(preview);preview.querySelector('.artwork-canvas').style.removeProperty('width');}
 canvasHome=null;dialog.close();document.body.classList.remove('canvas-editor-open');selectedArtwork=null;lastArtworkTap=null;
 document.querySelector('.text-quick-tools')?.remove();updatePreview();observeCanvasPreview();save();
 if(restoreFocus)document.querySelector('[data-action="open-canvas"]')?.focus({preventScroll:true});
}
const arrow = () => icon('arrow',18);
const currentDesign = id => designs.find(d=>d.id===id) || designs[0];
const casePreview = (id,model=phoneModels[0]) => phone(designFor(id),model,'',{loading:'lazy',sizes:'(max-width: 700px) 100px, 180px'}).replace(/aria-label="[^"]*"/,`aria-label="${esc(currentDesign(id).name+' on '+model)}"`);
function save() {
  try {workspace.check();const ref=p=>p?.version===2?{code:p.code}:p;localStorage.setItem(KEY,JSON.stringify({...state,photo:undefined,pass:ref(state.pass),job:state.job?{...state.job,pass:ref(state.job.pass)}:null}));storageWarning=false;}
  catch {storageWarning=true;notify('Your design could not be saved on this browser. Please reload and try again.');}
}
function notify(message) {
  const el=document.querySelector('#notice');el.textContent=t(message);el.classList.add('visible');
  clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>el.classList.remove('visible'),5000);
}
function go(route) {if(location.hash==='#'+route)render();else location.hash=route;}
function header() {
 const route=location.hash.slice(1).split('?')[0]||'home';
 return shellHeader({lang:locale(),authenticated:membership.authenticated,language:languageControl(),route})+`${aiJob&&['queued','generating','ready'].includes(aiJob.status)&&state.ai?.jobId!==aiJob.id?`<div class="ai-resume wrap"><a href="#ai">✦ AI studio · ${aiJob.status==='ready'?'Your AI image is ready':aiJob.status==='queued'?'Waiting in queue':'Rendering'} <span>View render →</span></a></div>`:''}`;
}
function footer() {return shellFooter(locale());}
function steps(active) {
  return `<ol class="steps" aria-label="Your design journey">${['Pick your design','Confirm & save','Scan & print'].map((label,i)=>`<li ${i===active?'aria-current="step"':''} class="${i===active?'active':i<active?'complete':''}"><span>${i<active?'✓':i+1}</span>${label}</li>`).join('')}</ol>`;
}
function home() {
 const gallery=`<section class="collection wrap home-gallery" id="designs"><div class="section-heading"><div><p class="eyebrow">A LITTLE INSPIRATION</p><h2>No photo in mind? Try the gallery.</h2></div><p>Ready-made designs, if you need a starting point.</p><a class="text-button" href="#designs">${locale()==='zh-CN'?'查看全部设计 →':'View all designs →'}</a></div><div class="design-grid">${designs.map((d,i)=>`<a class="design-card" href="#work?id=${d.id}" aria-label="${esc(t('View design')+': '+d.name)}"><div class="design-image" style="--card:${d.color}"><span class="card-index">0${i+1}</span><div class="card-case">${casePreview(d.id)}</div><span class="card-arrow">${arrow()}</span></div><div class="card-caption"><div><h3>${d.name}</h3><p>${d.category}</p></div></div></a>`).join('')}</div></section>`;
 return homePresentation({lang:locale(),busy:photoBusy,gallery,station:stockScope?`<div class="v35-wrap">${stationContext()}</div>`:''});
}
function phonePicker(){
 return `<div class="model-first"><button type="button" class="model-summary-button" data-action="choose-phone" aria-haspopup="dialog"><span class="model-summary-label">${state.model?'Your phone':'First, choose your phone'}</span><strong class="model-summary-value">${esc(state.model||'')}</strong><span class="model-summary-action">${state.model?'Change':'Choose'}</span><span class="model-summary-chevron" aria-hidden="true">⌄</span></button></div><p id="model-preview-note" class="field-note" ${!state.model||state.phoneTemplateId?'hidden':''}>Illustrative preview. The exact case template will be confirmed before printing.</p>`;
}
function openModelPicker(forAI=false){
 cleanupPhoneModels();
 cleanupPhoneModels=openPhoneModelDialog({root:app,selected:forAI?aiJob?.model:state.model,lang:locale(),catalog:()=>({models:phoneModels,status:stockCatalogStatus,selection:stockSelection}),refresh:refreshStockChoices,
  onSelect:model=>{if(forAI)void changeAIPhoneModel(model);else selectPhoneModel(model);}});
}
function syncDraftColor(reset=false){
 // Only a current catalog can invalidate a saved color. A transport failure or
 // pending inventory refresh is not an authoritative empty color list.
 if(stockCatalogStatus!=='ready')return false;
 const result=reconcilePhoneColor(reset?null:state.phoneColor,stockSelection(state.model,state.caseMaterial)?.colors||[]);
 state.phoneColor=result.color;colorNotice=reset?false:colorNotice||result.changed;
 return result.changed;
}
function assertCurrentColor(selection,available){
 if(!selection.phoneColor&&!available.colors?.length)return;
 const result=reconcilePhoneColor(selection.phoneColor,available.colors||[]);
 if(JSON.stringify(result.color)!==JSON.stringify(selection.phoneColor||null))throw Error(locale()==='zh-CN'?'机身颜色已变化，请重新确认预览。':'The phone color changed. Please preview your design again.');
}
function selectPhoneModel(model){
 if(!phoneModels.includes(model))return;
 if(model!==state.model){state.model=model;state.caseMaterial='';state.phoneTemplateId=undefined;selectSupplierTemplate(model,undefined);syncDraftColor(true);reviewPass=null;save();}
 if(location.hash==='#choose?step=model')history.replaceState(null,'','#choose');
 render(true);document.querySelector('[data-action="choose-phone"]')?.focus({preventScroll:true});
}
function openHomePhone(entry){
 cleanupHomePhone();
 cleanupHomePhone=openHomePhoneDialog({root:app,initial:state,lang:locale(),scoped:Boolean(stockScope),
  catalog:()=>({models:phoneModels,status:stockCatalogStatus,selection:stockSelection}),refresh:refreshStockChoices,
  onConfirm:choice=>{Object.assign(state,choice);selectSupplierTemplate(state.model,state.phoneTemplateId);colorNotice=false;reviewPass=null;save();if(entry==='photo')openPhotoPicker();else go('choose?source=photo&studio=1');}});
}
function openPhotoPicker(){
 // Run inside the click gesture, before any await, so mobile browsers allow it.
 const input=document.querySelector('#photo-file');
 if(!input||photoBusy||aiBusy||passBusy)return;
 input.value=''; // Picking the same file again should still replace the draft.
 input.click();
}
function bindEditorPanel(panel){
 panel.addEventListener('toggle',()=>{
  if(!panel.isConnected)return;
  const remember=element=>{const key=element.dataset.editorPanel;if(key==='ai')effectPanelOpen=element.open;else editorPanels[key]=element.open;};
  remember(panel);
  if(panel.open)document.querySelectorAll('[data-editor-panel]').forEach(other=>{if(other!==panel&&other.open){other.open=false;remember(other);}});
 });
}
function refreshAIStudio({resetScroll=false}={}){
 const dialog=document.querySelector('.look-browser');if(!dialog)return;
 const scroll=resetScroll?0:dialog.querySelector('.look-filmstrip')?.scrollLeft||0,tabsScroll=dialog.querySelector('.look-subjects')?.scrollLeft||0;
 dialog.innerHTML=lookBrowserContent(state,aiJob,aiUi);localize(dialog);
 updateLookImageState(dialog);
 dialog.querySelector('.look-filmstrip').scrollLeft=scroll;dialog.querySelector('.look-subjects').scrollLeft=tabsScroll;
 const selected=dialog.querySelector('.look-thumb[aria-pressed=true]');selected?.focus({preventScroll:true});selected?.scrollIntoView({block:'nearest',inline:'nearest'});
 const label=document.querySelector('.ai-picker-launch small');if(label)label.textContent=localized(activeLook(state).look.style);
}
function openAIStudio(){
 const dialog=document.querySelector('.look-browser');if(!dialog)return;
 effectPanelOpen=true;
 document.querySelectorAll('[data-editor-panel]').forEach(panel=>panel.open=false);
 if(!dialog.open)dialog.showModal();
 updateLookImageState(dialog);
 dialog.querySelector('.look-thumb[aria-pressed=true]')?.scrollIntoView({block:'nearest',inline:'nearest'});
}
function closeAIStudio(){
 effectPanelOpen=false;const dialog=document.querySelector('.look-browser');dialog?.close();dialog?.classList.remove('is-zoomed');
 document.querySelector('.ai-picker-launch')?.focus({preventScroll:true});
}
function zoomAIStudio(){
 const dialog=document.querySelector('.look-browser');if(!dialog)return;
 const expanded=dialog.classList.toggle('is-zoomed');const button=dialog.querySelector('[data-look-action=zoom]');button.setAttribute('aria-pressed',String(expanded));button.setAttribute('aria-label',t(expanded?'Back to styles':'Enlarge style example'));
}
async function receivePhoto(file,{startFresh=false}={}){
 if(!file||photoBusy||aiBusy)return;
 let imported=false;
 photoBusy=true;render(true);
 try{
  const photo=await importPhoto(file);
  await privateWrite('draft-photo',photo);
  Object.assign(state,{photo,photoOrigin:'upload',ai:null,effect:'original',source:'photo',zoom:100,x:50,y:50,intensity:65});
  clearPreviousPhotoArtwork();
  // A homepage upload starts a new design only after the image is safely saved.
  if(startFresh){
   state.artworkLayouts={};state.editOrderId=null;
   effectPanelOpen=false;cropPanelOpen=false;
   editorPanels.collection=false;editorPanels.graphics=false;
   Object.assign(aiUi,{accepted:false,error:''});
   history.replaceState(null,'','#choose');
  }
  imported=true;save();notify('New photo added. Previous graphics and text cleared.');
 }catch(error){notify(error.message||'Your photo could not be saved. Try a smaller image.');}
 finally{photoBusy=false;render(!(startFresh&&imported));}
}
app.addEventListener('dragover',event=>{
 const zone=event.target.closest('[data-photo-drop]');if(!zone||!event.dataTransfer?.types.includes('Files'))return;
 event.preventDefault();event.dataTransfer.dropEffect=photoBusy||aiBusy?'none':'copy';zone.classList.add('is-drag-over');
});
app.addEventListener('dragleave',event=>{const zone=event.target.closest('[data-photo-drop]');if(zone&&!zone.contains(event.relatedTarget))zone.classList.remove('is-drag-over');});
app.addEventListener('drop',async event=>{
 const zone=event.target.closest('[data-photo-drop]');if(!zone)return;
 event.preventDefault();zone.classList.remove('is-drag-over');await receivePhoto(event.dataTransfer?.files[0]);
});
function choose() {
 const d=currentDesign(state.designId),own=state.source==='photo',hasPhoto=Boolean(state.photo);
 return `${designSteps(state.model?1:0,locale())}<section class="flow wrap editor-flow v35-editor">${stationContext()}<div class="v35-editor-heading"><div><p class="v35-kicker">A LITTLE MORE YOU.</p><h1>${locale()==='zh-CN'?'让灵感，成为你的设计。':'Make it yours.'}</h1></div><a class="text-button" href="#my-designs">${locale()==='zh-CN'?'本机保存的设计 →':'Saved on this browser →'}</a></div>${phonePicker()}<div id="case-style-panel">${caseStylePicker(stockSelection(state.model),state.caseMaterial,{lang:locale(),scoped:Boolean(stockScope)})}</div><div id="phone-color-picker">${colorPicker(stockSelection(state.model,state.caseMaterial)?.colors||[],state.phoneColor,locale(),colorNotice)}</div>
 <div class="choose-layout">
  <div class="source-switch editor-sources" role="group" aria-label="Design source"><button type="button" data-source="collection" aria-pressed="${!own}" ${photoBusy?'disabled':''}>The collection</button><button type="button" data-source="photo" aria-pressed="${own}" aria-busy="${photoBusy}" ${photoBusy?'disabled':''}>${photoBusy?'<i class="studio-spinner"></i> Reading your photo…':icon('upload',15)+' Your photo'}</button></div>
  <div class="large-preview" ${own?'data-photo-drop':''} aria-busy="${photoBusy}" style="--card:${own?'#eeece7':d.color}">
   ${own&&!hasPhoto&&!state.keepCollection?`<div class="photo-placeholder">${icon('image',32)}<h2>Your photo goes here.</h2><label class="button primary" for="photo-file">Upload a photo ${icon('upload',17)}</label></div>`:`<div class="large-case artwork-canvas">${personalizedPreview(state,state.model||phoneModels[0],own?'Your photo':d.name,comparing)}</div>`}
   ${!own||hasPhoto||state.keepCollection?`<button type="button" class="canvas-open-hit" data-action="open-canvas" aria-label="Expand to edit"><span>${icon('scan',16)} Expand to edit</span></button>`:''}
  </div>
  <div class="choose-details"><h1 class="sr-only">${own?'Make it personal.':d.name+'.'}</h1>
   <input class="file-input" type="file" id="photo-file" accept="image/jpeg,image/png,image/webp" aria-label="Upload your photo" ${photoBusy?'disabled':''}>
   ${own?'':`<details class="editor-panel" data-editor-panel="collection" ${editorPanels.collection?'open':''}><summary><span class="editor-tool-icon" aria-hidden="true">${icon('image',18)}</span><span>Collection</span><small>${esc(d.name)}</small><span class="editor-chevron" aria-hidden="true">⌄</span></summary><div class="editor-panel-body"><fieldset class="design-choices visual-design-choices"><legend class="sr-only">Pick a design</legend>${designs.map(item=>`<button type="button" data-design="${item.id}" class="design-thumbnail ${d.id===item.id?'selected':''}" aria-label="${item.name}" aria-pressed="${d.id===item.id}" style="--swatch:${designFor(item.id).background}"><span class="design-thumbnail-case">${casePreview(item.id,state.model||phoneModels[0])}</span><span class="design-thumbnail-check" aria-hidden="true">${d.id===item.id?'✓':''}</span></button>`).join('')}</fieldset></div></details>`}
   ${stylePanel(state,aiJob,effectPanelOpen,membership,aiUi)}${creativeLibrary()}
   ${own&&state.ai?'<p class="effect-selection">✓ AI image applied · You can adjust the crop or replace the photo above.</p>':''}
   <div class="editor-next"><form id="design-form"><button class="button primary full" type="submit" ${photoBusy||passBusy||own&&!hasPhoto?'disabled':''}>${passBusy?(locale()==='zh-CN'?'正在检查设计…':'Checking your design…'):(locale()==='zh-CN'?'预览确认':'Review')} ${arrow()}</button></form><p class="v35-page-note">${locale()==='zh-CN'?'下一步确认机型和设计。':'Next, check your phone model and design.'}</p></div>
  </div>
 </div>${canvasEditor()}</section>`;
}
function privateWorkspaceNotice(){
 const zh=locale()==='zh-CN';
 return `<section class="v35-page v35-wrap v35-empty"><h1>${zh?'请先核实登录状态。':'Check your sign-in first.'}</h1><p role="alert">${zh?'当前私有视图已清空，设计仍保留在原身份的本机空间。重新载入后从服务端核实身份。':'The private view is cleared. Designs remain in their original local workspace. Reload to verify your session with the server.'}</p><button class="button primary" data-action="reload-private-workspace">${zh?'重新载入':'Reload'}</button><a class="text-button" href="#home">${zh?'返回首页':'Home'}</a></section>`;
}
async function loadLocalDesigns(){
 localDesignBusy=true;localDesignError='';
 try{
  // Frozen preview templates can survive their removal from the current catalog.
  const rows=await privateRead('saved-designs')||[];
  for(const row of rows)if(row.phoneTemplate?.id?.startsWith('supplier-'))registerSupplierTemplates([row.phoneTemplate]);
  localDesigns=await library.list();
 }catch(error){localDesigns=[];localDesignError=error.message;}
 finally{localDesignBusy=false;}
}
async function restoreLocalDesign(pass){
 const p=readPass(pass.code,pass);
 if(p.source==='photo')await privateWrite('draft-photo',p.photo);
 workspace.check();finishInlineText();
 Object.assign(state,{source:p.source,designId:p.designId,model:phoneModels.includes(p.model)||stockCatalogStatus!=='ready'?p.model:'',caseMaterial:p.caseMaterial||'',phoneTemplateId:p.phoneTemplateId,phoneColor:p.phoneColor||null,photo:p.source==='photo'?p.photo:'',effect:p.effect,intensity:p.intensity,zoom:p.zoom,x:p.x,y:p.y,ai:p.ai||null,aiJobId:null,photoOrigin:'upload',photoArtwork:p.source==='photo'?structuredClone(p.addedArtwork||[]):[],photoPlacement:structuredClone(p.photoPlacement||null),keepCollection:Boolean(p.collectionLayout),artworkLayouts:{},pass:null,job:null,editOrderId:null});
 if(p.source==='collection')state.artworkLayouts[p.designId]={zoom:p.zoom,x:p.x,y:p.y,artworkEdits:structuredClone(p.artworkEdits||{}),addedArtwork:structuredClone(p.addedArtwork||[])};
 if(p.collectionLayout)state.artworkLayouts[p.designId]={...structuredClone(p.collectionLayout),addedArtwork:[]};
 if(stockCatalogStatus==='ready'&&!stockSelection(state.model,state.caseMaterial))state.caseMaterial='';
 const currentTemplate=stockSelection(state.model,state.caseMaterial)?.templateId;
 const templateChanged=Boolean(currentTemplate&&currentTemplate!==state.phoneTemplateId);
 if(currentTemplate)state.phoneTemplateId=currentTemplate;
 syncDraftColor();aiJob=null;selectedArtwork=null;comparing=false;reviewPass=null;save();go('choose');
 if(templateChanged)notify(locale()==='zh-CN'?'机型模板已变化，请重新确认预览。':'The phone template changed. Please preview your design again.');
 if(!state.model)notify('This phone model is out of stock or unavailable. Please choose again.');
}
async function prepareDesignReview(submitted){
 if(!phoneModels.includes(submitted.model))throw Error('Choose your phone model first.');
 if(submitted.source==='photo'&&!isPhoto(submitted.photo))throw Error('Choose a photo first.');
 await refreshStockChoices();
 if(!submitted.caseMaterial)throw Error('Choose your case style first.');
 const available=stockSelection(submitted.model,submitted.caseMaterial);
 if(!available)throw Error(stockScope?'This phone model is out of stock or unavailable. Please choose again.':'This phone model is unavailable. Please choose again.');
 if(submitted.phoneTemplateId&&submitted.phoneTemplateId!==available.templateId){state.phoneTemplateId=available.templateId;throw Error('The phone template changed. Please review your design again.');}
 assertCurrentColor(submitted,available);
 const pass=createPersonalPass({...layoutSelection(submitted),phoneTemplateId:available.templateId});
 return pass;
}
function closeDesignReview(){reviewPass=null;reviewSaved=false;go('choose');}
function passPage() {
 const pass=state.pass,zh=locale()==='zh-CN',say=(en,cn)=>zh?cn:en;
 if(!pass)return `<section class="empty wrap"><h1>${say('Choose your photo first.','先选择你的照片。')}</h1><a class="button primary" href="#choose">${say('Create a design','开始设计')}</a></section>`;
 const order=orderForCode(orderBook,pass.code);
 if(isProviderOrder(order))return `<section class="empty wrap"><p>${say('Opening your order…','正在打开订单…')}</p><a class="button primary" href="#${esc(providerOrderRoute(order))}">${say('Open order','打开订单')}</a></section>`;
 const price=order?money(order.priceCents):PRINT_PRICE;
 return `<section class="flow wrap review-flow payment-flow v35-checkout"><div class="ai-heading"><h1>${say('Your design is saved.','设计已保存。')}</h1><p>${order?say('Demo order — no real payment was taken.','演示订单，未实际收款。'):say('Review your design before placing an order.','请确认设计后下单。')}</p></div><div class="ai-order-layout"><div class="checkout-preview"><div class="checkout-case">${passPreview(pass)}</div><h2>${passName(pass)}</h2><p>${esc(pass.model)}${pass.caseMaterial?' · '+esc(caseMaterialLabel(pass.caseMaterial,locale())):''}</p>${effectCaption(pass)}</div><div class="ai-order-card">${order?`<p class="eyebrow">${esc(orderStatus(order.status,order.refund))} · ${say('DEMO','演示')}</p><h2>${esc(order.currency||'USD')} ${price}</h2>`:''}${previewStationPanel(order,{station:scannedStation,scope:stockScope,lang:locale()})}<a class="button secondary full" href="#choose" data-action="new-order-from-pass">${say('Use this design for a new order','使用此设计重新下单')}</a>${order?.server?`<details class="payment-receipt"><summary>${say('Order details','订单详情')}</summary><p>${esc(order.id)}</p><a class="text-button" href="#orders">${say('View all my orders →','查看全部订单 →')}</a></details>`:''}</div></div></section>`;
}
function publicStationPage(legacy=false){
 return locationsPage({lang:locale(),station:scannedStation,hasScope:Boolean(stockScope),error:stationError,busy:passBusy,legacy});
}
function stationContext(){
 if(!scannedIds)return '';
 const zh=locale()==='zh-CN';
 return `<section class="station-context" aria-label="${zh?'当前打印设备':'Selected print station'}">${scannedStation?`${stationIdentity(scannedStation,{lang:locale()})}<p class="device-scan-notice">${zh?'已选择此设备。已有订单可确认推单，新设计将在此设备打印。':'Station selected. Confirm an existing order here, or create a new design.'}</p>`:`${lastScannedStation?stationIdentity({...lastScannedStation,coordinates:null},{lang:locale()})+`<small>${zh?'上次读取的设备资料，当前待核实':'Previously loaded station details; verification pending'}</small>`:''}<p role="status">${esc(deviceInfoErrorMessage(stationError,locale()))}</p><button class="text-button" data-action="refresh-device-info" ${passBusy?'disabled':''}>${zh?'刷新设备信息':'Refresh station details'}</button>`}</section>`;
}
async function savedOrderRoute(id){
 const order=await refreshOrder(id);
 state.pass=order.pass;
 state.job=order.stationId&&['printing','ready','collected'].includes(order.status)?{pass:order.pass,stationId:order.stationId,status:order.status,orderId:order.id}:null;
 if(isProviderOrder(order))paymentOrder=order;
 save();return isProviderOrder(order)?'payment?order='+order.id:'pass';
}
function ordersPage(){return `<section class="flow wrap v35-orders" aria-busy="${orderLoading}">${stationContext()}<div class="ai-heading"><p class="eyebrow">YOUR DESIGNS, ALL TOGETHER.</p><h1>My orders.</h1><p>Your orders are saved on the server and accessible from this browser.</p></div><button class="text-button" data-action="refresh-orders" ${orderLoading?'disabled':''}>Refresh orders ↻</button>${orderLoading?'<p class="v35-order-notice" role="status">Loading your orders…</p>':orderError?`<p class="error" role="alert">${esc(orderError)}</p>`:orderRows.length?`<div class="order-list">${orderRows.map(o=>`<article class="order-row"><div><span class="eyebrow">${esc(o.progress?progressPaymentText(o.progress,locale()):orderStatus(o.status,o.refund))} · ${paymentLabel(o.mode)}</span><h2>${esc(o.model_name)}</h2>${o.case_material?`<p>${esc(caseMaterialLabel(o.case_material,locale()))}</p>`:''}<p>${deliveryLabel(o.fulfillment_type,locale())}</p>${progressPanel(o.progress,{lang:locale(),compact:true})}${o.refund?`<p>${esc(orderStatus(o.status,o.refund))}</p>`:''}<p>${esc(o.reference)}</p><small>${new Date(o.created_at).toLocaleString(locale())}</small></div><div><strong>${esc(o.currency)} ${Number(o.amount).toFixed(2)}</strong><button class="button secondary" data-action="view-order" data-id="${esc(o.reference)}">${o.status==='pending'?(locale()==='zh-CN'?'继续付款 →':'Continue payment →'):(locale()==='zh-CN'?'查看打印进度 →':'View print progress →')}</button></div></article>`).join('')}</div><div class="pass-actions">${orderPage>1?`<button class="text-button" data-action="orders-page" data-page="${orderPage-1}">← Previous</button>`:''}${orderHasMore?`<button class="text-button" data-action="orders-page" data-page="${orderPage+1}">Next →</button>`:''}</div>`:'<div class="empty"><h2>Your first design is waiting.</h2><p>Confirm a print order to see it here.</p><a class="button primary" href="#choose">Create a design →</a></div>'}<p class="demo-note">Keep this browser’s site data to retain access to your orders. Test payments and demo payments do not charge money.</p></section>`;}
function orderStatus(status,refund){if(refund)return ({requested:'Checking refund status.',pending:'Refund processing.',succeeded:'Payment refunded.',failed:'Refund could not be completed.'})[refund.status]||'Checking refund status.';return ({pending:'Awaiting payment',paid:'Paid',printing:'Printing',ready:'Ready to collect',completed:'Collected',collected:'Collected',cancelled:'Cancelled'})[status]||status;}
function isProviderOrder(order){return (/^(stripe|airwallex)_(test|live)$/.test(order?.mode||'')||order?.mode==='free_test');}
function providerName(provider){return provider==='free'?(locale()==='zh-CN'?'0 元免付联调':'No-charge test'):provider==='airwallex'?'Airwallex':'Stripe';}
function paymentLabel(mode){return ({free_test:locale()==='zh-CN'?'0 元免付联调':'NO-CHARGE TEST',stripe_test:'STRIPE TEST',stripe_live:'STRIPE',airwallex_test:'AIRWALLEX TEST',airwallex_live:'AIRWALLEX',demo:'DEMO PAYMENT'})[mode]||'ORDER';}
async function openPaymentCheckout(id){
 if(devicePrinting.enabled){const order=await refreshOrder(id);paymentOrder=await prepareDeviceOrder(order,stockScope,{save:rememberOrder});}
 const data=await orderRequest(id+'/checkout/',{method:'POST',body:{}});
 if(data.provider==='airwallex')await openAirwallexCheckout(data);
 else location.assign(stripeCheckoutUrl(data.checkout_url));
}
function deviceFulfillmentPanel(order){
 if(!isPickup(order))return '';
 if(!order.mode.endsWith('_live')&&order.mode!=='free_test')return previewStationPanel(order,{station:scannedStation,scope:stockScope,lang:locale()});
 const zh=locale()==='zh-CN',say=(en,cn)=>zh?cn:en,f=order.fulfillment,v=fulfillmentView(order);
 if(['refund','closed'].includes(v.state))return '';
 if(!f&&!scopeIds(stockScope))return `<section class="device-fulfillment"><h3>${say('Print at a station','设备打印')}</h3>${stationScanPrompt(locale())}</section>`;
 if(!devicePrinting.enabled)return `<section class="device-fulfillment"><h3>${say('Print at a station','设备打印')}</h3>${f?stationIdentity({name:f.device_name,location:f.device_location,number:f.device_number,device_id:f.device_id,coordinates:f.device_coordinates},{lang:locale(),navigation:!pickupContext()}):scannedStation?stationIdentity(scannedStation,{lang:locale(),navigation:!pickupContext()}):''}<p role="status">${say('Sending orders to this station is not available yet. Your order is saved. Please contact staff.','设备推单暂未开放，订单已保存，请联系工作人员。')}</p>${order.status==='paid'?`<button class="button primary full" disabled>${say('I’m at this printer — send order','确认在打印机前并推单')}</button>`:''}</section>`;
 const simulationNotice=f?.simulated?`<p role="status">${say('Direct backend simulation — no physical printing or dispensing.','服务端直连模拟：不会实际打印或出货。')}</p><p>${say('Simulation progress: ','模拟进度：')}${esc(v.phase||v.state)}</p>`:'';
 const ids=scopeIds(stockScope),selection=stockSelection(order.pass.model,order.pass.caseMaterial);
 return `<section class="device-fulfillment" aria-label="${say('Station printing','设备打印')}"><h3>${say('Print at a station','设备打印')}</h3>${simulationNotice}${f?`${stationIdentity({name:f.device_name,location:f.device_location,number:f.device_number,device_id:f.device_id,coordinates:f.device_coordinates},{lang:locale(),navigation:!pickupContext()})}${v.releasePending?`<button class="button primary full" disabled>${say('Print now','立即打印')}</button><small role="status">${f.zero_release_unconfirmed?say('Your order was sent. Zero-amount printing is awaiting supplier confirmation.','订单已推送，0 元开印仍待供应商确认支持。'):say('Immediate printing is unavailable at this station. Your order is saved; please contact staff.','此设备暂不能确认开印，订单已保存，请联系工作人员。')}</small>`:''}${v.canPrint?`<button class="button primary full" data-action="confirm-device-print" ${passBusy?'disabled':''}>${say('Print now','立即打印')}</button><small>${say('Confirm that you are at this station before printing.','请确认你已在这台设备前。')}</small>`:''}${(v.state==='draft'||v.canRetry)?`<button class="button primary full" data-action="send-device-order" ${passBusy?'disabled':''}>${order.status==='paid'?say('I’m at this printer — send order','确认在打印机前并推单'):say('Prepare print files','准备打印文件')}</button>`:''}`:
 ids?`${scannedStation?stationIdentity(scannedStation,{lang:locale(),navigation:!pickupContext()}):`<p>${esc(deviceInfoErrorMessage(stationError,locale()))}</p><small>${say('Device ID','设备编号')}：${esc(ids.device_id)}</small><button class="text-button" data-action="refresh-device-info" ${passBusy?'disabled':''}>${say('Refresh station details','刷新设备信息')}</button>`}${selection&&scannedStation?`<div class="checkout-case">${passPreview({...order.pass,phoneTemplateId:selection.templateId})}</div><p>${say('Check this station’s template before sending.','请确认此设备的机型预览，再发送订单。')}</p><button class="button primary full" data-action="send-device-order" ${passBusy?'disabled':''}>${order.status==='paid'?say('I’m at this printer — send order','确认在打印机前并推单'):say('Use this printer','使用此打印设备')}</button>`:`<p>${scannedStation?say('This station has no stock for this phone model and case style. Scan another station.','此设备暂无该机型和款式的库存，请扫描其他设备。'):''}</p>`}`:
 stationScanPrompt(locale())}</section>`;
}
function providerOrderPage(order){
 const provider=providerName(order.mode.split('_')[0]);
 const returned=new URLSearchParams(location.hash.split('?')[1]||'').get('result')==='success';
 const view=paymentState(order,{returned,exhausted:paymentPollCount>=12});
 const oldReceipt=document.querySelector('.payment-receipt');
 const receiptOpen=oldReceipt?.dataset.order===order.id&&oldReceipt.open;
 const headline=order.progress&&!order.refund&&!view.pending?progressPaymentText(order.progress,locale()):view.title;
 const headingMessage=order.progress&&!order.refund&&!view.pending?(locale()==='zh-CN'?'订单已保存，打印与出货进度见下方。':'Your order is saved. See printing and dispensing progress below.'):view.message;
 const canStartNew=['ready','completed','collected','cancelled'].includes(order.status)||order.refund?.status==='succeeded';
 return `<section class="flow wrap review-flow payment-flow v35-checkout ${view.fulfilled?'payment-fulfilled':''}" data-active-order="${esc(order.id)}"><div class="ai-heading">${view.fulfilled?'':`<p class="eyebrow">${paymentLabel(order.mode)}</p>`}<h1>${esc(headline)}</h1><p role="status">${esc(headingMessage)}</p></div>${progressPanel(order.progress,{lang:locale()})}<div id="pickup-station-panel">${pickupStationPanel()}</div>
 <div class="ai-order-layout"><div class="checkout-preview"><div class="checkout-case">${passPreview(order.pass)}</div><h2>${passName(order.pass)}</h2><p>${esc(order.pass.model)}${order.pass.caseMaterial?' · '+esc(caseMaterialLabel(order.pass.caseMaterial,locale())):''}</p></div>
 <div class="ai-order-card" aria-busy="${passBusy}">${view.fulfilled?'':`<p class="eyebrow">${esc(orderStatus(order.status,order.refund))}</p><h2>${esc(order.currency)} ${money(order.priceCents)}</h2>`}
 ${order.mode==='free_test'?`<p class="payment-environment">${locale()==='zh-CN'?'0 元免付联调，不产生实际收款。':'No-charge test order. No payment was collected.'}</p>`:order.mode.endsWith('_test')?`<p class="payment-environment">${provider} test mode · No real charge.</p>`:view.pending?'<p class="payment-environment">Live payment · Your payment method will be charged.</p>':''}
 ${orderActionError||paymentError?`<p class="error" role="alert">${esc(orderActionError||paymentError)}</p>`:''}
 ${passBusy?`<p role="status" aria-live="polite">${locale()==='zh-CN'?'正在处理，请稍候…':'Processing your request… Please wait.'}</p>`:''}
 ${view.canPay&&isPickup(order)?`<button class="button primary full" data-action="pay-provider" data-id="${esc(order.id)}" ${passBusy?'disabled':''}>${passBusy?'Opening secure checkout…':`Continue to ${provider}`}</button>`:''}
 ${deliveryStatusPanel(order,{lang:locale(),busy:passBusy})}${deviceFulfillmentPanel(order)}
 <button class="text-button payment-refresh" data-action="refresh-payment" ${passBusy?'disabled':''}>${locale()==='zh-CN'?'刷新订单进度':'Refresh order progress'}</button>

 <details class="payment-receipt" data-order="${esc(order.id)}" ${receiptOpen?'open':''}><summary><span>Order details</span><span>${view.fulfilled?`${esc(order.currency)} ${money(order.priceCents)}`:''}</span></summary><div class="payment-receipt-body"><dl><div><dt>Order number</dt><dd>${esc(order.id)}</dd></div><div><dt>Delivery method</dt><dd>${deliveryLabel(order.fulfillmentType,locale())}</dd></div><div><dt>Payment method</dt><dd>${provider}</dd></div><div><dt>Order status</dt><dd>${esc(orderStatus(order.status,order.refund))}</dd></div></dl><a class="text-button" href="#orders">View all my orders →</a><p class="field-note">Keep this browser’s site data to retain access to your order.</p></div></details>
 ${canStartNew?'<a class="button secondary full payment-next-design" href="#choose">Create a new design →</a>':''}</div></div></section>`;
}
function paymentPage(){return paymentOrder?providerOrderPage(paymentOrder):`<section class="empty wrap v35-checkout" aria-busy="${!paymentError}"><h1>Payment status</h1><p class="${paymentError?'error':'v35-order-notice'}" role="${paymentError?'alert':'status'}">${esc(paymentError||'Loading your order…')}</p><button class="text-button" data-action="refresh-payment">Refresh payment status</button><a class="text-button" href="#orders">View all my orders →</a></section>`;}
function schedulePaymentPoll(){
 stopPaymentPolling();
 if(!paymentOrder)return;
 const hash=location.hash,id=paymentOrder.id;
 stopPaymentPolling=startVisiblePolling({interval:5000,
  enabled:()=>location.hash===hash&&!passBusy&&!photoBusy&&!aiBusy&&(!['dispensed','cancelled','closed','refunded','test','delivery','unspecified'].includes(paymentOrder?.progress?.code)||['requested','pending'].includes(paymentOrder?.refund?.status)),
  refresh:async alive=>{const before=paymentOrder;try{
   const data=await orderRequest(id+'/progress/');
   if(!alive()||location.hash!==hash||passBusy||paymentOrder!==before||paymentOrder?.id!==id)return;
   paymentOrder=mergeOrderProgress(paymentOrder,data);syncStationFinder();paymentPollCount++;paymentError='';render(true);
  }catch{if(alive()&&location.hash===hash){paymentError=locale()==='zh-CN'?'进度暂时无法刷新，已保留上次结果。':'Progress could not be refreshed. Showing the last known result.';render(true);}}}
 });
}
startVisiblePolling({interval:15000,enabled:()=>location.hash.split('?')[0]==='#orders'&&!passBusy&&!photoBusy&&!aiBusy,
 refresh:async alive=>{const hash=location.hash,page=orderPage,nav=navigationId;try{
  const data=await orderRequest('?page='+page);
  if(!alive()||location.hash!==hash||orderPage!==page||navigationId!==nav)return;
  orderRows=data.results;orderHasMore=data.has_more;orderError='';render(true);
 }catch{if(alive()&&location.hash===hash&&navigationId===nav){orderError=locale()==='zh-CN'?'订单进度暂时无法刷新，已保留上次结果。':'Order progress could not be refreshed. Showing the last known results.';render(true);}}}
});
function quoteBreakdown(pass,price,editing){
 const provider=providerName(paymentConfig?.provider),paidCheckout=['stripe','airwallex'].includes(paymentConfig?.provider)&&!editing;
 const hasAI=pass.source==='photo'&&Boolean(pass.ai);
 return `<section class="print-quote" aria-label="Price details"><h2>Price details</h2><dl>
  <div><dt>Standard printing · 1 case</dt><dd>${price}</dd></div>
  <div><dt>Graphics & text</dt><dd>Included</dd></div>
  <div><dt>AI image</dt><dd>${hasAI?'Already generated':'Not used'}</dd></div>
  ${editing?`<div><dt>Already paid · Demo</dt><dd>${price}</dd></div><div><dt>Design update</dt><dd>$0.00</dd></div>`:''}
  <div class="quote-total"><dt>${paidCheckout||paymentConfig?.zero_price_test?'Total due':'Total due · Demo'}</dt><dd>${editing?'$0.00':price}</dd></div>
 </dl>${hasAI?'<p class="quote-note">AI generation uses your separate allowance. It is not charged again with this print.</p>':''}<p class="quote-note">${devicePrinting.simulated?(locale()==='zh-CN'?'服务端直连模拟：0 元、不扣款、不实际打印。':'Direct backend simulation: no charge and no physical printing.'):paymentConfig?.zero_price_test?(locale()==='zh-CN'?'0 元免付联调：不扣款，可推单；0 元开印待供应商确认。':'No-charge integration test: orders can be sent; zero-amount printing awaits supplier confirmation.'):paidCheckout?(paymentConfig.mode==='test'?`${provider} test mode · No real charge.`:`Pay securely with ${provider}. Your payment method will be charged.`):'No real payment is taken in this demo.'}</p></section>`;
}
function checkoutPage(){
 if(!checkoutDraft)return '<section class="empty wrap"><h1>Choose your design first.</h1><a class="button primary" href="#choose">Back to your design</a></section>';
 const {pass,editId}=checkoutDraft,order=editId?orderBook.orders[editId]:null,locked=editId&&order?.status!=='paid';
 const delivery=order?.fulfillmentType||checkoutDraft.fulfillmentType||'pickup',pickup=delivery==='pickup';
 const price=order?money(order.priceCents):PRINT_PRICE;
 const provider=providerName(paymentConfig?.provider),paidCheckout=['stripe','airwallex'].includes(paymentConfig?.provider)&&!editId;
 return `<section class="flow wrap review-flow v35-checkout">${pickup?steps(1):''}<a class="back-link" href="#choose">← Keep editing</a><div class="ai-heading"><p class="eyebrow">REVIEW YOUR PRINT · ${paymentConfig?.zero_price_test?provider:paidCheckout?provider.toUpperCase():paymentConfig||editId?'DEMO':'CHECKOUT'}</p><h1>${editId?'Make it just right.':'Happy with your design?'}</h1><p>Check your artwork and phone model before confirming.</p></div><div class="ai-order-layout"><div class="checkout-preview"><div class="checkout-case">${passPreview(pass)}</div><h2>${passName(pass)}</h2><p>${esc(pass.model)}${pass.caseMaterial?' · '+esc(caseMaterialLabel(pass.caseMaterial,locale())):''}</p>${effectCaption(pass)}</div><div class="ai-order-card">${singlePrintNotice(checkoutDraft,locale())}${!editId?deliveryOptions(delivery,locale(),{pickupDetails:pickupStationPanel()}):''}${pickup&&scannedStation?stationIdentity(scannedStation,{lang:locale(),navigation:false}):''}${pickup&&(paymentConfig||editId)?quoteBreakdown(pass,price,Boolean(editId)):''}${pickup?`<p class="field-note">${paidCheckout||paymentConfig?.zero_price_test?'Check your design carefully. The artwork is locked when the payment order is created.':'You can edit your design until printing starts. Saving a revision updates your design. After printing starts, changes need a new order.'}</p>`:''}${!pickup?`<p class="delivery-notice" role="status">${locale()==='zh-CN'?'快递／空运配送暂未开放，设计已保存，暂不收款。可返回继续编辑，或选择设备现场自取。':'Courier and air delivery are coming soon. Your design is saved and checkout is paused. You can keep editing or choose on-site pickup.'}</p>`:paymentLoading?'<p role="status" aria-live="polite">Loading checkout… If the service is busy, we will retry up to 3 times.</p>':!editId&&(!paymentConfig?.available||paymentError)?`<p class="error" role="alert">${esc(paymentError||'Payment is unavailable. Please try again later.')}</p><button class="text-button" data-action="refresh-payment">Reload checkout</button>`:!PRINT_AVAILABLE&&!editId?'<p class="error">Printing is unavailable. Please reload and try again.</p>':locked?'<p class="error">This order has started printing. Return to My design to create a new order.</p>':`<form id="print-checkout-form">${!editId?checkoutEmailField(membership):''}<label class="ai-consent"><input name="accepted" type="checkbox" required><span>I confirm this design and phone model. ${editId?'Update my existing design at no extra printing charge.':paidCheckout?`Pay ${price} for one case with ${provider}.${paymentConfig.mode==='test'?' Test mode: no real charge.':''}`:devicePrinting.simulated?(locale()==='zh-CN'?'创建 0 元模拟订单，手机确认后模拟打印，不会操作真实设备。':'Create a no-charge simulation order. Phone confirmation starts simulated printing only.'):paymentConfig?.zero_price_test?'Create a no-charge integration order. Confirm at the station to start a real print.':`Simulate a ${price} payment for one print. No real charge.`} The design and any photo will be securely saved with this order.</span></label><button class="button primary full" ${!editId&&!pickupCheckoutReady()?'disabled':''}>${editId?'Save design changes':paidCheckout?`Pay ${price} with ${provider}`:paymentConfig?.zero_price_test?'Complete free test order':`Confirm ${price} test order`}</button></form>`}</div></div></section>`;
}
function render(preserveScroll=false) {
  finishInlineText();
  cleanupAIStudio();
  cleanupShell();
  cleanupHomePhone();
  cleanupPhoneModels();
  const oldY=window.scrollY;
  const [route='home',query='']=location.hash.slice(1).split('?');
  if(!['choose','review'].includes(route)){reviewPass=null;reviewSaved=false;}
  canvasObserver?.disconnect();canvasObserver=null;canvasHome=null;
  if(route!=='choose')canvasExpanded=false;
  if(route!=='choose')effectPanelOpen=false;
  document.body.classList.toggle('canvas-editor-open',canvasExpanded);
  const pages={review:()=>designReview({pass:reviewPass,preview:passPreview,lang:locale(),busy:passBusy,saved:reviewSaved}),account:()=>customerPage(membership,customerUI),'my-designs':()=>myDesignsPage({rows:localDesigns,lang:locale(),preview:passPreview,error:localDesignError,busy:localDesignBusy,guest:workspace.owner==='guest'}),choose,pass:passPage,kiosk:()=>publicStationPage(true),designs:()=>worksPage({works:designs,preview:casePreview,lang:locale(),params:new URLSearchParams(query)}),work:()=>workDetailPage({works:designs,preview:casePreview,lang:locale(),params:new URLSearchParams(query)}),'how-it-works':()=>tutorialPage({lang:locale()}),about:()=>aboutPage({lang:locale()}),locations:publicStationPage,printers:publicStationPage,ai:()=>aiPage(aiJob,membership,aiBusy,{...aiUi,phoneModels,stockCatalogStatus}),membership:()=>membershipInfoPage({account:membership,lang:locale()}),checkout:checkoutPage,orders:ordersPage,payment:paymentPage};
  app.classList.toggle('is-ai-studio',route==='ai'&&aiJob?.mode==='live');
  app.classList.toggle('is-editor',route==='choose');
  document.body.classList.toggle('v35-home-page',!Object.hasOwn(pages,route));
  const privateRoute=['choose','review','pass','ai','membership','my-designs','checkout','orders','payment'].includes(route);
  document.body.dataset.v35Route=route;
  app.innerHTML=header()+`<main id="main" tabindex="-1">${catalogStatus==='unavailable'?'<div class="catalog-warning" role="status">Prices and AI previews could not be loaded. Your saved designs are still available. <button class="text-button" data-action="reload-catalog">Try again</button></div>':''}${!workspace.active&&privateRoute?privateWorkspaceNotice():(Object.hasOwn(pages,route)?pages[route]:home)()}</main>`+footer();
  if(aiBusy)document.querySelectorAll('[data-ai-action],#ai-credit-form button,#ai-subscription-form button').forEach(el=>el.disabled=true);
  const title=({review:locale()==='zh-CN'?'预览确认':'Review & confirm',account:'My account','my-designs':'My designs',choose:'Choose your case',pass:'Your design pass',kiosk:'Print locations',designs:'Works center',work:'Design details','how-it-works':'How to use',about:'About POPOMO',locations:'Print locations',printers:'Print locations',ai:'Your AI render',membership:'AI membership',checkout:'Review print order',orders:'My orders',payment:'Payment status'})[route];
  document.title=title?`${t(title)} · POPOMO`:t('POPOMO — A little more you.');
  localize(app);document.querySelector('.skip-link').textContent=t('Skip to content');
  cleanupAIStudio=mountAIStudio(app,aiJob,aiUi);
  cleanupShell=mountShell(app,{lang:locale(),onLanguage:value=>{const select=document.querySelector('#language');select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('[data-shell-menu]')?.focus({preventScroll:true});}});
  document.querySelector('#language').disabled=aiBusy||photoBusy||passBusy;
  document.querySelectorAll('[data-editor-panel]').forEach(bindEditorPanel);
  document.querySelector('.canvas-editor')?.addEventListener('cancel',event=>{event.preventDefault();closeCanvasEditor();});
  document.querySelector('.look-browser')?.addEventListener('cancel',event=>{event.preventDefault();closeAIStudio();});
  observeCanvasPreview();
  if(canvasExpanded)openCanvasEditor();
  else if(effectPanelOpen)openAIStudio();
  highlightArtwork();
  document.querySelector('.crop-panel')?.addEventListener('toggle',e=>cropPanelOpen=e.target.open);
  if(preserveScroll)window.scrollTo(0,oldY);
  else if(new URLSearchParams(query).has('section')){const section=new URLSearchParams(query).get('section');if(['steps','save','print','story','our-story'].includes(section))document.getElementById(section)?.scrollIntoView();else window.scrollTo(0,0);}
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
 if(!event.target.closest('.artwork-canvas [data-layer-id],.artwork-canvas [data-photo-layer],.artwork-gizmo,.text-quick-tools,.artwork-selection-actions,.canvas-toolbar,.canvas-editor-header'))deselectArtwork();
});
document.addEventListener('keydown',event=>{
 if(event.key==='Escape'&&document.querySelector('.studio-render-dialog[open]')){
  if(document.querySelector('.studio-photo-dialog[open]'))return;
  event.preventDefault();go('choose');return;
 }
 if(event.key==='Escape'&&effectPanelOpen){event.preventDefault();if(document.querySelector('.look-browser.is-zoomed'))zoomAIStudio();else closeAIStudio();return;}
 if(['Delete','Backspace'].includes(event.key)&&!event.isComposing&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!event.target.closest('input,textarea,select,[contenteditable],[role="textbox"]')){
  if(deleteSelectedArtwork())event.preventDefault();
 }
 if(event.key==='Escape'&&!artworkDrag&&!event.isComposing){event.preventDefault();if(canvasExpanded&&!inlineTextId)closeCanvasEditor();else{finishInlineText();deselectArtwork();}}
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
 fitCanvasEditor();
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
app.addEventListener('toggle',event=>{const el=event.target;if(!el.isConnected||!el.matches('.pickup-stations .station-navigation'))return;const key=el.closest('[data-station-key]')?.dataset.stationKey;if(key){if(el.open)openStationMaps.add(key);else openStationMaps.delete(key);}},true);
app.addEventListener('click',event=>{if(event.target.closest('.pickup-stations a')&&(stationFinder.state.error||Date.now()-stationFinder.state.loadedAt>60000)){event.preventDefault();void stationFinder.refresh();}},true);
app.addEventListener('click',event=>{if(event.target.matches('input[name=fulfillment_type][value=pickup]')&&checkoutDraft&&!checkoutDraft.editId&&(checkoutDraft.fulfillmentType||'pickup')==='pickup')void requestStationLocation();});
app.addEventListener('change',async event=>{
  if(event.target.matches('#ai-credit-form [name=accepted]'))aiUi.accepted=event.target.checked;
  if(event.target.name==='fulfillment_type'&&checkoutDraft&&!checkoutDraft.editId){
    if(passBusy)return;
    if(!['pickup','courier','air'].includes(event.target.value))return;
    checkoutDraft.fulfillmentType=event.target.value;checkoutDraft.requestKey=crypto.randomUUID();
    if(event.target.value==='pickup')void requestStationLocation();
    await privateWrite('checkout-draft',checkoutDraft);syncStationFinder();render(true);return;
  }
  if(event.target.id==='language'){
    if(aiBusy||photoBusy||passBusy)return;
    finishInlineText();
    const fields=[...app.querySelectorAll('input:not([type=file]),textarea,select:not(#language)')].map(el=>({id:el.id,name:el.name,form:el.form?.id,type:el.type,value:el.value,checked:el.checked}));
    const details=[...app.querySelectorAll('details')].map(el=>el.open);
    setLocale(event.target.value);render(true);
    for(const field of fields){const el=[...app.querySelectorAll('input:not([type=file]),textarea,select:not(#language)')].find(el=>field.id?el.id===field.id:field.name&&el.name===field.name&&el.form?.id===field.form&&(field.type!=='radio'||el.value===field.value));if(el){if(el.type!=='radio')el.value=field.value;if('checked' in el)el.checked=field.checked;}}
    [...app.querySelectorAll('details')].forEach((el,i)=>{if(details[i]!==undefined)el.open=details[i];});
    document.querySelector('#language').focus({preventScroll:true});return;
  }
  if(event.target.id==='station'){state.stationId=event.target.value;save();render(true);document.querySelector('#station')?.focus({preventScroll:true});}
  if(event.target.id==='photo-file'){
    await receivePhoto(event.target.files[0],{startFresh:event.target.hasAttribute('data-home-upload')});
  }
});
app.addEventListener('input',event=>{
  if(event.target.matches('.look-wipe')){aiUi.lookCompare=setLookComparison(document.querySelector('.look-browser'),event.target.value);return;}
  if(event.target.id==='canvas-size'&&selectedArtwork){artworkTarget()[selectedArtwork==='all'?'zoom':'scale']=Number(event.target.value);save();updatePreview();return;}
 if(event.target.matches('[data-ai-compare]')){aiUi.compare=setAIComparison(app,event.target.value);return;}
 if(event.target.matches('[data-inline-text]')){if(!event.isComposing){writeInlineText(event.target);highlightArtwork();}return;}
 if(event.target.dataset.textField){applyTextStyle(event.target.dataset.textField,event.target.value);return;}

  if(event.target.dataset.artwork){const key=event.target.dataset.artwork;setArtwork(key,Number(event.target.value));}
  if(event.target.dataset.crop){const key=event.target.dataset.crop;state[key]=Number(event.target.value);document.getElementById(key+'-value').textContent=state[key]+'%';updatePreview();save();}
  if(event.target.id==='effect-strength'){state.intensity=Number(event.target.value);document.getElementById('intensity-value').textContent=state.intensity+'%';document.getElementById('selected-strength').textContent=state.intensity+'%';updatePreview();save();}
});
app.addEventListener('submit',async event=>{
  if(sessionCheckBusy){event.preventDefault();return;}
  if(event.target.id==='customer-profile-form'){event.preventDefault();await handleCustomer('profile',new FormData(event.target));return;}
  if(event.target.id==='customer-email-form'){event.preventDefault();const fields=new FormData(event.target);await handleCustomer(customerUI.codeSent?'verify':'send',fields);return;}
  if(event.target.id==='ai-credit-form'||event.target.id==='ai-subscription-form'){
    event.preventDefault();if(aiBusy)return;const accepted=new FormData(event.target).has('accepted');
    await confirmAI(event.target.id==='ai-credit-form',accepted);return;
  }

  if(event.target.id==='print-checkout-form'){event.preventDefault();if(passBusy||!checkoutDraft)return;passBusy=true;
    const button=event.target.querySelector('button');button.disabled=true;button.textContent=t('Saving your order…');
    try{
      await syncAIAccount();workspace.check();
      const values=new FormData(event.target),accepted=values.has('accepted'),existing=orderBook.orders[checkoutDraft.editId];let order;
      if(!existing&&checkoutDraft.fulfillmentType&&checkoutDraft.fulfillmentType!=='pickup')throw Error('Courier and air delivery are not available for checkout yet. Your design is saved; no payment has been taken.');
      if(!existing&&!pickupCheckoutReady())throw Error(locale()==='zh-CN'?'请先刷新并确认有该机型库存的网点。':'Refresh station stock and confirm availability before checkout.');
      if(!existing&&!paymentConfig?.available)throw Error('Payment is unavailable. Please reload and try again.');
      if(checkoutDraft.editId&&!existing)throw Error('This order could not be loaded. Open it from My orders and retry.');
      if(existing&&!existing.server){let result;orderBook=await updateDesign('print-orders-v1',b=>{result=commitPrintOrder(b,checkoutDraft.pass,{accepted,editId:existing.id});return result.book;},freshOrders());order=result.order;}
      else{
        checkoutDraft.requestKey||=crypto.randomUUID();await privateWrite('checkout-draft',checkoutDraft);
        const data=existing?await orderRequest(existing.id+'/',{method:'PATCH',body:{quantity:1,accepted,revision:checkoutDraft.revision??existing.revision,snapshot:checkoutDraft.pass}}):await orderRequest('',{method:'POST',body:checkoutBody(checkoutDraft,{accepted,email:String(values.get('email')||''),account:membership,amount:(PRINT_PRICE_CENTS/100).toFixed(2),provider:paymentConfig.provider,mode:paymentConfig.mode})});
        order=await rememberOrder(data);
      }
      if(devicePrinting.enabled&&isProviderOrder(order))order=await prepareDeviceOrder(order,stockScope,{save:rememberOrder});
      state.pass=order.pass;state.job=null;state.editOrderId=null;checkoutDraft=null;await privateWrite('checkout-draft',null);save();
      if(isProviderOrder(order)){paymentOrder=order;go('payment?order='+order.id);if(order.status==='pending'){render(true);await openPaymentCheckout(order.id);}}else go('pass');
    }
    catch(error){if(paymentOrder)paymentError=error.message;if(error.message==='Your sign-in changed. Reload checkout to review your email.'){paymentError=error.message;paymentConfig=null;}notify(error.message);}finally{passBusy=false;render(true);}return;
  }
  if(event.target.id==='design-form'){
    event.preventDefault();if(passBusy||photoBusy)return;
    if(!phoneModels.includes(state.model)){openModelPicker();notify('Choose your phone model first.');return;}
    const submitted={...state},submittedHash=location.hash;passBusy=true;render(true);
    try{
      const pass=await prepareDesignReview(submitted);
      if(location.hash!==submittedHash)return;
      reviewPass=pass;reviewSaved=false;comparing=false;go('review');
    }catch(error){notify(error.message||'The design could not be saved. Please try again.');}
    finally{passBusy=false;if(location.hash.startsWith('#choose'))render(true);}
  }
  if(event.target.id==='v35-work-search'){event.preventDefault();const fields=new FormData(event.target),params=new URLSearchParams({category:String(fields.get('category')||'all'),q:String(fields.get('q')||'').slice(0,100)});go('designs?'+params);}
});
app.addEventListener('click',async event=>{
  const el=event.target.closest('[data-case-material],[data-phone-color],[data-action],[data-design],[data-start-design],[data-source],[data-effect],[data-ai-action],[data-ai-look-example],[data-ai-look-step],[data-look-action],[data-look-mode],[data-ai-group],[data-ai-view],[data-artwork-item],[data-add-graphic],[data-quick-font],[data-quick-color]');if(!el||el.disabled||photoBusy||passBusy||aiBusy||sessionCheckBusy)return;
  if(el.dataset.action==='choose-phone'){openModelPicker();return;}
  if(el.dataset.action==='ai-choose-phone'){openModelPicker(true);return;}
  if(['home-photo','home-ai'].includes(el.dataset.action)){event.preventDefault();openHomePhone(el.dataset.action==='home-photo'?'photo':'ai');return;}
  if(el.dataset.action==='reload-private-workspace'){location.reload();return;}
  if(el.dataset.action==='close-design-review'){closeDesignReview();return;}
  if(['save-local-design','continue-design-checkout','restore-design','delete-design','refresh-designs','restore-legacy-draft'].includes(el.dataset.action)){
   event.preventDefault();passBusy=true;
   try{
    workspace.check();
    if(el.dataset.action==='save-local-design'){
     if(!reviewPass)throw Error('Preview your design again before saving.');
     await library.save(reviewPass,phoneTemplate(reviewPass.model,reviewPass.phoneTemplateId));reviewSaved=true;
     notify(locale()==='zh-CN'?'设计已保存到当前身份的本机空间。':'Design saved on this browser for your current account.');
    }else if(el.dataset.action==='continue-design-checkout'){
     if(!reviewPass)throw Error('Preview your design again before ordering.');
     if(!PRINT_AVAILABLE&&!state.editOrderId)throw Error('Printing is unavailable. Your local design can still be saved.');
     await refreshStockChoices();const available=stockSelection(reviewPass.model,reviewPass.caseMaterial);
     if(!available||available.templateId!==reviewPass.phoneTemplateId)throw Error('The phone template changed. Please review your design again.');
     assertCurrentColor(reviewPass,available);
     const pass=reviewPass;
     checkoutDraft={quantity:1,pass,fulfillmentType:orderBook.orders[state.editOrderId]?.fulfillmentType||checkoutDraft?.fulfillmentType||'pickup',phoneTemplate:phoneTemplate(pass.model,pass.phoneTemplateId),editId:state.editOrderId||null,requestKey:crypto.randomUUID(),revision:orderBook.orders[state.editOrderId]?.revision};
     await privateWrite('checkout-draft',checkoutDraft);reviewPass=null;go('checkout');
    }else if(el.dataset.action==='refresh-designs')await loadLocalDesigns();
    else if(el.dataset.action==='delete-design'){
     await library.remove(el.dataset.id);await loadLocalDesigns();
    }else if(el.dataset.action==='restore-design'){
     const row=localDesigns.find(row=>row.id===el.dataset.id);if(!row)throw Error('This saved design could not be found.');
     await restoreLocalDesign(row.pass);
    }else if(el.dataset.action==='restore-legacy-draft'){
     if(workspace.owner!=='guest')throw Error('Older browser drafts are separate from signed-in accounts.');
     const legacy=JSON.parse(localStorage.getItem('popomo-simple-v1')||'null');
     if(!legacy)throw Error('No older browser draft was found.');
     const photo=await readDesign('draft-photo');
     // Copy only validated design fields, never legacy identity, jobs or orders.
     const pass=createPersonalPass({...layoutSelection({...legacy,photo:legacy.source==='photo'?photo:''}),ai:null});
     await restoreLocalDesign(pass);
    }
   }catch(error){notify(error.message);}
   finally{passBusy=false;render(true);}
   return;
  }
  if(el.dataset.lookAction==='open'){openAIStudio();return;}
  if(el.dataset.lookAction==='close'){closeAIStudio();return;}
  if(el.dataset.lookAction==='zoom'){zoomAIStudio();return;}
  if(el.dataset.lookMode){const dialog=document.querySelector('.look-browser');aiUi.lookMode=setLookMode(dialog,el.dataset.lookMode);updateLookImageState(dialog);return;}
  if(el.dataset.aiLookStep){
   const {group,index}=activeLook(state),next=group.looks[(index+Number(el.dataset.aiLookStep)+group.looks.length)%group.looks.length];
   state.aiExample=next.example.id;state.aiStyle=next.style.id;save();refreshAIStudio();return;
  }
  if(el.dataset.action==='reload-catalog'){location.reload();return;}
  if(el.dataset.action==='refresh-models'){await refreshStockChoices();render(true);return;}
  if(el.dataset.action==='open-canvas'){openCanvasEditor();return;}
  if(el.dataset.action==='close-canvas'){closeCanvasEditor();return;}
  if(el.dataset.action==='rotate-canvas-artwork'&&selectedArtwork){
   const target=artworkTarget();
   if(selectedArtwork==='all'){const phone=document.querySelector('.artwork-canvas .phone-case');target.artworkEdits=rotateGroup(target.artworkEdits,designFor(state.designId).layers,15,phone.clientWidth/phone.clientHeight);}
   else target.rotation=rotationFromPointer({rotation:target.rotation||0,startAngle:0,angle:Math.PI/12});
   save();updatePreview();return;
  }
  if(el.dataset.caseMaterial){const choice=stockSelection(state.model,el.dataset.caseMaterial);if(!choice)return;state.caseMaterial=choice.caseMaterial;state.phoneTemplateId=choice.templateId;syncDraftColor();selectSupplierTemplate(state.model,choice.templateId);save();render(true);return;}
  if(el.dataset.phoneColor){const color=stockSelection(state.model,state.caseMaterial)?.colors?.find(c=>c.code===el.dataset.phoneColor);if(!color)return;state.phoneColor=structuredClone(color);colorNotice=false;reviewPass=null;save();updatePreview();const colors=document.querySelector('#phone-color-picker');colors.innerHTML=colorPicker(stockSelection(state.model,state.caseMaterial).colors,state.phoneColor,locale());colors.querySelector(`[data-phone-color="${color.code}"]`)?.focus();return;}
  if(el.dataset.quickFont){applyTextStyle('font',el.dataset.quickFont);return;}
  if(el.dataset.quickColor){applyTextStyle('color',el.dataset.quickColor);return;}
  if(el.dataset.addGraphic){
   if(extraArtwork().length>=20){notify('You can add up to 20 graphics and text elements.');return;}
   if(!stickers.some(a=>a.id===el.dataset.addGraphic)||state.source==='photo'&&!state.photo&&!state.keepCollection)return;
   finishInlineText();const item={id:'extra-'+crypto.randomUUID(),type:'sticker',asset:el.dataset.addGraphic,x:50,y:55,scale:100,rotation:0};extraArtwork().push(item);selectedArtwork=item.id;save();updatePreview();revealArtwork();return;
  }
  if(el.dataset.artworkItem){selectedArtwork=el.dataset.artworkItem;refreshArtworkControls();document.querySelector(`[data-artwork-item="${selectedArtwork}"]`)?.focus({preventScroll:true});return;}
  if(el.dataset.aiGroup){
   const group=activeLook(state).groups.find(g=>g.example.id===el.dataset.aiGroup);if(!group)return;
   const next=group.looks.find(l=>l.style.id===state.aiStyle)||group.looks[0];state.aiExample=next.example.id;state.aiStyle=next.style.id;save();refreshAIStudio({resetScroll:true});
   document.querySelector(`[data-ai-group="${CSS.escape(el.dataset.aiGroup)}"]`)?.focus({preventScroll:true});return;
  }
  if(el.dataset.aiView){aiUi.mode=setAIView(app,el.dataset.aiView);return;}
  if(el.dataset.aiLookExample){
   const example=aiExamples.find(e=>e.id===el.dataset.aiLookExample),styleId=el.dataset.aiLookStyle;
   if(!example?.results[styleId])return;
   state.aiExample=example.id;state.aiStyle=styleId;effectPanelOpen=true;save();refreshAIStudio();
   document.querySelector(`[data-ai-look-example="${CSS.escape(example.id)}"][data-ai-look-style="${CSS.escape(styleId)}"]`)?.focus({preventScroll:true});return;
  }
  if(el.dataset.aiAction){await handleAI(el.dataset.aiAction);return;}
  if(el.dataset.source){
   if(el.dataset.source==='photo'){openPhotoPicker();return;}
   finishInlineText();
   selectedArtwork=null;state.source=el.dataset.source;comparing=false;history.replaceState(null,'','#choose');save();render(true);return;
  }
  if(el.dataset.design||el.dataset.startDesign){
   event.preventDefault();const startFresh=Boolean(el.dataset.startDesign);photoBusy=true;
   try{await selectCollectionDesign(el.dataset.design||el.dataset.startDesign,{startFresh});}
   catch(error){notify(error.message||'Your design could not be saved. Please try again.');return;}
   finally{photoBusy=false;}
   editorPanels.collection=false;history.replaceState(null,'',`#choose?design=${state.designId}`);render(!startFresh);document.querySelector('[data-editor-panel=collection]>summary')?.focus({preventScroll:true});if(startFresh)notify('New design started. Previous edits cleared.');
   return;
  }
  if(el.dataset.effect){state.effect=el.dataset.effect;comparing=false;effectPanelOpen=true;save();render(true);document.querySelector(`[data-effect="${state.effect}"]`)?.focus({preventScroll:true});return;}
  try {
    if(['refresh-stations','more-stations'].includes(el.dataset.action)){syncStationFinder();await stationFinder.refresh(el.dataset.action==='more-stations');return;}
    if(el.dataset.action==='locate-stations'){await requestStationLocation({force:true});return;}
    if(el.dataset.action==='scan-station'){
      openStationScanner({lang:locale(),onScan:async (destination,{signal})=>{
        const url=new URL(destination),ids=scopeIds(url.search);
        await loadDeviceInfo({deviceId:ids.device_id,shopId:ids.shop_id});
        if(!signal.aborted)location.assign(url.href);
      }});return;
    }
    if(el.dataset.action==='refresh-device-info'){if(passBusy)return;passBusy=true;render(true);try{scannedStation=await readScannedStation();}finally{passBusy=false;render(true);}return;}
    if(el.dataset.action==='confirm-pickup'){
      if(passBusy||!paymentOrder)return;passBusy=true;render(true);
      try{paymentOrder=await rememberOrder(await orderRequest(paymentOrder.id+'/fulfillment/',{method:'POST',body:{fulfillment_type:'pickup',confirmed:true}}));paymentError='';}
      catch(e){paymentError=e.message;notify(e.message);}
      finally{passBusy=false;render(true);}return;
    }
    if(['send-device-order','confirm-device-print'].includes(el.dataset.action)){
      if(passBusy)return;
      try{
        requireDisplayedOrder(paymentOrder,el.closest('[data-active-order]')?.dataset.activeOrder,location.hash);
        passBusy=true;orderActionError='';render(true);
        if(el.dataset.action==='send-device-order')paymentOrder=await prepareDeviceOrder(paymentOrder,stockScope,{save:rememberOrder});
        else{await orderRequest(paymentOrder.id+'/confirm-print/',{method:'POST',body:{confirm:true}});paymentOrder=await refreshOrder(paymentOrder.id);}
        paymentError='';syncStationFinder();schedulePaymentPoll();
      }catch(e){orderActionError=e.message;notify(e.message);}finally{passBusy=false;render(true);}return;
    }
    if(el.dataset.action==='toggle-library'){libraryExpanded=!libraryExpanded;render(true);return;}
    if(el.dataset.action==='edit-text'){if(inlineTextId)finishInlineText();else beginInlineText();return;}
    if(el.dataset.action==='text-submit'){
     if(extraArtwork().length>=20){notify('You can add up to 20 graphics and text elements.');return;}
     finishInlineText();
     const item={id:'extra-'+crypto.randomUUID(),type:'text',...textDraft,text:'Your text',x:50,y:65,scale:100,rotation:0};extraArtwork().push(item);selectedArtwork=item.id;save();updatePreview();openCanvasEditor();beginInlineText();return;
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
    if(['edit-pass','new-order-from-pass'].includes(el.dataset.action)){
      event.preventDefault();const current=orderForCode(orderBook,state.pass.code);if(current?.server){const latest=await refreshOrder(current.id);state.pass=latest.pass;}const p=state.pass;orderBook=await readDesign('print-orders-v1')||freshOrders();const order=orderForCode(orderBook,p.code);selectedArtwork=null;if(p.source==='collection')state.artworkLayouts[p.designId]={zoom:p.zoom,x:p.x,y:p.y,artworkEdits:structuredClone(p.artworkEdits||{}),addedArtwork:structuredClone(p.addedArtwork||[])};state.editOrderId=el.dataset.action==='edit-pass'&&order?.mode==='demo'&&order?.status==='paid'?order.id:null;
      if(p.version===2){if(p.source==='photo')await privateWrite('draft-photo',p.photo);Object.assign(state,{source:p.source,designId:p.designId,model:p.model,caseMaterial:p.caseMaterial||'',phoneTemplateId:p.phoneTemplateId,phoneColor:p.phoneColor||null,photo:p.source==='photo'?p.photo:state.photo,effect:p.effect,intensity:p.intensity,zoom:p.zoom,x:p.x,y:p.y,ai:p.ai||null,photoOrigin:'upload',...(p.source==='photo'?{photoArtwork:structuredClone(p.addedArtwork||[]),photoPlacement:structuredClone(p.photoPlacement||null),keepCollection:Boolean(p.collectionLayout)}:{})});}
      else Object.assign(state,{source:'collection',designId:p.designId,model:p.model,caseMaterial:'',phoneColor:null,effect:'original'});
      if(!phoneModels.includes(state.model))state.model='';
      if(stockCatalogStatus==='ready'&&!stockSelection(state.model,state.caseMaterial))state.caseMaterial='';
      state.phoneTemplateId=stockSelection(state.model,state.caseMaterial)?.templateId;selectSupplierTemplate(state.model,state.phoneTemplateId);syncDraftColor();
      if(p.source==='photo'&&p.collectionLayout)state.artworkLayouts[p.designId]={...structuredClone(p.collectionLayout),addedArtwork:structuredClone(p.addedArtwork||[])};
      comparing=false;save();go('choose');
    }
    if(el.dataset.action==='copy-code'){
      try{await navigator.clipboard.writeText(state.pass.code);notify('Design code copied.');}
      catch{notify('Your design code: '+state.pass.code);}
    }
    if(el.dataset.action==='view-order'){go(await savedOrderRoute(el.dataset.id));}
    if(el.dataset.action==='cancel-order'){const order=orderForCode(orderBook,state.pass.code);if(order?.server){await orderAction(order,'cancel');notify('Test order cancelled. No money was charged.');render(true);}}
    if(el.dataset.action==='orders-page'){orderPage=Number(el.dataset.page);await navigate();}
    if(el.dataset.action==='refresh-orders'||el.dataset.action==='refresh-payment')await navigate();
    if(el.dataset.action==='pay-provider'){if(passBusy)return;passBusy=true;paymentError='';render(true);try{await openPaymentCheckout(el.dataset.id);}catch(e){paymentError=e.message;}finally{passBusy=false;render(true);}}
  } catch(error){notify(error.message||'Your design could not be saved. Please try again.');}
});
document.querySelector('.skip-link').addEventListener('click',event=>{event.preventDefault();document.querySelector('#main')?.focus();});
let stockRefreshedAt=Date.now();
async function refreshStockChoices(){
 const before=JSON.stringify(phoneModels.map(model=>stockSelection(model))),beforeStatus=stockCatalogStatus;
 await loadStockCatalog(undefined,stockScope);stockRefreshedAt=Date.now();
 if(stockCatalogStatus==='ready'&&state.model&&!phoneModels.includes(state.model)){state.model='';state.caseMaterial='';state.phoneTemplateId=undefined;save();}
 if(stockCatalogStatus==='ready'){
  if(state.caseMaterial&&!stockSelection(state.model,state.caseMaterial))state.caseMaterial='';
  state.phoneTemplateId=stockSelection(state.model,state.caseMaterial)?.templateId;
  selectSupplierTemplate(state.model,state.phoneTemplateId);
 }
 if(stockCatalogStatus==='ready'&&(state.phoneColor||stockSelection(state.model,state.caseMaterial)?.colors?.length)){syncDraftColor();save();}
 return before!==JSON.stringify(phoneModels.map(model=>stockSelection(model)))||beforeStatus!==stockCatalogStatus;
}
setInterval(async()=>{if(document.hidden||passBusy||photoBusy||aiBusy||canvasExpanded||(stockCatalogStatus==='ready'&&Date.now()-stockRefreshedAt<60000))return;const changed=await refreshStockChoices();if(changed&&location.hash.startsWith('#choose'))render(true);},10000);
async function navigate(){
 const currentNavigation=++navigationId;
 const [route,query='']=location.hash.slice(1).split('?');const params=new URLSearchParams(query);
 if(['choose','review','ai','my-designs','pass','orders','payment'].includes(route))try{await syncAIAccount();}catch(error){if(currentNavigation!==navigationId)return;customerUI.error=error.message;}
 // Identity reads may finish after a newer navigation has already rendered.
 // Retire the old route before it can restart loading or consume entry data.
 if(currentNavigation!==navigationId)return;
 if(!workspace.active&&route!=='account'){render();return;}
 if(route==='choose'){reviewPass=null;reviewSaved=false;await refreshStockChoices();}
 if(route==='review'&&!reviewPass){try{const prepared=await prepareDesignReview({...state});if(currentNavigation!==navigationId)return;reviewPass=prepared;reviewSaved=false;}catch(error){if(currentNavigation!==navigationId)return;notify(error.message);go('choose');return;}}
 if(route==='my-designs'){localDesigns=[];localDesignBusy=true;render(true);await loadLocalDesigns();}
 if(route==='account'||route==='membership')try{await syncAIAccount();if(route==='account'&&membership.authenticated)await loadCustomerCredits(true);}catch(error){customerUI.error=error.message;}
 stopPaymentPolling();paymentPollCount=0;
 if(route==='checkout'){
  paymentConfig=null;paymentError='';paymentLoading=true;render(true);
  const [config,account]=await Promise.allSettled([getPaymentConfig(),syncAIAccount()]);
  if(currentNavigation!==navigationId)return;
  paymentLoading=false;
  if(config.status==='fulfilled')paymentConfig=config.value;
  paymentError=config.status==='rejected'?config.reason.message:account.status==='rejected'?account.reason.message:'';
 }else paymentLoading=false;
 if(route==='payment'){
  const paymentHash=location.hash;paymentError='';orderActionError='';paymentOrder=null;render(true);
  try{const latest=await refreshOrder(params.get('order'));if(location.hash!==paymentHash)return;paymentOrder=latest;state.pass=paymentOrder.pass;save();}
  catch(e){if(location.hash!==paymentHash)return;paymentError=e.message;}
  schedulePaymentPoll();
 }
 if(route==='pass'||route==='kiosk'){
   orderBook=await readDesign('print-orders-v1')||freshOrders();const order=state.pass&&orderForCode(orderBook,state.pass.code);
   if(currentNavigation!==navigationId)return;
   const detailRoute=route==='pass'&&providerOrderRoute(order);
   if(detailRoute){history.replaceState(null,'','#'+detailRoute);return navigate();}
   if(order?.server)try{const latest=await refreshOrder(order.id);state.pass=latest.pass;if(state.job?.orderId===latest.id)state.job={...state.job,status:latest.status,pass:latest.pass};}catch(e){notify(e.message);}
 }
 if(route==='orders'){orderLoading=true;orderError='';render(true);try{if(entryOrderError)throw Error(entryOrderError);const data=entryOrders||await orderRequest('?page='+orderPage);if(currentNavigation!==navigationId)return;orderRows=data.results;orderHasMore=data.has_more;orderError='';}catch(e){if(currentNavigation!==navigationId)return;orderError=e.message;}finally{if(currentNavigation===navigationId)orderLoading=false;entryOrders=null;entryOrderError='';}}
 if(route==='choose'&&designs.some(d=>d.id===params.get('design'))){state.designId=params.get('design');state.source='collection';}
 if(route==='choose'&&params.get('source')==='photo'){
  if(params.get('fresh')==='1'){
   photoBusy=true;
   try{await clearPhotoDraft();state.editOrderId=null;}
   catch(error){notify(error.message||'Your design could not be saved. Please try again.');return;}
   finally{photoBusy=false;}
   params.delete('fresh');history.replaceState(null,'',`#choose?${params}`);
  }
  state.source='photo';save();
 }
 if(route==='choose'&&params.get('studio')==='1')effectPanelOpen=true;
 if(currentNavigation!==navigationId)return;
 syncStationFinder();render();document.querySelector('#main')?.focus({preventScroll:true});
 if(route==='choose'&&params.get('studio')==='1')openAIStudio();
 if(route==='choose'&&params.get('step')==='model')openModelPicker();
}
const entryHash=location.hash;
const entry=await stationEntry({scope:stockScope,hash:entryHash,station:scannedStation});
if(entry&&location.hash===entryHash){
 entryOrderError=entry.error||'';
 let target=entry.route;
 if(entry.reference)try{target=await savedOrderRoute(entry.reference);}catch(error){target='orders';entryOrderError=error.message;}
 entryOrders=target==='orders'?(entry.data||null):null;
 if(location.hash===entryHash)history.replaceState(null,'','#'+target);
}
window.addEventListener('hashchange',navigate);
let sessionCheckBusy=false;
async function checkVisibleSession(){
 if(document.hidden||sessionCheckBusy)return;
 sessionCheckBusy=true;
 try{await syncAIAccount();}catch(error){customerUI.error=error.message;render(true);}
 finally{sessionCheckBusy=false;}
}
// Another tab can change the session. Block submissions during this check;
// keep the file input alive when the native picker returns window focus.
window.addEventListener('focus',checkVisibleSession);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkVisibleSession();});
window.addEventListener('resize',()=>{if(!artworkDrag)highlightArtwork();});
app.addEventListener('load',event=>{if(!artworkDrag&&event.target.closest?.('.artwork-canvas'))highlightArtwork();},true);
for(const type of ['load','error'])app.addEventListener(type,event=>{if(event.target.matches?.('.look-comparison img'))updateLookImageState(document.querySelector('.look-browser'));},true);
startVisiblePolling({interval:60000,enabled:()=>Boolean(pickupContext())&&!passBusy&&!stationFinder.state.busy,refresh:()=>stationFinder.refresh()});
await navigate();

async function loadAssetPhoto(url){
 const response=await fetch(url);if(!response.ok)throw Error('The style sample could not be loaded. Please try again.');
 const blob=await response.blob();return importPhoto(new File([blob],'sample.png',{type:blob.type}));
}
async function mergeAIAccount(data){
 const owner=designOwner(data);
 if(!owner)throw Error('Your sign-in could not be verified. Please reload.');
 if(!workspace.active||owner!==workspace.owner){
  lockPrivateWorkspace();location.reload();
  throw Error('Your sign-in changed. Reloading your private workspace.');
 }
 if(membership.customer?.id!==data.customer?.id)Object.assign(customerUI,{ledger:[],ledgerNext:null,ledgerError:'',ledgerBusy:false,ledgerOpen:false});
 if(aiJob&&(aiJob.customerId&&aiJob.customerId!==data.customer?.id||aiJob.remoteId&&!aiJob.customerId)){aiJob=null;state.aiJobId=null;save();}
 membership=await privateUpdate('ai-membership-v1',a=>({...a,...data,jobs:a.customer?.id===data.customer?.id?a.jobs||{}:{}}),freshMembership());
}
function lockPrivateWorkspace(){
 workspace.lock();
 // Keep committed data in its original namespace while removing private views.
 Object.assign(state,{photo:'',phoneColor:null,pass:null,job:null,ai:null,aiJobId:null,artworkLayouts:{},photoArtwork:[],photoPlacement:null,editOrderId:null});
 reviewPass=null;reviewSaved=false;checkoutDraft=null;aiJob=null;localDesigns=[];orderRows=[];paymentOrder=null;orderBook=freshOrders();
 membership={...freshMembership(),server:true,authenticated:false,customer:null};
 Object.assign(customerUI,{email:'',codeSent:false,ledger:[],ledgerNext:null,ledgerOpen:false});
}
async function syncAIAccount(){try{await mergeAIAccount(await getAIAccount());}catch(error){lockPrivateWorkspace();throw error;}}
async function rememberLiveJob(job){
 job={...job,customerId:job.customerId||membership.customer?.id||null};
 membership=await privateUpdate('ai-membership-v1',a=>({...a,jobs:{...a.jobs,[job.id]:job}}),freshMembership());
 aiJob=job;state.aiJobId=job.id;save();
}
async function changeAIPhoneModel(model){
 if(aiBusy||photoBusy||passBusy||sessionCheckBusy||aiJob?.mode!=='live'||aiJob.status!=='awaiting_confirmation'||aiJob.remoteId||aiJob.submissionAttempted||model===aiJob.model)return;
 const jobId=aiJob.id;aiBusy=true;aiUi.error='';render(true);
 try{
  await syncAIAccount();workspace.check();await refreshStockChoices();
  if(!aiJob||aiJob.id!==jobId||aiJob.status!=='awaiting_confirmation'||aiJob.remoteId||aiJob.submissionAttempted)throw Error('This render has changed. Please review it again.');
  if(stockCatalogStatus!=='ready'||!phoneModels.includes(model))throw Error('This phone model is unavailable. Please choose again.');
  // Preserve the request key, photo and style. Changing a draft must not submit a render.
  await rememberLiveJob({...aiJob,model});
  Object.assign(state,{model,caseMaterial:'',phoneTemplateId:undefined,phoneColor:null});
  selectSupplierTemplate(model,undefined);colorNotice=false;reviewPass=null;aiUi.accepted=false;save();
 }catch(error){aiUi.error=error.message;notify(error.message);}
 finally{aiBusy=false;render(true);document.querySelector('#ai-phone-model')?.focus({preventScroll:true});}
}
async function confirmAI(generation,accepted){
 if(aiBusy)return;
 if(!membership.authenticated){customerUI.next='ai';go('account');return;}
 aiBusy=true;aiUi.error='';aiUi.accepted=accepted;render(true);
 try{
  await syncAIAccount();workspace.check();
  if(generation){
   if(aiJob?.mode!=='live')throw Error('Choose your photo and start a new AI render.');
   if(!accepted)throw Error('Confirm using one AI generation first.');
   if(!aiJob.submissionAttempted){
    await refreshStockChoices();
    if(stockCatalogStatus!=='ready'||!phoneModels.includes(aiJob.model))throw Error('This phone model is unavailable. Please choose again.');
   }
   // Freeze model changes before sending: a timeout may already have reserved a credit.
   await rememberLiveJob({...aiJob,submissionAttempted:true});
   await rememberLiveJob(await submitLiveRender(aiJob,accepted));
   await syncAIAccount();
  }else await mergeAIAccount(await changeAIAccount('subscribe',accepted));
 }catch(error){aiUi.error=error.message||'The AI service could not be reached. Please try again.';notify(aiUi.error);}
 finally{aiBusy=false;render(true);if(location.hash==='#ai')document.querySelector('#main')?.focus({preventScroll:true});}
}
async function newAI(input){
 if(!AI_GENERATION_CONNECTED)throw Error('AI generation is not configured. Please contact the store.');
 const job=createLiveRender({...input,model:input.model||state.model});
 if(aiJob?.mode==='live'&&aiJob.status==='awaiting_confirmation'&&!aiJob.remoteId)await rememberLiveJob({...aiJob,status:'cancelled'});
 Object.assign(aiUi,{mode:'pair',compare:50,accepted:false,error:'',reconnecting:false});
 await rememberLiveJob(job);
 if(!membership.authenticated){customerUI.next='ai';go('account');}else go('ai');
}
async function handleAI(action){
 if(action==='upload'){openPhotoPicker();return;}
 aiBusy=true;aiUi.error='';aiUi.busyAction=action;render(true);
 try{
  if(action==='cancel'){
   const unsubmitted=aiJob?.status==='awaiting_confirmation';
   if(aiJob?.mode==='live')await rememberLiveJob(await cancelLiveRender(aiJob));
   await syncAIAccount();
   if(unsubmitted)go('choose');
  }
  if(action==='stop-renewal'||action==='resume-renewal')await mergeAIAccount(await changeAIAccount(action,true));
  if(action==='sample'){
   const example=exampleFor(state.aiExample);const photo=await loadAssetPhoto(example.original);await privateWrite('draft-photo',photo);
   Object.assign(state,{photo,source:'photo',photoOrigin:example.origin,ai:null,effect:'original',intensity:65,zoom:100,x:50,y:50});clearPreviousPhotoArtwork();effectPanelOpen=true;save();render(true);
  }
  if(action==='create'){
   if(aiJob?.mode==='live'&&['queued','generating'].includes(aiJob.status)){go('ai');notify('Finish or cancel your current render before starting another.');}
   else await newAI({photo:state.photo,sourceKind:state.photoOrigin===exampleFor(state.aiExample).origin?'sample':'upload',styleId:state.aiStyle,exampleId:state.aiExample});
  }
  if(action==='retry')await newAI({photo:aiJob.photo,sourceKind:aiJob.sourceKind,styleId:aiJob.styleId,exampleId:aiJob.exampleId,model:state.model||aiJob.model});
  if(action==='refresh')await rememberLiveJob(await refreshLiveRender(aiJob));
  if(action==='apply'){
   if(aiJob?.mode!=='live')throw Error('Choose your photo and start a new AI render.');
   await rememberLiveJob(await refreshLiveRender(aiJob));
   if(!canApplyAIOrder(aiJob))throw Error('Wait until the render is ready before using its result.');
   const photo=aiJob.resultPhoto;await privateWrite('draft-photo',photo);
   Object.assign(state,{photo,source:'photo',photoOrigin:'upload',effect:'original',zoom:100,x:50,y:50,photoPlacement:null,ai:{styleId:aiJob.styleId,jobId:aiJob.id,mode:'live'}});
   save();go('choose');notify('AI image applied. Adjust your crop, then review your print order.');
  }
 }catch(error){aiUi.error=error.message||'The AI service could not be reached. Please try again.';notify(aiUi.error);}
 finally{aiBusy=false;render(true);}
}
let pollBusy=false,pollErrors=0;
setInterval(async()=>{
 if(!aiJob||aiJob.mode!=='live'||aiBusy||pollBusy||!(['queued','generating'].includes(aiJob.status)||aiJob.status==='ready'&&!aiJob.resultPhoto))return;
 pollBusy=true;const pollingJob=aiJob;
 try{
  const previous=aiJob.status,hadImage=Boolean(aiJob.resultPhoto);
  const updated=await refreshLiveRender(pollingJob);
  if(aiJob?.id!==pollingJob.id)return;
  await rememberLiveJob(updated);pollErrors=0;aiUi.reconnecting=false;
  if(previous!==aiJob.status||hadImage!==Boolean(aiJob.resultPhoto)){
   if(['ready','failed','cancelled'].includes(aiJob.status))try{await syncAIAccount();}catch{/* Show the finished image even if the balance refresh is unavailable. */}
   render(true);
   if(aiJob.status==='ready')notify('Your AI image is ready. Open AI studio to use it.');
  }
 }catch{if(aiJob?.id===pollingJob.id){aiUi.reconnecting=true;if(++pollErrors===1)notify('We could not update your render. Reconnecting…');}}
 finally{pollBusy=false;}
},3000);

app.addEventListener('click',async event=>{
 const button=event.target.closest('[data-customer-action]');
 if(!button)return;event.preventDefault();await handleCustomer(button.dataset.customerAction);
});
async function handleCustomer(action,fields){
 if(action==='credits-toggle'){customerUI.ledgerOpen=!customerUI.ledgerOpen;render(true);return;}
 if(action==='credits-more'||action==='credits-refresh'){const loading=loadCustomerCredits(action==='credits-refresh');render(true);await loading;render(true);return;}
 if(customerUI.busy)return;
 if(action==='change-email'){customerUI.codeSent=false;customerUI.error='';render(true);return;}
 customerUI.busy=true;customerUI.error='';customerUI.success='';
 if(action==='send')customerUI.email=String(fields.get('email')||'').trim();
 const code=String(fields?.get('code')||'').trim();
 render(true);
 try{
  if(action==='profile'){
   await updateCustomerName(String(fields.get('displayName')||'').trim());await syncAIAccount();customerUI.success='Your profile has been saved.';
  }else if(action==='send'||action==='resend'){
   await sendEmailCode(customerUI.email);customerUI.codeSent=true;customerUI.resendAt=Date.now()+60000;
   clearTimeout(resendTimer);resendTimer=setTimeout(()=>{const button=app.querySelector('[data-customer-action="resend"]');if(button&&!customerUI.busy)button.disabled=false;},60000);
  }else if(action==='verify'){
   await verifyEmailCode(customerUI.email,code);await syncAIAccount();customerUI.codeSent=false;
   customerUI.busy=false;go(customerUI.next==='ai'&&aiJob?'ai':'choose');
  }else if(action==='logout'){
   try{await signOutCustomer();}finally{lockPrivateWorkspace();}
   location.reload();return;
  }
 }catch(error){customerUI.error=error.message;}
 finally{customerUI.busy=false;render(true);if(customerUI.codeSent)document.getElementById('customer-code')?.focus({preventScroll:true});}
}
async function loadCustomerCredits(reset=false){
 if(!membership.authenticated||customerUI.ledgerBusy)return;
 const id=membership.customer.id;customerUI.ledgerBusy=true;customerUI.ledgerError='';
 try{const data=await getCustomerCredits(reset?null:customerUI.ledgerNext);if(membership.customer?.id===id){customerUI.ledger=reset?data.results:[...customerUI.ledger,...data.results];customerUI.ledgerNext=data.nextCursor;}}
 catch(error){if(membership.customer?.id===id)customerUI.ledgerError=error.message;}
 finally{if(membership.customer?.id===id)customerUI.ledgerBusy=false;}
}
}

// A failed startup must not install navigation, polling, or business handlers.
// Reload retries the original URL and session without deleting browser data.
if(await startStorefront()==='storage-unavailable')showStorageStartupError(document.querySelector('#app'));
