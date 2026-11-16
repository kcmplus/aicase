import test from 'node:test';
import assert from 'node:assert/strict';
import {selectSupplierTemplate} from '../storefront/phone-templates.js';
import {caseStylePicker} from '../storefront/case-styles.js';
import {applyStockCatalog,stockSelection} from '../storefront/stock-catalog.js';
import {createPersonalPass} from '../storefront/simple-core.js';
import {prepareDeviceOrder} from '../storefront/fulfillment-service.js';
import {loadPrintStations} from '../storefront/pickup-stations.js';
const template=id=>({id:'supplier-'+id+'-'+'a'.repeat(20),model:'iPhone Styles',inventoryItemId:id,overlay:'/media/supplier-templates/'+'b'.repeat(64)+'-overlay.png',previewOverlay:'/media/supplier-templates/'+'b'.repeat(64)+'-overlay.png',mask:'/media/supplier-templates/'+'c'.repeat(64)+'-mask.png',sourceWidth:600,sourceHeight:1200,printWidth:600,printHeight:1200,previewOnly:true,dpi:null});
const standard=template(1),magnetic=template(2);
const record={name:'iPhone Styles',brand:'Apple',templateId:standard.id,inventoryItemId:1,styles:[{caseMaterial:'standard',available:true,templateId:standard.id,inventoryItemId:1},{caseMaterial:'magnetic',available:false}]};
test('styles appear after phone selection, unavailable style is greyed and cannot be selected',()=>{
 assert.equal(caseStylePicker(null,''),'');
 const html=caseStylePicker(record,'standard',{lang:'zh-CN',scoped:true});
 assert.match(html,/普通款/);assert.match(html,/磁吸款/);
 assert.match(html,/data-case-material="magnetic" aria-pressed="false" disabled/);
 applyStockCatalog({version:1,scope:'device',models:[record],templates:[standard]});
 assert.equal(stockSelection(record.name,'magnetic'),null);
 assert.equal(stockSelection(record.name,'standard').inventoryItemId,1);
});
test('unscoped styles are selectable without inventory and survive design snapshots',()=>{
 const both={...record,styles:record.styles.map(s=>({...s,available:true}))};
 applyStockCatalog({version:1,scope:'catalog',models:[both],templates:[standard]});
 assert.equal(stockSelection(record.name,'magnetic').templateId,undefined);
 selectSupplierTemplate(record.name,undefined);
 const pass=createPersonalPass({source:'collection',designId:'bloom',model:record.name,caseMaterial:'magnetic',effect:'original',intensity:0,zoom:100,x:50,y:50});
 assert.equal(pass.caseMaterial,'magnetic');
});
test('device binding selects exact style rather than first model stock and will not fall back',async()=>{
 let bound;
 const order={id:'test',mode:'free_test',status:'paid',fulfillmentType:'pickup',pass:{model:record.name,caseMaterial:'magnetic'}};
 const fetcher=async()=>({ok:true,json:async()=>({models:[{...record,styles:[record.styles[0],{caseMaterial:'magnetic',available:true,templateId:magnetic.id,inventoryItemId:2}]}],templates:[standard,magnetic]})});
 await prepareDeviceOrder(order,'device_id=789&shop_id=351',{fetcher,request:async(path,opts)=>{if(opts)bound=opts.body;return {...order,fulfillment:{state:'prepared'}};},save:async v=>v});
 assert.equal(bound.inventory_item_id,2);
 await assert.rejects(prepareDeviceOrder(order,'device_id=789&shop_id=351',{fetcher:async()=>({ok:true,json:async()=>({models:[record],templates:[standard]})}),request:async()=>assert.fail('must not bind')}),/case style/);
});
test('station queries include style and reject a response for another style',async()=>{
 const context={model:record.name,caseMaterial:'magnetic'};
 await assert.rejects(loadPrintStations(context,1,{fetcher:async url=>{assert.ok(url.includes('case_material=magnetic'));return {ok:true,json:async()=>({case_material:'standard'})};}}),/invalid-response/);
});
