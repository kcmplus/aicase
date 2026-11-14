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
import {makePersonalDesign} from '../storefront/simple-personalize.js';
import {validatePhoneColor,validPhoneColors,reconcilePhoneColor,colorPicker} from '../storefront/phone-colors.js';
import {phone} from '../storefront/art.js';
import {exportCase} from '../storefront/print-export.js';
import {orderRequest,savedOrder} from '../storefront/order-service.js';
import {applyStockCatalog,stockSelection} from '../storefront/stock-catalog.js';
import {customerPage} from '../storefront/customer-account.js';

test('V35 home prioritizes the real album handler and preserves gallery and AI editor destinations',()=>{
 const html=homePresentation({gallery:'<section id="designs">CATALOG</section>'});
 assert.ok(html.indexOf('data-action="home-photo"')<html.indexOf('href="#designs"'));
 assert.match(html,/id="photo-file" data-home-upload type="file" accept="image\/jpeg,image\/png,image\/webp"/);
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
  for(const hash of ['home','designs','how-it-works','choose?source=photo','orders','pass','account'])assert.ok(header.includes(`href="#${hash}"`),hash);
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
 assert.match(html,/扫描设备屏上的二维码/);
 assert.match(html,/已出货不等于已取件/);
 assert.match(html,/快递／空运暂未开放结算/);
 assert.doesNotMatch(html,/保存.{0,4}二维码|Keep your code|save the QR code|Show your code/);
 assert.match(shellInfo('station','en-US')[1],/Nearby search is not available/);
 assert.match(shellInfo('ai','zh-CN')[1],/服务端确认/);
});
test('all V35 presentation assets are local and available; editor entry retains the existing service module',async()=>{
 const html=homePresentation(),css=await readFile(new URL('../storefront/v35-shell.css',import.meta.url),'utf8');
 for(const path of new Set([...html.matchAll(/(?:src)="\.\/([^"?]+)"/g),...css.matchAll(/url\('\.\/([^']+)'\)/g)].map(match=>match[1])))await access(new URL('../storefront/'+path,import.meta.url));
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
 assert.match(html,/No matching designs/);assert.match(html,/value="&lt;unmatched&gt;&quot;"/);assert.doesNotMatch(html,/value="<unmatched>/);
 for(const lang of ['en-US','zh-CN']){
  const all=worksPage({works:designs,preview,lang});
  for(const work of designs)assert.match(all,new RegExp(`href="#work\\?id=${work.id}"`));
  assert.match(all,/id="v35-work-search"/);assert.match(all,/role="status"/);
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
 const context={stationContext:()=>'',orderError:'',orderRows:[{status:'paid',mode:'free_test',model_name:'Synthetic model',fulfillment_type:'pickup',reference:'SYNTHETIC-1',created_at:'2026-01-01T00:00:00Z',currency:'USD',amount:0}],esc:String,paymentLabel:()=>'',deliveryLabel:()=>'',locale:()=> 'en-US',orderPage:1,orderHasMore:false};
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
  const html=vm.runInNewContext(`${status}\n${page}\nordersPage()`,{stationContext:()=>'',orderError:'',orderRows:[order],esc:String,paymentLabel:()=>'',deliveryLabel:()=>'',locale:()=> 'en-US',orderPage:1,orderHasMore:false});
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
 const names=['orderStatus','isProviderOrder','providerName','paymentLabel','passPage','providerOrderPage','paymentPage'];
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
   const context={state:{pass},orderBook:{},orderForCode:()=>order,locale:()=> 'en-US',esc,
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
    if(status!=='pending'||refund)assert.doesNotMatch(html,/data-action="pay-provider"/);
    if(status==='pending'){
     assert.match(html,/Confirming your payment/);
     assert.doesNotMatch(html,/data-action="pay-provider"|Payment received/);
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
  assert.match(preview,/<dialog .*aria-labelledby="v35-review-title"/);assert.match(preview,/data-action="save-local-design" disabled/);assert.match(preview,/data-action="continue-design-checkout" disabled/);assert.match(preview,/data-action="close-design-review"/);
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
  state:{...pass,editOrderId:null},phoneModels:[pass.model],refreshStockChoices:async()=>{},stockSelection:()=>({templateId:pass.phoneTemplateId}),createPersonalPass,layoutSelection:value=>value,workspace,library,
  phoneTemplate,orderBook:{orders:{}},checkoutDraft:null,PRINT_AVAILABLE:true,privateWrite:async(name,value)=>{writes.push({name,value});await workspace.write(name,value);},crypto,
  location:{hash:'#choose'},render:()=>{},notify:message=>notices.push(message),go:route=>routes.push(route),locale:()=> 'en-US'};
 const submitStart=source.indexOf("app.addEventListener('submit',async event=>{");
 const clickStart=source.indexOf("app.addEventListener('click',async event=>{",submitStart);
 const clickEnd=source.indexOf("  if(el.dataset.lookAction==='open')",clickStart);
 vm.createContext(context);vm.runInContext(appFunction(source,'assertCurrentColor')+'\n'+source.slice(submitStart,clickStart)+source.slice(clickStart,clickEnd)+'});',context);
 await submit({target:{id:'design-form'},preventDefault(){}});
 assert.ok(context.reviewPass);assert.deepEqual(context.reviewPass.photoPlacement,pass.photoPlacement);assert.equal(context.checkoutDraft,null);assert.equal(writes.length,0);assert.equal(routes.length,0);
 const button=action=>({preventDefault(){},target:{closest:()=>({dataset:{action},disabled:false})}});
 await click(button('save-local-design'));assert.equal((await library.list()).length,1);assert.equal(writes.length,0);assert.equal(routes.length,0);assert.equal(notices.length,1);
 await click(button('continue-design-checkout'));assert.equal(writes.length,1);assert.equal(writes[0].name,'checkout-draft');assert.deepEqual(writes[0].value.pass.photoPlacement,pass.photoPlacement);assert.equal(routes.at(-1),'checkout');assert.equal(context.reviewPass,null);
});
test('actual restore handler retains rotations, text, crop and original bytes while clearing order authority',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),pass=syntheticPass(),before=JSON.stringify(pass),writes=[],routes=[];
 const context={readPass,phoneModels:[pass.model],privateWrite:async(name,value)=>writes.push([name,value]),workspace:{check(){}},finishInlineText:()=>{},state:{pass:{paid:true},job:{status:'printing'},editOrderId:'OLD'},structuredClone,
  stockSelection:()=>null,reconcilePhoneColor,colorNotice:false,aiJob:{id:'OLD'},selectedArtwork:'OLD',comparing:true,reviewPass:{},save:()=>{},go:route=>routes.push(route),notify:()=>{},pass};
 await vm.runInNewContext(appFunction(source,'syncDraftColor')+'\n'+appFunction(source,'restoreLocalDesign')+'\nrestoreLocalDesign(pass)',context);
 assert.equal(context.state.pass,null);assert.equal(context.state.job,null);assert.equal(context.state.editOrderId,null);assert.equal(context.aiJob,null);
 assert.equal(context.state.photo,pass.photo);assert.deepEqual(context.state.photoPlacement,pass.photoPlacement);assert.deepEqual(context.state.photoArtwork,pass.addedArtwork);
 assert.equal(context.state.artworkLayouts.bloom.zoom,113);assert.equal(context.state.zoom,127);assert.equal(writes[0][0],'draft-photo');assert.equal(writes[0][1],pass.photo);assert.equal(routes.at(-1),'choose');assert.equal(JSON.stringify(pass),before);
});
test('the actual library loader keeps bundled templates valid instead of treating them as supplier uploads',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage),library=createDesignLibrary(workspace,{validate:validateLocal});
 const pass=syntheticPass();await library.save(pass,phoneTemplate(pass.model,pass.phoneTemplateId));let registrations=0;
 const context={privateRead:key=>workspace.read(key),library,localDesigns:[],localDesignError:'',localDesignBusy:false,registerSupplierTemplates(){registrations++;throw Error('Invalid supplier template');}};
 await vm.runInNewContext(appFunction(source,'loadLocalDesigns')+'\nloadLocalDesigns()',context);
 assert.equal(registrations,0);assert.equal(context.localDesigns.length,1);assert.equal(context.localDesignError,'');assert.equal(context.localDesignBusy,false);
});
test('actual identity merge clears private memory on a changed session before reload and rejects late AI results',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage);
 await workspace.write('draft-photo','synthetic-private-photo');let reloads=0;
 const context={workspace,designOwner,freshMembership:()=>({jobs:{}}),freshOrders:()=>({orders:{}}),privateUpdate:(...args)=>workspace.update(...args),save:()=>{},state:{photo:'synthetic-private-photo',pass:{code:'private'},artworkLayouts:{secret:{}},photoArtwork:[{}]},membership:customerIdentity(8),aiJob:{customerId:8,remoteId:'private'},checkoutDraft:{},reviewPass:{},localDesigns:[{}],orderRows:[{}],paymentOrder:{},customerUI:{ledger:[{}]},location:{reload(){reloads++;}},data:customerIdentity(9)};
 vm.createContext(context);vm.runInContext(appFunction(source,'lockPrivateWorkspace')+'\n'+appFunction(source,'mergeAIAccount')+'\n'+appFunction(source,'rememberLiveJob'),context);
 await assert.rejects(vm.runInContext('mergeAIAccount(data)',context),/sign-in changed/);
 assert.equal(reloads,1);assert.equal(workspace.active,false);assert.equal(context.state.photo,'');assert.equal(context.state.pass,null);assert.equal(context.aiJob,null);assert.equal(context.checkoutDraft,null);assert.equal(context.localDesigns.length,0);assert.equal(context.customerUI.ledger.length,0);
 assert.equal(storage.rows.get('v35:customer-8:draft-photo'),'synthetic-private-photo');assert.equal(storage.rows.has('v35:customer-9:draft-photo'),false);
 await assert.rejects(vm.runInContext("rememberLiveJob({id:'late-private-result',status:'ready',customerId:8})",context),/sign-in needs checking/);assert.equal(context.aiJob,null);
});

test('actual sign-out failure still clears the private view, and rejected verification codes never sign in',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 for(const action of ['logout','verify']){
  const storage=memoryDesignStorage(),workspace=createDesignWorkspace(customerIdentity(8),storage);let verificationCalls=0,syncCalls=0,navigations=0;
  const context={workspace,customerUI:{busy:false,email:'synthetic@example.test',ledger:[{}],codeSent:false},state:{photo:'synthetic-private'},membership:customerIdentity(8),aiJob:{},localDesigns:[{}],orderRows:[],reviewPass:{},paymentOrder:{},checkoutDraft:{},freshOrders:()=>({orders:{}}),freshMembership:()=>({jobs:{}}),
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
 const context={state:{model:'new-model',phoneColor:old},stockSelection:()=>({colors:[fresh]}),reconcilePhoneColor,colorNotice:false};
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

test('actual color click selects only a current model option, updates preview and restores button focus',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8');
 const start=source.indexOf("app.addEventListener('click',async event=>{"),end=source.indexOf('  if(el.dataset.quickFont)',start);
 const one=previewColor(),two=previewColor(undefined,'other',2);let handler,saves=0,previews=0,focuses=0;
 const picker={innerHTML:'',querySelector:()=>({focus(){focuses++;}})};
 const context={app:{addEventListener:(name,fn)=>{handler=fn;}},sessionCheckBusy:false,photoBusy:false,aiBusy:false,passBusy:false,
  state:{model:'synthetic',phoneColor:one},stockSelection:()=>({colors:[one,two]}),reviewPass:{},colorNotice:true,
  save:()=>{saves++;},updatePreview:()=>{previews++;},document:{querySelector:()=>picker},colorPicker,structuredClone,locale:()=> 'en-US'};
 vm.runInNewContext(source.slice(start,end)+'});',context);
 const click=code=>handler({target:{closest:selector=>{assert.ok(selector.includes('[data-phone-color]'));return {dataset:{phoneColor:code}};}}});
 await click('other');assert.equal(context.state.phoneColor.code,'other');assert.equal(context.reviewPass,null);assert.equal(context.colorNotice,false);
 assert.match(picker.innerHTML,/data-phone-color="other" aria-pressed="true"/);assert.equal(saves,1);assert.equal(previews,1);assert.equal(focuses,1);
 await click('foreign-model-color');assert.equal(saves,1);assert.equal(context.state.phoneColor.code,'other');
});

test('actual local restore clears unavailable color while retaining composition and the immutable saved record',async()=>{
 const source=await readFile(new URL('../storefront/simple-app.js',import.meta.url),'utf8'),template=phoneTemplates[0],color=previewColor(template);
 const pass=createPersonalPass({source:'collection',designId:'bloom',model:template.model,phoneTemplateId:template.id,phoneColor:color,effect:'original',intensity:0,zoom:113,x:42,y:61});
 const before=JSON.stringify(pass),context={pass,readPass,phoneModels:[pass.model],privateWrite:async()=>{},workspace:{check(){}},finishInlineText:()=>{},state:{},structuredClone,
  stockSelection:()=>({templateId:template.id,colors:[]}),reconcilePhoneColor,colorNotice:false,save:()=>{},go:()=>{},notify:()=>{}};
 await vm.runInNewContext(appFunction(source,'syncDraftColor')+'\n'+appFunction(source,'restoreLocalDesign')+'\nrestoreLocalDesign(pass)',context);
 assert.equal(context.state.phoneColor,null);assert.equal(context.colorNotice,true);assert.equal(context.state.artworkLayouts.bloom.zoom,113);assert.equal(context.state.artworkLayouts.bloom.x,42);
 assert.equal(JSON.stringify(pass),before);
});
