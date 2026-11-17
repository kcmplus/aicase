import {esc} from './art.js';
import {validCoordinates,stationNavigation} from './station-navigation.js';
import {orderRequest} from './order-service.js';

export function distanceKm(position,coordinates){
 if(!position||!Number.isFinite(position.latitude)||!Number.isFinite(position.longitude)||Math.abs(position.latitude)>90||Math.abs(position.longitude)>180||!validCoordinates(coordinates)||coordinates.coordinate_type!=='WGS84')return null;
 const rad=value=>value*Math.PI/180,a=rad(position.latitude),b=rad(Number(coordinates.latitude));
 const h=Math.sin((b-a)/2)**2+Math.cos(a)*Math.cos(b)*Math.sin(rad(Number(coordinates.longitude)-position.longitude)/2)**2;
 return 6371.0088*2*Math.asin(Math.sqrt(Math.min(1,Math.max(0,h))));
}
export function locateUser(geolocation=globalThis.navigator?.geolocation){
 return new Promise((resolve,reject)=>{
  if(!geolocation){reject(Error('unsupported'));return;}
  geolocation.getCurrentPosition(result=>{
   const {latitude,longitude,accuracy}=result.coords;
   if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180){reject(Error('unavailable'));return;}
   resolve({latitude,longitude,accuracy,acquiredAt:Date.now()});
  },error=>reject(Error(({1:'denied',2:'unavailable',3:'timeout'})[error.code]||'unavailable')),{enableHighAccuracy:false,timeout:12000,maximumAge:60000});
 });
}
export async function loadPrintStations(context,page=1,{request=orderRequest,fetcher=fetch}={}){
 const params=new URLSearchParams({page:String(page)});
 // User location stays in memory in the browser, never in URLs or order data.
 let data;
 if(context.orderId)data=await request(context.orderId+'/stations/?'+params);
 else{
  params.set('model',context.model);
  if(context.caseMaterial)params.set('case_material',context.caseMaterial);
  if(context.scope)for(const [key,value] of Object.entries(context.scope))params.set(key,value);
  const response=await fetcher('/api/v1/store/print-stations/?'+params,{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error('unavailable');data=await response.json();
 }
 if(context.caseMaterial&&data.case_material!==context.caseMaterial)throw Error('invalid-response');
 if(data.model!==context.model||context.orderId&&data.reference!==context.orderId||!Array.isArray(data.results)||data.page!==page||typeof data.has_more!=='boolean'||typeof data.applicable!=='boolean'||typeof data.bound!=='boolean')throw Error('invalid-response');
 const identities=new Set();
 for(const s of data.results){
  const key=s.shop_id+':'+s.device_id;
  if(!/^\d{1,40}$/.test(s.device_id)||!/^\d{1,40}$/.test(s.shop_id)||typeof s.name!=='string'||typeof s.location!=='string'||!['available','out_of_stock','updating','unsupported','unavailable'].includes(s.availability)||identities.has(key)||s.availability==='available'&&(!Number.isSafeInteger(s.quantity)||s.quantity<=0||!Number.isFinite(Date.parse(s.updated_at))))throw Error('invalid-response');
  identities.add(key);
 }
 return data;
}
export function createStationFinder({load=loadPrintStations,onChange=()=>{},now=Date.now}={}){
 let generation=0,context=null;
 let state={key:'',rows:[],busy:false,error:false,loadedAt:0,page:0,hasMore:false,bound:false,applicable:true};
 async function refresh(more=false){
  if(!context||state.busy)return;
  const current=context,version=++generation,page=more?state.page+1:1;
  state={...state,busy:true,error:false};onChange();
  try{
   const data=await load(current,page);if(version!==generation)return;
   const combined=more?[...state.rows,...data.results]:data.results;
   state={...state,rows:[...new Map(combined.map(s=>[s.shop_id+':'+s.device_id,s])).values()],busy:false,error:false,loadedAt:more?state.loadedAt:now(),page,hasMore:data.has_more,bound:data.bound,applicable:data.applicable};
  }catch{if(version!==generation)return;state={...state,busy:false,error:true};}
  onChange();
 }
 function setContext(value){
  if((value?.key||'')===state.key)return;
  ++generation;context=value;state={key:value?.key||'',rows:[],busy:false,error:false,loadedAt:0,page:0,hasMore:false,bound:false,applicable:true};
  if(value)void refresh();
 }
 return {setContext,refresh,get state(){return state;}};
}
export function stationFinderPanel(state,{model,lang='en-US',position=null,locating=false,locationError='',openMaps=new Set(),selectable=false,selectedKey='',search='',now=Date.now()}={}){
 if(state.applicable===false)return '';
 const zh=lang==='zh-CN',say=(en,cn)=>zh?cn:en;
 const stale=!state.loadedAt||now-state.loadedAt>60000||state.error;
 const currentPosition=position&&now-position.acquiredAt<300000?position:null;
 const query=search.trim().toLowerCase();
 const rows=state.rows.filter(s=>(!query||[s.name,s.location,s.device_id].join(' ').toLowerCase().includes(query))&&validCoordinates(s.coordinates)&&s.coordinates.coordinate_type==='WGS84').map((s,index)=>({...s,index,distance:distanceKm(currentPosition,s.coordinates)})).sort((a,b)=>(a.distance??Infinity)-(b.distance??Infinity)||a.index-b.index);
 const errors={denied:say('Location permission is off. Allow location for this site in your browser or system settings, then retry. You can still browse addresses.','定位权限未开启。请在浏览器或系统设置中允许此网站定位，再重试；仍可查看网点地址。'),timeout:say('Location timed out. Please retry.','定位超时，请重试。'),unsupported:say('This browser cannot provide location. You can still browse stations.','当前浏览器不支持定位，仍可查看网点。'),unavailable:say('Location is unavailable. Please retry or browse addresses.','暂时无法定位，请重试或查看地址。')};
 const items=rows.map(s=>{
  const distance=s.distance==null?say(currentPosition?'Distance unavailable':'Enable location to see distance',currentPosition?'暂无距离信息':'授权定位后显示距离'):say(`Approx. ${s.distance<1?Math.max(50,Math.round(s.distance*1000/50)*50)+' m':s.distance.toFixed(1)+' km'} · straight-line`, `约 ${s.distance<1?Math.max(50,Math.round(s.distance*1000/50)*50)+' 米':s.distance.toFixed(1)+' 公里'} · 直线距离`);
  const labels={available:stale?say(`Last recorded stock: ${s.quantity}`,`上次记录：库存 ${s.quantity}`):say(`${s.quantity} in stock`,`库存 ${s.quantity}`),out_of_stock:say('This model is out of stock','该机型暂时缺货'),updating:say('Stock needs updating','库存待更新'),unsupported:say('This model is not supported','暂无该机型'),unavailable:say('Printing is unavailable','暂不可打印')};
  const navigation=!stale&&s.availability==='available'?stationNavigation(s,{lang,compact:true}).replace('<details class="station-navigation">','<details class="station-navigation"'+(openMaps.has(s.shop_id+':'+s.device_id)?' open':'')+'>'):'';
  return `<li class="pickup-station-row" data-station-key="${esc(s.shop_id+':'+s.device_id)}"><div class="pickup-row-heading"><strong>${esc(s.name)}</strong><span class="pickup-distance">${esc(distance)}</span></div><p class="pickup-row-address">${esc(s.location||say('Station address not provided','网点地址未填写'))}</p><div class="pickup-row-actions"><span class="pickup-stock">${esc(labels[s.availability])}</span>${navigation}${selectable?`<button type="button" class="station-select button primary" data-action="select-station" data-station-key="${esc(s.shop_id+':'+s.device_id)}" ${stale||state.busy||s.availability!=='available'?'disabled':''}>${say(selectedKey===s.shop_id+':'+s.device_id?'Selected':'Choose station',selectedKey===s.shop_id+':'+s.device_id?'已选择':'选择此网点')}</button>`:''}</div><small>${say('Stock updated','库存更新')}：${Number.isFinite(Date.parse(s.updated_at))?esc(new Date(s.updated_at).toLocaleString(lang)):say('Unknown','未知')}</small></li>`;
 }).join('');
 return `<section class="pickup-stations" aria-label="${say('Stations with your phone model','有该机型库存的网点')}"><h3>${state.bound?say('Your assigned station','订单绑定网点'):say('Stations with your phone model','有该机型库存的网点')}</h3><p>${esc(model)}</p><div class="pickup-station-actions"><button type="button" class="text-button" data-action="locate-stations" ${locating?'disabled':''}>${locating?say('Locating…','正在定位…'):currentPosition?say('Update my location','更新我的位置'):say('Use my location for distance','获取位置，查看距离')}</button><button type="button" class="text-button" data-action="refresh-stations" ${state.busy?'disabled':''}>${say('Refresh stock','刷新库存')}</button></div><p class="field-note">${say('Location is used only on this page to calculate straight-line distance, not driving distance.','位置仅在当前页面计算直线距离，不代表驾车距离。')}${currentPosition&&Number.isFinite(position.accuracy)?say(` Location accuracy: about ${Math.ceil(position.accuracy)} m.`,` 定位精度约 ${Math.ceil(position.accuracy)} 米。`):''}</p>${locationError?`<p role="status">${esc(errors[locationError]||errors.unavailable)}</p>`:''}${state.busy?`<p role="status">${say('Checking station stock…','正在查询网点库存…')}</p>`:''}${state.error?`<p class="error" role="status">${say('Stock could not be refreshed. Refresh before choosing navigation.','库存查询失败，请刷新后再选择导航。')}</p>`:stale&&state.loadedAt?`<p role="status">${say('Stock needs refreshing before navigation.','库存信息需要刷新后再导航。')}</p>`:''}${items?`<ul class="pickup-station-list">${items}</ul>`:''}${!state.busy&&!state.error&&!rows.length?`<p>${query?say('No matching stations in the loaded list. Try another name or address.','已加载列表中没有匹配网点，请尝试其他名称或地址。'):say('No stations with valid locations and available stock for this model were found. Please refresh later or contact support.','暂未找到已配置位置且有该机型库存的网点，请稍后刷新或联系客服。')}</p>`:''}${state.hasMore?`<p class="field-note">${say('Distances are sorted within the stations loaded so far.','当前按已加载网点的直线距离排序。')}</p><button type="button" class="text-button" data-action="more-stations" ${state.busy?'disabled':''}>${say('Load more stations','加载更多网点')}</button>`:''}<p class="field-note">${say('Stock is not reserved. Scan the station QR code when you arrive and confirm before sending your order. Stock is checked again before printing.','库存不预留。到达后扫描设备二维码，确认后再推单；打印前仍会核验库存。')}</p></section>`;
}
