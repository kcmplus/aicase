import test from 'node:test';
import assert from 'node:assert/strict';
import {deviceInfoScope,loadDeviceInfo,scopedDesignUrl} from '../storefront/device-info-service.js';
const scope={deviceId:'401',shopId:'146'};
test('device scope requires merchant and device without demo fallback',()=>{
 assert.deepEqual(deviceInfoScope('?device_id=401&shop_id=146'),scope);
 assert.deepEqual(deviceInfoScope('',{deviceId:401,shopId:146}),scope);
 for(const search of ['?device_id=401','?device_id=x&shop_id=146','?device_id=&shop_id=146'])assert.throws(()=>deviceInfoScope(search));
});
test('QR is device scoped and cannot send customers to loopback or carry unrelated secrets',()=>{
 const value=scopedDesignUrl('https://shop.example',undefined,scope,'zh-CN');
 const url=new URL(value);
 assert.equal(url.searchParams.get('device_id'),'401');assert.equal(url.searchParams.get('shop_id'),'146');
 assert.equal(url.hash,'#home');
 assert.equal(scopedDesignUrl('http://127.0.0.1:4173',null,scope,'en-US'),null);
 assert.equal(scopedDesignUrl('https://shop.example','javascript:alert(1)',scope,'en-US'),null);
 assert.equal(scopedDesignUrl('https://shop.example','https://user:pass@shop.example',scope,'en-US'),null);
 assert.ok(!scopedDesignUrl('https://shop.example','/?token=private',scope,'en-US').includes('private'));
});
test('real device reads are anonymous and mismatched identities fail closed',async()=>{
 const data={device_id:'401',shop_id:'146',name:'Station',models:[],inventory:{availability:'empty',model_count:0},fulfillment_connected:false};
 assert.deepEqual(await loadDeviceInfo(scope,async(url,opts)=>{
  assert.equal(url,'/api/v1/store/device-info/?device_id=401&shop_id=146');assert.equal(opts.credentials,'omit');
  return {ok:true,json:async()=>data};
 }),data);
 await assert.rejects(loadDeviceInfo(scope,async()=>({ok:true,json:async()=>({...data,device_id:'400'})})));
 await assert.rejects(loadDeviceInfo(scope,async()=>({ok:false,status:404})),/device-unavailable/);
});
