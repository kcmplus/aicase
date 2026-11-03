export function deviceInfoScope(search,config={}){
 const query=new URLSearchParams(search);
 const deviceId=query.get('device_id')??String(config.deviceId??'');
 const shopId=query.get('shop_id')??String(config.shopId??'');
 if(!/^\d{1,40}$/.test(deviceId)||!/^\d{1,40}$/.test(shopId))throw Error('invalid-device');
 return {deviceId,shopId};
}
export async function loadDeviceInfo(scope,fetcher=fetch){
 const query=new URLSearchParams({device_id:scope.deviceId,shop_id:scope.shopId});
 const response=await fetcher('/api/v1/store/device-info/?'+query,{credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(15000)});
 if(!response.ok)throw Error(response.status===404?'device-unavailable':'connection');
 const data=await response.json();
 if(data.device_id!==scope.deviceId||data.shop_id!==scope.shopId||typeof data.name!=='string'||
    !Array.isArray(data.models)||!data.models.every(m=>typeof m.name==='string'&&typeof m.brand==='string')||
    !['ready','updating','empty'].includes(data.inventory?.availability)||data.inventory.model_count!==data.models.length||
    data.fulfillment_connected!==false)throw Error('invalid-response');
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
