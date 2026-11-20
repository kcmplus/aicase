import {generatedPhotoPlacement} from '../storefront/ai-service.js';
import {homeLooks} from '../storefront/v35-home.js';
import {orderListPage} from '../storefront/v35-order-list.js';
import {createOrderSuccessTracker} from '../storefront/order-success.js';
import {progressPanel,progressPaymentText} from '../storefront/order-progress.js';
import {caseMaterialLabel} from '../storefront/case-styles.js';
import {createStationFinder} from '../storefront/pickup-stations.js';
import {selectSupplierTemplate} from '../storefront/phone-templates.js';
import {singlePrintDraft} from '../storefront/order-service.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,access} from 'node:fs/promises';
import {shellHeader,shellFooter,homePresentation,shellInfo,mountShell} from '../storefront/v35-shell.js';
import {worksPage,workDetailPage,matchingWorks,tutorialPage,aboutPage,locationsPage,membershipInfoPage,publicPageDestination} from '../storefront/v35-pages.js';
import {designs} from '../storefront/simple-core.js';
import {normalizeLocale} from '../storefront/simple-i18n.js';
import {paymentState} from '../storefront/payment-state.js';
import {esc} from '../storefront/art.js';
import vm from 'node:vm';
import {createDesignWorkspace,createDesignLibrary,designOwner} from '../storefront/design-workspace.js';
import {myDesignsPage,designReview} from '../storefront/v35-designs.js';
import {createPersonalPass,readPass} from '../storefront/simple-core.js';
import {phoneTemplates,phoneTemplate} from '../storefront/phone-templates.js';
import {makePersonalDesign,isPhoto,validateAddedArtwork,validatePlacement,validatePhotoPlacement} from '../storefront/simple-personalize.js';
import {validatePhoneColor,validPhoneColors,frozenPhoneColor,reconcilePhoneColor,colorPicker,colorSelection,phoneColorName} from '../storefront/phone-colors.js';
import {phone} from '../storefront/art.js';
import {exportCase} from '../storefront/print-export.js';
import {orderRequest,savedOrder} from '../storefront/order-service.js';
import {applyStockCatalog,stockSelection,stockedPhoneModels,stockCatalogStatus,loadStockCatalog} from '../storefront/stock-catalog.js';
import {customerPage} from '../storefront/customer-account.js';

test('V35 home prioritizes photo design without an automatic album picker',()=>{
 const html=homePresentation({gallery:'<section id="designs">CATALOG</section>'});
 assert.ok(html.indexOf('data-action="home-photo"')<html.indexOf('data-home-collection'));
 assert.doesNotMatch(html,/type="file"|data-home-upload/);
 assert.match(html,/href="#choose\?source=photo&studio=1"/);
 assert.match(html,/<section id="designs">CATALOG<\/section>/);
 assert.doesNotMatch(html,/sessionStorage|setTimeout|pay_status|data-action="advance-print"/);
});
test('upload busy state disables the album action without claiming upload success',()=>{
 const html=homePresentation({busy:true});
 assert.match(html,/data-action="home-photo" aria-busy="true" disabled/);
 assert.match(html,/Reading your photo…/);
 assert.doesNotMatch(homePresentation(),/aria-busy="true"/);
});
test('shared shell exposes working legacy destinations and bilingual native menu semantics',()=>{
 for(const lang of ['en-US','zh-CN']){
  const header=shellHeader({lang,authenticated:true,route:'orders'});
  for(const hash of ['home','designs','how-it-works','orders','account'])assert.ok(header.includes(`href="#${hash}"`),hash);
  assert.match(header,/<dialog id="v35-menu"/);
  assert.match(header,/aria-controls="v35-menu" aria-expanded="false"/);
  assert.match(header,/href="#orders" aria-current="page"/);
  assert.match(header,new RegExp(`data-shell-language="${lang}" aria-pressed="true"`));
  assert.doesNotMatch(header,/href="\.\/.*\.html|#kiosk|#membership/);
  assert.match(shellFooter(lang),/data-shell-info="station"/);
 }
 assert.match(shellHeader({lang:'zh-CN'}),/打开菜单/);
 assert.match(shellHeader(),/Open menu/);
});
test('home instructions follow phone confirmation and do not ask to save a design QR',()=>{
 const html=homePresentation({lang:'zh-CN'});
 assert.doesNotMatch(html,/快递／空运暂未开放结算|v35-guide/);
 assert.match(html,/未扫码可设计全部已发布机型/);
 assert.match(shellInfo('tutorial','zh-CN')[1],/扫描设备屏二维码/);
 assert.doesNotMatch(html,/保存.{0,4}二维码|Keep your code|save the QR code|Show your code/);
 assert.match(shellInfo('station','en-US')[1],/Nearby search is not available/);
 assert.match(shellInfo('ai','zh-CN')[1],/服务端确认/);
});
test('all V35 presentation assets are local and available; editor entry retains the existing service module',async()=>{
 const html=homePresentation(),css=await readFile(new URL('../storefront/v35-shell.css',import.meta.url),'utf8');
 for(const path of new Set([...html.matchAll(/(?:src)="\.\/([^"?]+)"/g),...css.matchAll(/url\('\.\/([^']+)'\)/g)].map(match=>match[1])))await access(new URL('../storefront/'+path,import.meta.url));
 for(const look of Object.values(homeLooks))for(const path of [look.original,look.result])await access(new URL('../storefront/'+path,import.meta.url));
 const entry=await readFile(new URL('../storefront/index.html',import.meta.url),'utf8');
 assert.match(entry,/href="\.\/v35-shell.css"/);assert.match(entry,/src="\.\/simple-app.js"/);
 assert.doesNotMatch(entry,/popomo-ui|order-store.js|profile-store.js/);
});

test('shell menu updates its expanded state and restores focus when closed',()=>{
 const listeners={}; let focused=0;
 const opener={isConnected:true,attrs:{},setAttribute(key,value){this.attrs[key]=value;},focus(){focused++;}};
 const closeButton={focus(){focused++;}};
 const menu={open:false,addEventListener(type,fn){listeners[type]=fn;},showModal(){this.open=true;},close(){this.open=false;listeners.close();},querySelector(){return closeButton;}};
 const classes=new Set();
 const originalDocument=globalThis.document;
 globalThis.document={body:{classList:{add:value=>classes.add(value),remove:value=>classes.delete(value)}}};
 const root={querySelector(selector){return selector==='#v35-menu'?menu:opener;},addEventListener(type,fn){listeners[type]=fn;},removeEventListener(type){delete listeners[type];}};
 const click=selector=>listeners.click({target:{closest(){return {matches(value){return value.split(',').includes(selector);},dataset:{}};}}});
 try{
  const cleanup=mountShell(root);
  click('[data-shell-menu]');
  assert.equal(menu.open,true);assert.equal(opener.attrs['aria-expanded'],'true');assert.ok(classes.has('v35-menu-open'));
  click('[data-shell-close]');
  assert.equal(menu.open,false);assert.equal(opener.attrs['aria-expanded'],'false');assert.equal(classes.has('v35-menu-open'),false);assert.equal(focused,2);
  cleanup();assert.equal(listeners.click,undefined);
 }finally{globalThis.document=originalDocument;}
});

const preview=id=>`<div class="phone-case" data-template="${id}"></div>`;
test('Works center filters the existing editable catalog, preserves bilingual search and has an empty state',()=>{
 assert.deepEqual(matchingWorks(designs,{query:'花开'}).map(work=>work.id),['bloom']);
 assert.deepEqual(matchingWorks(designs,{category:'graphic',query:'statement'}).map(work=>work.id),['type']);
 assert.deepEqual(matchingWorks(designs,{category:'travel'}).map(work=>work.id),['sunset']);
 const html=worksPage({works:designs,preview,params:new URLSearchParams({category:'all',q:'<unmatched>"'})});
 assert.match(html,/No matching designs/);assert.match(html,/&lt;unmatched&gt;&quot;/);assert.doesNotMatch(html,/<unmatched>/);
 for(const lang of ['en-US','zh-CN']){
  const all=worksPage({works:designs,preview,lang});
  for(const work of designs)assert.match(all,new RegExp(`href="#work\\?id=${work.id}"`));
  assert.doesNotMatch(all,/id="v35-work-search"|v35-works-toolbar/);assert.match(all,/role="status"/);assert.match(all,/v35-community-grid/);assert.match(all,/href="#my-designs"/);
 }
});
test('Work details resolve only available template ids and lead to the real editor without simulated orders',()=>{
 const html=workDetailPage({works:designs,preview,params:new URLSearchParams({id:'popomo-bloom'})});
 assert.match(html,/data-template="bloom"/);assert.match(html,/href="#choose\?design=bloom"/);assert.match(html,/href="#designs"/);
 assert.doesNotMatch(html,/sessionStorage|data-like|data-use="print"|quantity/);
 const missing=workDetailPage({works:designs,preview,params:new URLSearchParams({id:'unpublished-customer-photo'})});
 assert.match(missing,/Design not found/);assert.doesNotMatch(missing,/data-template|href="#choose/);
});
test('Tutorial and about retain real destinations and explain the current printing boundaries in both languages',()=>{
 for(const lang of ['en-US','zh-CN']){
  const html=tutorialPage({lang});
  for(const section of ['steps','save','print'])assert.match(html,new RegExp(`id="${section}"`));
  for(const target of ['#choose?source=photo','#designs','#orders','#locations'])assert.ok(html.includes(`href="${target}"`));
  assert.match(html,/data-shell-info="tutorial"/);
  assert.doesNotMatch(html,/3–4|US\$4|保存.{0,4}二维码|save the QR|data-action="advance-print"/);
  assert.match(aboutPage({lang}),/id="our-story"/);
 }
 assert.match(tutorialPage(),/Dispensed does not mean collected/);
 assert.match(tutorialPage({lang:'zh-CN'}),/快递／空运结算与附近搜索暂未开放/);
 assert.match(shellInfo('tutorial','zh-CN')[1],/确认已付订单/);
 assert.equal(shellInfo('station')[2],'#locations');
});
const station={device_id:'123',shop_id:'351',name:'Verified <device>',location:'Actual address',number:'A-1',models:[{name:'iPhone 17',brand:'Apple'}],inventory:{availability:'ready'},coordinates:{coordinate_type:'WGS84',latitude:10,longitude:20}};
test('Station pages show verified data and navigate only with confirmed WGS84 coordinates',()=>{
 const html=locationsPage({station,hasScope:true});
 assert.match(html,/Verified &lt;device&gt;/);assert.match(html,/Actual address/);assert.match(html,/iPhone 17/);
 assert.match(html,/maps\.google|www\.google\.com\/maps/);assert.match(html,/destination=10%2C20/);
 assert.match(html,/data-action="scan-station"/);assert.doesNotMatch(html,/DEMO-0|New York|km away|online now/);
 for(const coordinates of [null,{...station.coordinates,coordinate_type:'GCJ02'},{...station.coordinates,latitude:999}]){
  const withoutMap=locationsPage({station:{...station,coordinates},hasScope:true});
  assert.doesNotMatch(withoutMap,/href="https:\/\/(?:www\.google|maps\.apple|uri\.amap|api\.map\.baidu)/);
 }
});
test('Station unknown, error, empty, updating and busy states never create fake print authority',()=>{
 const unknown=locationsPage();assert.match(unknown,/No printer selected/);assert.match(unknown,/Nearby search is not available/);assert.doesNotMatch(unknown,/data-action="refresh-device-info"/);
 const error=locationsPage({hasScope:true,error:'device-unavailable',legacy:true});
 assert.match(error,/identity is ambiguous/);assert.match(error,/read-only/);assert.doesNotMatch(error,/Verified|Actual address|data-action="(?:start-print|advance-print)"/);
 const busy=locationsPage({hasScope:true,busy:true});assert.match(busy,/aria-busy="true" disabled/);
 for(const [status,message] of [['empty','No available models'],['updating','Inventory is being refreshed']])assert.ok(locationsPage({station:{...station,models:[],inventory:{availability:status}}}).includes(message));
});
test('Membership deep link keeps actual allowances and exposes no simulated purchase or renewal',()=>{
 const html=membershipInfoPage({account:{authenticated:true,trialRemaining:7,subscription:{endsAt:Date.now()+60000,monthlyLimit:20,used:4}}});
 assert.match(html,/<strong>7<\/strong>/);assert.match(html,/<strong>16<\/strong>/);assert.match(html,/href="#account"/);
 assert.match(html,/Membership purchases are not available/);assert.doesNotMatch(html,/<form|data-ai-action|subscribe|renewal/);
 const signedOut=membershipInfoPage({account:{authenticated:false,trialRemaining:7}});assert.doesNotMatch(signedOut,/<strong>7<\/strong>/);assert.match(signedOut,/Sign in to view/);
});
test('Public HTML aliases preserve device, language, design and section parameters',async()=>{
 assert.equal(normalizeLocale('zh'),'zh-CN');assert.equal(normalizeLocale('en'),'en-US');assert.equal(normalizeLocale('zh-CN'),'zh-CN');assert.equal(normalizeLocale('invalid'),null);
 for(const [name,route] of [['works-center','designs'],['work-detail','work'],['how-to','how-it-works'],['about','about'],['printers','printers'],['print-locations','locations']]){
  const destination=new URL(publicPageDestination(`http://127.0.0.1:4173/${name}.html?device_id=123&shop_id=351&lang=zh&id=bloom#steps`));
  assert.equal(destination.pathname,'/');assert.equal(destination.searchParams.get('device_id'),'123');
  assert.equal(destination.hash.split('?')[0],'#'+route);
  const params=new URLSearchParams(destination.hash.split('?')[1]);
  assert.equal(params.get('shop_id'),'351');assert.equal(params.get('lang'),'zh');assert.equal(params.get('id'),'bloom');assert.equal(params.get('section'),'steps');
  const entry=await readFile(new URL(`../storefront/${name}.html`,import.meta.url),'utf8');assert.match(entry,/src="\.\/v35-page-entry.js"/);
 }
 assert.equal(publicPageDestination('http://127.0.0.1:4173/unregistered.html'),null);
});
test('Public page integration registers real routes and removes obsolete manual hardware simulation',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 for(const route of ['designs:()=>worksPage','work:()=>workDetailPage',"'how-it-works':()=>tutorialPage",'about:()=>aboutPage','locations:publicStationPage','printers:publicStationPage','kiosk:()=>publicStationPage(true)','membership:()=>membershipInfoPage'])assert.ok(source.includes(route));
 assert.match(source,/event.target.id==='v35-work-search'/);
 assert.doesNotMatch(source,/data-action="(?:start-print|advance-print|scan-saved)"|if\(el.dataset.action==='(?:start-print|advance-print)'\)/);
 const deviceEntry=await readFile(new URL('../storefront/device-entry.js',import.meta.url),'utf8');
 assert.match(deviceEntry,/import\('\.\/device-info-app.js'\)/);assert.match(deviceEntry,/destination.hash='kiosk'/);assert.doesNotMatch(deviceEntry,/import\('\.\/device-app.js'\)/);
 const htmls=[worksPage({works:designs,preview}),workDetailPage({works:designs,preview,params:new URLSearchParams({id:'bloom'})}),tutorialPage(),aboutPage(),locationsPage()];
 for(const html of htmls)for(const [,path] of html.matchAll(/src="\.\/([^"?]+)"/g))await access(new URL('../storefront/'+path,import.meta.url));
});

test('orders page renders a server order and its status',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const declaration=source.match(/^function ordersPage\(\)\{.*$/m)?.[0];
 assert.ok(declaration,'ordersPage must exist');
 const context={orderListPage,orderFilter:'all',orderSearch:'',orderCounts:null,designs:[],localized:v=>v?.name,progressPanel,progressPaymentText,caseMaterialLabel,stationContext:()=>'',orderLoading:false,orderError:'',orderRows:[{status:'paid',mode:'free_test',model_name:'Synthetic model',fulfillment_type:'pickup',reference:'SYNTHETIC-1',created_at:'2026-01-01T00:00:00Z',currency:'USD',amount:0}],esc:String,paymentLabel:()=>'',deliveryLabel:()=>'',locale:()=> 'en-US',orderPage:1,orderHasMore:false};
 const statusDeclaration=source.match(/^function orderStatus\([^\n]+$/m)?.[0]||'';
 const html=vm.runInNewContext(`${statusDeclaration}\n${declaration}\nordersPage()`,context);
 assert.match(html,/SYNTHETIC-1/);
 assert.match(html,/Paid/);
});

test('orders list renders each server refund state without changing historical amount',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const status=source.match(/^function orderStatus\([^\n]+$/m)?.[0];
 const page=source.match(/^function ordersPage\(\)\{.*$/m)?.[0];
 assert.ok(status&&page);
 for(const [refund,label] of [[null,'Paid'],[{status:'requested'},'Checking refund status.'],[{status:'pending'},'Refund processing.'],[{status:'succeeded'},'Payment refunded.'],[{status:'failed'},'Refund could not be completed.']]){
  const order=Object.freeze({status:'paid',refund,mode:'stripe_test',model_name:'Synthetic model',fulfillment_type:'pickup',reference:'SYNTHETIC-REFUND',created_at:'2026-01-01T00:00:00Z',currency:'USD',amount:'10.00'});
  const before=JSON.stringify(order);
  const html=vm.runInNewContext(`${status}\n${page}\nordersPage()`,{orderListPage,orderFilter:'all',orderSearch:'',orderCounts:null,designs:[],localized:v=>v?.name,progressPanel,progressPaymentText,caseMaterialLabel,stationContext:()=>'',orderLoading:false,orderError:'',orderRows:[order],esc:String,paymentLabel:()=>'',deliveryLabel:()=>'',locale:()=> 'en-US',orderPage:1,orderHasMore:false});
  assert.ok(html.includes(label),`refund ${refund?.status||'none'}`);
  assert.ok(html.includes('USD 10.00'));
  assert.equal(JSON.stringify(order),before);
 }
});

test('order status labels preserve historical fulfillment and refund precedence without mutating orders',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const declaration=source.match(/^function orderStatus\([^\n]+$/m)?.[0];
 assert.ok(declaration,'shared order status renderer must exist');
 const labels={pending:'Awaiting payment',paid:'Paid',printing:'Printing',ready:'Ready to collect',completed:'Collected',collected:'Collected',cancelled:'Cancelled',unknown:'unknown'};
 const refunds={requested:'Checking refund status.',pending:'Refund processing.',succeeded:'Payment refunded.',failed:'Refund could not be completed.',unknown:'Checking refund status.'};
 for(const [status,label] of Object.entries(labels)){
  assert.equal(vm.runInNewContext(`${declaration}\norderStatus(status)`,{status}),label);
  for(const [refundStatus,refundLabel] of Object.entries(refunds)){
   const refund=Object.freeze({status:refundStatus});
   assert.equal(vm.runInNewContext(`${declaration}\norderStatus(status,refund)`,{status,refund}),refundLabel);
   assert.equal(refund.status,refundStatus);
  }
 }
});

test('saved design, payment page and order receipt render shared statuses from synthetic server snapshots',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const names=['checkoutDesignCard','checkoutDock','orderStatus','isProviderOrder','providerName','paymentLabel','passPage','providerOrderPage','paymentPage'];
 const declarations=names.map(name=>{
  const start=source.indexOf(`function ${name}(`);
  assert.ok(start>=0,`${name} must exist`);
  const end=source.indexOf('\nfunction ',start+1);
  assert.ok(end>start,`${name} must have a following function boundary`);
  return source.slice(start,end);
 }).join('\n');
 const pass=Object.freeze({code:'SYNTHETIC-DESIGN',model:'Synthetic model'});
 for(const [status,refund,label] of [['pending',null,'Awaiting payment'],['paid',null,'Paid'],['ready',null,'Ready to collect'],['completed',null,'Collected'],['cancelled',null,'Cancelled'],['paid',{status:'pending'},'Refund processing.'],['paid',{status:'succeeded'},'Payment refunded.'],['paid',{status:'failed'},'Refund could not be completed.'],['<unknown>',null,'&lt;unknown&gt;']]){
  for(const mode of ['demo','stripe_test','airwallex_test','free_test']){
   const order=Object.freeze({id:'SYNTHETIC-ORDER',server:true,pass,status,refund,mode,priceCents:0,currency:'USD',fulfillmentType:'pickup'});
   const before=JSON.stringify(order);
   const context={progressPanel:()=>'<section class="order-progress">PRINT PROGRESS</section>',caseMaterialLabel,phoneColorName,arrow:()=>'→',t:v=>v,pickupStationPanel:()=>'',orderActionError:'',state:{pass},orderBook:{},orderForCode:()=>order,locale:()=> 'en-US',esc,
    money:()=> '0.00',PRINT_PRICE:'0.00',passPreview:()=>'',passName:()=> 'Synthetic design',effectCaption:()=>'',
    previewStationPanel:()=>'',scannedStation:null,stockScope:'',paymentState,paymentOrder:order,paymentPollCount:0,paymentError:'',passBusy:false,
    document:{querySelector:()=>null},location:{hash:'#payment?order=SYNTHETIC-ORDER&result=success'},URLSearchParams,
    fulfillmentView:()=>({state:'test'}),deviceFulfillmentPanel:()=>'',deliveryStatusPanel:()=>'',deliveryLabel:()=> 'On-site pickup',isPickup:()=>true};
   const html=vm.runInNewContext(`${declarations}\n${mode==='demo'?'passPage()':'paymentPage()'}`,context);
   assert.ok(html.includes(label),`${mode} ${status} ${refund?.status||''}: ${label}`);
   assert.ok(html.includes('SYNTHETIC-ORDER'));
   assert.equal(JSON.stringify(order),before,'rendering cannot change server order state');
   if(mode!=='demo'){
    assert.match(html,/<dt>Order status<\/dt><dd>/);
    if(paymentState(order).fulfilled){
     assert.match(html,/v35-order-detail/);
     assert.match(html,/<h1>Order details<\/h1>/);
     assert.match(html,new RegExp(`<span class="checkout-status">${label}</span>`));
     assert.doesNotMatch(html,/class="order-progress|PRINT PROGRESS|progress below/);
     assert.equal((html.match(/id="pickup-station-panel"/g)||[]).length,1);
    }

    if(status!=='pending'||refund)assert.doesNotMatch(html,/data-action="pay-provider"/);
    if(status==='pending'){
     assert.match(html,/Confirming your payment/);
     assert.doesNotMatch(html,/data-action="pay-provider"|Payment received/);
     if(!refund){
      context.location.hash='#payment?order=SYNTHETIC-ORDER';
      const pending=vm.runInNewContext(`${declarations}\npaymentPage()`,context);
      assert.match(pending,/class="checkout-pay-dock"/);assert.match(pending,/data-action="pay-provider" data-id="SYNTHETIC-ORDER"/);
      context.isPickup=()=>false;
      assert.doesNotMatch(vm.runInNewContext(`${declarations}\npaymentPage()`,context),/data-action="pay-provider"/,'Delivery orders cannot gain payment eligibility from the presentation change');
     }
    }
   }
  }
 }
});

// Development coverage for local design storage and the actual app handlers.
// These use synthetic state, not customer images or a real identity/AI channel.
function memoryDesignStorage(){
 const rows=new Map();
 return {rows,read:async key=>structuredClone(rows.get(key)),write:async(key,value)=>{rows.set(key,structuredClone(value));},update:async(key,transform,initial)=>{const value=transform(structuredClone(rows.get(key)??initial));rows.set(key,structuredClone(value));return value;}};
}
const customerIdentity=id=>({server:true,authenticated:true,customer:{id}});
function syntheticPass(){return createPersonalPass({source:'photo',designId:'bloom',model:phoneTemplates[0].model,phoneTemplateId:phoneTemplates[0].id,photo:'data:image/png;base64,aGVsbG8=',effect:'original',intensity:0,zoom:127,x:32,y:68,photoPlacement:{x:32,y:68,scale:127,rotation:23},collectionLayout:{zoom:113,x:46,y:54,artworkEdits:{}},addedArtwork:[{id:'extra-synthetic',type:'text',text:'Synthetic only',font:'sans',color:'#a234fd',x:36,y:61,scale:92,rotation:-12}]});}
const validateLocal=pass=>readPass(pass.code,pass);
test('verified identity selects a separate workspace; unknown sessions never read or inherit legacy caches',async()=>{
 const storage=memoryDesignStorage();storage.rows.set('draft-photo','old-unassigned');storage.rows.set('ai-membership-v1',{authenticated:true,customer:{id:8}});
 const guest=createDesignWorkspace({authenticated:false},storage),a=createDesignWorkspace(customerIdentity(8),storage),b=createDesignWorkspace(customerIdentity(9),storage);
 for(const [workspace,photo] of [[guest,'guest'],[a,'account-a'],[b,'account-b']])await workspace.write('draft-photo',photo);
 assert.equal(await a.read('draft-photo'),'account-a');assert.equal(await b.read('draft-photo'),'account-b');assert.equal(await guest.read('draft-photo'),'guest');
 assert.equal(storage.rows.get('draft-photo'),'old-unassigned');assert.equal(storage.rows.get('ai-membership-v1').customer.id,8);
 for(const account of [null,{}, {authenticated:true},{authenticated:true,customer:{id:'../../guest'}},{authenticated:true,customer:{id:true}}]){
  assert.equal(designOwner(account),null);const unavailable=createDesignWorkspace(account,storage);
  await assert.rejects(unavailable.read('draft-photo'),/sign-in needs checking/);await assert.rejects(unavailable.write('draft-photo','bad'),/sign-in needs checking/);
 }
});
test('a locked workspace rejects delayed reads and queued writes while preserving already committed data',async()=>{
 const storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage);
 await workspace.write('draft-photo','original');let release;
 const delayed=createDesignWorkspace(customerIdentity(8),{...storage,read:()=>new Promise(resolve=>release=resolve)});
 const pending=delayed.read('draft-photo');delayed.lock();release('private-image');await assert.rejects(pending,/sign-in needs checking/);
 let commit;const queued=createDesignWorkspace(customerIdentity(8),{...storage,update:(key,transform,initial)=>new Promise((resolve,reject)=>{commit=()=>{try{const value=transform(initial);storage.rows.set(key,value);resolve(value);}catch(error){reject(error);}};})});
 const write=queued.update('draft-photo',()=> 'late-write','original');queued.lock();commit();await assert.rejects(write,/sign-in needs checking/);
 assert.equal(await workspace.read('draft-photo'),'original');workspace.lock();await assert.rejects(workspace.read('draft-photo'),/sign-in needs checking/);
});
test('local library preserves exact composition, template and input pixels across save/reopen, without granting payment',async()=>{
 const storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage),library=createDesignLibrary(workspace,{validate:validateLocal,now:()=>1234});
 const pass=syntheticPass(),before=structuredClone(pass),template=phoneTemplate(pass.model,pass.phoneTemplateId);
 await library.save(pass,template);await library.save(pass,template);pass.photoPlacement.rotation=0;
 const reopened=createDesignLibrary(createDesignWorkspace(customerIdentity(8),storage),{validate:validateLocal});
 const rows=await reopened.list();assert.equal(rows.length,1);assert.deepEqual(rows[0].pass,before);assert.deepEqual(rows[0].phoneTemplate,template);
 assert.deepEqual(makePersonalDesign(rows[0].pass),makePersonalDesign(before));assert.equal(rows[0].pass.photo,before.photo);
 assert.equal(rows[0].updatedAt,1234);assert.equal(rows[0].paid,undefined);assert.equal(rows[0].pass.status,undefined);
 assert.deepEqual(await createDesignLibrary(createDesignWorkspace(customerIdentity(9),storage),{validate:validateLocal}).list(),[]);
 rows[0].pass.photo='altered-view';assert.deepEqual((await reopened.list())[0].pass,before);
 await reopened.remove(before.code);assert.deepEqual(await reopened.list(),[]);
});
test('storage and invalid snapshot failures remain failures, with existing records preserved',async()=>{
 const storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage),library=createDesignLibrary(workspace,{validate:validateLocal});
 const pass=syntheticPass();await library.save(pass);
 await assert.rejects(library.save({...pass,photo:'https://arbitrary.example/private.jpg'}),/photo/);
 assert.equal((await library.list()).length,1);
 const broken=createDesignLibrary(createDesignWorkspace(customerIdentity(8),{...storage,update:async()=>{throw Error('Quota exceeded');}}),{validate:validateLocal});
 await assert.rejects(broken.save(pass),/Quota exceeded/);assert.equal((await library.list()).length,1);
});
test('local design pages expose distinct empty/loading/error states and bilingual real actions without private-data HTML injection',()=>{
 for(const lang of ['en-US','zh-CN']){
  const empty=myDesignsPage({lang});assert.match(empty,lang==='en-US'?/No cloud sync/:/不提供云同步/);assert.doesNotMatch(empty,/data-action="restore-legacy-draft"/);
  const busy=myDesignsPage({lang,busy:true});assert.match(busy,/role="status"/);
  const error=myDesignsPage({lang,error:'<unsafe>'});assert.match(error,/&lt;unsafe&gt;/);assert.match(error,/data-action="refresh-designs"/);
  const populated=myDesignsPage({lang,guest:true,rows:[{id:'"><script>',pass:{model:'<Synthetic>'},updatedAt:1234}],preview:()=>'<div>SYNTHETIC PREVIEW</div>'});
  assert.match(populated,/data-action="restore-design"/);assert.match(populated,/data-action="delete-design"/);assert.match(populated,/data-action="restore-legacy-draft"/);assert.match(populated,/SYNTHETIC PREVIEW/);assert.match(populated,/&lt;Synthetic&gt;/);assert.doesNotMatch(populated,/<script>/);
  const preview=designReview({pass:syntheticPass(),preview:()=>'<div>SYNTHETIC PREVIEW</div>',lang,busy:true});
  assert.match(preview,/<section .*aria-labelledby="v35-review-title"/);assert.doesNotMatch(preview,/<dialog|physical verification|print command/);assert.match(preview,/aria-current="step"/);assert.match(preview,/data-action="save-local-design" disabled/);assert.match(preview,/data-action="continue-design-checkout" disabled/);assert.match(preview,/data-action="close-design-review"/);
  assert.doesNotMatch(preview,/Design saved on this browser/);assert.match(designReview({pass:syntheticPass(),preview:()=>'',lang,saved:true}),/role="status"/);
  assert.doesNotMatch(preview,/sessionStorage|pay_status|QRCode|setTimeout|data-action="confirm-device-print"/);
 }
 const account=customerPage({...customerIdentity(8),customer:{id:8,email:'synthetic@example.test'},trialRemaining:2},{email:''});
 assert.match(account,/v35-account-story/);assert.match(account,/href="#my-designs"/);assert.match(account,/customer-profile-form/);assert.doesNotMatch(account,/OAuth|data-avatar|data-action="subscribe"/);
});
test('editor/account/design aliases retain original device, language and fragment data; mobile preview redirects through customize',async()=>{
 for(const [name,route] of [['customize','choose'],['account','account'],['my-designs','my-designs']]){
  const url=new URL(publicPageDestination(`http://127.0.0.1:4173/${name}.html?device_id=123&shop_id=351&lang=zh&source=photo#edit`));
  assert.equal(url.hash.split('?')[0],'#'+route);const params=new URLSearchParams(url.hash.split('?')[1]);
  for(const [key,value] of Object.entries({device_id:'123',shop_id:'351',lang:'zh',source:'photo',section:'edit'}))assert.equal(params.get(key),value);
  assert.match(await readFile(new URL(`../storefront/${name}.html`,import.meta.url),'utf8'),/src="\.\/v35-page-entry.js"/);
 }
 const original=new URL('http://127.0.0.1:4173/mobile-preview.html?device_id=123&shop_id=351&lang=zh&design=bloom#edit');
 const target=new URL(publicPageDestination(original));assert.equal(target.pathname,'/customize.html');assert.equal(target.search,original.search);assert.equal(target.hash,original.hash);
 assert.match(shellHeader(),/href="#my-designs"/);
});
function appFunction(source,name){
 const begin=source.indexOf(`function ${name}(`);assert.ok(begin>=0,name);
 const end=source.indexOf('\nfunction ',begin+1),asyncEnd=source.indexOf('\nasync function ',begin+1);
 const ends=[end,asyncEnd].filter(value=>value>=0);
 return (source.slice(Math.max(0,begin-6),begin)==='async '?'async ':'')+source.slice(begin,Math.min(...ends));
}
test('actual editor submit opens a validated preview; saving stays local and only review-order creates a checkout draft',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),storage=memoryDesignStorage();
 const workspace=createDesignWorkspace(customerIdentity(8),storage),library=createDesignLibrary(workspace,{validate:validateLocal});
 let submit,click;const writes=[],routes=[],notices=[];const pass=syntheticPass();
 const context={app:{addEventListener:(name,fn)=>{if(name==='submit')submit=fn;else click=fn;}},sessionCheckBusy:false,photoBusy:false,aiBusy:false,passBusy:false,reviewPass:null,reviewSaved:false,comparing:false,
  isPhoto,state:{...pass,caseMaterial:'standard',editOrderId:null},phoneModels:[pass.model],refreshStockChoices:async()=>{},stockSelection:()=>({templateId:pass.phoneTemplateId}),createPersonalPass,layoutSelection:value=>value,workspace,library,
  phoneTemplate,orderBook:{orders:{}},checkoutDraft:null,PRINT_AVAILABLE:true,privateWrite:async(name,value)=>{writes.push({name,value});await workspace.write(name,value);},crypto,
  location:{hash:'#choose'},render:()=>{},notify:message=>notices.push(message),go:route=>routes.push(route),locale:()=> 'en-US'};
 const submitStart=source.indexOf("app.addEventListener('submit',async event=>{");
 const clickStart=source.indexOf("app.addEventListener('click',async event=>{",submitStart);
 const clickEnd=source.indexOf("  if(el.dataset.lookAction==='open')",clickStart);
 vm.createContext(context);vm.runInContext(appFunction(source,'assertCurrentColor')+'\n'+appFunction(source,'prepareDesignReview')+'\n'+source.slice(submitStart,clickStart)+source.slice(clickStart,clickEnd)+'});',context);
 await submit({target:{id:'design-form'},preventDefault(){}});
 assert.ok(context.reviewPass);assert.deepEqual(context.reviewPass.photoPlacement,pass.photoPlacement);assert.equal(context.checkoutDraft,null);assert.equal(writes.length,0);assert.deepEqual(routes,['review']);
 const button=action=>({preventDefault(){},target:{closest:()=>({dataset:{action},disabled:false})}});
 await click(button('save-local-design'));assert.equal((await library.list()).length,1);assert.equal(writes.length,0);assert.deepEqual(routes,['review']);assert.equal(notices.length,1);
 await click(button('continue-design-checkout'));assert.equal(writes.length,1);assert.equal(writes[0].name,'checkout-draft');assert.deepEqual(writes[0].value.pass.photoPlacement,pass.photoPlacement);assert.equal(routes.at(-1),'checkout');assert.equal(context.reviewPass,null);
});
test('actual restore handler retains rotations, text, crop and original bytes while clearing order authority',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),pass=syntheticPass(),before=JSON.stringify(pass),writes=[],routes=[];
 const context={readPass,phoneModels:[pass.model],privateWrite:async(name,value)=>writes.push([name,value]),workspace:{check(){}},finishInlineText:()=>{},state:{pass:{paid:true},job:{status:'printing'},editOrderId:'OLD'},structuredClone,
  stockCatalogStatus:'ready',stockSelection:()=>null,reconcilePhoneColor,colorNotice:false,aiJob:{id:'OLD'},selectedArtwork:'OLD',comparing:true,reviewPass:{},save:()=>{},go:route=>routes.push(route),notify:()=>{},pass};
 await vm.runInNewContext(appFunction(source,'syncDraftColor')+'\n'+appFunction(source,'restoreLocalDesign')+'\nrestoreLocalDesign(pass)',context);
 assert.equal(context.state.pass,null);assert.equal(context.state.job,null);assert.equal(context.state.editOrderId,null);assert.equal(context.aiJob,null);
 assert.equal(context.state.photo,pass.photo);assert.deepEqual(context.state.photoPlacement,pass.photoPlacement);assert.deepEqual(context.state.photoArtwork,pass.addedArtwork);
 assert.equal(context.state.artworkLayouts.bloom.zoom,113);assert.equal(context.state.zoom,127);assert.equal(writes[0][0],'draft-photo');assert.equal(writes[0][1],pass.photo);assert.equal(routes.at(-1),'choose');assert.equal(JSON.stringify(pass),before);
});
test('the actual library loader keeps bundled templates valid instead of treating them as supplier uploads',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage),library=createDesignLibrary(workspace,{validate:validateLocal});
 const pass=syntheticPass();await library.save(pass,phoneTemplate(pass.model,pass.phoneTemplateId));let registrations=0;
 const context={privateRead:key=>workspace.read(key),library,photoDraftLibrary:createPhotoDraftLibrary(workspace),localPhotoDrafts:[],localDesigns:[],localDesignError:'',localDesignBusy:false,registerSupplierTemplates(){registrations++;throw Error('Invalid supplier template');}};
 await vm.runInNewContext(appFunction(source,'loadLocalDesigns')+'\nloadLocalDesigns()',context);
 assert.equal(registrations,0);assert.equal(context.localDesigns.length,1);assert.equal(context.localDesignError,'');assert.equal(context.localDesignBusy,false);
});
test('actual identity merge clears private memory on a changed session before reload and rejects late AI results',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage);
 await workspace.write('draft-photo','synthetic-private-photo');let reloads=0;
 const context={orderSuccessDialog:null,workspace,designOwner,freshMembership:()=>({jobs:{}}),freshOrders:()=>({orders:{}}),privateUpdate:(...args)=>workspace.update(...args),save:()=>{},state:{photo:'synthetic-private-photo',pass:{code:'private'},artworkLayouts:{secret:{}},photoArtwork:[{}]},membership:customerIdentity(8),aiJob:{customerId:8,remoteId:'private'},checkoutDraft:{},reviewPass:{},localDesigns:[{}],localPhotoDrafts:[{}],orderRows:[{}],paymentOrder:{},customerUI:{ledger:[{}]},location:{reload(){reloads++;}},data:customerIdentity(9)};
 vm.createContext(context);vm.runInContext(appFunction(source,'lockPrivateWorkspace')+'\n'+appFunction(source,'mergeAIAccount')+'\n'+appFunction(source,'rememberLiveJob'),context);
 await assert.rejects(vm.runInContext('mergeAIAccount(data)',context),/sign-in changed/);
 assert.equal(reloads,1);assert.equal(workspace.active,false);assert.equal(context.state.photo,'');assert.equal(context.state.pass,null);assert.equal(context.aiJob,null);assert.equal(context.checkoutDraft,null);assert.equal(context.localDesigns.length,0);assert.equal(context.localPhotoDrafts.length,0);assert.equal(context.customerUI.ledger.length,0);
 assert.equal(storage.rows.get('v35:customer-8:draft-photo'),'synthetic-private-photo');assert.equal(storage.rows.has('v35:customer-9:draft-photo'),false);
 await assert.rejects(vm.runInContext("rememberLiveJob({id:'late-private-result',status:'ready',customerId:8})",context),/sign-in needs checking/);assert.equal(context.aiJob,null);
});

test('actual sign-out failure still clears the private view, and rejected verification codes never sign in',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 for(const action of ['logout','verify']){
  const storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage);let verificationCalls=0,syncCalls=0,navigations=0;
  const context={orderSuccessDialog:null,workspace,customerUI:{busy:false,email:'synthetic@example.test',ledger:[{}],codeSent:false},state:{photo:'synthetic-private'},membership:customerIdentity(8),aiJob:{},localDesigns:[{}],orderRows:[],reviewPass:{},paymentOrder:{},checkoutDraft:{},freshOrders:()=>({orders:{}}),freshMembership:()=>({jobs:{}}),
   render:()=>{},signOutCustomer:async()=>{throw Error('Unknown sign-out result');},verifyEmailCode:async(email,code)=>{verificationCalls++;assert.equal(code,'123456');throw Error('Code expired');},syncAIAccount:async()=>{syncCalls++;},go:()=>{navigations++;},location:{reload(){navigations++;}}};
  vm.createContext(context);vm.runInContext(appFunction(source,'lockPrivateWorkspace')+'\n'+appFunction(source,'handleCustomer'),context);
  await vm.runInContext(`handleCustomer('${action}',new Map([['code','123456']]))`,context);
  assert.equal(navigations,0);assert.equal(syncCalls,0);assert.equal(context.customerUI.busy,false);
  if(action==='logout'){assert.equal(workspace.active,false);assert.equal(context.state.photo,'');assert.equal(context.membership.authenticated,false);assert.equal(context.customerUI.ledger.length,0);assert.match(context.customerUI.error,/Unknown sign-out/);}
  else{assert.equal(verificationCalls,1);assert.match(context.customerUI.error,/Code expired/);}
 }
});
test('AI submission requires the current server identity and cannot start after account verification fails',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');let submissions=0;
 const context={aiBusy:false,aiUi:{},membership:{authenticated:true},aiJob:{mode:'live',status:'awaiting_confirmation'},render:()=>{},notify:()=>{},location:{hash:'#choose'},syncAIAccount:async()=>{throw Error('Session unavailable');},workspace:{check(){}},submitLiveRender:async()=>{submissions++;}};
 await vm.runInNewContext(appFunction(source,'confirmAI')+'\nconfirmAI(true,true)',context);
 assert.equal(submissions,0);assert.equal(context.aiBusy,false);assert.equal(context.aiJob.status,'awaiting_confirmation');assert.match(context.aiUi.error,/Session unavailable/);
});

const previewColor=(template=phoneTemplates[0],code='natural',version=1)=>({code,name:'Natural <body>',rgb:{r:10,g:120,b:230},isDefault:false,resource:{version,templateId:template.id,width:template.sourceWidth,height:template.sourceHeight,overlay:'/media/phone-colors/'+String(version).padStart(32,'0')+'/overlay.png',mask:'/media/phone-colors/'+String(version).padStart(32,'0')+'/mask.png'}});
test('managed preview colors validate RGB, exact template, dimensions and local versioned paths',()=>{
 const template=phoneTemplates[0],color=previewColor(template);
 assert.deepEqual(validatePhoneColor(color,template),color);
 for(const rgb of [{r:true,g:1,b:2},{r:'1',g:1,b:2},{r:1.2,g:1,b:2},{r:256,g:1,b:2},{r:-1,g:1,b:2},{r:1,g:2}])assert.throws(()=>validatePhoneColor({...color,rgb},template));
 for(const changes of [{version:0},{version:'1'},{templateId:'wrong'},{width:1},{overlay:'https://evil.test/a.png'},{mask:'/media/../private.png'}])assert.throws(()=>validatePhoneColor({...color,resource:{...color.resource,...changes}},template));
 assert.deepEqual(validPhoneColors([color,color,{...color,code:'bad',resource:null}],template),[color]);
});
test('RGB-only model colors survive drafts, render safely and send a validated RGB selection',()=>{
 const color={code:'blue',name:'Blue',rgb:{r:20,g:40,b:80},isDefault:false,previewMode:'rgb',resource:null};
 assert.deepEqual(validatePhoneColor(color),color);
 assert.deepEqual(colorSelection(color),{code:'blue',version:0,rgb:color.rgb});
 const pass=createPersonalPass({source:'collection',designId:'bloom',model:phoneTemplates[0].model,phoneColor:color,effect:'original',intensity:0,zoom:100,x:50,y:50});
 assert.deepEqual(readPass(pass.code,pass).phoneColor,color);
 assert.doesNotThrow(()=>phone(makePersonalDesign(pass),pass.model));
 assert.equal(reconcilePhoneColor(color,[{...color,rgb:{r:1,g:2,b:3}}]).changed,true);
 assert.match(colorPicker([color],color),/background:rgb\(20,40,80\)/);
 for(const rgb of [{r:true,g:0,b:0},{r:300,g:0,b:0},{r:1,g:2}])assert.throws(()=>validatePhoneColor({...color,rgb}));
});
test('color names follow the selected language without changing saved bilingual data',()=>{
 const color={...previewColor(),name:'石墨色 / Graphite'},before=structuredClone(color);
 assert.equal(phoneColorName(color,'en-US'),'Graphite');assert.equal(phoneColorName(color,'zh-CN'),'石墨色');
 assert.equal(phoneColorName({...color,name:'Black / White'},'en-US'),'Black / White');
 assert.equal(phoneColorName({...color,name:''},'en-US'),color.code);
 assert.doesNotMatch(colorPicker([color],color,'en-US'),/石墨色/);
 assert.doesNotMatch(colorPicker([color],color,'zh-CN'),/Graphite/);
 for(const [lang,label,other] of [['en-US','Graphite','石墨色'],['zh-CN','石墨色','Graphite']]){
  const html=designReview({pass:{model:'Test phone',phoneColor:color},preview:()=>'',lang});
  assert(html.includes(label));assert(!html.includes(other));
 }
 assert.deepEqual(color,before);
});
test('no colors skip the picker; defaults, single/multiple colors and stale selections stay model-specific',()=>{
 const one=previewColor(),two={...previewColor(undefined,'other'),isDefault:true};
 for(const colors of [undefined,[],null])assert.equal(colorPicker(colors||[],null),'');
 assert.equal(reconcilePhoneColor(null,[one]).color.code,one.code);
 assert.equal(reconcilePhoneColor(null,[one,two]).color.code,two.code);
 assert.equal(reconcilePhoneColor(one,[one,two]).color.code,one.code);
 assert.equal(reconcilePhoneColor(one,[]).color,null);assert.equal(reconcilePhoneColor(one,[]).changed,true);
 assert.equal(reconcilePhoneColor(one,[previewColor(undefined,'natural',2)]).changed,true);
 assert.equal(reconcilePhoneColor(one,[{...one,rgb:{r:0,g:0,b:0}}]).changed,true);
 for(const lang of ['en-US','zh-CN']){
  const html=colorPicker([one,two],two,lang,true);
  assert.match(html,/background:rgb\(10,120,230\)/);assert.match(html,/data-phone-color="other" aria-pressed="true"/);
  assert.match(html,/role="status"/);assert.match(html,/&lt;body&gt;/);assert.doesNotMatch(html,/<body>/);
  assert.match(colorPicker([],null,lang,true),/role="status"/);assert.doesNotMatch(colorPicker([],null,lang,true),/fieldset/);
 }
});
test('actual draft reconciliation clears an old model color, selects its own default and reports resource changes',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const old=previewColor(),fresh=previewColor(undefined,'new',2);
 const context={state:{model:'new-model',phoneColor:old},stockCatalogStatus:'ready',stockSelection:()=>({colors:[fresh]}),reconcilePhoneColor,colorNotice:false};
 vm.createContext(context);vm.runInContext(appFunction(source,'syncDraftColor')+'\n'+appFunction(source,'assertCurrentColor'),context);
 vm.runInContext('syncDraftColor(true)',context);assert.equal(context.state.phoneColor.code,'new');assert.equal(context.colorNotice,false);
 context.state.phoneColor=old;vm.runInContext('syncDraftColor()',context);assert.equal(context.colorNotice,true);assert.equal(context.state.phoneColor.code,'new');
 context.locale=()=> 'en-US';context.selection={phoneColor:old};context.available={colors:[fresh]};
 assert.throws(()=>vm.runInContext('assertCurrentColor(selection,available)',context),/preview your design again/);
 context.stockSelection=()=>({colors:[]});vm.runInContext('syncDraftColor()',context);assert.equal(context.state.phoneColor,null);
});
test('a local design and server order retain their frozen body preview after current colors disappear',()=>{
 const template=phoneTemplates[0],color=previewColor(template);
 const pass=createPersonalPass({source:'collection',designId:'bloom',model:template.model,phoneTemplateId:template.id,phoneColor:color,effect:'original',intensity:0,zoom:100,x:50,y:50});
 const copy=readPass(pass.code,pass);assert.deepEqual(copy.phoneColor,color);
 const design=makePersonalDesign(copy),html=phone(design,copy.model);
 assert.match(html,new RegExp(color.resource.overlay));assert.match(html,new RegExp(color.resource.mask));
 const without=makePersonalDesign({...copy,phoneColor:null});delete design.phoneColor;assert.deepEqual(design,without);
 const order=savedOrder({reference:'frozen-color',snapshot:pass,status:'paid',mode:'demo',amount:'10.00',currency:'USD',revision:1});
 assert.deepEqual(order.pass.phoneColor,color);assert.equal(order.priceCents,1000);
});
test('order writes send only color code and version, leaving local frozen previews untouched',async()=>{
 const template=phoneTemplates[0],color=previewColor(template),snapshot={code:'synthetic',phoneColor:color},before=structuredClone(snapshot),sent=[];
 const fetcher=async(url,options)=>{sent.push({url,options});return {ok:true,json:async()=>url.includes('csrf')?{csrfToken:'synthetic'}:{reference:'synthetic'}};};
 for(const method of ['POST','PATCH'])await orderRequest('',{method,body:{snapshot},key:'a'.repeat(64),fetcher});
 for(const request of sent.filter(r=>r.url.includes('/orders/')))assert.deepEqual(JSON.parse(request.options.body).snapshot.phoneColor,{code:'natural',version:1});
 assert.deepEqual(snapshot,before);
});
test('actual export uses body assets only for preview and keeps native print dimensions and mask',async()=>{
 const template=phoneTemplates[0],color=previewColor(template),loads=[],canvases=[];
 const encoded=await readFile(new URL('../storefront'+template.mask,import.meta.url));
 const original={document:globalThis.document,Image:globalThis.Image,location:globalThis.location};
 const context={fillRect(){},save(){},restore(){},translate(){},rotate(){},scale(){},drawImage(){},filter:'none'};
 try{
  globalThis.location={href:'http://localhost/'};
  globalThis.Image=class{naturalWidth=600;naturalHeight=1200;set src(value){loads.push(value);queueMicrotask(()=>this.onload());}};
  globalThis.document={fonts:{ready:Promise.resolve()},createElement(){const c={width:0,height:0,getContext:()=>({...context}),toBlob:fn=>fn(new Blob([encoded]))};canvases.push(c);return c;}};
  const design={art:'solid',layers:[],phoneTemplateId:template.id,phoneColor:color};
  await exportCase(design,template.model,'print');
  assert.ok(loads.some(s=>s.endsWith(template.mask)));assert.ok(loads.every(s=>!s.includes('/phone-colors/')));
  assert.equal(canvases[0].width,template.printWidth);assert.equal(canvases[0].height,template.printHeight);
  loads.length=0;await exportCase(design,template.model,'preview');
  assert.ok(loads.some(s=>s.endsWith(color.resource.mask)));assert.ok(loads.some(s=>s.endsWith(color.resource.overlay)));
  loads.length=0;const rgbOnly={...color,previewMode:'rgb',resource:null};
  await exportCase({...design,phoneColor:rgbOnly},template.model,'preview');
  assert.ok(loads.every(s=>!s.includes('/phone-colors/')));
  loads.length=0;await exportCase({...design,phoneColor:rgbOnly},template.model,'print');
  assert.ok(loads.some(s=>s.endsWith(template.mask)));assert.ok(loads.every(s=>!s.includes('/phone-colors/')));
 }finally{for(const [key,value] of Object.entries(original)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}}
});

test('public color extensions preserve the stocked base template and discard only invalid variants',()=>{
 const template={...phoneTemplates[0],id:'supplier-887-'+ 'd'.repeat(20),inventoryItemId:887,dpi:null,previewOnly:true,model:'Synthetic Color Model',
  overlay:'/media/supplier-templates/'+'e'.repeat(64)+'-overlay.png',previewOverlay:'/media/supplier-templates/'+'e'.repeat(64)+'-overlay.png',mask:'/media/supplier-templates/'+'f'.repeat(64)+'-mask.png'};
 const color=previewColor(template);
 const catalog=colors=>({version:1,templates:[template],models:[{name:template.model,brand:'Synthetic',templateId:template.id,inventoryItemId:887,colors}]});
 for(const colors of [undefined,[],[{...color,resource:null}],[{...color,rgb:{r:0,g:0,b:999}}]]){
  applyStockCatalog(catalog(colors));assert.ok(stockSelection(template.model));assert.deepEqual(stockSelection(template.model).colors,[]);
  assert.equal(phoneTemplate(template.model).mask,template.mask);
 }
 applyStockCatalog(catalog([color]));assert.deepEqual(stockSelection(template.model).colors,[color]);
 const next={...color,rgb:{r:255,g:0,b:0}};applyStockCatalog(catalog([next]));assert.deepEqual(stockSelection(template.model).colors[0].rgb,next.rgb);
 applyStockCatalog({version:1,models:[],templates:[]});assert.equal(stockSelection(template.model),null);
});

test('a frozen color survives an explicit device template change without painting incompatible assets',()=>{
 const original=phoneTemplates[0],color=previewColor(original);
 const pass=createPersonalPass({source:'collection',designId:'bloom',model:original.model,phoneTemplateId:original.id,phoneColor:color,effect:'original',intensity:0,zoom:100,x:50,y:50});
 const next={...original,id:'supplier-888-'+ 'b'.repeat(20),inventoryItemId:888,dpi:null,previewOnly:true,
  overlay:'/media/supplier-templates/'+'c'.repeat(64)+'-overlay.png',previewOverlay:'/media/supplier-templates/'+'c'.repeat(64)+'-overlay.png',mask:'/media/supplier-templates/'+'d'.repeat(64)+'-mask.png'};
 const order=savedOrder({reference:'changed-device-template',snapshot:{...pass,phoneTemplateId:next.id},phone_template:next,status:'paid',mode:'free_test',amount:'0.00',currency:'USD',revision:2});
 assert.deepEqual(order.pass.phoneColor,color);
 const html=phone(makePersonalDesign(order.pass),order.pass.model);
 assert.ok(html.includes(next.previewOverlay));assert.ok(html.includes(next.mask));assert.ok(!html.includes('/phone-colors/'));
});

test('actual color click selects a current option and collapses settings with summary focus',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const start=source.indexOf("app.addEventListener('click',async event=>{"),end=source.indexOf('  if(el.dataset.quickFont)',start);
 const one=previewColor(),two=previewColor(undefined,'other',2);let handler,saves=0,previews=0,focuses=0;
 const picker={focus(){focuses++;}};
 const context={app:{addEventListener:(name,fn)=>{handler=fn;}},sessionCheckBusy:false,photoBusy:false,aiBusy:false,passBusy:false,
  state:{model:'synthetic',phoneColor:one},stockSelection:()=>({colors:[one,two]}),reviewPass:{},colorNotice:true,
  save:()=>{saves++;},render:()=>{previews++;},phoneSettingsOpen:true,document:{querySelector:selector=>{assert.equal(selector,'.phone-settings-summary');return picker;}},structuredClone};
 vm.runInNewContext(source.slice(start,end)+'});',context);
 const click=code=>handler({target:{closest:selector=>{assert.ok(selector.includes('[data-phone-color]'));return {dataset:{phoneColor:code}};}}});
 await click('other');assert.equal(context.state.phoneColor.code,'other');assert.equal(context.reviewPass,null);assert.equal(context.colorNotice,false);
 assert.equal(context.phoneSettingsOpen,false);assert.equal(saves,1);assert.equal(previews,1);assert.equal(focuses,1);
 await click('foreign-model-color');assert.equal(saves,1);assert.equal(context.state.phoneColor.code,'other');
});

test('actual local restore clears unavailable color while retaining composition and the immutable saved record',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),template=phoneTemplates[0],color=previewColor(template);
 const pass=createPersonalPass({source:'collection',designId:'bloom',model:template.model,phoneTemplateId:template.id,phoneColor:color,effect:'original',intensity:0,zoom:113,x:42,y:61});
 const before=JSON.stringify(pass),context={pass,readPass,phoneModels:[pass.model],privateWrite:async()=>{},workspace:{check(){}},finishInlineText:()=>{},state:{},structuredClone,
  stockCatalogStatus:'ready',stockSelection:()=>({templateId:template.id,colors:[]}),reconcilePhoneColor,colorNotice:false,save:()=>{},go:()=>{},notify:()=>{}};
 await vm.runInNewContext(appFunction(source,'syncDraftColor')+'\n'+appFunction(source,'restoreLocalDesign')+'\nrestoreLocalDesign(pass)',context);
 assert.equal(context.state.phoneColor,null);assert.equal(context.colorNotice,true);assert.equal(context.state.artworkLayouts.bloom.zoom,113);assert.equal(context.state.artworkLayouts.bloom.x,42);
 assert.equal(JSON.stringify(pass),before);
});

// Run the actual startup, persistence and refresh code against the real catalog
// module. Only HTTP/storage are synthetic; a failed read must remain distinct
// from a successfully loaded catalog with no colors.
async function startColorDraft(editor,response){
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const start=source.indexOf('async function startStorefront(){');
 const end=source.indexOf('try{if(!accountEntry',start);
 const refreshStart=source.indexOf('async function refreshStockChoices(){');
 const refreshEnd=source.indexOf('\nsetInterval(async()=>',refreshStart);
 assert.ok(start>=0&&end>start&&refreshStart>0&&refreshEnd>refreshStart);
 let currentResponse=response;
 const context=vm.createContext({createOrderSuccessTracker,singlePrintDraft,createStationFinder,selectSupplierTemplate,editorHistory:{record(){}},syncEditorHistoryButtons(){},
  document:{querySelector:()=>({textContent:''})},location:{hash:'#choose',href:'http://localhost/#choose'},
  localStorage:{getItem:key=>editor.get(key)||null,setItem:(key,value)=>editor.set(key,value)},
  t:value=>value,deviceScope:()=>'',scopeIds:()=>null,loadCatalog:async()=>null,
  loadStockCatalog:()=>loadStockCatalog(async()=>currentResponse(),''),fulfillmentConfig:async()=>({}),
  getAIAccount:async()=>customerIdentity(8),createDesignWorkspace,createDesignLibrary,createPhotoDraftLibrary,readPass,
  readDesign:async()=>undefined,writeDesign:async()=>{},updateDesign:async(key,transform,initial)=>transform(initial),
  freshMembership:()=>({jobs:{}}),freshOrders:()=>({orders:{}}),designs:[{id:'bloom'}],phoneModels:stockedPhoneModels,
  stations:[],aiStyles:[],aiExamples:[],effects:[],stockSelection,
  exampleFor:()=>({id:'portrait',results:{anime:'synthetic'}}),migrateRender:value=>value,
  frozenPhoneColor,reconcilePhoneColor,isPhoto,validateAddedArtwork,validatePlacement,validatePhotoPlacement,phoneBrands:()=>[],phoneBrand:()=> 'Synthetic',notify:message=>assert.fail(message),
 });
 Object.defineProperty(context,'stockCatalogStatus',{get:()=>stockCatalogStatus});
 const controller=await vm.runInContext(`(async()=>{${source.slice(start,end)}
  let stockRefreshedAt=0,modelBrand='Synthetic';
  ${appFunction(source,'syncDraftColor')}
  ${appFunction(source,'save')}
  ${source.slice(refreshStart,refreshEnd)}
  return {get state(){return state;},get changed(){return colorNotice;},save,refresh:refreshStockChoices};
 } return await startStorefront();})()`,context);
 assert.equal(typeof controller,'object','the actual startup must reach the draft state');
 return {controller,respond:next=>{currentResponse=next;}};
}
function draftColorCatalog(){
 const template={...phoneTemplates[0],id:'supplier-889-'+'a'.repeat(20),inventoryItemId:889,dpi:null,previewOnly:true,model:'Synthetic Draft Color Model',
  overlay:'/media/supplier-templates/'+'e'.repeat(64)+'-overlay.png',previewOverlay:'/media/supplier-templates/'+'e'.repeat(64)+'-overlay.png',mask:'/media/supplier-templates/'+'f'.repeat(64)+'-mask.png'};
 const selected=previewColor(template,'chosen'),fallback={...previewColor(template,'default'),isDefault:true};
 const catalog=colors=>({version:1,templates:[template],models:[{name:template.model,brand:'Synthetic',templateId:template.id,inventoryItemId:889,colors,styles:[{caseMaterial:'standard',available:true,templateId:template.id,inventoryItemId:889,colors},{caseMaterial:'magnetic',available:false,colors:[]}]}]});
 const draft={designId:'bloom',model:template.model,caseMaterial:'standard',phoneColor:selected,source:'collection',zoom:123,x:35,y:67};
 return {selected,fallback,catalog,draft};
}
test('503 startup and saves preserve the non-default draft color until a successful catalog refresh',async()=>{
 const {selected,fallback,catalog,draft}=draftColorCatalog();
 const key='v35:customer-8:editor',editor=new Map([[key,JSON.stringify(draft)]]),unavailable=()=>({ok:false,status:503});
 let session=await startColorDraft(editor,()=>({ok:true,json:async()=>catalog([fallback,selected])}));
 session.controller.save();assert.equal(JSON.parse(editor.get(key)).phoneColor.code,'chosen');
 session=await startColorDraft(editor,unavailable);
 for(let attempt=0;attempt<2;attempt++){
  const app=session.controller;
  assert.equal(stockCatalogStatus,'unavailable');assert.deepEqual(stockedPhoneModels,[]);assert.equal(stockSelection(draft.model),null);
  assert.equal(app.state.model,draft.model);assert.deepEqual(JSON.parse(JSON.stringify(app.state.phoneColor)),selected);assert.equal(app.changed,false);
  app.state.x=29;app.save();await app.refresh();
  assert.equal(JSON.parse(editor.get(key)).phoneColor.code,'chosen');assert.equal(JSON.parse(editor.get(key)).model,draft.model);
  session=await startColorDraft(editor,unavailable);
 }
 session.respond(()=>({ok:true,json:async()=>catalog([fallback,selected])}));
 await session.controller.refresh();
 assert.equal(stockCatalogStatus,'ready');assert.equal(session.controller.state.model,draft.model);
 assert.equal(session.controller.state.phoneColor.code,'chosen','recovery must not silently replace a saved non-default color');
 assert.equal(session.controller.changed,false);assert.equal(JSON.parse(editor.get(key)).x,29);
 assert.equal(JSON.parse(editor.get(key)).phoneColor.code,'chosen');
});
test('inventory updating preserves a draft; a confirmed empty color list then clears and persists its invalid selection',async()=>{
 const {catalog,draft}=draftColorCatalog(),key='v35:customer-8:editor',editor=new Map([[key,JSON.stringify(draft)]]);
 const session=await startColorDraft(editor,()=>({ok:true,json:async()=>({version:1,templates:[],models:[],availability:'updating'})}));
 assert.equal(stockCatalogStatus,'updating');assert.equal(session.controller.state.model,draft.model);
 assert.equal(session.controller.state.phoneColor.code,'chosen');assert.equal(session.controller.changed,false);
 session.controller.save();assert.equal(JSON.parse(editor.get(key)).phoneColor.code,'chosen');
 session.respond(()=>({ok:true,json:async()=>catalog([])}));await session.controller.refresh();
 assert.equal(session.controller.state.model,draft.model);assert.equal(session.controller.state.phoneColor,null);
 assert.equal(session.controller.changed,true);assert.equal(JSON.parse(editor.get(key)).phoneColor,null);
});
test('a successfully loaded startup catalog still rejects a removed color or unavailable model',async()=>{
 const {catalog,draft}=draftColorCatalog(),key='v35:customer-8:editor';
 for(const data of [catalog([]),{version:1,models:[],templates:[]}]){
  const editor=new Map([[key,JSON.stringify(draft)]]),{controller}=await startColorDraft(editor,()=>({ok:true,json:async()=>data}));
  assert.equal(stockCatalogStatus,'ready');assert.equal(controller.state.phoneColor,null);assert.equal(controller.changed,true);
  assert.equal(controller.state.model,data.models.length?draft.model:'');
  controller.save();assert.equal(JSON.parse(editor.get(key)).phoneColor,null);
 }
});
test('invalid cached color data is not restored while the catalog is unavailable',async()=>{
 const {draft}=draftColorCatalog(),key='v35:customer-8:editor';
 const editor=new Map([[key,JSON.stringify({...draft,phoneColor:{code:'broken',resource:null}})]]);
 const {controller}=await startColorDraft(editor,()=>({ok:false,status:503}));
 assert.equal(controller.state.model,draft.model);assert.equal(controller.state.phoneColor,undefined);
 controller.save();assert.equal(JSON.parse(editor.get(key)).phoneColor,undefined);
});
test('local design restore retains a valid frozen color during catalog failure and updating',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),template=phoneTemplates[0],color=previewColor(template);
 const pass=createPersonalPass({source:'collection',designId:'bloom',model:template.model,phoneTemplateId:template.id,phoneColor:color,effect:'original',intensity:0,zoom:113,x:42,y:61});
 const before=JSON.stringify(pass);
 for(const status of ['unavailable','updating']){
  let saves=0;
  const context={pass,readPass,phoneModels:[],stockCatalogStatus:status,privateWrite:async()=>{},workspace:{check(){}},finishInlineText:()=>{},state:{},structuredClone,
   stockSelection:()=>null,reconcilePhoneColor,colorNotice:false,save:()=>{saves++;},go:()=>{},notify:message=>assert.fail(message)};
  await vm.runInNewContext(appFunction(source,'syncDraftColor')+'\n'+appFunction(source,'restoreLocalDesign')+'\nrestoreLocalDesign(pass)',context);
  assert.equal(context.state.model,pass.model);assert.deepEqual(context.state.phoneColor,color);assert.equal(context.colorNotice,false);
  assert.equal(context.state.artworkLayouts.bloom.zoom,113);assert.equal(context.state.artworkLayouts.bloom.x,42);assert.equal(saves,1);
  assert.equal(JSON.stringify(pass),before);
 }
});

test('single-print local draft adjustment preserves artwork, idempotency and historical edits',async()=>{
 const {singlePrintDraft,singlePrintNotice,checkoutBody}=await import('../storefront/order-service.js');
 const original={quantity:4,requestKey:'existing-key',pass:{photo:'synthetic',x:32},expectedAmount:'40.00'};
 const draft=singlePrintDraft(original);
 assert.equal(draft.quantity,1);assert.equal(draft.quantityAdjusted,true);
 assert.equal(draft.pass,original.pass);assert.equal(draft.requestKey,original.requestKey);
 assert.equal(original.quantity,4);
 assert.deepEqual(singlePrintDraft(draft),draft);
 for(const lang of ['en','zh-CN'])assert.match(singlePrintNotice(draft,lang),/role="status"/);
 assert.equal(singlePrintNotice(singlePrintDraft({pass:{}})), '');
 const historical={...original,editId:'paid-order'};
 assert.equal(singlePrintDraft(historical),historical);
 assert.throws(()=>checkoutBody(original,{accepted:true,amount:'10.00'}),/single-print/);
 const body=checkoutBody(draft,{accepted:true,amount:'10.00'});
 assert.equal(body.quantity,1);assert.equal(body.expected_amount,'10.00');
 assert.equal(body.request_key,'existing-key');assert.equal(body.snapshot,original.pass);
});

test('QA actual checkout bootstrap persists one-copy adjustment across reloads without rotating a timed-out key',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const start=source.indexOf('let checkoutDraft;');
 const end=source.indexOf('for(const order of Object.values(orderBook.orders||{}))',start);
 assert.ok(start>=0&&end>start);
 let stored={quantity:3,requestKey:'previous-timeout-key',pass:{code:'synthetic',zoom:123,x:31,y:67}};
 const original=structuredClone(stored);let writes=0;
 for(let reload=0;reload<2;reload++){
  const context=vm.createContext({createOrderSuccessTracker,singlePrintDraft,createStationFinder,selectSupplierTemplate,editorHistory:{record(){}},syncEditorHistoryButtons(){},
   privateRead:async key=>{assert.equal(key,'checkout-draft');return structuredClone(stored);},
   privateWrite:async(key,value)=>{assert.equal(key,'checkout-draft');stored=structuredClone(value);writes++;},
   stopForStorage:()=>assert.fail('bootstrap unexpectedly failed'),
  });
  await vm.runInContext(`(async()=>{${source.slice(start,end)}})()`,context);
  assert.equal(stored.quantity,1);assert.equal(stored.quantityAdjusted,true);
  assert.equal(stored.requestKey,original.requestKey);assert.deepEqual(stored.pass,original.pass);
 }
 assert.equal(writes,2);
});

test('checkout entity entry preserves server order, channel return and station context without inventing payment',async()=>{
 await access(new URL('../storefront/checkout.html',import.meta.url));
 for(const [query,route] of [['','checkout'],['view=orders','orders'],['order=SYNTHETIC-1&result=success','payment'],['view=orders&order=SYNTHETIC-1&result=cancel','payment']]){
  const url=new URL(publicPageDestination(`https://example.test/checkout.html?${query}&device_id=D1&shop_id=S1&lang=zh#receipt`));
  assert.equal(url.pathname,'/');assert.equal(url.hash.split('?')[0],'#'+route);
  const params=new URLSearchParams(url.hash.split('?')[1]);
  assert.equal(params.get('device_id'),'D1');assert.equal(params.get('shop_id'),'S1');assert.equal(params.get('lang'),'zh');assert.equal(params.get('section'),'receipt');
  if(route==='payment'){assert.equal(params.get('order'),'SYNTHETIC-1');assert.equal(params.get('result'),query.includes('cancel')?'cancel':'success');}
  assert.equal(url.searchParams.get('device_id'),'D1');
 }
 const state=paymentState({status:'pending',mode:'stripe_test'},{returned:true});
 assert.equal(state.fulfilled,false);assert.equal(state.canPay,false);
});

test('orders loading and failure remain distinct from empty, and server text is escaped',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const page=source.match(/^function ordersPage\(\)\{.*$/m)[0];
 const status=source.match(/^function orderStatus\([^\n]+$/m)[0];
 const base={orderListPage,orderFilter:'all',orderSearch:'',orderCounts:null,designs:[],localized:v=>v?.name,progressPanel,progressPaymentText,caseMaterialLabel,stationContext:()=>'',orderLoading:false,orderError:'',orderRows:[],esc,paymentLabel:()=>'',deliveryLabel:()=>'',locale:()=> 'en-US',orderPage:2,orderHasMore:true};
 const render=overrides=>vm.runInNewContext(`${status}\n${page}\nordersPage()`,{...base,...overrides});
 const busy=render({orderLoading:true});assert.match(busy,/aria-busy="true"/);assert.match(busy,/role="status">Loading your orders/);assert.doesNotMatch(busy,/Your first design/);assert.match(busy,/data-action="refresh-orders" disabled/);
 const error=render({orderError:'<script>bad</script>'});assert.match(error,/role="alert"/);assert.match(error,/&lt;script&gt;/);assert.doesNotMatch(error,/Your first design|<script>/);
 assert.match(render({}),/No matching orders/);
 const row=Object.freeze({reference:'<img>',model_name:'<script>',status:'paid',mode:'stripe_test',currency:'USD',amount:'30.00',created_at:'2026-11-14T00:00:00Z'});
 const list=render({orderRows:[row]});assert.match(list,/USD 30.00/);assert.match(list,/data-id="&lt;img&gt;"/);assert.match(list,/Order details ↗/);assert.match(list,/data-page="1"/);assert.match(list,/data-page="3"/);assert.doesNotMatch(list,/<script>|pay-provider/);
});

// Run the complete production navigation function with controlled identity/API
// responses. No browser, database or external service is involved in this race.
async function qaOrdersNavigation(){
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const start=source.indexOf('async function navigate(');
 const end=source.indexOf('\nconst entryHash=',start);
 assert.ok(start>=0&&end>start);
 const identity=[];
 const context=vm.createContext({
  loadOrderHistory:async({request,page,filter,search,initial})=>initial||request('?page='+page+'&status='+filter+'&q='+encodeURIComponent(search)),
  URLSearchParams,location:{hash:'#orders'},navigationId:0,
  syncAIAccount:()=>new Promise(resolve=>identity.push(resolve)),
  workspace:{active:true},customerUI:{},clearTimeout:()=>{},
  stopPaymentPolling:()=>{},syncStationFinder:()=>{},paymentPollCount:0,paymentLoading:false,
  orderFilter:'all',orderSearch:'',orderCounts:null,
  orderLoading:false,orderError:'',orderRows:[],orderHasMore:false,
  orderPage:1,entryOrders:null,entryOrderError:'',
  orderRequest:async()=>({results:[{reference:'QA-SYNTHETIC'}],has_more:false}),
  render:()=>{},document:{querySelector:()=>null},
 });
 vm.runInContext(source.slice(start,end),context);
 return {context,identity};
}

test('QA orders navigation clears loading after a successful or failed server read',async()=>{
 for(const fails of [false,true]){
  const {context,identity}=await qaOrdersNavigation();
  if(fails)context.orderRequest=async()=>{throw Error('Synthetic API failure');};
  const navigation=context.navigate();identity[0]();await navigation;
  assert.equal(context.orderLoading,false);
  assert.equal(context.orderError,fails?'Synthetic API failure':'');
  assert.equal(context.orderRows.length,fails?0:1);
 }
});

test('account navigation shows the complete provider list only after the session is known',async()=>{
 const {context,identity}=await qaOrdersNavigation();
 const providerList=['google','facebook'];
 const views=[];
 context.location.hash='#account';
 context.membership={authenticated:false,socialProviders:[]};
 context.render=()=>views.push(customerPage(context.membership,context.customerUI));
 const opening=context.navigate();
 assert.equal(context.customerUI.loading,true);
 // Other app events may render while this request is still pending.
 context.render();
 assert.match(views[0],/Loading sign-in options/);
 assert.doesNotMatch(views[0],/customer-email-form|social-google|social-facebook/);
 context.membership={authenticated:false,socialProviders:providerList};
 identity[0]();
 await opening;
 assert.match(views[1],/customer-email-form/);
 assert.match(views[1],/data-customer-action="social-google"/);
 assert.match(views[1],/data-customer-action="social-facebook"/);
 assert.equal(views.length,2);
});

test('direct account entry reuses the startup session and offers reload when unavailable',async()=>{
 const {context,identity}=await qaOrdersNavigation();
 const views=[];
 context.location.hash='#account';
 context.membership={authenticated:false,socialProviders:['google','facebook']};
 context.render=()=>views.push(customerPage(context.membership,context.customerUI));
 await context.navigate({useInitialAccount:true});
 assert.equal(identity.length,0);
 assert.match(views[0],/social-google/);
 context.workspace.active=false;
 await context.navigate({useInitialAccount:true});
 assert.equal(identity.length,0);
 assert.match(views[1],/data-action="reload-account"/);
 assert.doesNotMatch(views[1],/customer-email-form|social-google/);
});

test('QA a superseded orders navigation cannot leave the newer loaded page permanently busy',async()=>{
 const {context,identity}=await qaOrdersNavigation();
 const oldNavigation=context.navigate();
 const newNavigation=context.navigate();
 identity[1]();await newNavigation;
 assert.equal(context.orderLoading,false);
 assert.equal(context.orderRows[0].reference,'QA-SYNTHETIC');
 // The older account read completes only after the newer page is ready.
 identity[0]();await oldNavigation;
 assert.equal(context.orderLoading,false,'stale navigation must not re-enable loading after the current navigation completed');
 assert.equal(context.orderRows[0].reference,'QA-SYNTHETIC');
});

test('superseded identity failures cannot overwrite the current orders error or restart its read',async()=>{
 const {context}=await qaOrdersNavigation();
 const pending=[];let reads=0;
 context.syncAIAccount=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));
 context.orderRequest=async()=>{reads++;throw Error('Current orders failure');};
 const oldNavigation=context.navigate();
 const newNavigation=context.navigate();
 pending[1].resolve();await newNavigation;
 context.customerUI.error='Current identity message';
 pending[0].reject(Error('Stale identity failure'));await oldNavigation;
 assert.equal(reads,1);
 assert.equal(context.customerUI.error,'Current identity message');
 assert.equal(context.orderError,'Current orders failure');
 assert.equal(context.orderLoading,false);
});

test('leaving orders retires a delayed identity continuation without consuming entry data',async()=>{
 const {context,identity}=await qaOrdersNavigation();
 let reads=0,renders=0;
 context.orderRequest=async()=>{reads++;return {results:[],has_more:false};};
 context.render=()=>{renders++;};
 const oldNavigation=context.navigate();
 context.location.hash='#home';await context.navigate();
 const entry={results:[{reference:'NEW-ENTRY'}],has_more:false};
 context.entryOrders=entry;context.entryOrderError='New entry error';
 const rendered=renders;
 identity[0]();await oldNavigation;
 assert.equal(reads,0);
 assert.equal(renders,rendered);
 assert.equal(context.orderLoading,false);
 assert.equal(context.entryOrders,entry);
 assert.equal(context.entryOrderError,'New entry error');
});

test('QA stale identity success preserves a current orders failure and refresh remains usable',async()=>{
 const {context,identity}=await qaOrdersNavigation();
 let reads=0;
 context.orderRequest=async()=>{reads++;if(reads===1)throw Error('Current read unavailable');return {results:[{reference:'REFRESHED'}],has_more:true};};
 const stale=context.navigate(),current=context.navigate();
 identity[1]();await current;
 identity[0]();await stale;
 assert.equal(reads,1);assert.equal(context.orderLoading,false);
 assert.equal(context.orderError,'Current read unavailable');
 const refresh=context.navigate();identity[2]();await refresh;
 assert.equal(reads,2);assert.equal(context.orderLoading,false);
 assert.equal(context.orderError,'');assert.equal(context.orderRows[0].reference,'REFRESHED');
 assert.equal(context.orderHasMore,true);
});

test('QA leaving and returning to orders ignores the first visit identity result',async()=>{
 const {context,identity}=await qaOrdersNavigation();let reads=0;
 context.orderRequest=async()=>{reads++;return {results:[{reference:'RETURN-VISIT'}],has_more:false};};
 const first=context.navigate();
 context.location.hash='#home';await context.navigate();
 context.location.hash='#orders';const returned=context.navigate();
 identity[1]();await returned;
 identity[0]();await first;
 assert.equal(reads,1);assert.equal(context.orderRows[0].reference,'RETURN-VISIT');
 assert.equal(context.orderLoading,false);assert.equal(context.orderError,'');
});

for(const oldFails of [false,true]){
 test(`QA an old orders API ${oldFails?'failure':'success'} cannot replace the latest page`,async()=>{
  const {context,identity}=await qaOrdersNavigation();const reads=[];
  context.orderRequest=()=>new Promise((resolve,reject)=>reads.push({resolve,reject}));
  const old=context.navigate();identity[0]();await new Promise(setImmediate);
  assert.equal(reads.length,1);assert.equal(context.orderLoading,true);
  const current=context.navigate();identity[1]();await new Promise(setImmediate);
  assert.equal(reads.length,2);
  reads[1].resolve({results:[{reference:'LATEST'}],has_more:true});await current;
  if(oldFails)reads[0].reject(Error('Old API failure'));
  else reads[0].resolve({results:[{reference:'STALE'}],has_more:false});
  await old;
  assert.equal(context.orderLoading,false);assert.equal(context.orderError,'');
  assert.equal(context.orderRows[0].reference,'LATEST');assert.equal(context.orderHasMore,true);
 });
}

test('merged catalog keeps body colors scoped to a case style and preserves both choices through a saved pass',()=>{
 const {catalog,selected,draft}=draftColorCatalog();
 const data=catalog([selected]),model=data.models[0];
 const magnetic={...data.templates[0],id:'supplier-890-'+'b'.repeat(20),inventoryItemId:890};
 data.templates.push(magnetic);
 model.styles[1]={caseMaterial:'magnetic',available:true,templateId:magnetic.id,inventoryItemId:890,colors:[selected]};
 applyStockCatalog(data);
 const standard=stockSelection(model.name,'standard'),magnet=stockSelection(model.name,'magnetic');
 assert.equal(standard.colors[0].code,'chosen');assert.deepEqual(magnet.colors,[]);
 assert.equal(magnet.templateId,magnetic.id);assert.equal(magnet.available,true);
 const pass=createPersonalPass({...draft,phoneTemplateId:standard.templateId,effect:'original',intensity:65});
 const restored=readPass(pass.code,JSON.parse(JSON.stringify(pass)));
 assert.equal(restored.caseMaterial,'standard');assert.equal(restored.phoneColor.code,'chosen');
 assert.equal(colorPicker(magnet.colors,null),'');
});

async function aiPhoneChangeHarness(){
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const writes=[],sent=[];
 const context={aiBusy:false,photoBusy:false,passBusy:false,sessionCheckBusy:false,aiUi:{accepted:true,error:'old error'},
  aiJob:{id:'AI-same-request',model:'iPhone 17',photo:'private synthetic photo',styleId:'anime',mode:'live',status:'awaiting_confirmation'},
  state:{model:'iPhone 17',caseMaterial:'standard',phoneColor:{code:'old'},phoneTemplateId:'old-template'},
  phoneModels:['iPhone 17','iPhone 13 Pro'],stockCatalogStatus:'ready',colorNotice:true,reviewPass:{old:true},
  membership:{authenticated:true},workspace:{check(){}},syncAIAccount:async()=>{},refreshStockChoices:async()=>{},
  render:()=>{},notify:()=>{},save:()=>{},selectSupplierTemplate:()=>{},stockSelection:()=>({templateId:'new-standard-template'}),document:{querySelector:()=>null},location:{hash:'#ai'},
  rememberLiveJob:async value=>{writes.push(structuredClone(value));context.aiJob=value;},
  submitLiveRender:async value=>{sent.push(structuredClone(value));return {...value,status:'queued',remoteId:'server-id'};}};
 vm.createContext(context);vm.runInContext(appFunction(source,'changeAIPhoneModel')+'\n'+appFunction(source,'confirmAI'),context);
 return {context,writes,sent};
}
test('changing the AI model preserves photo/style/request identity and submits the selected model',async()=>{
 const {context,writes,sent}=await aiPhoneChangeHarness();
 await context.changeAIPhoneModel('iPhone 13 Pro');
 assert.equal(context.aiJob.model,'iPhone 13 Pro');assert.equal(context.aiJob.id,'AI-same-request');
 assert.equal(context.aiJob.photo,'private synthetic photo');assert.equal(context.aiJob.styleId,'anime');
 assert.equal(context.state.model,'iPhone 13 Pro');assert.equal(context.state.caseMaterial,'standard');assert.equal(context.state.phoneTemplateId,'new-standard-template');assert.equal(context.state.phoneColor,null);
 assert.equal(context.aiUi.accepted,false);assert.equal(context.aiUi.error,'');assert.equal(sent.length,0);
 await context.confirmAI(true,true);
 assert.equal(sent.length,1);assert.equal(sent[0].phoneTemplateId,'new-standard-template');assert.equal(sent[0].caseMaterial,'standard');assert.equal(sent[0].model,'iPhone 13 Pro');assert.equal(sent[0].submissionAttempted,true);
 assert(writes.find(item=>item.submissionAttempted&&item.status==='awaiting_confirmation'),'Attempt flag persists before sending');
});
test('unavailable models and frozen AI jobs cannot change their original selection',async()=>{
 for(const overrides of [{stockCatalogStatus:'unavailable'},{phoneModels:[]},{aiBusy:true}]){
  const {context,writes}=await aiPhoneChangeHarness();Object.assign(context,overrides);
  await context.changeAIPhoneModel('iPhone 13 Pro');assert.equal(context.aiJob.model,'iPhone 17');assert.equal(writes.length,0);
 }
 for(const change of [{submissionAttempted:true},{remoteId:'already-created'},{status:'queued'},{status:'ready'}]){
  const {context,writes}=await aiPhoneChangeHarness();Object.assign(context.aiJob,change);
  await context.changeAIPhoneModel('iPhone 13 Pro');assert.equal(context.aiJob.model,'iPhone 17');assert.equal(writes.length,0);
 }
});
test('an ambiguous AI submission freezes model changes and retries with the original request key',async()=>{
 const {context}=await aiPhoneChangeHarness(),requests=[];
 context.submitLiveRender=async value=>{requests.push(structuredClone(value));throw Error('Synthetic timeout');};
 await context.confirmAI(true,true);assert.equal(context.aiJob.submissionAttempted,true);
 await context.changeAIPhoneModel('iPhone 13 Pro');assert.equal(context.aiJob.model,'iPhone 17');
 await context.confirmAI(true,true);
 assert.equal(requests.length,2);assert.equal(requests[0].id,requests[1].id);assert.equal(requests[0].model,requests[1].model);
});


test('prototype review shows one case and only configured body colors, without internal technical copy',()=>{
 const pass={...syntheticPass(),caseMaterial:'magnetic',quantity:20};
 const html=designReview({pass,preview:()=>'<div>preview</div>'});
 assert.match(html,/Phone model/);assert.match(html,/Design your case/);assert.match(html,/Review &amp; confirm|Review & confirm/);
 assert.match(html,/<dd>Magnetic<\/dd>/);assert.match(html,/<dd>1 case<\/dd>/);
 assert.doesNotMatch(html,/Phone body color|physical verification|print command|<dialog/);
 assert.match(html,/Save draft/);assert.match(html,/Print now/);
 const colored=designReview({pass:{...pass,phoneColor:{name:'<script>test</script>'}},preview:()=>'',lang:'zh-CN'});
 assert.match(colored,/机身颜色/);assert.match(colored,/&lt;script&gt;test&lt;\/script&gt;/);assert.match(colored,/1 个手机壳/);
});

test('editor history restores composition without restoring phone, color or image selections',async()=>{
 const {createEditorHistory}=await import('../storefront/editor-history.js');
 const history=createEditorHistory(),state={source:'photo',photo:'private-original',model:'Phone A',caseMaterial:'standard',photoColor:'gold',photoArtwork:[],photoPlacement:null};
 history.record(state,'owner-a');state.photoArtwork.push({id:'text-1',text:'Hello',x:50});history.record(state,'owner-a');
 state.photoArtwork[0].x=65;history.record(state,'owner-a');
 assert(history.undo(state,'owner-a'));assert.equal(state.photoArtwork[0].x,50);
 assert(history.undo(state,'owner-a'));assert.deepEqual(state.photoArtwork,[]);
 assert(history.redo(state,'owner-a'));assert.equal(state.photoArtwork[0].text,'Hello');
 assert.equal(state.photo,'private-original');assert.equal(state.model,'Phone A');assert.equal(state.photoColor,'gold');
 state.photoArtwork[0].text='New text';history.record(state,'owner-a');assert.equal(history.canRedo,false);
 state.photo='replacement';assert.equal(history.undo(state,'owner-a'),false,'Replacing a photo starts a new composition history');
 state.photoArtwork.push({id:'text-2'});history.record(state,'owner-a');assert(history.canUndo);
 assert.equal(history.undo(state,'owner-b'),false,'History cannot cross customer workspaces');
 state.model='Phone B';assert.equal(history.undo(state,'owner-b'),false,'History cannot restore a different phone');
});
test('editor composition history retains a bounded sequence and ignores unchanged saves',async()=>{
 const {createEditorHistory}=await import('../storefront/editor-history.js');
 const history=createEditorHistory(3),state={source:'collection',designId:'bloom',zoom:100};
 history.record(state,'guest');history.record(state,'guest');assert.equal(history.canUndo,false);
 for(const zoom of [110,120,130]){state.zoom=zoom;history.record(state,'guest');}
 assert(history.undo(state,'guest'));assert.equal(state.zoom,120);
 assert(history.undo(state,'guest'));assert.equal(state.zoom,110);
 assert.equal(history.undo(state,'guest'),false);
});
test('opening editing controls does not add an undo step for lazily initialized layout defaults',async()=>{
 const {createEditorHistory}=await import('../storefront/editor-history.js');
 const history=createEditorHistory(),state={source:'photo',designId:'bloom',photo:'original',zoom:100,photoArtwork:[],artworkLayouts:{},photoPlacement:null};
 history.record(state,'guest');
 state.artworkLayouts.bloom={zoom:100,x:50,y:50,artworkEdits:{},addedArtwork:[]};
 state.photoPlacement={x:50,y:50,scale:100,rotation:0};
 history.record(state,'guest');assert.equal(history.canUndo,false);
 state.photoArtwork.push({id:'sticker'});history.record(state,'guest');
 assert(history.undo(state,'guest'));assert.deepEqual(state.photoArtwork,[]);
});

test('photo fit survives save/restore and uses matching cover/contain geometry',async()=>{
 const {photoRect}=await import('../storefront/print-export.js');
 for(const fit of ['cover','contain','blur']){
  const input={...syntheticPass(),photoPlacement:{x:50,y:50,scale:100,rotation:0,fit}};
  const pass=readPass(input.code,input),design=makePersonalDesign(pass);
  assert.equal(pass.photoPlacement.fit,fit);assert.equal(design.photoPlacement.fit,fit);
  const html=phone(design,pass.model);
  assert.match(html,new RegExp('object-fit:'+(fit==='cover'?'cover':'contain')));
  assert.equal(html.includes('photo-blur-background'),fit==='blur');
 }
 assert.throws(()=>validatePhotoPlacement({x:50,y:50,scale:100,rotation:0,fit:'url(secret)'}),/fit/);
 assert.deepEqual(photoRect(400,200,300,600,50,50,'contain'),{x:0,y:225,width:300,height:150,scale:.75});
 assert.deepEqual(photoRect(400,200,300,600,50,50,'cover'),{x:-450,y:0,width:1200,height:600,scale:3});
});

test('prototype checkout dock preserves consent, loading, fulfillment and availability gates',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const declarations=['checkoutDesignCard','checkoutDock','checkoutPage'].map(name=>appFunction(source,name)).join('\n');
 const base={checkoutDraft:{quantity:1,fulfillmentType:'pickup',pass:{source:'photo',model:'Synthetic phone',caseMaterial:'standard'}},orderBook:{orders:{}},locale:()=> 'en-US',
  PRINT_PRICE:'$12.34',PRINT_AVAILABLE:true,paymentConfig:{available:true,provider:'stripe',mode:'live'},paymentError:'',paymentLoading:false,passBusy:false,
  providerName:()=> 'Stripe',money:()=> '12.34',esc,caseMaterialLabel,phoneColorName,passPreview:()=>'<div class="phone-case"></div>',passName:()=> 'My design',arrow:()=> '→',
  courierAddressForm:()=>'<form id="courier-address-form"></form>',pickupStationPanel:()=>'',pickupCheckoutReady:()=>true,singlePrintNotice:()=>'',deliveryOptions:()=>'',deliveryLabel:()=> 'Courier delivery',scannedStation:null,
  quoteBreakdown:()=>'',checkoutEmailField:()=>'',membership:{},devicePrinting:{simulated:false}};
 const html=extra=>vm.runInNewContext(declarations+'\ncheckoutPage()',{...base,...extra});
 const normal=html({});assert.match(normal,/id="print-checkout-form"/);assert.match(normal,/name="accepted" type="checkbox" required/);assert.match(normal,/type="submit"/);assert.match(normal,/\$12.34/);
 for(const extra of [{paymentLoading:true},{paymentConfig:{available:false}},{paymentError:'Unavailable'},{PRINT_AVAILABLE:false},{checkoutDraft:{...base.checkoutDraft,fulfillmentType:'air'}}]){
  const rendered=html(extra);assert.doesNotMatch(rendered,/id="print-checkout-form"/);
  assert.equal((rendered.match(/class="checkout-pay-dock"/g)||[]).length,1);
  assert.match(rendered,/class="button primary"\s+disabled/);
 }
 assert.match(html({pickupCheckoutReady:()=>false}),/type="submit" class="button primary"\s+disabled/);
 const courierDraft={...base.checkoutDraft,fulfillmentType:'courier',deliveryAddressSaved:true};
 const courierConfig={available:true,provider:'stripe',mode:'test',fulfillment_type:'courier',quote:{print_amount:'12.34',shipping_amount:'4.00',total_amount:'16.34',currency:'USD'}};
 const courier=html({checkoutDraft:courierDraft,paymentConfig:courierConfig,pickupCheckoutReady:()=>false});
 assert.match(courier,/id="courier-address-form"/);assert.match(courier,/\$16.34/);assert.match(courier,/type="submit" class="button primary"\s*>/);
 assert.match(html({checkoutDraft:{...courierDraft,deliveryAddressSaved:false},paymentConfig:courierConfig}),/type="submit" class="button primary"\s+disabled/);
 const free=html({paymentConfig:{available:true,provider:'free_test',zero_price_test:true},PRINT_PRICE:'$0.00'});
 assert.match(free,/Confirm free order/);assert.doesNotMatch(free,/Awaiting payment/);
 const freeCourier=html({devicePrinting:{simulated:true},checkoutDraft:courierDraft,paymentConfig:{...courierConfig,provider:'free',mode:'test',zero_price_test:true,quote:{...courierConfig.quote,print_amount:'0.00',shipping_amount:'0.00',total_amount:'0.00'}}});
 assert.match(freeCourier,/Confirm free order/);assert.match(freeCourier,/no-charge delivery test order/);assert.doesNotMatch(freeCourier,/Confirm at the station/);

});

async function qaStudioEntry(){
 const {context}=await qaOrdersNavigation();
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const start=source.indexOf('function clearPreviousPhotoArtwork(){');
 const end=source.indexOf('// The editor keeps a draft per template.',start);
 const writes=[];
 Object.assign(context,{
  location:{hash:'#choose?source=photo&studio=1'},syncAIAccount:async()=>{},
  refreshStockChoices:async()=>{},designs:[],save:()=>{},notify:message=>{throw Error(message);},
  state:{source:'photo',photo:'old-upload',model:'iPhone 13 Pro',phoneColor:{rgb:'#535451'},caseMaterial:'standard',photoArtwork:[{id:'old-text'}],photoPlacement:{scale:150},ai:{jobId:'previous'},editOrderId:'old-order'},
  aiJob:{id:'generating-job',status:'generating',photo:'render-snapshot'},aiUi:{accepted:true,error:'old error'},
  photoDraftLibrary:{save:async()=>{}},photoBusy:false,effectPanelOpen:false,cropPanelOpen:true,editorPanels:{collection:true,graphics:true},
  finishInlineText:()=>{},privateWrite:async(key,value)=>{writes.push([key,value]);},
  opened:0,openAIStudio:()=>{context.opened++;},
  history:{replaceState:(_state,_title,hash)=>{context.location.hash=hash;}},
 });
 vm.runInContext(source.slice(start,end),context);
 return {context,writes};
}

test('external AI Studio entry clears the draft photo once, retaining phone choice and render snapshots',async()=>{
 const {context,writes}=await qaStudioEntry();
 await context.navigate();
 assert.equal(context.state.photo,'');assert.equal(context.state.ai,null);
 assert.equal(context.state.photoArtwork.length,0);assert.equal(context.state.photoPlacement,null);
 assert.equal(context.state.editOrderId,null);assert.equal(context.state.model,'iPhone 13 Pro');
 assert.equal(context.state.phoneColor.rgb,'#535451');assert.equal(context.state.caseMaterial,'standard');
 assert.deepEqual(writes,[['draft-photo','']]);
 assert.equal(context.aiJob.status,'generating');assert.equal(context.aiJob.photo,'render-snapshot');
 assert.equal(context.opened,1);assert.equal(context.effectPanelOpen,true);
 assert.equal(context.location.hash,'#choose?source=photo');
 // A subsequent navigation/refresh must not consume the newly uploaded image.
 context.state.photo='new-upload';await context.navigate();
 assert.equal(context.state.photo,'new-upload');assert.equal(writes.length,1);
 // Leaving and deliberately entering Studio again begins another creation.
 context.location.hash='#home';await context.navigate();
 context.location.hash='#choose?source=photo&studio=1';await context.navigate();
 assert.equal(context.state.photo,'');assert.equal(writes.length,2);
});

test('ordinary editor navigation keeps its photo, and obsolete Studio navigation cannot clear it',async()=>{
 const {context,writes}=await qaStudioEntry();
 context.location.hash='#choose';await context.navigate();
 assert.equal(context.state.photo,'old-upload');assert.equal(writes.length,0);
 let release;context.refreshStockChoices=()=>new Promise(resolve=>{release=resolve;});
 context.location.hash='#choose?source=photo&studio=1';const pending=context.navigate();
 await new Promise(resolve=>setImmediate(resolve));
 context.location.hash='#home';await context.navigate();release();await pending;
 assert.equal(context.state.photo,'old-upload');assert.equal(writes.length,0);
 assert.equal(context.location.hash,'#home');assert.equal(context.opened,0);
});

import {createPhotoDraftLibrary} from '../storefront/photo-drafts.js';
test('photo drafts are private, deduplicated editing snapshots without order or request authority',async()=>{
 const storage=memoryDesignStorage();
 const guest=createDesignWorkspace({authenticated:false},storage);
 const member=createDesignWorkspace({authenticated:true,customer:{id:8}},storage);
 let count=0;const drafts=createPhotoDraftLibrary(guest,{now:()=>42,id:()=>String(++count)});
 const state={source:'photo',photo:'data:image/png;base64,AAAA',model:'',photoPlacement:{x:42,y:31,scale:120,rotation:90},photoArtwork:[{id:'text'}],pass:{code:'private-order'},job:{id:'print'},aiJobId:'request',editOrderId:'order'};
 await drafts.save(state);await drafts.save(state);
 let rows=await drafts.list();assert.equal(rows.length,1);
 assert.equal(rows[0].snapshot.model,'','unfinished photos can be saved without a model');
 assert.deepEqual(rows[0].snapshot.photoPlacement,state.photoPlacement);
 for(const key of ['pass','job','aiJobId','editOrderId'])assert.equal(key in rows[0].snapshot,false);
 state.photoPlacement.x=90;assert.equal((await drafts.list())[0].snapshot.photoPlacement.x,42);
 assert.equal((await createPhotoDraftLibrary(member).list()).length,0);
 await drafts.save({source:'photo',photo:''});assert.equal((await drafts.list()).length,1);
 await drafts.remove(rows[0].id);assert.equal((await drafts.list()).length,0);
 guest.lock();await assert.rejects(drafts.save(state),/sign-in needs checking/);
});

test('a failed photo archive never clears the active photo or consumes the Studio entry',async()=>{
 const {context,writes}=await qaStudioEntry();
 context.photoDraftLibrary.save=async()=>{throw Error('Storage full');};
 const notices=[];context.notify=message=>notices.push(message);
 await context.navigate();
 assert.equal(context.state.photo,'old-upload');assert.equal(writes.length,0);
 assert.deepEqual(notices,['Storage full']);assert.equal(context.photoBusy,false);
 assert.equal(context.location.hash,'#choose?source=photo&studio=1');assert.equal(context.opened,0);
});

test('My designs combines automatic and saved drafts in one private collection with escaped labels',()=>{
 const html=myDesignsPage({rows:[{id:'saved-1',updatedAt:12,pass:{model:'Saved model'}}],photoDrafts:[{id:'draft-1',updatedAt:42,snapshot:{photo:'data:image/png;base64,AAAA',model:'<model>'}}],preview:()=>'<div>SAVED PREVIEW</div>',draftPreview:()=>'<div>DRAFT PREVIEW</div>'});
 assert.match(html,/2 designs/);assert.equal((html.match(/class="v35-private-grid"/g)||[]).length,1);assert.equal((html.match(/>Private draft</g)||[]).length,2);assert.doesNotMatch(html,/Photo drafts|Saved designs/);assert.ok(html.indexOf('DRAFT PREVIEW')<html.indexOf('SAVED PREVIEW'));assert.match(html,/data-action="print-photo-draft"/);assert.match(html,/data-action="print-design"/);assert.match(html,/&lt;model&gt;/);
 assert.match(html,/data-action="restore-photo-draft"/);assert.match(html,/data-action="delete-photo-draft"/);
 assert.doesNotMatch(html,/A little inspiration is waiting/);
});

test('restoring a photo draft recovers composition and archives the current photo without restoring order authority',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const saved={source:'photo',photo:'data:image/png;base64,AAAA',model:'iPhone 13 Pro',caseMaterial:'standard',phoneColor:{rgb:'#535451'},photoPlacement:{x:36,y:58,scale:120,rotation:90},photoArtwork:[{id:'caption',text:'Hello'}],artworkLayouts:{},keepCollection:false};
 const old={source:'photo',photo:'data:image/png;base64,BBBB',pass:{code:'old'},job:{id:'order'},editOrderId:'order'};
 const writes=[],archives=[],routes=[];
 const context={isPhoto,structuredClone,state:old,finishInlineText:()=>{},photoDraftLibrary:{save:async state=>archives.push(structuredClone(state))},privateWrite:async(...args)=>writes.push(args),workspace:{check(){}},stockCatalogStatus:'ready',phoneModels:['iPhone 13 Pro'],stockSelection:()=>({templateId:'current-template'}),selectSupplierTemplate:()=>{},syncDraftColor:()=>{},save:()=>{},go:route=>routes.push(route)};
 vm.createContext(context);vm.runInContext(appFunction(source,'restorePhotoDraft'),context);
 await context.restorePhotoDraft(saved);
 assert.equal(archives[0].photo,'data:image/png;base64,BBBB');
 assert.deepEqual(writes,[['draft-photo',saved.photo]]);
 assert.deepEqual(context.state.photoPlacement,saved.photoPlacement);
 assert.deepEqual(context.state.photoArtwork,saved.photoArtwork);
 assert.equal(context.state.pass,null);assert.equal(context.state.job,null);assert.equal(context.state.editOrderId,null);
 assert.equal(context.state.phoneTemplateId,'current-template');assert.equal(context.effectPanelOpen,false);
 assert.deepEqual(routes,['choose']);
 context.state.photoPlacement.x=99;assert.equal(saved.photoPlacement.x,36);
});

test('Print on either private draft card restores it and opens review without creating an order',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 for(const photo of [false,true]){
  const routes=[],restores=[];
  const row={snapshot:{photo:'local-photo'},pass:{code:'saved'}};
  const context={state:{model:'iPhone 13 Pro'},restorePhotoDraft:async(value,options)=>restores.push(['photo',value,options.navigate]),restoreLocalDesign:async(value,options)=>restores.push(['saved',value,options.navigate]),prepareDesignReview:async state=>({...state,code:'checked-preview'}),go:value=>routes.push(value)};
  vm.createContext(context);vm.runInContext(appFunction(source,'reviewSavedDesign'),context);
  await context.reviewSavedDesign(row,photo);
  assert.equal(restores[0][0],photo?'photo':'saved');assert.equal(restores[0][2],false);
  assert.deepEqual(routes,['review']);assert.equal(context.reviewPass.code,'checked-preview');
  context.prepareDesignReview=async()=>{throw Error('Choose your phone model first.');};
  await assert.rejects(context.reviewSavedDesign(row,photo),/Choose your phone model/);
  assert.equal(routes.at(-1),'choose');
 }
});

test('applying camera-aware AI preserves the full image and rejects a changed case configuration',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 for(const change of [{},{model:'Other'},{caseMaterial:'magnetic'},{phoneTemplateId:'replacement'}]){
  const writes=[];
  const context={aiBusy:false,aiUi:{},state:{model:'iPhone 17',caseMaterial:'standard',phoneTemplateId:'original',photo:'previous',...change},
   aiJob:{id:'AI-fixture',mode:'live',model:'iPhone 17',status:'ready',resultPhoto:'generated',composition:{version:1,fit:'blur',case_material:'standard',template_id:'original'}},
   render:()=>{},save:()=>{},go:()=>{},notify:()=>{},canApplyAIOrder:()=>true,generatedPhotoPlacement,
   phoneTemplate:(model,id)=>({id}),refreshLiveRender:async job=>job,
   rememberLiveJob:async job=>{context.aiJob=job;},privateWrite:async(...args)=>writes.push(args)};
  vm.createContext(context);vm.runInContext(appFunction(source,'handleAI').split('let pollBusy=')[0],context);
  await context.handleAI('apply');
  if(Object.keys(change).length){assert.equal(writes.length,0);assert.equal(context.state.photo,'previous');assert.ok(context.aiUi.error);}
  else{assert.equal(writes.length,1);assert.equal(context.state.photo,'generated');assert.equal(context.state.photoPlacement.fit,'blur');assert.equal(context.state.photoPlacement.scale,100);}
 }
});


test('scoped checkout needs fresh stock for the exact scanned device, without requiring coordinates',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const scope={shop_id:'351',device_id:'789'},context={key:'checkout',scope};
 const state={key:'checkout',error:false,busy:false,loadedAt:Date.now(),rows:[{...scope,availability:'available',coordinates:null}]};
 const ready=(changes={},ctx=context)=>vm.runInNewContext(appFunction(source,'pickupCheckoutReady')+';pickupCheckoutReady()', {pickupContext:()=>ctx,stationFinder:{state:{...state,...changes}}});
 assert.equal(ready(),true);
 for(const changes of [{error:true},{busy:true},{loadedAt:Date.now()-61000},{key:'old'},{rows:[]},{rows:[{...scope,availability:'out_of_stock'}]},{rows:[{...scope,device_id:'999',availability:'available'}]},{rows:[{...scope,shop_id:'999',availability:'available'}]}])assert.equal(ready(changes),false);
 assert.equal(ready({}, {key:'checkout'}),true);
});
