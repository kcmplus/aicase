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
  return {enabled:r.ok&&data.enabled===true,release_enabled:r.ok&&data.release_enabled===true,
   ...(r.ok&&data.simulated===true?{simulated:true}:{})};
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
export function deliveryOptions(selected='pickup',lang='en-US',{pickupDetails='',presentation='default'}={}){
 const zh=lang==='zh-CN';
 if(presentation==='checkout')return `<fieldset class="delivery-options checkout-delivery-options"><legend>${zh?'选择如何收取手机壳':'Choose how to receive your case'}</legend>${['pickup','courier'].map(type=>`<label data-delivery="${type}"><input type="radio" name="fulfillment_type" value="${type}" ${selected===type?'checked':''}><span><span class="delivery-option-icon" aria-hidden="true">${type==='pickup'?'⌖':type==='courier'?'▱':'↗'}</span><strong>${type==='pickup'?(zh?'附近打印':'Nearby printing'):type==='courier'?(zh?'配送到家':'Ship to home'):deliveryLabel(type,lang)}</strong><small>${type==='pickup'?(zh?'查看有库存的网点，到设备前扫码打印。':'View stations with stock. Scan the station when you arrive.'):(zh?'每单固定运费，填写收货信息后付款。':'Fixed shipping per order. Enter your delivery address to continue.')}</small></span></label>`).join('')}${selected==='pickup'?`<div id="pickup-station-panel" class="pickup-option-details">${pickupDetails}</div>`:''}</fieldset>`;
 return `<fieldset class="delivery-options"><legend>${zh?'选择配送方式':'Delivery method'}</legend>${['pickup','courier'].map(type=>`<label><input type="radio" name="fulfillment_type" value="${type}" ${selected===type?'checked':''}><span>${deliveryLabel(type,lang)}${type==='pickup'?`<small>${zh?'点击查看网点并请求定位，到设备前扫码打印。':'Choose to view stations and request your location. Scan the station when you arrive.'}</small>`:`<small>${zh?'每单固定运费，填写收货信息后付款。':'Fixed shipping per order. Enter your delivery address to continue.'}</small>`}</span></label>${type==='pickup'&&selected==='pickup'?`<div id="pickup-station-panel" class="pickup-option-details">${pickupDetails}</div>`:''}`).join('')}</fieldset>`;
}
// Recipient details remain in the private draft until the customer confirms checkout.
export function courierAddressForm(draft,lang='en-US'){
 const zh=lang==='zh-CN',say=(en,cn)=>zh?cn:en,a=draft.deliveryAddress||{};
 const field=(name,label,autocomplete,{type='text',max=150,required=true,min=0}={})=>`<label>${label}<input name="${name}" type="${type}" autocomplete="shipping ${autocomplete}" maxlength="${max}" ${min?`minlength="${min}"`:''} ${required?'required':''} value="${esc(a[name]||'')}"></label>`;
 return `<form id="courier-address-form" class="checkout-address"><h3>${say('Delivery address','收货信息')}</h3><p>${say('Complete the required fields and save your address before payment.','请填写必填信息，保存收货地址后继续付款。')}</p><div class="address-pair">${field('recipient',say('Recipient (required)','收件人（必填）'),'name',{max:60})}${field('phone',say('Phone (required)','联系电话（必填）'),'tel',{type:'tel',max:24,min:6})}</div>${field('region',say('Country / state / city (required)','国家／州／城市（必填）'),'address-level1')}${field('street',say('Street address (required)','详细地址（必填）'),'street-address',{max:250})}${field('postal',say('Postal code (optional)','邮政编码（选填）'),'postal-code',{max:20,required:false})}<button class="button secondary" type="submit">${say('Save address','保存收货地址')}</button><p class="address-status" role="status">${draft.deliveryAddressSaved?say('Address saved.','收货地址已保存。'):''}</p></form>`;
}
export function deliveryStatusPanel(order,{lang='en-US',busy=false}={}){
 const zh=lang==='zh-CN',say=(en,cn)=>zh?cn:en;
 if(isPickup(order)||['cancelled','completed','collected'].includes(order.status)||(order.refund&&order.refund.status!=='failed'))return '';
 if(order.fulfillmentType==='courier'&&order.shippingQuote?.version===1){
  const a=order.deliveryAddress||{},q=order.shippingQuote;
  return `<section class="device-fulfillment"><h3>${say('Ship to home','快递到家')}</h3><p>${say('Delivery is arranged separately. Contact support for delivery updates.','快递将独立安排配送，物流进度请联系客服。')}</p><dl><div><dt>${say('Recipient','收件人')}</dt><dd>${esc(a.recipient)}</dd></div><div><dt>${say('Phone','联系电话')}</dt><dd>${esc(a.phone)}</dd></div><div><dt>${say('Address','收货地址')}</dt><dd>${esc(a.region)}<br>${esc(a.street)} ${esc(a.postal||'')}</dd></div><div><dt>${say('Case price','手机壳价格')}</dt><dd>${esc(q.currency)} ${esc(q.print_amount)}</dd></div><div><dt>${say('Fixed shipping','固定运费')}</dt><dd>${esc(q.currency)} ${esc(q.shipping_amount)}</dd></div></dl></section>`;
 }
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
 if(f?.simulated===true&&f.print_confirmed)return {state:'simulation',phase:cloud?.phase||'queued'};
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
// Keep the reason visible when a station action is unavailable; this is not a
// replacement for server authorization or a reason to retry an uncertain write.
export function stationOrderNotice(order,{lang='en-US'}={}){
 const v=fulfillmentView(order),f=order.fulfillment,zh=lang==='zh-CN';
 if(!f||v.canPrint||v.canRetry||v.releasePending)return '';
 const messages={
  station_cancelled:['This print request was cancelled by the station service. It cannot be printed. Contact staff with your order number.','设备服务已取消此打印请求，无法继续打印。请提供订单号联系工作人员。'],
  unknown:f.print_confirmed||f.release_state==='unknown'
   ?['Your print confirmation is awaiting verification. Contact staff before trying again.','开印确认结果待核实，请联系工作人员，勿重复操作。']
   :['The station has not confirmed whether it received this order. Contact staff with your order number; do not submit it again yet.','设备是否收到此订单尚未核实。请提供订单号联系工作人员，暂勿重复推单。'],
  prepared:['Your design is waiting to be sent to the station. Refresh this order shortly.','设计正在等待发送至设备，请稍后刷新订单。'],
  submitting:['Your design is being sent to the station. Refresh this order shortly; do not submit it again.','设计正在发送至设备，请稍后刷新订单，勿重复推单。'],
  confirming:['Your print confirmation is being checked. Refresh this order shortly; do not confirm again.','正在核实开印确认，请稍后刷新订单，勿重复确认。'],
  released:['Printing has been authorized. Waiting for the station to report progress.','已确认开印，正在等待设备返回进度。'],
  failed:['The station reported a printing or dispensing problem. Contact staff before trying again.','设备报告打印或出货异常，请联系工作人员，勿重复操作。'],
  rejected:['The station did not accept this request. Contact staff before sending it again.','设备未接受此请求，请联系工作人员核实后再发送。'],
  submitted:['This order needs verification before printing. Contact staff with your order number.','此订单需要核实后才能打印，请提供订单号联系工作人员。'],
 };
 const message=messages[v.state];
 return message?`<p class="station-order-notice" role="status">${esc(message[zh?1:0])}</p>`:'';
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
  const catalog=await response.json(),phone=catalog.models?.find(m=>m.name===order.pass.model);
  const style=order.pass.caseMaterial?phone?.styles?.find(s=>s.caseMaterial===order.pass.caseMaterial&&s.available):null;
  const model=order.pass.caseMaterial?(style?.templateId?{...phone,...style}:null):phone;
  if(!model)throw Error('This station has no stock for your phone model and case style.');
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
