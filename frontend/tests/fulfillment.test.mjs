import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareDeviceOrder,fulfillmentView,scanScope,scopeIds,fulfillmentConfig,stationIdentity,isPickup,deliveryLabel,deliveryOptions,deliveryStatusPanel} from '../storefront/fulfillment-service.js';
import {orderRequest} from '../storefront/order-service.js';

const template={id:'supplier-1-'+'a'.repeat(20),model:'iPhone 16 Pro',inventoryItemId:1,
 overlay:'/media/supplier-templates/'+'b'.repeat(64)+'-overlay.png',
 previewOverlay:'/media/supplier-templates/'+'b'.repeat(64)+'-overlay.png',
 mask:'/media/supplier-templates/'+'c'.repeat(64)+'-mask.png',sourceWidth:600,sourceHeight:1200,printWidth:600,printHeight:1200,previewOnly:true,dpi:null};
const order=()=>({id:'order-1',mode:'airwallex_live',fulfillmentType:'pickup',status:'paid',pass:{version:2,source:'collection',designId:'bloom',model:template.model,
 effect:'original',zoom:100,x:50,y:50,intensity:65,phoneTemplateId:template.id}});
test('direct simulation completion is never presented as physical delivery',()=>{
 const value={...order(),mode:'free_test',fulfillment:{simulated:true,print_confirmed:true,cloud_status:{phase:'dispensed',phase_verified:false}}};
 assert.deepEqual(fulfillmentView(value),{state:'simulation',phase:'dispensed'});
 assert.equal(fulfillmentView({...value,refund:{status:'requested'}}).state,'refund');
 assert.notEqual(fulfillmentView({...value,fulfillment:{...value.fulfillment,simulated:false}}).state,'delivered');
});
test('station identity leads with a name and location, escapes supplied text and makes missing location explicit',()=>{
 const html=stationIdentity({name:'Mall <East>',location:'Level 1 <script>alert(1)</script>',device_id:'401',number:'WM-401'},{lang:'zh-CN'});
 assert.ok(html.indexOf('Mall &lt;East&gt;')<html.indexOf('设备编号'));
 assert.ok(html.includes('Level 1 &lt;script&gt;'));
 assert.ok(!html.includes('<script>'));
 assert.ok(html.includes('401'));
 assert.ok(stationIdentity({name:'Mall',device_id:'401'},{lang:'zh-CN'}).includes('位置暂未填写'));
});
test('scan identity accepts only the current storefront QR and never treats it as authorization',()=>{
 assert.deepEqual(scanScope('https://shop.example/?device_id=401&shop_id=146#home','https://shop.example/#payment'),{device_id:'401',shop_id:'146'});
 for(const url of ['https://evil.example/?device_id=401&shop_id=146','https://shop.example/?device_id=401','https://shop.example/?device_id=x&shop_id=146'])assert.throws(()=>scanScope(url,'https://shop.example/'));
 assert.equal(scopeIds('device_id=401'),null);
});
test('only an authoritative paid submitted order can show Print now',()=>{
 const base={...order(),fulfillment:{state:'submitted',can_confirm_print:true,release_available:true}};
 assert.equal(fulfillmentView(base).canPrint,true);
 assert.equal(fulfillmentView({...base,status:'pending'}).canPrint,false);
 assert.equal(fulfillmentView({...base,refund:{status:'pending'}}).state,'refund');
 assert.equal(fulfillmentView({...base,fulfillment:{...base.fulfillment,print_confirmed:true,release_state:'unknown'}}).state,'unknown');
 assert.equal(fulfillmentView({...base,status:'ready'}).state,'delivered');
});
test('binding freezes the server template before rendering and uploading files',async()=>{
 let current=order();const calls=[],renders=[];
 const request=async(path,options)=>{
  calls.push([path,options]);
  if(path.endsWith('/device/'))current={...current,fulfillment:{state:'draft',device_id:'401',shop_id:'146'}};
  if(path.endsWith('/print-files/')){
   assert.ok(options.body instanceof FormData);assert.equal(options.body.get('print_image').type,'image/png');
   current={...current,fulfillment:{...current.fulfillment,state:'prepared'}};
  }
  return current;
 };
 const result=await prepareDeviceOrder(current,'device_id=401&shop_id=146',{save:async x=>x,request,
  fetcher:async()=>({ok:true,json:async()=>({models:[{name:template.model,inventoryItemId:1}],templates:[template]})}),
  render:async(design,model,kind)=>{renders.push(kind);assert.equal(design.phoneTemplateId,template.id);return {blob:new Blob(['png'],{type:'image/png'})};}});
 assert.equal(result.fulfillment.state,'prepared');
 assert.deepEqual(renders,['supplier-print','preview']);
 assert.equal(calls[0][0],'order-1/device/');
 assert.equal(calls[0][1].body.accept_template,true);
});
test('retries reuse prepared files and never move a submitted order to a different device',async()=>{
 const current={...order(),fulfillment:{state:'prepared',device_id:'401',shop_id:'146'}};
 const fail=async()=>{throw Error('must not call')};
 assert.equal(await prepareDeviceOrder(current,'',{request:fail,render:fail}),current);
 await assert.rejects(prepareDeviceOrder(current,'device_id=402&shop_id=146',{request:fail}),/another station/);
 const sandbox={...current,mode:'airwallex_test'};
 assert.equal(await prepareDeviceOrder(sandbox,'device_id=402&shop_id=146',{request:fail}),sandbox);
});
test('file upload sends multipart without overriding its boundary and still uses order key and CSRF',async()=>{
 const calls=[],body=new FormData();body.append('print_image',new Blob(['png'],{type:'image/png'}),'print.png');
 await orderRequest('order-1/print-files/',{method:'POST',body,key:'a'.repeat(64),fetcher:async(url,options)=>{
  calls.push([url,options]);return {ok:true,json:async()=>url.includes('csrf')?{csrfToken:'csrf'}:{state:'prepared'}};
 }});
 assert.equal(calls[1][1].body,body);
 assert.equal(calls[1][1].headers['Content-Type'],undefined);
 assert.equal(calls[1][1].headers['X-CSRFToken'],'csrf');
 assert.equal(calls[1][1].headers['X-Order-Key'],'a'.repeat(64));
});
test('unavailable configuration fails closed',async()=>{
 assert.deepEqual(await fulfillmentConfig(async()=>{throw Error('offline')}),{enabled:false,release_enabled:false});
});
test('courier, air and unclassified orders never bind a device or upload files, even after scanning',async()=>{
 const fail=async()=>{throw Error('must not access device API')};
 for(const fulfillmentType of ['courier','air','unspecified',undefined]){
  const current={...order(),fulfillmentType};
  assert.equal(isPickup(current),false);
  assert.equal(await prepareDeviceOrder(current,'device_id=401&shop_id=146',{request:fail,render:fail,fetcher:fail}),current);
  const view=fulfillmentView({...current,fulfillment:{state:'submitted',can_confirm_print:true,release_available:true}});
  assert.equal(view.canPrint,undefined);
  assert.equal(view.state,['courier','air'].includes(fulfillmentType)?'delivery':'unspecified');
 }
});
test('delivery choices explain availability and do not silently change a saved selection',()=>{
 const html=deliveryOptions('air','zh-CN');
 assert.match(html,/快递配送/);assert.match(html,/空运配送/);assert.match(html,/暂未开放/);
 assert.match(html,/value="air" checked/);assert.doesNotMatch(html,/value="pickup" checked/);
 assert.equal(deliveryLabel('air','zh-CN'),'空运配送');
 assert.equal(deliveryLabel(undefined),'Delivery method not confirmed');
});
test('missing cloud release capability and legacy confirmations do not fabricate a queue',()=>{
 const current={...order(),fulfillment:{state:'submitted',can_confirm_print:true,release_available:false}};
 assert.equal(fulfillmentView(current).canPrint,false);
 assert.equal(fulfillmentView(current).releasePending,true);
 assert.equal(fulfillmentView({...current,fulfillment:{...current.fulfillment,print_confirmed:true,release_state:'submitted'}}).state,'confirming');
 assert.equal(fulfillmentView({...current,status:'printing',fulfillment:{...current.fulfillment,print_confirmed:true,release_state:'unknown'}}).state,'unknown');
});
test('cloud payment proof is separate from mapped print and shipment progress',()=>{
 const current={...order(),fulfillment:{state:'submitted',print_confirmed:true,release_state:'observed',
  cloud_status:{payment_recorded:true,phase:'unknown'}}};
 assert.equal(fulfillmentView(current).state,'released');
 assert.equal(fulfillmentView({...current,fulfillment:{...current.fulfillment,cloud_status:{payment_recorded:true,phase:'printing',phase_verified:true}}}).state,'printing');
 assert.equal(fulfillmentView({...current,fulfillment:{...current.fulfillment,cloud_status:{payment_recorded:true,phase:'dispensed',phase_verified:true}}}).state,'delivered');
 assert.equal(fulfillmentView({...current,fulfillment:{...current.fulfillment,cloud_status:{payment_recorded:true,phase:'print_failed',phase_verified:true}}}).state,'failed');
 assert.equal(fulfillmentView({...current,fulfillment:{...current.fulfillment,release_state:'unknown'}}).state,'unknown');
 assert.equal(fulfillmentView({...current,fulfillment:{...current.fulfillment,cloud_status:{payment_recorded:true,phase:'dispensed',phase_verified:false}}}).state,'released');
 assert.equal(fulfillmentView({...current,fulfillment:{...current.fulfillment,cloud_status:{status:4,phase:'cancelled',phase_verified:true}}}).state,'station_cancelled');
});

test('refunded and closed orders do not ask customers to choose delivery',()=>{
 for(const fulfillmentType of ['unspecified','pickup','courier','air']){
  for(const status of ['pending','submitted','succeeded','unknown']){
   assert.equal(deliveryStatusPanel({...order(),fulfillmentType,refund:{status}}),'');
  }
  for(const status of ['cancelled','completed','collected']){
   assert.equal(deliveryStatusPanel({...order(),fulfillmentType,status}),'');
  }
 }
 assert.equal(deliveryStatusPanel(order()),'');
 assert.match(deliveryStatusPanel({...order(),fulfillmentType:'unspecified'}),/data-action="confirm-pickup"/);
 assert.match(deliveryStatusPanel({...order(),fulfillmentType:'unspecified',refund:{status:'failed'}}),/data-action="confirm-pickup"/);
 assert.match(deliveryStatusPanel({...order(),fulfillmentType:'courier'}),/separate delivery process/);
});


import {stationEntry} from '../storefront/station-entry.js';
const scannedEntry={scope:'device_id=401&shop_id=146',hash:'',station:{device_id:'401',shop_id:'146'}};
const soleRef='33333333-3333-4333-8333-333333333333';
test('QR entry reads only the owner order list and routes zero, one or multiple orders',async()=>{
 for(const hash of ['', '#home']){
  for(const count of [0,1,2]){
   const data={results:Array.from({length:count},()=>({reference:soleRef})),has_more:false,page:1};
   const calls=[];
   const entry=await stationEntry({...scannedEntry,hash,request:async(...args)=>{calls.push(args);return data;}});
   assert.deepEqual(calls,[['?page=1']]);
   assert.equal(entry.reference,count===1?soleRef:undefined);
   assert.equal(entry.route,count===0?'choose?source=photo':count===2?'orders':undefined);
  }
 }
});
test('QR entry never intercepts checkout, payment returns, explicit lists or later editing',async()=>{
 const fail=async()=>{throw Error('must not read or write');};
 for(const hash of ['#orders','#choose','#checkout','#payment?order='+soleRef+'&result=success','#pass','#account']){
  assert.equal(await stationEntry({...scannedEntry,hash,request:fail}),null);
 }
 for(const scope of ['', 'device_id=401', 'device_id=bad&shop_id=146']){
  assert.equal(await stationEntry({...scannedEntry,scope,request:fail}),null);
 }
 for(const station of [null,{device_id:'402',shop_id:'146'},{device_id:'401',shop_id:'147'}]){
  assert.deepEqual(await stationEntry({...scannedEntry,station,request:fail}),{route:'orders'});
 }
});
test('QR entry does not mistake partial pages or failures for a single order or new customer',async()=>{
 const partial={results:[{reference:soleRef}],has_more:true,page:1};
 assert.equal((await stationEntry({...scannedEntry,request:async()=>partial})).route,'orders');
 const error=await stationEntry({...scannedEntry,request:async()=>{throw Error('Unavailable');}});
 assert.equal(error.route,'orders');assert.equal(error.error,'Unavailable');
 for(const data of [{},{results:[]},{results:[],has_more:false,page:2},{results:[{reference:'bad'}],has_more:false,page:1}]){
  const result=await stationEntry({...scannedEntry,request:async()=>data});
  assert.equal(result.route,'orders');assert.ok(result.error);
 }
});


import {stationScanPrompt,previewStationPanel,stationScanDestination,acquireStationCamera} from '../storefront/station-scanner.js';
import decodeQR from '../storefront/vendor/jsqr.js';
import {create as encodeQR} from '../storefront/vendor/qr.js';
test('phone orders use scan actions instead of displaying a design QR',()=>{
 const plain=previewStationPanel({mode:'demo',status:'paid'},{lang:'zh-CN'});
 assert.match(plain,/扫描设备二维码/);assert.match(plain,/没有实际收款/);assert.doesNotMatch(plain,/<img|download=|confirm-device-print|send-device-order/);
 const scoped=previewStationPanel({mode:'demo',status:'paid'},{scope:'device_id=401&shop_id=146',station:{device_id:'401',shop_id:'146',name:'Test station'},lang:'en-US'});
 assert.match(scoped,/Test station/);assert.doesNotMatch(scoped,/data-action="scan-station"|<img|confirm-device-print|send-device-order/);
 for(const fulfillmentType of ['courier','air'])assert.equal(previewStationPanel({...order(),fulfillmentType}), '');
 assert.equal(previewStationPanel({...order(),refund:{status:'succeeded'}}),'');
 assert.match(stationScanPrompt('zh-CN'),/机器屏幕|打印机.*屏幕/);
});
test('scanning preserves the current order and rejects unrelated codes and destinations',()=>{
 const current='https://shop.example/?lang=zh-CN#payment?order='+soleRef;
 const target=stationScanDestination('https://shop.example/?device_id=401&shop_id=146#home',current);
 assert.equal(new URL(target).hash,new URL(current).hash);
 assert.equal(new URL(target).searchParams.get('lang'),'zh-CN');
 assert.equal(new URL(target).searchParams.get('device_id'),'401');
 for(const bad of ['POP-1117','https://evil.example/?device_id=401&shop_id=146','https://shop.example/?device_id=401','javascript:alert(1)'])assert.throws(()=>stationScanDestination(bad,current));
});
test('a camera grant after the scan dialog closes immediately stops its tracks',async()=>{
 let stopped=0,options;
 const stream={getTracks:()=>[{stop:()=>stopped++}]};
 assert.equal(await acquireStationCamera({getUserMedia:async value=>{options=value;return stream;}},()=>true),null);
 assert.equal(stopped,1);assert.equal(options.audio,false);assert.equal(options.video.facingMode.ideal,'environment');
 assert.equal(await acquireStationCamera({getUserMedia:async()=>stream},()=>false),stream);
 assert.equal(stopped,1);
 await assert.rejects(acquireStationCamera({getUserMedia:async()=>{throw Error('permission denied');}},()=>false));
});
test('the bundled decoder reads a device QR without any remote service',()=>{
 const value='https://shop.example/?device_id=401&shop_id=146',matrix=encodeQR(value,{errorCorrectionLevel:'M'}).modules;
 const scale=6,width=(matrix.size+8)*scale,pixels=new Uint8ClampedArray(width*width*4).fill(255);
 for(let y=0;y<matrix.size;y++)for(let x=0;x<matrix.size;x++)if(matrix.get(y,x)){
  for(let dy=0;dy<scale;dy++)for(let dx=0;dx<scale;dx++){
   const offset=(((y+4)*scale+dy)*width+(x+4)*scale+dx)*4;
   pixels[offset]=pixels[offset+1]=pixels[offset+2]=0;
  }
 }
 assert.equal(decodeQR(pixels,width,width).data,value);
});

test('no-charge test orders retain dispatch states but cannot fabricate zero-payment release',()=>{
 const current={...order(),mode:'free_test',priceCents:0,fulfillment:{state:'submitted',release_available:false,can_confirm_print:false,zero_release_unconfirmed:true}};
 assert.equal(fulfillmentView(current).state,'submitted');
 assert.equal(fulfillmentView(current).canPrint,false);assert.equal(fulfillmentView(current).releasePending,true);
});

test('rejected dispatch preserves the order and requires an explicit attempt-bound retry',async()=>{
 const current={...order(),fulfillment:{state:'rejected',device_id:'401',shop_id:'146',can_retry_dispatch:true,submitted_at:'2026-11-06T10:00:00Z'}};
 assert.equal(fulfillmentView(current).canRetry,true);
 const calls=[];
 const result=await prepareDeviceOrder(current,'device_id=401&shop_id=146',{save:async x=>x,render:()=>assert.fail('must reuse frozen files'),request:async(path,options)=>{calls.push([path,options]);return {...current,fulfillment:{...current.fulfillment,state:'prepared'}};}});
 assert.equal(result.fulfillment.state,'prepared');
 assert.deepEqual(calls[0],['order-1/retry-dispatch/',{method:'POST',body:{confirm:true,submitted_at:'2026-11-06T10:00:00Z'}}]);
 const uncertain={...current,fulfillment:{...current.fulfillment,state:'unknown',can_retry_dispatch:false}};
 assert.equal(fulfillmentView(uncertain).canRetry,false);
 assert.equal(await prepareDeviceOrder(uncertain,'device_id=401&shop_id=146',{request:()=>assert.fail('unknown is never replayed')}),uncertain);
});


test('zero-price print controls follow server authorization and show observed release once',()=>{
 const current={...order(),mode:'free_test',priceCents:0,fulfillment:{state:'submitted',release_available:true,can_confirm_print:true}};
 assert.equal(fulfillmentView(current).canPrint,true);
 current.fulfillment={...current.fulfillment,print_confirmed:true,release_state:'observed',cloud_status:{payment_recorded:true,pay_money:'0.00',pay_status:1}};
 assert.equal(fulfillmentView(current).state,'released');
 assert.equal(fulfillmentView(current).canPrint,undefined);
});


test('pickup station information sits directly after its choice and before courier options',()=>{
 const html=deliveryOptions('pickup','zh-CN',{pickupDetails:'<section>Matching stations</section>'});
 assert.ok(html.indexOf('value="pickup"')<html.indexOf('Matching stations'));
 assert.ok(html.indexOf('Matching stations')<html.indexOf('value="courier"'));
 assert.ok(html.includes('</label><div id="pickup-station-panel"'));
 assert.ok(html.includes('请求定位'));
 for(const method of ['courier','air'])assert.ok(!deliveryOptions(method,'zh-CN',{pickupDetails:'Matching stations'}).includes('Matching stations'));
});

test('prototype delivery cards retain pickup, courier and air values without promising shipping availability',()=>{
 for(const selected of ['pickup','courier','air']){
  const html=deliveryOptions(selected,'en-US',{presentation:'checkout',pickupDetails:'Existing stock-aware station finder'});
  assert.match(html,new RegExp(`value="${selected}" checked`));
  assert.match(html,/Nearby printing/);assert.match(html,/Ship to home/);assert.match(html,/Air delivery/);
  assert.match(html,/Coming soon\. No payment is taken\./);
  assert.equal(html.includes('Existing stock-aware station finder'),selected==='pickup');
  assert.doesNotMatch(html,/US\$4|3–4 days|reservation|pay-provider/);
 }
});
