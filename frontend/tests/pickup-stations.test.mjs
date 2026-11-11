import test from 'node:test';
import assert from 'node:assert/strict';
import {distanceKm,locateUser,loadPrintStations,createStationFinder,stationFinderPanel} from '../storefront/pickup-stations.js';
const now=Date.now(),stamp=new Date(now).toISOString();
const station={device_id:'401',shop_id:'146',name:'Station',location:'Address',availability:'available',quantity:2,updated_at:stamp,coordinates:{latitude:'0',longitude:'1',coordinate_type:'WGS84'}};
const payload={model:'Test phone',applicable:true,bound:false,results:[station],page:1,has_more:false};

test('straight-line distance handles equator, poles, antimeridian and unsupported coordinates',()=>{
 assert.ok(Math.abs(distanceKm({latitude:0,longitude:0},station.coordinates)-111.195)<0.01);
 assert.equal(distanceKm({latitude:0,longitude:1},station.coordinates),0);
 assert.ok(distanceKm({latitude:0,longitude:179.9},{latitude:0,longitude:-179.9,coordinate_type:'WGS84'})<23);
 assert.ok(Number.isFinite(distanceKm({latitude:90,longitude:180},{latitude:-90,longitude:-180,coordinate_type:'WGS84'})));
 assert.equal(distanceKm({latitude:91,longitude:0},station.coordinates),null);
 assert.equal(distanceKm({latitude:0,longitude:0},{...station.coordinates,coordinate_type:'GCJ02'}),null);
});
test('geolocation is explicit and handles denial, timeout and unsupported browsers',async()=>{
 let options;
 const pos=await locateUser({getCurrentPosition(ok,bad,opts){options=opts;ok({coords:{latitude:23,longitude:113,accuracy:80}});}});
 assert.equal(pos.latitude,23);assert.equal(options.timeout,12000);
 for(const [code,message] of [[1,'denied'],[2,'unavailable'],[3,'timeout']])await assert.rejects(locateUser({getCurrentPosition(ok,bad){bad({code});}}),new RegExp(message));
 await assert.rejects(locateUser(null),/unsupported/);
});
test('station reads never send user location or write supplier orders and validate identities',async()=>{
 const calls=[];
 const fetcher=async (url,options)=>{calls.push({url,options});return {ok:true,json:async()=>payload};};
 await loadPrintStations({model:'Test phone',latitude:23,longitude:113},1,{fetcher});
 assert.ok(!calls[0].url.includes('latitude'));assert.equal(calls[0].options.credentials,'omit');
 const request=async path=>{assert.equal(path,'order-1/stations/?page=1');return {...payload,reference:'order-1'};};
 await loadPrintStations({model:'Test phone',orderId:'order-1'},1,{request});
 await assert.rejects(loadPrintStations({model:'Different'},1,{fetcher}),/invalid-response/);
 await assert.rejects(loadPrintStations({model:'Test phone',orderId:'wrong'},1,{request:async()=>({...payload,reference:'other'})}),/invalid-response/);
});
test('station list sorts distances, escapes content, preserves access without location and disables stale navigation',()=>{
 const state={rows:[{...station,name:'Far'}, {...station,device_id:'402',name:'Near',coordinates:{...station.coordinates,longitude:0.1}}],loadedAt:now};
 const html=stationFinderPanel(state,{model:'Test <phone>',position:{latitude:0,longitude:0,acquiredAt:now,accuracy:40},lang:'zh-CN',now});
 assert.ok(html.indexOf('Near')<html.indexOf('Far'));assert.ok(html.includes('直线距离'));assert.ok(html.includes('库存 2'));assert.ok(html.includes('选择地图导航'));
 assert.ok(!html.includes('Test <phone>'));assert.ok(html.includes('Test &lt;phone&gt;'));
 const noLocation=stationFinderPanel(state,{model:'Test phone',lang:'zh-CN',locationError:'denied',now});
 assert.ok(noLocation.includes('定位权限未开启'));assert.ok(noLocation.includes('选择地图导航'));
 assert.ok(stationFinderPanel(state,{now,openMaps:new Set(['146:401'])}).includes('class="station-navigation" open'));
 for(const modified of [{error:true},{loadedAt:now-61000},{rows:[{...station,availability:'out_of_stock',quantity:0}]}])assert.ok(!stationFinderPanel({...state,...modified},{now}).includes('Choose a map'));
 assert.ok(!stationFinderPanel({...state,error:true},{now}).includes('Choose a map'));
});
test('late responses cannot replace another model and failures retain rows without usable navigation',async()=>{
 let first,fail=false;
 const finder=createStationFinder({now:()=>now,load:async context=>{if(context.model==='Old')return await new Promise(resolve=>{first=resolve;});if(fail)throw Error();return payload;}});
 finder.setContext({key:'old',model:'Old'});finder.setContext({key:'new',model:'Test phone'});
 await new Promise(r=>setTimeout(r,0));
 first({...payload,model:'Old',results:[]});await new Promise(r=>setTimeout(r,0));
 assert.equal(finder.state.key,'new');assert.equal(finder.state.rows.length,1);
 fail=true;await finder.refresh();assert.equal(finder.state.error,true);assert.equal(finder.state.rows.length,1);
 assert.ok(!stationFinderPanel(finder.state,{now}).includes('Choose a map'));
 finder.setContext(null);assert.equal(finder.state.rows.length,0);
});
