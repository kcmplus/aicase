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
