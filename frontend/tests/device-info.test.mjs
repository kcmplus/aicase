import test from 'node:test';
import assert from 'node:assert/strict';
import {deviceInfoScope,loadDeviceInfo,scopedDesignUrl} from '../storefront/device-info-service.js';
import {stationNavigationLinks,stationNavigation} from '../storefront/station-navigation.js';
const scope={deviceId:'401',shopId:'146'};
test('device scope requires merchant and device without demo fallback',()=>{
 assert.deepEqual(deviceInfoScope('?device_id=401&shop_id=146'),scope);
 assert.deepEqual(deviceInfoScope('',{deviceId:401,shopId:146}),scope);
 for(const search of ['?device_id=401','?device_id=x&shop_id=146','?device_id=&shop_id=146'])assert.throws(()=>deviceInfoScope(search));
});

test('device info retries only temporary 503 reads and preserves identity checks',async()=>{
 const data={device_id:'401',shop_id:'146',name:'Station',models:[],inventory:{availability:'empty',model_count:0},fulfillment_connected:false};
 let calls=0;const delays=[];
 const loaded=await loadDeviceInfo(scope,async()=>++calls<3?{ok:false,status:503}:{ok:true,json:async()=>data},{sleep:async ms=>delays.push(ms)});
 assert.equal(loaded,data);assert.equal(calls,3);assert.deepEqual(delays,[1000,2000]);
 calls=0;
 await assert.rejects(loadDeviceInfo(scope,async()=>{calls++;return {ok:false,status:503};},{sleep:async()=>{}}),/connection/);
 assert.equal(calls,4);
 calls=0;
 await assert.rejects(loadDeviceInfo(scope,async()=>{calls++;return {ok:true,json:async()=>({...data,shop_id:'351'})};},{sleep:async()=>{}}),/invalid-response/);
 assert.equal(calls,1);
 await assert.rejects(loadDeviceInfo(scope,async()=>({ok:false,status:400})),/invalid-device/);
 const invalid=await loadDeviceInfo(scope,async()=>({ok:true,json:async()=>({...data,coordinates:{latitude:91,longitude:1,coordinate_type:'WGS84'}})}));
 assert.equal(invalid.name,'Station');assert.equal(invalid.coordinates,null);
});

test('navigation offers only Google and Apple with the exact WGS84 destination',()=>{
 const device={name:'高玥 & 测试',location:'广州小蛮腰',coordinates:{latitude:'23.109611405810412',longitude:'113.31919351869149',coordinate_type:'WGS84'}};
 const links=Object.fromEntries(stationNavigationLinks(device).map(l=>[l.id,new URL(l.url)]));
 assert.deepEqual(Object.keys(links),['google','apple']);
 assert.equal(links.google.searchParams.get('destination'),'23.109611405810412,113.31919351869149');
 assert.equal(links.apple.searchParams.get('destination'),links.google.searchParams.get('destination'));
 for(const value of Object.values(links)){assert.equal(value.protocol,'https:');assert.equal(value.searchParams.has('origin'),false);}
 const html=stationNavigation({...device,name:'<script>alert(1)</script>'},{lang:'zh-CN'});
 assert.ok(html.includes('Google 地图'));assert.ok(html.includes('Apple 地图'));assert.doesNotMatch(html,/高德|百度|amap|baidu/);assert.ok(html.includes('rel="noopener noreferrer"'));assert.ok(!html.includes('<script>'));
 assert.deepEqual(stationNavigationLinks({...device,coordinates:null}),[]);
 for(const latitude of [null,true,'',NaN,Infinity,91,[],{}])assert.deepEqual(stationNavigationLinks({...device,coordinates:{...device.coordinates,latitude}}),[]);
 assert.deepEqual(stationNavigationLinks({...device,coordinates:{...device.coordinates,coordinate_type:''}}),[]);
 for(const coordinate_type of ['GCJ02','BD09'])assert.deepEqual(stationNavigationLinks({...device,coordinates:{...device.coordinates,coordinate_type}}),[]);
 const overseas=stationNavigationLinks({...device,coordinates:{latitude:-33.9,longitude:151.2,coordinate_type:'WGS84'}});
 assert.equal(new URL(overseas[0].url).searchParams.get('destination'),'-33.9,151.2');
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
