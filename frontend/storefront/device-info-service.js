import {retryUnavailableRead} from './request-retry.js';
import {validCoordinates} from './station-navigation.js';

export function deviceInfoErrorMessage(error,lang='en-US'){
 const messages={
  'device-unavailable':['This station is not available or its identity is ambiguous. Check the QR code or contact staff.','设备未开放或编号存在冲突，请核对二维码或联系工作人员。'],
  'invalid-device':['The station link is incomplete. Scan the station QR code again.','设备链接不完整，请重新扫描设备二维码。'],
  'invalid-response':['Station details could not be verified. Refresh before confirming your order.','设备资料校验未通过，请刷新后再确认推单。'],
  'connection':['Station details could not be loaded. Check your connection and refresh.','设备信息暂时加载失败，请检查网络后刷新。']
 };
 return (messages[error]||messages.connection)[lang==='zh-CN'?1:0];
}
export function deviceInfoScope(search,config={}){
 const query=new URLSearchParams(search);
 const deviceId=query.get('device_id')??String(config.deviceId??'');
 const shopId=query.get('shop_id')??String(config.shopId??'');
 if(!/^\d{1,40}$/.test(deviceId)||!/^\d{1,40}$/.test(shopId))throw Error('invalid-device');
 return {deviceId,shopId};
}
export async function loadDeviceInfo(scope,fetcher=fetch,retryOptions){
 const query=new URLSearchParams({device_id:scope.deviceId,shop_id:scope.shopId});
 let response;
 try{response=await retryUnavailableRead(()=>fetcher('/api/v1/store/device-info/?'+query,{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(15000)}),retryOptions);}
 catch{throw Error('connection');}
 if(!response.ok)throw Error(response.status===404?'device-unavailable':response.status===400?'invalid-device':'connection');
 const data=await response.json();
 if(data.device_id!==scope.deviceId||data.shop_id!==scope.shopId||typeof data.name!=='string'||
    (data.location!==undefined&&(typeof data.location!=='string'||data.location.length>403))||
    (data.number!==undefined&&(typeof data.number!=='string'||data.number.length>120))||
    !Array.isArray(data.models)||!data.models.every(m=>typeof m.name==='string'&&typeof m.brand==='string')||
    !['ready','updating','empty'].includes(data.inventory?.availability)||data.inventory.model_count!==data.models.length||
    data.fulfillment_connected!==false)throw Error('invalid-response');
 if(data.coordinates!=null&&!validCoordinates(data.coordinates))data.coordinates=null;
 return data;
}
export function scopedDesignUrl(origin,configured,scope,lang){
 try{
  const url=new URL(configured||'/',origin);
  if(!['https:','http:'].includes(url.protocol)||url.username||url.password)return null;
  // A QR containing loopback would send the customer's phone to itself.
  if(['localhost','127.0.0.1','[::1]'].includes(url.hostname))return null;
  url.search='';url.hash='home';
  for(const [key,value] of Object.entries({device_id:scope.deviceId,shop_id:scope.shopId,lang}))url.searchParams.set(key,value);
  return url.href;
 }catch{return null;}
}
