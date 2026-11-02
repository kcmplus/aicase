import test from 'node:test';
import assert from 'node:assert/strict';
import {applyStockCatalog,stockedPhoneModels,stockCatalogStatus,loadStockCatalog,stockSelection,deviceScope} from '../storefront/stock-catalog.js';
import {phoneTemplate} from '../storefront/phone-templates.js';
import {createPersonalPass,readPass,stationAvailability} from '../storefront/simple-core.js';
import {savedOrder} from '../storefront/order-service.js';
import {phone} from '../storefront/art.js';
const template={id:'supplier-123-'+ 'a'.repeat(20),model:'Redmi Test 5G',code:'redmi-test',inventoryItemId:123,
 overlay:'/media/supplier-templates/'+'a'.repeat(64)+'-overlay.png',previewOverlay:'/media/supplier-templates/'+'a'.repeat(64)+'-overlay.png',
 mask:'/media/supplier-templates/'+'b'.repeat(64)+'-mask.png',printWidth:600,printHeight:1200,sourceWidth:600,sourceHeight:1200,dpi:null,previewOnly:true,calibrated:false};
const catalog=()=>({version:1,models:[{name:template.model,brand:'Xiaomi',code:'redmi-test',templateId:template.id,inventoryItemId:123}],templates:[template]});

test('stock catalog drives choices and exact supplier overlay, without rewriting legacy indexes',()=>{
 applyStockCatalog(catalog());
 assert.deepEqual(stockedPhoneModels,[template.model]);
 assert.equal(stockSelection(template.model).inventoryItemId,123);
 assert.equal(phoneTemplate(template.model).id,template.id);
 assert.ok(phone({},template.model).includes(template.overlay));
 const pass=createPersonalPass({source:'collection',designId:'bloom',model:template.model,effect:'original',intensity:0,zoom:100,x:50,y:50});
 assert.equal(pass.phoneTemplateId,template.id);
 assert.equal(stationAvailability('DEMO-01',pass).ok,true);
 assert.equal(stationAvailability('DEMO-02',pass).ok,false);
 assert.equal(readPass('POP-1117').model,'iPhone 16 Pro');
 applyStockCatalog({version:1,models:[],templates:[]});
 assert.deepEqual(stockedPhoneModels,[]);
 assert.equal(readPass(pass.code,pass).phoneTemplateId,template.id);
});
test('loading failure clears choices instead of offering bundled or stale models',async()=>{
 applyStockCatalog(catalog());
 assert.equal(await loadStockCatalog(async()=>({ok:false}),'device_id=401'),false);
 assert.deepEqual(stockedPhoneModels,[]);
 assert.equal(stockSelection(template.model),null);
});
test('expired inventory is shown as updating and can recover without reloading the page',async()=>{
 applyStockCatalog({version:1,models:[],templates:[],availability:'updating'});
 assert.equal(stockCatalogStatus,'updating');
 assert.deepEqual(stockedPhoneModels,[]);
 await loadStockCatalog(async()=>({ok:true,json:async()=>catalog()}),'');
 assert.equal(stockCatalogStatus,'ready');
 assert.deepEqual(stockedPhoneModels,[template.model]);
});
test('device scope is forwarded and an empty device result stays empty',async()=>{
 assert.equal(deviceScope({search:'?lang=en-US&device_id=401&shop_id=146',hash:'#choose'}),'device_id=401&shop_id=146');
 assert.equal(deviceScope({search:'',hash:'#choose?device_id=401'}),'device_id=401');
 await loadStockCatalog(async(url)=>{assert.equal(url,'/api/v1/store/phone-models/?device_id=401&shop_id=146');return {ok:true,json:async()=>({version:1,models:[],templates:[]})};},'device_id=401&shop_id=146');
 assert.deepEqual(stockedPhoneModels,[]);
});
test('untrusted asset paths and mismatched template identities are rejected',()=>{
 const invalid=catalog();invalid.templates=[{...template,mask:'https://evil.test/mask.png'}];
 assert.throws(()=>applyStockCatalog(invalid));
 const mismatch=catalog();mismatch.models[0].templateId='wrong';assert.throws(()=>applyStockCatalog(mismatch));
});
test('server orders restore their frozen template after current inventory disappears',()=>{
 const snapshot={version:2,code:'POP-C-0123456789ABCDEF',source:'collection',designId:'bloom',model:template.model,phoneTemplateId:template.id,photo:'',effect:'original',intensity:0,zoom:100,x:50,y:50};
 const order=savedOrder({reference:'order-1',snapshot,phone_template:template,status:'paid',mode:'demo',amount:'10.00',currency:'USD',revision:1});
 assert.equal(order.pass.phoneTemplateId,template.id);
 assert.equal(order.phoneTemplate.mask,template.mask);
});
