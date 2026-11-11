import {orderRequest} from './order-service.js';
import {makePersonalDesign} from './simple-personalize.js';
import {registerSupplierTemplates} from './phone-templates.js';
import {exportCase} from './print-export.js';
import {esc} from './art.js';
import {stationNavigation} from './station-navigation.js';

export function stationIdentity(device,{lang='en-US',navigation=true}={}){
 const text=value=>typeof value==='string'?value.trim():'';
 const zh=lang==='zh-CN',name=text(device?.name)||(zh?'打印设备':'Print station');
 const location=text(device?.location)||(zh?'位置暂未填写，请核对现场设备。':'Location not provided. Check the station on site.');
 const number=text(device?.number),id=device?.device_id;
 return `<div class="station-identity"><strong class="station-identity-name">${esc(name)}</strong><p class="station-identity-location">${esc(location)}</p><small>${zh?'设备编号':'Device ID'}：${esc(id||'—')}${number&&number!==id?` · ${esc(number)}`:''}</small>${navigation?stationNavigation(device,{lang}):''}</div>`;
}

export async function fulfillmentConfig(fetcher=fetch){
 try{
  const r=await fetcher('/api/v1/store/fulfillment-config/',{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(10000)});
  const data=await r.json();
  return {enabled:r.ok&&data.enabled===true,release_enabled:r.ok&&data.release_enabled===true};
 }catch{return {enabled:false,release_enabled:false};}
}
export function scanScope(value,base){
 const url=new URL(value,base),origin=new URL(base);
 if(url.origin!==origin.origin||url.pathname!==origin.pathname||url.username||url.password)throw Error('Scan this station’s POPOMO QR code.');
 const data={device_id:url.searchParams.get('device_id'),shop_id:url.searchParams.get('shop_id')};
 if(!Object.values(data).every(v=>/^\d{1,40}$/.test(v||'')))throw Error('Scan this station’s POPOMO QR code.');
 return data;
}
export function scopeIds(scope){
 const params=new URLSearchParams(scope),device_id=params.get('device_id'),shop_id=params.get('shop_id');
 return /^\d{1,40}$/.test(device_id||'')&&/^\d{1,40}$/.test(shop_id||'')?{device_id,shop_id}:null;
}
export function isPickup(order){return order?.fulfillmentType==='pickup';}
export function deliveryLabel(type,lang='en-US'){
 const labels={pickup:['On-site pickup','到网点自取'],courier:['Courier delivery','快递配送'],air:['Air delivery','空运配送'],unspecified:['Delivery method not confirmed','配送方式待确认']};
 return (labels[type]||labels.unspecified)[lang==='zh-CN'?1:0];
}
export function deliveryOptions(selected='pickup',lang='en-US',{pickupDetails=''}={}){
 const zh=lang==='zh-CN';
 return `<fieldset class="delivery-options"><legend>${zh?'选择配送方式':'Delivery method'}</legend>${['pickup','courier','air'].map(type=>`<label><input type="radio" name="fulfillment_type" value="${type}" ${selected===type?'checked':''}><span>${deliveryLabel(type,lang)}${type==='pickup'?`<small>${zh?'点击查看网点并请求定位，到设备前扫码打印。':'Choose to view stations and request your location. Scan the station when you arrive.'}</small>`:`<small>${zh?'暂未开放，下单前不会收款':'Coming soon. Checkout is not available yet.'}</small>`}</span></label>${type==='pickup'&&selected==='pickup'?`<div id="pickup-station-panel" class="pickup-option-details">${pickupDetails}</div>`:''}`).join('')}</fieldset>`;
}
export function deliveryStatusPanel(order,{lang='en-US',busy=false}={}){
 const zh=lang==='zh-CN',say=(en,cn)=>zh?cn:en;
 if(isPickup(order)||['cancelled','completed','collected'].includes(order.status)||(order.refund&&order.refund.status!=='failed'))return '';
 if(['courier','air'].includes(order.fulfillmentType))return `<section class="device-fulfillment"><h3>${deliveryLabel(order.fulfillmentType,lang)}</h3><p>${say('This order follows a separate delivery process. Contact support for its fulfillment status.','此订单走独立配送流程，请联系客服确认履约进度。')}</p></section>`;
 if(!['pending','paid'].includes(order.status))return '';
 return `<section class="device-fulfillment"><h3>${deliveryLabel('unspecified',lang)}</h3><p>${order.fulfillment?say('This existing order needs staff review. No new print command will be sent.','此历史订单需要工作人员核对，不会重新下发打印指令。'):say('Confirm how you will receive this order before payment or printing.','付款或打印前，请先确认这笔订单的配送方式。')}</p>${!order.fulfillment&&['pending','paid'].includes(order.status)&&(!order.refund||order.refund.status==='failed')?`<button class="button secondary full" data-action="confirm-pickup" ${busy?'disabled':''}>${say('Confirm on-site pickup','确认设备现场自取')}</button>`:''}</section>`;
}
export function fulfillmentView(order){
 const f=order.fulfillment;
 if(order.refund&&order.refund.status!=='failed')return {state:'refund'};
 if(!isPickup(order))return {state:['courier','air'].includes(order.fulfillmentType)?'delivery':'unspecified'};
 if(!/_(live)$/.test(order.mode)&&order.mode!=='free_test')return {state:'test'};
 if(order.status==='ready')return {state:'delivered'};
 const cloud=f?.cloud_status;
 if(cloud?.phase==='cancelled'||cloud?.status===4)return {state:'station_cancelled'};
 if(Number(cloud?.pay_money)>0&&cloud?.payment_recorded!==true)return {state:'unknown'};
 if(cloud?.phase_verified&&['print_failed','delivery_failed'].includes(cloud?.phase))return {state:'failed'};
 if(f?.release_state==='unknown')return {state:'unknown'};
 if(cloud?.payment_recorded===true){
  if(cloud.phase_verified&&cloud.phase==='dispensed')return {state:'delivered'};
  if(cloud.phase_verified&&['printing','printed','delivering'].includes(cloud.phase))return {state:'printing'};
  return {state:'released'};
 }
 if(f?.print_confirmed)return {state:['claimed','submitted'].includes(f.release_state)?'confirming':'unknown'};
 if(order.status==='printing')return {state:'printing'};
 if(order.status!=='paid'&&order.status!=='pending')return {state:'closed'};
 if(!f)return {state:'unbound'};
 return {state:f.state,canRetry:f.state==='rejected'&&order.status==='paid'&&f.can_retry_dispatch===true,canPrint:order.status==='paid'&&f.can_confirm_print===true&&f.release_available===true,
  releasePending:f.state==='submitted'&&f.release_available!==true};
}
export async function prepareDeviceOrder(order,scope,{save,request=orderRequest,render=exportCase,fetcher=fetch}={}){
 if(!isPickup(order)||(!/^(stripe|airwallex)_live$/.test(order.mode)&&order.mode!=='free_test'))return order;
 const ids=scopeIds(scope)||order.fulfillment&&{device_id:order.fulfillment.device_id,shop_id:order.fulfillment.shop_id};
 if(!ids)return order;
 if(order.fulfillment&&(order.fulfillment.device_id!==ids.device_id||order.fulfillment.shop_id!==ids.shop_id))throw Error('This order has already been sent to another station.');
 let current=order;
 if(current.fulfillment?.state==='rejected'){
  if(!current.fulfillment.can_retry_dispatch)throw Error('The previous submission must be checked before sending again.');
  await request(order.id+'/retry-dispatch/',{method:'POST',body:{confirm:true,submitted_at:current.fulfillment.submitted_at}});
  return save(await request(order.id+'/'));
 }
 if(!current.fulfillment){
  const response=await fetcher('/api/v1/store/phone-models/?'+new URLSearchParams(ids),{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw Error('This station’s phone models could not be loaded.');
  const catalog=await response.json(),model=catalog.models?.find(m=>m.name===order.pass.model);
  if(!model)throw Error('This station has no stock for your phone model.');
  registerSupplierTemplates(catalog.templates);
  await request(order.id+'/device/',{method:'POST',body:{...ids,inventory_item_id:model.inventoryItemId,accept_template:true}});
  current=await save(await request(order.id+'/'));
 }
 if(current.fulfillment?.state==='draft'){
  const design=makePersonalDesign(current.pass);
  const final=await render(design,current.pass.model,'supplier-print');
  const preview=await render(design,current.pass.model,'preview');
  const files=new FormData();files.append('print_image',final.blob,'print.png');files.append('preview_image',preview.blob,'preview.png');
  await request(order.id+'/print-files/',{method:'POST',body:files});
  current=await save(await request(order.id+'/'));
 }
 return current;
}
